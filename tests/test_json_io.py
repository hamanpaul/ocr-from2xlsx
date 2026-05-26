from __future__ import annotations

import json
from pathlib import Path

import pytest

from ocr_from2xlsx.constants import SCHEMA_VERSION
from ocr_from2xlsx.domain import (
    Batch,
    OcrInfo,
    PatientFields,
    Record,
    ReviewInfo,
    Services,
    SourceBatch,
)
from ocr_from2xlsx.json_io import dump_batch, load_batch


def make_record(record_id: str = "scan-0001") -> Record:
    return Record(
        record_id=record_id,
        service_date="2026-03-15",
        identity="patient",
        name="王小明",
        medical_record_no="A123456",
        gender="female",
        patient_fields=PatientFields(
            nationality="local",
            age_group="51_60",
            channel="internal_referral",
            disease_status="treating",
            source="outpatient",
            cancers=["breast_cancer"],
            newly_diagnosed_within_year=True,
        ),
        services=Services(
            consultation={"health_medical": ["screening_prevention"]},
            supplies=["wig_hat"],
            internal_referrals=[],
            external_referrals=[],
            referral_outcomes=[],
        ),
        ocr=OcrInfo(confidence=0.93, raw_text="raw", warnings=[]),
        review=ReviewInfo(status="pending", edited_by_user=False),
    )


def test_ocr_info_casts_integer_confidence_to_float() -> None:
    ocr = OcrInfo.from_dict({"confidence": 1, "raw_text": "raw", "warnings": []})

    assert isinstance(ocr.confidence, float)
    assert ocr.confidence == 1.0


def test_ocr_info_rejects_string_confidence() -> None:
    with pytest.raises(ValueError, match="ocr.confidence must be a number"):
        OcrInfo.from_dict({"confidence": "0.9", "raw_text": "", "warnings": []})


def test_batch_json_round_trip(tmp_path: Path) -> None:
    batch = Batch(
        source_batch=SourceBatch(
            created_at="2026-05-24T15:30:00+08:00",
            source_type="json_import",
            template_name="template.xlsx",
        ),
        records=[make_record()],
    )
    path = tmp_path / "records.json"

    dump_batch(batch, path)
    loaded = load_batch(path)

    assert loaded.schema_version == "service_record.v1"
    assert loaded.records[0].name == "王小明"
    assert loaded.records[0].patient_fields.cancers == ["breast_cancer"]
    assert loaded.records[0].duplicate_key() == (
        "2026-03-15",
        "王小明",
        "A123456",
        "health_medical:screening_prevention|supplies:wig_hat",
    )


def test_batch_json_round_trip_keeps_pdf_source_and_ocr_metadata(tmp_path: Path) -> None:
    batch = Batch(
        source_batch=SourceBatch(
            created_at="2026-05-26T09:00:00+08:00",
            source_type="prepare_records",
            template_name="service_record.v1",
        ),
        records=[make_record()],
    )
    record = batch.records[0]
    record.source.kind = "pdf_page"
    record.source.document_path = "tests/fixtures/pdf/for testing only.pdf"
    record.source.page_number = 1
    record.source.preprocessed_image_path = "tmp/scan-0001.png"
    record.source.template_id = "service_record.v1"
    record.ocr.backend = "fixture"
    record.ocr.model = "manual-gold"
    record.ocr.field_confidences = {"name": 0.99, "service_date": 0.95}

    path = tmp_path / "prepared.json"
    dump_batch(batch, path)
    loaded = load_batch(path)

    assert loaded.records[0].source.kind == "pdf_page"
    assert loaded.records[0].source.document_path == "tests/fixtures/pdf/for testing only.pdf"
    assert loaded.records[0].source.page_number == 1
    assert loaded.records[0].source.preprocessed_image_path == "tmp/scan-0001.png"
    assert loaded.records[0].source.template_id == "service_record.v1"
    assert loaded.records[0].ocr.backend == "fixture"
    assert loaded.records[0].ocr.model == "manual-gold"
    assert loaded.records[0].ocr.field_confidences == {"name": 0.99, "service_date": 0.95}


