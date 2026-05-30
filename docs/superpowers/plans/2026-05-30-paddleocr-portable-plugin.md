# PaddleOCR Portable Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable, offline PaddleOCR plugin (sub-project 2) that speaks the `ocr_plugin.v1` contract from sub-project 1, recognizing the service-record form full-page and extracting the text fields (service date / name / medical-record-no) via text anchors. Packaged as an embedded-venv folder under `plugins/paddleocr/` that the main app invokes by subprocess.

**Architecture:** The plugin is self-contained (no dependency on the `ocr_from2xlsx` package). Pure, CI-safe logic (ROC-date normalization + anchor-based field extraction) lives in `plugins/paddleocr/field_extract.py` and is unit-tested without PaddleOCR. The plugin entry `plugins/paddleocr/main.py` reads an `ocr_plugin.v1` request on stdin, runs PaddleOCR full-page (injectable OCR function for testability), maps results through `field_extract`, and writes an `ocr_plugin.v1` response on stdout. A build script assembles a runnable offline bundle (bundled Python venv + mobile models + entry) and end-to-end verification runs it through sub-project 1's `PluginOcrBackend`.

**Tech Stack:** Python 3.12, PaddleOCR 3.6 (`PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec` + `PP-LCNet_x1_0_textline_ori`), stdlib only for the pure logic. Plugin runs under its own bundled venv (`.venv-paddle` during dev), never the main `.venv`.

---

## Spike Findings (already verified, drives this plan)

- PaddleOCR 3.6.0 + paddlepaddle 3.0.0 (CPU) installed in `.venv-paddle` recognizes the real form offline:
  printed title `癌症資源中心服務紀錄表` (0.99), handwritten ROC date `服務年/月/日：114.06.25` (0.88),
  and **every `□` option label** at 0.9+. Mobile models: init ~7s, predict ~7s/page, ~188 lines.
- PaddleOCR 3.x API (note: differs from 2.x):
  ```python
  from paddleocr import PaddleOCR
  ocr = PaddleOCR(
      text_detection_model_name="PP-OCRv5_mobile_det",
      text_recognition_model_name="PP-OCRv5_mobile_rec",
      use_doc_orientation_classify=False,
      use_doc_unwarping=False,
      use_textline_orientation=True,
  )
  results = ocr.predict("page.png")  # list; each item has res["rec_texts"], res["rec_scores"], res["rec_polys"]
  ```
  Passing explicit model names makes `lang` ignored (warning is benign); `PP-OCRv5_mobile_rec` reads
  Traditional Chinese fine.
- Models cache at `~/.paddlex/official_models/<model>`; ~172 MB (server) / mobile smaller. First run
  downloads them. Offline operation: set `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` and point the
  PaddleX cache home at a bundled models dir.
- Decisions (user-approved): embedded-venv-folder packaging (NOT PyInstaller single-exe); mobile models;
  full-page OCR + text-anchor extraction (NOT zone-crop).

## File Structure

```text
plugins/paddleocr/
  field_extract.py     NEW. Pure: ROC-date normalize + anchor field extraction. stdlib only.
  main.py              NEW. ocr_plugin.v1 entry: stdin->PaddleOCR(injectable)->field_extract->stdout.
  plugin.json          NEW. Manifest; command runs the bundled venv python on main.py.
build/
  build_paddle_plugin.py  NEW. Assemble dist/plugins/paddleocr/ offline bundle; verify via PluginOcrBackend.
tests/
  test_paddle_field_extract.py  NEW. Pure unit tests (no paddle), CI-safe.
  test_paddle_plugin_run.py     NEW. main.run() plumbing with a fake OCR fn (no paddle), CI-safe.
README.md              MODIFY. PaddleOCR plugin build/run section.
CHANGELOG.md           MODIFY. [Unreleased] entries.
```

