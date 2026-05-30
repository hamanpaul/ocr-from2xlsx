# record-preparation Specification (Delta)

**Change ID:** `fix-core-field-recognition`
**Affects:** OCR plugin field extraction (`plugins/paddleocr/`), validation/import verification path.

---

## ADDED

### Requirement: Recognize checkbox-selected identity and gender from the form

The system SHALL determine the selected `identity` (病人 / 親友及照顧者 / 一般民眾及其他) and `gender`
(女性 / 男性 / 其他) by locating each option label from OCR output and detecting whether its checkbox is
marked, deriving box positions from runtime OCR positions rather than hard-coded coordinates.

#### Scenario: Marked identity and gender are recognized
- **WHEN** the reference filled form is processed and 病人 and 女性 are ticked
- **THEN** the prepared record has `identity = patient` and `gender = female`

#### Scenario: Unmarked options are not selected
- **WHEN** an option's checkbox shows no mark
- **THEN** that option's code is not assigned to its field

### Requirement: Detect a checkbox mark by checkbox-region ink with an OCR-anomaly secondary signal

The system SHALL decide whether a checkbox is marked primarily by measuring ink density in the checkbox
region adjacent to the option label, and MAY use OCR text anomalies (a checked box losing its `□` glyph,
or a tick read as `中`/`V`) as a secondary confirming signal.

#### Scenario: Filled checkbox region is detected as marked
- **WHEN** the checkbox region next to an option label contains ink above the marked threshold
- **THEN** that option is treated as marked

#### Scenario: Empty checkbox region is detected as unmarked
- **WHEN** the checkbox region next to an option label is effectively empty
- **THEN** that option is treated as unmarked

### Requirement: Extract handwritten name and medical-record-no from the 姓名/病歷號 region

The system SHALL extract a handwritten `name` (a CJK character run) and `medical_record_no` (a long digit
run) from the OCR output around the 姓名/病歷號 anchor, while rejecting stray marks that are neither a CJK
name nor a digit-bearing record number.

#### Scenario: Reference handwriting is parsed
- **WHEN** the reference form's 姓名/病歷號 region yields handwriting for 葉心安 and 6250712919
- **THEN** the prepared record has `name = 葉心安` and `medical_record_no = 6250712919`

#### Scenario: Stray marks are not treated as name or record number
- **WHEN** the only text near the anchor is a stray mark such as `V`
- **THEN** `name` and `medical_record_no` remain empty rather than capturing the stray mark

### Requirement: Provide a non-blocking verification path for recognized records

The system SHALL provide a non-blocking path that emits or writes the recognized fields even when some
required fields are missing, recording the missing fields as warnings rather than blockers, so recognition
results can be verified against the source image. The default blocking behavior SHALL remain unchanged.

#### Scenario: Incomplete-but-recognized record is emitted for verification
- **WHEN** a record is processed through the non-blocking verification path with some required fields missing
- **THEN** the recognized fields are written out and the missing fields are reported as warnings, not blockers

#### Scenario: Default behavior still blocks
- **WHEN** a record with missing required fields is processed through the default path
- **THEN** it is blocked as before and not written

### Requirement: Verify core-field recognition against a designated ground-truth form

The system SHALL maintain a ground-truth expectation for the designated reference form covering the core
fields (`service_date`, `identity`, `name`, `medical_record_no`, `gender`), and SHALL provide a regression
check that the plugin's recognition of that form matches the ground truth.

#### Scenario: Reference form matches the ground truth
- **WHEN** the designated reference form is recognized by the PaddleOCR plugin
- **THEN** the produced core fields equal the approved ground-truth values
