from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

import pytest
from openpyxl import load_workbook

from ocr_from2xlsx import app as app_module
from ocr_from2xlsx.confirm_form import record_to_form_state
from ocr_from2xlsx.constants import BASIC_COLUMN_BY_FIELD
from ocr_from2xlsx.correction_store import load_corrections
from ocr_from2xlsx.app import ReviewApp
from ocr_from2xlsx.form_layout import service_record_layout
from ocr_from2xlsx.session import AcceptResult, ImportSession
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


class StubSession:
    def __init__(self, result: AcceptResult) -> None:
        self.result = result
        self.calls: list[tuple[str, bool, bool]] = []

    def accept_scan(
        self, record, force: bool = False, human_confirmed: bool = False
    ) -> AcceptResult:
        self.calls.append((record.record_id, force, human_confirmed))
        if human_confirmed and self.result.status in {"forced", "written"}:
            record.ocr.warnings = [warning for warning in record.ocr.warnings if warning != "name.unconfirmed"]
        return self.result

    def close(self) -> None:
        return None


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def set(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


class FakeListbox:
    def __init__(self) -> None:
        self.items: list[str] = []

    def insert(self, _index, message: str) -> None:
        self.items.append(message)

    def see(self, _index) -> None:
        return None


class FakePreview:
    def __init__(self) -> None:
        self.text = ""
        self.state = "normal"
        self.image = None

    def configure(self, state: str | None = None) -> None:
        if state is not None:
            self.state = state

    def delete(self, _start: str, _end: str) -> None:
        self.text = ""
        self.image = None

    def insert(self, _index: str, value: str) -> None:
        self.text += value

    def image_create(self, _index: str, image) -> None:
        self.image = image

    def get(self, _start: str, _end: str) -> str:
        return self.text


class FakeConfirmForm:
    def __init__(self, fields: dict[str, FakeVar]) -> None:
        self._fields = fields
        self.state: dict[str, object] = {}

    def prefill(self, state: dict[str, object]) -> None:
        self.state = dict(state)
        for key in ("service_date", "identity", "name", "medical_record_no", "gender"):
            if key in self._fields and key in state:
                value = state[key]
                self._fields[key].set("" if value is None else str(value))

    def collect(self) -> dict[str, object]:
        collected = dict(self.state)
        for key in ("service_date", "identity", "name", "medical_record_no", "gender"):
            if key in self._fields:
                collected[key] = self._fields[key].get()
        return collected


def _column_for_header(sheet, header: str) -> int:
    for cell in sheet[1]:
        if cell.value == header:
            return cell.column
    raise AssertionError(f"Missing header in fixture: {header}")


def _button_texts(widget: tk.Misc) -> list[str]:
    texts: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Button):
            texts.append(child.cget("text"))
        texts.extend(_button_texts(child))
    return texts


def _preview_text(preview: object) -> str:
    if isinstance(preview, tk.Text):
        return preview.get("1.0", "end-1c")
    if hasattr(preview, "get"):
        return preview.get("1.0", "end-1c")
    return str(preview)


def test_review_app_builds_confirm_form_and_prefills_record(tmp_path: Path) -> None:
    try:
        app = ReviewApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")

    app.withdraw()
    try:
        record = make_record("scan-0003")
        app.loaded_json_path = tmp_path / "records.json"

        app._show_record(record)

        expected_state = record_to_form_state(app.layout, record)
        collected = app.confirm_form.collect()
        assert app.layout == service_record_layout()
        assert collected["service_date"] == expected_state["service_date"]
        assert collected["identity"] == expected_state["identity"]
        assert collected["name"] == expected_state["name"]
        assert collected["medical_record_no"] == expected_state["medical_record_no"]
        assert collected["gender"] == expected_state["gender"]
        assert collected["cancer"] == expected_state["cancer"]
        assert {"上一筆", "下一筆", "確認並寫入", "強制寫入"} <= set(_button_texts(app))
    finally:
        app.destroy()


