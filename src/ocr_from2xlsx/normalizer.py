from __future__ import annotations

from typing import Any

from ocr_from2xlsx.domain import Record


def normalize_raw_record(raw: dict[str, Any]) -> Record:
    review = raw.get("review")
    if not isinstance(review, dict):
        raw["review"] = {"status": "pending", "edited_by_user": False}
    else:
        review.setdefault("status", "pending")
        review.setdefault("edited_by_user", False)
    return Record.from_dict(raw)
