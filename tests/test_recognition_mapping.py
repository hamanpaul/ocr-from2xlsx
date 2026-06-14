from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT
from ocr_from2xlsx.recognition.mapping import (
    apply_tile_result,
    empty_record_fields,
    parse_roc_date,
)


def test_marked_single_option_sets_field():
    fields = empty_record_fields()
    apply_tile_result(
        fields,
        SERVICE_RECORD_V1_LAYOUT,
        {
            "options": [
                {"id": "identity.patient", "marked": True, "confidence": 0.9},
                {"id": "gender.female", "marked": True, "confidence": 0.8},
            ],
            "values": [{"id": "service_date", "text": "114.06.25", "confidence": 0.7}],
        },
    )
    assert fields["identity"] == "patient"
    assert fields["gender"] == "female"
    assert fields["service_date"] == "2025-06-25"


def test_marked_multi_option_appends_code_without_duplicates():
    fields = empty_record_fields()
    tile = {"options": [{"id": "cancer.liver_cancer", "marked": True, "confidence": 0.9}], "values": []}
    apply_tile_result(fields, SERVICE_RECORD_V1_LAYOUT, tile)
    apply_tile_result(fields, SERVICE_RECORD_V1_LAYOUT, tile)  # idempotent
    assert fields["patient_fields"]["cancers"] == ["liver_cancer"]


def test_unmarked_option_leaves_field_empty():
    fields = empty_record_fields()
    apply_tile_result(
        fields,
        SERVICE_RECORD_V1_LAYOUT,
        {"options": [{"id": "identity.patient", "marked": False, "confidence": 0.9}], "values": []},
    )
    assert fields["identity"] == ""


def test_nested_patient_field_is_set():
    fields = empty_record_fields()
    apply_tile_result(
        fields,
        SERVICE_RECORD_V1_LAYOUT,
        {"options": [{"id": "age_group.21_30", "marked": True, "confidence": 0.9}], "values": []},
    )
    assert fields["patient_fields"]["age_group"] == "21_30"


def test_unknown_option_id_is_ignored():
    fields = empty_record_fields()
    apply_tile_result(
        fields,
        SERVICE_RECORD_V1_LAYOUT,
        {"options": [{"id": "bogus.option", "marked": True, "confidence": 0.9}], "values": []},
    )
    assert fields["identity"] == ""


def test_empty_value_text_is_skipped():
    fields = empty_record_fields()
    apply_tile_result(
        fields,
        SERVICE_RECORD_V1_LAYOUT,
        {"options": [], "values": [{"id": "service_date", "text": "  ", "confidence": 0.1}]},
    )
    assert fields["service_date"] == ""


def test_parse_roc_date_variants():
    assert parse_roc_date("114.06.25") == "2025-06-25"
    assert parse_roc_date("114、06、25") == "2025-06-25"
    assert parse_roc_date("nonsense") == ""
