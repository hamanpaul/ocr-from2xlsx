# record-preparation Specification (Delta)

## ADDED

### Requirement: Register a captured form to the canonical template before checkbox classification

The system SHALL align a captured or scanned service-record image to the canonical template
coordinate space (the space `template_boxes.json` uses) by automatic feature-based homography against
a blank-form reference, falling back to a manual four-corner perspective warp when automatic
registration is not confident, so the geometric checkbox boxes land on the actual checkboxes.

#### Scenario: Confident automatic registration aligns the boxes
- **WHEN** automatic feature registration finds enough inliers
- **THEN** the image is warped to the canonical space and the template boxes are used directly for
  checkbox classification

#### Scenario: Low-confidence registration requests manual correction
- **WHEN** automatic registration cannot find enough inliers
- **THEN** the result signals that a manual four-corner selection is needed, and the app prompts the
  user to pick the form corners before re-running, without crashing or producing a misaligned record

### Requirement: Extract the full form's checkboxes into the record

The system SHALL classify all of the template's checkbox boxes on the registered image and map every
marked box, via the shared form layout, into a complete `service_record.v1` record — not only the
identity and gender fields — applying single-choice (at most one) and multi-choice (a subset)
constraints, with unselected fields left empty.

#### Scenario: All marked checkboxes populate the record
- **WHEN** a registered form is classified
- **THEN** the resulting record reflects the marked options across all form sections (service items,
  cancer types, identity, gender, …) under the layout's single/multi-choice constraints

#### Scenario: Registration assets or opencv are unavailable
- **WHEN** registration assets are missing, opencv is unavailable, or registration fails
- **THEN** the plugin preserves the existing behavior without crashing
