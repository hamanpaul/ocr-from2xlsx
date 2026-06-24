from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx.app import ReviewApp
from ocr_from2xlsx.form_layout import service_record_layout
from tests.test_app_navigation import FakeConfirmForm, FakePreview, FakeVar
from tests.test_json_io import make_record


def _headless_app() -> ReviewApp:
    review_app = ReviewApp.__new__(ReviewApp)
    review_app.records = []
    review_app.current_index = -1
    review_app.session = None
    review_app.editing = False
    review_app.written_indices = set()
    review_app._written_rows = {}
    review_app._blocked_indices = set()
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
    review_app._preview_rotation = 0
    review_app._status_log = []
    review_app._status_var = None
    review_app._status_log_path = None
    review_app._pending_var = None
    review_app._progress_var = None
    review_app._badge_var = None
    return review_app


def test_show_record_focuses_first_flagged_and_counts():
    app = _headless_app()
    record = make_record("scan-0001")
    record.ocr.warnings = ["name.unconfirmed"]
    app.records = [record]
    app.current_index = 0

    app._show_record(record)

    assert app.confirm_form.focused == "name"
    assert app._pending_count == 1


def test_cancel_edit_reshows_record_and_clears_editing():
    app = _headless_app()
    record = make_record("scan-0001")
    app.records = [record]
    app.current_index = 0
    app._show_record(record)
    app.editing = True
    app.fields["name"].set("典型誤打")

    app._cancel_edit()

    assert app.editing is False
    assert app.fields["name"].get() == record.name


def test_key_handlers_invoke_existing_actions(monkeypatch):
    app = _headless_app()
    calls = []
    monkeypatch.setattr(app, "_confirm_current", lambda: calls.append("confirm"))
    monkeypatch.setattr(app, "_force_write", lambda: calls.append("force"))
    monkeypatch.setattr(app, "_next_record", lambda: calls.append("next"))
    monkeypatch.setattr(app, "_previous_record", lambda: calls.append("prev"))

    assert app._on_confirm_key() == "break"
    assert app._on_force_key() == "break"
    assert app._on_next_record_key() == "break"
    assert app._on_prev_record_key() == "break"
    assert calls == ["confirm", "force", "next", "prev"]


def test_next_prev_flagged_handlers_delegate_to_form():
    app = _headless_app()
    seen = []
    app.confirm_form.focus_next_flagged = lambda: seen.append("next")
    app.confirm_form.focus_prev_flagged = lambda: seen.append("prev")

    assert app._on_next_flagged_key() == "break"
    assert app._on_prev_flagged_key() == "break"
    assert seen == ["next", "prev"]


def test_review_app_binds_documented_shortcuts():
    try:
        app = ReviewApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    app.withdraw()
    try:
        for sequence in (
            "<Return>",
            "<KP_Enter>",
            "<Control-Return>",
            "<F2>",
            "<Control-Shift-Return>",
            "<Next>",
            "<Prior>",
            "<Control-Right>",
            "<Control-Left>",
            "<Escape>",
            "<Control-Tab>",
            "<Control-Shift-Tab>",
        ):
            assert app.bind(sequence), f"missing binding for {sequence}"
    finally:
        app.destroy()