def test_confirm_current_writes_whole_page_and_clears_unconfirmed_name(tmp_path: Path) -> None:
    try:
        app = ReviewApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")

    app.withdraw()
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    session = ImportSession.start(template, working)
    try:
        first = make_record("scan-0001")
        first.ocr.warnings = ["name.unconfirmed"]
        first.ocr.raw_text = "癌症資源中心服務紀錄表\n姓名 王小明"
        second = make_record("scan-0002")
        app.session = session
        app.records = [first, second]
        app.loaded_json_path = tmp_path / "records.json"
        app.correction_store_path = tmp_path / "name_corrections.jsonl"

        app._next_record()
        app.confirm_form.text_fields["name"].set(" 王小明 ")
        app.confirm_form.multi_choice_fields["cancer"]["lung_cancer"].set(True)

        app._confirm_current()

        assert app.written_indices == {0}
        assert app.current_index == 1
        assert app.fields["record_id"].get() == second.record_id
        assert first.name == "王小明"
        assert first.ocr.warnings == []
        assert set(first.patient_fields.cancers) == {"breast_cancer", "lung_cancer"}
        assert load_corrections(app.correction_store_path)[0].final_value == "王小明"
        assert any(
            "scan-0001: written" in status for status in app.status_list.get(0, tk.END)
        )

        workbook = load_workbook(working)
        try:
            sheet = workbook["個案總表"]
            name_col = _column_for_header(sheet, BASIC_COLUMN_BY_FIELD["name"])
            assert sheet.cell(row=2, column=name_col).value == "王小明"
        finally:
            workbook.close()
    finally:
        session.close()
        app.destroy()


def test_show_record_without_source_image_keeps_placeholder_preview(tmp_path: Path) -> None:
    try:
        app = ReviewApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")

    app.withdraw()
    try:
        record = make_record("scan-0004")
        record.source.preprocessed_image_path = "missing-preview.png"
        app.loaded_json_path = tmp_path / "records.json"

        app._show_record(record)

        assert "攝影機或圖片預覽區" in _preview_text(app.preview)
    finally:
        app.destroy()


def test_confirm_form_round_trips_prefilled_state() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")

    root.withdraw()
    try:
        form = app_module.ConfirmForm(root, service_record_layout())
        state = {
            "service_date": "2026-05-31",
            "identity": "patient",
            "name": "王小明",
            "medical_record_no": "A123456",
            "diagnosis_date": "2026-01-15",
            "gender": "female",
            "nationality": "local",
            "age": "51_60",
            "channel": "internal_referral",
            "disease_status": "treating",
            "source": "outpatient",
            "newly_diagnosed": "true",
            "consultation.health_medical": {"screening_prevention", "other"},
            "consultation.care_support": {"peer_experience"},
            "supplies": {"wig_hat"},
            "cancer": {"breast_cancer", "lung_cancer"},
        }

        form.prefill(state)

        assert isinstance(form.frame, tk.Widget)
        assert isinstance(form.text_fields["service_date"], tk.StringVar)
        assert isinstance(form.single_choice_fields["identity"], tk.StringVar)
        assert isinstance(form.multi_choice_fields["cancer"]["breast_cancer"], tk.BooleanVar)
        collected = form.collect()
        for key, value in state.items():
            assert collected[key] == value
    finally:
        root.destroy()


def test_confirm_form_single_choice_can_clear_to_unselected() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")

    root.withdraw()
    try:
        form = app_module.ConfirmForm(root, service_record_layout())

        form.prefill({"nationality": "local"})
        assert form.collect()["nationality"] == "local"

        form.single_choice_clear_buttons["nationality"].invoke()

        assert form.collect()["nationality"] == ""
    finally:
        root.destroy()


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> ReviewApp:
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda *args, **kwargs: None)
    review_app = ReviewApp.__new__(ReviewApp)
    review_app.records = []
    review_app.current_index = -1
    review_app.session = None
    review_app.editing = False
    review_app.written_indices = set()
    review_app.loaded_json_path = None
    review_app.correction_store_path = None
    review_app.layout = service_record_layout()
    review_app.fields = {
        "record_id": FakeVar(),
        "service_date": FakeVar(),
        "identity": FakeVar(),
        "name": FakeVar(),
        "medical_record_no": FakeVar(),
        "gender": FakeVar(),
    }
    review_app.confirm_form = FakeConfirmForm(review_app.fields)
    review_app.preview = FakePreview()
    review_app._preview_image = None
    review_app.status_list = FakeListbox()
    return review_app


