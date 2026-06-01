from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ocr_from2xlsx.domain import Record, SourceInfo
from ocr_from2xlsx.form_layout import FormLayout, service_record_layout
from ocr_from2xlsx.json_io import load_batch

from training.eval_answer_key import raw_records, resolve_source_image
from training.eval_metrics import compare_records, prf


@dataclass(frozen=True, slots=True)
class SyntheticPreparedPage:
    image_path: Path
    source: SourceInfo
    template_id: str


class OcrBackend(Protocol):
    def extract(self, page: SyntheticPreparedPage) -> dict[str, Any]:
        ...


def _aggregate_record_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    scalar_total = 0
    scalar_correct = 0
    multi_tp = 0
    multi_fp = 0
    multi_fn = 0
    for sample in samples:
        comparison = sample["comparison"]
        scalar = comparison["scalar"]
        scalar_total += int(scalar["total"])
        scalar_correct += int(scalar["correct"])
        multi = comparison["multi_choice"]
        multi_tp += int(multi["tp"])
        multi_fp += int(multi["fp"])
        multi_fn += int(multi["fn"])
    return {
        "scalar": {
            "total": scalar_total,
            "correct": scalar_correct,
            "accuracy": scalar_correct / scalar_total if scalar_total else 0.0,
        },
        "multi_choice": prf(multi_tp, multi_fp, multi_fn),
    }


def _write_reports(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    scalar = report["records"]["scalar"]
    multi = report["records"]["multi_choice"]
    markdown = "\n".join(
        [
            "# Synthetic pipeline diagnostic",
            "",
            f"- Samples: {report['sample_count']}",
            f"- Scalar accuracy: {scalar['accuracy']:.4f}",
            f"- Multi-choice precision: {multi['precision']:.4f}",
            f"- Multi-choice recall: {multi['recall']:.4f}",
            f"- Multi-choice F1: {multi['f1']:.4f}",
            "",
        ]
    )
    (output_dir / "report.md").write_text(markdown, encoding="utf-8")


def _prepared_page(image_path: Path, *, template_id: str) -> SyntheticPreparedPage:
    return SyntheticPreparedPage(
        image_path=image_path,
        template_id=template_id,
        source=SourceInfo(
            kind="training_synthetic",
            image_path=str(image_path),
            preprocessed_image_path=str(image_path),
            template_id=template_id,
        ),
    )


def evaluate_answer_key(
    answer_key_path: Path | str,
    *,
    layout: FormLayout,
    output_dir: Path | str,
    backend: OcrBackend,
) -> dict[str, Any]:
    answer_key = Path(answer_key_path)
    raw_answer_records = raw_records(answer_key)
    batch = load_batch(answer_key)
    if len(raw_answer_records) != len(batch.records):
        raise ValueError("Answer key raw records and parsed records differ in length")

    samples: list[dict[str, Any]] = []
    for raw, gold_record in zip(raw_answer_records, batch.records, strict=True):
        source_image = raw.get("source_image")
        if not isinstance(source_image, str) or not source_image:
            raise ValueError(f"Record {gold_record.record_id!r} is missing source_image")
        image_path = resolve_source_image(answer_key, source_image)
        predicted_record = Record.from_dict(backend.extract(_prepared_page(image_path, template_id=layout.template_id)))
        samples.append(
            {
                "record_id": gold_record.record_id,
                "predicted_record_id": predicted_record.record_id,
                "source_image": str(image_path),
                "comparison": compare_records(layout, gold_record, predicted_record),
            }
        )

    report = {
        "kind": "pipeline-diagnostic",
        "sample_count": len(samples),
        "records": _aggregate_record_metrics(samples),
        "samples": samples,
    }
    _write_reports(report, Path(output_dir))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run diagnostic synthetic OCR pipeline evaluation.")
    parser.add_argument("answers", type=Path, help="Path to training answers.json")
    parser.add_argument("--ocr-plugin-dir", type=Path, required=True, help="OCR plugin directory")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for report.json/report.md")
    args = parser.parse_args(argv)
    from ocr_from2xlsx.plugin_backend import PluginOcrBackend

    evaluate_answer_key(
        args.answers,
        layout=service_record_layout(),
        output_dir=args.output_dir,
        backend=PluginOcrBackend.resolve(explicit_dir=args.ocr_plugin_dir),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
