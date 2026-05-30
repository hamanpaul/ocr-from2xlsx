"""Fuzzy-match an OCR/agent name candidate against a roster of confirmed names."""
from __future__ import annotations

import difflib

DEFAULT_THRESHOLD = 0.6


def roster_match(candidate: str, roster: list[str], threshold: float = DEFAULT_THRESHOLD) -> str | None:
    candidate = (candidate or "").strip()
    if not candidate or not roster:
        return None
    best_name: str | None = None
    best_score = 0.0
    for name in roster:
        score = difflib.SequenceMatcher(None, candidate, name).ratio()
        if score > best_score:
            best_score = score
            best_name = name
    return best_name if best_score >= threshold else None
