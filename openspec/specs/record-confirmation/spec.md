# record-confirmation Specification

## Purpose
Define the human confirmation UI and its pure record access / form-state helpers so a reviewer can edit the
entire service record on one page, compare it with the source image when available, and write it as
human-confirmed in one action.

## Requirements

### Requirement: Present all record fields on one editable page from the form layout
The system SHALL present, on a single page, every field of the service record — text fields, single-choice
fields, and multi-choice fields — generated from the shared form-layout model and grouped by its sections,
pre-filled from the record and directly editable, without requiring field-by-field confirmation.

#### Scenario: Whole record shown and editable at once
- **WHEN** a prepared record is opened for review
- **THEN** all of its fields appear on one page with controls matching each field's kind, pre-filled from the
  record, and the user can edit any of them directly

#### Scenario: Form is driven by the layout
- **WHEN** the form-layout model defines the fields and options
- **THEN** the page is generated from that model rather than from hard-coded field widgets

### Requirement: Read and write the record by its layout record-path
The system SHALL read and write record values addressed by the layout's record-path, including nested paths
(patient fields and service categories), multi-choice list values, and boolean fields, and SHALL not write
fields whose record-path is absent.

#### Scenario: Nested and multi-choice values round-trip
- **WHEN** the page state is applied back to the record
- **THEN** single-choice, multi-choice (list), boolean, and nested patient/service values are written to their
  correct record positions, and a form-only field with no record-path is not written

### Requirement: Confirm the whole page in one action and write as human-confirmed
The system SHALL provide a single confirm action that applies the entire page to the record and writes it as
human-confirmed, clearing the unconfirmed-name marker and persisting the confirmed name, then advances to the
next record. A force-write path SHALL remain for incomplete records.

#### Scenario: One-click confirm writes the record
- **WHEN** the user confirms the page
- **THEN** the edited record is written to the workbook as human-confirmed, the unconfirmed-name marker is
  cleared, the name correction is recorded, and the next record is shown

#### Scenario: Blocking error keeps the page
- **WHEN** confirming a record that still has a blocking error
- **THEN** the error is shown and the record is not advanced, while a force-write remains available

### Requirement: Show the source image beside the form when available
The system SHALL show the record's source page image beside the editable form when such an image is available,
and SHALL show the form alone when it is not (for example webcam input), without affecting the confirm flow.

#### Scenario: Image-based record shows a comparison image
- **WHEN** the record has an available source page image
- **THEN** that image is shown beside the form for comparison

#### Scenario: Webcam record shows the form alone
- **WHEN** the record has no available source page image
- **THEN** only the editable form is shown and confirming still works

### Requirement: Drive the whole review loop from the keyboard
The system SHALL provide keyboard shortcuts, active regardless of which field currently has focus, for the
core review actions — confirm-and-write, force-write, next record, previous record, and cancel the current
edit — each invoking the same behavior as its existing toolbar action, so a reviewer can process a record
without using the mouse.

#### Scenario: Confirm shortcut writes and advances
- **WHEN** the reviewer presses the confirm shortcut on a record with no blocking errors
- **THEN** the record is written as human-confirmed and the next record is shown, identically to pressing
  「確認並寫入」

#### Scenario: Next / previous shortcuts navigate records
- **WHEN** the reviewer presses the next-record or previous-record shortcut
- **THEN** the form moves to the next or previous record, identically to 「下一筆」/「上一筆」 (including the
  existing guard that blocks navigation while the current record has unsaved edits)

#### Scenario: Force-write shortcut is available
- **WHEN** the reviewer presses the force-write shortcut
- **THEN** the record is force-written, identically to 「強制寫入」

#### Scenario: Cancel-edit shortcut discards in-progress edits
- **WHEN** the reviewer presses the cancel-edit shortcut after changing fields on the current record
- **THEN** the current record is re-shown from its stored values and the unsaved-edit state is cleared, so
  navigation is no longer blocked

### Requirement: Open each record at the first field needing attention
When a record is opened for review, the system SHALL move keyboard focus to the first field needing attention
— the first flagged (`⚠`) field in layout order, or the first editable field when none are flagged — scroll
that field into view, visually de-emphasize the high-confidence (unflagged) fields so the flagged fields stand
out, and show how many fields on the current record still need confirmation.

