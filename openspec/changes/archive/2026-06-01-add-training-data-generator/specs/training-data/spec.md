# training-data Specification (Delta)

## ADDED

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