def test_load_batch_accepts_integral_float_page_number(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["source"]["page_number"] = 1.0
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    batch = load_batch(path)

    assert batch.records[0].source.page_number == 1


def test_load_batch_rejects_non_integral_float_page_number(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["source"]["page_number"] = 1.5
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source.page_number must be an int"):
        load_batch(path)


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text('{"schema_version":"wrong","source_batch":{},"records":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported schema_version"):
        load_batch(path)


def test_load_batch_rejects_source_batch_not_object(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": "oops", "records": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source_batch must be an object"):
        load_batch(path)


def test_load_batch_rejects_missing_record_id(tmp_path: Path) -> None:
    record = make_record().to_dict()
    del record["record_id"]
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="record_id is required"):
        load_batch(path)


def test_load_batch_rejects_empty_record_id(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["record_id"] = ""
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="record_id is required"):
        load_batch(path)


def test_load_batch_rejects_non_string_record_id(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["record_id"] = 123
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="record_id must be a string"):
        load_batch(path)


def test_load_batch_accepts_missing_service_date(tmp_path: Path) -> None:
    record = make_record().to_dict()
    del record["service_date"]
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    batch = load_batch(path)

    assert batch.records[0].service_date == ""


def test_load_batch_rejects_non_string_name(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["name"] = 123
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="name must be a string"):
        load_batch(path)


def test_load_batch_rejects_non_string_source_batch_template_name(tmp_path: Path) -> None:
    record = make_record().to_dict()
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "source_batch": {"template_name": 123},
                "records": [record],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source_batch.template_name must be a string"):
        load_batch(path)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("ocr.raw_text", 123, "ocr.raw_text must be a string"),
        ("review.status", 123, "review.status must be a string"),
    ],
)
def test_load_batch_rejects_non_string_ocr_review_fields(
    tmp_path: Path, field: str, value: object, match: str
) -> None:
    record = make_record().to_dict()
    if field == "ocr.raw_text":
        record["ocr"]["raw_text"] = value
    else:
        record["review"]["status"] = value
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=match):
        load_batch(path)


def test_load_batch_rejects_supplies_string(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["services"]["supplies"] = "wig_hat"
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="services.supplies must be a list"):
        load_batch(path)


def test_load_batch_rejects_consultation_value_string(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["services"]["consultation"] = {"health_medical": "screening_prevention"}
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"services\.consultation\.health_medical must be a list"):
        load_batch(path)


def test_load_batch_rejects_services_string(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["services"] = "oops"
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="services must be an object"):
        load_batch(path)


def test_load_batch_rejects_patient_fields_list(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["patient_fields"] = []
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="patient_fields must be an object"):
        load_batch(path)


def test_load_batch_rejects_patient_fields_age_group_non_string(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["patient_fields"]["age_group"] = 51
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"patient_fields\.age_group must be a string"):
        load_batch(path)


def test_load_batch_rejects_source_image_path_non_string(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["source"]["image_path"] = 123
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"source\.image_path must be a string"):
        load_batch(path)


def test_load_batch_rejects_birthdate_non_string(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["birthdate"] = 123
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="birthdate must be a string"):
        load_batch(path)


def test_load_batch_rejects_records_not_list(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": "oops"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="records must be a list"):
        load_batch(path)


def test_load_batch_rejects_record_item_not_object(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": ["oops"]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"records\[0\] must be an object"):
        load_batch(path)


def test_load_batch_rejects_supplies_non_string(tmp_path: Path) -> None:
    record = make_record().to_dict()
    record["services"]["supplies"] = [123]
    path = tmp_path / "records.json"
    path.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "source_batch": {}, "records": [record]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"services\.supplies\[0\] must be a string"):
        load_batch(path)


def test_service_month_label_requires_service_date() -> None:
    record = make_record()
    record.service_date = ""

    with pytest.raises(ValueError, match="service_date is required to calculate service month"):
        record.service_month_label()


def test_service_month_label_rejects_invalid_service_date() -> None:
    record = make_record()
    record.service_date = "not-a-date"

    with pytest.raises(ValueError, match="Invalid service_date: 'not-a-date'"):
        record.service_month_label()


def test_batch_from_dict_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        Batch.from_dict({"schema_version": "wrong", "source_batch": {}, "records": []})


def test_batch_from_dict_defaults_schema_version() -> None:
    batch = Batch.from_dict({"source_batch": {}, "records": []})

    assert batch.schema_version == SCHEMA_VERSION


def test_load_batch_rejects_non_object_top_level(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text(json.dumps([]), encoding="utf-8")

    with pytest.raises(ValueError, match="Expected JSON object at top level"):
        load_batch(path)


def test_record_from_dict_strips_record_id() -> None:
    record = Record.from_dict({"record_id": "  scan-1  "})

    assert record.record_id == "scan-1"


def test_record_from_dict_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="record must be an object"):
        Record.from_dict("oops")  # type: ignore[arg-type]
