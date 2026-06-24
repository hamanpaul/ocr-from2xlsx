# record-confirmation Specification (Delta)

**Change ID:** `improve-review-workflow`
**Affects:** the human confirmation UI (`ReviewApp`), the workbook write path (`WorkbookWriter`,
`ImportSession`), and pure review-workflow helpers

## ADDED

### Requirement: Separate scan and correction into switchable modes

The system SHALL present scan-station actions and correction actions as two switchable modes. In the
correction mode it SHALL show only the correction controls — previous record, next record, confirm-and-write,
force-write, and progress — and hide the scan-station controls (capture-and-recognize, folder batch import,
camera selection, rotate, zoom). The active mode SHALL follow the session state.

#### Scenario: Correction mode hides scan-station controls
- **WHEN** the app is in correction mode
- **THEN** only the navigation, confirm-and-write, force-write, and progress controls are shown, and the
  scan-station controls are not reachable

#### Scenario: Scan mode shows the capture controls
- **WHEN** the app is switched to scan/capture mode
- **THEN** the scan-station controls (capture-and-recognize, folder batch import, camera selection, rotate,
  zoom) are shown

### Requirement: Show persistent batch progress and per-record write status

The system SHALL persistently show the batch progress as written-count over total (已寫入 X / 共 N) together
with the current record's workbook row, and SHALL show a per-record status badge — written, pending, or
blocked — so that navigating to any record reveals whether it has already been written.

#### Scenario: Progress and current row are always visible
- **WHEN** records are loaded and one is shown
- **THEN** the UI shows how many records have been written out of the total and the current record's row

#### Scenario: A written record shows its written badge on revisit
- **WHEN** the reviewer navigates back to a record that was already written
- **THEN** that record shows a "written" status badge and its workbook row, distinct from a pending or
  blocked record

### Requirement: Aid handwritten-name correction with a name crop and roster candidates

The system SHALL show a zoomed view of the record's name crop when one is available
(`record.ocr.name_crop`), falling back to the full source image when it is absent or unreadable, and SHALL
present roster candidates (from the confirmed-name correction store) as selectable suggestions for the name
field. Selecting a candidate SHALL fill the name and clear the unconfirmed-name marker.

#### Scenario: Name crop is shown zoomed with a full-image fallback
- **WHEN** a record with a name crop is opened
- **THEN** the name crop is shown zoomed; **AND WHEN** no name crop is available **THEN** the full source
  image is shown instead

#### Scenario: Selecting a roster candidate fills and confirms the name
- **WHEN** the reviewer selects a roster candidate for the name
- **THEN** the name field is filled with that candidate and the unconfirmed-name marker is cleared

### Requirement: Re-open a written record and overwrite its workbook row

The system SHALL allow re-opening an already-written record and re-writing it to its original workbook row,
rather than appending a new row, after a confirmation that names the row to be overwritten. The overwrite
SHALL replace the prior row's values (leaving no stale cells) and SHALL keep the written-record bookkeeping
and duplicate-key tracking consistent. Cancelling the confirmation SHALL write nothing.

#### Scenario: Overwrite replaces the original row without duplicating
- **WHEN** the reviewer re-opens an already-written record, edits it, and confirms the overwrite of its row
- **THEN** the record is re-written to its original workbook row with the prior values replaced and no
  duplicate row is created

#### Scenario: Overwrite is confirmed before writing
- **WHEN** the reviewer triggers a write on an already-written record
- **THEN** a confirmation naming the row to be overwritten is shown, and the row is overwritten only if the
  reviewer confirms; cancelling writes nothing
