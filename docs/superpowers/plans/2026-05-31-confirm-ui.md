# Single-page Confirmation UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the six-field review form with a single-page, `form_layout`-driven, fully editable confirmation that shows every service-record field, writes on one click as human-confirmed, and shows the source page image beside the form when available.

**Architecture:** Two pure, Tkinter-free modules — `record_access` (get/set a Record by dotted `record_path`) and `confirm_form` (round-trip a Record ↔ a form-state using `form_layout` + `record_access`) — plus a data-driven Tkinter view in `app.py`. The pure logic is unit-tested without a display; the view has a construction/integration smoke test in the existing `tests/test_app_navigation.py` style.

**Tech Stack:** Python 3.12 stdlib + Tkinter (already used by `app.py`); reuses `form_layout`, `domain.Record`, `session.ImportSession`, `correction_store`. No new dependency.

---

## Spec Reference

Implements `openspec/changes/add-confirm-ui/` and design `docs/superpowers/specs/2026-05-31-confirm-ui-design.md`.

Record structure (`src/ocr_from2xlsx/domain.py`) the paths address:
- top-level str attrs: `service_date`, `identity`, `name`, `medical_record_no`, `gender`
- `patient_fields` (`PatientFields`): `nationality`, `age_group`, `channel`, `disease_status`, `source` (str|None), `cancers` (list[str]), `newly_diagnosed_within_year` (bool|None)
- `services` (`Services`): `consultation` (dict[str, list[str]]), `supplies`/`internal_referrals`/`external_referrals`/`referral_outcomes` (list[str])
- `ocr.warnings` (list[str]) carries `name.unconfirmed`; `review.edited_by_user` (bool)

`form_layout.service_record_layout()` gives sections → fields (`kind` ∈ text/single_choice/multi_choice, `record_path`, `options[code]`). Invariant: pure modules import only stdlib + `ocr_from2xlsx` (no Tkinter).

## File Structure

```text
src/ocr_from2xlsx/record_access.py   NEW. get_by_path / set_by_path over a Record (pure).
src/ocr_from2xlsx/confirm_form.py     NEW. record_to_form_state / apply_form_state (pure, uses form_layout + record_access).
src/ocr_from2xlsx/app.py              MODIFY. Data-driven single-page view + adaptive image panel + one-click confirm.
tests/test_record_access.py           NEW
tests/test_confirm_form.py            NEW
tests/test_app_navigation.py          MODIFY (view build + confirm integration smoke tests)
CHANGELOG.md                          MODIFY
```

---

## Task 1: `record_access` — path get/set (pure)

**Files:**
- Create: `src/ocr_from2xlsx/record_access.py`
- Create: `tests/test_record_access.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_record_access.py`:

```python
from __future__ import annotations

import pytest

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.record_access import get_by_path, set_by_path


def _record() -> Record:
    return Record.from_dict({
        "record_id": "r1", "service_date": "2026-05-26", "identity": "patient",
        "name": "王小明", "medical_record_no": "A1", "gender": "female",
        "patient_fields": {"age_group": "51_60", "cancers": ["breast_cancer"],
                           "newly_diagnosed_within_year": True},
        "services": {"consultation": {"health_medical": ["screening_prevention"]},
                     "supplies": ["wig_hat"]},
    })


def test_get_top_level_and_nested_and_dict():
    r = _record()
    assert get_by_path(r, "identity") == "patient"
    assert get_by_path(r, "patient_fields.age_group") == "51_60"
    assert get_by_path(r, "patient_fields.cancers") == ["breast_cancer"]
    assert get_by_path(r, "patient_fields.newly_diagnosed_within_year") is True
    assert get_by_path(r, "services.consultation.health_medical") == ["screening_prevention"]
    assert get_by_path(r, "services.supplies") == ["wig_hat"]


def test_get_missing_consultation_category_returns_none():
    r = _record()
    assert get_by_path(r, "services.consultation.care_support") is None


def test_set_top_level_nested_list_and_bool():
    r = _record()
    set_by_path(r, "gender", "male")
    set_by_path(r, "patient_fields.age_group", "61_70")
    set_by_path(r, "patient_fields.cancers", ["lung_cancer", "liver_cancer"])
    set_by_path(r, "patient_fields.newly_diagnosed_within_year", False)
    set_by_path(r, "services.consultation.care_support", ["peer_experience"])
    assert r.gender == "male"
    assert r.patient_fields.age_group == "61_70"
    assert r.patient_fields.cancers == ["lung_cancer", "liver_cancer"]
    assert r.patient_fields.newly_diagnosed_within_year is False
    assert r.services.consultation["care_support"] == ["peer_experience"]


def test_set_none_path_is_noop():
    r = _record()
    set_by_path(r, None, "anything")  # record_path=None fields (e.g. diagnosis_date)
    assert r.name == "王小明"


def test_unknown_attr_raises():
    r = _record()
    with pytest.raises(AttributeError):
        set_by_path(r, "nope_field", "x")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_record_access.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/ocr_from2xlsx/record_access.py`:

