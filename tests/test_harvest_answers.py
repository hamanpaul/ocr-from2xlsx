from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ocr_from2xlsx.form_layout import Field, FormLayout, Option, Section


def _tiny_layout() -> FormLayout:
    return FormLayout(
        template_id="tiny",
        sections=(
            Section(
                id="main",
                title="Main",
                fields=(
                    Field(
                        key="identity",
                        title="Identity",
                        kind="single_choice",
                        record_path="identity",
                        anchor_cell="A1",
                        options=(
                            Option(label="病人", code="patient", cell="A1"),
                            Option(label="親友", code="family", cell="A1"),
                        ),
                    ),
                    Field(
                        key="supplies",
                        title="Supplies",
                        kind="multi_choice",
                        record_path="services.supplies",
                        anchor_cell="A2",
                        options=(
                            Option(label="口罩", code="mask", cell="A2"),
                            Option(label="手套", code="glove", cell="A3"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _write_tiny_template(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "template_id": "tiny.v1",
                "boxes": [
                    {"field": "identity", "code": "patient", "box": [0.0, 0.0, 1.0, 1.0]},
                    {"field": "identity", "code": "family", "box": [1.0, 0.0, 2.0, 1.0]},
                    {"field": "supplies", "code": "mask", "box": [0.0, 1.0, 1.0, 2.0]},
                    {"field": "supplies", "code": "glove", "box": [1.0, 1.0, 2.0, 2.0]},
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_tiny_image(path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    image = Image.new("L", (2, 2))
    image.putdata([10, 20, 30, 40])
    image.save(path)


def _write_answers(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "service_record.v1",
                "source_batch": {
                    "created_at": "2026-06-10T00:00:00Z",
                    "source_type": "training_synthetic",
                    "template_name": "service_record.v1",
                },
                "records": records,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_harvest_answer_batch_appends_rows_for_every_record(tmp_path: Path) -> None:
    pytest.importorskip("PIL.Image")
    from training.harvest_corrections import harvest_answer_batch
    from training.mark_dataset import read_manifest

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_tiny_image(images_dir / "train-0001.png")
    _write_tiny_image(images_dir / "train-0002.png")
    template_path = tmp_path / "template_boxes.json"
    _write_tiny_template(template_path)
    answers_path = tmp_path / "answers.json"
    _write_answers(
        answers_path,
        [
            {
                "record_id": "train-0001",
                "identity": "patient",
                "services": {"supplies": ["mask"]},
                "training": True,
                "source_image": "images/train-0001.png",
            },
            {
                "record_id": "train-0002",
                "identity": "family",
                "services": {"supplies": ["mask", "glove"]},
                "training": True,
                "source_image": "images/train-0002.png",
            },
        ],
    )

    total = harvest_answer_batch(
        answers_path,
        _tiny_layout(),
        template_path,
        tmp_path / "dataset",
        source="synthetic",
        created_at="2026-06-10T01:02:03Z",
    )

    rows = read_manifest(tmp_path / "dataset" / "manifest.jsonl")
    assert total == 8
    assert len(rows) == 8
    assert {row["source"] for row in rows} == {"synthetic"}
    by_key = {(row["record_id"], row["field"], row["code"]): row["label"] for row in rows}
    assert by_key[("train-0001", "identity", "patient")] == 1
    assert by_key[("train-0001", "identity", "family")] == 0
    assert by_key[("train-0001", "supplies", "mask")] == 1
    assert by_key[("train-0001", "supplies", "glove")] == 0
    assert by_key[("train-0002", "identity", "family")] == 1
    assert by_key[("train-0002", "supplies", "glove")] == 1


def test_harvest_answer_batch_treats_empty_single_choice_as_unselected(tmp_path: Path) -> None:
    pytest.importorskip("PIL.Image")
    from training.harvest_corrections import harvest_answer_batch
    from training.mark_dataset import read_manifest

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _write_tiny_image(images_dir / "train-0001.png")
    template_path = tmp_path / "template_boxes.json"
    _write_tiny_template(template_path)
    answers_path = tmp_path / "answers.json"
    _write_answers(
        answers_path,
        [
            {
                "record_id": "train-0001",
                "identity": "",
                "services": {"supplies": []},
                "training": True,
                "source_image": "images/train-0001.png",
            }
        ],
    )

    harvest_answer_batch(answers_path, _tiny_layout(), template_path, tmp_path / "dataset")

    rows = read_manifest(tmp_path / "dataset" / "manifest.jsonl")
    assert {row["label"] for row in rows} == {0}


def test_harvest_answer_batch_rejects_record_without_source_image(tmp_path: Path) -> None:
    pytest.importorskip("PIL.Image")
    from training.harvest_corrections import harvest_answer_batch

    template_path = tmp_path / "template_boxes.json"
    _write_tiny_template(template_path)
    answers_path = tmp_path / "answers.json"
    _write_answers(answers_path, [{"record_id": "train-0001", "identity": "patient"}])

    with pytest.raises(ValueError, match="source_image"):
        harvest_answer_batch(answers_path, _tiny_layout(), template_path, tmp_path / "dataset")


def test_harvest_corrections_cli_exposes_answers_batch_mode() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "training.harvest_corrections", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert "--answers" in completed.stdout


def test_harvest_corrections_cli_requires_exactly_one_input_mode(tmp_path: Path) -> None:
    from training.harvest_corrections import main

    with pytest.raises(SystemExit):
        main(
            [
                "--template-boxes",
                str(tmp_path / "template_boxes.json"),
                "--dataset-dir",
                str(tmp_path / "dataset"),
            ]
        )
