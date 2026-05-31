from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

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


def test_prepare_records_from_paths_emits_one_record_per_pdf_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "two-page.pdf"
    ocr_path = tmp_path / "two-page.ocr.json"

    document = fitz.open()
    document.new_page(width=595.44, height=841.68)
    document.new_page(width=595.44, height=841.68)
    document.save(pdf_path)
    document.close()

    ocr_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "document_name": pdf_path.name,
                        "page_number": 1,
                        "record": {
                            "record_id": "pdf-0001",
                            "service_date": "2026-05-26",
                            "identity": "patient",
                            "name": "AI test 1",
                            "medical_record_no": "TRAINING-ONLY",
                            "gender": "female",
                            "ocr": {"raw_text": "page 1"},
                        },
                    },
                    {
                        "document_name": pdf_path.name,
                        "page_number": 2,
                        "record": {
                            "record_id": "pdf-0002",
                            "service_date": "2026-05-27",
                            "identity": "patient",
                            "name": "AI test 2",
                            "medical_record_no": "TRAINING-ONLY",
                            "gender": "female",
                            "ocr": {"raw_text": "page 2"},
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    batch = prepare_records_from_paths(
        input_paths=[pdf_path],
        output_dir=tmp_path,
        template=service_record_template(),
        backend=FixtureOcrBackend.from_path(ocr_path),
        created_at="2026-05-26T00:00:00+08:00",
    )

    assert [record.record_id for record in batch.records] == ["pdf-0001", "pdf-0002"]
    assert [record.source.page_number for record in batch.records] == [1, 2]
    assert [record.source.preprocessed_image_path for record in batch.records] == [
        "two-page-page-0001.png",
        "two-page-page-0002.png",
    ]


def test_prepare_records_assigns_record_id_when_backend_omits_it(tmp_path: Path) -> None:
    pdf_path = tmp_path / "no-id.pdf"
    document = fitz.open()
    document.new_page(width=595.44, height=841.68)
    document.new_page(width=595.44, height=841.68)
    document.save(pdf_path)
    document.close()

    class _NoIdBackend:
        def extract(self, page: PreparedPage) -> dict:
            return {
                "service_date": "2026-05-26",
                "identity": "patient",
                "name": "X",
                "medical_record_no": "Y",
                "gender": "female",
                "ocr": {"raw_text": "x"},
            }

    batch = prepare_records_from_paths(
        input_paths=[pdf_path],
        output_dir=tmp_path,
        template=service_record_template(),
        backend=_NoIdBackend(),
        created_at="2026-05-26T00:00:00+08:00",
    )

    assert [record.record_id for record in batch.records] == ["pdf-0001", "pdf-0002"]


def test_prepare_records_preserves_backend_supplied_record_id(tmp_path: Path) -> None:
    pdf_path = tmp_path / "has-id.pdf"
    document = fitz.open()
    document.new_page(width=595.44, height=841.68)
    document.save(pdf_path)
    document.close()

    class _WithIdBackend:
        def extract(self, page: PreparedPage) -> dict:
            return {
                "record_id": "gold-9",
                "service_date": "2026-05-26",
                "identity": "patient",
                "name": "X",
                "medical_record_no": "Y",
                "gender": "female",
            }

    batch = prepare_records_from_paths(
        input_paths=[pdf_path],
        output_dir=tmp_path,
        template=service_record_template(),
        backend=_WithIdBackend(),
        created_at="2026-05-26T00:00:00+08:00",
    )

    assert [record.record_id for record in batch.records] == ["gold-9"]


def test_prepare_records_marks_backend_supplied_name_as_unconfirmed(tmp_path: Path) -> None:
    pdf_path = tmp_path / "has-name.pdf"
    document = fitz.open()
    document.new_page(width=595.44, height=841.68)
    document.save(pdf_path)
    document.close()

    class _WithNameBackend:
        def extract(self, page: PreparedPage) -> dict:
            return {
                "record_id": "gold-9",
                "service_date": "2026-05-26",
                "identity": "patient",
                "name": "AI test",
                "medical_record_no": "Y",
                "gender": "female",
                "ocr": {
                    "raw_text": "AI test",
                    "warnings": ["existing-warning"],
                },
            }

    batch = prepare_records_from_paths(
        input_paths=[pdf_path],
        output_dir=tmp_path,
        template=service_record_template(),
        backend=_WithNameBackend(),
        created_at="2026-05-26T00:00:00+08:00",
    )

    assert batch.records[0].name == "AI test"
    assert batch.records[0].ocr.warnings == ["existing-warning", "name.unconfirmed"]


def test_prepare_records_from_paths_rejects_non_object_source_metadata(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "single-page.pdf"
    ocr_path = tmp_path / "single-page.ocr.json"

    document = fitz.open()
    document.new_page(width=595.44, height=841.68)
    document.save(pdf_path)
    document.close()

    ocr_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "document_name": pdf_path.name,
                        "page_number": 1,
                        "record": {
                            "record_id": "pdf-0001",
                            "service_date": "2026-05-26",
                            "identity": "patient",
                            "name": "AI test",
                            "medical_record_no": "TRAINING-ONLY",
                            "gender": "female",
                            "source": "broken",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source"):
        prepare_records_from_paths(
            input_paths=[pdf_path],
            output_dir=tmp_path,
            template=service_record_template(),
            backend=FixtureOcrBackend.from_path(ocr_path),
            created_at="2026-05-26T00:00:00+08:00",
        )


def test_prepare_records_from_paths_rejects_null_source_metadata(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "single-page.pdf"
    ocr_path = tmp_path / "single-page.ocr.json"

    document = fitz.open()
    document.new_page(width=595.44, height=841.68)
    document.save(pdf_path)
    document.close()

    ocr_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "document_name": pdf_path.name,
                        "page_number": 1,
                        "record": {
                            "record_id": "pdf-0001",
                            "service_date": "2026-05-26",
                            "identity": "patient",
                            "name": "AI test",
                            "medical_record_no": "TRAINING-ONLY",
                            "gender": "female",
                            "source": None,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source"):
        prepare_records_from_paths(
            input_paths=[pdf_path],
            output_dir=tmp_path,
            template=service_record_template(),
            backend=FixtureOcrBackend.from_path(ocr_path),
            created_at="2026-05-26T00:00:00+08:00",
        )
