from __future__ import annotations

import json
from pathlib import Path

from ocr_from2xlsx.constants import SCHEMA_VERSION
from ocr_from2xlsx.domain import Batch


def load_batch(path: Path | str) -> Batch:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {data.get('schema_version')!r}")
    return Batch.from_dict(data)


def dump_batch(batch: Batch, path: Path | str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(batch.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
