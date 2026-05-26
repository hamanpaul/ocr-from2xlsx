from __future__ import annotations

import json
from pathlib import Path

from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.form_template import service_record_template
from ocr_from2xlsx.ocr_backend import FixtureOcrBackend
from ocr_from2xlsx.preprocess import PreparedPage
from ocr_from2xlsx.prepare_records import prepare_records_from_paths


def test_fixture_ocr_backend_extract_isolates_nested_state() -> None:
    backend = FixtureOcrBackend(
        pages={
            (
                "fixture.pdf",
                1,
            ): {
                "record_id": "pdf-0001",
                "service_date": "2026-05-26",
                "identity": "patient",
                "name": "AI test",
                "medical_record_no": "TRAINING-ONLY",
                "gender": "female",
                "source": {"kind": "fixture", "document_path": "fixture.pdf", "page_number": 1},
                "review": {"status": "pending", "edited_by_user": False},
            }
        }
    )
    page = PreparedPage(
        image_path=Path("fixture.png"),
        source=SourceInfo(document_path="fixture.pdf", page_number=1),
        template_id="template",
    )

    first = backend.extract(page)
    first["source"]["kind"] = "mutated"
    first["review"]["status"] = "approved"

    second = backend.extract(page)

    assert second["source"]["kind"] == "fixture"
    assert second["review"]["status"] == "pending"


def test_prepare_records_from_pdf_matches_gold_fixture(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    pdf_path = fixture_dir / "for testing only.pdf"
    ocr_path = fixture_dir / "for testing only.ocr.json"
    expected_path = fixture_dir / "for testing only.expected.json"

    batch = prepare_records_from_paths(
        input_paths=[pdf_path],
        output_dir=tmp_path,
        template=service_record_template(),
        backend=FixtureOcrBackend.from_path(ocr_path),
        created_at="2026-05-26T00:00:00+08:00",
    )

    assert batch.to_dict() == json.loads(expected_path.read_text(encoding="utf-8"))
