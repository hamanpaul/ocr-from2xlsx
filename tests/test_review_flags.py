from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT
from ocr_from2xlsx.recognition.review_flags import flagged_fields


def test_low_confidence_option_maps_to_record_field():
    flags = flagged_fields(["low-confidence:identity.patient:0.40"], SERVICE_RECORD_V1_LAYOUT)
    assert flags["identity"] == "low-confidence"


def test_empty_value_maps_to_value_field():
    flags = flagged_fields(["empty:service_date"], SERVICE_RECORD_V1_LAYOUT)
    assert flags["service_date"] == "empty"


def test_unconfirmed_name_flag():
    flags = flagged_fields(["name.unconfirmed"], SERVICE_RECORD_V1_LAYOUT)
    assert flags["name"] == "unconfirmed"


def test_unknown_warning_is_ignored():
    flags = flagged_fields(["something-weird"], SERVICE_RECORD_V1_LAYOUT)
    assert flags == {}


def test_multiple_warnings_collected():
    flags = flagged_fields(
        ["low-confidence:gender.female:0.5", "empty:medical_record_no", "name.unconfirmed"],
        SERVICE_RECORD_V1_LAYOUT,
    )
    assert flags == {
        "gender": "low-confidence",
        "medical_record_no": "empty",
        "name": "unconfirmed",
    }
