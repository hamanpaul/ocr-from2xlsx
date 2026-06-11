from __future__ import annotations

import random
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from training.gen_names import read_label_file, render_corpus

_WINDOWS_CJK_FONT_NAMES = ("kaiu.ttf", "msjh.ttc", "mingliu.ttc")
_WINDOWS_LATIN_FONT_NAMES = ("arial.ttf", "calibri.ttf", "segoeui.ttf", "times.ttf")


def _available_windows_fonts(names: tuple[str, ...]) -> list[Path]:
    fonts_dir = Path(r"C:\Windows\Fonts")
    return [fonts_dir / name for name in names if (fonts_dir / name).is_file()]


def test_render_corpus_writes_images_and_three_disjoint_label_files(tmp_path: Path) -> None:
    try:
        summary = render_corpus(
            tmp_path,
            rng=random.Random(0),
            total=12,
            validation_fraction=0.25,
            holdout_fraction=0.25,
            augment=False,
        )
    except RuntimeError as e:
        if "no usable handwriting/CJK font" in str(e):
            pytest.skip("no usable handwriting/CJK font found; skipping render tests")
        raise

    train = read_label_file(tmp_path / "train.txt")
    validation = read_label_file(tmp_path / "validation.txt")
    holdout = read_label_file(tmp_path / "holdout.txt")

    assert summary == {"train": 6, "validation": 3, "holdout": 3}
    labels = [label for _, label in train + validation + holdout]
    assert len(set(labels)) == 12
    for image_rel, _ in train + validation + holdout:
        assert (tmp_path / image_rel).is_file()


def test_render_corpus_uses_cjk_fallback_for_latin_handwriting_fonts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from PIL import Image
    from training import generate
    from training import gen_names

    cjk_fonts = _available_windows_fonts(_WINDOWS_CJK_FONT_NAMES)
    latin_fonts = _available_windows_fonts(_WINDOWS_LATIN_FONT_NAMES)
    if not cjk_fonts or not latin_fonts:
        pytest.skip("requires at least one Windows CJK font and one Latin font")

    latin_font = latin_fonts[0]
    if generate._font_supports_cjk_text(latin_font, "王小明"):
        pytest.skip("requires a Latin font that cannot render Chinese text")

    cjk_font = cjk_fonts[0]
    monkeypatch.setattr(gen_names, "_handwriting_font_paths", lambda: [latin_font])
    monkeypatch.setattr(generate, "_system_font_candidates", lambda: iter((cjk_font,)))

    seen_font_paths: list[Path] = []

    def _capture_render(name: str, font_path: Path, rng: random.Random, *, augment: bool):
        seen_font_paths.append(Path(font_path))
        return Image.new("L", gen_names.CANVAS_SIZE, color=255)

    monkeypatch.setattr(gen_names, "_render_name", _capture_render)

    summary = render_corpus(
        tmp_path,
        rng=random.Random(2),
        total=1,
        validation_fraction=0.0,
        holdout_fraction=0.0,
        augment=False,
    )

    assert summary == {"train": 1, "validation": 0, "holdout": 0}
    assert seen_font_paths == [cjk_font]


def test_render_corpus_image_is_grayscale_with_ink(tmp_path: Path) -> None:
    from PIL import Image

    try:
        render_corpus(tmp_path, rng=random.Random(1), total=2, validation_fraction=0.0, holdout_fraction=0.5, augment=False)
    except RuntimeError as e:
        if "no usable handwriting/CJK font" in str(e):
            pytest.skip("no usable handwriting/CJK font found; skipping render tests")
        raise
    image_rel, _ = read_label_file(tmp_path / "train.txt")[0]
    with Image.open(tmp_path / image_rel) as image:
        assert image.mode == "L"
        assert image.height >= 32 and image.width >= image.height
        pixel_iter = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        assert min(pixel_iter) < 128  # some ink present
