from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "mark_detect.py"
_spec = importlib.util.spec_from_file_location("paddle_mark_detect", _MODULE)
mark_detect = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(mark_detect)

dark_ratio = mark_detect.dark_ratio
is_marked = mark_detect.is_marked
match_probe_label = mark_detect.match_probe_label
text_implied_marked_label = mark_detect.text_implied_marked_label


def _filled(w, h, value):
    return [[value for _ in range(w)] for _ in range(h)]


def test_dark_ratio_all_dark_is_one():
    assert dark_ratio(_filled(4, 4, 0)) == 1.0


def test_dark_ratio_all_light_is_zero():
    assert dark_ratio(_filled(4, 4, 255)) == 0.0


def test_is_marked_true_for_inked_region():
    region = _filled(10, 10, 255)
    for r in range(10):
        for c in range(4):  # a vertical stroke ~ a tick
            region[r][c] = 0
    assert is_marked(region) is True


def test_is_marked_false_for_empty_box():
    region = _filled(10, 10, 255)
    # faint printed box border (above the dark threshold) -> not marked
    for c in range(10):
        region[0][c] = 200
        region[9][c] = 200
    for r in range(10):
        region[r][0] = 200
        region[r][9] = 200
    assert is_marked(region) is False


def test_is_marked_handles_empty_region():
    assert is_marked([]) is False


def test_match_probe_label_accepts_exact_label():
    assert match_probe_label("親友及照顧者") == "親友及照顧者"


def test_match_probe_label_accepts_decorated_gender_labels():
    assert match_probe_label("□女性") == "女性"
    assert match_probe_label("女性□") == "女性"


def test_match_probe_label_rejects_heading_and_quantity_text():
    assert match_probe_label("女性數量：") is None
    assert match_probe_label("B.綜合身份統計(病人就會填到ABC：其他一概只需填AB)") is None


def test_text_implied_marked_label_detects_selected_gender_tokens():
    assert text_implied_marked_label("中女性") == "女性"
    assert text_implied_marked_label("V女性") == "女性"


def test_text_implied_marked_label_detects_merged_patient_mrn():
    assert text_implied_marked_label("病人6250712919") == "病人"


def test_text_implied_marked_label_rejects_unselected_and_plain_labels():
    assert text_implied_marked_label("□男性") is None
    assert text_implied_marked_label("親友及照顧者") is None