```python
"""Read/write a Record by a dotted path (the form_layout record_path).

Walks attributes via getattr; when the current node is a dict (e.g. Services.consultation),
uses key access. A path of None is a no-op on set and returns None on get (form-only fields).
"""
from __future__ import annotations

from typing import Any


def get_by_path(record: Any, path: str | None) -> Any:
    if not path:
        return None
    node: Any = record
    for part in path.split("."):
        if node is None:
            return None
        node = node.get(part) if isinstance(node, dict) else getattr(node, part)
    return node


def set_by_path(record: Any, path: str | None, value: Any) -> None:
    if not path:
        return
    parts = path.split(".")
    node: Any = record
    for part in parts[:-1]:
        node = node[part] if isinstance(node, dict) else getattr(node, part)
    last = parts[-1]
    if isinstance(node, dict):
        node[last] = value
    else:
        if not hasattr(node, last):
            raise AttributeError(f"Record has no field for path part {last!r}")
        setattr(node, last, value)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_record_access.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/record_access.py tests/test_record_access.py
git commit -m "feat: add record path get/set accessor"
```
End every commit message with a blank line then exactly:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## Task 2: `confirm_form` — record ↔ form-state round-trip (pure)

**Files:**
- Create: `src/ocr_from2xlsx/confirm_form.py`
- Create: `tests/test_confirm_form.py`

Form-state shape: a dict keyed by `Field.key`. Value per kind:
- `text` → `str`
- `single_choice` → selected code `str` (`""` if none); the boolean field `newly_diagnosed` uses the code
  `"true"` when its record bool is True, else `""`.
- `multi_choice` → `set[str]` of selected codes.

- [ ] **Step 1: Write failing tests**

Create `tests/test_confirm_form.py`:

```python
from __future__ import annotations

from ocr_from2xlsx.confirm_form import apply_form_state, record_to_form_state
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import service_record_layout


def _record() -> Record:
    return Record.from_dict({
        "record_id": "r1", "service_date": "2026-05-26", "identity": "patient",
        "name": "王小明", "medical_record_no": "A1", "gender": "female",
        "patient_fields": {"nationality": "local", "age_group": "51_60",
                           "cancers": ["breast_cancer", "lung_cancer"],
                           "newly_diagnosed_within_year": True},
        "services": {"consultation": {"health_medical": ["screening_prevention"]}},
    })


def test_record_to_form_state_reads_each_kind():
    layout = service_record_layout()
    state = record_to_form_state(layout, _record())
    assert state["service_date"] == "2026-05-26"          # text
    assert state["identity"] == "patient"                  # single_choice
    assert state["gender"] == "female"
    assert state["cancer"] == {"breast_cancer", "lung_cancer"}   # multi_choice (set)
    assert state["consultation.health_medical"] == {"screening_prevention"}
    assert state["newly_diagnosed"] == "true"              # bool True -> code "true"


def test_apply_form_state_writes_back():
    layout = service_record_layout()
    record = _record()
    state = {
        "gender": "male",
        "cancer": {"liver_cancer"},
        "consultation.care_support": {"peer_experience"},
        "newly_diagnosed": "",          # unchecked -> False
        "name": "陳大文",
    }
    apply_form_state(layout, record, state)
    assert record.gender == "male"
    assert set(record.patient_fields.cancers) == {"liver_cancer"}
    assert record.services.consultation["care_support"] == ["peer_experience"]
    assert record.patient_fields.newly_diagnosed_within_year is False
    assert record.name == "陳大文"


def test_round_trip_is_stable():
    layout = service_record_layout()
    record = _record()
    apply_form_state(layout, record, record_to_form_state(layout, record))
    again = record_to_form_state(layout, record)
    assert again["identity"] == "patient"
    assert again["cancer"] == {"breast_cancer", "lung_cancer"}
    assert again["newly_diagnosed"] == "true"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_confirm_form.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/ocr_from2xlsx/confirm_form.py`:

