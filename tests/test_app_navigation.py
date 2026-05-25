from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx.app import ReviewApp
from ocr_from2xlsx.session import AcceptResult
from tests.test_json_io import make_record


class StubSession:
    def __init__(self, result: AcceptResult) -> None:
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    def accept_scan(self, record, force: bool = False) -> AcceptResult:
        self.calls.append((record.record_id, force))
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
    review_app.fields = {
        "record_id": FakeVar(),
        "service_date": FakeVar(),
        "identity": FakeVar(),
        "name": FakeVar(),
        "medical_record_no": FakeVar(),
        "gender": FakeVar(),
    }
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
    assert session.calls == [(records[0].record_id, True)]
    assert app.fields["record_id"].get() == records[0].record_id


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


def test_next_record_skips_written_record(app: ReviewApp) -> None:
    records = [make_record("scan-0001"), make_record("scan-0002")]
    app.records = records
    app.current_index = 0
    app._show_record(records[0])
    app.written_indices = {0}

    class FailingSession:
        def accept_scan(self, record, force: bool = False) -> AcceptResult:
            raise AssertionError("accept_scan should not be called")

        def close(self) -> None:
            return None

    app.session = FailingSession()

    app._next_record()

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


def test_next_record_blocked_does_not_advance(app: ReviewApp) -> None:
    records = [make_record("scan-0001"), make_record("scan-0002")]
    app.records = records
    app.current_index = 0
    app._show_record(records[0])
    result = AcceptResult(
        record_id=records[0].record_id,
        status="blocked",
        row_number=None,
        blockers=["service_date.invalid"],
        warnings=[],
    )
    app.session = StubSession(result)

    app._next_record()

    assert app.current_index == 0
    assert app.fields["record_id"].get() == records[0].record_id
    assert 0 not in app.written_indices
