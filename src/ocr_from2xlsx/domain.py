from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ocr_from2xlsx.constants import SCHEMA_VERSION


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ValueError(f"{field_name} must be an object")


def _require_list(value: Any, field_name: str, item_type: type | None = None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        if item_type is not None:
            label = "string" if item_type is str else item_type.__name__
            for index, item in enumerate(value):
                if not isinstance(item, item_type):
                    raise ValueError(f"{field_name}[{index}] must be a {label}")
        return value
    raise ValueError(f"{field_name} must be a list")


def _require_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a bool")


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    raise ValueError(f"{field_name} must be a string")


def _lenient_string(value: Any, field_name: str) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    raise ValueError(f"{field_name} must be a string")


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    trimmed = value.strip()
    if trimmed == "":
        raise ValueError(f"{field_name} is required")
    return trimmed


def _optional_bool(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a bool")


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{field_name} must be a number")


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an int")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ValueError(f"{field_name} must be an int")


def _require_float_map(value: Any, field_name: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    result: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{field_name}.{key} must be a number")
        result[key] = float(item)
    return result


def _require_consultation(value: Any, field_name: str) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    consultation: dict[str, list[str]] = {}
    for category, values in value.items():
        items = _require_list(values, f"{field_name}.{category}", item_type=str)
        consultation[str(category)] = items
    return consultation


@dataclass(slots=True)
class SourceInfo:
    kind: str | None = None
    document_path: str | None = None
    page_number: int | None = None
    image_path: str | None = None
    preprocessed_image_path: str | None = None
    capture_time: str | None = None
    template_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceInfo":
        data = _require_dict(data, "source")
        return cls(
            kind=_optional_string(data.get("kind"), "source.kind"),
            document_path=_optional_string(data.get("document_path"), "source.document_path"),
            page_number=_optional_int(data.get("page_number"), "source.page_number"),
            image_path=_optional_string(data.get("image_path"), "source.image_path"),
            preprocessed_image_path=_optional_string(
                data.get("preprocessed_image_path"),
                "source.preprocessed_image_path",
            ),
            capture_time=_optional_string(data.get("capture_time"), "source.capture_time"),
            template_id=_optional_string(data.get("template_id"), "source.template_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "document_path": self.document_path,
            "page_number": self.page_number,
            "image_path": self.image_path,
            "preprocessed_image_path": self.preprocessed_image_path,
            "capture_time": self.capture_time,
            "template_id": self.template_id,
        }


@dataclass(slots=True)
class PatientFields:
    nationality: str | None = None
    age_group: str | None = None
    channel: str | None = None
    disease_status: str | None = None
    source: str | None = None
    cancers: list[str] = field(default_factory=list)
    newly_diagnosed_within_year: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PatientFields":
        data = _require_dict(data, "patient_fields")
        return cls(
            nationality=_optional_string(data.get("nationality"), "patient_fields.nationality"),
            age_group=_optional_string(data.get("age_group"), "patient_fields.age_group"),
            channel=_optional_string(data.get("channel"), "patient_fields.channel"),
            disease_status=_optional_string(data.get("disease_status"), "patient_fields.disease_status"),
            source=_optional_string(data.get("source"), "patient_fields.source"),
            cancers=_require_list(data.get("cancers"), "patient_fields.cancers", item_type=str),
            newly_diagnosed_within_year=_optional_bool(
                data.get("newly_diagnosed_within_year"),
                "patient_fields.newly_diagnosed_within_year",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nationality": self.nationality,
            "age_group": self.age_group,
            "channel": self.channel,
            "disease_status": self.disease_status,
            "source": self.source,
            "cancers": list(self.cancers),
            "newly_diagnosed_within_year": self.newly_diagnosed_within_year,
        }


@dataclass(slots=True)
class Services:
    consultation: dict[str, list[str]] = field(default_factory=dict)
    supplies: list[str] = field(default_factory=list)
    internal_referrals: list[str] = field(default_factory=list)
    external_referrals: list[str] = field(default_factory=list)
    referral_outcomes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Services":
        data = _require_dict(data, "services")
        return cls(
            consultation=_require_consultation(data.get("consultation"), "services.consultation"),
            supplies=_require_list(data.get("supplies"), "services.supplies", item_type=str),
            internal_referrals=_require_list(data.get("internal_referrals"), "services.internal_referrals", item_type=str),
            external_referrals=_require_list(data.get("external_referrals"), "services.external_referrals", item_type=str),
            referral_outcomes=_require_list(data.get("referral_outcomes"), "services.referral_outcomes", item_type=str),
        )

    def summary(self) -> str:
        parts: list[str] = []
        for category in sorted(self.consultation):
            for code in sorted(self.consultation[category]):
                parts.append(f"{category}:{code}")
        for name, values in [
            ("supplies", self.supplies),
            ("internal", self.internal_referrals),
            ("external", self.external_referrals),
            ("outcomes", self.referral_outcomes),
        ]:
            for code in sorted(values):
                parts.append(f"{name}:{code}")
        return "|".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "consultation": {key: list(values) for key, values in self.consultation.items()},
            "supplies": list(self.supplies),
            "internal_referrals": list(self.internal_referrals),
            "external_referrals": list(self.external_referrals),
            "referral_outcomes": list(self.referral_outcomes),
        }


@dataclass(slots=True)
class OcrInfo:
    backend: str = ""
    model: str = ""
    confidence: float | None = None
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)
    field_confidences: dict[str, float] = field(default_factory=dict)
    name_crop: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OcrInfo":
        data = _require_dict(data, "ocr")
        return cls(
            backend=_lenient_string(data.get("backend"), "ocr.backend"),
            model=_lenient_string(data.get("model"), "ocr.model"),
            confidence=_optional_float(data.get("confidence"), "ocr.confidence"),
            raw_text=_lenient_string(data.get("raw_text"), "ocr.raw_text"),
            warnings=_require_list(data.get("warnings"), "ocr.warnings", item_type=str),
            field_confidences=_require_float_map(data.get("field_confidences"), "ocr.field_confidences"),
            name_crop=_optional_string(data.get("name_crop"), "ocr.name_crop"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "backend": self.backend,
            "model": self.model,
            "raw_text": self.raw_text,
            "warnings": list(self.warnings),
            "field_confidences": dict(self.field_confidences),
        }
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.name_crop is not None:
            result["name_crop"] = self.name_crop
        return result


@dataclass(slots=True)
class ReviewInfo:
    status: str = "pending"
    edited_by_user: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReviewInfo":
        data = _require_dict(data, "review")
        if "edited_by_user" in data:
            edited_by_user = _require_bool(data.get("edited_by_user"), "review.edited_by_user")
        else:
            edited_by_user = False
        return cls(status=_lenient_string(data.get("status"), "review.status"), edited_by_user=edited_by_user)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "edited_by_user": self.edited_by_user,
        }


@dataclass(slots=True)
class Record:
    record_id: str
    service_date: str
    identity: str
    name: str
    medical_record_no: str
    gender: str
    source: SourceInfo = field(default_factory=SourceInfo)
    birthdate: str | None = None
    patient_fields: PatientFields = field(default_factory=PatientFields)
    services: Services = field(default_factory=Services)
    discharge_followup: bool | None = None
    notes: str = ""
    ocr: OcrInfo = field(default_factory=OcrInfo)
    review: ReviewInfo = field(default_factory=ReviewInfo)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        data = _require_dict(data, "record")
        record_id = _require_non_empty_string(data.get("record_id"), "record_id")
        return cls(
            record_id=record_id,
            source=SourceInfo.from_dict(data.get("source")),
            service_date=_lenient_string(data.get("service_date"), "service_date"),
            identity=_lenient_string(data.get("identity"), "identity"),
            name=_lenient_string(data.get("name"), "name"),
            medical_record_no=_lenient_string(data.get("medical_record_no"), "medical_record_no"),
            birthdate=_optional_string(data.get("birthdate"), "birthdate"),
            gender=_lenient_string(data.get("gender"), "gender"),
            patient_fields=PatientFields.from_dict(data.get("patient_fields")),
            services=Services.from_dict(data.get("services")),
            discharge_followup=_optional_bool(data.get("discharge_followup"), "discharge_followup"),
            notes=_lenient_string(data.get("notes"), "notes"),
            ocr=OcrInfo.from_dict(data.get("ocr")),
            review=ReviewInfo.from_dict(data.get("review")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "service_date": self.service_date,
            "identity": self.identity,
            "name": self.name,
            "medical_record_no": self.medical_record_no,
            "gender": self.gender,
            "source": self.source.to_dict(),
            "birthdate": self.birthdate,
            "patient_fields": self.patient_fields.to_dict(),
            "services": self.services.to_dict(),
            "discharge_followup": self.discharge_followup,
            "notes": self.notes,
            "ocr": self.ocr.to_dict(),
            "review": self.review.to_dict(),
        }

    def service_month_label(self) -> str:
        if not self.service_date:
            raise ValueError("service_date is required to calculate service month")
        try:
            parsed = date.fromisoformat(self.service_date)
        except ValueError as exc:
            raise ValueError(f"Invalid service_date: {self.service_date!r}") from exc
        return f"{parsed.month}月"

    def duplicate_key(self) -> tuple[str, str, str, str]:
        return (self.service_date, self.name.strip(), self.medical_record_no.strip(), self.services.summary())


@dataclass(slots=True)
class SourceBatch:
    created_at: str
    source_type: str
    template_name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceBatch":
        data = _require_dict(data, "source_batch")
        return cls(
            created_at=_lenient_string(data.get("created_at"), "source_batch.created_at"),
            source_type=_lenient_string(data.get("source_type"), "source_batch.source_type"),
            template_name=_lenient_string(data.get("template_name"), "source_batch.template_name"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "source_type": self.source_type,
            "template_name": self.template_name,
        }


@dataclass(slots=True)
class Batch:
    source_batch: SourceBatch
    records: list[Record]
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Batch":
        if "schema_version" in data and data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema_version: {data.get('schema_version')!r}")
        if "records" in data:
            records_value = data.get("records")
            if not isinstance(records_value, list):
                raise ValueError("records must be a list")
        else:
            records_value = []
        records: list[Record] = []
        for index, item in enumerate(records_value):
            if not isinstance(item, dict):
                raise ValueError(f"records[{index}] must be an object")
            records.append(Record.from_dict(item))
        return cls(
            schema_version=SCHEMA_VERSION,
            source_batch=SourceBatch.from_dict(data.get("source_batch")),
            records=records,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_batch": self.source_batch.to_dict(),
            "records": [record.to_dict() for record in self.records],
        }
