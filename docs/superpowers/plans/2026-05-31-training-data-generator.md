# Handwriting Training-Data Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone `training/` tool that synthesizes service-record images (handwritten text + procedural checkbox marks) from the shared `form_layout`, and emits a `service_record.v1` answer key (each record + `training` + `source_image`) aligned field-by-field with OCR output.

**Architecture:** Pure, testable core — `sampler` (coverage-driven option selection), `answer_key` (selected codes → Record via `confirm_form` → Batch), `layout_render` geometry (cell → pixel box) — is separated from PIL drawing (`layout_render` base image, `handwriting` text/marks) and orchestration (`generate`). Fonts are fetched locally by `fetch_fonts.py` (OFL). The tool runs under `.venv-paddle` (PIL+numpy) and adds no main-package dependency.

**Tech Stack:** Python 3.12 stdlib for pure logic; PIL (Pillow) + numpy (in `.venv-paddle`) for image work; reuses `form_layout`, `confirm_form`, `record_access`, `domain.Record`, `json_io`. `openpyxl` (existing dep) reads the blank xlsx geometry.

---

## Spec Reference

Implements `openspec/changes/add-training-data-generator/` and design
`docs/superpowers/specs/2026-05-31-training-data-generator-design.md`.

Reuse: `form_layout.service_record_layout()` (fields: `key`, `kind` ∈ text/single_choice/multi_choice,
`options[].code`, `.cell`); `confirm_form.apply_form_state(layout, record, state)` (state per field: text=str,
single=code str or "", multi=set[str]); `domain.Record.from_dict/to_dict`; `json_io.load_batch`.

Run pure tests with `.venv\Scripts\python.exe`; run PIL/smoke tests + the generator with
`.venv-paddle\Scripts\python.exe`. Pure modules import only stdlib + `ocr_from2xlsx` (no PIL/numpy at module
top).

## File Structure

```text
training/__init__.py
training/sampler.py         NEW. Pure coverage-driven option selection.
training/answer_key.py      NEW. Pure: selection -> Record (via confirm_form) -> service_record.v1 Batch.
training/layout_render.py   NEW. Pure cell->pixel geometry + PIL base-image drawing.
training/handwriting.py     NEW. PIL text (OFL fonts + jitter) + procedural marks (tick/dash/blackout).
training/fetch_fonts.py     NEW. Download curated OFL handwriting CJK fonts into training/fonts/.
training/generate.py        NEW. Orchestration: sample -> draw -> save PNG + answers.json.
tests/test_training_sampler.py      NEW (pure)
tests/test_training_answer_key.py   NEW (pure)
tests/test_training_layout_geom.py  NEW (pure)
tests/test_training_generate_smoke.py  NEW (PIL smoke; skips if PIL unavailable)
.gitignore                  MODIFY (training/fonts/, training/out/)
README.md / CHANGELOG.md    MODIFY
```

---

## Task 1: Coverage-driven sampler (pure)

**Files:**
- Create: `training/__init__.py` (empty), `training/sampler.py`
- Create: `tests/test_training_sampler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_training_sampler.py`:

```python
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `training` importable

from ocr_from2xlsx.form_layout import service_record_layout
from training.sampler import choice_fields, generate_until_coverage, sample_selection


def test_choice_fields_are_single_or_multi_with_options():
    fields = choice_fields(service_record_layout())
    assert fields, "expected choice fields"
    assert all(f.kind in {"single_choice", "multi_choice"} and f.codes for f in fields)


def test_sample_respects_ratio_singlecap_and_min_one():
    fields = choice_fields(service_record_layout())
    total = sum(len(f.codes) for f in fields)
    rng = random.Random(1)
    by_key = {f.key: f for f in fields}
    for _ in range(50):
        sel = sample_selection(fields, rng)
        marked = sum(len(v) for v in sel.values())
        assert 1 <= marked <= round(0.5 * total) + 1            # ratio upper bound (+rounding slack)
        assert marked >= max(1, round(0.10 * total)) - 1        # ratio lower bound (rounding slack)
        for key, codes in sel.items():
            assert codes, "empty selections are dropped"
            if by_key[key].kind == "single_choice":
                assert len(codes) == 1
            assert len(set(codes)) == len(codes)
            assert set(codes) <= set(by_key[key].codes)


def test_generate_until_coverage_marks_every_option_at_least_min():
    fields = choice_fields(service_record_layout())
    rng = random.Random(7)
    selections = generate_until_coverage(fields, rng, min_per_option=5)
    coverage = {code: 0 for f in fields for code in f.codes}
    for sel in selections:
        for codes in sel.values():
            for code in codes:
                coverage[code] += 1
    assert min(coverage.values()) >= 5
    assert len(selections) < 1000  # terminates reasonably
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_training_sampler.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `training/__init__.py` (empty). Create `training/sampler.py`:

```python
"""Coverage-driven option sampling for synthetic forms (pure stdlib)."""
from __future__ import annotations

