# Offline VLM Assisted Recognition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the OCR/geometry/heuristic recognition layer with a fully-local Vision-LLM that pre-fills the full `service_record.v1`, verified by a human in the existing review UI.

**Architecture:** A new `VisionOcrBackend` implements the existing `OcrBackend` Protocol (`extract(page) -> dict`). It crops wide proportional **section tiles**, asks a local VLM (served by `llama-server`) to mark each tile's **known options** and read handwritten dates/numbers, then merges the per-tile JSON into a `service_record.v1` record dict with per-field confidence. Pure logic (layout, mapping, flags, name/MRN) is model-free and unit-tested; the VLM call is an injectable `vlm_fn` faked in tests. Weights/runtime ship via a `build/` script into `dist/`, never git.

**Tech Stack:** Python 3, dataclasses, Pillow (crop, backend layer only), `llama-server` (llama.cpp) HTTP, pytest. Reuses `domain.Record`, `OcrBackend`, `name_roster`/`name_suggestion`, `OcrInfo.field_confidences`/`warnings`, `confirm_form`.

**Refs:** Spec `docs/superpowers/specs/2026-06-14-offline-vlm-assisted-recognition-design.md`; openspec `replace-recognition-with-local-vlm`.

**Conventions (paulsha):** Not on `main` (use this `feature/*` or a `wt/offline-vlm-recognition/*` worktree). Every code commit syncs `CHANGELOG.md [Unreleased]`. Before claim-done: `python -m policy_check --repo .` clean, tests/build green, PR template checklist all ticked.

---

## Data contracts (defined now, not Phase-0-gated)

**Per-tile VLM JSON** the model must return for one tile:

```json
{
  "options": [{"id": "identity.patient", "marked": true, "confidence": 0.92}],
  "values":  [{"id": "service_date", "text": "114.06.25", "confidence": 0.8}]
}
```

**Recognition layout** — one entry per option/value the form carries:

```python
# RecognitionLayout = list[Section]
# Section: {key, band (x0,y0,x1,y1 as 0..1 fractions of the upright page), options, values}
# Option: {id, label, field, code, kind}   kind in {"single","multi"}
# ValueSpec: {id, field, parser}            parser in {"date","int","name","mrn"}
```

`field` is the dotted target in the record dict (e.g. `identity`, `patient_fields.cancers`, `services.supplies`). Initial band fractions are best-guess for the fixed IPEVO layout and **tuned in Phase 0** (tests assert behavior from the config, not pixel values, so tuning never breaks tests).

---

## Task 0: Phase 0 spike — model + runtime bake-off (manual, user hardware)

**Files:**
- Create: `output/phase0/README.md` (notes; `output/` is gitignored — copy the final numbers into the spec).

- [ ] **Step 1: Stand up a local server**

Run (dev): `ollama serve` then `ollama pull qwen3.5-vl:2b` (or the current tag). For the shipping runtime, fetch a `llama-server` build with Vulkan and a Qwen 3.5 VL 2B GGUF + mmproj.

- [ ] **Step 2: Verify the vision path actually works in the portable runtime**

Send one tile image + a "list what you see" prompt to each candidate via the HTTP API; confirm a non-empty image-grounded answer. **If `llama-server` lacks vision for the chosen model, record it and either pick a supported model or keep Ollama as the runtime.** (Gemma 3n E2B was text-only in llama.cpp — verify before committing to any model.)

- [ ] **Step 3: Bake-off on real samples**

For each of {Qwen 3.5 VL 2B (default), 4B, Gemma 4 E2B, 7B}: run the tile prompts over `output/reg/filled_cam.png` (rotate upright first) and record per-section pre-fill accuracy vs. a hand-label, plus per-image latency on this machine.

- [ ] **Step 4: Decide and record**

Pick the default model; tune the band fractions and the prompt template; confirm the per-tile JSON contract above is reliably produced. Write the decision + numbers into the design spec's Phase 0 section and `output/phase0/README.md`.

**Quality Gate:**
- [ ] Vision path verified in the runtime that will ship
- [ ] Phase 0 numbers + decision recorded in the spec

---

## Task 1: Recognition layout config + pure band geometry

