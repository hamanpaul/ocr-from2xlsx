from __future__ import annotations

from typing import Any

from ocr_from2xlsx.domain import Record


def normalize_raw_record(raw: dict[str, Any]) -> Record:
    return Record.from_dict(raw)
