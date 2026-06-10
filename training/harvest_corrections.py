from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ocr_from2xlsx.form_layout import FormLayout
from ocr_from2xlsx.record_access import get_by_path

from training.mark_dataset import append_row, write_crop_image

Mark = tuple[str, str]


def _record_id(record: Any) -> str:
    if isinstance(record, dict):
        value = record.get("record_id")
    else:
        value = getattr(record, "record_id", None)
    if not isinstance(value, str) or not value:
        raise ValueError("record must provide a non-empty record_id")
    return value


def _created_at(value: str | None) -> str:
    if value is not None:
        if not isinstance(value, str) or not value:
            raise ValueError("created_at must be a non-empty string")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-_")
    return safe or "unknown"


def _unique_filename(crops_dir: Path, base_filename: str) -> str:
    candidate = base_filename
    stem = Path(base_filename).stem
    suffix = Path(base_filename).suffix
    index = 2
    while (crops_dir / candidate).exists():
        candidate = f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def _selected_marks(record: Any, layout: FormLayout) -> set[Mark]:
    marks: set[Mark] = set()
    for field in layout.iter_fields():
        if field.kind not in ("single_choice", "multi_choice") or field.record_path is None:
            continue
        valid_codes = {option.code for option in field.options}
        value = get_by_path(record, field.record_path)
        for code in field.selected_codes(value):
            if code not in valid_codes:
                raise ValueError(f"unknown selected code for {field.key}: {code}")
            marks.add((field.key, code))
    return marks


def _layout_option_keys(layout: FormLayout) -> set[Mark]:
    return {
        (field.key, option.code)
        for field in layout.iter_fields()
        if field.kind in ("single_choice", "multi_choice")
        for option in field.options
    }


def harvest_record_corrections(
    record: Any,
    layout: FormLayout,
    image_path: str | Path,
    template_boxes_path: str | Path,
    dataset_dir: str | Path,
    *,
    source: str = "correction",
    provider: str = "geometry",
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    from plugins.paddleocr.crop_provider import GeometryCropProvider

    record_id = _record_id(record)
    timestamp = _created_at(created_at)
    dataset = Path(dataset_dir)
    crops_dir = dataset / "crops"
    manifest_path = dataset / "manifest.jsonl"
    selected = _selected_marks(record, layout)
    crops = GeometryCropProvider(template_boxes_path).crop(image_path)
    valid_keys = _layout_option_keys(layout)
    invalid_keys = sorted(key for key in crops if key not in valid_keys)
    if invalid_keys:
        field, code = invalid_keys[0]
        raise ValueError(f"template box is not present in layout options: {field}.{code}")

    rows: list[dict[str, Any]] = []
    for (field, code), region in crops.items():
        filename = _unique_filename(
            crops_dir,
            f"{_safe_part(record_id)}-{_safe_part(field)}-{_safe_part(code)}.png",
        )
        write_crop_image(region, crops_dir, filename)
        row = {
            "crop": (Path("crops") / filename).as_posix(),
            "label": 1 if (field, code) in selected else 0,
            "field": field,
            "code": code,
            "source": source,
            "provider": provider,
            "record_id": record_id,
            "created_at": timestamp,
        }
        append_row(manifest_path, row)
        rows.append(row)
    return rows


def harvest_answer_batch(
    answers_path: str | Path,
    layout: FormLayout,
    template_boxes_path: str | Path,
    dataset_dir: str | Path,
    *,
    source: str = "synthetic",
    provider: str = "geometry",
    created_at: str | None = None,
) -> int:
    """Harvest every record in a synthetic answers.json batch; returns total manifest rows."""
    from training.eval_answer_key import raw_records, resolve_source_image

    answers = Path(answers_path)
    total = 0
    for payload in raw_records(answers):
        source_image = payload.get("source_image")
        if not isinstance(source_image, str) or not source_image:
            record_id = payload.get("record_id", "<unknown>")
            raise ValueError(f"answers record {record_id} is missing source_image")
        rows = harvest_record_corrections(
            payload,
            layout,
            resolve_source_image(answers, source_image),
            template_boxes_path,
            dataset_dir,
            source=source,
            provider=provider,
            created_at=created_at,
        )
        total += len(rows)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Harvest labeled checkbox crops from a confirmed record JSON.")
    parser.add_argument("record_json", nargs="?", help="Path to a confirmed service-record JSON object")
    parser.add_argument("--answers", help="Synthetic answers.json batch to harvest instead of a single record")
    parser.add_argument("--image", help="Aligned source image path (required with record_json)")
    parser.add_argument("--template-boxes", required=True, help="Geometry template_boxes.json path")
    parser.add_argument("--dataset-dir", required=True, help="Output mark dataset directory")
    parser.add_argument("--source", help="Manifest source value (default: correction, or synthetic with --answers)")
    parser.add_argument("--provider", default="geometry", help="Manifest provider value")
    parser.add_argument("--created-at", help="Optional timestamp for manifest rows")
    args = parser.parse_args(argv)

    if bool(args.record_json) == bool(args.answers):
        parser.error("provide exactly one of record_json or --answers")

    from ocr_from2xlsx.form_layout import service_record_layout

    if args.answers:
        total = harvest_answer_batch(
            args.answers,
            service_record_layout(),
            args.template_boxes,
            args.dataset_dir,
            source=args.source or "synthetic",
            provider=args.provider,
            created_at=args.created_at,
        )
        print(json.dumps({"rows": total}, ensure_ascii=False))
        return 0

    if not args.image:
        parser.error("--image is required with record_json")

    from ocr_from2xlsx.domain import Record

    payload = json.loads(Path(args.record_json).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("record_json must contain a JSON object")
    rows = harvest_record_corrections(
        Record.from_dict(payload),
        service_record_layout(),
        args.image,
        args.template_boxes,
        args.dataset_dir,
        source=args.source or "correction",
        provider=args.provider,
        created_at=args.created_at,
    )
    print(json.dumps({"rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