**Files:**
- Create: `src/ocr_from2xlsx/recognition/__init__.py`
- Create: `src/ocr_from2xlsx/recognition/layout.py`
- Test: `tests/test_recognition_layout.py`

- [ ] **Step 1: Write the failing test**

```python
from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT, band_pixels

def test_band_pixels_scales_fractions_to_image_size():
    section = SERVICE_RECORD_V1_LAYOUT[0]
    # band fractions are 0..1; for a 1000x2000 image they scale to pixels
    x0, y0, x1, y1 = band_pixels(section.band, width=1000, height=2000)
    assert (x0, y0, x1, y1) == (
        int(section.band[0] * 1000), int(section.band[1] * 2000),
        int(section.band[2] * 1000), int(section.band[3] * 2000),
    )
    assert x0 < x1 and y0 < y1

def test_layout_covers_core_fields():
    fields = {opt.field for s in SERVICE_RECORD_V1_LAYOUT for opt in s.options}
    assert {"identity", "gender", "patient_fields.cancers"} <= fields
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_recognition_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: ocr_from2xlsx.recognition.layout`

- [ ] **Step 3: Implement**

```python
# src/ocr_from2xlsx/recognition/layout.py
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Option:
    id: str
    label: str
    field: str          # dotted target, e.g. "identity" or "patient_fields.cancers"
    code: str           # value written when marked
    kind: str = "single"  # "single" (one per field) or "multi" (list)

@dataclass(frozen=True, slots=True)
class ValueSpec:
    id: str
    field: str
    parser: str         # "date" | "int" | "name" | "mrn"

@dataclass(frozen=True, slots=True)
class Section:
    key: str
    band: tuple[float, float, float, float]   # x0,y0,x1,y1 in 0..1
    options: tuple[Option, ...] = ()
    values: tuple[ValueSpec, ...] = ()

def band_pixels(band, width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = band
    return (int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height))

# Best-guess bands for the fixed IPEVO upright layout; tuned in Phase 0.
SERVICE_RECORD_V1_LAYOUT: tuple[Section, ...] = (
    Section("identity_gender", (0.50, 0.45, 1.0, 0.60), options=(
        Option("identity.patient", "病人", "identity", "patient"),
        Option("identity.family_caregiver", "親友及照顧者", "identity", "family_caregiver"),
        Option("identity.public_other", "一般民眾及其他", "identity", "public_other"),
        Option("gender.female", "女性", "gender", "female"),
        Option("gender.male", "男性", "gender", "male"),
        Option("gender.other", "其他", "gender", "other"),
    ), values=(
        ValueSpec("service_date", "service_date", "date"),
    )),
    Section("cancers", (0.50, 0.75, 1.0, 0.95), options=(
        Option("cancer.10", "肝癌", "patient_fields.cancers", "liver", kind="multi"),
        # ... full cancer catalog filled during implementation from the form ...
    )),
    Section("name_mrn", (0.0, 0.45, 0.50, 0.52), values=(
        ValueSpec("name", "name", "name"),
        ValueSpec("medical_record_no", "medical_record_no", "mrn"),
    )),
    # ... services (Section A), age_group, nationality, channel, disease_status, source ...
)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_recognition_layout.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/recognition/__init__.py src/ocr_from2xlsx/recognition/layout.py tests/test_recognition_layout.py
# sync CHANGELOG [Unreleased] Added: recognition layout config
git add CHANGELOG.md
git commit -m "feat: add recognition layout config and pure band geometry"
```

---

## Task 2: Tile-JSON → service_record dict mapper (pure)

**Files:**
- Create: `src/ocr_from2xlsx/recognition/mapping.py`
- Test: `tests/test_recognition_mapping.py`

- [ ] **Step 1: Write the failing test**

