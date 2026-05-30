from pathlib import Path
import shutil

import pytest
import fitz

from ocr_from2xlsx.capture import PdfDocumentSource
from ocr_from2xlsx.form_template import FormTemplate, service_record_template
from ocr_from2xlsx.preprocess import prepare_pdf_page


def test_prepare_pdf_page_renders_png_and_assigns_template(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(fixture_path).pages()[0]

    prepared = prepare_pdf_page(page, output_dir=tmp_path, template=service_record_template())
    pixmap = fitz.Pixmap(str(prepared.image_path))

    assert prepared.template_id == "service_record.v1"
    assert prepared.source.document_path == "tests/fixtures/pdf/for testing only.pdf"
    assert prepared.source.page_number == 1
    assert prepared.source.preprocessed_image_path == "for testing only-page-0001.png"
    assert prepared.image_path.exists()
    assert prepared.image_path.suffix.lower() == ".png"
    assert 3200 <= pixmap.width <= 3400
    assert 4600 <= pixmap.height <= 4750


def test_prepare_pdf_page_uses_repo_relative_document_path_outside_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(fixture_path).pages()[0]

    monkeypatch.chdir(tmp_path)

    prepared = prepare_pdf_page(page, output_dir=tmp_path / "prepared", template=service_record_template())

    assert prepared.source.document_path == "tests/fixtures/pdf/for testing only.pdf"


def test_prepare_pdf_page_allocates_unique_image_path_for_collisions(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    source_one = tmp_path / "one" / fixture_path.name
    source_two = tmp_path / "two" / fixture_path.name
    source_one.parent.mkdir(parents=True)
    source_two.parent.mkdir(parents=True)
    shutil.copyfile(fixture_path, source_one)
    shutil.copyfile(fixture_path, source_two)

    output_dir = tmp_path / "prepared"
    first_page = PdfDocumentSource(source_one).pages()[0]
    second_page = PdfDocumentSource(source_two).pages()[0]

    first_prepared = prepare_pdf_page(first_page, output_dir=output_dir, template=service_record_template())
    second_prepared = prepare_pdf_page(second_page, output_dir=output_dir, template=service_record_template())

    assert first_prepared.image_path.name == "for testing only-page-0001.png"
    assert second_prepared.image_path != first_prepared.image_path
    assert first_prepared.image_path.exists()
    assert second_prepared.image_path.exists()
    assert second_prepared.source.preprocessed_image_path != first_prepared.source.preprocessed_image_path


def test_prepare_pdf_page_rejects_mismatched_template_size(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(fixture_path).pages()[0]
    template = FormTemplate(template_id="service_record.v1", page_size_points=(620.0, 800.0), zones={})
    output_dir = tmp_path / "prepared"

    with pytest.raises(ValueError, match="template"):
        prepare_pdf_page(page, output_dir=output_dir, template=template)

    assert not output_dir.exists()
