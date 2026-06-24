"""Name-crop geometry (pure) + a Pillow saver (plugin-only).

The name sits on the 姓名/病歷號 anchor line, to the right of the label. The medical-record-no is on the
line above and the diagnosis date on the line below; the crop stays inside the anchor band and trims away
any MRN box that intrudes into the top of that band, minimizing PII in the crop.
"""
from __future__ import annotations

import math
from typing import Any

_ANCHOR = "姓名"
_RIGHT_PAD_FACTOR = 6.0  # extend right of the label by N * label-height to cover the handwriting
_ANCHOR_ROW_OVERLAP_RATIO = 0.6
_TOP_RIGHT_BLEED_PROBE_WIDTH = 40
_TOP_RIGHT_BLEED_SEARCH_ROWS = 20
_TOP_RIGHT_BLEED_THRESHOLD = 240


def _bbox(line: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in line["box"]]
    ys = [pt[1] for pt in line["box"]]
    return (min(xs), min(ys), max(xs), max(ys))


def _visible_anchor_top(
    lines: list[dict[str, Any]],
    anchor: dict[str, Any],
    crop_left: float,
    crop_right: float,
    anchor_top: float,
    anchor_bottom: float,
) -> float:
    top = anchor_top
    for line in lines:
        if line is anchor:
            continue
        lx0, ly0, lx1, ly1 = _bbox(line)
        if ly0 >= anchor_top or ly1 <= anchor_top:
            continue
        if lx1 <= crop_left or lx0 >= crop_right:
            continue
        line_height = max(1.0, ly1 - ly0)
        anchor_overlap = max(0.0, min(ly1, anchor_bottom) - max(ly0, anchor_top))
        if ((lx0 + lx1) / 2) >= crop_left and (anchor_overlap / line_height) >= _ANCHOR_ROW_OVERLAP_RATIO:
            continue
        top = max(top, min(ly1, anchor_bottom))
    if top >= anchor_bottom:
        return anchor_bottom
    return top


def _has_intruding_top_line(
    lines: list[dict[str, Any]],
    anchor: dict[str, Any],
    crop_left: float,
    crop_right: float,
    anchor_top: float,
    anchor_bottom: float,
) -> bool:
    return _visible_anchor_top(
        lines,
        anchor,
        crop_left,
        crop_right,
        anchor_top,
        anchor_bottom,
    ) > anchor_top


def _trim_top_right_bleed(
    image: "Image.Image", box: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = box
    crop = image.crop(box)
    if crop.width <= 0 or crop.height <= 1:
        return box
    probe_left = max(0, crop.width - _TOP_RIGHT_BLEED_PROBE_WIDTH)
    search_rows = min(_TOP_RIGHT_BLEED_SEARCH_ROWS, crop.height - 1)
    trim_rows = 0
    for row in range(search_rows):
        row_has_bleed = any(
            crop.getpixel((column, row)) < _TOP_RIGHT_BLEED_THRESHOLD
            for column in range(probe_left, crop.width)
        )
        if not row_has_bleed:
            break  # only trim the contiguous bleed at the top, never into the name below
        trim_rows = row + 1
    if trim_rows == 0:
        return box
    trimmed_top = y0 + trim_rows
    if trimmed_top >= y1:
        return None
    return (x0, trimmed_top, x1, y1)


def name_crop_box(lines: list[dict[str, Any]], page_width: float) -> tuple[int, int, int, int] | None:
    anchor = next((ln for ln in lines if _ANCHOR in str(ln.get("text") or "")), None)
    if anchor is None:
        return None
    ax0, ay0, ax1, ay1 = _bbox(anchor)
    height = max(1.0, ay1 - ay0)
    x0 = ax1
    x1 = min(float(page_width), ax1 + height * _RIGHT_PAD_FACTOR)
    if x1 <= x0:
        x1 = min(float(page_width), x0 + height)
    y0 = _visible_anchor_top(lines, anchor, x0, x1, ay0, ay1)
    top = math.ceil(y0)
    bottom = math.floor(ay1)
    if top >= bottom:
        return None
    return (int(x0), top, int(x1), bottom)


def save_name_crop(image_path: str, lines: list[dict[str, Any]], out_path: str) -> str | None:
    from PIL import Image

    image = Image.open(image_path).convert("L")
    box = name_crop_box(lines, page_width=image.width)
    if box is None:
        return None
    anchor = next((ln for ln in lines if _ANCHOR in str(ln.get("text") or "")), None)
    if anchor is not None:
        ax0, ay0, ax1, ay1 = _bbox(anchor)
        if _has_intruding_top_line(lines, anchor, box[0], box[2], ay0, ay1):
            box = _trim_top_right_bleed(image, box)
            if box is None:
                return None
    image.crop(box).save(out_path)
    return out_path
