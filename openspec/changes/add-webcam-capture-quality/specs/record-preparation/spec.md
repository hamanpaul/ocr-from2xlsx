# record-preparation Specification (Delta)

## ADDED

### Requirement: Capture a high-quality still from the webcam with a sharpness gate

The system SHALL provide a reusable webcam still-capture that enables autofocus, negotiates the
camera's native maximum resolution (by requesting an oversized resolution and reading back the
actual value rather than hardcoding a target), warms up so autofocus can settle, and measures frame
sharpness; frames below a sharpness threshold SHALL be rejected with a retake prompt and SHALL NOT be
sent to OCR.

#### Scenario: A blurry capture is rejected before OCR
- **WHEN** a captured frame's sharpness is below the threshold
- **THEN** the capture is rejected, the user is prompted to retake, and no OCR is run on it

#### Scenario: Capture uses the camera's native maximum resolution
- **WHEN** a still is captured
- **THEN** the resolution used is the camera's negotiated native maximum (read back from the device),
  not a fixed hardcoded target

### Requirement: Recognize a captured image through the existing OCR into a form-fillable record

The system SHALL accept a still image (webcam capture or file), run it through the existing OCR
plugin, and produce a normalized `service_record.v1` record consistent with the existing import flow,
both from an in-app "capture & recognize" action and a CLI path, degrading gracefully when no camera
is available, the frame is rejected, or OCR fails.

#### Scenario: A good capture fills the review form
- **WHEN** a sufficiently sharp image of a service-record form is captured and recognized
- **THEN** a `service_record.v1` record is produced and its recognized fields populate the review form
  as suggestions (names remain `name.unconfirmed` until human confirmation)

#### Scenario: No camera or OCR failure preserves the existing flow
- **WHEN** no camera is available, the frame is rejected by the sharpness gate, or OCR fails
- **THEN** the app keeps the existing preview and JSON import flow without error
