from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ocr_from2xlsx.constants import SCHEMA_VERSION


def resolve_source_image(answer_key_path: Path | str, source_image: str) -> Path:
    path = Path(source_image)
    if path.is_absolute():
        return path
    return Path(answer_key_path).parent / path


def raw_records(answer_key_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(answer_key_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Answer key must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {payload.get('schema_version')!r}")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Answer key records must be a list")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Answer key records[{index}] must be an object")
    return records
