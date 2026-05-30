# record-preparation Specification (Delta)

**Change ID:** `add-handwritten-name-agent`
**Affects:** OCR plugin name-crop output, optional cloud VLM name agent, correction store + confirmed-name
roster (main app), name-confirmation flagging.

---

## ADDED

### Requirement: Emit a privacy-minimized name crop from the form

The system SHALL emit a cropped image containing only the handwritten name (the content after the
姓名/病歷號 anchor on its line), derived from runtime OCR anchor geometry, and SHALL exclude the
medical-record-no digits and the diagnosis-date line from that crop. The record SHALL reference the crop's
location.

#### Scenario: Name crop excludes the medical-record-no
- **WHEN** the form's 姓名/病歷號 region contains a handwritten name on its line and the medical-record-no on a different line
- **THEN** the emitted name crop covers the name line and does not include the medical-record-no digits, and the record references the crop path

### Requirement: Suggest a handwritten name via an optional, gracefully-absent agent

The system SHALL support a configurable name agent that, given only the name crop, returns a suggested
name. When no agent is configured, the agent is disabled, or the agent is unreachable or errors, the system
SHALL behave exactly as if the agent were absent, without affecting the rest of the pipeline and without
error.

#### Scenario: Configured agent suggests a name
- **WHEN** a name agent is configured and enabled and a name crop is available
- **THEN** the record's name is populated with the agent's suggested name

#### Scenario: Absent agent does not affect the pipeline
- **WHEN** no name agent is configured (or it is disabled or unavailable)
- **THEN** the pipeline produces the same record it would have without the agent, the name is left for human entry, and no error is raised

### Requirement: Never write a name without human confirmation

The system SHALL flag any machine-produced name as unconfirmed and SHALL NOT treat it as final until a human
confirms it.

#### Scenario: Machine-suggested name is marked unconfirmed
- **WHEN** the name is produced by the agent or a roster match rather than by a human
- **THEN** the record carries a `name.unconfirmed` warning until a human confirms the name

### Requirement: Record human name corrections for learning

The system SHALL append each human confirmation or correction to a local correction store capturing the name
crop reference, the raw OCR text, the agent suggestion, the roster suggestion, the final confirmed value, the
field, the record id, and the source page.

#### Scenario: Confirmation is recorded
- **WHEN** a human confirms or corrects the name for a record
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
