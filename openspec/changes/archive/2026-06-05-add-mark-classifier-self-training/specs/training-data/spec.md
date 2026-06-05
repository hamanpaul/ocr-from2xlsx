# training-data Specification (Delta)

## ADDED

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
