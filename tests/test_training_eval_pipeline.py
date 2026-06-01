from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from ocr_from2xlsx.constants import SCHEMA_VERSION
from ocr_from2xlsx.form_layout import Field, FormLayout, Option, Section
from training.eval_pipeline import evaluate_answer_key


class FakeBackend:
    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record
        self.pages: list[Any] = []

    def extract(self, page: Any) -> dict[str, Any]:
        self.pages.append(page)
        return self.record


def _layout() -> FormLayout:
    return FormLayout(
        template_id="tiny",
        sections=(
            Section(
                id="main",
                title="Main",
                fields=(
                    Field("name", "Name", "text", "name", "A1"),
                    Field(
                        "identity",
                        "Identity",
                        "single_choice",
                        "identity",
                        "A2",
                        (Option("病人", "patient", "A2"), Option("親友", "family", "A3")),
                    ),
                    Field(
                        "supplies",
                        "Supplies",
                        "multi_choice",
                        "services.supplies",
                        "A4",
                        (Option("口罩", "mask", "A4"), Option("手套", "glove", "A5")),
                    ),
                ),
            ),
        ),
    )


def _answers(path: Path) -> Path:
    image_path = path.parent / "sample.png"
    image_path.write_bytes(b"not-used-by-fake-backend")
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "source_batch": {
                    "created_at": "2026-06-01T00:00:00Z",
                    "source_type": "training_synthetic",
                    "template_name": "service_record.v1",
                },
                "records": [
                    {
                        "record_id": "gold-001",
                        "service_date": "",
                        "identity": "patient",
                        "gender": "",
                        "name": "Alice",
                        "medical_record_no": "",
                        "services": {"supplies": ["mask", "glove"]},
                        "source_image": "sample.png",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_eval_pipeline_imports_without_plugin_bundle() -> None:
    script = """
import importlib.abc
import sys

class BlockPaddleOcr(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "plugins.paddleocr" or fullname.startswith("plugins.paddleocr."):
            raise ModuleNotFoundError(fullname)
        return None

sys.meta_path.insert(0, BlockPaddleOcr())
from training import eval_pipeline
assert callable(eval_pipeline.main)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_evaluate_answer_key_uses_backend_and_emits_diagnostic_report(tmp_path: Path) -> None:
    answers_path = _answers(tmp_path / "answers.json")
    backend = FakeBackend(
        {
            "record_id": "pred-001",
            "service_date": "",
            "identity": "family",
            "gender": "",
            "name": "Alice",
            "medical_record_no": "",
            "services": {"supplies": ["mask"]},
        }
    )

    report = evaluate_answer_key(
        answers_path,
        layout=_layout(),
        output_dir=tmp_path / "pipeline-eval",
        backend=backend,
    )

    assert backend.pages[0].template_id == "tiny"
    assert backend.pages[0].source.kind == "training_synthetic"
    assert report["kind"] == "pipeline-diagnostic"
    assert report["sample_count"] == 1
    assert report["records"]["scalar"] == {"total": 2, "correct": 1, "accuracy": 0.5}
    assert report["records"]["multi_choice"]["tp"] == 1
    assert report["records"]["multi_choice"]["fn"] == 1
    assert report["samples"][0]["record_id"] == "gold-001"
    assert report["samples"][0]["predicted_record_id"] == "pred-001"
    assert (tmp_path / "pipeline-eval" / "report.json").is_file()
    assert "Synthetic pipeline diagnostic" in (tmp_path / "pipeline-eval" / "report.md").read_text(encoding="utf-8")
