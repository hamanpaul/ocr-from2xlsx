# record-confirmation Specification (Delta)

**Change ID:** `improve-review-keyboard-flow`
**Affects:** the human confirmation UI (`ReviewApp`, `ConfirmForm`) and its pure navigation helpers

## ADDED

### Requirement: Drive the whole review loop from the keyboard

The system SHALL provide keyboard shortcuts, active regardless of which field currently has focus, for
the core review actions — confirm-and-write, force-write, next record, previous record, and cancel the
current edit — each invoking the same behavior as its existing toolbar action, so a reviewer can process
a record without using the mouse.

#### Scenario: Confirm shortcut writes and advances
- **WHEN** the reviewer presses the confirm shortcut on a record with no blocking errors
- **THEN** the record is written as human-confirmed and the next record is shown, identically to pressing
  「確認並寫入」

#### Scenario: Next / previous shortcuts navigate records
- **WHEN** the reviewer presses the next-record or previous-record shortcut
- **THEN** the form moves to the next or previous record, identically to 「下一筆」/「上一筆」 (including
  the existing guard that blocks navigation while the current record has unsaved edits)

#### Scenario: Force-write shortcut is available
- **WHEN** the reviewer presses the force-write shortcut
- **THEN** the record is force-written, identically to 「強制寫入」

#### Scenario: Cancel-edit shortcut discards in-progress edits
- **WHEN** the reviewer presses the cancel-edit shortcut after changing fields on the current record
- **THEN** the current record is re-shown from its stored values and the unsaved-edit state is cleared,
  so navigation is no longer blocked

### Requirement: Open each record at the first field needing attention

When a record is opened for review, the system SHALL move keyboard focus to the first field needing
attention — the first flagged (`⚠`) field in layout order, or the first editable field when none are
flagged — scroll that field into view, visually de-emphasize the high-confidence (unflagged) fields so
the flagged fields stand out, and show how many fields on the current record still need confirmation.

#### Scenario: First flagged field is focused and scrolled into view
- **WHEN** a record with one or more flagged fields is opened
- **THEN** keyboard focus moves to the first flagged field in layout order and that field is scrolled
  into view

#### Scenario: No flagged fields focuses the first editable field
- **WHEN** a record with no flagged fields is opened
- **THEN** keyboard focus moves to the first editable field and no field is marked as needing attention

#### Scenario: High-confidence fields are de-emphasized
- **WHEN** a record is shown with its flagged fields marked
- **THEN** the unflagged (high-confidence) fields are visually de-emphasized while the flagged fields
  keep their `⚠` highlight

#### Scenario: Count of fields needing confirmation is shown
- **WHEN** a record is shown
- **THEN** the number of flagged fields on the current record is displayed to the reviewer

### Requirement: Jump between only the fields needing attention

The system SHALL provide a keyboard "next field needing attention" action that moves focus through only
the flagged fields, in layout order, wrapping from the last flagged field back to the first, and skipping
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

The system SHALL let the reviewer set field values from the keyboard: while a single-choice field has
focus, a number key (1–N over that field's options) selects the matching option and clears the others;
while a multi-choice option has focus, the spacebar toggles it; and digits typed into a text field are
entered as text and never consumed as option selection.

#### Scenario: Number key selects a single-choice option
- **WHEN** a single-choice field has focus and the reviewer presses a number key within the field's
  option count
- **THEN** the matching option becomes selected and the other options of that field are cleared

#### Scenario: Spacebar toggles a focused multi-choice option
- **WHEN** a multi-choice option has focus and the reviewer presses the spacebar
- **THEN** that option toggles between selected and unselected

#### Scenario: Digits in a text field stay text
- **WHEN** a text field has focus and the reviewer types a digit
- **THEN** the digit is entered into the text field and no option selection is triggered
