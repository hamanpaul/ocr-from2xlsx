from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.session import ImportSession
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


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
