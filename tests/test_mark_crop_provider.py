from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ocr_from2xlsx.form_layout import service_record_layout
from training.layout_render import option_mark_box, render_sheet_template, sheet_geometry

_XLSX = Path(__file__).resolve().parents[1] / "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"
_SCRATCH = Path(__file__).resolve().parent / "_tmp_mark_crop_provider"


def _clean_scratch() -> None:
    if _SCRATCH.exists():
        shutil.rmtree(_SCRATCH)


class _TinyGrayImage:
    def __init__(self, pixels: list[list[int]]) -> None:
        self._pixels = pixels
        self.size = (len(pixels[0]) if pixels else 0, len(pixels))

    def convert(self, mode: str) -> "_TinyGrayImage":
        if mode != "L":
            raise ValueError(mode)
        return self

    def crop(self, box: tuple[int, int, int, int]) -> "_TinyGrayImage":
        x0, y0, x1, y1 = box
        return _TinyGrayImage([row[x0:x1] for row in self._pixels[y0:y1]])

    def getdata(self) -> list[int]:
        return [value for row in self._pixels for value in row]


@pytest.fixture(autouse=True)
def scratch_dir():
    _clean_scratch()
    _SCRATCH.mkdir()
    try:
        yield _SCRATCH
    finally:
        _clean_scratch()


def test_exported_boxes_cover_every_layout_option_and_match_known_box(scratch_dir: Path) -> None:
    pytest.importorskip("PIL")

    from training.export_template_boxes import export_template_boxes

    output_path = scratch_dir / "template_boxes.json"
    exported = export_template_boxes(_XLSX, output_path)
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    layout = service_record_layout()

    expected_keys = {(field.key, option.code) for field, option in layout.iter_options()}
    actual_keys = {(box["field"], box["code"]) for box in loaded["boxes"]}

    assert exported == loaded
    assert loaded["template_id"] == "service_record.v1"
    assert actual_keys == expected_keys
    assert all(isinstance(coord, float) for item in loaded["boxes"] for coord in item["box"])

    geom = sheet_geometry(_XLSX)
    rendered = render_sheet_template(geom)
    known = next(
        item
        for item in loaded["boxes"]
        if item["field"] == "identity" and item["code"] == "patient"
    )
    assert known["box"] == pytest.approx(
        option_mark_box(layout, geom, "identity", "patient", rendered=rendered)
    )


def test_geometry_crop_provider_crops_tiny_image_to_grayscale_regions(scratch_dir: Path) -> None:
    from plugins.paddleocr.crop_provider import GeometryCropProvider

    template_path = scratch_dir / "template_boxes.json"
    template_path.write_text(
        json.dumps(
            {
                "template_id": "tiny.v1",
                "boxes": [
                    {"field": "field_a", "code": "yes", "box": [1.0, 1.0, 3.0, 3.0]},
                    {"field": "field_b", "code": "no", "box": [0.0, 0.0, 2.0, 1.0]},
                ],
            }
        ),
        encoding="utf-8",
    )
    image = _TinyGrayImage([[y * 10 + x for x in range(4)] for y in range(4)])

    crops = GeometryCropProvider(template_path).crop(image)

    assert crops == {
        ("field_a", "yes"): [[11, 12], [21, 22]],
        ("field_b", "no"): [[0, 1]],
    }


def test_geometry_crop_provider_rejects_box_outside_image_bounds(scratch_dir: Path) -> None:
    from plugins.paddleocr.crop_provider import GeometryCropProvider

    template_path = scratch_dir / "template_boxes.json"
    template_path.write_text(
        json.dumps(
            {
                "template_id": "tiny.v1",
                "boxes": [
                    {"field": "field_a", "code": "yes", "box": [1.0, 1.0, 4.0, 4.0]},
                ],
            }
        ),
        encoding="utf-8",
    )
    image = _TinyGrayImage([[255, 255], [255, 255]])

    with pytest.raises(ValueError, match="outside image bounds"):
        GeometryCropProvider(template_path).crop(image)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"boxes": []}, "template_id"),
        ({"template_id": "tiny.v1"}, "boxes"),
        (
            {"template_id": "tiny.v1", "boxes": [{"field": "a", "code": "b", "box": [0, 1, 2]}]},
            "box",
        ),
        (
            {"template_id": "tiny.v1", "boxes": [{"field": "a", "code": "b", "box": [2, 0, 1, 1]}]},
            "increasing",
        ),
    ],
)
def test_geometry_crop_provider_rejects_invalid_template_json(
    scratch_dir: Path,
    payload: dict[str, object],
    message: str,
) -> None:
    from plugins.paddleocr.crop_provider import GeometryCropProvider

    template_path = scratch_dir / "template_boxes.json"
    template_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        GeometryCropProvider(template_path)


def test_crop_provider_module_imports_without_pillow_side_effects() -> None:
    import importlib

    module = importlib.import_module("plugins.paddleocr.crop_provider")

    assert hasattr(module, "CropProvider")
    assert hasattr(module, "GeometryCropProvider")
