from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from ocr_from2xlsx.capture import (
    ImageFolderSource,
    JsonRecordSource,
    PdfDocumentSource,
    UvcCameraSource,
)
from ocr_from2xlsx.json_io import dump_batch
from ocr_from2xlsx.sample_data import generate_sample_batch


def _iterdir_in_order(path: Path, ordered: list[Path]):
    original_iterdir = Path.iterdir

    def fake_iterdir(self: Path):
        if self == path:
            return iter(ordered)
        return original_iterdir(self)

    return fake_iterdir


def test_json_record_source_yields_records(tmp_path: Path) -> None:
    batch = generate_sample_batch(count=2)
    path = tmp_path / "records.json"

    dump_batch(batch, path)

    source = JsonRecordSource(path)
    names = [record.name for record in source.records()]

    assert names == [record.name for record in batch.records]


def test_image_folder_source_sorts_and_filters(tmp_path: Path) -> None:
    for name in ["b.JPG", "a.png", "c.txt", "D.JPEG", "e.BMP"]:
        (tmp_path / name).write_text("x", encoding="utf-8")

    source = ImageFolderSource(tmp_path)

    assert [path.name for path in source.image_paths()] == ["a.png", "b.JPG", "D.JPEG", "e.BMP"]


def test_image_folder_source_sorts_case_collisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lower = tmp_path / "a.png"
    upper = tmp_path / "A.png"
    for path in [lower, upper]:
        path.write_text("x", encoding="utf-8")

    source = ImageFolderSource(tmp_path)
    monkeypatch.setattr(Path, "iterdir", _iterdir_in_order(tmp_path, [lower, upper]))

    assert [path.name for path in source.image_paths()] == ["A.png", "a.png"]


def test_pdf_document_source_reads_fixture_page_metadata() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"

    source = PdfDocumentSource(fixture_path)
    pages = source.pages()

    assert len(pages) == 1
    assert pages[0].document_path == fixture_path
    assert pages[0].page_number == 1
    assert pages[0].width_points == pytest.approx(595.44, abs=0.5)
    assert pages[0].height_points == pytest.approx(841.68, abs=0.5)


def test_uvc_camera_source_returns_false_without_cv2() -> None:
    if importlib.util.find_spec("cv2") is not None:
        pytest.skip("cv2 available")

    source = UvcCameraSource()

    assert source.is_available() is False
