from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("PIL")

from PIL import Image

from ocr_from2xlsx.confirm_form import record_to_form_state
from ocr_from2xlsx.form_layout import service_record_layout
from ocr_from2xlsx.json_io import load_batch
from training.layout_render import cell_box, draw_base_form, sheet_geometry

_XLSX = Path(__file__).resolve().parents[1] / "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"


def _first_selected_cell(batch_path: Path) -> str:
    layout = service_record_layout()
    batch = load_batch(batch_path)
    record = batch.records[0]
    state = record_to_form_state(layout, record)

    for field in layout.iter_fields():
        value = state[field.key]
        if field.kind == "single_choice" and value:
            return layout.options_by_code(field.key)[value].cell
        if field.kind == "multi_choice" and value:
            code = sorted(value)[0]
            return layout.options_by_code(field.key)[code].cell
    raise AssertionError("expected at least one selected option in generated record")


def _ink_delta_in_cell(image_path: Path, cell: str) -> int:
    layout = service_record_layout()
    geom = sheet_geometry(_XLSX)
    from training.generate import _select_text_font

    base = draw_base_form(layout, geom, font_path=_select_text_font())
    generated = Image.open(image_path).convert("L")

    x0, y0, x1, y1 = cell_box(cell, geom)
    left, top, right, bottom = map(int, (x0, y0, x1, y1))
    base_crop = base.crop((left, top, right, bottom))
    generated_crop = generated.crop((left, top, right, bottom))
    base_pixels = base_crop.load()
    generated_pixels = generated_crop.load()
    return sum(
        1
        for y in range(base_crop.height)
        for x in range(base_crop.width)
        if generated_pixels[x, y] < base_pixels[x, y]
    )


def test_generate_tiny_batch(tmp_path: Path) -> None:
    from training.generate import generate

    result = generate(str(_XLSX), str(tmp_path), min_per_option=1, seed=3)

    assert result["images"] >= 1
    answers_path = tmp_path / "answers.json"
    assert answers_path.is_file()

    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    assert answers["schema_version"] == "service_record.v1"
    assert answers["records"]

    first = answers["records"][0]
    assert first["training"] is True
    assert first["source_image"].startswith("images/")

    image_path = tmp_path / first["source_image"]
    assert image_path.is_file()

    selected_cell = _first_selected_cell(answers_path)
    assert _ink_delta_in_cell(image_path, selected_cell) > 0
