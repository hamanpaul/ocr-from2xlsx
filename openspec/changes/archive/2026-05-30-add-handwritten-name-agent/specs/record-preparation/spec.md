# record-preparation Specification (Delta)

**Change ID:** `add-handwritten-name-agent`
**Affects:** OCR plugin name-crop output, optional cloud VLM name agent, correction store + confirmed-name
roster (main app), name-confirmation flagging.

---

## ADDED

### Requirement: Emit a privacy-minimized name crop from the form

The system SHALL emit a cropped image containing only the handwritten name (the content after the
姓名/病歷號 anchor on its line), derived from runtime OCR anchor geometry, and SHALL exclude the
medical-record-no digits and the diagnosis-date line from that crop. The preparation flow SHALL make the
crop discoverable to downstream suggestion logic, either by recording its path in OCR metadata or by using
the stable sibling naming convention derived from the prepared page image.

#### Scenario: Name crop excludes the medical-record-no
- **WHEN** the form's 姓名/病歷號 region contains a handwritten name on its line and the medical-record-no on a different line
- **THEN** the emitted name crop covers the name line, does not include the medical-record-no digits, and remains discoverable to the downstream suggestion flow

### Requirement: Suggest a handwritten name via an optional, gracefully-absent agent

The system SHALL support a configurable handwritten-name suggestion pass that can reuse previously confirmed
local names and, when configured, call a cloud name agent using only the minimized name crop. When no agent
is configured, the agent is disabled, the agent is unreachable or errors, or no crop is available, the
system SHALL behave exactly as if the suggestion pass were absent, without affecting the rest of the
pipeline and without error.

#### Scenario: Configured suggestion pass proposes a name
- **WHEN** a name agent is configured and enabled and a name crop is available
- **THEN** the record's name is populated with a suggested candidate and marked for human confirmation

#### Scenario: Absent or disabled suggestion pass does not affect the pipeline
- **WHEN** no name agent is configured (or it is disabled or unavailable)
- **THEN** the pipeline produces the same record it would have without the suggestion pass, the name is left for human confirmation, and no error is raised

### Requirement: Never write a name without human confirmation

The system SHALL flag any machine-produced or roster-recommended name as unconfirmed and SHALL NOT treat it
as final until a human confirms it.

#### Scenario: Machine-suggested name is marked unconfirmed
- **WHEN** the name is produced by the agent or a roster match rather than by a human
- **THEN** the record carries a `name.unconfirmed` warning until a human confirms the name

#### Scenario: Direct import blocks unconfirmed names
- **WHEN** an import reaches a record whose name still carries `name.unconfirmed`
- **THEN** the write is blocked until a human confirms the name

### Requirement: Record human name corrections for learning

The system SHALL append each human confirmation or correction of an unconfirmed name to a local correction
store capturing the crop reference, the raw OCR text, the agent suggestion, the roster suggestion, the final
confirmed value, the field, the record id, and the source page.

#### Scenario: Confirmation is recorded
- **WHEN** a human confirms or corrects the name for a record in the review workflow
- **THEN** a correction entry with the above fields is appended to the local correction store

### Requirement: Recommend confirmed names via a local roster fuzzy match

The system SHALL maintain a local roster of confirmed names and SHALL recommend the closest roster name for a
candidate when their similarity meets a configured threshold, so that recurring names can be resolved locally
without calling the cloud agent. A recommendation SHALL NOT bypass human confirmation.

#### Scenario: Near-miss candidate matches a known name
- **WHEN** an OCR or agent name candidate is sufficiently similar to a name already in the roster
- **THEN** the system recommends that roster name for human confirmation

#### Scenario: Dissimilar candidate is not forced onto a roster name
- **WHEN** a candidate's similarity to every roster name is below the threshold
- **THEN** no roster name is recommended and the candidate is left for human entry
