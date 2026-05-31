# record-confirmation Specification (Delta)

**Change ID:** `add-confirm-ui`
**Affects:** the human review/confirmation UI and the pure record path-access / form-state helpers it uses.

---

## ADDED

### Requirement: Present all record fields on one editable page from the form layout

The system SHALL present, on a single page, every field of the service record — text fields, single-choice
fields, and multi-choice fields — generated from the shared form-layout model and grouped by its sections,
pre-filled from the record and directly editable, without requiring field-by-field confirmation.

#### Scenario: Whole record shown and editable at once
- **WHEN** a prepared record is opened for review
- **THEN** all of its fields appear on one page with controls matching each field's kind, pre-filled from the record, and the user can edit any of them directly

#### Scenario: Form is driven by the layout
- **WHEN** the form-layout model defines the fields and options
- **THEN** the page is generated from that model rather than from hard-coded field widgets

### Requirement: Read and write the record by its layout record-path

The system SHALL read and write record values addressed by the layout's record-path, including nested paths
(patient fields and service categories), multi-choice list values, and boolean fields, and SHALL not write
fields whose record-path is absent.

#### Scenario: Nested and multi-choice values round-trip
- **WHEN** the page state is applied back to the record
- **THEN** single-choice, multi-choice (list), boolean, and nested patient/service values are written to their correct record positions, and a form-only field with no record-path is not written

### Requirement: Confirm the whole page in one action and write as human-confirmed

The system SHALL provide a single confirm action that applies the entire page to the record and writes it as
human-confirmed, clearing the unconfirmed-name marker and persisting the confirmed name, then advances to the
next record. A force-write path SHALL remain for incomplete records.

#### Scenario: One-click confirm writes the record
- **WHEN** the user confirms the page
- **THEN** the edited record is written to the workbook as human-confirmed, the unconfirmed-name marker is cleared, the name correction is recorded, and the next record is shown

#### Scenario: Blocking error keeps the page
- **WHEN** confirming a record that still has a blocking error
- **THEN** the error is shown and the record is not advanced, while a force-write remains available

### Requirement: Show the source image beside the form when available

The system SHALL show the record's source page image beside the editable form when such an image is
available, and SHALL show the form alone when it is not (for example webcam input), without affecting the
confirm flow.

#### Scenario: Image-based record shows a comparison image
- **WHEN** the record has an available source page image
- **THEN** that image is shown beside the form for comparison

#### Scenario: Webcam record shows the form alone
- **WHEN** the record has no available source page image
- **THEN** only the editable form is shown and confirming still works
