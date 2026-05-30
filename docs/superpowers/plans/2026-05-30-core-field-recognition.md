# Core Field Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recognize the four core service-record fields the form actually carries — `identity`, `gender` (checkbox marks), `name`, `medical_record_no` (handwriting) — in the PaddleOCR plugin, and let recognized results be written for verification even when incomplete.

**Architecture:** Keep the plugin's pure/testable boundary: pure parsing + choice-resolution live in `field_extract.py` and a new pure mark-scoring core in `mark_detect.py`; PaddleOCR and image I/O stay in the plugin. `run()` gains an injectable `mark_fn(image_path, lines) -> set[str]` (the set of option label texts whose checkbox is marked) so the whole composition is unit-testable with fakes. The CLI `import-json` exposes the existing `ImportSession` `force` path as `--allow-incomplete` for non-blocking verification.

**Tech Stack:** Python 3.12, PaddleOCR 3.6 (plugin), Pillow (plugin image crop), stdlib for pure logic. Pure tests run on the main `.venv`; real-OCR checks use the built bundle / `.venv-paddle`.

---

## Spec Reference

Implements `openspec/changes/fix-core-field-recognition/` (proposal + `specs/record-preparation/spec.md` delta).
Ground truth for the reference form `tests/fixtures/pdf/for testing only.pdf`:
`service_date=2025-06-25, identity=patient, name=葉心安, medical_record_no=6250712919, gender=female`
(confirmed against the image; `葉心安` confirmed by the user).

Key constraints: do not change the `ocr_plugin.v1` record shape or the workbook writer; pure logic must not
import paddle/cv2/PIL; box positions come from runtime OCR (no hard-coded coordinates).

## File Structure

```text
plugins/paddleocr/
  field_extract.py   MODIFY. Add identity/gender resolution from marked labels; improve name/MRN parse;
                     extract_fields(lines, marked_labels) returns all five core fields.
  mark_detect.py     NEW. Pure mark-scoring core (dark-pixel ratio over a 2D grayscale region) +
                     plugin-only image wrapper detect_marked_labels(image_path, lines, labels).
  main.py            MODIFY. run(request, ocr_fn, mark_fn); real mark_fn wraps mark_detect on the page image.
src/ocr_from2xlsx/
  cli.py             MODIFY. import-json: add --allow-incomplete (passes force=True to accept_scan).
tests/
  test_paddle_field_extract.py  MODIFY. name/MRN + identity/gender resolution tests (pure).
  test_mark_detect.py           NEW. pure mark-scoring tests (synthetic 2D arrays).
  test_paddle_plugin_run.py     MODIFY. run() with fake ocr_fn + fake mark_fn yields the full core record.
  test_cli.py                   MODIFY. import-json --allow-incomplete writes a forced row.
  fixtures/pdf/for testing only.groundtruth.json  NEW. core-field ground truth.
README.md / CHANGELOG.md        MODIFY.
```

Pure modules (`field_extract.py`, `mark_detect.py` core) import only stdlib; tests load them by file path
via `importlib` (the established pattern in `tests/test_paddle_field_extract.py`).

---

## Task 1: Handwritten name / medical-record-no parsing (pure)

**Files:**
- Modify: `plugins/paddleocr/field_extract.py`
- Modify: `tests/test_paddle_field_extract.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_paddle_field_extract.py`:

```python
def test_extract_name_and_mrn_from_anchor_row_handwriting():
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("葉心安", x=120, y=50),
        _line("6250712919", x=260, y=50),
    ]
    fields = extract_fields(lines, marked_labels=set())
    assert fields["name"] == "葉心安"
    assert fields["medical_record_no"] == "6250712919"


def test_extract_mrn_when_ocr_merges_label_and_digits():
    # OCR often merges the identity mark + ID into one run like "病人62507..."
    lines = [
        _line("姓名/病歷號", x=0, y=50),
        _line("葉心安", x=120, y=50),
        _line("病人6250712919", x=260, y=50),
    ]
    fields = extract_fields(lines, marked_labels=set())
    assert fields["name"] == "葉心安"
    assert fields["medical_record_no"] == "6250712919"
```

