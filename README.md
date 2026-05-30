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
Prepare PDF records or import normalized service-record JSON into the monthly report XLSX.

usage: ocr-from2xlsx [-h] [--version]
                     {sample-json,validate-json,import-json,prepare-records,app}
                     ...

Prepare PDF records or import normalized service-record JSON into the monthly
report XLSX.

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

## OCR plugin (portable, offline)

`prepare-records` can read OCR results from an external, portable OCR plugin instead of a fixture:

```powershell
ocr-from2xlsx prepare-records `
  --input "scan.pdf" `
  --output output\prepared.json `
  --ocr-backend plugin `
  --ocr-plugin-dir path\to\plugins\paddleocr
```

The plugin directory must contain a `plugin.json` manifest:

```json
{ "contract_version": "ocr_plugin.v1", "command": ["__PYTHON__", "main.py"] }
```

`__PYTHON__` is replaced with the running interpreter. The plugin receives an `ocr_plugin.v1`
request on stdin and returns `{ "contract_version": "ocr_plugin.v1", "record": { ... } }` on stdout.
If no plugin is found (via `--ocr-plugin-dir`, `OCR_PLUGIN_DIR`, or the default
`plugins/paddleocr` next to the executable), `prepare-records` exits with an error so you can fall
back to `--ocr-backend fixture` or the review UI. The PaddleOCR plugin itself is built separately
(see the design spec).

### Building the PaddleOCR plugin

The PaddleOCR plugin is built separately into a portable offline folder:

```powershell
# one-time: create the paddle env and download models
py -3.12 -m venv .venv-paddle
.venv-paddle\Scripts\python -m pip install "paddlepaddle==3.0.0" paddleocr

# assemble the bundle at dist/plugins/paddleocr/
.venv\Scripts\python build/build_paddle_plugin.py

# use it
ocr-from2xlsx prepare-records --input scan.pdf --output out.json `
  --ocr-backend plugin --ocr-plugin-dir dist\plugins\paddleocr
```

The bundle ships a Python venv, the PP-OCRv5 mobile models, and runs fully offline
(`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`, models loaded from the bundle). It recognizes the form
full-page and extracts service date / name / medical-record-no via text anchors; checkbox fields are
added in a later sub-project.

## Packaging

Build a portable executable:

```powershell
python build/package.py
```

Output: `dist/ocr-from2xlsx.exe`

## Version

`VERSION` is the single source of truth for repository versioning. Update it together with `CHANGELOG.md` according to the selected `policy_profile`.