```python
from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT
from ocr_from2xlsx.recognition.mapping import empty_record_fields, apply_tile_result

def test_marked_single_option_sets_field():
    fields = empty_record_fields()
    apply_tile_result(
        fields, SERVICE_RECORD_V1_LAYOUT,
        {"options": [{"id": "identity.patient", "marked": True, "confidence": 0.9},
                     {"id": "gender.female", "marked": True, "confidence": 0.8}],
         "values": [{"id": "service_date", "text": "114.06.25", "confidence": 0.7}]},
    )
    assert fields["identity"] == "patient"
    assert fields["gender"] == "female"
    assert fields["service_date"] == "2025-06-25"   # ROC 114 -> 2025

def test_marked_multi_option_appends_code():
    fields = empty_record_fields()
    apply_tile_result(fields, SERVICE_RECORD_V1_LAYOUT,
        {"options": [{"id": "cancer.10", "marked": True, "confidence": 0.9}], "values": []})
    assert fields["patient_fields"]["cancers"] == ["liver"]

def test_unmarked_option_leaves_field_empty():
    fields = empty_record_fields()
    apply_tile_result(fields, SERVICE_RECORD_V1_LAYOUT,
        {"options": [{"id": "identity.patient", "marked": False, "confidence": 0.9}], "values": []})
    assert fields["identity"] == ""
```

- [ ] **Step 2: Run, verify fail** (`ModuleNotFoundError: ...recognition.mapping`)

- [ ] **Step 3: Implement**

```python
# src/ocr_from2xlsx/recognition/mapping.py
from __future__ import annotations
from typing import Any
from ocr_from2xlsx.recognition.layout import Option, Section

def empty_record_fields() -> dict[str, Any]:
    return {
        "service_date": "", "identity": "", "name": "", "medical_record_no": "", "gender": "",
        "patient_fields": {"nationality": None, "age_group": None, "channel": None,
                           "disease_status": None, "source": None, "cancers": [],
                           "newly_diagnosed_within_year": None},
        "services": {"consultation": {}, "supplies": [], "internal_referrals": [],
                     "external_referrals": [], "referral_outcomes": []},
    }

def _set_dotted(fields: dict[str, Any], dotted: str, value: Any) -> None:
    head, _, tail = dotted.partition(".")
    if not tail:
        fields[head] = value
        return
    fields.setdefault(head, {})[tail] = value

def _append_dotted(fields: dict[str, Any], dotted: str, value: Any) -> None:
    head, _, tail = dotted.partition(".")
    target = fields[head][tail] if tail else fields[head]
    if value not in target:
        target.append(value)

def parse_roc_date(text: str) -> str:
    # "114.06.25" / "114、06、25" -> "2025-06-25"
    digits = [p for p in __import__("re").split(r"[^0-9]+", text) if p]
    if len(digits) >= 3:
        y, m, d = int(digits[0]), int(digits[1]), int(digits[2])
        return f"{y + 1911:04d}-{m:02d}-{d:02d}"
    return ""

def apply_tile_result(fields, layout, tile_json) -> None:
    options = {o.id: o for s in layout for o in s.options}
    values = {v.id: v for s in layout for v in s.values}
    for entry in tile_json.get("options", []):
        opt = options.get(entry.get("id"))
        if opt is None or not entry.get("marked"):
            continue
        if opt.kind == "multi":
            _append_dotted(fields, opt.field, opt.code)
        else:
            _set_dotted(fields, opt.field, opt.code)
    for entry in tile_json.get("values", []):
        spec = values.get(entry.get("id"))
        text = (entry.get("text") or "").strip()
        if spec is None or not text:
            continue
        if spec.parser == "date":
            text = parse_roc_date(text)
        _set_dotted(fields, spec.field, text)
```

- [ ] **Step 4: Run, verify pass.** **Step 5: Commit** (`feat: map per-tile VLM JSON into service_record fields`; sync CHANGELOG).

*(Name/MRN value parsers covered in Task 4.)*

---

## Task 3: Confidence flags into ocr.field_confidences + warnings (pure)

**Files:**
- Create: `src/ocr_from2xlsx/recognition/confidence.py`
- Test: `tests/test_recognition_confidence.py`

- [ ] **Step 1: Failing test**

```python
from ocr_from2xlsx.recognition.confidence import collect_confidence

def test_low_confidence_and_empty_flagged():
    tiles = [{"options": [{"id": "identity.patient", "marked": True, "confidence": 0.4}],
              "values": [{"id": "service_date", "text": "", "confidence": 0.0}]}]
    field_conf, warnings = collect_confidence(tiles, threshold=0.6)
    assert field_conf["identity"] == 0.4
    assert any("identity" in w for w in warnings)      # below threshold
    assert any("service_date" in w for w in warnings)  # empty
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement**

```python
# src/ocr_from2xlsx/recognition/confidence.py
from __future__ import annotations

