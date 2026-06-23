# record-preparation Specification (Delta)

> Detection redesign (2026-06-24): the "new page" / re-arm signal is now **difference from a
> per-session empty-desk baseline over a central ROI**, not difference from the previously captured
> form. Design: `docs/superpowers/specs/2026-06-24-continuous-capture-detection-redesign-design.md`.
> Resumable correction progress is tracked separately (issue #37) and is NOT part of this change.

## ADDED

### Requirement: Continuously auto-capture multiple forms from the webcam, hands-free

The system SHALL provide a continuous capture session that, while the live preview runs, automatically
detects when a form is **present** (the central region of the frame differs from the session's
empty-desk baseline by at least a present threshold) and is stationary and in focus, then captures a
high-resolution still through the existing capture path that confirms focus before the saved shot, and
accumulates the still without a per-form manual trigger. Presence and clearance SHALL be judged against
the empty-desk baseline (not against the previously captured form), so a stack of visually identical
form templates is handled. After a capture, the session SHALL require the scene to return near the
empty-desk baseline (the form removed) before arming the next capture, so the same form is not captured
twice.

#### Scenario: A settled, in-focus form is auto-captured
- **WHEN** a form is placed under the camera and held stationary until autofocus has settled (preview
  sharpness at or above the threshold and no longer changing beyond a tolerance) and the central region
  differs from the empty-desk baseline beyond the present threshold
- **THEN** the session captures one high-resolution still, re-confirms sharpness on the full-resolution
  frame, and adds it to the pending batch

#### Scenario: A second form of the same template is still captured
- **WHEN** one form has been captured, the desk is cleared (central region returns near the empty-desk
  baseline) and re-arms, and a second form of the **same printed template** (nearly identical to the
  first) is then placed and settled
- **THEN** the second form is captured, because presence is judged against the empty desk rather than
  against the first form

#### Scenario: Focus not yet settled is not captured
- **WHEN** a form is present and stationary but still out of focus (preview sharpness below threshold,
  or still changing beyond the settle tolerance)
- **THEN** no capture is taken until focus settles

#### Scenario: The same form is not captured twice
- **WHEN** a form has just been captured and remains in place (the central region stays far from the
  empty-desk baseline)
- **THEN** no further capture is taken until the desk is cleared near the baseline, after which the
  session re-arms for the next form

#### Scenario: Repeated too-blurry captures pause the session
- **WHEN** the high-resolution capture fails the sharpness gate repeatedly up to a bounded retry limit
- **THEN** the still is not added and the session pauses (stops auto-capturing) and asks the user to
  adjust focus/lighting and re-establish the baseline or restart, rather than retrying indefinitely

#### Scenario: Non-ASCII output path saves the still correctly
- **WHEN** the chosen output directory path contains non-ASCII (e.g. CJK) characters
- **THEN** the captured still is written successfully (the save path does not silently fail), and the
  capture is counted

#### Scenario: No camera preserves the existing flow
- **WHEN** a continuous session is requested but no camera is available or OpenCV is unavailable
- **THEN** the session does not start and the app keeps its existing preview and JSON import flow
  without error

### Requirement: Establish and reset an empty-desk baseline for the session

The system SHALL capture an empty-desk baseline at the start of a continuous session, prompting the user
to clear the capture area first, and SHALL provide a way to re-establish that baseline at any time
(e.g. after lighting or background changes, or to resume after a paused session). Detection SHALL not
begin until a baseline exists.

#### Scenario: Baseline captured at session start
- **WHEN** the user starts a continuous session and confirms the desk is clear
- **THEN** the system captures the empty-desk baseline (central region) and only then begins detecting

#### Scenario: Manual baseline reset
- **WHEN** the user re-establishes the baseline during a session
- **THEN** subsequent presence/clearance decisions use the new empty-desk baseline

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

### Requirement: Recognize a continuously-captured batch and enter per-form review without losing work

On completion of a continuous session, the system SHALL recognize all accumulated stills through the
existing image-batch preparation into one normalized `Batch`, notify the user that recognition is
complete, and load the batch into the existing per-record review (each record's original captured image
shown, per-form progress reported during recognition). Captured stills SHALL remain recognizable even if
the camera is lost mid-session, and a recognition failure SHALL preserve the captured stills so the user
can retry. Completing with no captures SHALL NOT start recognition, and cancelling SHALL discard the
session without recognition.

#### Scenario: Completing a session recognizes the batch and announces completion
- **WHEN** the user completes a continuous session that has one or more captures
- **THEN** all accumulated stills are recognized into one normalized `Batch` with per-form progress, a
  "recognition complete" notification is shown, and the batch is presented in the existing per-record
  review for confirm-and-write-to-XLSX, one form at a time

#### Scenario: Camera lost mid-session keeps captured stills recognizable
- **WHEN** the camera disconnects during a session after one or more stills were captured
- **THEN** the already-captured stills are not discarded and the user can still run recognition on them

#### Scenario: Recognition failure preserves the stills for retry
- **WHEN** recognition raises an error during completion
- **THEN** the captured stills are preserved and the user can retry recognition rather than losing the
  session

#### Scenario: Completing with no captures does nothing
- **WHEN** the user completes a continuous session with zero captures
- **THEN** no recognition runs and the user is told there is nothing to recognize

#### Scenario: Cancelling discards the session without recognition
- **WHEN** the user cancels a continuous session
- **THEN** no recognition runs on the captured stills
