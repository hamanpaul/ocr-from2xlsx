## Why

The current workflow starts at normalized JSON or, at most, PDF page metadata. That makes it impossible to validate the real PDF/image capture path against a stable contract before a handwritten OCR backend is chosen and integrated.

This change creates a formal preprocessing contract from fixed-layout PDF/image inputs to normalized `Batch`/`Record` JSON, so the provided `for testing only.pdf` can become a durable regression fixture while keeping the downstream workbook-import flow unchanged.

## What Changes

- Add a new front-end preparation flow that reads PDF pages or images and emits normalized `Batch` JSON before `validate-json` and `import-json`.
- Define one fixed-layout record-preparation capability that combines page preprocessing, form template zoning, OCR backend selection, field extraction, and final normalization.
- Extend normalized records with source provenance and OCR metadata so PDF/image origins remain traceable without changing the workbook import contract.
- Introduce a manually curated gold JSON fixture for the provided reference PDF and use it as the regression baseline for preprocessing and normalization.

## Capabilities

### New Capabilities
- `record-preparation`: Convert fixed-layout PDF/image pages into normalized `Batch`/`Record` JSON through a pluggable OCR preprocessing pipeline while preserving source and OCR metadata.

### Modified Capabilities
- None.

## Impact

- Affected code: `src/ocr_from2xlsx/capture.py`, `src/ocr_from2xlsx/normalizer.py`, `src/ocr_from2xlsx/json_io.py`, `src/ocr_from2xlsx/cli.py`, related tests, and new fixtures.
- Affected dependencies: local/offline OCR backend support and preprocessing helpers suitable for Windows portable packaging.
- Affected workflow: introduces a new `prepare-records` stage ahead of the existing `validate-json` and `import-json` commands.
