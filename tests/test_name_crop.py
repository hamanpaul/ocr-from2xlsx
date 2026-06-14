from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from PIL import Image

_MODULE = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "name_crop.py"
_spec = importlib.util.spec_from_file_location("paddle_name_crop", _MODULE)
name_crop = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(name_crop)

name_crop_box = name_crop.name_crop_box
save_name_crop = name_crop.save_name_crop
_SCAN_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "scan"
_SCAN_LINES = json.loads((_SCAN_FIXTURE_DIR / "lines.json").read_text(encoding="utf-8"))


def _line(text, x0, y0, x1, y1):
    return {"text": text, "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def _overlaps(box_a, box_b):
    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


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


def test_crop_trims_top_to_avoid_overlapping_mrn_line():
    overlapping_mrn_box = (60, 360, 360, 405)
    lines = [
        _line("病人6250712919", *overlapping_mrn_box),
        _line("姓名/病歷號", 60, 396, 200, 428),
    ]
    box = name_crop_box(lines, page_width=1000)
    assert box is not None
    assert box[1] >= overlapping_mrn_box[3]
    assert not _overlaps(box, overlapping_mrn_box)


def test_crop_rounds_trimmed_top_up_after_float_overlap() -> None:
    overlapping_mrn_box = (60, 360.0, 360, 427.4)
    lines = [
        _line("病人6250712919", *overlapping_mrn_box),
        _line("姓名/病歷號", 60, 396.2, 200, 429.2),
    ]

    box = name_crop_box(lines, page_width=1000)

    assert box is not None
    assert box[1] >= 428
    assert box[3] > box[1]
    assert not _overlaps(box, overlapping_mrn_box)


def test_crop_does_not_trim_same_row_name_text_to_the_right_of_anchor() -> None:
    lines = [
        _line("姓名/病歷號", 60, 396.2, 200, 427.9),
        _line("王小明", 220, 392.0, 380, 427.4),
    ]

    box = name_crop_box(lines, page_width=1000)

    assert box == (200, 397, 390, 427)


def test_crop_trims_tall_mrn_intrusion_from_above_without_losing_same_row_name_text() -> None:
    overlapping_mrn_box = (80, 380.0, 260, 412.6)
    same_row_name_box = (220, 392.0, 380, 427.4)
    lines = [
        _line("病人6250712919", *overlapping_mrn_box),
        _line("姓名/病歷號", 60, 396.2, 200, 429.2),
        _line("王小明", *same_row_name_box),
    ]

    box = name_crop_box(lines, page_width=1000)

    assert box is not None
    assert box[1] == 413
    assert box[3] > box[1]
    assert not _overlaps(box, overlapping_mrn_box)
    assert _overlaps(box, same_row_name_box)


def test_crop_returns_none_when_integer_rounding_would_make_zero_height() -> None:
    lines = [
        _line("病人6250712919", 60, 360.0, 360, 427.4),
        _line("姓名/病歷號", 60, 396.2, 200, 427.9),
    ]

    assert name_crop_box(lines, page_width=1000) is None


def test_returns_none_without_anchor():
    assert name_crop_box([_line("無關", 0, 0, 50, 20)], page_width=1000) is None


def test_save_name_crop_excludes_top_right_mrn_bleed_on_real_scan_fixture(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "name-crop.png"

    saved = save_name_crop(
        str(_SCAN_FIXTURE_DIR / "form.png"),
        _SCAN_LINES,
        str(out_path),
    )

    assert saved == str(out_path)

    crop = Image.open(out_path).convert("L")
    dark_pixels = sum(
        1
        for y in range(min(4, crop.height))
        for x in range(max(0, crop.width - 40), crop.width)
        if crop.getpixel((x, y)) < 240
    )
    assert dark_pixels == 0