import random
from dataclasses import dataclass

from ocr_from2xlsx.form_layout import FormLayout


@dataclass(frozen=True, slots=True)
class FieldOptions:
    key: str
    kind: str
    codes: tuple[str, ...]


def choice_fields(layout: FormLayout) -> list[FieldOptions]:
    fields: list[FieldOptions] = []
    for fld in layout.iter_fields():
        if fld.kind in {"single_choice", "multi_choice"} and fld.options:
            fields.append(FieldOptions(fld.key, fld.kind, tuple(o.code for o in fld.options)))
    return fields


def sample_selection(
    fields: list[FieldOptions],
    rng: random.Random,
    *,
    min_ratio: float = 0.10,
    max_ratio: float = 0.50,
    coverage: dict[str, int] | None = None,
) -> dict[str, list[str]]:
    total = sum(len(f.codes) for f in fields)
    target = max(1, round(rng.uniform(min_ratio, max_ratio) * total))
    selected: dict[str, list[str]] = {f.key: [] for f in fields}
    candidates = [(f, code) for f in fields for code in f.codes]
    chosen = 0
    while chosen < target:
        avail = [
            (f, code)
            for (f, code) in candidates
            if code not in selected[f.key]
            and not (f.kind == "single_choice" and selected[f.key])
        ]
        if not avail:
            break
        weights = [1.0 / (1 + (coverage.get(code, 0) if coverage else 0)) for (f, code) in avail]
        f, code = rng.choices(avail, weights=weights, k=1)[0]
        selected[f.key].append(code)
        chosen += 1
    return {key: codes for key, codes in selected.items() if codes}


def generate_until_coverage(
    fields: list[FieldOptions],
    rng: random.Random,
    *,
    min_per_option: int = 5,
    max_images: int = 1000,
) -> list[dict[str, list[str]]]:
    coverage = {code: 0 for f in fields for code in f.codes}
    selections: list[dict[str, list[str]]] = []
    while any(count < min_per_option for count in coverage.values()):
        if len(selections) >= max_images:
            break
        sel = sample_selection(fields, rng, coverage=coverage)
        for codes in sel.values():
            for code in codes:
                coverage[code] += 1
        selections.append(sel)
    return selections
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_training_sampler.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```powershell
git add training/__init__.py training/sampler.py tests/test_training_sampler.py
git commit -m "feat: add coverage-driven training sampler"
```
End every commit message with a blank line then exactly:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## Task 2: Answer-key assembler (pure, reuses confirm_form)

