from __future__ import annotations

from ocr_from2xlsx.sample_data import generate_sample_batch


def test_generates_100_records_with_required_mix() -> None:
    batch = generate_sample_batch(count=100, template_name="template.xlsx")

    assert len(batch.records) == 100
    assert {record.identity for record in batch.records} == {"patient", "family_caregiver", "public_other"}
    assert {record.gender for record in batch.records} == {"female", "male", "other"}
    assert {record.service_date[5:7] for record in batch.records} == {
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
    }


def test_sample_includes_duplicates_and_invalid_cases() -> None:
    batch = generate_sample_batch(count=100, template_name="template.xlsx")
    keys = [record.duplicate_key() for record in batch.records]
    missing_dates = [record for record in batch.records if not record.service_date]
    low_confidence = [
        record for record in batch.records if record.ocr.confidence is not None and record.ocr.confidence < 0.7
    ]

    assert len(set(keys)) < len(keys)
    assert missing_dates
    assert low_confidence