#### Scenario: First flagged field is focused and scrolled into view
- **WHEN** a record with one or more flagged fields is opened
- **THEN** keyboard focus moves to the first flagged field in layout order and that field is scrolled into
  view

#### Scenario: No flagged fields focuses the first editable field
- **WHEN** a record with no flagged fields is opened
- **THEN** keyboard focus moves to the first editable field and no field is marked as needing attention

#### Scenario: High-confidence fields are de-emphasized
- **WHEN** a record is shown with its flagged fields marked
- **THEN** the unflagged (high-confidence) fields are visually de-emphasized while the flagged fields keep
  their `⚠` highlight

#### Scenario: Count of fields needing confirmation is shown
- **WHEN** a record is shown
- **THEN** the number of flagged fields on the current record is displayed to the reviewer

### Requirement: Jump between only the fields needing attention
The system SHALL provide a keyboard "next field needing attention" action that moves focus through only the
flagged fields, in layout order, wrapping from the last flagged field back to the first, and skipping
high-confidence fields entirely.

#### Scenario: Next-flagged cycles only flagged fields
- **WHEN** the reviewer triggers the next-field-needing-attention action
- **THEN** focus moves to the next flagged field in layout order, skipping any unflagged fields in between

#### Scenario: Next-flagged wraps around
- **WHEN** the reviewer triggers the action while focused on the last flagged field
- **THEN** focus wraps to the first flagged field

#### Scenario: No flagged fields makes the action a no-op
- **WHEN** the reviewer triggers the action on a record with no flagged fields
- **THEN** focus does not move and nothing is changed

### Requirement: Select field options from the keyboard
The system SHALL let the reviewer set field values from the keyboard: while a single-choice field has focus, a
number key (1–N over that field's options) selects the matching option and clears the others; while a
multi-choice option has focus, the spacebar toggles it; and digits typed into a text field are entered as text
and never consumed as option selection.

#### Scenario: Number key selects a single-choice option
- **WHEN** a single-choice field has focus and the reviewer presses a number key within the field's option
  count
- **THEN** the matching option becomes selected and the other options of that field are cleared

#### Scenario: Spacebar toggles a focused multi-choice option
- **WHEN** a multi-choice option has focus and the reviewer presses the spacebar
- **THEN** that option toggles between selected and unselected

#### Scenario: Digits in a text field stay text
- **WHEN** a text field has focus and the reviewer types a digit
- **THEN** the digit is entered into the text field and no option selection is triggered

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

### Requirement: Pan and wheel-zoom the source image during review
The system SHALL present the record's source page in a viewer that supports dragging to pan and using the
mouse wheel to zoom about the cursor, and SHALL remember the zoom level for the session, replacing the
previous center-crop-only zoom. The live-camera preview and the no-image placeholder SHALL continue to render
correctly through the viewer (the live preview fit to the pane).

#### Scenario: Drag pans and wheel zooms the source image
- **WHEN** a record's source page is shown and the reviewer drags on it or scrolls the mouse wheel
- **THEN** the image pans with the drag and zooms about the cursor with the wheel, staying within bounds

#### Scenario: Zoom is remembered for the session
- **WHEN** the reviewer sets a zoom level and then moves to another record's source image
- **THEN** the viewer keeps that zoom level for the session rather than resetting to center-crop

#### Scenario: Live preview and placeholder still render
- **WHEN** the live camera is previewing, or no source image is available
- **THEN** the live frame renders fit to the pane and the placeholder shows, through the same viewer, without
  error

### Requirement: Frame the source image to a focused field's region
The system SHALL, when a field receives focus, frame (scroll/zoom) the source-image viewer to that field's
region — the field's section band from the recognition layout geometry — so the reviewer sees the relevant
area without hunting the whole page. A field with no known region or with no source image loaded SHALL leave
the view unchanged.

#### Scenario: Focusing a field frames its region
- **WHEN** a field with a known region is focused and a source image is loaded
- **THEN** the viewer frames that field's region (its section band)

#### Scenario: Unknown region leaves the view unchanged
- **WHEN** a focused field has no known region, or no source image is loaded
- **THEN** the viewer does not change its pan/zoom