The plugin source files are stdlib-only / paddle-only and do NOT import `ocr_from2xlsx`. Tests load them
by file path with `importlib` (shown below) since `plugins/` is not on `sys.path`.

---

## Task 1: ROC-date + anchor field extractor (pure, CI-safe)

**Files:**
- Create: `plugins/paddleocr/field_extract.py`
- Create: `tests/test_paddle_field_extract.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_paddle_field_extract.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "field_extract.py"
_spec = importlib.util.spec_from_file_location("paddle_field_extract", _MODULE_PATH)
field_extract = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(field_extract)

normalize_roc_date = field_extract.normalize_roc_date
extract_fields = field_extract.extract_fields


def _line(text, x=0.0, y=0.0):
    # box is 4 points [tl, tr, br, bl]; only center is used downstream
    return {"text": text, "box": [[x, y], [x + 50, y], [x + 50, y + 10], [x, y + 10]]}


def test_normalize_roc_date_dotted():
    assert normalize_roc_date("114.06.25") == "2026-06-25"


def test_normalize_roc_date_with_label_and_cjk_separators():
    assert normalize_roc_date("服務年/月/日：114、6、5") == "2026-06-05"


def test_normalize_roc_date_slash():
    assert normalize_roc_date("113/12/31") == "2024-12-31"


def test_normalize_roc_date_rejects_garbage():
    assert normalize_roc_date("no date here") is None


def test_normalize_roc_date_rejects_impossible_month():
    assert normalize_roc_date("114.13.40") is None


def test_extract_fields_finds_service_date_from_anchor_line():
    lines = [
        _line("癌症資源中心服務紀錄表", y=0),
        _line("服務年/月/日：114.06.25", y=20),
        _line("A.服務評估統計", y=40),
    ]
    fields = extract_fields(lines)
    assert fields["service_date"] == "2026-06-25"


def test_extract_fields_returns_none_when_no_date():
    lines = [_line("癌症資源中心服務紀錄表", y=0), _line("備註", y=99)]
    fields = extract_fields(lines)
    assert fields["service_date"] is None


def test_extract_fields_reads_name_and_mrn_to_right_of_anchor():
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("王小明 A123456", x=120, y=50),
    ]
    fields = extract_fields(lines)
    assert fields["name"] == "王小明"
    assert fields["medical_record_no"] == "A123456"


def test_extract_fields_name_mrn_none_when_anchor_value_missing():
    lines = [_line("姓名/病歷號", x=0, y=50)]
    fields = extract_fields(lines)
    assert fields["name"] is None
    assert fields["medical_record_no"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_field_extract.py -q`
Expected: FAIL (module/functions not found).

- [ ] **Step 3: Implement the extractor**

Create `plugins/paddleocr/field_extract.py`:

```python
"""Pure, dependency-free field extraction from PaddleOCR full-page results.

An OCR line is a dict: {"text": str, "box": [[x, y], [x, y], [x, y], [x, y]]}.
Only text and box centers are used, so this module is unit-testable without PaddleOCR.
"""
from __future__ import annotations

import re
from typing import Any

_ROC_DATE = re.compile(r"(\d{2,3})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})")
_DATE_ANCHOR = ("服務年", "年/月/日", "年月日")
_NAME_ANCHOR = "姓名"
# A handwritten medical-record-no token: letters/digits, >=4 chars, contains a digit.
_MRN_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{3,}")


def normalize_roc_date(text: str) -> str | None:
    match = _ROC_DATE.search(text or "")
    if not match:
        return None
    roc_year, month, day = (int(part) for part in match.groups())
    year = roc_year + 1911
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _center(box: list[list[float]]) -> tuple[float, float]:
    xs = [pt[0] for pt in box]
    ys = [pt[1] for pt in box]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _find_anchor(lines: list[dict[str, Any]], needles: tuple[str, ...] | str):
    needle_tuple = (needles,) if isinstance(needles, str) else needles
    for line in lines:
        text = str(line.get("text") or "")
        if any(needle in text for needle in needle_tuple):
            return line
    return None


def extract_service_date(lines: list[dict[str, Any]]) -> str | None:
    anchor = _find_anchor(lines, _DATE_ANCHOR)
    if anchor is None:
        return None
    return normalize_roc_date(str(anchor.get("text") or ""))


def extract_name_and_mrn(lines: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    anchor = _find_anchor(lines, _NAME_ANCHOR)
    if anchor is None:
        return (None, None)
    ax, ay = _center(anchor["box"])
    candidates = []
    for line in lines:
        if line is anchor:
            continue
        cx, cy = _center(line["box"])
        if cx > ax and abs(cy - ay) <= 15:
            candidates.append((cx, str(line.get("text") or "")))
    if not candidates:
        return (None, None)
    candidates.sort(key=lambda item: item[0])
    value = candidates[0][1].strip()
    if not value:
        return (None, None)
    mrn_match = _MRN_TOKEN.search(value)
    mrn = mrn_match.group(0) if mrn_match else None
    name = value
    if mrn:
        name = value.replace(mrn, "").strip()
    return (name or None, mrn)


def extract_fields(lines: list[dict[str, Any]]) -> dict[str, Any]:
    name, mrn = extract_name_and_mrn(lines)
    return {
        "service_date": extract_service_date(lines),
        "name": name,
        "medical_record_no": mrn,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_field_extract.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```powershell
git add plugins/paddleocr/field_extract.py tests/test_paddle_field_extract.py
git commit -m "feat: add PaddleOCR field extraction logic"
```
(End commit message with a blank line then exactly:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`)

---

## Task 2: Plugin entry `main.py` + manifest (CI-safe plumbing)

**Files:**
- Create: `plugins/paddleocr/main.py`
- Create: `plugins/paddleocr/plugin.json`
- Create: `tests/test_paddle_plugin_run.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_paddle_plugin_run.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_plugin_main", _MODULE_PATH)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)

run = plugin_main.run

CONTRACT = "ocr_plugin.v1"


def _fake_ocr_fn(image_path):
    # Returns OCR lines like field_extract expects; ignores the image.
    def line(text, x=0.0, y=0.0):
        return {"text": text, "box": [[x, y], [x + 50, y], [x + 50, y + 10], [x, y + 10]]}

    return [
        line("癌症資源中心服務紀錄表", y=0),
        line("服務年/月/日：114.06.25", y=20),
        line("姓名/病歷號", x=0, y=50),
        line("王小明 A123456", x=120, y=50),
    ]


def test_run_builds_contract_response_with_extracted_fields():
    request = {
        "contract_version": CONTRACT,
        "template_id": "service_record.v1",
        "page": {"image_path": "ignored.png", "document_name": "scan.pdf", "page_number": 1},
    }

    response = run(request, ocr_fn=_fake_ocr_fn)

    assert response["contract_version"] == CONTRACT
    record = response["record"]
    assert record["service_date"] == "2025-06-25"  # ROC 114 + 1911 = 2025
    assert record["name"] == "王小明"
    assert record["medical_record_no"] == "A123456"
    assert record["ocr"]["backend"] == "paddleocr"
    assert isinstance(record["ocr"]["raw_text"], str)
    assert "癌症資源中心服務紀錄表" in record["ocr"]["raw_text"]


def test_run_rejects_wrong_contract_version():
    request = {"contract_version": "nope", "page": {"image_path": "x.png"}}
    try:
        run(request, ocr_fn=_fake_ocr_fn)
    except ValueError as exc:
        assert "contract_version" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_plugin_run.py -q`
Expected: FAIL (module/`run` not found).

- [ ] **Step 3: Implement `main.py`**

Create `plugins/paddleocr/main.py`:

```python
"""PaddleOCR plugin entry implementing the ocr_plugin.v1 contract.

Runs under its own bundled venv (paddleocr installed). The pure orchestration `run()` takes an
injectable `ocr_fn` so it can be unit-tested without PaddleOCR. `main()` wires the real engine.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import field_extract  # noqa: E402  (sibling module, loaded from plugin dir)

CONTRACT_VERSION = "ocr_plugin.v1"

OcrFn = Callable[[str], list[dict[str, Any]]]


def run(request: dict[str, Any], ocr_fn: OcrFn) -> dict[str, Any]:
    if request.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported contract_version: {request.get('contract_version')!r}; "
            f"expected {CONTRACT_VERSION!r}"
        )
    page = request.get("page") or {}
    image_path = str(page.get("image_path") or "")
    lines = ocr_fn(image_path)
    fields = field_extract.extract_fields(lines)
    raw_text = "\n".join(str(line.get("text") or "") for line in lines)
    record: dict[str, Any] = {
        "service_date": fields["service_date"],
        "name": fields["name"],
        "medical_record_no": fields["medical_record_no"],
        "ocr": {
            "backend": "paddleocr",
            "model": "PP-OCRv5_mobile",
            "raw_text": raw_text,
            "warnings": [],
        },
    }
    return {"contract_version": CONTRACT_VERSION, "record": record}


def _configure_offline_models() -> None:
    # Make PaddleX load models from the bundled cache and never phone home.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    bundled_models = _HERE / "models"
    if bundled_models.is_dir():
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(bundled_models))


def _paddle_ocr_fn(image_path: str) -> list[dict[str, Any]]:
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
    )
    lines: list[dict[str, Any]] = []
    for res in ocr.predict(image_path):
        texts = res.get("rec_texts", [])
        polys = res.get("rec_polys", res.get("dt_polys", []))
        for text, poly in zip(texts, polys):
            box = [[float(pt[0]), float(pt[1])] for pt in poly]
            lines.append({"text": text, "box": box})
    return lines


def main() -> int:
    _configure_offline_models()
    request = json.loads(sys.stdin.read())
    response = run(request, ocr_fn=_paddle_ocr_fn)
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create the manifest**

Create `plugins/paddleocr/plugin.json`:

```json
{
  "contract_version": "ocr_plugin.v1",
  "command": ["python\\Scripts\\python.exe", "main.py"]
}
```

This relative command resolves against the bundle directory (sub-project 1's `PluginOcrBackend` runs the
plugin with `cwd=<plugin dir>`). The build script (Task 3) places the bundled venv at `<plugin>/python/`.

- [ ] **Step 5: Run the test and verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_plugin_run.py -q`
Expected: `2 passed`.

- [ ] **Step 6: Commit**

```powershell
git add plugins/paddleocr/main.py plugins/paddleocr/plugin.json tests/test_paddle_plugin_run.py
git commit -m "feat: add PaddleOCR plugin entry and manifest"
```
(End commit message with the `Co-Authored-By` trailer as above.)

---

## Task 3: Portable offline bundle build + end-to-end verification

**Files:**
- Create: `build/build_paddle_plugin.py`
- Modify: `.gitignore` only if needed (the `dist/` output is already ignored; do not commit the bundle)

This task is empirical: it assembles a runnable offline bundle and proves it works through sub-project 1's
`PluginOcrBackend`. Use the dev paddle venv `.venv-paddle` (already created) as the source venv. Run all
commands with the MAIN `.venv` python EXCEPT where noted.

- [ ] **Step 1: Write the build script**

Create `build/build_paddle_plugin.py`:

```python
"""Assemble a portable, offline PaddleOCR plugin bundle at dist/plugins/paddleocr/.

Bundle layout:
  dist/plugins/paddleocr/
    python/      copy of the paddle venv (.venv-paddle) — interpreter + paddleocr + deps
    models/official_models/<model>/   bundled mobile + textline models
    main.py, field_extract.py, plugin.json

Run with any python: `python build/build_paddle_plugin.py`
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_VENV = REPO / ".venv-paddle"
SRC_PLUGIN = REPO / "plugins" / "paddleocr"
MODELS_SRC = Path.home() / ".paddlex" / "official_models"
NEEDED_MODELS = ["PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec", "PP-LCNet_x1_0_textline_ori"]
OUT = REPO / "dist" / "plugins" / "paddleocr"


def _copy_models(dest_models: Path) -> None:
    for name in NEEDED_MODELS:
        src = MODELS_SRC / name
        if not src.is_dir():
            raise SystemExit(f"Missing model dir (run the plugin once to download it): {src}")
        shutil.copytree(src, dest_models / name, dirs_exist_ok=True)


def main() -> int:
    if not SRC_VENV.is_dir():
        raise SystemExit(f"Missing source venv: {SRC_VENV}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    print(f"copying venv {SRC_VENV} -> {OUT / 'python'} (large, please wait)")
    shutil.copytree(SRC_VENV, OUT / "python", dirs_exist_ok=True)
    _copy_models(OUT / "models" / "official_models")
    for name in ["main.py", "field_extract.py", "plugin.json"]:
        shutil.copy2(SRC_PLUGIN / name, OUT / name)
    print(f"bundle ready: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Ensure the mobile + textline models are present in the dev cache**

If `~/.paddlex/official_models/PP-OCRv5_mobile_det` etc. do not exist yet, run the plugin once with the
dev venv to download them (network required ONCE):

```powershell
$env:PYTHONIOENCODING="utf-8"
echo '{"contract_version":"ocr_plugin.v1","template_id":"service_record.v1","page":{"image_path":"PUT_A_PNG_PATH","document_name":"x.pdf","page_number":1}}' | .venv-paddle\Scripts\python.exe plugins\paddleocr\main.py
```

To produce a test PNG, render the fixture page with the MAIN venv:
```powershell
.venv\Scripts\python.exe -c "import fitz; fitz.open('tests/fixtures/pdf/for testing only.pdf').load_page(0).get_pixmap(dpi=200).save('dist/_form.png')"
```
Use `dist\_form.png` as the `image_path` above. Confirm it prints a JSON response containing
`"service_date": "2026-06-..."`. (This both downloads models and smoke-tests the entry with real paddle.)

- [ ] **Step 3: Build the bundle**

Run: `.venv\Scripts\python.exe build/build_paddle_plugin.py`
Expected: prints "bundle ready: ...dist\plugins\paddleocr". Confirm `dist/plugins/paddleocr/python/Scripts/python.exe`, `dist/plugins/paddleocr/models/official_models/PP-OCRv5_mobile_rec`, and `main.py`/`field_extract.py`/`plugin.json` exist.

- [ ] **Step 4: End-to-end verification through sub-project 1's PluginOcrBackend (offline)**

Render the form page, then drive the built bundle through the real `PluginOcrBackend` using the MAIN venv.
Create and run this one-off check (do NOT commit it; use a temp file or `python -c`):

```powershell
.venv\Scripts\python.exe -c "import fitz; fitz.open('tests/fixtures/pdf/for testing only.pdf').load_page(0).get_pixmap(dpi=200).save('dist/_form.png')"
```

```powershell
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True"
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); from pathlib import Path; from ocr_from2xlsx.domain import SourceInfo; from ocr_from2xlsx.preprocess import PreparedPage; from ocr_from2xlsx.plugin_backend import PluginOcrBackend; p=PreparedPage(image_path=Path('dist/_form.png'), template_id='service_record.v1', source=SourceInfo(kind='pdf_page', document_path='for testing only.pdf', page_number=1, preprocessed_image_path='_form.png', template_id='service_record.v1')); rec=PluginOcrBackend('dist/plugins/paddleocr').extract(p); print('service_date=', rec.get('service_date')); print('backend=', rec.get('ocr',{}).get('backend'))"
```

Expected: prints `service_date= 2025-06-25` (ROC 114 + 1911; or the date the OCR reads) and `backend= paddleocr`.

**If the model still loads from `~/.paddlex` instead of the bundle:** determine the correct PaddleX
cache-home redirect (the env var may differ from `PADDLE_PDX_CACHE_HOME`; check paddlex docs/source for
the official-models lookup) and update `_configure_offline_models()` in `main.py` accordingly, then
re-run Step 4. The acceptance criterion is that the bundle produces a record offline.

- [ ] **Step 5: Verify offline (no network)**

Repeat Step 4's backend command with networking disabled (or rely on
`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` and a bundled cache). Confirm it still returns a record.
Record the observed `service_date` and timing in the commit message / PR.

- [ ] **Step 6: Commit the build script**

```powershell
git add build/build_paddle_plugin.py
git commit -m "feat: add portable PaddleOCR plugin bundle build"
```
(Trailer as above. The built `dist/` bundle is gitignored and not committed.)

**Known limitation to document (not a blocker):** copying a venv keeps `pyvenv.cfg home` pointing at the
build machine's base Python, so the bundle is portable across folders on a machine with the same Python
3.12 install. A fully relocatable bundle (embeddable Python distribution) is a follow-up; note it in the PR.

---

## Task 4: Docs, CHANGELOG, policy

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add a README section**

After the existing "OCR plugin (portable, offline)" section, add:

````markdown
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
added in sub-project 4.
````

- [ ] **Step 2: Update CHANGELOG**

Under `## [Unreleased]` `### Added`:

```markdown
- 新增 PaddleOCR 可攜離線外掛（`plugins/paddleocr/`）：全頁 OCR + 文字錨點擷取服務日期/姓名/病歷號，內嵌 venv + mobile 模型，透過 `ocr_plugin.v1` 契約供主程式呼叫。
- 新增 `build/build_paddle_plugin.py` 組裝可攜外掛 bundle。
```

- [ ] **Step 3: Run tests and policy**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (existing 140 + 11 new pure tests = 151).

Run: `python -m policy_check --repo .`
Expected: no failures. Note: the PaddleOCR-dependent code in `plugins/paddleocr/main.py` `_paddle_ocr_fn`
is not exercised by CI tests (only the pure `run()`/`field_extract` paths are). The real-engine path is
verified manually in Task 3.

- [ ] **Step 4: Commit**

```powershell
git add README.md CHANGELOG.md
git commit -m "docs: document PaddleOCR portable plugin"
```
(Trailer as above.)

---

## Self-Review Notes

- **Spec coverage** (design spec sub-project 2 + concept ④ groundwork): embedded-venv portable bundle (Task 3) ✓; mobile models (Task 2/3) ✓; full-page OCR + text-anchor extraction (Task 1/2) ✓; offline operation (Task 2 `_configure_offline_models`, Task 3 Step 5) ✓; `ocr_plugin.v1` contract reuse (Task 2) ✓; CI-safe tests without paddle (Task 1/2) ✓; real-engine verification via sub-project 1 backend (Task 3 Step 4) ✓.
- **Out of scope (sub-projects 3/4):** full form layout export from the `服務紀錄表` sheet, checkbox/mark detection, and webcam image registration/deskew. This sub-project does text fields only; missing checkbox fields fall to validation → review UI by design.
- **Type consistency:** OCR line shape `{"text": str, "box": [[x,y]*4]}` is identical across `field_extract`, `main.run`, `_paddle_ocr_fn`, and both test files. `run(request, ocr_fn)` and `extract_fields(lines)` signatures match their tests.
- **Risk:** Task 3 (packaging/offline-cache redirect) is empirical; its steps are verify-and-adjust with an explicit acceptance criterion ("bundle produces a record offline") rather than rigid code. The pure logic (Tasks 1-2) is fully TDD and CI-gated.
```
