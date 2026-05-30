"""Append-only JSONL store of human name confirmations/corrections (learning data)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class Correction:
    field: str
    final_value: str
    record_id: str = ""
    crop_path: str | None = None
    ocr_raw: str = ""
    agent_suggestion: str | None = None
    roster_suggestion: str | None = None
    source: str = ""
    timestamp: str = ""


def default_correction_store_path(batch_json_path: Path | str) -> Path:
    return Path(batch_json_path).parent / "name_corrections.jsonl"


def append_correction(store_path: Path | str, correction: Correction) -> None:
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(correction), ensure_ascii=False) + "\n")


def load_corrections(store_path: Path | str) -> list[Correction]:
    path = Path(store_path)
    if not path.is_file():
        return []
    corrections: list[Correction] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        allowed_keys = Correction.__dataclass_fields__.keys()
        corrections.append(Correction(**{key: value for key, value in payload.items() if key in allowed_keys}))
    return corrections


def roster_from_store(store_path: Path | str, field: str = "name") -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for correction in load_corrections(store_path):
        if correction.field != field:
            continue
        value = (correction.final_value or "").strip()
        if value and value not in seen:
            seen.add(value)
            names.append(value)
    return names
