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
