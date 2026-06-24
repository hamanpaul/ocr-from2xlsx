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

You can open the desktop review app in any of these ways:

- Run the CLI with no subcommand to open the app directly: `ocr-from2xlsx`.
- Run the explicit subcommand: `ocr-from2xlsx app`.
- Double-click the packaged executable (`dist/ocr-from2xlsx.exe`) to launch the app.

Note: The packaged exe is windowed (no console). CLI users who need stdout should run an explicit subcommand, for example `python -m ocr_from2xlsx <subcommand>` (e.g. `python -m ocr_from2xlsx import-json`).

On startup the app auto-detects webcams: if exactly one camera is found it auto-connects and shows a preview; if multiple cameras are present it prompts to select one; if none are present or OpenCV is unavailable it gracefully falls back to the existing JSON-driven flow and the preview placeholder is used. A `選擇攝影機` button is provided in the UI to switch cameras.

```powershell
ocr-from2xlsx
```

<!-- BEGIN: cli-help marker="ocr-from2xlsx-help" -->
Prepare PDF records or import normalized service-record JSON into the monthly report XLSX.

usage: ocr-from2xlsx [-h] [--version]
                     {sample-json,validate-json,import-json,prepare-records,scan,app}
                     ...

Prepare PDF records or import normalized service-record JSON into the monthly
report XLSX.

positional arguments:
  {sample-json,validate-json,import-json,prepare-records,scan,app}
    sample-json         Generate deterministic sample service-record JSON.
    validate-json       Validate normalized service-record JSON.
    import-json         Import normalized JSON records into a working XLSX.
    prepare-records     Prepare normalized JSON records from PDF inputs.
    scan                Capture a webcam still (or read an image) and
                        recognize it into normalized JSON.
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
(`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`, models loaded from the bundle). The default portable
bundle does not include the extra PaddleX document-orientation / unwarping models (`PP-LCNet_x1_0_doc_ori`,
`UVDoc`), so `SCAN_DOC_PREPROCESS=1` only takes effect when those model dirs are also present in the
cache/bundle; otherwise the plugin safely keeps that opt-in path off. It recognizes the form full-page,
probes checkbox ink immediately left of OCR label anchors, and also uses OCR-text anomalies such as
`中女性` / `病人625...` as secondary marked signals. The current plugin extracts service date, identity,
gender, handwritten name, and medical-record-no; PDF preprocessing now renders at 400 DPI to
improve real-form MRN recovery.

The plugin also emits a PII-minimized handwritten-name crop. When `prepare-records` runs with
`--name-agent-config`, it uses `record.ocr.name_crop` if present and otherwise falls back to the sibling
`*-name.png` next to `source.preprocessed_image_path`; only that crop is sent to the optional agent.

For review-oriented verification, `import-json --allow-incomplete` will still write a recognized record
as `forced` when only writable patient-only fields are missing. On the reference form, the mobile
recognizer still may not recover the handwritten name reliably, so this path remains the practical way
to inspect real OCR output before manual completion.

### Handwritten name agent

`--name-agent-config` points to a TOML file that enables the optional handwritten-name agent. The
agent is a no-op when the file is missing, disabled, or uses an unsupported provider. The API key is
read from the env var named in the config (`api_key_env`, default `ANTHROPIC_API_KEY`), and only the
name crop is sent.

Suggested names are always tagged `name.unconfirmed` until a human confirms them. Confirmations are
handled through the review/edit workflow in `ocr-from2xlsx app`; there is no dedicated `confirm-name`
CLI. That confirmation is written to the local correction store and roster, which later matching can
reuse to improve hits and reduce cloud calls. If you are importing without the app, review the record
manually before import.

## Training data generator

Use the synthetic training generator to create form images plus workflow-aligned answer keys from the
blank workbook template.

```powershell
# one-time: download OFL fonts into training/fonts/
.venv-paddle\Scripts\python training/fetch_fonts.py

# generate images and answers.json
.venv-paddle\Scripts\python -m training.generate `
  --xlsx "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx" `
  --out training\out `
  --min-per-option 5 `
  --seed 0
```

Outputs:

- `training\out\images\train-*.png`
- `training\out\answers.json`

`answers.json` uses `service_record.v1` and stores `training: true` plus `source_image` on each record.
Generation stays offline. If `training\fonts\` is empty, or a downloaded font cannot render the needed
Chinese text, the generator falls back to Windows system fonts. Add `--augment` for light
rotation/blur/speckle augmentation.

Evaluate synthetic outputs in two stages:

```powershell
# mark-blinded checkbox evaluation: uses known workbook geometry and answers.json, no OCR plugin
.venv-paddle\Scripts\python -m training.eval_marks `
  training\out\answers.json `
  --workbook "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx" `
  --output-dir training\out\eval-marks

# diagnostic end-to-end evaluation: runs the OCR plugin, then compares records to answers.json
.venv\Scripts\python -m training.eval_pipeline `
  training\out\answers.json `
  --ocr-plugin-dir plugins\paddleocr `
  --output-dir training\out\eval-pipeline
```

Both evaluators write `report.json` and `report.md`. Mark-blinded evaluation isolates checkbox mark
detection from OCR text recognition; pipeline evaluation is diagnostic because it runs the full OCR
plugin and reports field-level record mismatches.

To bootstrap the lightweight mark classifier, export geometry boxes, harvest labeled crops, and train a
JSON weight file:

```powershell
# export all known checkbox boxes for aligned images
.venv\Scripts\python -m training.export_template_boxes `
  "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx" `
  plugins\paddleocr\template_boxes.json