def collect_confidence(tiles, threshold: float = 0.6):
    field_conf: dict[str, float] = {}
    warnings: list[str] = []
    for tile in tiles:
        for e in tile.get("options", []):
            if not e.get("marked"):
                continue
            fid, c = e.get("id", ""), float(e.get("confidence") or 0.0)
            field_conf[fid] = c
            if c < threshold:
                warnings.append(f"low-confidence:{fid}:{c:.2f}")
        for e in tile.get("values", []):
            fid, c = e.get("id", ""), float(e.get("confidence") or 0.0)
            if not (e.get("text") or "").strip():
                warnings.append(f"empty:{fid}")
            else:
                field_conf[fid] = c
                if c < threshold:
                    warnings.append(f"low-confidence:{fid}:{c:.2f}")
    return field_conf, warnings
```

- [ ] **Step 4: Run, verify pass. Step 5: Commit** (`feat: derive recognition confidence flags`; CHANGELOG).

---

## Task 4: Name/MRN parse + roster snap (pure)

**Files:**
- Create: `src/ocr_from2xlsx/recognition/name_mrn.py`
- Test: `tests/test_recognition_name_mrn.py`

- [ ] **Step 1: Failing test**

```python
from ocr_from2xlsx.recognition.name_mrn import parse_name, parse_mrn, snap_name

def test_parse_name_keeps_cjk_run():
    assert parse_name("葉心安") == "葉心安"
    assert parse_name("V 葉心安") == "葉心安"   # strip stray mark
    assert parse_name("123") == ""              # digits are not a name

def test_parse_mrn_keeps_long_digit_run():
    assert parse_mrn("病入6250712919") == "6250712919"
    assert parse_mrn("V") == ""

def test_snap_name_to_roster():
    assert snap_name("葉心妄", roster=["葉心安", "王小明"]) == "葉心安"  # nearest
    assert snap_name("陌生人", roster=["葉心安"]) == "陌生人"           # no close match -> keep
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** (reuse roster matching from `name_suggestion` if it exposes a distance; otherwise a local edit-distance with a max-1 substitution threshold).

```python
# src/ocr_from2xlsx/recognition/name_mrn.py
from __future__ import annotations
import re

_CJK = re.compile(r"[一-鿿]{2,4}")
_DIGITS = re.compile(r"\d{6,}")

def parse_name(text: str) -> str:
    m = _CJK.search(text or "")
    return m.group(0) if m else ""

def parse_mrn(text: str) -> str:
    m = _DIGITS.search(text or "")
    return m.group(0) if m else ""

def _dist(a: str, b: str) -> int:
    if len(a) != len(b):
        return max(len(a), len(b))
    return sum(1 for x, y in zip(a, b) if x != y)

def snap_name(name: str, roster: list[str]) -> str:
    if not name:
        return name
    best, best_d = name, 2
    for cand in roster:
        d = _dist(name, cand)
        if d < best_d:
            best, best_d = cand, d
    return best
```

- [ ] **Step 4: Run, verify pass. Step 5: Commit** (`feat: name/MRN parse + roster snap`; CHANGELOG).

---

## Task 5: VisionOcrBackend composition with injectable vlm_fn

**Files:**
- Create: `src/ocr_from2xlsx/recognition/backend.py`
- Test: `tests/test_vision_backend.py`

- [ ] **Step 1: Failing test** (fake vlm_fn, no model, no image decode — inject a fake tiler too)

