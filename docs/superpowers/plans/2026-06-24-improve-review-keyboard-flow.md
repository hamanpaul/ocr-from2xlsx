# Keyboard-first, exception-oriented review correction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator confirm-and-write a scanned record entirely from the keyboard, landed straight on the fields that need a human, for issues #42 (keyboard-first) and #43 (exception-oriented review).

**Architecture:** A new pure module `review_nav.py` holds the decision logic (next/prev flagged cycling, number-key → option index) with no Tk, fully unit-testable. The `ConfirmForm` widget class (in `app.py`) gains a focus/de-emphasis/count surface that drives those helpers and exposes deterministic, testable handlers for digit-select (single-choice) and space-toggle (multi-choice). `ReviewApp` (in `app.py`) binds window-level shortcuts to its existing `_confirm_current`/`_force_write`/`_next_record`/`_previous_record` methods (write semantics unchanged) and, on `_show_record`, focuses the first flagged field and shows a "待確認 N" count.

**Tech Stack:** Python 3.11, Tkinter/ttk, pytest. Tests follow the repo pattern: pure logic unit-tested without Tk; real-Tk tests `try: tk.Tk()/ReviewApp()` and `pytest.skip` on `tk.TclError`; headless `ReviewApp.__new__` fixtures with fakes for write/navigation logic. Focus is asserted via method return values and `_current_focus` (a withdrawn Tk root returns `None` from `focus_get()`), and bindings via the non-empty string from `widget.bind("<Event>")`.

---

## File Structure

