from __future__ import annotations

import json
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")

from ocr_from2xlsx.constants import SCHEMA_VERSION
from ocr_from2xlsx.form_layout import Field, FormLayout, Option, Section
from training.eval_marks import evaluate_answer_key, resolve_source_image
from training.layout_render import CellStyle, SheetGeometry, option_mark_box, render_sheet_template


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
                        options=(Option(label="病人", code="patient", cell="A1"),),
                    ),
                    Field(
                        key="services",
                        title="Services",
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


def _tiny_geom() -> SheetGeometry:
    return SheetGeometry(
        col_x=(0.0, 140.0),
        row_y=(0.0, 24.0, 48.0, 72.0),
        width=140,
        height=72,
        cell_text={"A1": "□病人", "A2": "□口罩", "A3": "□手套"},
        cell_style={
            "A1": CellStyle("Arial", 16.0, False, False, "left", "top"),
            "A2": CellStyle("Arial", 16.0, False, False, "left", "top"),
            "A3": CellStyle("Arial", 16.0, False, False, "left", "top"),
        },
        span_ref_by_cell={"A1": "A1", "A2": "A2", "A3": "A3"},
        span_anchor_by_ref={"A1": "A1", "A2": "A2", "A3": "A3"},
    )


def test_resolve_source_image_uses_answer_key_directory_for_relative_paths(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    source = tmp_path / "images" / "sample.png"
    source.parent.mkdir()
    source.write_bytes(b"not-an-image")

    assert resolve_source_image(answers_path, "images/sample.png") == source


def test_evaluate_answer_key_emits_mark_report_without_ocr(tmp_path: Path) -> None:
    layout = _tiny_layout()
    geom = _tiny_geom()
    rendered = render_sheet_template(geom)
    image = Image.new("L", (geom.width, geom.height), 255)
    draw = ImageDraw.Draw(image)
    for field_key, code in (("identity", "patient"), ("services", "mask")):
        box = option_mark_box(layout, geom, field_key, code, rendered=rendered)
        draw.rectangle(tuple(map(int, box)), fill=0)

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "sample.png"
    image.save(image_path)

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
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
                        "record_id": "sample-001",
                        "identity": "patient",
                        "gender": "",
                        "name": "",
                        "medical_record_no": "",
                        "service_date": "",
                        "services": {"supplies": ["mask", "glove"]},
                        "source_image": "images/sample.png",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = evaluate_answer_key(
        answers_path,
        layout=layout,
        geom=geom,
        output_dir=tmp_path / "eval",
    )

    assert report["kind"] == "mark-blinded"
    assert report["sample_count"] == 1
    assert report["marks"]["aggregate"]["tp"] == 2
    assert report["marks"]["aggregate"]["fn"] == 1
    assert report["marks"]["per_field"]["services"]["recall"] == 0.5
    assert report["samples"][0]["record_id"] == "sample-001"
    assert report["samples"][0]["predicted_marks"] == [["identity", "patient"], ["services", "mask"]]
    assert (tmp_path / "eval" / "report.json").is_file()
    assert (tmp_path / "eval" / "report.md").read_text(encoding="utf-8").startswith("# Synthetic mark evaluation")


def test_evaluate_answer_key_does_not_count_printed_blank_checkbox_as_mark(tmp_path: Path) -> None:
    layout = _tiny_layout()
    geom = _tiny_geom()
    rendered = render_sheet_template(geom)
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "sample.png"
    rendered.image.save(image_path)

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
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
                        "record_id": "sample-blank",
                        "identity": "",
                        "gender": "",
                        "name": "",
                        "medical_record_no": "",
                        "service_date": "",
                        "services": {"supplies": []},
                        "source_image": "images/sample.png",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = evaluate_answer_key(
        answers_path,
        layout=layout,
        geom=geom,
        output_dir=tmp_path / "eval",
    )

    assert report["marks"]["aggregate"]["fp"] == 0
    assert report["samples"][0]["predicted_marks"] == []
