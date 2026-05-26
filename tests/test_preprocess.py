from pathlib import Path

from ocr_from2xlsx.capture import PdfDocumentSource
from ocr_from2xlsx.form_template import service_record_template
from ocr_from2xlsx.preprocess import prepare_pdf_page


def test_prepare_pdf_page_renders_png_and_assigns_template(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(fixture_path).pages()[0]

    prepared = prepare_pdf_page(page, output_dir=tmp_path, template=service_record_template())

    assert prepared.template_id == "service_record.v1"
    assert prepared.source.document_path == "tests/fixtures/pdf/for testing only.pdf"
    assert prepared.source.page_number == 1
    assert prepared.source.preprocessed_image_path == "for testing only-page-0001.png"
    assert prepared.image_path.exists()
    assert prepared.image_path.suffix.lower() == ".png"
