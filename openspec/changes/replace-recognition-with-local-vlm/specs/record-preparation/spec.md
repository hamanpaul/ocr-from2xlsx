# record-preparation Specification (Delta)

**Change ID:** `replace-recognition-with-local-vlm`
**Affects:** recognition backend (`src/`), OCR plugin wiring (`plugins/paddleocr/`), review UI (`confirm_form`), packaging (`build/`, `dist/`).

---

## ADDED

### Requirement: Pre-fill the full service record from a fully-local Vision-LLM

The system SHALL provide a recognition backend that reads a captured service-record image with a
fully-local Vision-LLM and pre-fills the **complete** `service_record.v1` — checkbox-selected fields
(identity, gender, nationality, age group, channel, disease status, source, cancers, and Section A
services) and handwritten dates and numbers — without sending any image data off the machine. The
backend SHALL read **wide proportional section tiles**, each accompanied by that section's known
option list, and SHALL NOT depend on per-checkbox geometric registration.

#### Scenario: Reference form is pre-filled across the whole form
- **WHEN** the designated reference form is recognized by the local Vision-LLM backend
- **THEN** the prepared `service_record.v1` has the marked checkboxes resolved to their codes and the handwritten dates/numbers populated, each verifiable against the image

#### Scenario: No image data leaves the machine
- **WHEN** a service-record image is recognized
- **THEN** recognition runs entirely on the local machine with no network call carrying image data

### Requirement: Read name and medical-record-no locally and keep them unconfirmed

The system SHALL read the handwritten `name` (a CJK run) and `medical_record_no` (a digit run) from
the name/medical-record-no region using the local model, snapping the name to the local roster when a
candidate matches, while preserving the existing `name.unconfirmed` flow until a human confirms.

#### Scenario: Reference handwriting is read locally
- **WHEN** the reference form's name/病歷號 region is recognized
- **THEN** `name` and `medical_record_no` are populated locally and `name` remains `name.unconfirmed` until human confirmation

### Requirement: Flag low-confidence and unfilled recognized fields for verification

The system SHALL mark recognized fields that are unfilled or low-confidence (for example: empty, no
roster match, or an abnormal digit length) so the review UI can direct the human to verify them
first. Recognition is a pre-fill: the final accepted record is produced by human confirmation.

#### Scenario: Low-confidence field is surfaced in review
- **WHEN** a recognized field is unfilled or below the confidence threshold
- **THEN** the review UI marks that field visibly distinct so the human verifies it before acceptance

### Requirement: Resolve a portable local model runtime with graceful degradation

The system SHALL resolve a portable local Vision-LLM runtime and weights (resolution order: explicit
config/env override, user runtime directory, then the bundled default), and SHALL degrade to the
existing manual review/import flow without error when the runtime or weights are unavailable. The
model weights SHALL NOT be committed to the repository.

#### Scenario: Runtime or weights absent
- **WHEN** the local model runtime or weights cannot be resolved
- **THEN** the app keeps the existing preview, review, and JSON import flow without error and without a pre-fill

---

## MODIFIED

### Requirement: Recognize a captured image through the configured recognition backend into a form-fillable record

The system SHALL accept a still image (webcam capture or file), run it through the **configured
recognition backend**, and produce a normalized `service_record.v1` record consistent with the
existing import flow, both from an in-app "capture & recognize" action and a CLI path. When the
configured backend is the local Vision-LLM, the produced record SHALL cover the full form (checkboxes
and handwritten dates/numbers), populated as pre-fill suggestions. The flow SHALL degrade gracefully
when no camera is available, the frame is rejected, or recognition is unavailable.

#### Scenario: A good capture pre-fills the review form
- **WHEN** a sufficiently sharp image of a service-record form is captured and recognized by the configured backend
- **THEN** a `service_record.v1` record is produced and its recognized fields populate the review form as suggestions (names remain `name.unconfirmed` until human confirmation)

#### Scenario: No camera or recognition failure preserves the existing flow
- **WHEN** no camera is available, the frame is rejected by the sharpness gate, or recognition fails/unavailable
- **THEN** the app keeps the existing preview and JSON import flow without error

---

## REMOVED

(None from the published `record-preparation` source-of-truth spec. The unmerged Draft change
`fix-core-field-recognition` — text-anchor + ink-probe field extraction — is superseded by this
change and SHALL NOT be archived.)
