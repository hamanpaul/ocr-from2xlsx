from PIL import Image

from ocr_from2xlsx.recognition.layout import Section
from ocr_from2xlsx.recognition.tiling import crop_sections, enhance_crop, resolve_preprocess_mode


def _image(tmp_path, size=(100, 200)):
    path = tmp_path / "frame.png"
    Image.new("RGB", size, "white").save(path)
    return str(path)


def test_crop_sections_writes_band_sized_crops(tmp_path):
    layout = (
        Section("top", (0.0, 0.0, 1.0, 0.5)),
        Section("bottom", (0.0, 0.5, 1.0, 1.0)),
    )
    crops = crop_sections(_image(tmp_path), layout, out_dir=tmp_path)
    assert set(crops) == {"top", "bottom"}
    with Image.open(crops["top"]) as top:
        assert top.size == (100, 100)
    with Image.open(crops["bottom"]) as bottom:
        assert bottom.size == (100, 100)


def test_crop_sections_rotate_changes_dimensions(tmp_path):
    layout = (Section("full", (0.0, 0.0, 1.0, 1.0)),)
    crops = crop_sections(_image(tmp_path), layout, out_dir=tmp_path, rotate=90)
    # a 100x200 image rotated a quarter turn is 200x100
    with Image.open(crops["full"]) as full:
        assert full.size == (200, 100)


# --- #60 per-crop preprocessing modes ----------------------------------------------------

def test_resolve_preprocess_mode_default_and_env(monkeypatch):
    monkeypatch.delenv("OCR_VLM_PREPROCESS", raising=False)
    assert resolve_preprocess_mode() == "autocontrast"  # default = prior behaviour
    monkeypatch.setenv("OCR_VLM_PREPROCESS", "BINARIZE")
    assert resolve_preprocess_mode() == "binarize"  # case-insensitive
    monkeypatch.setenv("OCR_VLM_PREPROCESS", "bogus")
    assert resolve_preprocess_mode() == "autocontrast"  # invalid -> default
    assert resolve_preprocess_mode("clahe") == "clahe"  # explicit wins


def test_enhance_crop_modes_produce_valid_images():
    import numpy as np

    crop = Image.fromarray(np.random.default_rng(0).integers(0, 255, (40, 60, 3), dtype="uint8"))
    for mode in ("raw", "none", "autocontrast", "clahe", "binarize"):
        out = enhance_crop(crop, mode)
        assert out.size == (60, 40)
    # binarize yields a 2-value image; raw keeps 3 channels.
    assert enhance_crop(crop, "raw").mode == "RGB"
    binar = np.asarray(enhance_crop(crop, "binarize"))
    assert set(np.unique(binar)).issubset({0, 255})


def test_crop_sections_binarize_mode(tmp_path):
    layout = (Section("full", (0.0, 0.0, 1.0, 1.0)),)
    crops = crop_sections(_image(tmp_path), layout, out_dir=tmp_path, preprocess_mode="binarize")
    with Image.open(crops["full"]) as full:
        assert full.size == (100, 200)