```python
"""Round-trip a Record <-> a Tkinter-free form-state using form_layout + record_access."""
from __future__ import annotations

from typing import Any

from ocr_from2xlsx.form_layout import FormLayout
from ocr_from2xlsx.record_access import get_by_path, set_by_path

# Single-choice fields whose record value is a boolean (one checkbox), keyed by the option code used.
_BOOL_TRUE_CODE = "true"


def _is_bool_field(record_path: str | None) -> bool:
    return record_path == "patient_fields.newly_diagnosed_within_year"


def record_to_form_state(layout: FormLayout, record: Any) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for fld in layout.iter_fields():
        value = get_by_path(record, fld.record_path)
        if fld.kind == "text":
            state[fld.key] = str(value or "")
        elif fld.kind == "multi_choice":
            state[fld.key] = set(value or [])
        else:  # single_choice
            if _is_bool_field(fld.record_path):
                state[fld.key] = _BOOL_TRUE_CODE if value is True else ""
            else:
                state[fld.key] = str(value or "")
    return state


def apply_form_state(layout: FormLayout, record: Any, state: dict[str, Any]) -> None:
    for fld in layout.iter_fields():
        if fld.key not in state or fld.record_path is None:
            continue
        value = state[fld.key]
        if fld.kind == "text":
            set_by_path(record, fld.record_path, str(value or ""))
        elif fld.kind == "multi_choice":
            set_by_path(record, fld.record_path, sorted(value))
        else:  # single_choice
            if _is_bool_field(fld.record_path):
                set_by_path(record, fld.record_path, value == _BOOL_TRUE_CODE)
            else:
                set_by_path(record, fld.record_path, str(value or ""))
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_confirm_form.py -q`
Expected: `3 passed`. (Note: multi_choice writes a sorted list for determinism; if a test compares list order, use `set(...)`.)

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/confirm_form.py tests/test_confirm_form.py
git commit -m "feat: add record/form-state round-trip"
```

---

## Task 3: Data-driven view builder + prefill/collect (Tkinter)

**Files:**
- Modify: `src/ocr_from2xlsx/app.py`
- Modify: `tests/test_app_navigation.py`

Replace the hard-coded six-field form with a builder that creates widgets from `service_record_layout()` and
exposes `prefill(state)` / `collect() -> state` matching the `confirm_form` shapes.

- [ ] **Step 1: Implement the form builder in `app.py`**

Add a `ConfirmForm` helper class (Tkinter) to `app.py`:

```python
class ConfirmForm:
    """Builds editable widgets for the whole service record from the form layout."""

    def __init__(self, parent: "tk.Misc", layout) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.layout = layout
        self._text: dict[str, tk.StringVar] = {}
        self._single: dict[str, tk.StringVar] = {}            # field.key -> selected code ("" = none)
        self._multi: dict[str, dict[str, tk.BooleanVar]] = {} # field.key -> {code: var}
        self.frame = ttk.Frame(parent)
        row = 0
        for section in layout.sections:
            group = ttk.LabelFrame(self.frame, text=f"{section.id} {section.title}")
            group.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
            row += 1
            grow = 0
            for fld in section.fields:
                ttk.Label(group, text=fld.title).grid(row=grow, column=0, sticky="w")
                if fld.kind == "text":
                    var = tk.StringVar()
                    ttk.Entry(group, textvariable=var, width=30).grid(row=grow, column=1, sticky="w")
                    self._text[fld.key] = var
                elif fld.kind == "single_choice":
                    var = tk.StringVar(value="")
                    col = 1
                    for opt in fld.options:
                        ttk.Radiobutton(group, text=opt.label, value=opt.code,
                                        variable=var).grid(row=grow, column=col, sticky="w")
                        col += 1
                    self._single[fld.key] = var
                else:  # multi_choice
                    self._multi[fld.key] = {}
                    col = 1
                    for opt in fld.options:
                        bvar = tk.BooleanVar(value=False)
                        ttk.Checkbutton(group, text=opt.label,
                                        variable=bvar).grid(row=grow, column=col, sticky="w")
                        self._multi[fld.key][opt.code] = bvar
                        col += 1
                grow += 1

    def prefill(self, state: dict) -> None:
        for key, var in self._text.items():
            var.set(str(state.get(key, "")))
        for key, var in self._single.items():
            var.set(str(state.get(key, "")))
        for key, code_vars in self._multi.items():
            selected = set(state.get(key, set()))
            for code, bvar in code_vars.items():
                bvar.set(code in selected)

    def collect(self) -> dict:
        state: dict = {}
        for key, var in self._text.items():
            state[key] = var.get()
        for key, var in self._single.items():
            state[key] = var.get()
        for key, code_vars in self._multi.items():
            state[key] = {code for code, bvar in code_vars.items() if bvar.get()}
        return state
