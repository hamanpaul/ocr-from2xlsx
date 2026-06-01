# training-data Specification (Delta)

## ADDED

### Requirement: Evaluate synthetic checkbox marks without OCR text recognition

The system SHALL evaluate synthetic checkbox mark detection by reading a generated answer key, resolving
each record's source image relative to the answer key, reconstructing option checkbox boxes from the
workbook geometry, running mark detection on those boxes, and reporting aggregate plus per-field
precision/recall/F1.

#### Scenario: Mark-blinded evaluation writes reports
- **WHEN** the evaluator processes `answers.json` and the blank workbook geometry
- **THEN** it writes `report.json` and `report.md` containing sample count, aggregate mark metrics,
  per-field mark metrics, and per-sample gold/predicted mark sets without invoking the OCR plugin

### Requirement: Evaluate the synthetic OCR pipeline diagnostically

The system SHALL provide a diagnostic synthetic pipeline evaluator that runs the OCR plugin on generated
source images, compares predicted records with the answer key using the shared form layout, and reports
scalar accuracy plus multi-choice precision/recall/F1.

#### Scenario: Pipeline evaluation writes diagnostic reports
- **WHEN** the pipeline evaluator processes `answers.json` with an explicit OCR plugin directory
- **THEN** it writes `report.json` and `report.md` with diagnostic record-comparison metrics and
  per-sample field mismatches
