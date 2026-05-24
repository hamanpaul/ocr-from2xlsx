from __future__ import annotations

from pathlib import Path

import pytest

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


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text('{"schema_version":"wrong","source_batch":{},"records":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported schema_version"):
        load_batch(path)
