from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from ocr_from2xlsx.session import ImportSession
from ocr_from2xlsx.constants import BASIC_COLUMN_BY_FIELD
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


def _column_for_header(sheet, header: str) -> int:
    for cell in sheet[1]:
        if cell.value == header:
            return cell.column
    raise AssertionError(f"Missing header in fixture: {header}")


def test_auto_confirm_writes_and_saves_record(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    session = ImportSession.start(template, working)
    result = session.accept_scan(make_record())
    session.close()

    assert result.status == "written"
    assert result.row_number == 2
    assert working.exists()
    wb = load_workbook(working)
    ws = wb["個案總表"]
    name_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["name"])
    id_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["medical_record_no"])
    assert ws.cell(row=2, column=name_col).value == "王小明"
    assert ws.cell(row=2, column=id_col).value == "A123456"
    wb.close()


def test_blocked_record_is_not_written(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    session = ImportSession.start(template, working)
    record = make_record()
    record.service_date = ""
    result = session.accept_scan(record)
    session.close()

    assert result.status == "blocked"
    assert result.row_number is None
    assert "service_date.invalid" in result.blockers
    wb = load_workbook(working)
    ws = wb["個案總表"]
    name_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["name"])
    id_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["medical_record_no"])
    assert ws.cell(row=2, column=name_col).value is None
    assert ws.cell(row=2, column=id_col).value is None
    wb.close()


def test_blocked_record_does_not_reserve_duplicate_key(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    session = ImportSession.start(template, working)
    blocked_record = make_record("scan-0001")
    blocked_record.patient_fields.nationality = None
    blocked_result = session.accept_scan(blocked_record)
    valid_record = make_record("scan-0002")
    valid_result = session.accept_scan(valid_record)
    session.close()

    assert blocked_result.status == "blocked"
    assert "patient.nationality.required" in blocked_result.blockers
    assert valid_result.status == "written"
    assert valid_result.row_number == 2
    assert "duplicate.in_batch" not in valid_result.blockers
