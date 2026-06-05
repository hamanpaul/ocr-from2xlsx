from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from plugins.paddleocr.mark_features import FEATURE_NAMES, extract_features
from plugins.paddleocr.mark_model import load_model, predict_proba
from training.eval_gate import choose_operating_point
from training.train_mark_model import (
    export_model,
    load_training_examples,
    main as train_main,
    train_linear_model,
)


def _feature_map(dark_ratio: float, ink_w: float = 0.0) -> dict[str, float]:
    features = {name: 0.0 for name in FEATURE_NAMES}
    features["dark_ratio"] = dark_ratio
    features["ink_w"] = ink_w
    return features


def _example(label: int, dark_ratio: float, *, source: str = "synthetic") -> dict[str, object]:
    return {"label": label, "features": _feature_map(dark_ratio), "source": source}


def _separable_examples() -> list[dict[str, object]]:
    return [
        _example(0, 0.05),
        _example(0, 0.15),
        _example(1, 0.85),
        _example(1, 0.95),
    ]


def _write_manifest_row(manifest_path: Path, row: dict[str, object]) -> None:
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _save_png(path: Path, region: list[list[int]]) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    image = Image.new("L", (len(region[0]), len(region)))
    image.putdata([value for row in region for value in row])
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def test_train_linear_model_exports_schema_and_scores_positives_above_negatives() -> None:
    examples = _separable_examples()

    model = train_linear_model(
        examples,
        epochs=120,
        learning_rate=0.5,
        min_precision=0.5,
        trained_at="2026-06-05T00:00:00Z",
    )

    assert model["version"] == 1
    assert model["feature_names"] == list(FEATURE_NAMES)
    assert len(model["mean"]) == len(FEATURE_NAMES)
    assert len(model["std"]) == len(FEATURE_NAMES)
    assert len(model["coef"]) == len(FEATURE_NAMES)
    assert isinstance(model["intercept"], float)
    assert isinstance(model["threshold"], float)
    assert model["trained_at"] == "2026-06-05T00:00:00Z"
    assert model["train_counts"] == {"synthetic": 4}

    positive_scores = [predict_proba(model, example["features"]) for example in examples if example["label"] == 1]
    negative_scores = [predict_proba(model, example["features"]) for example in examples if example["label"] == 0]
    assert min(positive_scores) > max(negative_scores)


def test_train_linear_model_threshold_matches_eval_gate_selection() -> None:
    examples = _separable_examples()
    model = train_linear_model(examples, epochs=80, learning_rate=0.4, min_precision=1.0)

    labels_scores = [(int(example["label"]), predict_proba(model, example["features"])) for example in examples]
    expected = choose_operating_point(labels_scores, min_precision=1.0)

    assert model["threshold"] == pytest.approx(float(expected["threshold"]))
    assert 0.0 <= model["threshold"] <= 1.0


def test_train_linear_model_uses_reject_all_threshold_when_no_safe_threshold_exists() -> None:
    examples = [_example(0, 0.5), _example(1, 0.5)]

    model = train_linear_model(examples, epochs=1, learning_rate=0.1, min_precision=1.0)
    scores = [predict_proba(model, example["features"]) for example in examples]

    assert model["threshold"] > max(scores)
    assert load_model_dict(model) == model


def test_train_linear_model_can_export_reject_all_threshold_above_one() -> None:
    examples = [_example(0, 0.5), _example(1, 0.5)]

    model = train_linear_model(examples, epochs=1, learning_rate=0.1, min_precision=1.0)

    assert model["threshold"] > 1.0
    assert load_model_dict(model) == model


def load_model_dict(model: dict[str, object]) -> dict[str, object]:
    output = Path.cwd() / "tests" / "_tmp_mark_model_reject_all.json"
    try:
        export_model(model, output)
        return load_model(output)
    finally:
        output.unlink(missing_ok=True)


def test_export_model_writes_sorted_json_loadable_by_mark_model(tmp_path: Path) -> None:
    output_path = tmp_path / "mark_model.json"
    model = train_linear_model(
        _separable_examples(),
        epochs=100,
        learning_rate=0.5,
        min_precision=0.5,
        trained_at="2026-06-05T00:00:00Z",
    )

    export_model(model, output_path)

    raw = output_path.read_text(encoding="utf-8")
    loaded_json = json.loads(raw)
    assert list(loaded_json) == sorted(loaded_json)
    assert raw.endswith("\n")
    assert load_model(output_path) == loaded_json


def test_load_training_examples_reads_manifest_pngs_and_preserves_metadata(tmp_path: Path) -> None:
    blank = [[255 for _ in range(4)] for _ in range(4)]
    marked = [[255 for _ in range(4)] for _ in range(4)]
    for index in range(4):
        marked[index][index] = 0

    dataset_dir = tmp_path / "dataset"
    manifest_path = dataset_dir / "manifest.jsonl"
    _save_png(dataset_dir / "crops" / "blank.png", blank)
    _save_png(dataset_dir / "crops" / "marked.png", marked)
    base_row = {
        "field": "gender",
        "code": "female",
        "provider": "unit-test",
        "record_id": "record-1",
        "created_at": "2026-06-05T00:00:00Z",
    }
    _write_manifest_row(manifest_path, {**base_row, "crop": "crops/blank.png", "label": 0, "source": "synthetic"})
    _write_manifest_row(manifest_path, {**base_row, "crop": "crops/marked.png", "label": 1, "source": "confirmed"})

    examples = load_training_examples(manifest_path, dataset_dir=dataset_dir)

    assert [example["label"] for example in examples] == [0, 1]
    assert [example["source"] for example in examples] == ["synthetic", "confirmed"]
    assert examples[0]["features"] == extract_features(blank)
    assert examples[1]["features"] == extract_features(marked)

    model = train_linear_model(examples, epochs=5, learning_rate=0.1, min_precision=0.5)
    assert model["train_counts"] == {"confirmed": 1, "synthetic": 1}


def test_cli_trains_and_exports_model(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    manifest_path = dataset_dir / "manifest.jsonl"
    output_path = tmp_path / "mark_model.json"
    blank = [[255 for _ in range(4)] for _ in range(4)]
    marked = [[0 for _ in range(4)] for _ in range(4)]
    _save_png(dataset_dir / "crops" / "blank.png", blank)
    _save_png(dataset_dir / "crops" / "marked.png", marked)
    row = {
        "field": "identity",
        "code": "patient",
        "source": "synthetic",
        "provider": "unit-test",
        "record_id": "record-1",
        "created_at": "2026-06-05T00:00:00Z",
    }
    _write_manifest_row(manifest_path, {**row, "crop": "crops/blank.png", "label": 0})
    _write_manifest_row(manifest_path, {**row, "crop": "crops/marked.png", "label": 1})

    result = train_main([str(manifest_path), "--output", str(output_path), "--min-precision", "0.5"])

    assert result == 0
    exported = load_model(output_path)
    assert exported["train_counts"] == {"synthetic": 2}
    assert all(math.isfinite(float(value)) for value in exported["coef"])
