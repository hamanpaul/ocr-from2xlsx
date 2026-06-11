"""Convert confirmed name corrections (name_corrections.jsonl) into rec label rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def corrections_to_label_rows(corrections_path: str | Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    path = Path(corrections_path)
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("field") != "name":
            continue
        value = payload.get("final_value")
        crop = payload.get("crop_path")
        if not isinstance(value, str) or not value.strip():
            continue
        if not isinstance(crop, str):
            continue
        crop_path = Path(crop)
        # if relative, resolve it relative to the corrections file parent
        if not crop_path.is_absolute():
            crop_path = path.parent / crop_path
        if not crop_path.is_file():
            continue
        # normalize to absolute path
        rows.append((str(crop_path.resolve()), value.strip()))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append confirmed name corrections to a rec label file.")
    parser.add_argument("corrections", help="name_corrections.jsonl path")
    parser.add_argument("--output", required=True, help="Label txt to append to (absolute crop paths)")
    args = parser.parse_args(argv)

    rows = corrections_to_label_rows(args.corrections)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for crop, value in rows:
            handle.write(f"{Path(crop).as_posix()}\t{value}\n")
    print(json.dumps({"rows": len(rows)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
