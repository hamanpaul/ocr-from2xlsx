from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "name_crop.py"
_spec = importlib.util.spec_from_file_location("paddle_name_crop", _MODULE)
name_crop = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(name_crop)

name_crop_box = name_crop.name_crop_box


def _line(text, x0, y0, x1, y1):
    return {"text": text, "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def test_crop_covers_name_line_and_excludes_record_no_and_date():
    lines = [
        _line("病人6250712919", 60, 360, 360, 392),    # record-no line ABOVE
        _line("姓名/病歷號", 60, 396, 200, 428),         # anchor line (name sits to its right)
        _line("114、06、25", 60, 432, 300, 470),         # diagnosis date BELOW
    ]
    box = name_crop_box(lines, page_width=1000)
    assert box is not None
    x0, y0, x1, y1 = box
    assert x0 >= 200
    assert 396 <= y0 <= 428 and 396 <= y1 <= 428
    assert y0 > 392 and y1 < 432
    assert x1 <= 1000 and x1 > x0


def test_returns_none_without_anchor():
    assert name_crop_box([_line("無關", 0, 0, 50, 20)], page_width=1000) is None
