from __future__ import annotations

import pytest

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.record_access import get_by_path, set_by_path


def _record() -> Record:
    return Record.from_dict({
        "record_id": "r1", "service_date": "2026-05-26", "identity": "patient",
        "name": "王小明", "medical_record_no": "A1", "gender": "female",
        "patient_fields": {"age_group": "51_60", "cancers": ["breast_cancer"],
                           "newly_diagnosed_within_year": True},
        "services": {"consultation": {"health_medical": ["screening_prevention"]},
                     "supplies": ["wig_hat"]},
    })


def test_get_top_level_and_nested_and_dict():
    r = _record()
    assert get_by_path(r, "identity") == "patient"
    assert get_by_path(r, "patient_fields.age_group") == "51_60"
    assert get_by_path(r, "patient_fields.cancers") == ["breast_cancer"]
    assert get_by_path(r, "patient_fields.newly_diagnosed_within_year") is True
    assert get_by_path(r, "services.consultation.health_medical") == ["screening_prevention"]
    assert get_by_path(r, "services.supplies") == ["wig_hat"]


def test_get_missing_consultation_category_returns_none():
    r = _record()
    assert get_by_path(r, "services.consultation.care_support") is None


def test_set_top_level_nested_list_and_bool():
    r = _record()
    set_by_path(r, "gender", "male")
    set_by_path(r, "patient_fields.age_group", "61_70")
    set_by_path(r, "patient_fields.cancers", ["lung_cancer", "liver_cancer"])
    set_by_path(r, "patient_fields.newly_diagnosed_within_year", False)
    set_by_path(r, "services.consultation.care_support", ["peer_experience"])
    assert r.gender == "male"
    assert r.patient_fields.age_group == "61_70"
    assert r.patient_fields.cancers == ["lung_cancer", "liver_cancer"]
    assert r.patient_fields.newly_diagnosed_within_year is False
    assert r.services.consultation["care_support"] == ["peer_experience"]


def test_set_none_path_is_noop():
    r = _record()
    set_by_path(r, None, "anything")  # record_path=None fields (e.g. diagnosis_date)
    assert r.name == "王小明"


def test_unknown_attr_raises():
    r = _record()
    with pytest.raises(AttributeError):
        set_by_path(r, "nope_field", "x")
