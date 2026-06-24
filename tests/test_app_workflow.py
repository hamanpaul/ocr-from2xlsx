from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx.app import ReviewApp
from ocr_from2xlsx.review_workflow import correction_mode_controls, scan_mode_controls


def _app_or_skip() -> ReviewApp:
    try:
        app = ReviewApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    app.withdraw()
    return app


def test_correction_mode_shows_only_correction_controls() -> None:
    app = _app_or_skip()
    try:
        app._set_review_mode("correction")
        for control in correction_mode_controls():
            if control == "progress":
                continue
            assert app._mode_buttons[control].winfo_manager(), f"{control} should be visible"
        for control in scan_mode_controls():
            assert not app._mode_buttons[control].winfo_manager(), f"{control} should be hidden"
    finally:
        app.destroy()


def test_scan_mode_shows_scan_controls() -> None:
    app = _app_or_skip()
    try:
        app._set_review_mode("scan")
        for control in scan_mode_controls():
            assert app._mode_buttons[control].winfo_manager(), f"{control} should be visible"
        assert not app._mode_buttons["confirm"].winfo_manager()
    finally:
        app.destroy()


def test_toggle_review_mode_flips_between_modes() -> None:
    app = _app_or_skip()
    try:
        app._set_review_mode("correction")
        app._toggle_review_mode()
        assert app._review_mode == "scan"
        app._toggle_review_mode()
        assert app._review_mode == "correction"
    finally:
        app.destroy()


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
