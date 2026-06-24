# Correction-workflow UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make manual-keying correction faster and safer — separate scan/correction modes, show persistent progress + per-record status, aid handwritten-name correction, and allow re-opening a written record to overwrite its row — for issues #44, #45, #46, #48.

**Architecture:** A new pure module `review_workflow.py` holds the decision logic (mode→visible controls, per-record badge state, roster-candidate ranking) with no Tk. `WorkbookWriter` and `ImportSession` gain an opt-in row-targeted overwrite. `ReviewApp` (in `app.py`) wires modes, progress/badge, the name-crop+roster panel, and the re-open/overwrite flow onto those helpers. The default append-and-advance flow and all validation blockers are unchanged except the explicit, confirmed overwrite path.

**Tech Stack:** Python 3.11, Tkinter/ttk, openpyxl, pytest. Tests follow the repo pattern: pure logic unit-tested without Tk; openpyxl write tests against fixtures (`tests/test_workbook.py`); `tests/test_session.py` for session logic; real-Tk tests `try: ReviewApp()/tk.Tk()` + `pytest.skip(tk.TclError)`; headless `ReviewApp.__new__` fixtures with fakes for write/UI logic. Builds on the keyboard-first review (#42/#43, PR #49) — the current `app.py` already has `ConfirmForm.focus_first_flagged`, `flagged_count`, and the `on_field_focused` surface.

---

## File Structure

- **Create** `src/ocr_from2xlsx/review_workflow.py` — pure helpers: `correction_mode_controls()`, `scan_mode_controls()`, `record_badge_state()`, `rank_roster_candidates()`. No Tk/cv2.
- **Create** `tests/test_review_workflow.py` — Tk-free unit tests.
- **Modify** `src/ocr_from2xlsx/workbook.py` — `write_record(record, row=None)` + `_clear_row(row)` for row-targeted overwrite.
- **Modify** `tests/test_workbook.py` — overwrite/append tests.
- **Modify** `src/ocr_from2xlsx/session.py` — `accept_scan(..., overwrite_row=None)`.
- **Modify** `tests/test_session.py` — overwrite threading + duplicate-key tests.
- **Modify** `src/ocr_from2xlsx/app.py` — `ReviewApp`: scan/correction modes + trimmed toolbar (#44); progress + per-record badge (#45); name-crop zoom + roster picker (#46); re-open & overwrite flow (#48).
- **Create** `tests/test_app_workflow.py` — real-Tk + headless tests for the app wiring.
- **Modify** `tests/test_app_navigation.py` — extend the shared `FakeConfirmForm`/`app` fixture if new `_show_record` calls require it.
- **Modify** `CHANGELOG.md`, `README.md`.

---

## Task 1: Pure workflow helpers

**Files:** Create `src/ocr_from2xlsx/review_workflow.py`; Test `tests/test_review_workflow.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review_workflow.py
from __future__ import annotations

from ocr_from2xlsx.review_workflow import (
    correction_mode_controls,
    rank_roster_candidates,
    record_badge_state,
    scan_mode_controls,
)


def test_modes_are_correct_and_disjoint():
    corr = set(correction_mode_controls())
    scan = set(scan_mode_controls())
    assert corr == {"prev_record", "next_record", "confirm", "force_write", "progress"}
    assert {"capture_recognize", "import_folder_batch", "choose_camera", "rotate"} <= scan
    assert corr.isdisjoint(scan)


def test_record_badge_state_written_takes_priority():
    assert record_badge_state(0, {0}, set()) == "written"
    assert record_badge_state(1, {0}, {1}) == "blocked"
    assert record_badge_state(2, {0}, {1}) == "pending"
    assert record_badge_state(0, {0}, {0}) == "written"


def test_rank_roster_exact_first_then_similar():
    roster = ["王小明", "王大明", "李四", "王小明"]
    out = rank_roster_candidates("王小明", roster)
    assert out[0] == "王小明"
    assert out[1] == "王大明"
    assert out.index("李四") > out.index("王大明")


def test_rank_roster_empty_query_keeps_order_deduped():
    assert rank_roster_candidates("", ["a", "a", "b"]) == ["a", "b"]


def test_rank_roster_limit_and_empty_roster():
    assert rank_roster_candidates("x", [], 5) == []
    assert len(rank_roster_candidates("王", ["王a", "王b", "王c", "王d"], 2)) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -W error -m pytest tests/test_review_workflow.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocr_from2xlsx.review_workflow'`.

- [ ] **Step 3: Implement**

```python
# src/ocr_from2xlsx/review_workflow.py
"""Pure helpers for the correction-workflow UX: toolbar modes, per-record badge
state, and roster-candidate ranking. No Tk/cv2 — plain-data decisions, unit-testable
in isolation, mirroring review_nav / flagged_fields."""
from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence

# Stable control identifiers the UI maps to actual toolbar buttons.
CORRECTION_CONTROLS: tuple[str, ...] = (
    "prev_record",
    "next_record",
    "confirm",
    "force_write",
    "progress",
)
SCAN_CONTROLS: tuple[str, ...] = (
    "choose_camera",
    "capture_recognize",
    "import_folder_batch",
    "rotate",
    "zoom_in",
    "zoom_out",
)


def correction_mode_controls() -> tuple[str, ...]:
    """Toolbar control ids shown in correction mode."""
    return CORRECTION_CONTROLS


def scan_mode_controls() -> tuple[str, ...]:
    """Toolbar control ids shown in scan/capture mode."""
    return SCAN_CONTROLS


def record_badge_state(
    index: int,
    written_indices: Iterable[int],
    blocked_indices: Iterable[int] = (),
) -> str:
    """Return 'written' | 'blocked' | 'pending' for a record index. Written wins."""
    if index in set(written_indices):
        return "written"
    if index in set(blocked_indices):
        return "blocked"
    return "pending"


def rank_roster_candidates(
    name: str,
    roster: Sequence[str],
    limit: int | None = 5,
) -> list[str]:
    """Rank roster names for a name field: exact match first, then by descending
    similarity to ``name``; de-duplicated (first occurrence kept), capped at ``limit``.
    With an empty ``name``, returns the roster in order (de-duplicated)."""
    query = (name or "").strip()
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in roster:
        value = (candidate or "").strip()
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    if not query:
        return unique if limit is None else unique[:limit]
    ordered = sorted(
        unique,
        key=lambda value: (
            0 if value == query else 1,
            -difflib.SequenceMatcher(None, query, value).ratio(),
        ),
    )
    return ordered if limit is None else ordered[:limit]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -W error -m pytest tests/test_review_workflow.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/review_workflow.py tests/test_review_workflow.py
git commit -m "feat: pure review-workflow helpers (modes, badge state, roster ranking) (#44 #45 #46)"
```

---

## Task 2: Workbook row-targeted overwrite

**Files:** Modify `src/ocr_from2xlsx/workbook.py`; Test `tests/test_workbook.py`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_workbook.py`; reuse its existing fixture style — `create_workbook_template` + a helper to build a `Record`)

```python
def test_write_record_to_explicit_row_overwrites_without_appending(tmp_path):
    from ocr_from2xlsx.workbook import WorkbookWriter
    from tests.fixtures import create_workbook_template

    template = tmp_path / "t.xlsx"
    working = tmp_path / "w.xlsx"
    create_workbook_template(template)
    writer = WorkbookWriter.create_from_template(template, working)
    try:
        first = _make_workbook_record(name="王小明", mrn="A1")
        second = _make_workbook_record(name="李大華", mrn="B2")
        row1 = writer.write_record(first)
        row2 = writer.write_record(second)
        assert row2 == row1 + 1
        # Overwrite row1 with a corrected record — no new row appended.
        corrected = _make_workbook_record(name="王小華", mrn="A9")
        out = writer.write_record(corrected, row=row1)
        assert out == row1
        writer.save()
    finally:
        writer.close()

    from openpyxl import load_workbook
    from ocr_from2xlsx.constants import BASIC_COLUMN_BY_FIELD

    wb = load_workbook(working)
    try:
        sheet = wb["個案總表"]
        name_col = _col(sheet, BASIC_COLUMN_BY_FIELD["name"])
        mrn_col = _col(sheet, BASIC_COLUMN_BY_FIELD["medical_record_no"])
        assert sheet.cell(row=row1, column=name_col).value == "王小華"
        assert sheet.cell(row=row1, column=mrn_col).value == "A9"
        assert sheet.cell(row=row2, column=name_col).value == "李大華"  # untouched
    finally:
        wb.close()


def test_overwrite_clears_stale_service_cells(tmp_path):
    from ocr_from2xlsx.workbook import WorkbookWriter
    from tests.fixtures import create_workbook_template

    template = tmp_path / "t.xlsx"
    working = tmp_path / "w.xlsx"
    create_workbook_template(template)
    writer = WorkbookWriter.create_from_template(template, working)
    try:
        full = _make_workbook_record(name="王小明", mrn="A1")
        full.services.consultation["health_medical"] = ["screening_prevention"]
        row = writer.write_record(full)
        # Re-write the same row with a record that has NO services.
        empty_services = _make_workbook_record(name="王小明", mrn="A1")
        writer.write_record(empty_services, row=row)
        writer.save()
    finally:
        writer.close()

    from openpyxl import load_workbook

    wb = load_workbook(working)
    try:
        sheet = wb["個案總表"]
        values = [c.value for c in sheet[row] if c.value not in (None, "")]
        assert "1.癌症篩檢與預防" not in values  # stale service cell cleared
    finally:
        wb.close()
```

Add the small test helpers near the top of `tests/test_workbook.py` if not already present:

```python
def _col(sheet, header):
    for cell in sheet[1]:
        if cell.value == header:
            return cell.column
    raise AssertionError(f"missing header {header}")


def _make_workbook_record(*, name, mrn):
    from ocr_from2xlsx.domain import Record

    return Record.from_dict(
        {
            "record_id": f"r-{mrn}",
            "service_date": "2026-06-01",
            "identity": "patient",
            "name": name,
            "medical_record_no": mrn,
            "gender": "female",
            "patient_fields": {"nationality": "local", "age_group": "51_60", "cancers": ["breast_cancer"]},
            "services": {"consultation": {}},
        }
    )
```

(If `tests/test_workbook.py` already defines equivalent helpers, reuse those instead of redefining.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -W error -m pytest tests/test_workbook.py -q`
Expected: FAIL — `TypeError: write_record() got an unexpected keyword argument 'row'`.

- [ ] **Step 3: Implement** in `src/ocr_from2xlsx/workbook.py`. Change `write_record`'s first line and add `_clear_row`.

Replace:
```python
    def write_record(self, record: Record) -> int:
        row = self._next_empty_row()
```
with:
```python
    def write_record(self, record: Record, row: int | None = None) -> int:
        if row is None:
            row = self._next_empty_row()
        else:
            self._clear_row(row)
```

Add this method next to `_next_empty_row`:
```python
    def _clear_row(self, row: int) -> None:
        # Blank every mapped column in the row so a re-write leaves no stale value
        # from the record that previously occupied it.
        for column in self.header_map.values():
            self.sheet.cell(row=row, column=column, value=None)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -W error -m pytest tests/test_workbook.py -q`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/workbook.py tests/test_workbook.py
git commit -m "feat: WorkbookWriter row-targeted overwrite that clears the row first (#48)"
```

---

## Task 3: Session overwrite threading

**Files:** Modify `src/ocr_from2xlsx/session.py`; Test `tests/test_session.py`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_session.py`, reusing its fixtures)

```python
def test_accept_scan_overwrite_row_writes_to_that_row(tmp_path):
    from ocr_from2xlsx.session import ImportSession
    from tests.fixtures import create_workbook_template

    template = tmp_path / "t.xlsx"
    working = tmp_path / "w.xlsx"
    create_workbook_template(template)
    session = ImportSession.start(template, working)
    try:
        a = _session_record(name="王小明", mrn="A1")
        b = _session_record(name="李大華", mrn="B2")
        r1 = session.accept_scan(a, human_confirmed=True).row_number
        session.accept_scan(b, human_confirmed=True)
        corrected = _session_record(name="王小華", mrn="A1")
        result = session.accept_scan(corrected, human_confirmed=True, overwrite_row=r1)
        assert result.row_number == r1
        assert result.status in {"written", "forced"}
        assert "duplicate.in_batch" not in result.blockers
    finally:
        session.close()
```

Add a `_session_record(*, name, mrn)` helper if `tests/test_session.py` lacks an equivalent (same shape as `_make_workbook_record` above).

- [ ] **Step 2: Run to verify it fails**

Run: `python -W error -m pytest tests/test_session.py -q`
Expected: FAIL — `accept_scan() got an unexpected keyword argument 'overwrite_row'`.

- [ ] **Step 3: Implement** in `src/ocr_from2xlsx/session.py`.

Change the signature:
```python
    def accept_scan(
        self,
        record: Record,
        force: bool = False,
        human_confirmed: bool = False,
        allow_unconfirmed_name: bool = False,
        overwrite_row: int | None = None,
    ) -> AcceptResult:
```

In the duplicate-key block, guard the in-batch blocker on a non-overwrite:
```python
        duplicate_key = None
        if _duplicate_key_is_usable(record):
            duplicate_key = record.duplicate_key()
            if overwrite_row is None and duplicate_key in self.batch_duplicate_keys:
                blockers.append("duplicate.in_batch")
```

Thread the row to the writer:
```python
        row_number = self.writer.write_record(record, row=overwrite_row)
```

(Leave the rest unchanged. An overwrite that changes the duplicate key leaves the prior key in `batch_duplicate_keys`; that rare stale-key case is out of scope and noted in the proposal.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -W error -m pytest tests/test_session.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/session.py tests/test_session.py
git commit -m "feat: ImportSession.accept_scan overwrite_row threads a target row (#48)"
```

---

## Task 4: App — scan/correction modes + trimmed toolbar (#44)

**Files:** Modify `src/ocr_from2xlsx/app.py` (`ReviewApp._build_ui` + mode methods); Test `tests/test_app_workflow.py`.

The current `_build_ui` packs toolbar buttons inline. Restructure so the scan-station and correction buttons are created into a `self._mode_buttons: dict[str, ttk.Button]`, packed/forgotten by mode; keep the setup buttons (選擇模板 XLSX, 匯入 JSON) and a mode toggle always visible.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app_workflow.py
from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx.app import ReviewApp
from ocr_from2xlsx.review_workflow import correction_mode_controls, scan_mode_controls


def _app_or_skip():
    try:
        app = ReviewApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    app.withdraw()
    return app


def test_correction_mode_shows_only_correction_controls():
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


def test_scan_mode_shows_scan_controls():
    app = _app_or_skip()
    try:
        app._set_review_mode("scan")
        for control in scan_mode_controls():
            assert app._mode_buttons[control].winfo_manager(), f"{control} should be visible"
        assert not app._mode_buttons["confirm"].winfo_manager()
    finally:
        app.destroy()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -W error -m pytest tests/test_app_workflow.py -q`
Expected: FAIL — `AttributeError: 'ReviewApp' object has no attribute '_set_review_mode'` / `_mode_buttons`.

- [ ] **Step 3: Implement** in `app.py`. In `_build_ui`, replace the inline toolbar-button packing with grouped creation. Replace the block that creates 上一筆 … 縮小 buttons with:

```python
        self._mode_buttons: dict[str, ttk.Button] = {}
        button_specs = {
            "prev_record": ("上一筆", self._previous_record),
            "next_record": ("下一筆", self._next_record),
            "confirm": ("確認並寫入", self._confirm_current),
            "force_write": ("強制寫入", self._force_write),
            "choose_camera": ("選擇攝影機", self._choose_camera),
            "capture_recognize": ("擷取並辨識", self._capture_and_recognize),
            "import_folder_batch": ("匯入資料夾批次", self._import_folder_batch),
            "rotate": ("旋轉", self._rotate_preview),
            "zoom_in": ("放大", lambda: self._zoom_preview(1.25)),
            "zoom_out": ("縮小", lambda: self._zoom_preview(1 / 1.25)),
        }
        for key, (label, command) in button_specs.items():
            self._mode_buttons[key] = ttk.Button(toolbar, text=label, command=command)
        ttk.Button(toolbar, text="掃描/校正", command=self._toggle_review_mode).pack(side=tk.LEFT, padx=4)
        self._review_mode = "correction"
        self._set_review_mode("correction")
```

Add the mode methods near `_bind_review_shortcuts`:

```python
    def _set_review_mode(self, mode: str) -> None:
        from ocr_from2xlsx.review_workflow import correction_mode_controls, scan_mode_controls

        self._review_mode = mode
        visible = set(correction_mode_controls() if mode == "correction" else scan_mode_controls())
        for key, button in self._mode_buttons.items():
            if key in visible:
                button.pack(side=tk.LEFT, padx=4)
            else:
                button.pack_forget()

    def _toggle_review_mode(self) -> None:
        self._set_review_mode("scan" if self._review_mode == "correction" else "correction")
```

(The footer progress/`待確認` labels stay always visible — "progress" is not a toolbar button.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -W error -m pytest tests/test_app_workflow.py -q`
Expected: PASS.

- [ ] **Step 5: Regression** — `python -W error -m pytest tests/test_app_navigation.py tests/test_app_shortcuts.py -q` (button discovery tests in `test_app_navigation` look up buttons by text via `_button_texts`; ensure those buttons still exist — they do, just packed conditionally). Fix any test that assumed a specific pack order. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_workflow.py
git commit -m "feat: split scan/correction toolbar modes (#44)"
```

---

## Task 5: App — persistent progress + per-record badge (#45)

**Files:** Modify `src/ocr_from2xlsx/app.py`; Test `tests/test_app_workflow.py`.

- [ ] **Step 1: Write the failing test** (headless, using the existing `app` fixture pattern from `test_app_navigation` — import its fakes)

```python
def test_progress_and_badge_update_on_write_and_navigation(monkeypatch):
    from tests.test_app_navigation import FakeConfirmForm, FakePreview, FakeVar, StubSession
    from ocr_from2xlsx.form_layout import service_record_layout
    from ocr_from2xlsx.session import AcceptResult
    from tests.test_json_io import make_record

    app = ReviewApp.__new__(ReviewApp)
    app.records = [make_record("scan-0001"), make_record("scan-0002")]
    app.current_index = 0
    app.session = None
    app.editing = False
    app.written_indices = set()
    app._written_rows = {}
    app._blocked_indices = set()
    app.loaded_json_path = None
    app.correction_store_path = None
    app.layout = service_record_layout()
    app.fields = {k: FakeVar() for k in ("record_id", "service_date", "identity", "name", "medical_record_no", "gender")}
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
    app.session = StubSession(AcceptResult(record_id="scan-0001", status="written", row_number=2, blockers=[], warnings=[]))

    app._show_record(app.records[0])
    assert app._badge_state == "pending"
    app._confirm_current()
    assert app.written_indices == {0}
    assert app._written_rows.get(0) == 2
    app._previous_record()  # back to a written record
    # navigating writes nothing; current is now index 1 in StubSession flow — assert badge derivation
    assert app._progress_text.startswith("已寫入 1 / 共 2")
```

(Refine the exact navigation assertions to match `StubSession` behavior during Step 3; the key checks are `_written_rows`, `_progress_text`, and `_badge_state` exist and update.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -W error -m pytest tests/test_app_workflow.py::test_progress_and_badge_update_on_write_and_navigation -q`
Expected: FAIL — missing `_written_rows` / `_progress_text` / `_badge_state`.

- [ ] **Step 3: Implement** in `app.py`:
  - In `__init__`: add `self._written_rows: dict[int, int] = {}`, `self._blocked_indices: set[int] = set()`, `self._progress_text = ""`, `self._badge_state = "pending"`.
  - In `_build_ui` footer: add `self._progress_var = tk.StringVar(value="")` and `self._badge_var = tk.StringVar(value="")` labels next to `_pending_var`.
  - Add:
    ```python
    def _update_progress(self) -> None:
        total = len(self.records)
        written = len(self.written_indices)
        row = self._written_rows.get(self.current_index)
        text = f"已寫入 {written} / 共 {total}"
        if row:
            text += f"　第 {row} 列"
        self._progress_text = text
        if getattr(self, "_progress_var", None) is not None:
            try:
                self._progress_var.set(text)
            except Exception:
                pass

    def _update_badge(self) -> None:
        from ocr_from2xlsx.review_workflow import record_badge_state

        state = record_badge_state(self.current_index, self.written_indices, self._blocked_indices)
        self._badge_state = state
        label = {"written": "已寫入", "blocked": "被擋下", "pending": "待處理"}[state]
        if getattr(self, "_badge_var", None) is not None:
            try:
                self._badge_var.set(label)
            except Exception:
                pass
    ```
  - In `_show_record`, after `_update_pending_count()`, call `self._update_progress()` and `self._update_badge()`.
  - In `_confirm_current`/`_force_write`, on a successful write record `self._written_rows[self.current_index] = result.row_number`; on a `blocked` result add `self.current_index` to `self._blocked_indices`; call `self._update_progress()`/`self._update_badge()` after state changes.

- [ ] **Step 4: Run to verify it passes**; **Step 5: Regression** (`tests/test_app_navigation.py`); **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_workflow.py
git commit -m "feat: persistent progress + per-record status badge (#45)"
```

---

## Task 6: App — name-crop zoom + roster candidate picker (#46)

**Files:** Modify `src/ocr_from2xlsx/app.py`; Test `tests/test_app_workflow.py`.

- [ ] **Step 1: Write the failing test** — assert `_roster_candidates_for(record)` ranks store roster against the record name, and `_apply_roster_choice(name)` sets the name field + clears `name.unconfirmed`.

```python
def test_apply_roster_choice_fills_name_and_clears_unconfirmed():
    from tests.test_app_navigation import FakeConfirmForm, FakePreview, FakeVar
    from ocr_from2xlsx.form_layout import service_record_layout
    from tests.test_json_io import make_record

    app = ReviewApp.__new__(ReviewApp)
    rec = make_record("scan-0001")
    rec.ocr.warnings = ["name.unconfirmed"]
    app.records = [rec]
    app.current_index = 0
    app.layout = service_record_layout()
    app.fields = {k: FakeVar() for k in ("record_id", "service_date", "identity", "name", "medical_record_no", "gender")}
    app.confirm_form = FakeConfirmForm(app.fields)

    app._apply_roster_choice("王小明")

    assert app.confirm_form.text_fields_value("name") == "王小明" or app.fields["name"].get() == "王小明"
    assert "name.unconfirmed" not in app.records[0].ocr.warnings
```

(Adjust the name-field assertion to however the real `ConfirmForm` exposes the name text var; in the headless fake, `app.fields["name"]` is the StringVar.)

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** in `app.py`:
  - `_roster_candidates_for(record)`: `roster = roster_from_store(self.correction_store_path)` (guard None/missing), then `rank_roster_candidates(record.name, roster)`. Import `roster_from_store` from `correction_store` and `rank_roster_candidates` from `review_workflow`.
  - `_apply_roster_choice(name)`: set the name field var (`self.confirm_form.text_fields["name"].set(name)` for real form; the fake uses `app.fields["name"]`), remove `NAME_UNCONFIRMED` from the current record's `ocr.warnings`, mark `editing = True`.
  - In `_build_ui`/`_show_record`: add a name-crop preview Label and a roster Listbox near the form; in `_show_record`, load `record.ocr.name_crop` (relative to `loaded_json_path.parent`) into the crop Label (fall back to the full source image when absent/unreadable — reuse the existing image-scaling helper), and populate the Listbox from `_roster_candidates_for(record)`; bind Listbox selection to `_apply_roster_choice`.

- [ ] **Step 4: Run to verify it passes**; **Step 5: Regression**; **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_workflow.py
git commit -m "feat: name-crop zoom + selectable roster candidates (#46)"
```

---

## Task 7: App — re-open & overwrite a written row (#48)

**Files:** Modify `src/ocr_from2xlsx/app.py`; Test `tests/test_app_workflow.py`.

- [ ] **Step 1: Write the failing test** (headless; confirm-on-an-already-written record overwrites its row)

```python
def test_confirm_on_written_record_overwrites_its_row(monkeypatch):
    from tests.test_app_navigation import FakeConfirmForm, FakePreview, FakeVar, StubSession
    from ocr_from2xlsx.form_layout import service_record_layout
    from ocr_from2xlsx.session import AcceptResult
    from tests.test_json_io import make_record

    app = ReviewApp.__new__(ReviewApp)
    rec = make_record("scan-0001")
    app.records = [rec]
    app.current_index = 0
    app.editing = True
    app.written_indices = {0}
    app._written_rows = {0: 5}
    app._blocked_indices = set()
    app.layout = service_record_layout()
    app.fields = {k: FakeVar() for k in ("record_id", "service_date", "identity", "name", "medical_record_no", "gender")}
    app.confirm_form = FakeConfirmForm(app.fields)
    app.preview = FakePreview()
    app._status_log = []
    app._status_var = None
    app._status_log_path = None
    app._pending_var = app._progress_var = app._badge_var = None
    app.correction_store_path = None
    app.loaded_json_path = None
    session = StubSession(AcceptResult(record_id="scan-0001", status="written", row_number=5, blockers=[], warnings=[]))
    app.session = session
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda *a, **k: None)

    app._confirm_current()

    # Overwrote row 5 (StubSession records the call); no new index added.
    assert app._written_rows[0] == 5
    assert any(call[0] == "scan-0001" for call in session.calls)
```

(`StubSession.accept_scan` in `test_app_navigation` records `(record_id, force, human_confirmed)`; extend it to also capture `overwrite_row` if asserting the row — update the fake accordingly in Step 3, keeping existing call sites working via a default.)

- [ ] **Step 2: Run to verify it fails** (current `_confirm_current` shows "已寫入，請切換下一筆" and does not overwrite).

- [ ] **Step 3: Implement** in `app.py`. Replace the early-return in `_confirm_current` (and `_force_write`) when `self.current_index in self.written_indices`:

```python
        if self.current_index in self.written_indices:
            row = self._written_rows.get(self.current_index)
            if row is None or not messagebox.askyesno("覆寫確認", f"此筆已寫入第 {row} 列，將覆寫該列。確定？"):
                messagebox.showinfo("提示", "目前資料已寫入，請切換下一筆。")
                return
            overwrite_row = row
        else:
            overwrite_row = None
```

Then pass `overwrite_row=overwrite_row` to `self.session.accept_scan(...)`, and on success keep `self._written_rows[self.current_index] = result.row_number` (unchanged row). Do NOT advance on an overwrite (stay on the corrected record); update progress/badge. Extend `StubSession.accept_scan` (in `tests/test_app_navigation.py`) to accept and record `overwrite_row` with a default of `None`.

- [ ] **Step 4: Run to verify it passes**; **Step 5: Regression** (`tests/test_app_navigation.py` — the overwrite branch must not change the already-written info path for the no-row case); **Step 6: Commit**

```bash
git add src/ocr_from2xlsx/app.py tests/test_app_workflow.py tests/test_app_navigation.py
git commit -m "feat: re-open a written record and overwrite its row (#48)"
```

---

## Task 8: Docs, full suite, policy

**Files:** Modify `CHANGELOG.md`, `README.md`.

- [ ] **Step 1: CHANGELOG** — under `## [Unreleased] / ### Added`, add entries for #44/#45/#46/#48 (modes, progress/badges, name aids, overwrite).
- [ ] **Step 2: README** — extend the correction-workflow section: scan↔correction modes, progress + status badges, name crop + roster picker, re-open-to-overwrite. No new CLI subcommand → CLI help unchanged.
- [ ] **Step 3:** Run `python -W error -m pytest -q` → expected PASS (whole suite green).
- [ ] **Step 4:** Run `python -m policy_check --repo .` → expected 0 failures.
- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "docs: changelog + README for correction-workflow UX (#44 #45 #46 #48)"
```

---

## Self-Review

**Spec coverage** (delta `record-confirmation`, change `improve-review-workflow`):
- "Separate scan and correction into switchable modes" → Task 1 (control sets) + Task 4 (`_set_review_mode`/`_toggle_review_mode`); tests `test_correction_mode_shows_only_correction_controls`, `test_scan_mode_shows_scan_controls`.
- "Show persistent batch progress and per-record write status" → Task 1 (`record_badge_state`) + Task 5 (`_update_progress`/`_update_badge`, `_written_rows`); test `test_progress_and_badge_update_on_write_and_navigation`.
- "Aid handwritten-name correction with a name crop and roster candidates" → Task 1 (`rank_roster_candidates`) + Task 6 (`_roster_candidates_for`/`_apply_roster_choice`, name-crop panel); test `test_apply_roster_choice_fills_name_and_clears_unconfirmed`.
- "Re-open a written record and overwrite its workbook row" → Task 2 (workbook `row=`/`_clear_row`) + Task 3 (`accept_scan overwrite_row=`) + Task 7 (confirm + overwrite flow); tests `test_write_record_to_explicit_row_overwrites_without_appending`, `test_overwrite_clears_stale_service_cells`, `test_accept_scan_overwrite_row_writes_to_that_row`, `test_confirm_on_written_record_overwrites_its_row`.

**Placeholder scan:** UI tasks (5/6/7) note "refine exact assertions during Step 3" — that is execution-time test tuning against the real fakes, not a code placeholder; all production code blocks are concrete.

**Type consistency:** `correction_mode_controls`/`scan_mode_controls`/`record_badge_state`/`rank_roster_candidates` signatures match between Task 1 (def) and Tasks 4/5/6 (callers). `write_record(record, row=None)` matches between Task 2 (def) and Task 3 (call). `accept_scan(..., overwrite_row=None)` matches between Task 3 (def) and Task 7 (call). `_written_rows`/`_blocked_indices`/`_progress_var`/`_badge_var` consistent across Tasks 5/7 and the fixtures.
