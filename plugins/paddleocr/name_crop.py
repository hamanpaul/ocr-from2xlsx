"""Name-crop geometry (pure) + a Pillow saver (plugin-only).

The name sits on the 姓名/病歷號 anchor line, to the right of the label. The medical-record-no is on the
line above and the diagnosis date on the line below; restricting the crop to the anchor line's y-band
excludes both, minimizing PII in the crop.
"""
from __future__ import annotations

from typing import Any

_ANCHOR = "姓名"
_RIGHT_PAD_FACTOR = 6.0  # extend right of the label by N * label-height to cover the handwriting


def _bbox(line: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in line["box"]]
    ys = [pt[1] for pt in line["box"]]
    return (min(xs), min(ys), max(xs), max(ys))


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
    return (int(x0), int(ay0), int(x1), int(ay1))


def save_name_crop(image_path: str, lines: list[dict[str, Any]], out_path: str) -> str | None:
    from PIL import Image

    image = Image.open(image_path).convert("L")
    box = name_crop_box(lines, page_width=image.width)
    if box is None:
        return None
    image.crop(box).save(out_path)
    return out_path
