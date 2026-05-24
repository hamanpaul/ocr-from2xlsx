from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from ocr_from2xlsx.workbook import WorkbookWriter
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


def test_writer_copies_template_and_writes_record(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    writer = WorkbookWriter.create_from_template(template, working)
    row_number = writer.write_record(make_record())
    writer.save()

    wb = load_workbook(working)
    ws = wb["個案總表"]
    assert row_number == 2
    assert ws["B2"].value == "3月"
    assert ws["C2"].value == "病人"
    assert ws["D2"].value == "2026-03-15"
    assert ws["E2"].value == "王小明"
    assert ws["F2"].value == "A123456"
    assert ws["G2"].value is None
    assert ws["H2"].value == "女性"
    assert ws["I2"].value is None
    assert ws["J2"].value == "本國籍"
    assert ws["K2"].value == "51-60歲"
    assert ws["O2"].value == "8.乳癌"
    assert ws["R2"].value == "是"
    assert ws["S2"].value == "1.癌症篩檢與預防"
    assert ws["T2"].value == "1.假髮/頭巾/毛帽用品"
    assert wb["一月"]["A1"].value == "=SUM(個案總表!A2:A6)"


def test_writer_preserves_style_and_column_width(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    before = load_workbook(template)
    before_fill = before["個案總表"]["B1"].fill.fgColor.rgb
    before_width = before["個案總表"].column_dimensions["B"].width

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(make_record())
    writer.save()

    after = load_workbook(working)
    assert after["個案總表"]["B1"].fill.fgColor.rgb == before_fill
    assert after["個案總表"].column_dimensions["B"].width == before_width


def test_existing_duplicate_keys_include_service_summary(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()

    reopened = WorkbookWriter(working)

    assert record.duplicate_key() in reopened.existing_duplicate_keys()