(Also update existing `extract_fields(lines)` calls in this file to `extract_fields(lines, marked_labels=set())` — `marked_labels` is a new required argument added in Task 3; for Task 1 add it with a default of `set()` so these tests pass now and Task 3 tightens behavior.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_field_extract.py -q -k "anchor_row_handwriting or merges_label"`
Expected: FAIL (extract_fields signature / digit-run parse not present).

- [ ] **Step 3: Implement**

In `plugins/paddleocr/field_extract.py`:

- Add a digit-run extractor and make `extract_name_and_mrn` gather ALL same-row candidates (not just the first), then pick the longest CJK run as the name and the longest digit run (length >= 6) as the MRN, ignoring the `_NAME_NOISE` label fragments for the name but still mining digits for the MRN:

```python
import re  # already imported

_DIGIT_RUN = re.compile(r"\d{6,}")


def _name_from_candidates(texts: list[str]) -> str | None:
    best = ""
    for text in texts:
        if any(token in text for token in _NAME_NOISE):
            continue
        cjk = "".join(ch for ch in text if _has_cjk(ch))
        if len(cjk) > len(best):
            best = cjk
    return best or None


def _mrn_from_candidates(texts: list[str]) -> str | None:
    best = ""
    for text in texts:
        for run in _DIGIT_RUN.findall(text):
            if len(run) > len(best):
                best = run
    return best or None
```

Rewrite `extract_name_and_mrn(lines)` to collect the same-row candidate texts (reuse the existing
anchor + `cx > ax` and `abs(cy-ay) <= 15` gathering), then `return (_name_from_candidates(texts), _mrn_from_candidates(texts))`.

Update `extract_fields` signature to `extract_fields(lines, marked_labels)` (add `marked_labels` param now;
identity/gender wired in Task 3). For Task 1 it may ignore `marked_labels`:

```python
def extract_fields(lines, marked_labels=None):
    name, mrn = extract_name_and_mrn(lines)
    return {
        "service_date": extract_service_date(lines),
        "name": name,
        "medical_record_no": mrn,
        "identity": "",   # populated in Task 3
        "gender": "",     # populated in Task 3
    }
```

Note `_has_cjk` already exists; `_name_from_candidates` uses it per-character.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_field_extract.py -q`
Expected: all pass (including the two new tests and updated existing ones).

- [ ] **Step 5: Commit**

```powershell
git add plugins/paddleocr/field_extract.py tests/test_paddle_field_extract.py
git commit -m "feat: parse handwritten name and medical-record-no"
```
End every commit message with a blank line then exactly:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## Task 2: Mark-scoring core (pure, no image library)

**Files:**
- Create: `plugins/paddleocr/mark_detect.py`
- Create: `tests/test_mark_detect.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_mark_detect.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "mark_detect.py"
_spec = importlib.util.spec_from_file_location("paddle_mark_detect", _MODULE)
mark_detect = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(mark_detect)

dark_ratio = mark_detect.dark_ratio
is_marked = mark_detect.is_marked


def _filled(w, h, value):
    return [[value for _ in range(w)] for _ in range(h)]


def test_dark_ratio_all_dark_is_one():
    assert dark_ratio(_filled(4, 4, 0)) == 1.0


def test_dark_ratio_all_light_is_zero():
    assert dark_ratio(_filled(4, 4, 255)) == 0.0


def test_is_marked_true_for_inked_region():
    region = _filled(10, 10, 255)
    for r in range(10):
        for c in range(4):  # a vertical stroke ~ a tick
            region[r][c] = 0
    assert is_marked(region) is True


def test_is_marked_false_for_empty_box():
    region = _filled(10, 10, 255)
    # thin border only (an empty printed box), below the marked threshold
    for c in range(10):
        region[0][c] = 0
        region[9][c] = 0
    for r in range(10):
        region[r][0] = 0
        region[r][9] = 0
    assert is_marked(region) is False


def test_is_marked_handles_empty_region():
    assert is_marked([]) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mark_detect.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the pure core**

Create `plugins/paddleocr/mark_detect.py`:

```python
"""Checkbox mark detection.

Pure core: score a grayscale region (2D list/sequence of 0-255 luminance) for ink.
Plugin wrapper (image I/O via Pillow) is below and is NOT exercised by CI tests.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

DARK_THRESHOLD = 128      # luminance below this counts as ink
MARKED_RATIO = 0.12       # fraction of dark pixels above which a region is "marked"


def dark_ratio(region: Sequence[Sequence[float]], dark_threshold: int = DARK_THRESHOLD) -> float:
    total = 0
    dark = 0
    for row in region:
        for value in row:
            total += 1
            if value < dark_threshold:
                dark += 1
    if total == 0:
        return 0.0
    return dark / total


def is_marked(
    region: Sequence[Sequence[float]],
    dark_threshold: int = DARK_THRESHOLD,
    marked_ratio: float = MARKED_RATIO,
) -> bool:
    return dark_ratio(region, dark_threshold) >= marked_ratio
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_mark_detect.py -q`
Expected: `5 passed`. (`MARKED_RATIO=0.12`: the vertical-stroke region is 40% dark → marked; the border-only box is ~36/100=0.36 ... ensure the empty-box test stays below threshold — if a thin 1px border on a 10x10 exceeds 0.12, make the empty-box test border represent a realistic faint box by using value 200 for the border instead of 0. Adjust the test border value to 200 so it is above DARK_THRESHOLD and the empty box scores 0.0.)

Correction to the empty-box test (use a light border so it models a faint printed box):

```python
def test_is_marked_false_for_empty_box():
    region = _filled(10, 10, 255)
    for c in range(10):
        region[0][c] = 200
        region[9][c] = 200
    for r in range(10):
        region[r][0] = 200
        region[r][9] = 200
    assert is_marked(region) is False
```

- [ ] **Step 5: Commit**

```powershell
git add plugins/paddleocr/mark_detect.py tests/test_mark_detect.py
git commit -m "feat: add pure checkbox mark-scoring core"
```

---

## Task 3: Identity / gender resolution from marked labels (pure)

**Files:**
- Modify: `plugins/paddleocr/field_extract.py`
- Modify: `tests/test_paddle_field_extract.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_paddle_field_extract.py`:

```python
def test_extract_identity_and_gender_from_marked_labels():
    lines = [
        _line("病人", x=10, y=50),
        _line("親友及照顧者", x=120, y=50),
        _line("一般民眾及其他", x=260, y=50),
        _line("女性", x=10, y=80),
        _line("男性", x=120, y=80),
    ]
    fields = extract_fields(lines, marked_labels={"病人", "女性"})
    assert fields["identity"] == "patient"
    assert fields["gender"] == "female"


def test_unmarked_identity_gender_stay_empty():
    lines = [_line("病人", x=10, y=50), _line("女性", x=10, y=80)]
    fields = extract_fields(lines, marked_labels=set())
    assert fields["identity"] == ""
    assert fields["gender"] == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_field_extract.py -q -k "marked_labels"`
Expected: FAIL (identity/gender stay "" because Task 1 stubbed them).

- [ ] **Step 3: Implement**

In `plugins/paddleocr/field_extract.py` add the dictionaries and resolver, and wire `extract_fields`:

```python
IDENTITY_BY_LABEL = {
    "病人": "patient",
    "親友及照顧者": "family_caregiver",
    "一般民眾及其他": "public_other",
}
GENDER_BY_LABEL = {
    "女性": "female",
    "男性": "male",
}


def _resolve_choice(marked_labels, mapping):
    for label, code in mapping.items():
        if label in marked_labels:
            return code
    return ""


def extract_identity(marked_labels) -> str:
    return _resolve_choice(marked_labels or set(), IDENTITY_BY_LABEL)


def extract_gender(marked_labels) -> str:
    return _resolve_choice(marked_labels or set(), GENDER_BY_LABEL)
```

Update `extract_fields` to populate identity/gender:

```python
def extract_fields(lines, marked_labels=None):
    name, mrn = extract_name_and_mrn(lines)
    return {
        "service_date": extract_service_date(lines),
        "name": name,
        "medical_record_no": mrn,
        "identity": extract_identity(marked_labels),
        "gender": extract_gender(marked_labels),
    }
```

Note: gender 其他 is intentionally omitted (bare "其他" collides with Section A options). 女性/男性 and the
three identity labels are unambiguous full strings. Gender-other is deferred (recorded in the spec scope).

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_field_extract.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add plugins/paddleocr/field_extract.py tests/test_paddle_field_extract.py
git commit -m "feat: resolve identity and gender from marked labels"
```

---

## Task 4: Plugin composition + image ink-probe wrapper

**Files:**
- Modify: `plugins/paddleocr/main.py`
- Modify: `plugins/paddleocr/mark_detect.py`
- Modify: `tests/test_paddle_plugin_run.py`

- [ ] **Step 1: Write failing test for `run` with mark_fn**

Replace the body of `test_run_builds_contract_response_with_extracted_fields` in
`tests/test_paddle_plugin_run.py` and add a fake `mark_fn`:

```python
def _fake_ocr_fn(image_path):
    def line(text, x=0.0, y=0.0):
        return {"text": text, "box": [[x, y], [x + 50, y], [x + 50, y + 10], [x, y + 10]]}

    return [
        line("癌症資源中心服務紀錄表", y=0),
        line("服務年/月/日：114.06.25", y=20),
        line("姓名/病歷號", x=0, y=50),
        line("葉心安", x=120, y=50),
        line("6250712919", x=260, y=50),
        line("病人", x=10, y=80),
        line("女性", x=10, y=110),
    ]


def _fake_mark_fn(image_path, lines):
    return {"病人", "女性"}


def test_run_builds_contract_response_with_extracted_fields():
    request = {
        "contract_version": CONTRACT,
        "template_id": "service_record.v1",
        "page": {"image_path": "ignored.png", "document_name": "scan.pdf", "page_number": 1},
    }

    response = run(request, ocr_fn=_fake_ocr_fn, mark_fn=_fake_mark_fn)

    record = response["record"]
    assert record["service_date"] == "2025-06-25"
    assert record["identity"] == "patient"
    assert record["gender"] == "female"
    assert record["name"] == "葉心安"
    assert record["medical_record_no"] == "6250712919"
    assert record["ocr"]["backend"] == "paddleocr"
```

Keep `test_run_rejects_wrong_contract_version`, but update its `run(...)` call to pass `mark_fn=_fake_mark_fn`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_plugin_run.py -q`
Expected: FAIL (run signature lacks mark_fn; identity/gender not set).

- [ ] **Step 3: Implement `run` + image wrapper**

In `plugins/paddleocr/main.py`, change `run` to accept and use `mark_fn`:

```python
def run(request, ocr_fn, mark_fn):
    if request.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported contract_version: {request.get('contract_version')!r}; "
            f"expected {CONTRACT_VERSION!r}"
        )
    page = request.get("page") or {}
    image_path = str(page.get("image_path") or "")
    lines = ocr_fn(image_path)
    marked_labels = mark_fn(image_path, lines)
    fields = field_extract.extract_fields(lines, marked_labels)
    raw_text = "\n".join(str(line.get("text") or "") for line in lines)
    record = {
        "service_date": fields["service_date"],
        "identity": fields["identity"],
        "name": fields["name"],
        "medical_record_no": fields["medical_record_no"],
        "gender": fields["gender"],
        "ocr": {
            "backend": "paddleocr",
            "model": "PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec",
            "raw_text": raw_text,
            "warnings": [],
        },
    }
    return {"contract_version": CONTRACT_VERSION, "record": record}
```

Add the real mark function to `main.py` (loads `mark_detect` as a sibling like `field_extract`):

```python
_MD_SPEC = _importlib_util.spec_from_file_location(
    "paddleocr_plugin_mark_detect", _HERE / "mark_detect.py"
)
mark_detect = _importlib_util.module_from_spec(_MD_SPEC)
assert _MD_SPEC and _MD_SPEC.loader
_MD_SPEC.loader.exec_module(mark_detect)
```

and update `main()` to use `mark_detect.detect_marked_labels` as `mark_fn`:

```python
    response = run(request, ocr_fn=_paddle_ocr_fn, mark_fn=mark_detect.detect_marked_labels)
```

In `plugins/paddleocr/mark_detect.py` add the plugin-only image wrapper (Pillow; not CI-tested). It probes
the checkbox region immediately left of each known option label and returns the set of marked label texts:

```python
_PROBE_LABELS = ("病人", "親友及照顧者", "一般民眾及其他", "女性", "男性")


def _line_bbox(line: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in line["box"]]
    ys = [pt[1] for pt in line["box"]]
    return (min(xs), min(ys), max(xs), max(ys))


def detect_marked_labels(image_path: str, lines: list[dict[str, Any]]) -> set[str]:
    from PIL import Image

    image = Image.open(image_path).convert("L")
    width, height = image.size
    marked: set[str] = set()
    for line in lines:
        text = str(line.get("text") or "")
        label = next((lbl for lbl in _PROBE_LABELS if lbl in text), None)
        if label is None:
            continue
        x0, y0, x1, y1 = _line_bbox(line)
        box_h = max(1.0, y1 - y0)
        # checkbox sits just left of the label; probe a square ~ the text height
        px1 = max(0, int(x0))
        px0 = max(0, int(x0 - box_h * 1.4))
        py0 = max(0, int(y0))
        py1 = min(height, int(y1))
        if px1 <= px0 or py1 <= py0:
            continue
        crop = image.crop((px0, py0, px1, py1))
        region = [list(crop.getdata())[r * crop.width:(r + 1) * crop.width] for r in range(crop.height)]
        if is_marked(region):
            marked.add(label)
    return marked
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paddle_plugin_run.py -q`
Expected: `2 passed` (fake-driven; no paddle, no Pillow needed in CI).

- [ ] **Step 5: Run full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add plugins/paddleocr/main.py plugins/paddleocr/mark_detect.py tests/test_paddle_plugin_run.py
git commit -m "feat: compose plugin record with checkbox mark detection"
```

---

## Task 5: Non-blocking verification via import-json --allow-incomplete

**Files:**
- Modify: `src/ocr_from2xlsx/cli.py`
- Modify: `tests/test_cli.py`

Background: `ImportSession.accept_scan(record, force=True)` already writes records whose blockers are all
"writable" (e.g. missing patient fields) as `forced`, while still refusing records with non-writable
blockers (`service_date.invalid`, `identity.invalid`, `gender.invalid`, `service.*`). Exposing `force`
gives the non-blocking verification path without new validation logic.

- [ ] **Step 1: Write failing CLI test**

Add to `tests/test_cli.py`:

```python
def test_import_json_allow_incomplete_writes_forced_row(tmp_path):
    import json as _json
    from pathlib import Path as _Path
    from openpyxl import load_workbook
    from ocr_from2xlsx.cli import main
    from ocr_from2xlsx.constants import WORKBOOK_SHEET, BASIC_COLUMN_BY_FIELD
    from tests.fixtures import create_workbook_template

    template = tmp_path / "t.xlsx"
    working = tmp_path / "w.xlsx"
    create_workbook_template(template)

    # A patient record missing patient-only fields -> writable blockers only.
    batch = {
        "schema_version": "service_record.v1",
        "source_batch": {"created_at": "2026-05-26T00:00:00+08:00", "source_type": "manual", "template_name": "t"},
        "records": [{
            "record_id": "pdf-0001", "service_date": "2025-06-25", "identity": "patient",
            "name": "葉心安", "medical_record_no": "6250712919", "gender": "female",
        }],
    }
    inp = tmp_path / "in.json"
    inp.write_text(_json.dumps(batch), encoding="utf-8")

    code = main([
        "import-json", "--input", str(inp), "--template", str(template), "--working", str(working),
        "--report-json", str(tmp_path / "r.json"), "--report-csv", str(tmp_path / "r.csv"),
        "--allow-incomplete",
    ])

    assert code == 0
    wb = load_workbook(working)
    ws = wb[WORKBOOK_SHEET]
    name_col = next(c.column for c in ws[1] if c.value == BASIC_COLUMN_BY_FIELD["name"])
    assert ws.cell(row=2, column=name_col).value == "葉心安"
    wb.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -k allow_incomplete`
Expected: FAIL (`--allow-incomplete` unknown; or row not written).

- [ ] **Step 3: Implement**

In `src/ocr_from2xlsx/cli.py`, add to the `import-json` subparser:

```python
    import_parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Write recognized records even if non-critical required fields are missing (forced write).",
    )
```

In the `import-json` branch of `main()`, pass force through the accept call:

```python
                    result = session.accept_scan(record, force=args.allow_incomplete)
```

(Locate the existing `session.accept_scan(record)` call and add `force=args.allow_incomplete`.)
Return-code note: a `forced` write is success; the branch already returns `1` only when there were
blocked records. With `--allow-incomplete`, a record that previously blocked on writable blockers becomes
`forced` (not `blocked`), so the command returns 0 and the report shows status `forced` with the gaps listed.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -k allow_incomplete`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run: `.venv\Scripts\python.exe -m pytest -q` (expect all pass; default import-json behavior unchanged).

```powershell
git add src/ocr_from2xlsx/cli.py tests/test_cli.py
git commit -m "feat: add import-json --allow-incomplete verification path"
```

---

## Task 6: Ground-truth fixture + real-OCR verification (empirical)

**Files:**
- Create: `tests/fixtures/pdf/for testing only.groundtruth.json`
- Create: `tests/test_core_field_groundtruth.py`

- [ ] **Step 1: Add the ground-truth fixture**

Create `tests/fixtures/pdf/for testing only.groundtruth.json`:

```json
{
  "service_date": "2025-06-25",
  "identity": "patient",
  "name": "葉心安",
  "medical_record_no": "6250712919",
  "gender": "female"
}
```

- [ ] **Step 2: Add an optional-marker real-OCR test**

Create `tests/test_core_field_groundtruth.py`:

```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_PADDLE_OCR") != "1",
    reason="real PaddleOCR bundle test; set RUN_PADDLE_OCR=1 and build dist/plugins/paddleocr",
)


def test_reference_form_matches_ground_truth(tmp_path):
    import fitz  # rendering needs the main venv's PyMuPDF
    sys.path.insert(0, "src")
    from ocr_from2xlsx.domain import SourceInfo
    from ocr_from2xlsx.preprocess import PreparedPage
    from ocr_from2xlsx.plugin_backend import PluginOcrBackend

    repo = Path(__file__).resolve().parents[1]
    pdf = repo / "tests" / "fixtures" / "pdf" / "for testing only.pdf"
    img = tmp_path / "form.png"
    fitz.open(pdf).load_page(0).get_pixmap(dpi=200).save(img)

    page = PreparedPage(
        image_path=img, template_id="service_record.v1",
        source=SourceInfo(kind="pdf_page", document_path=str(pdf), page_number=1,
                          preprocessed_image_path=img.name, template_id="service_record.v1"),
    )
    rec = PluginOcrBackend(str(repo / "dist" / "plugins" / "paddleocr")).extract(page)
    gold = json.loads((repo / "tests" / "fixtures" / "pdf" / "for testing only.groundtruth.json").read_text(encoding="utf-8"))
    for key, expected in gold.items():
        assert rec.get(key) == expected, f"{key}: got {rec.get(key)!r}, want {expected!r}"
```

- [ ] **Step 3: Build the bundle and run the real verification manually**

```powershell
.venv\Scripts\python build/build_paddle_plugin.py
$env:RUN_PADDLE_OCR="1"
.venv\Scripts\python -m pytest tests/test_core_field_groundtruth.py -q
```

Expected: PASS — the plugin's recognition of the reference form equals the ground truth, field by field.

**If a field does not match** (esp. handwritten `name`, which depends on PaddleOCR reading 葉心安): record
the actual recognized value, and either (a) tune the mark probe / parse for that field, or (b) if real OCR
cannot read the handwriting at 200 dpi, raise render DPI for the plugin or note the field as review-only in
the proposal's risks. Do NOT weaken the ground truth to make the test pass. If `name` proves unreadable by
the mobile recognizer, report back to the controller with the observed OCR text before deciding.

- [ ] **Step 4: Commit**

```powershell
git add "tests/fixtures/pdf/for testing only.groundtruth.json" tests/test_core_field_groundtruth.py
git commit -m "test: add core-field ground truth and real-OCR verification"
```

---

## Task 7: Docs, policy, integration

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: README** — under the PaddleOCR plugin section, add a short paragraph: the plugin now
recognizes identity/gender via checkbox mark detection (ink probe left of each option label, positions from
runtime OCR) and handwritten name/medical-record-no; `import-json --allow-incomplete` writes recognized
records for verification even when patient-only fields are missing.

- [ ] **Step 2: CHANGELOG** — add under `## [Unreleased]`:

```markdown
### Added
- PaddleOCR 外掛新增身分/性別打勾辨識（文字錨點 + 框內墨跡）與手寫姓名/病歷號擷取。
- `import-json --allow-incomplete`：辨識到的記錄即使缺病人限定欄位也可寫入（forced）以供核對。
```

- [ ] **Step 3: Tests + policy**

```powershell
.venv\Scripts\python -W error -m pytest -q
.venv\Scripts\python build/package.py
python -m policy_check --repo .
```
Expected: all pass; policy 0 failures. (The real-OCR test stays skipped without `RUN_PADDLE_OCR=1`.)

- [ ] **Step 4: Commit**

```powershell
git add README.md CHANGELOG.md
git commit -m "docs: document checkbox recognition and verification path"
```

---

## Self-Review Notes

- **Spec coverage:** identity/gender mark recognition (Tasks 2-4) ✓; ink probe + OCR-anomaly secondary
  signal — ink probe in Task 4 ✓ (OCR-anomaly secondary signal is optional hardening, not required for the
  reference form; note: not separately implemented — acceptable as the spec says MAY). handwritten name/MRN
  (Task 1) ✓; non-blocking verification path (Task 5) ✓; ground-truth regression (Task 6) ✓.
- **Type consistency:** `extract_fields(lines, marked_labels)` used consistently in Tasks 1/3/4 and tests;
  `mark_fn(image_path, lines) -> set[str]`, `detect_marked_labels(image_path, lines)`, `is_marked(region)`
  consistent across Tasks 2/4.
- **Known risk (flagged in Task 6):** the mobile recognizer may not read the handwritten `name` 葉心安 at
  200 dpi. Task 6 makes this an explicit, honest verification gate rather than assuming success; the
  `--allow-incomplete` path still surfaces whatever is recognized.
- **OCR-anomaly secondary signal:** the spec lists it as MAY (optional). If the ink probe alone misreads
  the reference form, add it during Task 4 as a fallback (a label line that lost its `□` or whose text
  starts with `中`/`V` counts as marked).
```
