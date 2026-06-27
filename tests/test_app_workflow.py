from __future__ import annotations

from ocr_from2xlsx.app import ReviewApp


def _headless_app(records, session=None):
    from ocr_from2xlsx.form_layout import service_record_layout
    from tests.test_app_navigation import FakeConfirmForm, FakePreview, FakeVar

    app = ReviewApp.__new__(ReviewApp)
    app.records = records
    app.current_index = 0
    app.session = session
    app.editing = False
    app.written_indices = set()
    app._written_rows = {}
    app._blocked_indices = set()
    app._pending_count = 0
    app.loaded_json_path = None
    app.correction_store_path = None
    app.layout = service_record_layout()
    app.fields = {
        k: FakeVar()
        for k in ("record_id", "service_date", "identity", "name", "medical_record_no", "gender")
    }
    app.confirm_form = FakeConfirmForm(app.fields)
    app.preview = FakePreview()
    app._preview_image = None
    app._preview_rotation = 0
    app._status_log = []
    app._status_var = None
    app._status_log_path = None
    app._pending_var = None
    app._progress_var = None
    app._badge_var = None
    app._progress_text = ""
    app._badge_state = "pending"
    return app


def test_progress_and_badge_reflect_write_and_revisit():
    from ocr_from2xlsx.session import AcceptResult
    from tests.test_app_navigation import StubSession
    from tests.test_json_io import make_record

    session = StubSession(
        AcceptResult(record_id="scan-0001", status="written", row_number=2, blockers=[], warnings=[])
    )
    app = _headless_app([make_record("scan-0001"), make_record("scan-0002")], session)

    app._show_record(app.records[0])
    assert app._badge_state == "pending"
    assert app._progress_text.startswith("已寫入 0 / 共 2")

    app._confirm_current()  # writes index 0 (row 2), advances to index 1
    assert app.written_indices == {0}
    assert app._written_rows.get(0) == 2

    app._previous_record()  # back to the written record
    assert app.current_index == 0
    assert app._badge_state == "written"
    assert "已寫入 1 / 共 2" in app._progress_text
    assert "第 2 列" in app._progress_text


def test_confirm_on_written_record_overwrites_its_row(monkeypatch):
    from ocr_from2xlsx.session import AcceptResult
    from tests.test_app_navigation import StubSession
    from tests.test_json_io import make_record

    session = StubSession(
        AcceptResult(record_id="scan-0001", status="written", row_number=5, blockers=[], warnings=[])
    )
    app = _headless_app([make_record("scan-0001")], session)
    app.written_indices = {0}
    app._written_rows = {0: 5}
    app.editing = True
    app.fields["name"].set("王小明")  # 確認並寫入 now requires a name; this harness skips _show_record
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda *a, **k: None)

    app._confirm_current()

    # Overwrote row 5 (not appended) and stayed on the corrected record (no advance).
    assert session.overwrite_rows == [5]
    assert app._written_rows[0] == 5
    assert app.current_index == 0


def test_confirm_on_written_record_cancel_writes_nothing(monkeypatch):
    from ocr_from2xlsx.session import AcceptResult
    from tests.test_app_navigation import StubSession
    from tests.test_json_io import make_record

    session = StubSession(
        AcceptResult(record_id="scan-0001", status="written", row_number=5, blockers=[], warnings=[])
    )
    app = _headless_app([make_record("scan-0001")], session)
    app.written_indices = {0}
    app._written_rows = {0: 5}
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askyesno", lambda *a, **k: False)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda *a, **k: None)

    app._confirm_current()

    assert session.calls == []  # cancelling the overwrite confirmation writes nothing


def test_force_write_on_written_record_overwrites_and_stays(monkeypatch):
    from ocr_from2xlsx.session import AcceptResult
    from tests.test_app_navigation import StubSession
    from tests.test_json_io import make_record

    session = StubSession(
        AcceptResult(record_id="scan-0001", status="forced", row_number=7, blockers=[], warnings=[])
    )
    app = _headless_app([make_record("scan-0001")], session)
    app.written_indices = {0}
    app._written_rows = {0: 7}
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda *a, **k: None)

    app._force_write()

    assert session.overwrite_rows == [7]
    assert app._written_rows[0] == 7
    assert app.current_index == 0
