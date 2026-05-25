from __future__ import annotations

from ocr_from2xlsx.normalizer import normalize_raw_record


def test_normalize_raw_record_builds_record() -> None:
    raw = {
        "record_id": "scan-0001",
        "service_date": "2026-03-15",
        "identity": "patient",
        "name": "王小明",
        "medical_record_no": "A123456",
        "gender": "female",
        "source": {
            "image_path": "scan-0001.jpg",
            "capture_time": "2026-03-15T10:00:00+08:00",
        },
        "birthdate": "1985-03-15",
        "patient_fields": {
            "nationality": "local",
            "age_group": "51_60",
            "channel": "internal_referral",
            "disease_status": "treating",
            "source": "outpatient",
            "cancers": ["breast_cancer"],
            "newly_diagnosed_within_year": True,
        },
        "services": {
            "consultation": {"health_medical": ["screening_prevention"]},
            "supplies": ["wig_hat"],
            "internal_referrals": ["nutrition"],
            "external_referrals": [],
            "referral_outcomes": ["connected"],
        },
        "discharge_followup": True,
        "notes": "note",
        "ocr": {"confidence": 0.93, "raw_text": "raw", "warnings": ["low_confidence"]},
        "review": {"status": "pending", "edited_by_user": True},
    }

    record = normalize_raw_record(raw)

    assert record.record_id == "scan-0001"
    assert record.name == "王小明"
    assert record.patient_fields.nationality == "local"
    assert record.services.consultation == {"health_medical": ["screening_prevention"]}
    assert record.ocr.raw_text == "raw"