```

- [ ] **Step 2: Smoke test (build + prefill + collect, no mainloop)**

Add to `tests/test_app_navigation.py` (follow the file's existing Tk-headless pattern — if it constructs
`ReviewApp()` directly, mirror that; if Tk is unavailable in CI the existing tests already handle skipping):

```python
def test_confirm_form_builds_prefills_and_collects():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        import pytest
        pytest.skip("no display")
    try:
        from ocr_from2xlsx.app import ConfirmForm
        from ocr_from2xlsx.form_layout import service_record_layout
        form = ConfirmForm(root, service_record_layout())
        form.prefill({"identity": "patient", "gender": "female",
                      "cancer": {"breast_cancer"}, "service_date": "2026-05-26"})
        collected = form.collect()
        assert collected["identity"] == "patient"
        assert collected["gender"] == "female"
        assert collected["cancer"] == {"breast_cancer"}
        assert collected["service_date"] == "2026-05-26"
    finally:
        root.destroy()
```

- [ ] **Step 3: Run + commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app_navigation.py -q`
Expected: pass (or skip if no display).

```powershell
git add src/ocr_from2xlsx/app.py tests/test_app_navigation.py
git commit -m "feat: build confirm form widgets from the form layout"
```

---

## Task 4: Wire the view into ReviewApp + adaptive source-image panel

**Files:**
- Modify: `src/ocr_from2xlsx/app.py`

- [ ] **Step 1: Replace the six-field `form` block** in `_build_ui` with a scrollable container holding a
`ConfirmForm(self.layout)` (set `self.layout = service_record_layout()` in `__init__`). Use a `Canvas` +
inner frame + vertical `Scrollbar` so the long form scrolls. Keep the toolbar, the left preview/source panel,
and the status list.

- [ ] **Step 2: Adaptive source image** — add `_show_source_image(record)`: resolve
`record.source.preprocessed_image_path` against the loaded JSON's directory (`self.loaded_json_path.parent`);
if the file exists, load it into the left preview (`tk.PhotoImage` for PNG, or leave the existing text
preview if loading fails); if absent, show the existing placeholder text. Never raise — on any failure fall
back to the text placeholder.

- [ ] **Step 3: Update `_show_record`** to `self.confirm_form.prefill(record_to_form_state(self.layout, record))`
and call `_show_source_image(record)`; remove the old per-field `self.fields[...]` sets.

- [ ] **Step 4: Smoke test** that `ReviewApp` builds with the new form and `_show_record` prefills without
error for a sample record (skip if no display), and that a record with no source image still shows.

- [ ] **Step 5: Run + commit**

Run: `.venv\Scripts\python.exe -m pytest tests/test_app_navigation.py -q`

