from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "field_extract.py"
_spec = importlib.util.spec_from_file_location("paddle_field_extract", _MODULE_PATH)
field_extract = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(field_extract)

normalize_roc_date = field_extract.normalize_roc_date
extract_fields = field_extract.extract_fields


def _line(text, x=0.0, y=0.0):
    # box is 4 points [tl, tr, br, bl]; only center is used downstream
    return {"text": text, "box": [[x, y], [x + 50, y], [x + 50, y + 10], [x, y + 10]]}


def test_normalize_roc_date_dotted():
    assert normalize_roc_date("114.06.25") == "2025-06-25"


def test_normalize_roc_date_with_label_and_cjk_separators():
    assert normalize_roc_date("服務年/月/日：114、6、5") == "2025-06-05"


def test_normalize_roc_date_slash():
    assert normalize_roc_date("113/12/31") == "2024-12-31"


def test_normalize_roc_date_merged_mmdd():
    # OCR sometimes merges month+day into one run: "114、0625" -> 2025-06-25.
    assert normalize_roc_date("服務年月日：114、0625") == "2025-06-25"


def test_normalize_roc_date_rejects_garbage():
    assert normalize_roc_date("no date here") is None


def test_normalize_roc_date_rejects_impossible_month():
    assert normalize_roc_date("114.13.40") is None


def test_extract_fields_finds_service_date_from_anchor_line():
    lines = [
        _line("癌症資源中心服務紀錄表", y=0),
        _line("服務年/月/日：114.06.25", y=20),
        _line("A.服務評估統計", y=40),
    ]
    fields = extract_fields(lines)
    assert fields["service_date"] == "2025-06-25"


def test_extract_fields_returns_none_when_no_date():
    lines = [_line("癌症資源中心服務紀錄表", y=0), _line("備註", y=99)]
    fields = extract_fields(lines)
    assert fields["service_date"] is None


def test_extract_fields_reads_name_and_mrn_to_right_of_anchor():
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("王小明 A123456", x=120, y=50),
    ]
    fields = extract_fields(lines)
    assert fields["name"] == "王小明"
    assert fields["medical_record_no"] == "A123456"


def test_extract_fields_name_mrn_none_when_anchor_value_missing():
    lines = [_line("姓名/病歷號", x=0, y=50)]
    fields = extract_fields(lines)
    assert fields["name"] is None
    assert fields["medical_record_no"] is None


def test_extract_fields_name_only_no_mrn():
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("陳美玲", x=120, y=50),
    ]
    fields = extract_fields(lines)
    assert fields["name"] == "陳美玲"
    assert fields["medical_record_no"] is None


def test_extract_fields_hyphenated_mrn():
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("林志偉 A12-3456", x=120, y=50),
    ]
    fields = extract_fields(lines)
    assert fields["name"] == "林志偉"
    assert fields["medical_record_no"] == "A12-3456"


def test_extract_fields_rejects_checkbox_and_stray_noise_as_name():
    # On a blank form the name cell is empty, but identity checkboxes and stray
    # marks sit on the same row. None of those are a valid name/MRN.
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("V", x=120, y=50),
        _line("□親友及照顧者", x=200, y=50),
        _line("□一般民眾及其他", x=320, y=50),
    ]
    fields = extract_fields(lines)
    assert fields["name"] is None
    assert fields["medical_record_no"] is None


def test_extract_fields_skips_noise_and_picks_real_name():
    # A checkbox label to the immediate right must be skipped in favour of the
    # real handwritten name+MRN further along the row.
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("□病人", x=110, y=50),
        _line("王大明 B998877", x=210, y=50),
    ]
    fields = extract_fields(lines)
    assert fields["name"] == "王大明"
    assert fields["medical_record_no"] == "B998877"


def test_extract_name_and_mrn_from_anchor_row_handwriting():
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("葉心安", x=120, y=50),
        _line("6250712919", x=260, y=50),
    ]
    fields = extract_fields(lines, marked_labels=set())
    assert fields["name"] == "葉心安"
    assert fields["medical_record_no"] == "6250712919"


def test_extract_mrn_when_ocr_merges_label_and_digits():
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("葉心安", x=120, y=50),
        _line("病人6250712919", x=260, y=50),
    ]
    fields = extract_fields(lines, marked_labels=set())
    assert fields["name"] == "葉心安"
    assert fields["medical_record_no"] == "6250712919"


def test_extract_identity_and_gender_from_marked_labels():
    lines = [
        _line("病人", x=10, y=50),
        _line("親友及照顧者", x=120, y=50),
        _line("一般民眾及其他", x=260, y=50),
        _line("女性", x=10, y=80),
        _line("男性", x=120, y=80),
    ]
    fields = extract_fields(lines, marked_labels={"病人", "女性"})
    assert fields["identity"] == "patient"
    assert fields["gender"] == "female"


def test_unmarked_identity_gender_stay_empty():
    lines = [_line("病人", x=10, y=50), _line("女性", x=10, y=80)]
    fields = extract_fields(lines, marked_labels=set())
    assert fields["identity"] == ""
    assert fields["gender"] == ""
