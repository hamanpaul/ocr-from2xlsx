from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_PADDLE_OCR") != "1",
    reason="real PaddleOCR bundle test; set RUN_PADDLE_OCR=1 and build dist/plugins/paddleocr",
)


def test_reference_form_matches_ground_truth(tmp_path: Path) -> None:
    sys.path.insert(0, "src")
    from ocr_from2xlsx.capture import PdfDocumentSource
    from ocr_from2xlsx.plugin_backend import PluginOcrBackend
    from ocr_from2xlsx.form_template import service_record_template
    from ocr_from2xlsx.preprocess import prepare_pdf_page

    repo = Path(__file__).resolve().parents[1]
    pdf = repo / "tests" / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(pdf).pages()[0]
    prepared = prepare_pdf_page(page, output_dir=tmp_path / "prepared", template=service_record_template())
    rec = PluginOcrBackend(str(repo / "dist" / "plugins" / "paddleocr")).extract(prepared)
    gold = json.loads((repo / "tests" / "fixtures" / "pdf" / "for testing only.groundtruth.json").read_text(encoding="utf-8"))
    for key, expected in gold.items():
        assert rec.get(key) == expected, f"{key}: got {rec.get(key)!r}, want {expected!r}"
