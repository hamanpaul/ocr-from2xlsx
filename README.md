# ocr-from2xlsx

> Portable Windows prototype for turning cancer resource center service-record OCR results into the existing monthly-report XLSX workbook.

## Install

Development install:

```powershell
python -m pip install -e ".[dev]"
```

Optional camera support for UVC webcam experiments:

```powershell
python -m pip install -e ".[dev,camera]"
```

## Usage

1. Prepare normalized JSON from PDF inputs.
2. Validate or review the prepared records.
3. Write confirmed records into the `個案總表` sheet.
4. Save the working XLSX after each confirmed record.
5. Export a final XLSX and import report.

```powershell
ocr-from2xlsx prepare-records --input "tests\fixtures\pdf\for testing only.pdf" --output prepared.json --ocr-fixture "tests\fixtures\pdf\for testing only.ocr.json"
```

Current capture boundaries cover normalized JSON, image folders, UVC cameras, and PDF page metadata so scanned service-record PDFs can be prepared through the fixture-backed `prepare-records` flow before import.

Launch the native desktop UI:

```powershell
ocr-from2xlsx app
```

<!-- BEGIN: cli-help marker="ocr-from2xlsx-help" -->
usage: ocr-from2xlsx [-h] [--version]
                     {sample-json,validate-json,import-json,prepare-records,app}
                     ...

Import normalized service-record JSON into the monthly report XLSX.

positional arguments:
  {sample-json,validate-json,import-json,prepare-records,app}
    sample-json         Generate deterministic sample service-record JSON.
    validate-json       Validate normalized service-record JSON.
    import-json         Import normalized JSON records into a working XLSX.
    prepare-records     Prepare normalized JSON records from PDF inputs.
    app                 Launch the native desktop review UI.

options:
  -h, --help            show this help message and exit
  --version             Print package version and exit.
<!-- END: cli-help marker="ocr-from2xlsx-help" -->

## Packaging

Build a portable executable:

```powershell
python build/package.py
```

Output: `dist/ocr-from2xlsx.exe`

## Version

`VERSION` is the single source of truth for repository versioning. Update it together with `CHANGELOG.md` according to the selected `policy_profile`.