```python
from ocr_from2xlsx.recognition.backend import VisionOcrBackend
from ocr_from2xlsx.preprocess import PreparedPage  # adjust import to real location

def _fake_page(tmp_path):
    img = tmp_path / "frame.png"; img.write_bytes(b"x")
    return PreparedPage(image_path=str(img), template_id="service_record.v1", source=...)  # minimal

def test_backend_builds_full_record(tmp_path):
    def fake_tiler(image_path, layout):  # returns one crop path per section
        return {s.key: f"{s.key}.png" for s in layout}
    def fake_vlm(crop_path, section):    # marks identity/gender/date on the right section
        if section.key == "identity_gender":
            return {"options": [{"id": "identity.patient", "marked": True, "confidence": 0.9},
                                {"id": "gender.female", "marked": True, "confidence": 0.9}],
                    "values": [{"id": "service_date", "text": "114.06.25", "confidence": 0.8}]}
        return {"options": [], "values": []}
    backend = VisionOcrBackend(vlm_fn=fake_vlm, tiler=fake_tiler, roster=[])
    record = backend.extract(_fake_page(tmp_path))
    assert record["identity"] == "patient"
    assert record["gender"] == "female"
    assert record["service_date"] == "2025-06-25"
    assert record["ocr"]["backend"] == "vision-llm"
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** — compose Tasks 1-4; build a record dict that `domain.Record.from_dict` accepts.

```python
# src/ocr_from2xlsx/recognition/backend.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable
from ocr_from2xlsx.preprocess import PreparedPage
from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT, Section
from ocr_from2xlsx.recognition.mapping import empty_record_fields, apply_tile_result
from ocr_from2xlsx.recognition.confidence import collect_confidence
from ocr_from2xlsx.recognition.name_mrn import parse_name, parse_mrn, snap_name

VlmFn = Callable[[str, Section], dict[str, Any]]
TilerFn = Callable[[str, tuple[Section, ...]], dict[str, str]]

class VisionOcrBackend:
    def __init__(self, vlm_fn: VlmFn, tiler: TilerFn, roster: list[str] | None = None,
                 layout: tuple[Section, ...] = SERVICE_RECORD_V1_LAYOUT, model_name: str = "qwen3.5-vl-2b") -> None:
        self.vlm_fn, self.tiler, self.roster = vlm_fn, tiler, roster or []
        self.layout, self.model_name = layout, model_name

    def extract(self, page: PreparedPage) -> dict[str, object]:
        crops = self.tiler(page.image_path, self.layout)
        fields = empty_record_fields()
        tiles: list[dict[str, Any]] = []
        name_text = mrn_text = ""
        for section in self.layout:
            crop = crops.get(section.key)
            if crop is None:
                continue
            result = self.vlm_fn(crop, section)
            tiles.append(result)
            apply_tile_result(fields, self.layout, result)
            for v in result.get("values", []):
                if v.get("id") == "name":
                    name_text = v.get("text") or ""
                elif v.get("id") == "medical_record_no":
                    mrn_text = v.get("text") or ""
        fields["name"] = snap_name(parse_name(name_text), self.roster)
        fields["medical_record_no"] = parse_mrn(mrn_text)
        field_conf, warnings = collect_confidence(tiles)
        if fields["name"]:
            warnings.append("name.unconfirmed")
        fields["ocr"] = {"backend": "vision-llm", "model": self.model_name, "raw_text": "",
                         "warnings": warnings, "field_confidences": field_conf}
        return fields
