# record-preparation Specification (Delta)

## ADDED

### Requirement: Continuously auto-capture multiple forms from the webcam, hands-free

The system SHALL provide a continuous capture session that, while the live preview runs, automatically
detects when a newly placed form is stationary and in focus, captures a high-resolution still through
the existing capture path that confirms focus before the saved shot, and accumulates the still without
a per-form manual trigger. After a capture, the session SHALL require the scene to change substantially
(the form removed or replaced) before arming the next capture, so the same form is not captured twice.

#### Scenario: A settled, in-focus form is auto-captured
- **WHEN** a form is placed under the camera and held stationary until autofocus has converged (frame
  sharpness at or above the preview threshold and no longer rising)
- **THEN** the session captures one high-resolution still, re-confirms sharpness on the full-resolution
  frame, and adds it to the pending batch

#### Scenario: Focus not yet converged is not captured
- **WHEN** the frame is stationary but still out of focus (sharpness below the preview threshold or
  still rising)
- **THEN** no capture is taken until focus converges

#### Scenario: The same form is not captured twice
- **WHEN** a form has just been captured and remains in place
- **THEN** no further capture is taken until the scene changes substantially (the form is removed or
  replaced), after which the session re-arms for the next form

#### Scenario: A too-blurry full-resolution capture is not added
- **WHEN** the high-resolution capture fails the sharpness gate
- **THEN** the still is not added, the user is told to adjust focus/lighting, and the session retries up
  to a bounded limit before pausing for the user

#### Scenario: No camera preserves the existing flow
- **WHEN** a continuous session is requested but no camera is available or OpenCV is unavailable
- **THEN** the session does not start and the app keeps its existing preview and JSON import flow
  without error

### Requirement: Give immediate per-capture feedback during a continuous session

The system SHALL give an immediate shutter sound and on-screen feedback each time a still is captured in
a continuous session, including a running capture count, so an operator not watching the screen knows a
form was captured. The shutter sound SHALL degrade safely (a fallback tone or silence) when the sound
asset or audio interface is unavailable, without failing the capture.

#### Scenario: Capture plays a shutter sound and updates the count
- **WHEN** a still is captured during a continuous session
- **THEN** a shutter sound plays, an on-screen capture indicator flashes, and the running capture count
  increments

#### Scenario: Unavailable audio degrades safely
- **WHEN** the shutter sound asset or audio interface is unavailable
- **THEN** the capture still succeeds and the count updates without error

### Requirement: Undo the most recent continuous capture

The system SHALL let the user discard the most recent capture during a continuous session, deleting its
stored still and decrementing the count, so an erroneous auto-capture can be corrected before
recognition.

#### Scenario: Undo removes the last still
- **WHEN** the user undoes the last capture during a continuous session
- **THEN** the most recently stored still is deleted and the pending capture count decreases by one

### Requirement: Recognize a continuously-captured batch through the existing batch flow

On completion of a continuous session, the system SHALL recognize all accumulated stills through the
existing image-batch preparation into one normalized `Batch` and load it into the existing per-record
review with each record's original captured image shown, reporting per-form progress. Completing a
session with no captures SHALL NOT start recognition, and cancelling a session SHALL discard it without
recognition.

#### Scenario: Completing a session recognizes the accumulated batch
- **WHEN** the user completes a continuous session that has one or more captures
- **THEN** all accumulated stills are recognized into one normalized `Batch` and presented in the
  existing per-record review, with per-form progress shown during recognition

#### Scenario: Completing with no captures does nothing
- **WHEN** the user completes a continuous session with zero captures
- **THEN** no recognition runs and the user is told there is nothing to recognize

#### Scenario: Cancelling discards the session without recognition
- **WHEN** the user cancels a continuous session
- **THEN** no recognition runs on the captured stills
