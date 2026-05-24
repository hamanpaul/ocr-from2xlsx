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


def test_non_patient_records_have_empty_patient_fields() -> None:
    batch = generate_sample_batch(count=30, template_name="template.xlsx")
    non_patient_records = [record for record in batch.records if record.identity != "patient"]

    assert non_patient_records
    for record in non_patient_records:
        fields = record.patient_fields
        assert fields.cancers == []
        assert fields.nationality is None
        assert fields.age_group is None
        assert fields.channel is None
        assert fields.disease_status is None
        assert fields.source is None
        assert fields.newly_diagnosed_within_year is None


def test_generate_sample_batch_is_deterministic() -> None:
    first = generate_sample_batch(count=100, template_name="template.xlsx").to_dict()
    second = generate_sample_batch(count=100, template_name="template.xlsx").to_dict()

    assert first == second
