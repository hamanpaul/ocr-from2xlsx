from __future__ import annotations

import json
from pathlib import Path
from typing import Any

Region = list[list[int]]

REQUIRED_FIELDS = ("crop", "label", "field", "code", "source", "provider", "record_id", "created_at")
REQUIRED_STRINGS = ("crop", "field", "code", "source", "provider", "record_id", "created_at")


def _validate_crop_path(value: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("manifest row crop must be a relative path under crops/")
    if len(path.parts) < 2 or path.parts[0] != "crops":
        raise ValueError("manifest row crop must be under crops/")
    if path.name in ("", ".", ".."):
        raise ValueError("manifest row crop must include a filename")


def _validate_row(row: dict[str, Any]) -> None:
    for field in REQUIRED_FIELDS:
        if field not in row:
            raise ValueError(f"manifest row missing required field: {field}")
    label = row["label"]
    if isinstance(label, bool) or not isinstance(label, int) or label not in (0, 1):
        raise ValueError("manifest row label must be 0 or 1")
    for field in REQUIRED_STRINGS:
        value = row[field]
        if not isinstance(value, str) or not value:
            raise ValueError(f"manifest row {field} must be a non-empty string")
    _validate_crop_path(row["crop"])
    try:
        json.dumps(row, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("manifest row must be JSON-serializable") from exc


def append_row(manifest_path: str | Path, row: dict[str, Any]) -> None:
    _validate_row(row)
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_manifest(manifest_path: str | Path) -> list[dict[str, Any]]:
    path = Path(manifest_path)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"manifest line {line_number} must be a JSON object")
            _validate_row(row)
            rows.append(row)
    return rows


def write_crop_image(region: Region, crops_dir: str | Path, filename: str) -> Path:
    if not region or not region[0]:
        raise ValueError("region must contain at least one pixel")
    width = len(region[0])
    if any(len(row) != width for row in region):
        raise ValueError("region rows must all have the same width")

    from PIL import Image

    filename_path = Path(filename)
    if filename_path.is_absolute() or ".." in filename_path.parts or len(filename_path.parts) != 1:
        raise ValueError("filename must be a simple relative filename")
    path = Path(crops_dir) / filename_path
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("L", (width, len(region)))
    image.putdata([int(value) for row in region for value in row])
    image.save(path, format="PNG")
    return path
