# Proposal: Correction-workflow UX — modes, progress, name aids, write recovery

**Change ID:** `improve-review-workflow`
**Created:** 2026-06-24
**Status:** Draft
**Issues:** #44 (拆掃描/校正模式、精簡工具列), #45 (常駐進度與每筆狀態), #46 (強化手寫姓名校正), #48 (寫入容錯：重開已寫入一筆並覆寫該列)

---

## Problem Statement

Building on the keyboard-first review (#42/#43), four mid-tier pain points still slow the manual-keying
operator and invite mistakes:

- **Mixed toolbar (#44).** One toolbar row holds ~13 buttons that interleave scan-station actions
  (擷取並辨識 / 匯入資料夾批次 / 選擇攝影機 / 旋轉 / 放大 / 縮小) with correction actions
  (上一筆 / 下一筆 / 確認並寫入 / 強制寫入). During correction nine-tenths of the buttons are noise and a
  mis-click (e.g. 擷取並辨識 mid-review) is easy.
- **Invisible progress (#45).** The footer shows only the latest one-line status; "已寫入第 N 列" flashes
  by, there is no batch progress (已完成 X / 共 N), and pressing 上一筆 gives no sign whether that record
  was already written (`written_indices` is tracked but never shown), so records get re-edited or re-written.
- **Hard handwritten-name correction (#46).** The name is the most-corrected field, yet the preview shows
  the **whole** source page and the operator hunts for the name with center-crop zoom. The pipeline already
  produces a **name crop** (`record.ocr.name_crop`) and a confirmed-name **roster** (from the correction
  store), but the UI uses neither — the field that most needs help is the most manual.
- **No write recovery (#48).** `確認並寫入` writes the xlsx row immediately and advances; a keying error is
  hard to fix from the UI because the writer only ever appends (`_next_empty_row`), so re-confirming creates
  a duplicate row instead of overwriting the original.

Affected: the cancer-resource-center operator keying scanned service-records into the monthly Excel.

## Proposed Solution

- **Two modes (#44).** Split the toolbar into a **Scan/Capture** mode and a **Correction** mode, switched by
  the session state. Correction mode shows only 上一筆 / 下一筆 / 確認並寫入 / 強制寫入 + progress; the
  scan-station controls live in Scan mode. This removes clutter and root-causes the mis-clicks.
- **Persistent progress + per-record badge (#45).** A corner indicator shows **已寫入 X / 共 N** and the
  current record's row number; each record shows a status badge — **已寫入 / 待處理 / 被擋下** — derived from
  `written_indices` and the last write result, so going back shows at a glance whether a record is done.
- **Name crop + roster picker (#46).** A dedicated panel shows a **zoomed `record.ocr.name_crop`** (falling
  back to the full source image when no crop exists), and the name field gains a **selectable roster
  candidate list** (from `roster_from_store` + `roster_match`); picking a candidate fills the name and clears
  the `name.unconfirmed` marker.
- **Re-open & overwrite a written row (#48).** A written record can be re-opened and **re-written to its
  original row** (instead of appended) after a confirmation that names the row, so a keying mistake is fixed
  in place with no duplicate or stale value. The workbook writer gains a targeted "overwrite this row" path
  (clear the row's cells, then write) keyed by the row number the original write returned.

Reusable decision logic stays pure and unit-testable (mode→visible-controls mapping, badge-state derivation,
roster-candidate ranking); the Tk wiring and the workbook overwrite are thin and covered by real-Tk / openpyxl
tests in the existing style. The confirm/force/blocked validation semantics are unchanged except for the
explicit, opt-in overwrite path.

## Scope

### In Scope
- Scan vs. Correction toolbar modes driven by session state; correction mode trimmed to navigation + write +
  progress (#44).
- Persistent "已寫入 X / 共 N" + current row indicator; per-record 已寫入/待處理/被擋下 badge from
  `written_indices` + last result (#45).
- Zoomed name-crop panel (fallback to full image) + selectable roster candidates that fill the name and clear
  `name.unconfirmed` (#46).
- Re-open an already-written record and overwrite its workbook row, with a "將覆寫第 N 列" confirmation;
  `WorkbookWriter` gains a row-targeted overwrite that clears then writes the row (#48).
- Pure helpers (mode→controls, badge state, roster ranking) with unit tests; Tk surface + workbook overwrite
  with real-Tk / openpyxl tests.

### Out of Scope
- Keyboard-first focus/shortcuts (#42/#43 — landed separately).
- Pan/zoom image viewer and field↔layout-region linking (#47 — separate, larger change).
- Mid-review progress persistence / resume across app restarts (#37).
- Changes to recognition, `service_record.v1`, the duplicate-key rules, or validation blockers (beyond the
  opt-in overwrite path).
- Continuous capture (#38 follow-ups).

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `src/ocr_from2xlsx/review_workflow.py` | Yes (new) | Pure helpers: which toolbar controls show per mode; per-record badge state from `written_indices` + last result; roster-candidate ranking for a name. No Tk. |
| `src/ocr_from2xlsx/app.py` (`ReviewApp`) | Yes | Toolbar split into Scan/Correction modes + a mode toggle wired to session state (#44); persistent progress label + row indicator + per-record badge (#45); name-crop zoom panel + roster candidate list bound to the name field (#46); re-open + overwrite flow with confirmation, tracking record-index → written row (#48). |
| `src/ocr_from2xlsx/workbook.py` (`WorkbookWriter`) | Yes | `write_record(record, row=None)` — when `row` is given, clear that row's basic + service cells and write in place instead of `_next_empty_row()`; expose nothing else new. |
| `src/ocr_from2xlsx/session.py` (`ImportSession`) | Yes (small) | `accept_scan(..., overwrite_row=None)` threads a target row to the writer and reports the overwritten row; duplicate-key bookkeeping treats an overwrite as replacing the prior key, not adding a new one. |
| `name_suggestion` / `name_roster` / `correction_store` | No (reuse) | Roster candidates via `roster_from_store` + `roster_match`; `confirm_name` unchanged. |
| Recognition / `service_record.v1` / validation | No | Reused unchanged. |

## Architecture Considerations

Follows the repo's "pure decision logic + thin UI wrappers" pattern. Mode→controls, badge-state, and
roster-ranking are pure functions (no Tk), unit-tested like `review_nav`/`flagged_fields`. The workbook
overwrite reuses the existing `_set` / `_write_services` machinery with a row-targeted entry point and a
row-clear step, tested directly against openpyxl fixtures (as `test_workbook` already does). The app tracks
`record_index → written_row` alongside `written_indices` so a re-opened record knows its row; the overwrite is
explicit and confirmed, leaving the default append-and-advance flow and all validation blockers unchanged.
Name-crop display reuses the existing preview-image scaling; the roster list reuses `roster_from_store`.

## Success Criteria

- [ ] Correction mode shows only navigation + write + progress; scan-station controls are hidden until Scan
  mode — verified mis-click controls are not reachable during correction (#44).
- [ ] The UI persistently shows 已寫入 X / 共 N + current row, and each record shows 已寫入 / 待處理 / 被擋下;
  navigating back to a written record shows its 已寫入 badge and row (#45).
- [ ] The name crop is shown zoomed (full image fallback) and roster candidates are selectable; picking one
  fills the name and clears `name.unconfirmed` (#46).
- [ ] A written record can be re-opened and re-written to its original row after a "將覆寫第 N 列" confirm,
  producing no duplicate row and replacing the prior values (#48).
- [ ] Pure helpers (mode→controls, badge state, roster ranking) and the workbook row-overwrite have unit /
  openpyxl tests; app wiring has real-Tk / headless-fake tests; `python -W error -m pytest -q` and
  `python -m policy_check --repo .` green; CHANGELOG + `record-confirmation` base spec synced on archive.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Row-targeted overwrite leaves stale service cells from the prior write | Med | High | Clear the full row (basic + all service columns) before re-writing; openpyxl test asserts no stale cell remains. |
| Overwrite corrupts duplicate-key bookkeeping (re-adds / double-counts) | Med | Med | On overwrite, remove the prior row's key before re-adding the new one; test re-confirm with changed/unchanged key. |
| Mode toggle hides a control the operator still needs mid-task | Low | Med | Mode is driven by session state with an explicit toggle; both modes keep 確認並寫入/強制寫入 reachable where it matters; documented. |
| Name crop path missing / unreadable | Med | Low | Fall back to the full source image (existing behavior) when `name_crop` is absent or unreadable. |
| Per-record badge drifts from actual workbook state after overwrite | Low | Med | Badge derived from `written_indices` + last result in one pure helper; updated on every write/overwrite; unit-tested. |
