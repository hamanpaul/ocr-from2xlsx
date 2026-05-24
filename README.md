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

The first implementation validates the workflow before real hand-written OCR is integrated:

1. Generate or import normalized service-record JSON.
2. Review records in the native desktop UI.
3. Write confirmed records into the `個案總表` sheet.
4. Save the working XLSX after each confirmed record.
5. Export a final XLSX and import report.

Launch the native desktop UI:

```powershell
ocr-from2xlsx app
```

<!-- BEGIN: cli-help marker="ocr-from2xlsx-help" -->
usage: ocr-from2xlsx [-h] [--version]
                     {sample-json,validate-json,import-json,app} ...

Import normalized service-record JSON into the monthly report XLSX.

positional arguments:
  {sample-json,validate-json,import-json,app}
    sample-json         Generate deterministic sample service-record JSON.
    validate-json       Validate normalized service-record JSON.
    import-json         Import normalized JSON records into a working XLSX.
    app                 Launch the native desktop review UI.

options:
  -h, --help            show this help message and exit
  --version             Print package version and exit.
<!-- END: cli-help marker="ocr-from2xlsx-help" -->

## Version

`VERSION` is the single source of truth for repository versioning. Update it together with `CHANGELOG.md` according to the selected `policy_profile`.
