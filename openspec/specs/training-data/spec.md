# training-data Specification

## Purpose

Define the dev-only `training/` tool that synthesizes labeled service-record images from the blank
workbook and emits workflow-aligned answer keys for OCR evaluation and training experiments.

## Requirements

### Requirement: Synthesize service-record images from the form layout

The system SHALL synthesize service-record form images using the shared form-layout model, drawing a
blank base form with handwritten text in the text fields and handwritten marks in the option
checkboxes, with the option/field positions derived from the layout so the ground-truth location of
each mark is known.

#### Scenario: A synthetic form is produced with known mark positions
- **WHEN** the generator produces an image
- **THEN** the image shows the form with marks placed in option checkboxes at positions derived from the
  layout

### Requirement: Emit a workflow-aligned answer key per image

The system SHALL emit an answer key in the same `service_record.v1` format as the workflow output,
where each record faithfully records what was filled on its image and additionally carries a training
marker and a reference to its source image, so the answer key aligns field-by-field with OCR output.

#### Scenario: Answer key matches the workflow schema
- **WHEN** an image is generated
- **THEN** its answer-key record is a `service_record.v1` record (built from the selected option codes
  via the shared form helpers) plus a training marker and a source-image reference

### Requirement: Produce varied handwritten checkbox marks

The system SHALL render checkbox marks in varied handwritten styles, including a tick, a dash, and a
partial blackout, with variation in stroke, size, and position.

#### Scenario: Marks vary in style
- **WHEN** options are marked across the generated set
- **THEN** the marks include tick, dash, and partial-blackout styles rather than a single fixed glyph

### Requirement: Enforce per-image selection ratio and batch coverage

The system SHALL select, per image, between 10% and 50% of the form's options to mark with at least
one option marked, respecting single-choice (at most one) and multi-choice (a non-empty subset)
semantics; and across the generated batch it SHALL ensure every option is marked at least five times.

#### Scenario: Per-image selection respects the ratio and field kinds
- **WHEN** an image's marked options are chosen
- **THEN** the marked options are 10–50% of all options with at least one, single-choice fields have at
  most one mark, and multi-choice fields have a non-empty subset

#### Scenario: Batch covers every option at least five times
- **WHEN** the batch is generated to completion
- **THEN** every option has been marked at least five times across the images

### Requirement: Use only open-license handwriting fonts, fetched locally, with offline generation

The system SHALL obtain handwriting fonts only under an open license via a setup step that stores them
locally with their sources and licenses recorded, SHALL generate images offline using the local fonts,
and SHALL fall back to system printed fonts when no suitable handwriting font is available for the
requested text.

#### Scenario: Generation runs offline with local fonts
- **WHEN** images are generated after fonts have been fetched
- **THEN** generation uses the local fonts without network access, and uses system printed fonts if no
  suitable handwriting font is present

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

### Requirement: Train and deploy a lightweight checkbox mark classifier

The system SHALL provide plugin-safe mark feature extraction, pure JSON mark-model scoring, geometry
crop providers, and offline training tools so checkbox crops can be classified without adding runtime
dependencies beyond the plugin bundle.

#### Scenario: Geometry classifier assets are available
- **WHEN** the PaddleOCR plugin can resolve template boxes from `MARK_TEMPLATE_BOXES` or bundled
  `template_boxes.json`
- **THEN** it classifies geometry crops and maps supported identity/gender option crops to the existing
  OCR mark labels consumed by field extraction

#### Scenario: Geometry classifier assets are unavailable
- **WHEN** no template box asset is available
- **THEN** the PaddleOCR plugin preserves the existing OCR-label mark detection fallback

### Requirement: Harvest confirmed crops and train precision-safe weights

The system SHALL harvest labeled checkbox crops from confirmed records, store them in a JSONL manifest
with crop PNGs, train a deterministic lightweight linear model, and export a pure JSON `mark_model.json`
with a precision-safe threshold selected by operating-point evaluation.

#### Scenario: Correction harvest writes a dataset row per template box
- **WHEN** a confirmed record and aligned image are harvested with geometry template boxes
- **THEN** the dataset receives one crop and manifest row per template box, with labels derived from the
  confirmed record's selected option codes

#### Scenario: Unsafe candidate thresholds are rejected or represented safely
- **WHEN** no threshold can satisfy the requested minimum precision
- **THEN** training exports a reject-all threshold above all observed probabilities so runtime
  classification cannot create false positives from that model

### Requirement: Generate synthetic handwritten-name recognition corpora

The system SHALL generate synthetic handwritten Chinese name crops with PaddleOCR rec format labels
(`path\tlabel`), sampling 2-4 character names from embedded common-surname and given-character pools,
rendered with handwriting fonts and reusing the existing augmentation, with fixed-seed train,
validation, and holdout batches where the holdout batch never enters training.

#### Scenario: Name corpus generation is reproducible
- **WHEN** `training.gen_names` runs twice with the same seed and parameters
- **THEN** it produces identical name/label sequences, and train, validation, and holdout batches are
  disjoint by construction

### Requirement: Finetune, gate, and deploy a name-only rec model

The system SHALL provide a repeatable CPU finetune wrapper over the official PaddleOCR trainer for
PP-OCRv5_mobile_rec, holdout evaluation (exact-match rate and character accuracy), and a gated deploy
that atomically replaces the user runtime name model directory only when exact-match improves and
character accuracy does not regress, appending every decision to an audit JSONL.

#### Scenario: Degraded name model candidates are rejected
- **WHEN** a candidate's holdout exact-match does not improve on the current model (or the mobile-rec
  baseline when no model is deployed), or its character accuracy regresses
- **THEN** the current runtime model directory is left untouched and the rejection reason is appended
  to the audit log

#### Scenario: Confirmed name corrections feed retraining
- **WHEN** `name_corrections.jsonl` entries with valid crop paths and confirmed values are harvested
- **THEN** they are converted into rec label rows usable by the next finetune run, and invalid or
  missing crops are skipped without aborting the harvest