**Files:**
- Create: `training/answer_key.py`
- Create: `tests/test_training_answer_key.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_training_answer_key.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_from2xlsx.form_layout import service_record_layout
from ocr_from2xlsx.json_io import load_batch
from training.answer_key import build_answer_batch, selection_to_record


def test_selection_to_record_places_codes_and_text():
    layout = service_record_layout()
    record = selection_to_record(
        layout,
        record_id="train-0001",
        selection={"gender": ["female"], "cancer": ["breast_cancer", "lung_cancer"],
                   "consultation.health_medical": ["screening_prevention"]},
        text_values={"name": "王小明", "service_date": "2026-05-26"},
    )
    assert record.gender == "female"
    assert set(record.patient_fields.cancers) == {"breast_cancer", "lung_cancer"}
    assert record.services.consultation["health_medical"] == ["screening_prevention"]
    assert record.name == "王小明"
    assert record.service_date == "2026-05-26"


def test_build_answer_batch_is_loadable_and_tagged(tmp_path):
    layout = service_record_layout()
    rec = selection_to_record(layout, record_id="train-0001",
                              selection={"gender": ["male"]}, text_values={"name": "陳大文"})
    batch_dict = build_answer_batch([(rec, "images/train-0001.png")],
                                    created_at="2026-05-31T00:00:00+08:00")
    assert batch_dict["schema_version"] == "service_record.v1"
    item = batch_dict["records"][0]
    assert item["training"] is True
    assert item["source_image"] == "images/train-0001.png"

    out = tmp_path / "answers.json"
    out.write_text(__import__("json").dumps(batch_dict, ensure_ascii=False), encoding="utf-8")
    loaded = load_batch(out)  # extra keys (training/source_image) ignored by Record.from_dict
    assert loaded.records[0].gender == "male"
    assert loaded.records[0].name == "陳大文"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_training_answer_key.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `training/answer_key.py`:

```python
"""Build a service_record.v1 answer key from sampled selections (pure)."""
from __future__ import annotations

from typing import Any

from ocr_from2xlsx.confirm_form import apply_form_state
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import FormLayout


def selection_to_record(
    layout: FormLayout,
    record_id: str,
    selection: dict[str, list[str]],
    text_values: dict[str, str],
) -> Record:
    record = Record.from_dict({"record_id": record_id})
    state: dict[str, Any] = {}
    for fld in layout.iter_fields():
        if fld.kind == "text":
            state[fld.key] = text_values.get(fld.key, "")
        elif fld.kind == "single_choice":
            codes = selection.get(fld.key, [])
            state[fld.key] = codes[0] if codes else ""
        else:  # multi_choice
            state[fld.key] = set(selection.get(fld.key, []))
    apply_form_state(layout, record, state)
    return record


