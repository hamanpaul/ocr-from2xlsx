# Implementation Tasks: Correction-workflow UX

**Change ID:** `improve-review-workflow`

All implementation uses TDD with fail-first tests before production code. Phase 1 (pure helpers) and
Phase 2 (the workbook row-overwrite) are the testable foundations and land first; the Tk wiring builds on
them. Targets `service_record.v1` review only; recognition/validation are untouched (except the opt-in
overwrite path).

## Phase 1: Pure workflow helpers (no Tk)

- [x] 1.1 Fail-first tests for `review_workflow`: `correction_mode_controls()` / `scan_mode_controls()`
  return the right disjoint control sets (correction = navigation + write + progress only; scan = the
  scan-station controls); `record_badge_state(index, written_indices, last_result)` → `"written"` /
  `"pending"` / `"blocked"`; `rank_roster_candidates(name, roster, limit)` returns the best matches first
  (exact/prefix/substring/fuzzy order), de-duplicated, capped at `limit`, `[]` for empty input.
- [x] 1.2 Implement `src/ocr_from2xlsx/review_workflow.py` with those pure functions (no Tk/cv2 imports).

**Quality Gate:** helper tests pass with no Tk.

## Phase 2: Workbook row-targeted overwrite

- [x] 2.1 Fail-first `test_workbook` cases: `write_record(record, row=R)` writes to row `R` (not the next
  empty row); overwriting a row first CLEARS its basic + service cells so no stale value from the prior
  record remains; `write_record(record)` (no row) keeps appending at `_next_empty_row()` exactly as today.
- [x] 2.2 Implement `WorkbookWriter.write_record(self, record, row: int | None = None)`: when `row` is None
  use `_next_empty_row()` (unchanged); when given, clear every mapped basic + service column in that row,
  then write the record into it. Add a private `_clear_row(row)` over `self.header_map`.

**Quality Gate:** workbook overwrite + append tests green; no stale cells after overwrite.

## Phase 3: Session overwrite threading

- [x] 3.1 Fail-first `test_session` cases: `accept_scan(record, overwrite_row=R, human_confirmed=True)`
  writes to row `R` and returns that row number; an overwrite that re-uses the same duplicate key does not
  raise `duplicate.in_batch`; an overwrite replaces the prior duplicate key rather than adding a second.
- [x] 3.2 Implement `ImportSession.accept_scan(..., overwrite_row: int | None = None)`: thread `overwrite_row`
  to `writer.write_record`; when overwriting, drop the prior row's duplicate key before re-adding the new
  one. Default `None` keeps current behavior.

**Quality Gate:** session overwrite tests green; duplicate-key bookkeeping correct on re-confirm.

## Phase 4: App — scan/correction modes + trimmed toolbar (#44)

- [x] 4.1 Fail-first tests (real-Tk + headless): a mode toggle switches between Scan and Correction; in
  Correction mode only 上一筆/下一筆/確認並寫入/強制寫入 (+ progress) are shown and the scan-station buttons
  are hidden; the active mode follows session state.
- [x] 4.2 Implement the toolbar split in `_build_ui`: build two control groups, show/hide by mode via the
  `review_workflow` control sets, add a mode toggle; default to the mode implied by session state.

**Quality Gate:** mode tests green; scan controls unreachable in Correction mode.

## Phase 5: App — persistent progress + per-record badge (#45)

- [x] 5.1 Fail-first tests: a persistent label shows `已寫入 X / 共 N` + the current row; `_show_record`
  shows the per-record badge (已寫入/待處理/被擋下) via `record_badge_state`; navigating back to a written
  record shows 已寫入 + its row.
- [x] 5.2 Implement the progress/row indicator + badge in `app.py`, tracking `record_index → written_row`
  and the last write result; update on every write/overwrite/navigation.

**Quality Gate:** progress + badge tests green headless and under real Tk.

## Phase 6: App — name-crop zoom + roster candidate picker (#46)

- [x] 6.1 Fail-first tests: when a record has `ocr.name_crop`, the name panel shows that crop (zoomed),
  falling back to the full source image when absent/unreadable; roster candidates (from the correction
  store) are listed and selectable; selecting one sets the name and clears `name.unconfirmed`.
- [x] 6.2 Implement the name-crop panel + selectable roster list in `app.py`, reusing the preview-image
  scaling and `roster_from_store`/`rank_roster_candidates`; wire selection to the name field + unconfirmed
  clear.

**Quality Gate:** name-crop + roster tests green.

## Phase 7: App — re-open & overwrite a written row (#48)

- [x] 7.1 Fail-first tests (headless fakes): re-opening a written record and confirming overwrite calls
  `accept_scan(overwrite_row=R)` (no new row); a "將覆寫第 N 列" confirmation is shown and honored; cancelling
  the confirmation writes nothing; the per-record badge stays 已寫入 with the same row.
- [x] 7.2 Implement the re-open/overwrite flow in `app.py`: detect a confirm on an already-written record,
  confirm "將覆寫第 N 列", call `accept_scan(overwrite_row=...)`, keep `written_indices`/row map consistent;
  clarify 確認並寫入 vs 強制寫入 guidance where blocked.

**Quality Gate:** overwrite flow tests green; no duplicate row produced.

## Phase 8: Integration, docs & verification

- [x] 8.1 CHANGELOG `[Unreleased]` entries for #44/#45/#46/#48; README correction-workflow notes (modes,
  progress/badges, name aids, overwrite). No new CLI subcommand → CLI help unchanged.
- [x] 8.2 `python -W error -m pytest -q` and `python -m policy_check --repo .` green.
- [x] 8.3 Behavior verified by automated tests: real-Tk tests cover the mode toggle / control visibility;
  headless tests cover progress+badge on write/navigation, roster pick (fills name + clears unconfirmed),
  and re-open→overwrite (overwrites the exact row, no append, stays on record) for both confirm and force.
  NOTE: a separate interactive operator GUI session (live camera + workbook) was NOT run in this
  environment — recommended as a pre-release smoke check.
- [x] 8.4 Base OpenSpec spec (`openspec/specs/record-confirmation/spec.md`) synced on archive.

**Quality Gate:** full suite (617 passed, 4 skipped) + policy (16 pass / 0 fail) green; docs synced; manual
interactive run deferred (covered by automated tests).

## Completion Checklist

- [x] All phases complete and quality gates green
- [x] CHANGELOG `[Unreleased]`, README, and PR-template checklist done
- [x] Ready for `/openspec-archive improve-review-workflow`
