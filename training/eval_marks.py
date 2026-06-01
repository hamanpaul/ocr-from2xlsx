from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import FormLayout, service_record_layout
from ocr_from2xlsx.json_io import load_batch
from ocr_from2xlsx.record_access import get_by_path

from training.eval_answer_key import raw_records, resolve_source_image
from training.eval_metrics import compare_mark_sets, prf
from training.layout_render import SheetGeometry, option_mark_box, render_sheet_template, sheet_geometry

Mark = tuple[str, str]
MarkDetector = Callable[[list[list[int]]], bool]


def _gold_marks(layout: FormLayout, record: Record) -> set[Mark]:
    marks: set[Mark] = set()
    for field in layout.iter_fields():
        if field.kind not in ("single_choice", "multi_choice") or field.record_path is None:
            continue
        value = get_by_path(record, field.record_path)
        for code in field.selected_codes(value):
            marks.add((field.key, code))
    return marks


def _crop_region(image: Any, box: tuple[float, float, float, float]) -> list[list[int]]:
    x0, y0, x1, y1 = box
    left = max(0, int(x0))
    top = max(0, int(y0))
    right = min(image.width, max(left + 1, int(x1)))
    bottom = min(image.height, max(top + 1, int(y1)))
    crop = image.crop((left, top, right, bottom))
    pixel_iter = crop.get_flattened_data() if hasattr(crop, "get_flattened_data") else crop.getdata()
    pixels = list(pixel_iter)
    return [
        [int(value) for value in pixels[row * crop.width : (row + 1) * crop.width]]
        for row in range(crop.height)
    ]


def _masked_mark_region(
    source_image: Any,
    template_image: Any,
    box: tuple[float, float, float, float],
    *,
    dark_threshold: int = 128,
) -> list[list[int]]:
    source = _crop_region(source_image, box)
    template = _crop_region(template_image, box)
    return [
        [
            source_value if template_value >= dark_threshold else 255
            for source_value, template_value in zip(source_row, template_row, strict=True)
        ]
        for source_row, template_row in zip(source, template, strict=True)
    ]


def _predicted_marks(
    image_path: Path,
    *,
    layout: FormLayout,
    geom: SheetGeometry,
    detector: MarkDetector,
) -> set[Mark]:
    from PIL import Image

    rendered = render_sheet_template(geom)
    marks: set[Mark] = set()
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        blank_template = rendered.image.convert("L")
        for field in layout.iter_fields():
            if field.kind not in ("single_choice", "multi_choice"):
                continue
            for option in field.options:
                region = _masked_mark_region(
                    grayscale,
                    blank_template,
                    option_mark_box(layout, geom, field.key, option.code, rendered=rendered),
                )
                if detector(region):
                    marks.add((field.key, option.code))
    return marks


def _json_marks(marks: Iterable[Mark]) -> list[list[str]]:
    return [[field_key, code] for field_key, code in sorted(marks)]


def _aggregate_mark_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    tp = 0
    fp = 0
    fn = 0
    per_field_counts: dict[str, dict[str, int]] = {}
    for sample in samples:
        aggregate = sample["marks"]["aggregate"]
        tp += int(aggregate["tp"])
        fp += int(aggregate["fp"])
        fn += int(aggregate["fn"])
        for field_key, metrics in sample["marks"]["per_field"].items():
            counts = per_field_counts.setdefault(field_key, {"tp": 0, "fp": 0, "fn": 0})
            counts["tp"] += int(metrics["tp"])
            counts["fp"] += int(metrics["fp"])
            counts["fn"] += int(metrics["fn"])
    return {
        "aggregate": prf(tp, fp, fn),
        "per_field": {
            field_key: prf(counts["tp"], counts["fp"], counts["fn"])
            for field_key, counts in sorted(per_field_counts.items())
        },
    }


def _write_reports(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    marks = report["marks"]["aggregate"]
    markdown = "\n".join(
        [
            "# Synthetic mark evaluation",
            "",
            f"- Samples: {report['sample_count']}",
            f"- Precision: {marks['precision']:.4f}",
            f"- Recall: {marks['recall']:.4f}",
            f"- F1: {marks['f1']:.4f}",
            "",
        ]
    )
    (output_dir / "report.md").write_text(markdown, encoding="utf-8")


def evaluate_answer_key(
    answer_key_path: Path | str,
    *,
    layout: FormLayout,
    geom: SheetGeometry,
    output_dir: Path | str,
    detector: MarkDetector | None = None,
) -> dict[str, Any]:
    answer_key = Path(answer_key_path)
    if detector is None:
        from plugins.paddleocr.mark_detect import is_marked

        detector = is_marked
    raw_answer_records = raw_records(answer_key)
    batch = load_batch(answer_key)
    if len(raw_answer_records) != len(batch.records):
        raise ValueError("Answer key raw records and parsed records differ in length")

    samples: list[dict[str, Any]] = []
    for raw, record in zip(raw_answer_records, batch.records, strict=True):
        source_image = raw.get("source_image")
        if not isinstance(source_image, str) or not source_image:
            raise ValueError(f"Record {record.record_id!r} is missing source_image")
        image_path = resolve_source_image(answer_key, source_image)
        gold = _gold_marks(layout, record)
        pred = _predicted_marks(image_path, layout=layout, geom=geom, detector=detector)
        samples.append(
            {
                "record_id": record.record_id,
                "source_image": str(image_path),
                "gold_marks": _json_marks(gold),
                "predicted_marks": _json_marks(pred),
                "marks": compare_mark_sets(gold, pred),
            }
        )

    report = {
        "kind": "mark-blinded",
        "sample_count": len(samples),
        "marks": _aggregate_mark_metrics(samples),
        "samples": samples,
    }
    _write_reports(report, Path(output_dir))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate synthetic checkbox mark detection against answers.json.")
    parser.add_argument("answers", type=Path, help="Path to training answers.json")
    parser.add_argument("--workbook", type=Path, required=True, help="Blank workbook used for geometry")
    parser.add_argument("--sheet-name", default="服務紀錄表", help="Workbook sheet name")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for report.json/report.md")
    args = parser.parse_args(argv)

    evaluate_answer_key(
        args.answers,
        layout=service_record_layout(),
        geom=sheet_geometry(args.workbook, sheet_name=args.sheet_name),
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
