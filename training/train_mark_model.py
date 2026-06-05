"""Deterministic stdlib training/export for checkbox mark models."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from plugins.paddleocr.mark_features import FEATURE_NAMES, extract_features
from plugins.paddleocr.mark_model import predict_proba
from training.eval_gate import choose_operating_point
from training.mark_dataset import read_manifest


DEFAULT_TRAINED_AT = "1970-01-01T00:00:00Z"


def _sigmoid(score: float) -> float:
    if score >= 0.0:
        exp_neg = math.exp(-score)
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(score)
    return exp_pos / (1.0 + exp_pos)


def _image_to_region(path: Path) -> list[list[int]]:
    from PIL import Image

    with Image.open(path) as image:
        grayscale = image.convert("L")
        width, height = grayscale.size
        pixels = grayscale.tobytes()
    return [list(pixels[row * width : (row + 1) * width]) for row in range(height)]


def load_training_examples(manifest_path: str | Path, dataset_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Load manifest rows, read crop PNGs lazily with Pillow, and extract features."""
    manifest = Path(manifest_path)
    root = Path(dataset_dir) if dataset_dir is not None else manifest.parent
    examples: list[dict[str, Any]] = []
    for row in read_manifest(manifest):
        crop_path = root / row["crop"]
        region = _image_to_region(crop_path)
        example = dict(row)
        example["label"] = int(row["label"])
        example["features"] = extract_features(region)
        examples.append(example)
    return examples


def _feature_matrix(examples: Sequence[Mapping[str, Any]]) -> tuple[list[list[float]], list[int]]:
    if not examples:
        raise ValueError("at least one training example is required")

    matrix: list[list[float]] = []
    labels: list[int] = []
    for index, example in enumerate(examples):
        label = example.get("label")
        if isinstance(label, bool) or int(label) not in (0, 1):
            raise ValueError(f"example {index} label must be 0 or 1")
        features = example.get("features")
        if not isinstance(features, Mapping):
            raise ValueError(f"example {index} features must be a mapping")

        row: list[float] = []
        for name in FEATURE_NAMES:
            if name not in features:
                raise ValueError(f"example {index} features missing {name!r}")
            value = float(features[name])
            if not math.isfinite(value):
                raise ValueError(f"example {index} feature {name!r} must be finite")
            row.append(value)
        matrix.append(row)
        labels.append(int(label))
    return matrix, labels


def _standardize(matrix: Sequence[Sequence[float]]) -> tuple[list[float], list[float], list[list[float]]]:
    count = len(matrix)
    width = len(FEATURE_NAMES)
    mean = [sum(row[column] for row in matrix) / count for column in range(width)]
    std: list[float] = []
    standardized: list[list[float]] = []
    for column in range(width):
        variance = sum((row[column] - mean[column]) ** 2 for row in matrix) / count
        value = math.sqrt(variance)
        std.append(value if value > 1e-12 else 1.0)

    for row in matrix:
        standardized.append([(row[column] - mean[column]) / std[column] for column in range(width)])
    return mean, std, standardized


def _source_counts(examples: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(example.get("source", "unknown")) for example in examples)
    return dict(sorted(counts.items()))


def train_linear_model(
    examples: Sequence[Mapping[str, Any]],
    *,
    epochs: int = 200,
    learning_rate: float = 0.2,
    min_precision: float = 0.99,
    trained_at: str | None = None,
) -> dict[str, Any]:
    """Train a deterministic standardized logistic model and select a safe threshold."""
    if epochs < 0:
        raise ValueError("epochs must be non-negative")
    if not math.isfinite(float(learning_rate)) or learning_rate <= 0.0:
        raise ValueError("learning_rate must be a positive finite number")

    matrix, labels = _feature_matrix(examples)
    mean, std, standardized = _standardize(matrix)
    coef = [0.0 for _ in FEATURE_NAMES]
    intercept = 0.0
    rate = float(learning_rate)
    count = len(labels)

    for _ in range(int(epochs)):
        grad_coef = [0.0 for _ in FEATURE_NAMES]
        grad_intercept = 0.0
        for row, label in zip(standardized, labels, strict=True):
            score = intercept + sum(weight * value for weight, value in zip(coef, row, strict=True))
            error = _sigmoid(score) - label
            grad_intercept += error
            for column, value in enumerate(row):
                grad_coef[column] += error * value
        intercept -= rate * grad_intercept / count
        for column in range(len(coef)):
            coef[column] -= rate * grad_coef[column] / count

    model: dict[str, Any] = {
        "version": 1,
        "feature_names": list(FEATURE_NAMES),
        "mean": [float(value) for value in mean],
        "std": [float(value) for value in std],
        "coef": [float(value) for value in coef],
        "intercept": float(intercept),
        "threshold": 1.0,
        "trained_at": trained_at if trained_at is not None else DEFAULT_TRAINED_AT,
        "train_counts": _source_counts(examples),
    }
    labels_scores = [
        (label, predict_proba(model, dict(zip(FEATURE_NAMES, row, strict=True))))
        for label, row in zip(labels, matrix, strict=True)
    ]
    operating_point = choose_operating_point(labels_scores, min_precision=min_precision)
    threshold = float(operating_point["threshold"])
    model["threshold"] = threshold
    return model


def export_model(model: Mapping[str, Any], output_path: str | Path) -> None:
    """Write a deterministic JSON mark model."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(model, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train and export a lightweight checkbox mark model.")
    parser.add_argument("manifest", help="JSONL mark dataset manifest")
    parser.add_argument("--dataset-dir", help="Dataset root for manifest crop paths")
    parser.add_argument("--output", required=True, help="Output mark_model.json path")
    parser.add_argument("--min-precision", type=float, default=0.99, help="Minimum precision for threshold selection")
    parser.add_argument("--epochs", type=int, default=200, help="Number of deterministic gradient epochs")
    parser.add_argument("--learning-rate", type=float, default=0.2, help="Gradient descent learning rate")
    args = parser.parse_args(argv)

    examples = load_training_examples(args.manifest, dataset_dir=args.dataset_dir)
    model = train_linear_model(
        examples,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        min_precision=args.min_precision,
    )
    export_model(model, args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
