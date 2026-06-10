"""Retrain the mark model from harvested corpora and deploy through the eval gate."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from plugins.paddleocr.mark_detect import is_marked
from plugins.paddleocr.mark_features import extract_features
from plugins.paddleocr.mark_model import load_model, predict_proba

from training.eval_gate import decide_candidate, metrics_at_threshold
from training.mark_dataset import read_manifest
from training.train_mark_model import export_model, load_training_examples, train_linear_model

WEIGHTS_FILENAME = "mark_model.json"
AUDIT_FILENAME = "mark_audit.jsonl"


def runtime_weights_dir() -> Path:
    """User-level runtime weights directory shared with the plugin loader."""
    home = os.environ.get("OCR_FROM2XLSX_HOME")
    return Path(home) if home else Path.home() / ".ocr_from2xlsx"


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _image_to_region(path: Path) -> list[list[int]]:
    from PIL import Image

    with Image.open(path) as image:
        grayscale = image.convert("L")
        width, height = grayscale.size
        pixels = grayscale.tobytes()
    return [list(pixels[row * width : (row + 1) * width]) for row in range(height)]


def load_holdout_examples(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Load holdout rows keeping both the raw region (for is_marked) and features."""
    manifest = Path(manifest_path)
    root = manifest.parent
    examples: list[dict[str, Any]] = []
    for row in read_manifest(manifest):
        region = _image_to_region(root / row["crop"])
        example = dict(row)
        example["label"] = int(row["label"])
        example["region"] = region
        example["features"] = extract_features(region)
        examples.append(example)
    return examples


def holdout_metrics(
    examples: Sequence[Mapping[str, Any]],
    model: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Precision/recall of a model (or the is_marked baseline) on holdout examples."""
    if model is None:
        labels_scores = [
            (int(example["label"]), 1.0 if is_marked(example["region"]) else 0.0)
            for example in examples
        ]
        return {**metrics_at_threshold(labels_scores, 0.5), "source": "is_marked"}
    labels_scores = [
        (int(example["label"]), predict_proba(model, example["features"]))
        for example in examples
    ]
    return {**metrics_at_threshold(labels_scores, float(model["threshold"])), "source": "model"}


def _atomic_export(model: Mapping[str, Any], weights_path: Path) -> None:
    temp_path = weights_path.with_name(weights_path.name + ".tmp")
    export_model(model, temp_path)
    os.replace(temp_path, weights_path)


def run_retrain(
    manifests: Sequence[str | Path],
    holdout_manifest: str | Path,
    *,
    validation_manifest: str | Path | None = None,
    runtime_dir: str | Path | None = None,
    current_model_path: str | Path | None = None,
    min_precision: float = 0.99,
    epochs: int = 200,
    learning_rate: float = 0.2,
    trained_at: str | None = None,
    created_at: str | None = None,
    audit_log: str | Path | None = None,
) -> dict[str, Any]:
    """Train a candidate, gate it against current weights on holdout, deploy only if safe."""
    runtime = Path(runtime_dir) if runtime_dir is not None else runtime_weights_dir()
    weights_path = runtime / WEIGHTS_FILENAME

    examples: list[dict[str, Any]] = []
    for manifest in manifests:
        examples.extend(load_training_examples(manifest))
    validation_examples = (
        load_training_examples(validation_manifest) if validation_manifest is not None else None
    )
    candidate = train_linear_model(
        examples,
        epochs=epochs,
        learning_rate=learning_rate,
        min_precision=min_precision,
        trained_at=trained_at if trained_at is not None else _now_utc(),
        validation_examples=validation_examples,
    )

    holdout = load_holdout_examples(holdout_manifest)
    candidate_metrics = holdout_metrics(holdout, candidate)
    current_path = Path(current_model_path) if current_model_path is not None else weights_path
    current_model = load_model(current_path) if current_path.is_file() else None
    current_metrics = holdout_metrics(holdout, current_model)

    decision = decide_candidate(current_metrics, candidate_metrics, min_precision=min_precision)
    adopt = bool(decision["adopt"])
    if adopt:
        runtime.mkdir(parents=True, exist_ok=True)
        _atomic_export(candidate, weights_path)

    entry: dict[str, Any] = {
        "created_at": created_at if created_at is not None else _now_utc(),
        "adopt": adopt,
        "reason": str(decision["reason"]),
        "min_precision": float(min_precision),
        "current_metrics": current_metrics,
        "candidate_metrics": candidate_metrics,
        "train_counts": candidate["train_counts"],
        "holdout_size": len(holdout),
        "validation_size": len(validation_examples) if validation_examples is not None else None,
        "weights_path": str(weights_path),
    }
    audit_path = Path(audit_log) if audit_log is not None else runtime / AUDIT_FILENAME
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    return {
        "adopt": adopt,
        "reason": str(decision["reason"]),
        "current_metrics": current_metrics,
        "candidate_metrics": candidate_metrics,
        "weights_path": str(weights_path),
        "audit_log": str(audit_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Retrain the checkbox mark model and deploy runtime weights only when the eval gate passes.",
    )
    parser.add_argument("manifests", nargs="+", help="JSONL mark dataset manifests (synthetic and/or corrections)")
    parser.add_argument("--holdout", required=True, help="Holdout manifest used by the eval gate (never trained on)")
    parser.add_argument(
        "--validation",
        help="Clean validation manifest for operating-point calibration (default: calibrate on training examples)",
    )
    parser.add_argument("--runtime-dir", help="Runtime weights directory (default: OCR_FROM2XLSX_HOME or ~/.ocr_from2xlsx)")
    parser.add_argument("--current-model", help="Current weights to gate against (default: runtime weights)")
    parser.add_argument("--min-precision", type=float, default=0.99, help="Minimum precision for threshold and gate")
    parser.add_argument("--epochs", type=int, default=200, help="Number of deterministic gradient epochs")
    parser.add_argument("--learning-rate", type=float, default=0.2, help="Gradient descent learning rate")
    parser.add_argument("--audit-log", help="Audit JSONL path (default: <runtime-dir>/mark_audit.jsonl)")
    args = parser.parse_args(argv)

    result = run_retrain(
        args.manifests,
        args.holdout,
        validation_manifest=args.validation,
        runtime_dir=args.runtime_dir,
        current_model_path=args.current_model,
        min_precision=args.min_precision,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        audit_log=args.audit_log,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["adopt"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
