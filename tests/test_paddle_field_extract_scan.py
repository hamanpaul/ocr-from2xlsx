from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

_FIELD_EXTRACT_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "field_extract.py"
_field_extract_spec = importlib.util.spec_from_file_location(
    "paddle_field_extract_scan", _FIELD_EXTRACT_PATH
)
field_extract = importlib.util.module_from_spec(_field_extract_spec)
assert _field_extract_spec and _field_extract_spec.loader
_field_extract_spec.loader.exec_module(field_extract)

_NAME_CROP_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "name_crop.py"
_name_crop_spec = importlib.util.spec_from_file_location("paddle_name_crop_scan", _NAME_CROP_PATH)
name_crop = importlib.util.module_from_spec(_name_crop_spec)
assert _name_crop_spec and _name_crop_spec.loader
_name_crop_spec.loader.exec_module(name_crop)

_LINES = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "scan" / "lines.json").read_text(
        encoding="utf-8"
    )
)


def _page_width(lines: list[dict[str, Any]]) -> float:
    return max(float(point[0]) for line in lines for point in line["box"])


def _bbox(line: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        min(float(point[0]) for point in line["box"]),
        min(float(point[1]) for point in line["box"]),
        max(float(point[0]) for point in line["box"]),
        max(float(point[1]) for point in line["box"]),
    )


def _boxes_overlap(
    box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]
) -> bool:
    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def test_scan_lines_recover_mrn_and_keep_name_unresolved_but_anchorable() -> None:
    fields = field_extract.extract_fields(_LINES, marked_labels=set())
    crop_box = name_crop.name_crop_box(_LINES, page_width=_page_width(_LINES))
    mrn_line = next(line for line in _LINES if line["text"] == "病人6258712919")

    assert fields["service_date"] == "2025-06-25"
    assert fields["medical_record_no"] == "6258712919"
    assert fields["name"] is None
    assert fields.get("name_anchor") == {
        "text": "姓名/病歷号",
        "box": [
            [659.0, 2016.0],
            [897.0, 2016.0],
            [897.0, 2065.0],
            [659.0, 2065.0],
        ],
    }
    assert crop_box is not None
    assert crop_box[0] >= fields["name_anchor"]["box"][1][0]
    assert crop_box[2] > crop_box[0]
    assert crop_box[1] >= max(point[1] for point in mrn_line["box"])
    assert crop_box[3] <= max(point[1] for point in fields["name_anchor"]["box"])
    assert not _boxes_overlap(crop_box, _bbox(mrn_line))
