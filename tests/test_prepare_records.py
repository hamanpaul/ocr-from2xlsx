from __future__ import annotations

import json
from pathlib import Path

from ocr_from2xlsx.form_template import service_record_template
from ocr_from2xlsx.ocr_backend import FixtureOcrBackend
from ocr_from2xlsx.prepare_records import prepare_records_from_paths


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
