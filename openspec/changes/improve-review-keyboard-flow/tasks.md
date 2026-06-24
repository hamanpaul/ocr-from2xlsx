# Implementation Tasks: Keyboard-first, exception-oriented review correction

**Change ID:** `improve-review-keyboard-flow`

All implementation uses TDD with fail-first tests before production code. Phase 1 (the pure
navigation/selection helpers) is the foundation and lands first; it must be testable with no Tk.

## Phase 1: Pure navigation & selection helpers (no Tk)

- [ ] 1.1 Add fail-first tests for `review_nav` driven by plain data (no Tk): `next_flagged_key` /
  `prev_flagged_key` cycle only flagged keys in the given field order and wrap; with an empty flagged
  set they return `None`; from an unflagged current key the "next" lands on the first flagged after it
  (wrapping); `option_index_for_digit` maps `"1".."9"` to a 0-based option index and returns `None`
  when the digit exceeds the option count or is not a digit.
- [ ] 1.2 Implement `src/ocr_from2xlsx/review_nav.py`: pure `next_flagged_key(order, flagged, current)`,
  `prev_flagged_key(order, flagged, current)`, and `option_index_for_digit(char, option_count)`. No
  imports of Tk/cv2.

**Quality Gate:**
- [ ] Helper tests pass with neither Tk nor a display.

## Phase 2: ConfirmForm focus / de-emphasis / count surface

- [ ] 2.1 Add fail-first real-Tk tests (skip on `tk.TclError`) for `ConfirmForm`: after
  `set_flagged_fields`, `flagged_count()` returns the number of flagged fields and `flagged_keys()`
  returns them in layout order; `focus_first_flagged()` puts focus on the first flagged field's widget
  (and on the first editable field when none are flagged); `focus_next_flagged()` / `focus_prev_flagged()`
  move focus through only the flagged fields and wrap; high-confidence (unflagged) field labels are
  de-emphasized while flagged labels keep the `⚠`/highlight; pressing a number key on a focused
  single-choice field selects that option and clears the others; a digit typed into a text `Entry`
  is entered as text and selects nothing.
- [ ] 2.2 Implement in `ConfirmForm`: record an ordered list of navigable field keys + the focus widget
  per field; store the flagged set in `set_flagged_fields` and add `flagged_keys()` / `flagged_count()`;
  add `focus_first_flagged()` / `focus_next_flagged()` / `focus_prev_flagged()` using `review_nav`
  (guarded so headless fixtures don't raise); de-emphasize unflagged field labels in `set_flagged_fields`;
  bind number keys on single-choice option widgets via `option_index_for_digit` (never on text entries).

**Quality Gate:**
- [ ] ConfirmForm focus/count/selection tests pass under real Tk and skip cleanly with no display.

## Phase 3: ReviewApp keyboard bindings & exception-first load

- [ ] 3.1 Add fail-first tests: a real-Tk test asserts the window binds the documented shortcuts and that
  each invokes the right existing handler (`Return`/`Ctrl+Return` → `_confirm_current`,
  `F2`/`Ctrl+Shift+Return` → `_force_write`, `Next`/`Ctrl+Right` → `_next_record`,
  `Prior`/`Ctrl+Left` → `_previous_record`, `Escape` → cancel-edit, the next-flagged key →
  `confirm_form.focus_next_flagged`); a headless test (fake form, `ReviewApp.__new__`) asserts
  `_show_record` calls `focus_first_flagged()` and updates the "本筆 N 個待確認" count from the flagged
  fields; `Escape` cancel re-shows the current record and clears `editing`.
- [ ] 3.2 Implement in `ReviewApp`: a `_bind_review_shortcuts()` called from `_build_ui`; a
  `_cancel_edit()` that re-shows the current record and clears `editing`; in `_show_record`, after
  prefill + `set_flagged_fields`, call `confirm_form.focus_first_flagged()` and push the
  "本筆 N 個待確認" count (status line/label); keep all confirm/force/blocked write semantics unchanged.

**Quality Gate:**
- [ ] App binding + exception-first-load tests pass headless (fakes) and under real Tk.

## Phase 4: Integration, docs & verification

- [ ] 4.1 CHANGELOG `[Unreleased]` `### Added` entry referencing #42 and #43; README correction-workflow
  note listing the shortcuts (no new CLI subcommand → CLI help unchanged).
- [ ] 4.2 `python -W error -m pytest -q` and `python -m policy_check --repo .` green.
- [ ] 4.3 Manually verify on a real display: open a record → focus lands on the first `⚠` field → fix via
  number/space/typing → Enter writes and advances; next-flagged cycles only flagged fields; record the
  behavior in the PR.
- [ ] 4.4 Base OpenSpec spec (`openspec/specs/record-confirmation/spec.md`) synced on archive.

**Quality Gate:**
- [ ] Full suite + policy green; shortcuts documented; manual run recorded.

## Completion Checklist

- [ ] All phases complete and quality gates green
- [ ] CHANGELOG `[Unreleased]`, README, and PR-template checklist done
- [ ] Ready for `/openspec-archive improve-review-keyboard-flow`
