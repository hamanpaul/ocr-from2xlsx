"""Pure helpers for the correction-workflow UX: per-record badge state and
roster-candidate ranking. No Tk/cv2 — plain-data decisions, unit-testable
in isolation, mirroring review_nav / flagged_fields."""
from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence


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
