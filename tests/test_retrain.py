from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

MARKED_ROW = {
    "field": "identity",
    "code": "patient",
    "source": "synthetic",
    "provider": "geometry",
    "created_at": "2026-06-10T00:00:00Z",
}


def _diagonal_region(size: int = 8, dark_pixels: int = 6) -> list[list[int]]:
    region = [[255 for _ in range(size)] for _ in range(size)]
    for index in range(1, dark_pixels + 1):
        region[index][index] = 0
    return region


def _blank_region(size: int = 8) -> list[list[int]]:
    return [[255 for _ in range(size)] for _ in range(size)]


def _write_dataset(dataset_dir: Path, *, marked: int, blank: int, prefix: str) -> Path:
    from training.mark_dataset import append_row, write_crop_image

    manifest = dataset_dir / "manifest.jsonl"
    crops_dir = dataset_dir / "crops"
    for index in range(marked):
        filename = f"{prefix}-marked-{index}.png"
        write_crop_image(_diagonal_region(), crops_dir, filename)
        append_row(
            manifest,
            {
                **MARKED_ROW,
                "crop": f"crops/{filename}",
                "label": 1,
                "record_id": f"{prefix}-marked-{index}",
            },
        )
    for index in range(blank):
        filename = f"{prefix}-blank-{index}.png"
        write_crop_image(_blank_region(), crops_dir, filename)
        append_row(
            manifest,
            {
                **MARKED_ROW,
                "crop": f"crops/{filename}",
                "label": 0,
                "record_id": f"{prefix}-blank-{index}",
            },
        )
    return manifest


def test_light_marks_are_invisible_to_is_marked_baseline() -> None:
    from plugins.paddleocr.mark_detect import is_marked

    assert is_marked(_diagonal_region()) is False
    assert is_marked(_blank_region()) is False


def test_run_retrain_adopts_candidate_over_baseline_and_writes_runtime_weights(tmp_path: Path) -> None:
    from plugins.paddleocr.mark_model import load_model
    from training.retrain import run_retrain

    train_manifest = _write_dataset(tmp_path / "train", marked=6, blank=6, prefix="train")
    holdout_manifest = _write_dataset(tmp_path / "holdout", marked=4, blank=4, prefix="holdout")
    runtime_dir = tmp_path / "runtime"

    result = run_retrain(
        [train_manifest],
        holdout_manifest,
        runtime_dir=runtime_dir,
        trained_at="2026-06-10T00:00:00Z",
        created_at="2026-06-10T00:00:00Z",
    )

    assert result["adopt"] is True
    assert result["candidate_metrics"]["recall"] > result["current_metrics"]["recall"]
    assert result["candidate_metrics"]["precision"] >= 0.99
    assert result["current_metrics"]["source"] == "is_marked"

    weights_path = runtime_dir / "mark_model.json"
    assert result["weights_path"] == str(weights_path)
    model = load_model(weights_path)
    assert model["trained_at"] == "2026-06-10T00:00:00Z"

    audit_lines = (runtime_dir / "mark_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 1
    entry = json.loads(audit_lines[0])
    assert entry["adopt"] is True
    assert entry["candidate_metrics"]["recall"] == result["candidate_metrics"]["recall"]


def test_run_retrain_rejects_degraded_candidate_and_keeps_existing_weights(tmp_path: Path) -> None:
    from training.retrain import run_retrain

    train_manifest = _write_dataset(tmp_path / "train", marked=6, blank=6, prefix="train")
    holdout_manifest = _write_dataset(tmp_path / "holdout", marked=4, blank=4, prefix="holdout")
    runtime_dir = tmp_path / "runtime"

    first = run_retrain(
        [train_manifest],
        holdout_manifest,
        runtime_dir=runtime_dir,
        trained_at="2026-06-10T00:00:00Z",
        created_at="2026-06-10T00:00:00Z",
    )
    assert first["adopt"] is True
    weights_path = runtime_dir / "mark_model.json"
    adopted_bytes = weights_path.read_bytes()

    second = run_retrain(
        [train_manifest],
        holdout_manifest,
        runtime_dir=runtime_dir,
        epochs=0,
        trained_at="2026-06-10T01:00:00Z",
        created_at="2026-06-10T01:00:00Z",
    )

    assert second["adopt"] is False
    assert second["current_metrics"]["source"] == "model"
    assert weights_path.read_bytes() == adopted_bytes

    audit_lines = (runtime_dir / "mark_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 2
    rejected = json.loads(audit_lines[1])
    assert rejected["adopt"] is False
    assert rejected["reason"]


def test_run_retrain_calibrates_threshold_on_validation_manifest(tmp_path: Path) -> None:
    from training.retrain import run_retrain

    train_manifest = _write_dataset(tmp_path / "train", marked=6, blank=6, prefix="train")
    validation_manifest = _write_dataset(tmp_path / "validation", marked=3, blank=3, prefix="val")
    holdout_manifest = _write_dataset(tmp_path / "holdout", marked=4, blank=4, prefix="holdout")

    result = run_retrain(
        [train_manifest],
        holdout_manifest,
        validation_manifest=validation_manifest,
        runtime_dir=tmp_path / "runtime",
        trained_at="2026-06-10T00:00:00Z",
        created_at="2026-06-10T00:00:00Z",
    )

    assert result["adopt"] is True
    assert result["candidate_metrics"]["precision"] >= 0.99


def test_runtime_weights_dir_prefers_env_home(monkeypatch, tmp_path: Path) -> None:
    from training.retrain import runtime_weights_dir

    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path / "custom-home"))
    assert runtime_weights_dir() == tmp_path / "custom-home"

    monkeypatch.delenv("OCR_FROM2XLSX_HOME")
    assert runtime_weights_dir() == Path.home() / ".ocr_from2xlsx"


def test_retrain_cli_help_is_available() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "training.retrain", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert "--holdout" in completed.stdout
    assert "--min-precision" in completed.stdout
