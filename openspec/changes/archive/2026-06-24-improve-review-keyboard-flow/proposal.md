# Proposal: Keyboard-first, exception-oriented review correction

**Change ID:** `improve-review-keyboard-flow`
**Created:** 2026-06-24
**Status:** Draft
**Issues:** #42 (校正改鍵盤優先), #43 (例外導向審核)

---

## Problem Statement

Manual-keying correction is the operator's hot loop: for each scanned record they verify the
prefilled fields against the source image and write the row. Today that loop is mouse-bound and
undirected, so every record is slow:

- **Mouse-bound actions (#42).** `上一筆 / 下一筆 / 確認並寫入 / 強制寫入` exist only as toolbar
  buttons with no shortcuts; single-choice fields are mutually-exclusive checkboxes that must be
  clicked; opening a new record does not put the cursor in any field. The hand shuttles between
  keyboard and mouse on every form.
- **Undirected scanning (#43).** Low-confidence fields are marked with `⚠` (`set_flagged_fields`),
  but on load the form neither scrolls to nor focuses the first flagged field, and there is no way to
  jump between flagged fields. The operator visually scans the whole form top-to-bottom hunting for
  `⚠` on every record, and never sees how many items still need confirmation on the current record.

Affected: the cancer-resource-center operator keying scanned paper service-records into Excel — the
highest-volume, most repetitive use of the app.

## Proposed Solution

Make the common record reviewable **without touching the mouse**, and steer the operator straight to
the **exceptions** that actually need a human:

- **Keyboard shortcuts** for the whole loop: confirm-and-write, force-write, next/previous record, and
  cancel-edit, bound at the window so they fire regardless of which field has focus.
- **Exception-first focus on load.** When a record opens, focus moves to the first field needing
  attention (first `⚠` flagged field, else the first editable field), scrolled into view; high-confidence
  fields are visually de-emphasized so the flagged ones stand out; a "本筆 N 個待確認" count is shown.
- **Jump between only the flagged fields.** A "next field needing attention" action cycles through the
  flagged fields in layout order (skipping high-confidence ones) and wraps around, reachable from the
  keyboard.
- **Keyboard option entry.** A focused single-choice field selects an option by number key (1–N);
  a focused multi-choice option toggles with the spacebar; digits typed into a text field are still
  entered as text, never consumed as option selection.

The reusable decision logic — ordered navigable fields, "next flagged" cycling, and number-key →
option mapping — is **pure and unit-testable** without Tk. The Tk layer (bindings, focus, scroll-into-
view, de-emphasis styling) is thin and covered by real-Tk tests that skip when no display is available,
matching the existing `app.py` / `confirm_form.py` test pattern.

## Scope

### In Scope
- Window-level keyboard shortcuts for confirm-and-write, force-write, next record, previous record, and
  cancel-edit.
- On opening a record: focus + scroll-into-view of the first flagged field (else first editable),
  visual de-emphasis of high-confidence fields, and a visible count of fields needing confirmation.
- A keyboard "next field needing attention" action that cycles only flagged fields and wraps.
- Number-key selection for a focused single-choice field; spacebar toggle for a focused multi-choice
  option; digits in text fields remain text input.
- Pure navigation/selection helpers (ordered fields, next-flagged cycling, number→option index) with
  unit tests; `ConfirmForm` focus/de-emphasis/count surface; `ReviewApp` key bindings.

### Out of Scope
- Splitting scan vs. correction modes or trimming the toolbar (#44).
- Persistent batch progress / per-record status badges (#45).
- Name-crop zoom / roster candidate picker (#46).
- Pan/zoom image viewer and field↔layout-region linking (#47).
- Re-open-and-overwrite an already-written row (#48).
- Any change to recognition, validation, the workbook write path, or `service_record.v1`.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `src/ocr_from2xlsx/review_nav.py` | Yes (new) | Pure helpers: ordered navigable field keys, next/prev-flagged cycling, number-key → single-choice option index. No Tk. |
| `src/ocr_from2xlsx/confirm_form.py` / `app.py::ConfirmForm` | Yes | Track flagged set + field order + focus widget per field; `flagged_count()`, `focus_first_flagged()`, `focus_next_flagged()`/`focus_prev_flagged()`; de-emphasize high-confidence fields; number-key on single-choice, ensure multi-choice options are space-toggleable. |
| `src/ocr_from2xlsx/app.py::ReviewApp` | Yes | Bind shortcuts (`Return`/`Ctrl+Return`=confirm, `F2`/`Ctrl+Shift+Return`=force, `Next`/`Ctrl+Right`=next, `Prior`/`Ctrl+Left`=prev, `Escape`=cancel-edit, `Tab`/dedicated key=next-flagged); on `_show_record` focus first flagged + show count. |
| Recognition / validation / `workbook.py` / `service_record.v1` | No | Reused unchanged; the confirm/force/blocked semantics are untouched. |
| `flagged_fields` (`review_flags.py`) | No | Reused as the source of which fields are flagged. |

## Architecture Considerations

Follows the repo's "pure decision logic + thin UI wrappers" pattern. The navigation/selection helpers
operate on plain data (ordered list of field keys, a flagged set, a current key, an option count), so
they are 100% unit-testable without OpenCV/Tk — mirroring `_wheel_scroll_units`, `decide_camera_selection`,
and `flagged_fields`. `ConfirmForm` already owns the per-field widgets and `set_flagged_fields`; it gains
the focus/de-emphasis/count surface that drives the pure helpers. `ReviewApp` already exposes
`_confirm_current` / `_force_write` / `_next_record` / `_previous_record`; the bindings are thin adapters
to those existing methods, so the confirm/force/blocked write semantics are unchanged. Shortcuts bound at
the window fire over any focused widget; single-line `ttk.Entry` does not consume `Return`, so a
window-level confirm-on-Enter is safe, while number-key option selection is bound only on single-choice
widgets so it never steals digits from text entries.

## Success Criteria

- [ ] A common record can be confirmed-and-written end-to-end from the keyboard with no mouse: open →
  focus lands on the first flagged field → fix via number/space/typing → Enter writes and advances.
- [ ] On load, focus + scroll go to the first flagged field (else first editable), high-confidence fields
  are de-emphasized, and the count of fields needing confirmation is visible.
- [ ] A keyboard "next field needing attention" cycles only flagged fields in layout order and wraps.
- [ ] Number keys select single-choice options on a focused single-choice field and clear the rest;
  spacebar toggles a focused multi-choice option; digits typed in a text field stay text.
- [ ] Pure navigation/selection helpers have Tk-free unit tests; `ConfirmForm` focus/count and `ReviewApp`
  bindings have real-Tk tests that skip cleanly with no display.
- [ ] `python -W error -m pytest -q` and `python -m policy_check --repo .` green; CHANGELOG `[Unreleased]`
  and the `record-confirmation` base spec synced on archive.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| `Return`-to-confirm fires accidentally while the operator is mid-typing | Med | Med | Single-line entries don't insert newlines, so Enter is a deliberate commit; the existing blocked-write dialog still guards incomplete records; `Esc` cancels the current edit. |
| Number-key selection steals digits needed in text fields (病歷號/日期) | Med | High | Bind digit keys only on single-choice option widgets, never globally or on text entries; covered by an explicit "digits stay text" test. |
| Tab/focus order surprises (option frames vs. entries) | Med | Low | Navigable order derived from the layout's field order via a pure helper and asserted in tests; focus targets a defined widget per field. |
| Auto-focus/scroll throws when there is no real Tk root (unit fixtures) | Low | Low | Focus/scroll guarded so headless fixtures (`ReviewApp.__new__`) stay testable, matching existing modal/preview guards. |
