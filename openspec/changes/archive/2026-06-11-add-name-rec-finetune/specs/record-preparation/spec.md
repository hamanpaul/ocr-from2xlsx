# record-preparation Specification (Delta)

## ADDED

### Requirement: Plugin recognizes handwritten names with a dedicated rec model when available

The PaddleOCR plugin SHALL resolve a name-only rec model directory in the order `NAME_REC_MODEL_DIR`
environment override, user runtime directory (`OCR_FROM2XLSX_HOME` or `~/.ocr_from2xlsx/name_rec/`),
then the bundled `name_rec/` baseline. When resolved, it recognizes the existing PII-minimized name
crop with that model and fills `record.name` as a suggestion that keeps the `name.unconfirmed`
warning; the name agent, roster matching, and GUI confirmation flow are unchanged.

#### Scenario: Name model directory is absent
- **WHEN** no name rec model directory can be resolved
- **THEN** plugin behavior is identical to the current name path (full-page rec, optional agent,
  roster, human confirmation)

#### Scenario: Name model fails at inference time
- **WHEN** the resolved name model directory is invalid or recognition raises an error
- **THEN** the plugin falls back to the current name path for that record instead of failing the run
