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
from training.layout_render import draw_base_form, option_mark_box, sheet_geometry, text_entry_box

_XLSX = Path(__file__).resolve().parents[1] / "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"
_WINDOWS_CJK_FONT_NAMES = ("kaiu.ttf", "msjh.ttc", "mingliu.ttc")


def _available_windows_cjk_fonts() -> list[Path]:
    fonts_dir = Path(r"C:\Windows\Fonts")
    return [fonts_dir / name for name in _WINDOWS_CJK_FONT_NAMES if (fonts_dir / name).is_file()]


def _first_selected_option(batch_path: Path) -> tuple[str, str]:
    layout = service_record_layout()
    batch = load_batch(batch_path)
    record = batch.records[0]
    state = record_to_form_state(layout, record)

    for field in layout.iter_fields():
        value = state[field.key]
        if field.kind == "single_choice" and value:
            return field.key, value
        if field.kind == "multi_choice" and value:
            return field.key, sorted(value)[0]
    raise AssertionError("expected at least one selected option in generated record")


def _ink_delta_in_box(image_path: Path, box: tuple[float, float, float, float]) -> int:
    layout = service_record_layout()
    geom = sheet_geometry(_XLSX)

    base = draw_base_form(layout, geom)
    generated = Image.open(image_path).convert("L")

    x0, y0, x1, y1 = box
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


def test_select_text_font_skips_latin_font_when_cjk_system_font_can_render_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from training import generate

    latin_font = Path(r"C:\Windows\Fonts\arial.ttf")
    cjk_fonts = _available_windows_cjk_fonts()
    if not latin_font.is_file() or not cjk_fonts:
        pytest.skip("requires arial.ttf and at least one Windows CJK font")

    cjk_font = cjk_fonts[0]
    monkeypatch.setattr(generate, "_system_font_candidates", lambda: iter((latin_font, cjk_font)))

    selected = Path(generate._select_text_font("王小明", [cjk_font]))

    assert selected == cjk_font


def test_font_supports_cjk_text_requires_unique_glyphs(monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import ImageFont
    from training import generate

    class _FakeMask:
        def __init__(self, token: bytes) -> None:
            self.size = (1, 1)
            self._token = token

        def __bytes__(self) -> bytes:
            return self._token

    class _FakeFont:
        _tokens = {"王": b"a", "小": b"b", "明": b"a"}

        def getmask(self, char: str) -> _FakeMask:
            return _FakeMask(self._tokens[char])

    monkeypatch.setattr(ImageFont, "truetype", lambda *args, **kwargs: _FakeFont())

    assert not generate._font_supports_cjk_text(Path("fake.ttf"), "王小明")


def test_select_text_font_prefers_local_handwriting_font_for_cjk_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from training import generate

    cjk_fonts = _available_windows_cjk_fonts()
    if len(cjk_fonts) < 2:
        pytest.skip("requires at least two Windows CJK fonts")

    handwriting_font = cjk_fonts[0]
    system_font = cjk_fonts[1]
    monkeypatch.setattr(generate, "_system_font_candidates", lambda: iter((system_font,)))

    selected = Path(generate._select_text_font("王小明", [handwriting_font]))

    assert selected == handwriting_font


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
    assert first["diagnosis_date"]

    image_path = tmp_path / first["source_image"]
    assert image_path.is_file()

    selected_field, selected_code = _first_selected_option(answers_path)
    assert _ink_delta_in_box(
        image_path,
        option_mark_box(service_record_layout(), sheet_geometry(_XLSX), selected_field, selected_code),
    ) > 0

    for field_key in ("service_date", "medical_record_no", "name", "diagnosis_date"):
        assert _ink_delta_in_box(
            image_path,
            text_entry_box(service_record_layout(), sheet_geometry(_XLSX), field_key),
        ) > 0, field_key
