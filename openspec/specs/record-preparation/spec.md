# record-preparation Specification

## Purpose
Define the PDF record-preparation flow that converts fixed-layout service-record PDFs into normalized `Batch`/`Record` JSON for the existing validation and workbook import pipeline.
## Requirements
### Requirement: Prepare normalized records from fixed-layout PDF inputs
The system SHALL accept a fixed-layout service-record PDF page and produce a normalized `Batch` JSON payload in which each supported page maps to exactly one `Record`.

#### Scenario: Single-page PDF becomes one normalized record
- **WHEN** the user runs the record-preparation flow on a one-page service-record PDF
- **THEN** the system emits a `Batch` JSON document containing one normalized `Record` for that page

### Requirement: Preserve source provenance for prepared records
The system SHALL preserve enough source metadata in each prepared record to identify where the normalized output came from, including the input kind and the originating document location.

#### Scenario: PDF provenance is retained
- **WHEN** a normalized record is prepared from a PDF page
- **THEN** the record includes the source kind, source document path, and source page number in its optional source metadata

### Requirement: Preserve OCR metadata for review and debugging
The system SHALL retain OCR metadata in the normalized output, including backend identity, raw OCR text, confidence information, and warnings when available.

#### Scenario: OCR warnings are surfaced with normalized output
- **WHEN** the OCR backend reports low confidence or ambiguous field detection
- **THEN** the normalized record includes that warning information in its OCR metadata without changing the workbook-facing field contract

### Requirement: Emit a privacy-minimized handwritten-name crop
The system SHALL emit a cropped image containing only the handwritten name line from the fixed-layout form and SHALL exclude the medical-record-no digit line and the diagnosis-date line. The preparation flow SHALL make that crop discoverable to downstream handwritten-name suggestion logic, either by recording the crop path in OCR metadata or by following the stable sibling naming convention derived from the prepared page image.

#### Scenario: Name crop excludes the medical-record-no
- **WHEN** the form's 姓名/病歷號 region contains a handwritten name on its line and the medical-record-no on a different line
- **THEN** the emitted name crop covers only the name line, excludes the medical-record-no digits, and remains discoverable to the downstream suggestion flow

### Requirement: Support optional handwritten-name suggestions with local roster reuse
The system SHALL support an optional handwritten-name suggestion pass that can reuse previously confirmed local names and, when configured, call a cloud name agent using only the privacy-minimized name crop. When the agent is absent, disabled, unreachable, errors, or no crop is available, the preparation flow SHALL behave as a no-op and leave the existing normalized output unchanged.

#### Scenario: Enabled suggestion pass populates an unconfirmed name
- **WHEN** a handwritten-name agent is configured and enabled, a discoverable name crop is available, and a local roster or agent suggestion yields a candidate
- **THEN** the prepared record's name is populated with that candidate and marked for human confirmation

#### Scenario: Absent or disabled suggestion pass does not affect the pipeline
- **WHEN** no handwritten-name agent is configured, the configuration is disabled, or no discoverable crop is available
- **THEN** the pipeline produces the same normalized record it would have without the suggestion pass and raises no error

### Requirement: Keep machine-produced names unconfirmed until a human review
The system SHALL mark machine-produced or roster-recommended names with `name.unconfirmed` and SHALL NOT allow direct import of those names until a human explicitly confirms them in the review workflow or by an equivalent explicit confirmation step.

#### Scenario: Direct import blocks an unconfirmed machine-produced name
- **WHEN** an `import-json` attempt reaches a record whose name still carries `name.unconfirmed`
- **THEN** the write is blocked until a human confirms the name

#### Scenario: Review confirmation clears the unconfirmed flag
- **WHEN** a human accepts or corrects a record in the review workflow
- **THEN** the record is written without the `name.unconfirmed` warning

### Requirement: Record confirmed names for future local reuse
The system SHALL append each human confirmation or correction of a previously unconfirmed name to a local JSONL correction store adjacent to the prepared JSON, capturing enough provenance for future roster reuse, and SHALL load confirmed names from that store as the local roster for future suggestion passes.

#### Scenario: Review confirmation updates the correction store
- **WHEN** a human confirms or corrects an unconfirmed handwritten-name suggestion in the review workflow
- **THEN** a correction entry is appended to the local store and the confirmed value becomes available to future roster-based suggestions

### Requirement: Support replaceable OCR backends behind a stable preparation interface
The system SHALL expose a preparation pipeline that can switch OCR backends without changing the normalized JSON contract consumed by downstream commands.

#### Scenario: Backend substitution does not change downstream contract
- **WHEN** the configured OCR backend is replaced with another supported backend
- **THEN** the preparation flow still emits the same normalized `Batch`/`Record` structure expected by validation and import commands

### Requirement: Produce outputs that are directly consumable by the existing validation and import workflow
The system SHALL emit prepared records in the same normalized schema used by `validate-json` and `import-json`, so the existing downstream workflow can run without a format conversion step.

#### Scenario: Prepared JSON feeds the existing import pipeline
- **WHEN** record preparation completes successfully
- **THEN** the resulting JSON can be passed directly to the existing validation and workbook import commands

### Requirement: Support designated gold fixtures for regression verification
The system SHALL support manually curated normalized gold fixtures for designated reference documents so preprocessing and normalization regressions can be detected before workbook import.

#### Scenario: Reference PDF is checked against approved gold output
- **WHEN** the designated reference PDF fixture is processed in tests
- **THEN** the produced normalized output is compared against the approved gold JSON fixture for regression verification