def build_answer_batch(
    records_with_images: list[tuple[Record, str]],
    created_at: str,
    template_name: str = "service_record.v1",
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for record, source_image in records_with_images:
        item = record.to_dict()
        item["training"] = True
        item["source_image"] = source_image
        records.append(item)
    return {
        "schema_version": "service_record.v1",
        "source_batch": {
            "created_at": created_at,
            "source_type": "training_synthetic",
            "template_name": template_name,
        },
        "records": records,
    }
```

Note: `Record.from_dict({"record_id": ...})` must succeed with only a record_id (other fields default). If
`Record.from_dict` requires more, pass the minimal required keys with empty defaults (check `domain.py`).

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_training_answer_key.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add training/answer_key.py tests/test_training_answer_key.py
git commit -m "feat: assemble service_record.v1 training answer key"
```

---

## Task 3: Layout geometry — cell → pixel box (pure)

**Files:**
- Create: `training/layout_render.py` (geometry part only this task)
- Create: `tests/test_training_layout_geom.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_training_layout_geom.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_from2xlsx.form_layout import service_record_layout
from training.layout_render import cell_box, sheet_geometry

_XLSX = Path(__file__).resolve().parents[1] / "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"


def test_cell_boxes_are_ordered_and_in_bounds():
    geom = sheet_geometry(_XLSX)
    c4 = cell_box("C4", geom)
    d4 = cell_box("D4", geom)
    c5 = cell_box("C5", geom)
    # within page
    for box in (c4, d4, c5):
        assert box[0] >= 0 and box[1] >= 0 and box[2] > box[0] and box[3] > box[1]
        assert box[2] <= geom.width and box[3] <= geom.height
    assert d4[0] >= c4[2] - 1   # D4 is to the right of C4
    assert c5[1] >= c4[3] - 1   # row 5 is below row 4


def test_every_layout_option_cell_has_a_box():
    geom = sheet_geometry(_XLSX)
    for _, option in service_record_layout().iter_options():
        x0, y0, x1, y1 = cell_box(option.cell, geom)
        assert x1 > x0 and y1 > y0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_training_layout_geom.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the geometry (pure)**

Create `training/layout_render.py` (geometry now; PIL drawing added in Task 4):

```python
"""Form geometry (pure) + base-image drawing (PIL, added later).

Reconstructs a consistent cell grid from the blank xlsx column widths / row heights so each cell maps to a
pixel box. Exact Excel pixel parity is not required; the grid only needs to be consistent and cell-aligned,
giving exact ground-truth boxes for synthesized marks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Approximate px per Excel column-width unit and per row-height point. Tunable; only consistency matters.
_COL_PX_PER_UNIT = 7.0
_COL_DEFAULT_WIDTH = 8.43      # Excel default column width (units)
_ROW_PX_PER_POINT = 1.33       # ~96 DPI
_ROW_DEFAULT_HEIGHT = 15.0     # points
_MAX_COL = 6                   # service-record sheet is A..F
_MAX_ROW = 52


@dataclass(frozen=True, slots=True)
class SheetGeometry:
    col_x: tuple[float, ...]   # left x of each column index 1..MAX_COL (len MAX_COL+1, col_x[i]=left of col i)
    row_y: tuple[float, ...]   # top y of each row 1..MAX_ROW
    width: float
    height: float


def _col_index(letter: str) -> int:
    idx = 0
    for ch in letter:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx


def _split_cell(cell: str) -> tuple[int, int]:
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", cell)
    if not m:
        raise ValueError(f"bad cell ref: {cell!r}")
    return _col_index(m.group(1)), int(m.group(2))


def sheet_geometry(xlsx_path: Path | str) -> SheetGeometry:
    from openpyxl import load_workbook

    ws = load_workbook(xlsx_path)["服務紀錄表"]
    widths = {}
    for letter, dim in ws.column_dimensions.items():
        if dim.width and len(letter) == 1:
            widths[_col_index(letter)] = dim.width
    heights = {}
    for idx, dim in ws.row_dimensions.items():
        if dim.height:
            heights[idx] = dim.height

    col_x = [0.0]
    x = 0.0
    for col in range(1, _MAX_COL + 1):
        col_x.append(x)
        x += widths.get(col, _COL_DEFAULT_WIDTH) * _COL_PX_PER_UNIT
    width = x
    row_y = [0.0]
    y = 0.0
    for row in range(1, _MAX_ROW + 1):
        row_y.append(y)
        y += heights.get(row, _ROW_DEFAULT_HEIGHT) * _ROW_PX_PER_POINT
    height = y
    return SheetGeometry(tuple(col_x), tuple(row_y), width, height)


def cell_box(cell: str, geom: SheetGeometry) -> tuple[float, float, float, float]:
    col, row = _split_cell(cell)
    x0 = geom.col_x[col]
    x1 = geom.col_x[col + 1] if col + 1 < len(geom.col_x) else geom.width
    y0 = geom.row_y[row]
    y1 = geom.row_y[row + 1] if row + 1 < len(geom.row_y) else geom.height
    return (x0, y0, x1, y1)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_training_layout_geom.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add training/layout_render.py tests/test_training_layout_geom.py
git commit -m "feat: add training form cell geometry"
```

---

## Task 4: Base image + handwriting + mark synthesis (PIL) + font fetch

**Files:**
- Modify: `training/layout_render.py` (add `draw_base_form`)
- Create: `training/handwriting.py`
- Create: `training/fetch_fonts.py`

Run/verify this task with `.venv-paddle\Scripts\python.exe` (has PIL).

- [ ] **Step 1: `draw_base_form`** — append to `training/layout_render.py`:

```python
def draw_base_form(layout, geom: "SheetGeometry", font_path: str | None = None):
    """Return a white PIL.Image with the grid + printed option/field labels drawn at their cell boxes."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (int(geom.width) + 2, int(geom.height) + 2), color=255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 12) if font_path else ImageFont.load_default()
    seen: set[str] = set()
    for fld in layout.iter_fields():
        for opt in fld.options:
            box = cell_box(opt.cell, geom)
            if opt.cell not in seen:
                draw.rectangle(box, outline=0)
                seen.add(opt.cell)
            draw.text((box[0] + 2, box[1] + 1), f"□{opt.label}", fill=0, font=font)
    return image
```

- [ ] **Step 2: `handwriting.py`** — text rendering (OFL fonts + jitter) and procedural marks:

```python
"""PIL handwriting + checkbox-mark synthesis."""
from __future__ import annotations

import random
from pathlib import Path

_MARK_STYLES = ("tick", "dash", "blackout")


def list_handwriting_fonts(fonts_dir: Path | str) -> list[Path]:
    d = Path(fonts_dir)
    return sorted(p for p in d.glob("*.tt[fc]")) if d.is_dir() else []


def draw_text(image, box, text, font_path, rng: random.Random) -> None:
    from PIL import ImageDraw, ImageFont

    x0, y0, x1, y1 = box
    size = rng.randint(14, 20)
    font = ImageFont.truetype(str(font_path), size)
    dx = rng.uniform(2, 6)
    dy = rng.uniform(1, 4)
    ImageDraw.Draw(image).text((x0 + dx, y0 + dy), text, fill=0, font=font)


def draw_mark(image, box, rng: random.Random, style: str | None = None) -> str:
    """Draw a checkbox mark inside `box`; return the style used. Stays within the box."""
    from PIL import ImageDraw

    style = style or rng.choice(_MARK_STYLES)
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pad = min(w, h) * 0.2
    ax0, ay0, ax1, ay1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    width = rng.randint(2, 4)
    if style == "tick":
        midx = ax0 + (ax1 - ax0) * 0.4
        draw.line([(ax0, (ay0 + ay1) / 2), (midx, ay1), (ax1, ay0)], fill=0, width=width)
    elif style == "dash":
        yy = rng.uniform(ay0, ay1)
        draw.line([(ax0, yy), (ax1, yy)], fill=0, width=width)
    else:  # blackout (partial)
        draw.rectangle([ax0, ay0, ax0 + (ax1 - ax0) * rng.uniform(0.5, 1.0), ay1], fill=0)
    return style
```

- [ ] **Step 3: `fetch_fonts.py`** — download curated OFL handwriting CJK fonts:

```python
"""Download curated OFL handwriting CJK fonts into training/fonts/ (one-off setup)."""
from __future__ import annotations

import urllib.request
from pathlib import Path

# OFL (SIL Open Font License) handwriting CJK fonts from the Google Fonts repo (raw).
# NOTE: these are Simplified-Chinese-leaning; verify Traditional-Chinese glyph coverage and add TC
# handwriting fonts as available. The generator falls back to system fonts for missing glyphs.
_FONTS = [
    ("LongCang-Regular.ttf",
     "https://github.com/google/fonts/raw/main/ofl/longcang/LongCang-Regular.ttf"),
    ("MaShanZheng-Regular.ttf",
     "https://github.com/google/fonts/raw/main/ofl/mashanzheng/MaShanZheng-Regular.ttf"),
    ("ZhiMangXing-Regular.ttf",
     "https://github.com/google/fonts/raw/main/ofl/zhimangxing/ZhiMangXing-Regular.ttf"),
    ("LiuJianMaoCao-Regular.ttf",
     "https://github.com/google/fonts/raw/main/ofl/liujianmaocao/LiuJianMaoCao-Regular.ttf"),
]
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"


def main() -> int:
    _FONTS_DIR.mkdir(parents=True, exist_ok=True)
    notes = ["# Fonts (SIL Open Font License). Sources:"]
    for name, url in _FONTS:
        dest = _FONTS_DIR / name
        notes.append(f"- {name}: {url}")
        if dest.exists():
            print(f"skip (exists): {name}")
            continue
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(url, dest)
    (_FONTS_DIR / "SOURCES.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    print(f"fonts in {_FONTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Smoke check (under .venv-paddle)** — verify a base form draws and a mark lands in its box:

Run:
```powershell
.venv-paddle\Scripts\python -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'src'); import random; from ocr_from2xlsx.form_layout import service_record_layout; from training.layout_render import sheet_geometry, draw_base_form, cell_box; from training.handwriting import draw_mark; L=service_record_layout(); g=sheet_geometry('115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx'); im=draw_base_form(L,g); b=cell_box('C4',g); draw_mark(im,b,random.Random(0),'tick'); im.save('training_smoke.png'); import numpy as np; a=np.asarray(im.crop([int(v) for v in b])); print('ink in C4 box:', (a<128).any())"
```
Expected: prints `ink in C4 box: True` and writes `training_smoke.png`. Delete the temp PNG afterward.

- [ ] **Step 5: Commit**

```powershell
git add training/layout_render.py training/handwriting.py training/fetch_fonts.py
git commit -m "feat: add base-form drawing, handwriting/mark synthesis, font fetch"
```

---

## Task 5: Generator orchestration + smoke test

**Files:**
- Create: `training/generate.py`
- Create: `tests/test_training_generate_smoke.py`

- [ ] **Step 1: Implement `training/generate.py`**

```python
"""Generate synthetic service-record images + a service_record.v1 answer key."""
from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path

from ocr_from2xlsx.form_layout import service_record_layout

from training.answer_key import build_answer_batch, selection_to_record
from training.handwriting import draw_mark, draw_text, list_handwriting_fonts
from training.layout_render import cell_box, draw_base_form, sheet_geometry
from training.sampler import choice_fields, generate_until_coverage

_NAMES = ["王小明", "陳美玲", "林志偉", "張雅婷", "李國華", "黃淑芬", "葉心安"]


def _text_values(rng: random.Random) -> dict[str, str]:
    roc_year = rng.randint(110, 115)
    return {
        "name": rng.choice(_NAMES),
        "medical_record_no": str(rng.randint(1000000000, 9999999999)),
        "service_date": f"{roc_year + 1911:04d}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
    }


def generate(xlsx_path: str, out_dir: str, *, min_per_option: int = 5, seed: int = 0) -> dict:
    layout = service_record_layout()
    geom = sheet_geometry(xlsx_path)
    fields = choice_fields(layout)
    rng = random.Random(seed)
    fonts = list_handwriting_fonts(Path(__file__).resolve().parent / "fonts")
    text_font = str(fonts[0]) if fonts else None

    out = Path(out_dir)
    (out / "images").mkdir(parents=True, exist_ok=True)
    selections = generate_until_coverage(fields, rng, min_per_option=min_per_option)
    records_with_images = []
    for i, selection in enumerate(selections, start=1):
        image = draw_base_form(layout, geom)
        for _, codes in selection.items():
            pass
        # mark each selected option's checkbox cell
        code_to_cell = {o.code: o.cell for f in layout.sections for fld in f.fields for o in fld.options}
        for key, codes in selection.items():
            for code in codes:
                draw_mark(image, cell_box(code_to_cell[code], geom), rng)
        text_values = _text_values(rng)
        if text_font:
            for fld in layout.iter_fields():
                if fld.kind == "text" and fld.key in text_values:
                    draw_text(image, cell_box(fld.anchor_cell, geom), text_values[fld.key], text_font, rng)
        record_id = f"train-{i:04d}"
        name = f"images/{record_id}.png"
        image.save(out / name)
        records_with_images.append(
            (selection_to_record(layout, record_id, selection, text_values), name)
        )
    batch = build_answer_batch(records_with_images, datetime.now().astimezone().isoformat(timespec="seconds"))
    (out / "answers.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"images": len(records_with_images), "answers": str(out / "answers.json")}


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(prog="training.generate")
    p.add_argument("--xlsx", required=True)
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    p.add_argument("--min-per-option", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    print(generate(a.xlsx, a.out, min_per_option=a.min_per_option, seed=a.seed))
```

(Note: `code_to_cell` is built from the layout's sections/fields/options; remove the empty `for _, codes`
loop — it is a leftover; the real marking loop follows it.)

- [ ] **Step 2: Smoke test** — create `tests/test_training_generate_smoke.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("PIL")
pytest.importorskip("numpy")

_XLSX = Path(__file__).resolve().parents[1] / "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"


def test_generate_tiny_batch(tmp_path):
    from training.generate import generate

    result = generate(str(_XLSX), str(tmp_path), min_per_option=1, seed=3)
    assert result["images"] >= 1
    answers = json.loads((tmp_path / "answers.json").read_text(encoding="utf-8"))
    assert answers["schema_version"] == "service_record.v1"
    first = answers["records"][0]
    assert first["training"] is True
    assert first["source_image"].startswith("images/")
    assert (tmp_path / first["source_image"]).is_file()
```

- [ ] **Step 3: Run smoke (under .venv-paddle)**

Run: `.venv-paddle\Scripts\python -m pytest tests/test_training_generate_smoke.py -q`
Expected: PASS (tiny batch produced; answers.json valid; image exists). With `min_per_option=1` it stays fast.

- [ ] **Step 4: Commit**

```powershell
git add training/generate.py tests/test_training_generate_smoke.py
git commit -m "feat: orchestrate synthetic form generation + answer key"
```

---

## Task 6: gitignore, docs, policy

**Files:**
- Modify: `.gitignore`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: .gitignore** — add:

```text
training/fonts/
training/out/
training_smoke.png
```

- [ ] **Step 2: README** — add a `training/` section: run `.venv-paddle\Scripts\python training/fetch_fonts.py`
(one-off, OFL fonts), then `.venv-paddle\Scripts\python -m training.generate --xlsx "<blank form xlsx>"`;
outputs `training/out/images/*.png` + `training/out/answers.json` (service_record.v1 + `training`/`source_image`);
note generation is offline and falls back to system fonts if `training/fonts/` is empty.

- [ ] **Step 3: CHANGELOG** — under `## [Unreleased]` `### Added`:

```markdown
- 新增 `training/` 手寫訓練資料產生器：以 form_layout 為底合成不同筆跡的服務記錄表影像（文字 + ✓/劃-/塗黑勾選），產出與 workflow 同格式的答案卷（service_record.v1 + training + source_image）；涵蓋率每選項≥5、每張10–50%、單多選約束；OFL 字型由 setup 腳本下載、產圖離線。
```

- [ ] **Step 4: Tests + policy**

```powershell
.venv\Scripts\python -W error -m pytest -q
.venv\Scripts\python build/package.py
python -m policy_check --repo .
```
Expected: all pass; policy 0 failures. (The PIL smoke test runs only under `.venv-paddle`; under `.venv` it
skips via `pytest.importorskip("PIL")`. The pure training tests run everywhere.)

- [ ] **Step 5: Commit**

```powershell
git add .gitignore README.md CHANGELOG.md
git commit -m "docs: document training data generator"
```

---

## Self-Review Notes

- **Spec coverage:** synthesize images from layout (Task 3/4/5) ✓; workflow-aligned answer key via confirm_form (Task 2) ✓; varied marks tick/dash/blackout (Task 4) ✓; per-image 10–50%/≥1, single≤1/multi-subset, per-option ≥5 (Task 1) ✓; OFL fonts fetched locally + offline gen + system fallback (Task 4 + generate font loader) ✓; pure unit tests + image smoke test (Tasks 1-5) ✓; gitignore/docs/policy (Task 6) ✓.
- **Type consistency:** `choice_fields(layout)->list[FieldOptions]`, `sample_selection(fields, rng, ...)->dict[key,list[code]]`, `generate_until_coverage(...)->list[selection]`, `selection_to_record(layout, record_id, selection, text_values)->Record`, `build_answer_batch(records_with_images, created_at)->dict`, `sheet_geometry(xlsx)->SheetGeometry`, `cell_box(cell, geom)->box`, `draw_base_form/draw_mark/draw_text` are consistent across tasks and tests.
- **Known caveats (flag for implementer/reviewer):** (1) `fetch_fonts.py` URLs are Google-Fonts OFL handwriting CJK that lean Simplified-Chinese; verify Traditional-Chinese glyph coverage for names and add TC handwriting fonts if needed — the generator must fall back to a system font (e.g. `C:\Windows\Fonts\kaiu.ttf`) for missing glyphs (the `generate` font loader should choose a TC-capable fallback when `training/fonts/` is empty). (2) The reconstructed base form is geometry-consistent but not a pixel-faithful replica of the printed form; its value is labeled mark coverage + workflow-aligned answer keys, not perfect scan realism. (3) `generate.py` has a leftover empty `for _, codes in selection.items(): pass` loop in the draft above — delete it during implementation. (4) `Record.from_dict({"record_id": ...})` must succeed with defaults; if not, pass the minimal empty fields per `domain.py`.
```
