# ocr-from2xlsx

> Portable Windows tool design for turning cancer resource center service-record OCR results into the existing monthly-report XLSX workbook.

## Install

This repository is currently in design/bootstrap state. No runtime package is available yet.

Development starts from the committed design spec in:

```text
docs/superpowers/specs/2026-05-24-ocr-xlsx-import-design.md
```

## Usage

Planned first workflow:

1. Load the blank monthly-report XLSX template.
2. Simulate or import OCR results as normalized JSON records.
3. Review and edit each recognized service record.
4. Write confirmed records into the `個案總表` sheet while preserving workbook formatting.
5. Save a working XLSX after each confirmed record and export a final workbook plus import report.

The first implementation will use Python for fast flow validation while keeping JSON and module boundaries friendly to a future Rust rewrite.

## Version

`VERSION` is the single source of truth for repository versioning. Update it together with `CHANGELOG.md` according to the selected `policy_profile`.
