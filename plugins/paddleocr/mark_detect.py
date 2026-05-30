"""Checkbox mark detection.

Pure core: score a grayscale region (2D sequence of 0-255 luminance) for ink.
The Pillow image wrapper is added in a later task and is NOT exercised by CI tests.
"""
from __future__ import annotations

from typing import Sequence

DARK_THRESHOLD = 128      # luminance below this counts as ink
MARKED_RATIO = 0.12       # fraction of dark pixels above which a region is "marked"


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