```powershell
git add src/ocr_from2xlsx/app.py tests/test_app_navigation.py
git commit -m "feat: single-page confirm view with adaptive source image"
```

---

## Task 5: One-click confirm-and-write flow

**Files:**
- Modify: `src/ocr_from2xlsx/app.py`

- [ ] **Step 1: Rework the confirm action.** Replace `_apply_form_to_record` to use
`apply_form_state(self.layout, record, self.confirm_form.collect())` then `record.review.edited_by_user = True`.
Keep `_needs_name_confirmation`/`_persist_confirmed_name_after_write`. The primary button "確認並寫入" applies
the page, then `session.accept_scan(record, human_confirmed=True)` (since the human reviewed the whole page),
shows blockers inline via the status list, and on written/forced advances to the next record. Keep "強制寫入"
calling `accept_scan(record, force=True, human_confirmed=True)` after applying the page. Update the toolbar
button label/command accordingly (one confirm button + force-write + prev/next).

- [ ] **Step 2: Integration test** (test_app_navigation style, skip if no display): load a small batch into a
`ReviewApp` with a started `ImportSession` (use `tests/fixtures.create_workbook_template`), edit the form
state for the current record (e.g. set identity/gender/name), invoke the confirm action, and assert the
record was written (status written/forced) and `name.unconfirmed` is no longer in `record.ocr.warnings` when
confirmed.

- [ ] **Step 3: Run full suite + commit**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (existing app-navigation tests updated coherently for the new form).

```powershell
git add src/ocr_from2xlsx/app.py tests/test_app_navigation.py
git commit -m "feat: one-click confirm-and-write for the whole record"
```

---

## Task 6: Docs, policy

**Files:**
- Modify: `README.md`, `CHANGELOG.md`

- [ ] **Step 1: README** — note the review UI now shows the whole service record on one page (text + choices +
checkboxes) from the form layout, with one-click confirm (human-confirmed write) and an adaptive source-image
panel.

- [ ] **Step 2: CHANGELOG** — under `## [Unreleased]` `### Added`:

```markdown
- 審核 UI 改為單頁鏡像確認：由 form_layout 資料驅動顯示整張服務記錄表所有欄位（文字/單選/多選），可直接編輯、一鍵確認（human-confirmed 寫入），並在有來源頁圖時並陳核對。
- 新增 `record_access`（依 record_path 讀寫 Record）與 `confirm_form`（record↔表單狀態往返）。
```

- [ ] **Step 3: Tests + policy**

```powershell
.venv\Scripts\python -W error -m pytest -q
.venv\Scripts\python build/package.py
python -m policy_check --repo .
```
Expected: all pass; policy 0 failures.

- [ ] **Step 4: Commit**

```powershell
git add README.md CHANGELOG.md
git commit -m "docs: document single-page confirm UI"
```

---

## Self-Review Notes

- **Spec coverage:** all-fields single page from layout (Task 3/4) ✓; path read/write incl nested/list/bool/None (Task 1) ✓; round-trip prefill/collect (Task 2/3) ✓; one-click human-confirmed write + force-write + blockers inline (Task 5) ✓; adaptive source image (Task 4) ✓; pure unit tests + view smoke/integration tests (Tasks 1-5) ✓; docs/policy (Task 6) ✓.
- **Type consistency:** form-state shapes are consistent across `confirm_form` (text=str, single=code str, multi=set), `ConfirmForm.prefill/collect` (same), and tests. `record_access.get_by_path/set_by_path(record, path|None, …)`, `record_to_form_state(layout, record)`, `apply_form_state(layout, record, state)` are used identically across tasks.
- **Bool field special case:** `newly_diagnosed` (record_path `patient_fields.newly_diagnosed_within_year`, a bool) is handled explicitly in `confirm_form` via `_is_bool_field`; documented. It is the only boolean single-choice field.
- **Known UI-test caveat:** Tkinter tests skip when no display is available; the pure modules (`record_access`, `confirm_form`) carry the substantive coverage and always run in CI. Copilot should follow the existing `tests/test_app_navigation.py` skip pattern.
- **`record_path == None`:** `apply_form_state` skips such fields (diagnosis_date), so the form can show/edit them without writing to the Record.
```
