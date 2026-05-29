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
