from __future__ import annotations

from ocr_from2xlsx.confirm_form import apply_form_state, record_to_form_state
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import service_record_layout


def _record() -> Record:
    return Record.from_dict(
        {
            "record_id": "r1",
            "service_date": "2026-05-26",
            "identity": "patient",
            "name": "王小明",
            "medical_record_no": "A1",
            "gender": "female",
            "patient_fields": {
                "nationality": "local",
                "age_group": "51_60",
                "cancers": ["breast_cancer", "lung_cancer"],
                "newly_diagnosed_within_year": True,
            },
            "services": {
                "consultation": {
                    "health_medical": ["screening_prevention"],
                },
            },
        }
    )


def test_record_to_form_state_reads_each_kind():
    layout = service_record_layout()

    state = record_to_form_state(layout, _record())

    assert state["service_date"] == "2026-05-26"
    assert state["identity"] == "patient"
    assert state["gender"] == "female"
    assert state["cancer"] == {"breast_cancer", "lung_cancer"}
    assert state["consultation.health_medical"] == {"screening_prevention"}
    assert state["newly_diagnosed"] == "true"


def test_apply_form_state_writes_back():
    layout = service_record_layout()
    record = _record()
    state = {
        "gender": "male",
        "cancer": {"liver_cancer"},
        "consultation.care_support": {"peer_experience"},
        "newly_diagnosed": "",
        "name": "陳大文",
        "diagnosis_date": "ignored",
    }

    apply_form_state(layout, record, state)

    assert record.gender == "male"
    assert set(record.patient_fields.cancers) == {"liver_cancer"}
    assert record.services.consultation["care_support"] == ["peer_experience"]
    assert record.patient_fields.newly_diagnosed_within_year is False
    assert record.name == "陳大文"


def test_round_trip_is_stable():
    layout = service_record_layout()
    record = _record()

    apply_form_state(layout, record, record_to_form_state(layout, record))
    again = record_to_form_state(layout, record)

    assert again["identity"] == "patient"
    assert again["cancer"] == {"breast_cancer", "lung_cancer"}
    assert again["newly_diagnosed"] == "true"