# harvest a whole synthetic answers.json batch (bootstrap corpus)
.venv\Scripts\python -m training.harvest_corrections `
  --answers training\out\answers.json `
  --template-boxes plugins\paddleocr\template_boxes.json `
  --dataset-dir training\out\mark_dataset

# or append confirmed record crops one at a time (manual correction loop)
.venv-paddle\Scripts\python -m training.harvest_corrections `
  prepared-confirmed.json `
  --image scan.png `
  --template-boxes plugins\paddleocr\template_boxes.json `
  --dataset-dir training\out\mark_dataset

# train pure JSON weights with a precision-safe operating point
.venv\Scripts\python -m training.train_mark_model `
  training\out\mark_dataset\manifest.jsonl `
  --output plugins\paddleocr\mark_model.json `
  --min-precision 0.99
```

After deployment, strengthen the model with confirmed corrections through the gated retrain command.
It trains on every manifest you pass, evaluates the candidate against the currently deployed weights on
a fixed holdout manifest, and only replaces the runtime weights when recall improves without dropping
precision below the gate. Every decision is appended to an audit JSONL:

```powershell
.venv\Scripts\python -m training.retrain `
  training\out\mark_dataset\manifest.jsonl `
  training\out\corrections\manifest.jsonl `
  --holdout training\out\holdout_dataset\manifest.jsonl `
  --min-precision 0.99
```

Adopted weights land in `%USERPROFILE%\.ocr_from2xlsx\mark_model.json` (override the directory with
`OCR_FROM2XLSX_HOME`; pick another target with `--runtime-dir`). The exit code is `0` when the candidate
is adopted and `2` when the gate keeps the current weights. The audit log defaults to
`mark_audit.jsonl` next to the runtime weights.

`plugins\paddleocr` uses `MARK_TEMPLATE_BOXES` / bundled `template_boxes.json` to enable geometry crops.
Mark model weights resolve in order: `MARK_MODEL_PATH` env override, user runtime weights
(`OCR_FROM2XLSX_HOME` or `~\.ocr_from2xlsx\mark_model.json`, written by `training.retrain`), then the
bundled baseline `mark_model.json`. Without any weights, geometry crops fall back to the legacy
`is_marked` threshold. Without template boxes, the plugin keeps the existing OCR-label mark fallback.

## Handwritten name model training

Finetune a name-only PP-OCRv5_mobile_rec model on synthetic handwritten name crops (CPU, offline
after the one-time fetch):

```powershell
# one-time: vendor the official PaddleOCR trainer (pinned tag) + pretrained rec weights
.venv-paddle\Scripts\python training/fetch_paddleocr_train.py

# generate a name corpus (disjoint train/validation/holdout; holdout never trains)
.venv-paddle\Scripts\python -m training.gen_names `
  --out training\out\namev1 --total 3000 --seed 20 `
  --dict training\vendor\PaddleOCR\ppocr\utils\dict\ppocrv5_dict.txt

# finetune and export an inference model dir
.venv-paddle\Scripts\python -m training.train_name_model `
  --corpus training\out\namev1 `
  --save-dir training\out\namev1\model `
  --inference-dir training\out\namev1\inference --epochs 20

# evaluate any model (omit --model-dir for the pip baseline)
.venv-paddle\Scripts\python -m training.eval_name_model `
  training\out\namev1\holdout.txt --output-dir training\out\namev1\eval-baseline

# gate against the current model on the fixed holdout and deploy atomically when better
.venv-paddle\Scripts\python -m training.retrain_name `
  training\out\namev1\inference --holdout training\out\namev1\holdout.txt

# fold human-confirmed corrections into the next finetune corpus
.venv-paddle\Scripts\python -m training.harvest_name_corrections `
  output\name_corrections.jsonl --output training\out\namev1\corrections.txt
```

The gate adopts a candidate only when holdout exact-match improves and character accuracy does not
regress; every decision is appended to `name_audit.jsonl` next to the deployed model. The plugin
resolves the name model dir in order: `NAME_REC_MODEL_DIR` env override, user runtime dir
(`OCR_FROM2XLSX_HOME` or `~\.ocr_from2xlsx\name_rec\`, written by `training.retrain_name`), then a
bundled `name_rec\` directory. Without a model the name path is unchanged (full-page rec, optional
agent, roster, human confirmation), and recognized names always stay `name.unconfirmed` until a
human confirms them.

Note: the v1 model is not committed to the repo — the exported inference dir is ~136 MB, far above
the repo-size budget (official mobile rec inference models are ~16 MB; the oversized export is a
known follow-up). Produce it locally with the commands above; `build/build_paddle_plugin.py` bundles
`plugins\paddleocr\name_rec\` when present.

## Packaging

Build a portable executable. Before running the packager, you must install the dev and camera extras so OpenCV is bundled into the packaged exe:

```powershell
# required: install dev and camera extras so OpenCV is included in the packaged exe
python -m pip install -e ".[dev,camera]"
python build/package.py
```

Output: `dist/ocr-from2xlsx.exe`

## Version

`VERSION` is the single source of truth for repository versioning. Update it together with `CHANGELOG.md` according to the selected `policy_profile`.
