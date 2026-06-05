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


def test_append_and_read_manifest_roundtrip_and_validates_rows(tmp_path: Path) -> None:
    from training.mark_dataset import append_row, read_manifest

    manifest = tmp_path / "nested" / "marks.jsonl"
    row = {
        "crop": "crops/rec-001-identity-patient.png",
        "label": 1,
        "field": "identity",
        "code": "patient",
        "source": "correction",
        "provider": "geometry",
        "record_id": "rec-001",
        "created_at": "2026-06-05T00:00:00Z",
    }

    append_row(manifest, row)

    assert read_manifest(manifest) == [row]
    with pytest.raises(ValueError, match="label"):
        append_row(manifest, {**row, "label": 2})
    with pytest.raises(ValueError, match="field"):
        append_row(manifest, {**row, "field": ""})
    with pytest.raises(ValueError, match="crop"):
        append_row(manifest, {**row, "crop": "../escape.png"})
    with pytest.raises(ValueError, match="crop"):
        append_row(manifest, {**row, "crop": "escape.png"})


def test_write_crop_image_writes_small_grayscale_png(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    from training.mark_dataset import write_crop_image

    output = write_crop_image([[0, 127], [200, 255]], tmp_path / "crops", "sample.png")

    assert output == tmp_path / "crops" / "sample.png"
    with Image.open(output) as image:
        assert image.mode == "L"
        assert image.size == (2, 2)
        pixel_iter = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        assert list(pixel_iter) == [0, 127, 200, 255]

    with pytest.raises(ValueError, match="filename"):
        write_crop_image([[0]], tmp_path / "crops", "../escape.png")


def test_harvest_record_corrections_writes_crops_and_manifest_rows(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    from training.harvest_corrections import harvest_record_corrections
    from training.mark_dataset import read_manifest
    image_path = tmp_path / "source.png"
    image = Image.new("L", (2, 2))
    image.putdata([10, 20, 30, 40])
    image.save(image_path)
    template_path = tmp_path / "template_boxes.json"
    _write_tiny_template(template_path)

    rows = harvest_record_corrections(
        {
            "record_id": "rec-001",
            "identity": "patient",
            "services": {"supplies": ["mask"]},
        },
        _tiny_layout(),
        image_path,
        template_path,
        tmp_path / "dataset",
        source="correction",
        provider="geometry",
        created_at="2026-06-05T01:02:03Z",
    )

    assert [(row["field"], row["code"], row["label"]) for row in rows] == [
        ("identity", "patient", 1),
        ("identity", "family", 0),
        ("supplies", "mask", 1),
        ("supplies", "glove", 0),
    ]
    for row in rows:
        assert row["source"] == "correction"
        assert row["provider"] == "geometry"
        assert row["record_id"] == "rec-001"
        assert row["created_at"] == "2026-06-05T01:02:03Z"
        crop_path = tmp_path / "dataset" / row["crop"]
        assert crop_path.is_file()

    assert read_manifest(tmp_path / "dataset" / "manifest.jsonl") == rows


def test_harvest_record_corrections_rejects_unknown_selected_or_template_codes(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    from training.harvest_corrections import harvest_record_corrections

    image_path = tmp_path / "source.png"
    image = Image.new("L", (2, 2))
    image.putdata([10, 20, 30, 40])
    image.save(image_path)
    template_path = tmp_path / "template_boxes.json"
    _write_tiny_template(template_path)

    with pytest.raises(ValueError, match="unknown selected code"):
        harvest_record_corrections(
            {
                "record_id": "rec-bad",
                "identity": "not-a-layout-code",
                "services": {"supplies": []},
            },
            _tiny_layout(),
            image_path,
            template_path,
            tmp_path / "dataset",
        )

    template_path.write_text(
        json.dumps(
            {
                "template_id": "tiny.v1",
                "boxes": [
                    {"field": "identity", "code": "not-a-layout-code", "box": [0.0, 0.0, 1.0, 1.0]},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="template box"):
        harvest_record_corrections(
            {"record_id": "rec-bad-template", "identity": "patient", "services": {"supplies": []}},
            _tiny_layout(),
            image_path,
            template_path,
            tmp_path / "dataset2",
        )


def test_harvest_record_corrections_rejects_mixed_invalid_template_without_partial_writes(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")
    from training.harvest_corrections import harvest_record_corrections

    image_path = tmp_path / "source.png"
    image = Image.new("L", (2, 2))
    image.putdata([10, 20, 30, 40])
    image.save(image_path)
    template_path = tmp_path / "template_boxes.json"
    template_path.write_text(
        json.dumps(
            {
                "template_id": "tiny.v1",
                "boxes": [
                    {"field": "identity", "code": "patient", "box": [0.0, 0.0, 1.0, 1.0]},
                    {"field": "identity", "code": "not-a-layout-code", "box": [1.0, 0.0, 2.0, 1.0]},
                ],
            }
        ),
        encoding="utf-8",
    )
    dataset_dir = tmp_path / "dataset"

    with pytest.raises(ValueError, match="template box"):
        harvest_record_corrections(
            {"record_id": "rec-mixed-template", "identity": "patient", "services": {"supplies": []}},
            _tiny_layout(),
            image_path,
            template_path,
            dataset_dir,
        )

    assert not (dataset_dir / "manifest.jsonl").exists()
    assert not (dataset_dir / "crops").exists()


def test_training_modules_do_not_import_paddleocr_or_plugin_main(tmp_path: Path) -> None:
    sys.modules.pop("paddleocr", None)
    sys.modules.pop("plugins.paddleocr.main", None)
    sys.modules.pop("training.harvest_corrections", None)
    sys.modules.pop("training.mark_dataset", None)

    import training.harvest_corrections  # noqa: F401
    import training.mark_dataset  # noqa: F401

    assert "paddleocr" not in sys.modules
    assert "plugins.paddleocr.main" not in sys.modules


def test_harvest_corrections_cli_help_is_available() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "training.harvest_corrections", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0
    assert "usage:" in completed.stdout
    assert "--template-boxes" in completed.stdout
