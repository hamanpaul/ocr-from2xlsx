"""Checkbox mark detection.

Pure core: score a grayscale region (2D sequence of 0-255 luminance) for ink.
"""
from __future__ import annotations

from typing import Any, Sequence

DARK_THRESHOLD = 128      # luminance below this counts as ink
MARKED_RATIO = 0.12       # fraction of dark pixels above which a region is "marked"
_PROBE_LABELS = ("病人", "親友及照顧者", "一般民眾及其他", "女性", "男性")
_LABEL_DECORATIONS = {"V", "v", "中", "✓", "✔", "☑", "☒", "✗", "×", "X", "x", "□"}
_TEXT_IMPLIED_MARKERS = _LABEL_DECORATIONS - {"□"}


def dark_ratio(region: Sequence[Sequence[float]], dark_threshold: int = DARK_THRESHOLD) -> float:
    total = 0
    dark = 0
    for row in region:
        for value in row:
            total += 1
            if value < dark_threshold:
                dark += 1
    if total == 0:
        return 0.0
    return dark / total


def is_marked(
    region: Sequence[Sequence[float]],
    dark_threshold: int = DARK_THRESHOLD,
    marked_ratio: float = MARKED_RATIO,
) -> bool:
    return dark_ratio(region, dark_threshold) >= marked_ratio


def _line_bbox(line: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in line["box"]]
    ys = [pt[1] for pt in line["box"]]
    return (min(xs), min(ys), max(xs), max(ys))


def match_probe_label(text: str) -> str | None:
    raw = str(text or "").strip()
    for label in _PROBE_LABELS:
        if raw == label:
            return label
        if len(raw) == len(label) + 1:
            if raw[0] in _LABEL_DECORATIONS and raw[1:] == label:
                return label
            if raw[:-1] == label and raw[-1] in _LABEL_DECORATIONS:
                return label
    return None


def text_implied_marked_label(text: str) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    for label in ("女性", "男性"):
        if len(raw) == len(label) + 1:
            if raw[0] in _TEXT_IMPLIED_MARKERS and raw[1:] == label:
                return label
            if raw[:-1] == label and raw[-1] in _TEXT_IMPLIED_MARKERS:
                return label
    for label in ("病人", "親友及照顧者", "一般民眾及其他"):
        if raw.startswith(label) and raw != label and any(ch.isdigit() for ch in raw[len(label):]):
            return label
    return None


def detect_marked_labels(image_path: str, lines: list[dict[str, Any]]) -> set[str]:
    from PIL import Image

    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        width, height = grayscale.size
        marked: set[str] = set()
        for line in lines:
            implied = text_implied_marked_label(str(line.get("text") or ""))
            if implied is not None:
                marked.add(implied)
                continue
            label = match_probe_label(str(line.get("text") or ""))
            if label is None:
                continue

            x0, y0, x1, y1 = _line_bbox(line)
            box_h = max(1.0, y1 - y0)
            px1 = max(0, int(x0))
            px0 = max(0, int(x0 - box_h * 1.4))
            py0 = max(0, int(y0))
            py1 = min(height, int(y1))
            if px1 <= px0 or py1 <= py0:
                continue

            crop = grayscale.crop((px0, py0, px1, py1))
            pixels = list(crop.getdata())
            region = [
                pixels[row * crop.width : (row + 1) * crop.width]
                for row in range(crop.height)
            ]
            if is_marked(region):
                marked.add(label)
        return marked
