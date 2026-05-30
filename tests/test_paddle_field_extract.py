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