```

- [ ] **Step 4: Run, verify pass. Step 5: Commit** (`feat: VisionOcrBackend composition (injectable vlm_fn)`; CHANGELOG).

---

## Task 6: Real vlm_fn (llama-server HTTP) + tiler (Pillow) with graceful degradation

**Files:**
- Create: `src/ocr_from2xlsx/recognition/llama_client.py` (HTTP), `src/ocr_from2xlsx/recognition/tiling.py` (Pillow crop)
- Test: `tests/test_llama_client.py`, `tests/test_tiling.py`

- [ ] **Step 1: Failing test for request building + error handling** (mock HTTP; assert the request carries the image + prompt, and that a connection error returns an empty `{"options":[],"values":[]}` rather than raising).
- [ ] **Step 2: Failing test for tiler** (create a small PIL image, assert each section crop file is written with the band-pixel size from Task 1's `band_pixels`).
- [ ] **Step 3: Implement** `tiling.crop_sections(image_path, layout) -> dict[str,str]` using `band_pixels` + Pillow; `llama_client.vlm_fn(crop_path, section)` POSTing base64 image + a schema-guided prompt built from `section.options`/`section.values`, parsing the JSON, and returning the empty result on any `OSError`/timeout/JSON error.
- [ ] **Step 4: Run, verify pass. Step 5: Commit** (`feat: llama-server vlm_fn + Pillow tiler with graceful degradation`; CHANGELOG).

---

## Task 7: Backend selection + review-UI confidence flagging

**Files:**
- Modify: the recognition entrypoint that picks a backend (`src/ocr_from2xlsx/scan.py` / `prepare_records.py` — wire `VisionOcrBackend` as a selectable backend, default per config/env).
- Modify: `src/ocr_from2xlsx/confirm_form.py` (render fields carrying `low-confidence:`/`empty:`/`*.unconfirmed` warnings visibly distinct).
- Test: extend `tests/test_confirm_form*.py` for the flagging; a backend-selection test asserting `VisionOcrBackend` keeps the normalized contract.

- [ ] **Step 1-4:** TDD each: a confirm_form test that a record with `ocr.warnings=["low-confidence:identity:0.40"]` marks the identity field; a selection test that the configured vision backend produces a `Record.from_dict`-valid dict.
- [ ] **Step 5: Commit** (`feat: select vision backend + flag low-confidence fields in review`; CHANGELOG).

---

## Task 8: Portable packaging (runtime + weights, not in git)

**Files:**
- Create: `build/build_vlm_runtime.py`; Modify: `.gitignore` (ignore the weights/runtime dir), `build/package.py`.

- [ ] **Step 1:** Script fetches a Vulkan `llama-server` + default GGUF + mmproj into a `dist/`-bound dir; verify checksums; print final size.
- [ ] **Step 2:** App resolves the server/model dir in order env → user runtime (`OCR_FROM2XLSX_HOME`) → bundle (mirror `_resolve_mark_model_path`).
- [ ] **Step 3:** `python build/package.py` runs end-to-end; confirm weights are gitignored.
- [ ] **Step 4: Commit** (`build: portable VLM runtime + weights fetch (not in git)`; CHANGELOG).

---

## Task 9: Ground-truth regression + optional real-VLM test

**Files:**
- Create: `tests/fixtures/recognition/service_record_v1_ground_truth.json`; `tests/test_vision_real.py` (optional marker).

- [ ] **Step 1:** Hand-label the reference form's full fields into the fixture.
- [ ] **Step 2:** Optional-marker test runs the real backend against the reference image and asserts field-by-field equality (skipped in default CI).
- [ ] **Step 3:** Manually run the full chain; record per-field results vs. image.
- [ ] **Step 4: Commit** (`test: recognition ground-truth fixture + optional real-VLM regression`; CHANGELOG).

---

## Task 10: Retire old recognition + docs/policy

**Files:**
- Modify: recognition wiring to stop using PaddleOCR field-extract/mark/geometry for the default path (keep code archived or remove per code review); `README.md`; `CHANGELOG.md`; openspec `replace-recognition-with-local-vlm/tasks.md` (tick).

- [ ] **Step 1:** Unwire the old path; ensure no test depends on the retired heuristic for the default recognition.
- [ ] **Step 2:** Update README recognition section + design-spec Phase 0 results; point the parked registration spec at this change.
- [ ] **Step 3:** `python -W error -m pytest -q`, `python build/package.py`, `python -m policy_check --repo .` all green.
- [ ] **Step 4: Commit** (`refactor: retire OCR/geometry recognition path; docs+policy sync`; CHANGELOG).

---

## Self-Review

- **Spec coverage:** ADDED "full-form local pre-fill" → Tasks 1,2,5,6; "local name/MRN unconfirmed" → Tasks 4,5; "confidence flags" → Tasks 3,7; "portable runtime + graceful degradation" → Tasks 6,8; MODIFIED "configured backend capture-recognition" → Tasks 5,7; REMOVED/supersede → Task 10. Phase 0 (model + runtime decision) → Task 0.
- **Placeholders:** Core pure tasks (1-5) carry complete code; integration/manual tasks (0,6-10) are concrete spikes with exact files/commands — not deferred logic. The cancer/services catalogs are explicitly filled from the form during Task 1/2 implementation (data entry, not undefined logic).
- **Type consistency:** `VlmFn = (crop_path, Section) -> tile_json`, `TilerFn = (image_path, layout) -> {key: crop_path}`, `apply_tile_result(fields, layout, tile_json)`, `collect_confidence(tiles, threshold)`, `snap_name(name, roster)`, `band_pixels(band, width, height)` are used consistently across tasks. `VisionOcrBackend.extract(page) -> dict` matches the `OcrBackend` Protocol.
