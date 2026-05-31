from __future__ import annotations

from ocr_from2xlsx.confirm_form import apply_form_state, record_to_form_state
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import service_record_layout
from ocr_from2xlsx.validation import validate_record


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


def _sparse_patient_record() -> Record:
    return Record.from_dict(
        {
            "record_id": "r2",
            "service_date": "2026-05-26",
            "identity": "patient",
            "name": "王小明",
            "medical_record_no": "A2",
            "gender": "female",
            "patient_fields": {
                "cancers": ["breast_cancer"],
            },
            "services": {
                "consultation": {},
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


def test_round_trip_preserves_missing_optional_single_choice_fields():
    layout = service_record_layout()
    record = _sparse_patient_record()
    blockers_before = validate_record(record).blockers

    apply_form_state(layout, record, record_to_form_state(layout, record))

    assert record.patient_fields.nationality is None
    assert record.patient_fields.age_group is None
    assert record.patient_fields.channel is None
    assert record.patient_fields.disease_status is None
    assert record.patient_fields.source is None
    assert validate_record(record).blockers == blockers_before


def test_round_trip_preserves_unknown_newly_diagnosed_state():
    layout = service_record_layout()
    record = _sparse_patient_record()

    apply_form_state(layout, record, record_to_form_state(layout, record))

    assert record.patient_fields.newly_diagnosed_within_year is None
