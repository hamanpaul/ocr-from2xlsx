"""Pure helpers for the correction-workflow UX: per-record badge state.
No Tk/cv2 — plain-data decisions, unit-testable in isolation, mirroring
review_nav / flagged_fields."""
from __future__ import annotations

from collections.abc import Iterable


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
