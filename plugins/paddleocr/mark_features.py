"""Plugin-safe checkbox mark feature extraction."""
from __future__ import annotations

from typing import Sequence

FEATURE_NAMES = (
    "dark_ratio",
    "centroid_dx",
    "centroid_dy",
    "ink_w",
    "ink_h",
    "rows_with_ink",
    "cols_with_ink",
    "max_run",
    "diag_ratio",
    "row_transitions",
)


def _zero_features() -> dict[str, float]:
    return {name: 0.0 for name in FEATURE_NAMES}


def _nearest_grid(region: Sequence[Sequence[float]], grid_size: int) -> list[list[float]]:
    rows = [list(row) for row in region]
    if grid_size <= 0 or not rows:
        return []
    height = len(rows)
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return []

    grid: list[list[float]] = []
    for y in range(grid_size):
        source_y = min(height - 1, int((y + 0.5) * height / grid_size))
        source_row = rows[source_y]
        grid_row: list[float] = []
        for x in range(grid_size):
            source_x = min(width - 1, int((x + 0.5) * width / grid_size))
            value = source_row[source_x] if source_x < len(source_row) else 255.0
            grid_row.append(float(value))
        grid.append(grid_row)
    return grid


def _longest_run(values: Sequence[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def extract_features(
    region: Sequence[Sequence[float]],
    grid_size: int = 24,
    dark_threshold: int = 128,
) -> dict[str, float]:
    """Return JSON-serializable mark features for a grayscale crop."""
    grid = _nearest_grid(region, grid_size)
    if not grid:
        return _zero_features()

    size = len(grid)
    dark_points: list[tuple[int, int]] = []
    rows_with_ink = set()
    cols_with_ink = set()
    max_run = 0
    transitions = 0
    diagonal_dark = 0

    for y, row in enumerate(grid):
        dark_row = [value < dark_threshold for value in row]
        max_run = max(max_run, _longest_run(dark_row))
        for x in range(1, size):
            if dark_row[x] != dark_row[x - 1]:
                transitions += 1
        for x, is_dark in enumerate(dark_row):
            if not is_dark:
                continue
            dark_points.append((x, y))
            rows_with_ink.add(y)
            cols_with_ink.add(x)
            if abs(x - y) <= 1 or abs((size - 1 - x) - y) <= 1:
                diagonal_dark += 1

    dark_count = len(dark_points)
    if dark_count == 0:
        return _zero_features()

    xs = [x for x, _ in dark_points]
    ys = [y for _, y in dark_points]
    centroid_x = sum(xs) / dark_count
    centroid_y = sum(ys) / dark_count
    span = float(size)

    return {
        "dark_ratio": dark_count / (size * size),
        "centroid_dx": (((centroid_x + 0.5) / span) - 0.5) * 2.0,
        "centroid_dy": (((centroid_y + 0.5) / span) - 0.5) * 2.0,
        "ink_w": (max(xs) - min(xs) + 1) / span,
        "ink_h": (max(ys) - min(ys) + 1) / span,
        "rows_with_ink": len(rows_with_ink) / span,
        "cols_with_ink": len(cols_with_ink) / span,
        "max_run": max_run / span,
        "diag_ratio": diagonal_dark / dark_count,
        "row_transitions": transitions / span / span,
    }
