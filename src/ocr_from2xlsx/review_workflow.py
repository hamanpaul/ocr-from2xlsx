"""Pure helpers for the correction-workflow UX: toolbar modes, per-record badge
state, and roster-candidate ranking. No Tk/cv2 — plain-data decisions, unit-testable
in isolation, mirroring review_nav / flagged_fields."""
from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence

# Stable control identifiers the UI maps to actual toolbar buttons.
CORRECTION_CONTROLS: tuple[str, ...] = (
    "prev_record",
    "next_record",
    "confirm",
    "force_write",
    # Static source-image zoom (correction mode drives the ImageViewer, not the camera);
    # distinct ids from the scan-mode camera zoom so the corr/scan sets stay disjoint.
    "zoom_in_static",
    "zoom_out_static",
    "zoom_reset_static",
    "progress",
)
SCAN_CONTROLS: tuple[str, ...] = (
    "choose_camera",
    "capture_recognize",
    "import_folder_batch",
    "rotate",
    "zoom_in",
    "zoom_out",
)


def correction_mode_controls() -> tuple[str, ...]:
    """Toolbar control ids shown in correction mode."""
    return CORRECTION_CONTROLS


def scan_mode_controls() -> tuple[str, ...]:
    """Toolbar control ids shown in scan/capture mode."""
    return SCAN_CONTROLS


def record_badge_state(
    index: int,
    written_indices: Iterable[int],
    blocked_indices: Iterable[int] = (),
) -> str:
    """Return 'written' | 'blocked' | 'pending' for a record index. Written wins."""
    if index in set(written_indices):
        return "written"
    if index in set(blocked_indices):
        return "blocked"
    return "pending"


def rank_roster_candidates(
    name: str,
    roster: Sequence[str],
    limit: int | None = 5,
) -> list[str]:
    """Rank roster names for a name field: exact match first, then by descending
    similarity to ``name``; de-duplicated (first occurrence kept), capped at ``limit``.
    With an empty ``name``, returns the roster in order (de-duplicated)."""
    query = (name or "").strip()
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in roster:
        value = (candidate or "").strip()
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    if not query:
        return unique if limit is None else unique[:limit]
    ordered = sorted(
        unique,
        key=lambda value: (
            0 if value == query else 1,
            -difflib.SequenceMatcher(None, query, value).ratio(),
        ),
    )
    return ordered if limit is None else ordered[:limit]
