from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest
from openpyxl import load_workbook

from ocr_from2xlsx.cli import build_parser, main
from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.json_io import dump_batch
from ocr_from2xlsx.session import ImportSession
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


def test_import_json_cli_writes_workbook(tmp_path: Path, capsys) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    input_json = tmp_path / "records.json"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)
    dump_batch(
        Batch(
            source_batch=SourceBatch(
                created_at="2026-05-24T15:30:00+08:00",
                source_type="json_import",
                template_name="template.xlsx",
            ),
            records=[make_record()],
        ),
        input_json,
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(input_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == f"{working}\n"
    assert working.exists()
    wb = load_workbook(working)
    ws = wb["個案總表"]
    assert ws["E2"].value == "王小明"
    wb.close()
    assert report_json.exists()
    assert report_csv.exists()
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert len(report) == 1
    assert report[0]["status"] == "written"


def test_import_json_cli_reports_blocked_records(tmp_path: Path, capsys) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    input_json = tmp_path / "records.json"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)
    blocked_record = make_record()
    blocked_record.service_date = ""
    dump_batch(
        Batch(
            source_batch=SourceBatch(
                created_at="2026-05-24T15:30:00+08:00",
                source_type="json_import",
                template_name="template.xlsx",
            ),
            records=[blocked_record],
        ),
        input_json,
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(input_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == f"{working}\n"
    assert working.exists()
    assert report_json.exists()
    assert report_csv.exists()
    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report[0]["status"] == "blocked"


def test_import_json_cli_reports_input_error_without_traceback(
    tmp_path: Path, capsys
) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    missing_input = tmp_path / "missing.json"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)

    exit_code = main(
        [
            "import-json",
            "--input",
            str(missing_input),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_import_json_cli_warns_when_report_write_fails(
    tmp_path: Path, capsys
) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    input_json = tmp_path / "records.json"
    report_json = tmp_path / "report-as-directory"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)
    report_json.mkdir()
    dump_batch(
        Batch(
            source_batch=SourceBatch(
                created_at="2026-05-24T15:30:00+08:00",
                source_type="json_import",
                template_name="template.xlsx",
            ),
            records=[make_record()],
        ),
        input_json,
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(input_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert working.exists()
    assert "working XLSX may contain imported records" in captured.err
    assert "Traceback" not in captured.err


def test_import_json_cli_omits_import_warning_when_empty_report_write_fails(
    tmp_path: Path, capsys
) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    input_json = tmp_path / "records.json"
    report_json = tmp_path / "report-as-directory"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)
    report_json.mkdir()
    dump_batch(
        Batch(
            source_batch=SourceBatch(
                created_at="2026-05-24T15:30:00+08:00",
                source_type="json_import",
                template_name="template.xlsx",
            ),
            records=[],
        ),
        input_json,
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(input_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "report writing did not complete" in captured.err
    assert "working XLSX may contain imported records" not in captured.err
    assert "Traceback" not in captured.err


def test_import_json_cli_omits_import_warning_when_blocked_report_write_fails(
    tmp_path: Path, capsys
) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    input_json = tmp_path / "records.json"
    report_json = tmp_path / "report-as-directory"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)
    report_json.mkdir()
    blocked_record = make_record()
    blocked_record.service_date = ""
    dump_batch(
        Batch(
            source_batch=SourceBatch(
                created_at="2026-05-24T15:30:00+08:00",
                source_type="json_import",
                template_name="template.xlsx",
            ),
            records=[blocked_record],
        ),
        input_json,
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(input_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "report writing did not complete" in captured.err
    assert "working XLSX may contain imported records" not in captured.err
    assert "Traceback" not in captured.err


def test_import_json_cli_warns_when_accept_fails_before_returning_result(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    input_json = tmp_path / "records.json"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)
    dump_batch(
        Batch(
            source_batch=SourceBatch(
                created_at="2026-05-24T15:30:00+08:00",
                source_type="json_import",
                template_name="template.xlsx",
            ),
            records=[make_record()],
        ),
        input_json,
    )

    class SaveFailingSession:
        closed = False

        def __enter__(self) -> "SaveFailingSession":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            self.closed = True

        def accept_scan(self, record: object) -> None:
            raise OSError("save failed")

        def write_report(self, json_path: object, csv_path: object) -> None:
            raise AssertionError("report should not be written")

    failing_session = SaveFailingSession()
    monkeypatch.setattr(
        ImportSession,
        "start",
        staticmethod(lambda template_path, working_path: failing_session),
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(input_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "save failed" in captured.err
    assert "working XLSX may contain imported records" in captured.err
    assert "Traceback" not in captured.err
    assert failing_session.closed


def test_import_json_cli_warns_when_accept_fails_after_write(
    tmp_path: Path, capsys
) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    input_json = tmp_path / "records.json"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template)
    first_record = make_record("scan-0001")
    failing_record = make_record("scan-0002")
    failing_record.name = "王大明"
    failing_record.medical_record_no = "B234567"
    failing_record.services.consultation["health_medical"] = [
        "screening_prevention",
        "disease_treatment_knowledge",
    ]
    dump_batch(
        Batch(
            source_batch=SourceBatch(
                created_at="2026-05-24T15:30:00+08:00",
                source_type="json_import",
                template_name="template.xlsx",
            ),
            records=[first_record, failing_record],
        ),
        input_json,
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(input_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert working.exists()
    assert "working XLSX may contain imported records" in captured.err
    assert "Traceback" not in captured.err


def test_prepare_records_cli_writes_batch_json_from_pdf_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(fixture_dir / "for testing only.ocr.json"),
        ]
    )

    assert exit_code == 0
    assert output_json.exists()
    captured = capsys.readouterr()
    assert captured.out == f"{output_json}\n"


def test_prepare_records_help_mentions_pdf_inputs_only(capsys) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["prepare-records", "--help"])

    captured = capsys.readouterr()
    help_text = captured.out
    assert "Input PDF path." in help_text
    assert "Input PDF or image path." not in help_text


def test_root_help_mentions_pdf_prep_workflow(capsys) -> None:
    parser = build_parser()

    assert parser.description is not None
    assert "PDF" in parser.description

    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])

    capsys.readouterr()


def test_prepare_records_cli_requires_ocr_fixture(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "prepare-records",
                "--input",
                str(fixture_dir / "for testing only.pdf"),
                "--output",
                str(output_json),
            ]
        )

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert "--ocr-fixture" in captured.err
    assert "required" in captured.err


def test_prepare_records_cli_rejects_unknown_template_id(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(fixture_dir / "for testing only.ocr.json"),
            "--template-id",
            "service_record.v2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Unsupported template_id: 'service_record.v2'" in captured.err
    assert "Traceback" not in captured.err


def test_prepare_records_cli_reports_missing_input_without_traceback(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"
    missing_input = tmp_path / "missing.pdf"

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(missing_input),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(fixture_dir / "for testing only.ocr.json"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_prepare_records_cli_reports_missing_ocr_fixture_without_traceback(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"
    missing_fixture = tmp_path / "missing.ocr.json"

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(missing_fixture),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_prepare_records_cli_reports_malformed_ocr_fixture_without_traceback(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"
    malformed_fixture = tmp_path / "malformed.ocr.json"
    malformed_fixture.write_text("{\"unexpected\": []}", encoding="utf-8")

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(malformed_fixture),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_prepare_records_cli_reports_non_object_source_without_traceback(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"
    malformed_fixture = tmp_path / "malformed-source.ocr.json"
    malformed_fixture.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "document_name": "for testing only.pdf",
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

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(malformed_fixture),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_prepare_records_cli_reports_null_source_without_traceback(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"
    malformed_fixture = tmp_path / "null-source.ocr.json"
    malformed_fixture.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "document_name": "for testing only.pdf",
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

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(malformed_fixture),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err


def test_prepare_records_cli_reports_missing_ocr_fixture_page_without_traceback(
    tmp_path: Path, capsys
) -> None:
    pdf_path = tmp_path / "two-page.pdf"
    output_json = tmp_path / "prepared.json"
    missing_page_fixture = tmp_path / "missing-page.ocr.json"
    document = fitz.open()
    document.new_page(width=595.44, height=841.68)
    document.new_page(width=595.44, height=841.68)
    document.save(pdf_path)
    document.close()
    missing_page_fixture.write_text(
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
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(pdf_path),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(missing_page_fixture),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert pdf_path.name in captured.err
    assert "page 2" in captured.err
    assert "Traceback" not in captured.err
