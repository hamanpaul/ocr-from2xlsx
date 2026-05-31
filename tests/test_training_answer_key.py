from __future__ import annotations

import json
from pathlib import Path

from ocr_from2xlsx.form_layout import service_record_layout
from ocr_from2xlsx.json_io import load_batch
from training.answer_key import build_answer_batch, selection_to_record


def test_selection_to_record_places_codes_and_text():
    layout = service_record_layout()

    record = selection_to_record(
        layout,
        record_id="train-0001",
        selection={
            "identity": ["patient"],
            "gender": ["female"],
            "nationality": ["local"],
            "age": ["51_60"],
            "source": ["outpatient"],
            "cancer": ["breast_cancer", "lung_cancer"],
            "newly_diagnosed": ["true"],
            "consultation.health_medical": [
                "screening_prevention",
                "doctor_patient_communication",
            ],
            "consultation.care_support": ["peer_experience", "caregiver_support"],
        },
        text_values={
            "service_date": "2026-05-31",
            "name": "王小明",
            "medical_record_no": "A123456",
        },
    )

    assert record.record_id == "train-0001"
    assert record.service_date == "2026-05-31"
    assert record.name == "王小明"
    assert record.medical_record_no == "A123456"
    assert record.identity == "patient"
    assert record.gender == "female"
    assert record.patient_fields.nationality == "local"
    assert record.patient_fields.age_group == "51_60"
    assert record.patient_fields.source == "outpatient"
    assert record.patient_fields.cancers == ["breast_cancer", "lung_cancer"]
    assert record.patient_fields.newly_diagnosed_within_year is True
    assert record.services.consultation["health_medical"] == [
        "doctor_patient_communication",
        "screening_prevention",
    ]
    assert record.services.consultation["care_support"] == [
        "caregiver_support",
        "peer_experience",
    ]


def test_build_answer_batch_is_loadable_and_tagged(tmp_path: Path):
    layout = service_record_layout()
    record = selection_to_record(
        layout,
        record_id="train-0001",
        selection={
            "identity": ["patient"],
            "gender": ["female"],
            "cancer": ["breast_cancer"],
            "consultation.health_medical": ["screening_prevention"],
        },
        text_values={
            "service_date": "2026-05-31",
            "name": "王小明",
            "medical_record_no": "A123456",
        },
    )

    payload = build_answer_batch(
        [(record, "images/train-0001.png")],
        created_at="2026-05-31T00:00:00+08:00",
    )

    assert payload["schema_version"] == "service_record.v1"
    assert payload["source_batch"] == {
        "created_at": "2026-05-31T00:00:00+08:00",
        "source_type": "training_synthetic",
        "template_name": "service_record.v1",
    }
    assert payload["records"][0]["training"] is True
    assert payload["records"][0]["source_image"] == "images/train-0001.png"

    path = tmp_path / "answer-key.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    loaded = load_batch(path)

    assert loaded.schema_version == "service_record.v1"
    loaded_record = loaded.records[0]
    assert loaded_record.record_id == "train-0001"
    assert loaded_record.service_date == "2026-05-31"
    assert loaded_record.name == "王小明"
    assert loaded_record.medical_record_no == "A123456"
    assert loaded_record.patient_fields.cancers == ["breast_cancer"]
    assert loaded_record.services.consultation["health_medical"] == ["screening_prevention"]