def test_force_write_does_not_advance(app: ReviewApp) -> None:
    records = [make_record("scan-0001"), make_record("scan-0002")]
    app.records = records
    app.current_index = 0
    app._show_record(records[0])
    app.editing = True
    result = AcceptResult(
        record_id=records[0].record_id,
        status="forced",
        row_number=2,
        blockers=["patient.nationality.required"],
        warnings=[],
    )
    session = StubSession(result)
    app.session = session

    app._force_write()

    assert app.current_index == 0
    assert app.editing is False
    assert app.written_indices == {0}
    assert session.calls == [(records[0].record_id, True, True)]
    assert app.fields["record_id"].get() == records[0].record_id


def test_force_write_persists_non_legacy_confirm_form_fields(app: ReviewApp) -> None:
    record = make_record("scan-0005")
    app.records = [record]
    app.current_index = 0
    app._show_record(record)
    app.editing = True
    app.confirm_form.state["cancer"] = {"lung_cancer"}
    result = AcceptResult(
        record_id=record.record_id,
        status="forced",
        row_number=2,
        blockers=[],
        warnings=[],
    )
    app.session = StubSession(result)

    app._force_write()

    assert record.patient_fields.cancers == ["lung_cancer"]
    assert record.review.edited_by_user is True


def test_force_write_skips_when_already_written(
    app: ReviewApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [make_record("scan-0001")]
    app.records = records
    app.current_index = 0
    app._show_record(records[0])
    app.written_indices = {0}
    info_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "ocr_from2xlsx.app.messagebox.showinfo",
        lambda title, message: info_calls.append((title, message)),
    )

    class FailingSession:
        def accept_scan(self, record, force: bool = False) -> AcceptResult:
            raise AssertionError("accept_scan should not be called")

        def close(self) -> None:
            return None

    app.session = FailingSession()

    app._force_write()

    assert info_calls == [("提示", "目前資料已寫入，請切換下一筆。")]
    assert app.written_indices == {0}


def test_next_record_browses_without_writing_current_record(app: ReviewApp) -> None:
    records = [make_record("scan-0001"), make_record("scan-0002")]
    app.records = records
    app.current_index = 0
    app._show_record(records[0])

    class FailingSession:
        def accept_scan(self, record, force: bool = False) -> AcceptResult:
            raise AssertionError("accept_scan should not be called")

        def close(self) -> None:
            return None

    app.session = FailingSession()

    app._next_record()

    assert app.current_index == 1
    assert app.fields["record_id"].get() == records[1].record_id
    assert app.written_indices == set()


def test_previous_record_browses_without_writing_current_record(app: ReviewApp) -> None:
    records = [make_record("scan-0001"), make_record("scan-0002")]
    app.records = records
    app.current_index = 1
    app._show_record(records[1])

    class FailingSession:
        def accept_scan(self, record, force: bool = False) -> AcceptResult:
            raise AssertionError("accept_scan should not be called")

        def close(self) -> None:
            return None

    app.session = FailingSession()

    ReviewApp._previous_record(app)

    assert app.current_index == 0
    assert app.fields["record_id"].get() == records[0].record_id


def test_next_record_from_initial_index_shows_first_record(app: ReviewApp) -> None:
    record = make_record("scan-0001")
    app.records = [record]

    class FailingSession:
        def accept_scan(self, record, force: bool = False) -> AcceptResult:
            raise AssertionError("accept_scan should not be called")

        def close(self) -> None:
            return None

    app.session = FailingSession()

    app._next_record()

    assert app.current_index == 0
    assert app.fields["record_id"].get() == record.record_id


