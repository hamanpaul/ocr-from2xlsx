# form-layout Specification (Delta)

**Change ID:** `add-form-layout-model`
**Affects:** new shared form-layout model consumed by the confirmation UI and the training-data generator.

---

## ADDED

### Requirement: Provide a structured, render-agnostic model of the service-record form

The system SHALL provide a structured model of the service-record form organized as sections, fields, and
options, where each field declares a kind (text, single-choice, or multi-choice) and each choice option
declares its display label, a canonical code, and the source cell reference. The model SHALL NOT include
pixel geometry.

#### Scenario: Model exposes sections, fields, and options
- **WHEN** a consumer loads the service-record form layout
- **THEN** it receives sections (A/B/C and the top), each field's kind, and for choice fields the options with label, code, and cell reference

#### Scenario: Codes reuse the existing canonical code set
- **WHEN** the layout assigns a code to an option
- **THEN** that code is one already defined in the project's canonical code set, not a new parallel code

### Requirement: Map every field to its workflow Record position

The system SHALL declare, for each field, the path of the corresponding value in the normalized
`service_record.v1` Record (for example identity, gender, `patient_fields.age_group`,
`services.consultation.health_medical`, `patient_fields.cancers`), or mark the path absent when the form
field has no Record counterpart.

#### Scenario: Marked options assemble into a valid Record
- **WHEN** a consumer has the set of selected option codes for a form
- **THEN** the field record-paths let it place each code at the correct position in a `service_record.v1` Record

#### Scenario: Form-only field has no Record path
- **WHEN** a form field has no counterpart in the workflow Record (for example the diagnosis date)
- **THEN** its record-path is marked absent and it is not written into the Record

### Requirement: Validate the model against the real form sheet

The system SHALL verify the model against the real blank `服務紀錄表` sheet with two-way coverage: every
modeled option matches the label at its declared cell, and every checkbox option present on the sheet is
represented in the model.

#### Scenario: Model and sheet agree
- **WHEN** the layout-validation check runs against the blank service-record sheet
- **THEN** each modeled option's cell contains its label and every sheet checkbox option is present in the model, otherwise the check fails

### Requirement: Enable a workflow-aligned training answer key

The model SHALL provide enough structure (codes and record-paths) for a training answer key to be expressed
in the same `service_record.v1` format as the workflow output, augmented only with a training marker and a
source-image reference, so the answer key aligns field-by-field with OCR output.

#### Scenario: Answer key aligns with OCR output
- **WHEN** a training answer key is produced for a synthetic form using this model
- **THEN** it is a `service_record.v1` record plus a training marker and a source-image reference, comparable field-by-field to the OCR pipeline's output for the same image
