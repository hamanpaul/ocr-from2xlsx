from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from openpyxl import load_workbook

import ocr_from2xlsx.workbook as workbook_module
from ocr_from2xlsx.constants import BASIC_COLUMN_BY_FIELD
from ocr_from2xlsx.domain import Services
from ocr_from2xlsx.workbook import WorkbookWriter
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


def _column_for_header(sheet, header: str) -> int:
    for cell in sheet[1]:
        if cell.value == header:
            return cell.column
    raise AssertionError(f"Missing header in fixture: {header}")


def test_writer_copies_template_and_writes_record(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    writer = WorkbookWriter.create_from_template(template, working)
    row_number = writer.write_record(make_record())
    writer.save()
    writer.close()

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
    consult_col = _column_for_header(ws, "諮詢-健康與醫療系統1")
    supplies_col = _column_for_header(ws, "提供實體用品及設備1")
    assert ws.cell(row=2, column=consult_col).value == "1.癌症篩檢與預防"
    assert ws.cell(row=2, column=supplies_col).value == "1.假髮/頭巾/毛帽用品"
    assert wb["一月"]["A1"].value == "=SUM(個案總表!A2:A6)"
    wb.close()


def test_writer_preserves_style_and_column_width(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    before = load_workbook(template)
    before_fill = before["個案總表"]["B1"].fill.fgColor.rgb
    before_width = before["個案總表"].column_dimensions["B"].width
    before.close()

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(make_record())
    writer.save()
    writer.close()

    after = load_workbook(working)
    assert after["個案總表"]["B1"].fill.fgColor.rgb == before_fill
    assert after["個案總表"].column_dimensions["B"].width == before_width
    after.close()


@pytest.mark.parametrize("suffix", [".xlsm", ".xltm"])
def test_workbook_writer_sets_keep_vba_for_macro_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    template = tmp_path / f"template{suffix}"
    create_workbook_template(template)
    captured: dict[str, object] = {}
    real_load_workbook = load_workbook

    def fake_load_workbook(path: Path, **kwargs: object):
        captured.clear()
        captured.update(kwargs)
        return real_load_workbook(path, **kwargs)

    monkeypatch.setattr(workbook_module, "load_workbook", fake_load_workbook)

    writer = WorkbookWriter(template)
    writer.close()

    assert captured.get("keep_vba") is True


def test_workbook_writer_does_not_set_keep_vba_for_xlsx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "template.xlsx"
    create_workbook_template(template)
    captured: dict[str, object] = {}
    real_load_workbook = load_workbook

    def fake_load_workbook(path: Path, **kwargs: object):
        captured.clear()
        captured.update(kwargs)
        return real_load_workbook(path, **kwargs)

    monkeypatch.setattr(workbook_module, "load_workbook", fake_load_workbook)

    writer = WorkbookWriter(template)
    writer.close()

    assert "keep_vba" not in captured


@pytest.mark.parametrize("suffix", [".xlsm", ".xltm"])
def test_create_from_template_rejects_macro_template_to_xlsx(
    tmp_path: Path, suffix: str
) -> None:
    template = tmp_path / f"template{suffix}"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    with pytest.raises(ValueError, match=re.escape("macro-enabled")):
        WorkbookWriter.create_from_template(template, working)


def test_existing_duplicate_keys_include_service_summary(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()
    writer.close()

    reopened = WorkbookWriter(working)

    assert record.duplicate_key() in reopened.existing_duplicate_keys()
    reopened.close()


def test_writer_maps_numbered_services_to_numbered_columns(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    record.services = Services(
        consultation={"health_medical": ["screening_prevention"]},
        supplies=["wig_hat"],
        internal_referrals=["social_welfare"],
        external_referrals=["care_information"],
        referral_outcomes=["received_service_help"],
    )

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()
    writer.close()

    wb = load_workbook(working)
    ws = wb["個案總表"]
    internal_col = _column_for_header(ws, "轉介或連結院內資源3")
    external_col = _column_for_header(ws, "轉介或連結院外資源9")
    outcome_col = _column_for_header(ws, "轉介或連結資源成果4")
    assert ws.cell(row=2, column=internal_col).value == "3.社福資源"
    assert ws.cell(row=2, column=external_col).value == "9.照護資訊"
    assert ws.cell(row=2, column=outcome_col).value == "4.獲得服務協助"
    wb.close()

    reopened = WorkbookWriter(working)

    expected_summary = "|".join(
        sorted(
            [
                "health_medical:screening_prevention",
                "supplies:wig_hat",
                "internal:social_welfare",
                "external:care_information",
                "outcomes:received_service_help",
            ]
        )
    )
    expected_key = ("2026-03-15", "王小明", "A123456", expected_summary)

    assert expected_key in reopened.existing_duplicate_keys()
    reopened.close()


def test_writer_raises_when_service_prefix_missing(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    wb = load_workbook(template)
    ws = wb["個案總表"]
    missing_header = "提供實體用品及設備1"
    ws.cell(row=1, column=_column_for_header(ws, missing_header)).value = None
    wb.save(template)
    wb.close()

    record = make_record()
    writer = WorkbookWriter.create_from_template(template, working)
    with pytest.raises(
        ValueError, match=re.escape("Missing workbook service columns for 提供實體用品及設備")
    ):
        writer.write_record(record)
    writer.close()


def test_writer_routes_unmapped_service_to_sparse_column(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    record.services = Services(internal_referrals=["psychology"])

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()
    writer.close()

    wb = load_workbook(working)
    ws = wb["個案總表"]
    internal_col = _column_for_header(ws, "轉介或連結院內資源3")
    assert ws.cell(row=2, column=internal_col).value == "psychology"
    wb.close()

    reopened = WorkbookWriter(working)
    assert record.duplicate_key() in reopened.existing_duplicate_keys()
    reopened.close()


def test_writer_raises_when_sparse_service_columns_are_full(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    record.services = Services(internal_referrals=["social_welfare", "psychology"])

    writer = WorkbookWriter.create_from_template(template, working)
    with pytest.raises(ValueError, match=re.escape("No available workbook column for service psychology")):
        writer.write_record(record)
    writer.close()


def test_existing_duplicate_keys_normalize_excel_date_and_whitespace(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()
    writer.close()

    wb = load_workbook(working)
    ws = wb["個案總表"]
    service_date_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["service_date"])
    name_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["name"])
    id_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["medical_record_no"])
    ws.cell(row=2, column=service_date_col, value=datetime(2026, 3, 15))
    ws.cell(row=2, column=name_col, value=f" {record.name} ")
    ws.cell(row=2, column=id_col, value=f" {record.medical_record_no} ")
    wb.save(working)
    wb.close()

    reopened = WorkbookWriter(working)

    assert record.duplicate_key() in reopened.existing_duplicate_keys()
    reopened.close()


def test_existing_duplicate_keys_include_raw_service_codes(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    create_workbook_template(template)

    wb = load_workbook(template)
    ws = wb["個案總表"]
    ws.cell(row=2, column=_column_for_header(ws, BASIC_COLUMN_BY_FIELD["service_date"]), value="2026-04-01")
    ws.cell(row=2, column=_column_for_header(ws, BASIC_COLUMN_BY_FIELD["name"]), value="李小美")
    ws.cell(row=2, column=_column_for_header(ws, BASIC_COLUMN_BY_FIELD["medical_record_no"]), value="B987654")
    ws.cell(row=2, column=_column_for_header(ws, "諮詢-健康與醫療系統1"), value="some_code")
    ws.cell(row=2, column=_column_for_header(ws, "提供實體用品及設備1"), value="some_supply")
    ws.cell(row=2, column=_column_for_header(ws, "轉介或連結院內資源3"), value="some_resource")
    ws.cell(row=2, column=_column_for_header(ws, "轉介或連結院外資源9"), value="some_external")
    ws.cell(row=2, column=_column_for_header(ws, "轉介或連結資源成果4"), value="some_outcome")
    wb.save(template)
    wb.close()

    expected_summary = "|".join(
        sorted(
            [
                "health_medical:some_code",
                "supplies:some_supply",
                "internal:some_resource",
                "external:some_external",
                "outcomes:some_outcome",
            ]
        )
    )
    expected_key = ("2026-04-01", "李小美", "B987654", expected_summary)

    reopened = WorkbookWriter(template)

    assert expected_key in reopened.existing_duplicate_keys()
    reopened.close()


def test_existing_duplicate_keys_include_non_health_consultation_summary(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    create_workbook_template(template)

    wb = load_workbook(template)
    ws = wb["個案總表"]
    ws.cell(row=2, column=_column_for_header(ws, BASIC_COLUMN_BY_FIELD["service_date"]), value="2026-05-01")
    ws.cell(row=2, column=_column_for_header(ws, BASIC_COLUMN_BY_FIELD["name"]), value="李大明")
    ws.cell(row=2, column=_column_for_header(ws, BASIC_COLUMN_BY_FIELD["medical_record_no"]), value="C111111")
    ws.cell(row=2, column=_column_for_header(ws, "諮詢-營養與飲食1"), value="nutrition_code")
    wb.save(template)
    wb.close()

    expected_key = ("2026-05-01", "李大明", "C111111", "nutrition_diet:nutrition_code")

    reopened = WorkbookWriter(template)

    assert expected_key in reopened.existing_duplicate_keys()
    reopened.close()


def test_workbook_writer_close_closes_workbook(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    create_workbook_template(template)
    writer = WorkbookWriter(template)
    real_close = writer.workbook.close
    called = False

    def fake_close() -> None:
        nonlocal called
        called = True
        real_close()

    writer.workbook.close = fake_close  # type: ignore[method-assign]

    writer.close()

    assert called is True


def test_workbook_writer_context_manager_closes_workbook(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    create_workbook_template(template)
    writer = WorkbookWriter(template)
    real_close = writer.workbook.close
    called = False

    def fake_close() -> None:
        nonlocal called
        called = True
        real_close()

    writer.workbook.close = fake_close  # type: ignore[method-assign]

    with writer as managed:
        assert managed is writer

    assert called is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "是"),
        (False, "否"),
        (None, None),
    ],
)
def test_writer_sets_discharge_followup(
    tmp_path: Path, value: bool | None, expected: str | None
) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    record.discharge_followup = value

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()
    writer.close()

    wb = load_workbook(working)
    ws = wb["個案總表"]
    column = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["discharge_followup"])

    assert ws.cell(row=2, column=column).value == expected
    wb.close()


def test_missing_patient_header_raises_value_error(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    create_workbook_template(template)

    wb = load_workbook(template)
    ws = wb["個案總表"]
    missing_header = BASIC_COLUMN_BY_FIELD["nationality"]
    missing_cell = ws.cell(row=1, column=_column_for_header(ws, missing_header))
    missing_cell.value = None
    wb.save(template)
    wb.close()

    with pytest.raises(ValueError, match=re.escape(missing_header)):
        WorkbookWriter(template)


def test_writer_leaves_newly_diagnosed_blank_when_none(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    record.patient_fields.newly_diagnosed_within_year = None

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()
    writer.close()

    wb = load_workbook(working)
    ws = wb["個案總表"]
    column = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["newly_diagnosed_within_year"])

    assert ws.cell(row=2, column=column).value is None
    wb.close()