def test_load_json_sets_default_correction_store_path(
    app: ReviewApp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    json_path = tmp_path / "records.json"
    records = [make_record("scan-0001")]

    monkeypatch.setattr(
        "ocr_from2xlsx.app.filedialog.askopenfilename", lambda **kwargs: str(json_path)
    )

    class FakeSource:
        def __init__(self, path: str) -> None:
            assert Path(path) == json_path

        def records(self):
            return iter(records)

    monkeypatch.setattr("ocr_from2xlsx.app.JsonRecordSource", FakeSource)

    app._load_json()

    assert app.loaded_json_path == json_path
    assert app.correction_store_path == json_path.parent / "name_corrections.jsonl"


def test_confirm_current_blocked_does_not_advance_or_persist_unconfirmed_name(
    app: ReviewApp, tmp_path: Path
) -> None:
    record = make_record("scan-0001")
    next_record = make_record("scan-0002")
    record.ocr.warnings = ["name.unconfirmed"]
    record.ocr.raw_text = "癌症資源中心服務紀錄表\n姓名 王小明\n病歷號 6250712919"
    app.records = [record, next_record]
    app.current_index = 0
    app.correction_store_path = tmp_path / "name_corrections.jsonl"
    session = StubSession(
        AcceptResult(
            record_id=record.record_id,
            status="blocked",
            row_number=None,
            blockers=["name.unconfirmed"],
            warnings=[],
        )
    )
    app.session = session
    app._show_record(record)

    ReviewApp._confirm_current(app)

    assert app.current_index == 0
    assert app.fields["record_id"].get() == record.record_id
    assert app.written_indices == set()
    assert record.ocr.warnings == ["name.unconfirmed"]
    assert session.calls == [(record.record_id, False, True)]
    assert load_corrections(app.correction_store_path) == []


def test_force_write_failure_does_not_persist_unconfirmed_name(app: ReviewApp, tmp_path: Path) -> None:
    record = make_record("scan-0001")
    record.ocr.warnings = ["name.unconfirmed"]
    record.ocr.raw_text = "王小明"
    app.records = [record]
    app.current_index = 0
    app.correction_store_path = tmp_path / "name_corrections.jsonl"
    app._show_record(record)

    class FailingSession:
        def accept_scan(
            self, record, force: bool = False, human_confirmed: bool = False
        ) -> AcceptResult:
            raise OSError("disk full")

        def close(self) -> None:
            return None

    app.session = FailingSession()

    app._force_write()

    assert record.ocr.warnings == ["name.unconfirmed"]
    assert load_corrections(app.correction_store_path) == []


def test_confirm_current_successful_write_tolerates_correction_store_failure(
    app: ReviewApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [make_record("scan-0001"), make_record("scan-0002")]
    records[0].ocr.warnings = ["name.unconfirmed"]
    app.records = records
    app.current_index = 0
    app.correction_store_path = Path("C:\\fake\\name_corrections.jsonl")
    app._show_record(records[0])
    app.session = StubSession(
        AcceptResult(
            record_id=records[0].record_id,
            status="written",
            row_number=2,
            blockers=[],
            warnings=[],
        )
    )
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "ocr_from2xlsx.app.messagebox.showerror",
        lambda title, message: errors.append((title, message)),
    )

    def _raise_store_locked(**kwargs):
        raise OSError("store locked")

    monkeypatch.setattr("ocr_from2xlsx.app.confirm_name", _raise_store_locked)

    ReviewApp._confirm_current(app)

    assert errors == [("寫入失敗", "store locked")]
    assert app.written_indices == {0}
    assert app.current_index == 1
    assert app.fields["record_id"].get() == records[1].record_id


def test_choose_template_clears_written_indices(
    app: ReviewApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.written_indices = {0, 1}
    closed: list[bool] = []

    class ExistingSession:
        def close(self) -> None:
            closed.append(True)

    app.session = ExistingSession()
    template_path = "C:\\templates\\base.xlsx"
    output_dir = "C:\\output"
    start_calls: list[tuple[str, Path]] = []

    monkeypatch.setattr(
        "ocr_from2xlsx.app.filedialog.askopenfilename", lambda **kwargs: template_path
    )
    monkeypatch.setattr(
        "ocr_from2xlsx.app.filedialog.askdirectory", lambda **kwargs: output_dir
    )

    class NewSession:
        def close(self) -> None:
            return None

    def fake_start(template: str, working: Path) -> NewSession:
        start_calls.append((template, working))
        return NewSession()

    monkeypatch.setattr("ocr_from2xlsx.app.ImportSession.start", fake_start)

    app._choose_template()

    assert closed == [True]
    assert start_calls == [(template_path, Path(output_dir) / "匯入中.xlsx")]
    assert app.written_indices == set()
