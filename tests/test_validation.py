from __future__ import annotations

from tests.test_json_io import make_record

from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.validation import validate_batch, validate_record


def test_patient_requires_patient_fields() -> None:
    record = make_record()
    record.patient_fields.age_group = None

    result = validate_record(record)

    assert "patient.age_group.required" in result.blockers


def test_non_patient_does_not_require_patient_fields() -> None:
    record = make_record()
    record.identity = "family_caregiver"
    record.patient_fields.age_group = None
    record.patient_fields.cancers = []

    result = validate_record(record)

    assert result.blockers == []


def test_duplicate_in_batch_blocks_second_record() -> None:
    first = make_record("scan-0001")
    second = make_record("scan-0002")
    batch = Batch(
        source_batch=SourceBatch(
            created_at="2026-05-24T00:00:00+08:00",
            source_type="manual",
            template_name="template.xlsx",
        ),
        records=[first, second],
    )

    results = validate_batch(batch)

    assert results["scan-0001"].blockers == []
    assert "duplicate.in_batch" in results["scan-0002"].blockers


def test_duplicate_record_id_preserves_all_results() -> None:
    first = make_record("scan-0001")
    second = make_record("scan-0001")
    second.service_date = "2026-03-16"
    batch = Batch(
        source_batch=SourceBatch(
            created_at="2026-05-24T00:00:00+08:00",
            source_type="manual",
            template_name="template.xlsx",
        ),
        records=[first, second],
    )

    results = validate_batch(batch)

    assert len(results) == 2
    assert "scan-0001" in results
    assert "scan-0001#2" in results
    assert "record_id.duplicate_in_batch" in results["scan-0001#2"].blockers


def test_incomplete_duplicate_key_skips_in_batch_check() -> None:
    first = make_record("scan-0001")
    second = make_record("scan-0002")
    for record in (first, second):
        record.service_date = ""
        record.name = ""
        record.medical_record_no = ""
    batch = Batch(
        source_batch=SourceBatch(
            created_at="2026-05-24T00:00:00+08:00",
            source_type="manual",
            template_name="template.xlsx",
        ),
        records=[first, second],
    )

    results = validate_batch(batch)

    assert "duplicate.in_batch" not in results["scan-0001"].blockers
    assert "duplicate.in_batch" not in results["scan-0002"].blockers


def test_incomplete_duplicate_key_skips_existing_check() -> None:
    record = make_record()
    record.service_date = ""
    record.name = ""
    record.medical_record_no = ""

    result = validate_record(record, {record.duplicate_key()})

    assert "duplicate.existing_workbook" not in result.blockers
    assert "service_date.invalid" in result.blockers


def test_low_confidence_is_warning_not_blocker() -> None:
    record = make_record()
    record.ocr.confidence = 0.55

    result = validate_record(record)

    assert result.blockers == []
    assert "ocr.low_confidence" in result.warnings


def test_missing_service_date_is_blocker() -> None:
    record = make_record()
    record.service_date = None  # type: ignore[assignment] - testing missing value handling

    result = validate_record(record)

    assert "service_date.invalid" in result.blockers
