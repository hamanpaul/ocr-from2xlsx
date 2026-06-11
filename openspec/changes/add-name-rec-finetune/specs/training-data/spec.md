# training-data Specification (Delta)

## ADDED

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
