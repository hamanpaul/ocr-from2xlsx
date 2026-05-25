from __future__ import annotations

from ocr_from2xlsx.sample_data import generate_sample_batch


def test_generates_100_records_with_required_mix() -> None:
    batch = generate_sample_batch(count=100, template_name="template.xlsx")

    assert len(batch.records) == 100
    assert {record.identity for record in batch.records} == {"patient", "family_caregiver", "public_other"}
    assert {record.gender for record in batch.records} == {"female", "male", "other"}
    assert {record.service_date[5:7] for record in batch.records if record.service_date} == {
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
    record_ids = [record.record_id for record in batch.records]
    missing_dates = [record for record in batch.records if not record.service_date]
    low_confidence = [
        record for record in batch.records if record.ocr.confidence is not None and record.ocr.confidence < 0.7
    ]
    duplicate_groups: dict[tuple[str, str, str, str], list[str]] = {}
    for record in batch.records:
        duplicate_groups.setdefault(record.duplicate_key(), []).append(record.record_id)

    assert len(set(keys)) < len(keys)
    assert len(set(record_ids)) == len(record_ids)
    assert batch.records[0].record_id == "sample-0001"
    assert any(len(ids) > 1 for ids in duplicate_groups.values())
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
