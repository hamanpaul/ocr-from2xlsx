from PIL import Image

from ocr_from2xlsx.recognition.layout import Section
from ocr_from2xlsx.recognition.tiling import crop_sections


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