- **Create** `src/ocr_from2xlsx/review_nav.py` — pure helpers: `next_flagged_key`, `prev_flagged_key`, `option_index_for_digit`. No Tk/cv2.
- **Create** `tests/test_review_nav.py` — Tk-free unit tests for the helpers.
- **Modify** `src/ocr_from2xlsx/app.py` — `ConfirmForm`: nav order + per-field focus widget, flagged set storage, `flagged_keys`/`flagged_count`, `focus_first_flagged`/`focus_next_flagged`/`focus_prev_flagged`, de-emphasis of unflagged labels, single-choice digit-select handlers, multi-choice space-toggle handler, optional `on_field_focused` callback. `ReviewApp`: `_bind_review_shortcuts` + named key handlers, `_cancel_edit`, `_update_pending_count`, `_show_record` focuses first flagged + updates count, `_build_ui` adds a pending-count label, stores the form canvas, wires the focus→scroll callback.
- **Create** `tests/test_confirm_form_keyboard.py` — real-Tk tests for the `ConfirmForm` keyboard surface.
- **Create** `tests/test_app_shortcuts.py` — real-Tk + headless tests for `ReviewApp` bindings, handlers, exception-first load, cancel-edit.
- **Modify** `tests/test_app_navigation.py` — extend the shared `FakeConfirmForm` and `app` fixture so `_show_record`'s new calls work headless.
- **Modify** `CHANGELOG.md` — `[Unreleased] / ### Added` entry (#42, #43).
- **Modify** `README.md` — correction-workflow shortcut note.

---

## Task 1: Pure navigation & selection helpers

**Files:**
- Create: `src/ocr_from2xlsx/review_nav.py`
- Test: `tests/test_review_nav.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review_nav.py
from __future__ import annotations

from ocr_from2xlsx.review_nav import (
    next_flagged_key,
    option_index_for_digit,
    prev_flagged_key,
)

ORDER = ["service_date", "identity", "name", "gender", "cancer"]


def test_next_flagged_cycles_only_flagged_in_order():
    assert next_flagged_key(ORDER, {"name", "gender"}, "service_date") == "name"
    assert next_flagged_key(ORDER, {"name", "gender"}, "name") == "gender"


def test_next_flagged_wraps_around():
    assert next_flagged_key(ORDER, {"name", "gender"}, "gender") == "name"


def test_next_flagged_from_none_returns_first_flagged():
    assert next_flagged_key(ORDER, {"gender", "name"}, None) == "name"


def test_next_flagged_single_flag_wraps_to_itself():
    assert next_flagged_key(ORDER, {"name"}, "name") == "name"


def test_next_flagged_empty_returns_none():
    assert next_flagged_key(ORDER, set(), "name") is None


def test_next_flagged_ignores_flags_not_in_order():
    assert next_flagged_key(ORDER, {"ghost"}, "name") is None


def test_prev_flagged_cycles_backwards_and_wraps():
    assert prev_flagged_key(ORDER, {"name", "gender"}, "gender") == "name"
    assert prev_flagged_key(ORDER, {"name", "gender"}, "name") == "gender"
    assert prev_flagged_key(ORDER, {"identity", "cancer"}, "identity") == "cancer"


def test_prev_flagged_empty_returns_none():
    assert prev_flagged_key(ORDER, set(), "name") is None


def test_option_index_for_digit_maps_one_based_to_zero_based():
    assert option_index_for_digit("1", 3) == 0
    assert option_index_for_digit("3", 3) == 2


def test_option_index_for_digit_rejects_out_of_range_and_non_digits():
    assert option_index_for_digit("4", 3) is None
    assert option_index_for_digit("0", 3) is None
    assert option_index_for_digit("a", 3) is None
    assert option_index_for_digit("", 3) is None
    assert option_index_for_digit("12", 3) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -W error -m pytest tests/test_review_nav.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocr_from2xlsx.review_nav'`.

- [ ] **Step 3: Write the implementation**

```python
# src/ocr_from2xlsx/review_nav.py
"""Pure navigation/selection helpers for the keyboard-first review form.

No Tk/cv2 imports: these operate on plain data (ordered field keys, a flagged
set, the current key, an option count), so they are fully unit-testable. The Tk
layer in ``app.py`` (ConfirmForm/ReviewApp) wires focus and key bindings to
these decisions, mirroring ``_wheel_scroll_units`` / ``decide_camera_selection``.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence


def next_flagged_key(
    order: Sequence[str], flagged: Iterable[str], current: str | None
) -> str | None:
    """Return the next flagged key after ``current`` in ``order``, wrapping once.

    Only keys present in both ``order`` and ``flagged`` count. ``current`` need
    not be flagged: the scan starts just after ``current`` (or at the start when
    ``current`` is ``None`` / not in ``order``). Returns ``None`` when nothing is
    flagged."""
    order_set = set(order)
    flagged_set = {key for key in flagged if key in order_set}
    if not flagged_set:
        return None
    n = len(order)
    start = order.index(current) + 1 if current in order else 0
    for offset in range(n):
        key = order[(start + offset) % n]
        if key in flagged_set:
            return key
    return None


def prev_flagged_key(
    order: Sequence[str], flagged: Iterable[str], current: str | None
) -> str | None:
    """Return the previous flagged key before ``current`` in ``order``, wrapping."""
    order_set = set(order)
    flagged_set = {key for key in flagged if key in order_set}
    if not flagged_set:
        return None
    n = len(order)
    start = order.index(current) - 1 if current in order else n - 1
    for offset in range(n):
        key = order[(start - offset) % n]
        if key in flagged_set:
            return key
    return None


def option_index_for_digit(char: str, option_count: int) -> int | None:
    """Map a digit char ``"1".."9"`` to a 0-based option index, else ``None``.

    Returns ``None`` for non-single-digit input or a digit outside
    ``1..option_count``."""
    if not isinstance(char, str) or len(char) != 1 or not char.isdigit():
        return None
    digit = int(char)
    if digit < 1 or digit > option_count:
        return None
    return digit - 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -W error -m pytest tests/test_review_nav.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/review_nav.py tests/test_review_nav.py
git commit -m "feat: pure next/prev-flagged + digit→option helpers for review nav"
```

---

## Task 2: ConfirmForm — flagged set, focus/nav, de-emphasis, keyboard option entry

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (class `ConfirmForm`, lines ~39-176)
- Test: `tests/test_confirm_form_keyboard.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_confirm_form_keyboard.py
from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx import app as app_module
from ocr_from2xlsx.form_layout import service_record_layout


def _form():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    root.withdraw()
    form = app_module.ConfirmForm(root, service_record_layout())
    return root, form


def test_flagged_keys_and_count_in_layout_order():
    root, form = _form()
    try:
        form.set_flagged_fields({"gender": "low-confidence", "name": "unconfirmed"})
        # "name" precedes "gender" in the layout, so order must be deterministic.
        assert form.flagged_keys() == ["name", "gender"]
        assert form.flagged_count() == 2
    finally:
        root.destroy()


def test_focus_first_flagged_returns_first_flagged_key():
    root, form = _form()
    try:
        form.set_flagged_fields({"gender": "low-confidence", "name": "unconfirmed"})
        assert form.focus_first_flagged() == "name"
        assert form._current_focus == "name"
    finally:
        root.destroy()


def test_focus_first_flagged_falls_back_to_first_editable_when_none_flagged():
    root, form = _form()
    try:
        form.set_flagged_fields({})
        assert form.focus_first_flagged() == "service_date"
    finally:
        root.destroy()


def test_focus_next_and_prev_flagged_cycle_and_wrap():
    root, form = _form()
    try:
        form.set_flagged_fields({"name": "unconfirmed", "gender": "low-confidence"})
        form.focus_first_flagged()  # name
        assert form.focus_next_flagged() == "gender"
        assert form.focus_next_flagged() == "name"   # wrap
        assert form.focus_prev_flagged() == "gender"  # wrap back
    finally:
        root.destroy()


def test_focus_next_flagged_noop_when_none_flagged():
    root, form = _form()
    try:
        form.set_flagged_fields({})
        assert form.focus_next_flagged() is None
    finally:
        root.destroy()


def test_unflagged_labels_are_deemphasized_when_some_field_flagged():
    root, form = _form()
    try:
        form.set_flagged_fields({"name": "unconfirmed"})
        assert form._field_labels["name"].cget("text").startswith("⚠")
        assert str(form._field_labels["name"].cget("foreground")) == "#b00020"
        assert str(form._field_labels["gender"].cget("foreground")) == "#9aa0a6"
    finally:
        root.destroy()


def test_no_flag_keeps_labels_normal():
    root, form = _form()
    try:
        form.set_flagged_fields({})
        assert form._field_labels["name"].cget("text") == "姓名"
        assert str(form._field_labels["name"].cget("foreground")) in ("", "#000000")
    finally:
        root.destroy()


def test_number_key_selects_single_choice_option_and_clears_others():
    root, form = _form()
    try:
        # identity options: patient(1), family_caregiver(2), public_other(3)
        handled = form._single_choice_select_by_digit["identity"]("2")
        assert handled is True
        assert form.single_choice_fields["identity"].get() == "family_caregiver"
        option_vars = form._single_choice_option_vars["identity"]
        assert option_vars["family_caregiver"].get() is True
        assert option_vars["patient"].get() is False
    finally:
        root.destroy()


def test_number_key_out_of_range_does_nothing():
    root, form = _form()
    try:
        handled = form._single_choice_select_by_digit["identity"]("7")
        assert handled is False
        assert form.single_choice_fields["identity"].get() == ""
    finally:
        root.destroy()


def test_digit_typed_in_text_field_stays_text():
    root, form = _form()
    try:
        # Text fields have no digit-select handler at all — digits are plain text.
        assert "medical_record_no" not in form._single_choice_select_by_digit
        assert "service_date" not in form._single_choice_select_by_digit
    finally:
        root.destroy()


def test_space_toggle_multi_choice_option():
    root, form = _form()
    try:
        form.toggle_multi_choice_option("cancer", "lung_cancer")
        assert form.collect()["cancer"] == {"lung_cancer"}
        form.toggle_multi_choice_option("cancer", "lung_cancer")
        assert form.collect()["cancer"] == set()
    finally:
        root.destroy()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -W error -m pytest tests/test_confirm_form_keyboard.py -q`
Expected: FAIL — `AttributeError` (e.g. `flagged_keys`, `_single_choice_select_by_digit`, `toggle_multi_choice_option` missing).

- [ ] **Step 3: Implement the ConfirmForm changes in `src/ocr_from2xlsx/app.py`**

Add the `review_nav` import near the existing imports (after the `review_flags` import on line 18):

```python
from ocr_from2xlsx.review_flags import flagged_fields  # existing line
from ocr_from2xlsx.review_nav import (
    next_flagged_key,
    option_index_for_digit,
    prev_flagged_key,
)
```

Change the `ConfirmForm.__init__` signature and the attributes it initializes. Replace the signature/attribute block (currently lines 40-57, from `def __init__` through `self.frame.columnconfigure(0, weight=1)`) with:

```python
    def __init__(
        self,
        parent: tk.Misc,
        layout: FormLayout,
        on_change: Callable[[], None] | None = None,
        on_field_focused: Callable[[tk.Misc], None] | None = None,
    ) -> None:
        self.layout = layout
        self._on_change = on_change
        self._on_field_focused = on_field_focused
        self.frame = ttk.Frame(parent)
        self.text_fields: dict[str, tk.StringVar] = {}
        self.single_choice_fields: dict[str, tk.StringVar] = {}
        self._single_choice_option_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        self.multi_choice_fields: dict[str, dict[str, tk.BooleanVar]] = {}
        # Field-title labels keyed by record_path, so recognition can flag
        # low-confidence / unfilled fields for the reviewer.
        self._field_labels: dict[str, ttk.Label] = {}
        self._field_titles: dict[str, str] = {}
        # Keyboard-first review surface (#42/#43): the ordered list of navigable
        # fields (by record_path), the focus widget per field, the current flagged
        # set + last-focused field for cycling, and per-field digit-select handlers.
        self._nav_order: list[str] = []
        self._focus_widgets: dict[str, tk.Misc] = {}
        self._flagged: dict[str, str] = {}
        self._current_focus: str | None = None
        self._single_choice_select_by_digit: dict[str, Callable[[str], bool]] = {}
        self.frame.columnconfigure(0, weight=1)
```

Inside the field loop, record the focus widget + nav order, and wire the keyboard option entry.

For the **text** branch (currently lines 69-76), after `self.text_fields[field.key] = var` add:

```python
                    if field.record_path:
                        self._focus_widgets[field.record_path] = entry
                        self._nav_order.append(field.record_path)
```

For the **single_choice** branch, replace the body (currently lines 77-111) with:

```python
                elif field.kind == "single_choice":
                    # Single-choice rendered as mutually-exclusive checkboxes (per the
                    # UI request: no radios, no "清除" button). A StringVar holds the
                    # selected code; one BooleanVar per option drives the checkbox.
                    # Clicking an option selects it (clearing the rest); clicking the
                    # selected one clears the field — replacing the clear button.
                    var = tk.StringVar(value="")
                    option_vars: dict[str, tk.BooleanVar] = {}
                    options = ttk.Frame(group)
                    options.grid(row=field_row, column=1, sticky="w", pady=3)

                    def _select(code: str, _var=var, _opts=option_vars) -> None:
                        chosen = "" if _var.get() == code else code
                        _var.set(chosen)
                        for option_code, option_var in _opts.items():
                            option_var.set(option_code == chosen)
                        self._notify_change()

                    option_codes = [option.code for option in field.options]
                    first_checkbox: ttk.Checkbutton | None = None
                    for option_index, option in enumerate(field.options):
                        bvar = tk.BooleanVar(value=False)
                        option_vars[option.code] = bvar
                        checkbox = ttk.Checkbutton(
                            options,
                            text=option.label,
                            variable=bvar,
                            command=lambda code=option.code: _select(code),
                        )
                        checkbox.grid(
                            row=option_index // 4,
                            column=option_index % 4,
                            sticky="w",
                            padx=(0, 8),
                            pady=2,
                        )
                        if first_checkbox is None:
                            first_checkbox = checkbox

                    def _digit_select(char: str, _codes=option_codes, _select=_select) -> bool:
                        index = option_index_for_digit(char, len(_codes))
                        if index is None:
                            return False
                        _select(_codes[index])
                        return True

                    # Number-key option entry is bound ONLY on this field's option
                    # checkboxes, so digits never get stolen from text entries.
                    for checkbox in options.winfo_children():
                        checkbox.bind(
                            "<Key>",
                            lambda event, handler=_digit_select: (
                                "break" if handler(event.char) else None
                            ),
                        )
                    self.single_choice_fields[field.key] = var
                    self._single_choice_option_vars[field.key] = option_vars
                    self._single_choice_select_by_digit[field.key] = _digit_select
                    if field.record_path and first_checkbox is not None:
                        self._focus_widgets[field.record_path] = first_checkbox
                        self._nav_order.append(field.record_path)
```

For the **multi_choice** branch, replace the body (currently lines 112-131) with:

```python
                elif field.kind == "multi_choice":
                    options = ttk.Frame(group)
                    options.grid(row=field_row, column=1, sticky="w", pady=3)
                    code_vars: dict[str, tk.BooleanVar] = {}
                    first_checkbox = None
                    for option_index, option in enumerate(field.options):
                        bvar = tk.BooleanVar(value=False)
                        checkbox = ttk.Checkbutton(
                            options,
                            text=option.label,
                            variable=bvar,
                            command=self._notify_change,
                        )
                        checkbox.grid(
                            row=option_index // 4,
                            column=option_index % 4,
                            sticky="w",
                            padx=(0, 8),
                            pady=2,
                        )
                        # Explicit space-toggle (deterministic + testable); "break"
                        # suppresses the native toggle so the option flips exactly once.
                        checkbox.bind(
                            "<space>",
                            lambda event, key=field.key, code=option.code: (
                                self.toggle_multi_choice_option(key, code) or "break"
                            ),
                        )
                        code_vars[option.code] = bvar
                        if first_checkbox is None:
                            first_checkbox = checkbox
                    self.multi_choice_fields[field.key] = code_vars
                    if field.record_path and first_checkbox is not None:
                        self._focus_widgets[field.record_path] = first_checkbox
                        self._nav_order.append(field.record_path)
```

Replace `set_flagged_fields` (currently lines 142-150) with a version that stores the flagged set and de-emphasizes unflagged labels when some field is flagged:

```python
    def set_flagged_fields(self, flagged: dict[str, str]) -> None:
        """Mark fields needing the reviewer's attention (low-confidence / empty /
        unconfirmed) and de-emphasize the rest. ``flagged`` maps record_path -> reason.
        When at least one field is flagged, high-confidence fields are greyed so the
        flagged ones stand out (#43)."""
        self._flagged = dict(flagged)
        any_flagged = bool(flagged)
        for record_path, label in self._field_labels.items():
            title = self._field_titles[record_path]
            if record_path in flagged:
                label.configure(text=f"⚠ {title}", foreground="#b00020")
            elif any_flagged:
                label.configure(text=title, foreground="#9aa0a6")
            else:
                label.configure(text=title, foreground="")
```

Add the focus/nav/count/toggle surface as new methods after `set_flagged_fields`:

```python
    def flagged_keys(self) -> list[str]:
        """Flagged fields in layout (navigable) order."""
        return [key for key in self._nav_order if key in self._flagged]

    def flagged_count(self) -> int:
        return len(self.flagged_keys())

    def _focus(self, record_path: str | None) -> str | None:
        if record_path is None:
            return None
        widget = self._focus_widgets.get(record_path)
        if widget is None:
            return None
        self._current_focus = record_path
        try:
            widget.focus_set()
        except Exception:
            pass
        if self._on_field_focused is not None:
            try:
                self._on_field_focused(widget)
            except Exception:
                pass
        return record_path

    def focus_first_flagged(self) -> str | None:
        """Focus the first flagged field, or the first editable field if none are
        flagged. Returns the focused field's record_path (or ``None``)."""
        flagged = self.flagged_keys()
        target = flagged[0] if flagged else (self._nav_order[0] if self._nav_order else None)
        return self._focus(target)

    def focus_next_flagged(self) -> str | None:
        return self._focus(next_flagged_key(self._nav_order, self._flagged, self._current_focus))

    def focus_prev_flagged(self) -> str | None:
        return self._focus(prev_flagged_key(self._nav_order, self._flagged, self._current_focus))

    def toggle_multi_choice_option(self, field_key: str, code: str) -> None:
        """Flip one multi-choice option (the spacebar action) and notify change."""
        bvar = self.multi_choice_fields.get(field_key, {}).get(code)
        if bvar is None:
            return
        bvar.set(not bvar.get())
        self._notify_change()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -W error -m pytest tests/test_confirm_form_keyboard.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Run the existing ConfirmForm/app tests to confirm no regression**

Run: `python -W error -m pytest tests/test_app_navigation.py tests/test_confirm_form.py -q`
Expected: PASS (still 51-area green; `ConfirmForm(...)` two-arg construction still works).

- [ ] **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_confirm_form_keyboard.py
git commit -m "feat: ConfirmForm keyboard surface — focus/nav, de-emphasis, digit/space option entry (#42 #43)"
```

---

## Task 3: ReviewApp — shortcuts, exception-first load, cancel-edit, pending count

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (class `ReviewApp`)
- Modify: `tests/test_app_navigation.py` (shared `FakeConfirmForm` + `app` fixture)
- Test: `tests/test_app_shortcuts.py`

- [ ] **Step 1: Extend the shared fakes in `tests/test_app_navigation.py`**

In `FakeConfirmForm` (class starting line 88) add these methods (so `_show_record`'s new calls work headless):

```python
    def flagged_keys(self) -> list[str]:
        return list(getattr(self, "flagged", {}).keys())

    def flagged_count(self) -> int:
        return len(getattr(self, "flagged", {}))

    def focus_first_flagged(self) -> str | None:
        keys = self.flagged_keys()
        self.focused = keys[0] if keys else None
        return self.focused

    def focus_next_flagged(self) -> str | None:
        return None

    def focus_prev_flagged(self) -> str | None:
        return None
```

In the `app` fixture (starting line 340), add `_pending_var` to the constructed instance (after `review_app._status_var = None`, line 367):

```python
    review_app._pending_var = None
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_app_shortcuts.py
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
    return review_app


def test_show_record_focuses_first_flagged_and_counts(monkeypatch):
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
    # Re-shown from the stored record, discarding the in-form edit.
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
    app.confirm_form.focus_next_flagged = lambda: seen.append("next")  # type: ignore[assignment]
    app.confirm_form.focus_prev_flagged = lambda: seen.append("prev")  # type: ignore[assignment]

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
            "<Control-Return>",
            "<F2>",
            "<Control-Shift-Return>",
            "<Next>",
            "<Prior>",
            "<Control-Right>",
            "<Control-Left>",
            "<Escape>",
            "<Control-Tab>",
        ):
            assert app.bind(sequence), f"missing binding for {sequence}"
    finally:
        app.destroy()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -W error -m pytest tests/test_app_shortcuts.py -q`
Expected: FAIL — `AttributeError: 'ReviewApp' object has no attribute '_cancel_edit'` / `_on_confirm_key` / missing bindings.

- [ ] **Step 4: Implement the ReviewApp changes in `src/ocr_from2xlsx/app.py`**

In `_build_ui`, store the canvas and wire the focus→scroll callback. Replace the `ConfirmForm(...)` construction line (currently line 317):

```python
        self._form_canvas = canvas
        self.confirm_form = ConfirmForm(
            canvas,
            self.layout,
            on_change=self._mark_editing,
            on_field_focused=self._scroll_form_widget_into_view,
        )
```

Add the pending-count label to the footer. Replace the status-bar block (currently lines 292-296) with:

```python
        # Footer status bar: shows only the latest status; full history goes to the log file.
        footer = ttk.Frame(self)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self._status_var = tk.StringVar(value="就緒")
        ttk.Label(footer, textvariable=self._status_var, anchor="w", relief="sunken").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        # Exception-first review (#43): how many fields on this record still need a human.
        self._pending_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self._pending_var, anchor="e", relief="sunken").pack(
            side=tk.RIGHT, padx=(8, 0)
        )
```

At the end of `_build_ui` (after `self._init_camera()`, line 346), add:

```python
        self._bind_review_shortcuts()
```

Add the new methods to `ReviewApp` (place them right after `_build_ui`, before `_bind_mousewheel_recursive`):

```python
    def _bind_review_shortcuts(self) -> None:
        # Keyboard-first review (#42): window-level shortcuts fire over any focused
        # field. Single-line ttk.Entry does not consume <Return>, so confirm-on-Enter
        # is safe; number-key option entry is bound per single-choice field, not here.
        self.bind("<Return>", self._on_confirm_key)
        self.bind("<KP_Enter>", self._on_confirm_key)
        self.bind("<Control-Return>", self._on_confirm_key)
        self.bind("<F2>", self._on_force_key)
        self.bind("<Control-Shift-Return>", self._on_force_key)
        self.bind("<Next>", self._on_next_record_key)        # PgDn
        self.bind("<Prior>", self._on_prev_record_key)       # PgUp
        self.bind("<Control-Right>", self._on_next_record_key)
        self.bind("<Control-Left>", self._on_prev_record_key)
        self.bind("<Escape>", self._on_cancel_key)
        self.bind("<Control-Tab>", self._on_next_flagged_key)
        self.bind("<Control-Shift-Tab>", self._on_prev_flagged_key)

    def _on_confirm_key(self, _event: "tk.Event | None" = None) -> str:
        self._confirm_current()
        return "break"

    def _on_force_key(self, _event: "tk.Event | None" = None) -> str:
        self._force_write()
        return "break"

    def _on_next_record_key(self, _event: "tk.Event | None" = None) -> str:
        self._next_record()
        return "break"

    def _on_prev_record_key(self, _event: "tk.Event | None" = None) -> str:
        self._previous_record()
        return "break"

    def _on_cancel_key(self, _event: "tk.Event | None" = None) -> str:
        self._cancel_edit()
        return "break"

    def _on_next_flagged_key(self, _event: "tk.Event | None" = None) -> str:
        self.confirm_form.focus_next_flagged()
        return "break"

    def _on_prev_flagged_key(self, _event: "tk.Event | None" = None) -> str:
        self.confirm_form.focus_prev_flagged()
        return "break"

    def _cancel_edit(self) -> None:
        # Re-show the current record from its stored values, discarding in-form edits,
        # and clear the unsaved-edit guard so navigation works again.
        if self.current_index < 0 or self.current_index >= len(self.records):
            self.editing = False
            return
        self._show_record(self.records[self.current_index])

    def _scroll_form_widget_into_view(self, widget: "tk.Misc") -> None:
        canvas = getattr(self, "_form_canvas", None)
        if canvas is None:
            return
        try:
            canvas.update_idletasks()
            offset = widget.winfo_rooty() - self.confirm_form.frame.winfo_rooty()
            total = self.confirm_form.frame.winfo_height()
            if total > 0:
                canvas.yview_moveto(max(0.0, min(1.0, offset / total)))
        except tk.TclError:
            pass

    def _update_pending_count(self) -> None:
        count = self.confirm_form.flagged_count()
        self._pending_count = count
        pending_var = getattr(self, "_pending_var", None)
        if pending_var is not None:
            try:
                pending_var.set(f"待確認 {count}" if count else "")
            except Exception:
                pass
```

Update `_show_record` (currently lines 701-708) to focus the first flagged field and refresh the count:

```python
    def _show_record(self, record: Record) -> None:
        self.fields["record_id"].set(record.record_id)
        self.confirm_form.prefill(record_to_form_state(self.layout, record))
        self.confirm_form.set_flagged_fields(
            flagged_fields(list(record.ocr.warnings), SERVICE_RECORD_V1_LAYOUT)
        )
        self._show_source_image(record)
        self.editing = False
        self._update_pending_count()
        self.confirm_form.focus_first_flagged()
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python -W error -m pytest tests/test_app_shortcuts.py -q`
Expected: PASS (6 tests; the real-Tk one runs given a display).

- [ ] **Step 6: Run the full app/confirm/review test set for regressions**

Run: `python -W error -m pytest tests/test_app_navigation.py tests/test_confirm_form.py tests/test_confirm_form_keyboard.py tests/test_review_flags.py tests/test_app_mousewheel.py -q`
Expected: PASS (no regression; `_show_record` headless calls resolve via the extended `FakeConfirmForm`).

- [ ] **Step 7: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_shortcuts.py tests/test_app_navigation.py
git commit -m "feat: ReviewApp keyboard shortcuts + exception-first load + pending count (#42 #43)"
```

---

## Task 4: Docs, full suite, policy

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`

- [ ] **Step 1: Add the CHANGELOG entry**

Under `## [Unreleased]`, in the first `### Added` block (create one if absent, above `### Changed`):

```markdown
### Added
- (#42, #43) 校正改鍵盤優先＋例外導向審核：載入一筆即自動聚焦第一個待確認（⚠）欄位並捲入視野，高信心
  欄位淡化、底部顯示「待確認 N」；快捷鍵 `Enter`/`Ctrl+Enter`＝確認並寫入、`F2`/`Ctrl+Shift+Enter`＝強制
  寫入、`PgDn`/`PgUp`（或 `Ctrl+→/←`）＝下/上一筆、`Esc`＝取消本筆編輯、`Ctrl+Tab`/`Ctrl+Shift+Tab`＝在
  待確認欄位間循環；單選欄可用數字鍵（1–N）選項、多選欄空白鍵切換；文字欄輸入數字仍為文字。
```

- [ ] **Step 2: Add the README shortcut note**

Add a short "校正快捷鍵" subsection near the app/usage section listing the same shortcuts (Enter/Ctrl+Enter, F2/Ctrl+Shift+Enter, PgDn/PgUp or Ctrl+←/→, Esc, Ctrl+Tab/Ctrl+Shift+Tab, number keys for single-choice, space for multi-choice). No new CLI subcommand → the `ocr-from2xlsx --help` marker is unchanged.

- [ ] **Step 3: Run the full suite**

Run: `python -W error -m pytest -q`
Expected: PASS (whole suite green, no skips beyond no-display ones).

- [ ] **Step 4: Run policy check**

Run: `python -m policy_check --repo .`
Expected: no failures (exit 0).

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "docs: changelog + README for keyboard-first review shortcuts (#42 #43)"
```

---

## Self-Review

**Spec coverage** (delta `record-confirmation`):
- "Drive the whole review loop from the keyboard" → Task 3 bindings + handlers (`_on_*_key`), `_cancel_edit`; tests `test_key_handlers_invoke_existing_actions`, `test_cancel_edit_reshows_record_and_clears_editing`, `test_review_app_binds_documented_shortcuts`.
- "Open each record at the first field needing attention" → Task 3 `_show_record` + `focus_first_flagged` + `_update_pending_count`; Task 2 de-emphasis; tests `test_show_record_focuses_first_flagged_and_counts`, `test_focus_first_flagged_*`, `test_unflagged_labels_are_deemphasized_*`.
- "Jump between only the fields needing attention" → Task 1 helpers + Task 2 `focus_next/prev_flagged` + Task 3 `_on_next/prev_flagged_key`; tests `test_focus_next_and_prev_flagged_cycle_and_wrap`, `test_next_flagged_*`.
- "Select field options from the keyboard" → Task 2 `_single_choice_select_by_digit`, `toggle_multi_choice_option`, no digit handler on text fields; tests `test_number_key_*`, `test_space_toggle_multi_choice_option`, `test_digit_typed_in_text_field_stays_text`.

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `next_flagged_key`/`prev_flagged_key`/`option_index_for_digit` signatures match between Task 1 (def) and Task 2 (call). `focus_first_flagged`/`focus_next_flagged`/`focus_prev_flagged`/`flagged_count`/`flagged_keys`/`toggle_multi_choice_option` names are identical in Task 2 (impl), Task 3 (caller + fake), and the tests. `on_field_focused` keyword matches between `ConfirmForm.__init__` (Task 2) and the `_build_ui` construction (Task 3). `_pending_var`/`_pending_count` consistent across Task 3 impl, fixture, and tests.
