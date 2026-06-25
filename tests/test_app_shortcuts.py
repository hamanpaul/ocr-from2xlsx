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


def test_clean_record_does_not_steal_focus():
    app = _headless_app()
    record = make_record("scan-0001")  # no warnings -> 0 flagged fields
    app.records = [record]
    app.current_index = 0

    app._show_record(record)

    assert app._pending_count == 0
    # A 0-flagged record must not yank the caret into the first field (#43).
    assert getattr(app.confirm_form, "focused", None) is None


class _FakeListbox:
    def __init__(self, items, selection=()):
        self.items = list(items)
        self._sel = tuple(selection)
        self.focused = False
        self.activated = None

    def size(self):
        return len(self.items)

    def curselection(self):
        return self._sel

    def index(self, _which):
        return 0  # Tk defaults ACTIVE to index 0 even with no real selection

    def get(self, i):
        return self.items[i]

    def focus_set(self):
        self.focused = True

    def activate(self, i):
        self.activated = i

    def selection_clear(self, *_a):
        pass

    def selection_set(self, i):
        self._sel = (i,)


def test_roster_commit_requires_real_selection(monkeypatch):
    app = _headless_app()
    record = make_record("scan-0001")
    app.records = [record]
    app.current_index = 0
    applied = []
    monkeypatch.setattr(app, "_apply_roster_choice", lambda name: applied.append(name))

    # No selection (e.g. Tab-focused but never browsed): must NOT commit the top candidate.
    app._roster_listbox = _FakeListbox(["王小明", "李大華"], selection=())
    assert app._on_roster_commit() == "break"
    assert applied == []

    # A real selection commits exactly that row.
    app._roster_listbox = _FakeListbox(["王小明", "李大華"], selection=(1,))
    assert app._on_roster_commit() == "break"
    assert applied == ["李大華"]


def test_f8_focuses_roster_and_escape_returns_to_name(monkeypatch):
    app = _headless_app()
    app._roster_listbox = _FakeListbox(["王小明", "李大華"])

    assert app._on_focus_roster_key() == "break"
    assert app._roster_listbox.focused is True
    assert app._roster_listbox.activated == 0

    homed = []
    monkeypatch.setattr(app, "_focus_name_field", lambda: homed.append(True))
    assert app._on_roster_escape() == "break"
    assert homed == [True]  # Esc bails to the name field (no commit)


def test_clean_record_resets_image_to_overview():
    app = _headless_app()
    record = make_record("scan-0001")  # 0 flagged -> clean-record path
    app.records = [record]
    app.current_index = 0

    app._show_record(record)

    assert app.preview.reset_called is True


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
            "<F8>",
        ):
            assert app.bind(sequence), f"missing binding for {sequence}"
    finally:
        app.destroy()
