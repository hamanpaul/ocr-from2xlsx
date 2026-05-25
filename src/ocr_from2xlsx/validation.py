from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ocr_from2xlsx.constants import (
    GENDERS,
    IDENTITIES,
    OUTCOME_CODES,
    PATIENT_ENUMS,
    RESOURCE_CODES,
    REVIEW_STATUSES,
    SERVICE_CATEGORIES,
    SUPPLY_CODES,
)
from ocr_from2xlsx.domain import Batch, Record


@dataclass(slots=True)
class ValidationResult:
    record_id: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def can_auto_confirm(self) -> bool:
        return not self.blockers


def validate_record(
    record: Record,
    existing_duplicate_keys: set[tuple[str, str, str, str]] | None = None,
) -> ValidationResult:
    result = ValidationResult(record_id=record.record_id)

    try:
        date.fromisoformat(record.service_date)
    except (TypeError, ValueError):
        result.blockers.append("service_date.invalid")

    if record.identity not in IDENTITIES:
        result.blockers.append("identity.invalid")
    if record.gender not in GENDERS:
        result.blockers.append("gender.invalid")
    if record.review.status not in REVIEW_STATUSES:
        result.blockers.append("review.status.invalid")

    _validate_services(record, result)

    if record.identity == "patient":
        _validate_patient_fields(record, result)
    elif _has_patient_field_values(record):
        result.warnings.append("non_patient.patient_fields_present")

    if record.ocr.confidence is not None and record.ocr.confidence < 0.7:
        result.warnings.append("ocr.low_confidence")

    if existing_duplicate_keys and _duplicate_key_is_usable(record):
        if record.duplicate_key() in existing_duplicate_keys:
            result.blockers.append("duplicate.existing_workbook")

    return result


def validate_batch(
    batch: Batch,
    existing_duplicate_keys: set[tuple[str, str, str, str]] | None = None,
) -> dict[str, ValidationResult]:
    seen: set[tuple[str, str, str, str]] = set()
    record_id_counts: dict[str, int] = {}
    results: dict[str, ValidationResult] = {}
    existing_duplicate_keys = existing_duplicate_keys or set()
    for record in batch.records:
        result = validate_record(record, existing_duplicate_keys)
        if _duplicate_key_is_usable(record):
            key = record.duplicate_key()
            if key in seen:
                result.blockers.append("duplicate.in_batch")
            else:
                seen.add(key)
        record_id_counts[record.record_id] = record_id_counts.get(record.record_id, 0) + 1
        occurrence = record_id_counts[record.record_id]
        if occurrence > 1:
            _append_unique(result.blockers, "record_id.duplicate_in_batch")
            first_result = results.get(record.record_id)
            if first_result is not None:
                _append_unique(first_result.blockers, "record_id.duplicate_in_batch")
        result_key = record.record_id if occurrence == 1 else f"{record.record_id}#{occurrence}"
        results[result_key] = result
    return results


def _validate_patient_fields(record: Record, result: ValidationResult) -> None:
    fields = record.patient_fields
    required = {
        "nationality": fields.nationality,
        "age_group": fields.age_group,
        "channel": fields.channel,
        "disease_status": fields.disease_status,
        "source": fields.source,
    }
    for name, value in required.items():
        if value is None:
            result.blockers.append(f"patient.{name}.required")
        elif value not in PATIENT_ENUMS[name]:
            result.blockers.append(f"patient.{name}.invalid")
    if not fields.cancers:
        result.blockers.append("patient.cancers.required")


def _has_patient_field_values(record: Record) -> bool:
    fields = record.patient_fields
    return any(
        [
            fields.nationality,
            fields.age_group,
            fields.channel,
            fields.disease_status,
            fields.source,
            fields.cancers,
            fields.newly_diagnosed_within_year is not None,
        ]
    )


def _validate_services(record: Record, result: ValidationResult) -> None:
    for category, codes in record.services.consultation.items():
        if category not in SERVICE_CATEGORIES:
            result.blockers.append(f"service.consultation.{category}.unknown")
            continue
        for code in codes:
            if code not in SERVICE_CATEGORIES[category]:
                result.blockers.append(f"service.consultation.{category}.{code}.invalid")
    for code in record.services.supplies:
        if code not in SUPPLY_CODES:
            result.blockers.append(f"service.supplies.{code}.invalid")
    for code in record.services.internal_referrals:
        if code not in RESOURCE_CODES:
            result.blockers.append(f"service.internal_referrals.{code}.invalid")
    for code in record.services.external_referrals:
        if code not in RESOURCE_CODES:
            result.blockers.append(f"service.external_referrals.{code}.invalid")
    for code in record.services.referral_outcomes:
        if code not in OUTCOME_CODES:
            result.blockers.append(f"service.referral_outcomes.{code}.invalid")


def _duplicate_key_is_usable(record: Record) -> bool:
    if not record.service_date:
        return False
    try:
        date.fromisoformat(record.service_date)
    except (TypeError, ValueError):
        return False
    if not record.name or not record.name.strip():
        return False
    if not record.medical_record_no or not record.medical_record_no.strip():
        return False
    return True


def _append_unique(values: list[str], item: str) -> None:
    if item not in values:
        values.append(item)
