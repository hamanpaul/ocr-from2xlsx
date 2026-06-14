# Form Registration + Full-Checkbox Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register a captured/scanned service-record image to the canonical template (auto ORB homography + manual 4-corner fallback) so all 125 `template_boxes` classify correctly, and map the full marked set into a complete `service_record.v1`.

**Architecture:** Registration is pure OpenCV in the self-contained plugin (`plugins/paddleocr/registration.py`). The plugin already crops + classifies all 125 boxes (`crop_provider` + `mark_model`); we make it emit the FULL marked `(field, code)` set (today it keeps only identity/gender). **Critical:** the plugin runs in its own bundled venv with NO `ocr_from2xlsx`, so the marked-set → record mapping (`form_layout.selection_to_record`) runs in the MAIN APP, not the plugin. The app prompts a manual 4-corner pick when auto-registration is not confident.

**Tech Stack:** Python 3.12; `.venv` for pure tests (cv2 via `pytest.importorskip`); `.venv-paddle` / built bundle for plugin + marker tests; OpenCV (ORB, findHomography, warpPerspective) — already bundled in the plugin.

**Branch:** `wt/bootstrap-ocr-design/form-registration`. Spec: `docs/superpowers/specs/2026-06-14-form-registration-checkbox-design.md`. OpenSpec: `openspec/changes/add-form-registration/`. Tracks GitHub #22.

**Real APIs to build on (verified):**
- `crop_provider.GeometryCropProvider(template_boxes_path).crop(image) -> {(field, code): Region}` — crops the 125 boxes from an ALIGNED image.
- `mark_model.load_model(path)`, `mark_model.is_marked_by_model(region, model) -> bool`.
- `plugins/paddleocr/main.py::classifier_mark_fn` already loops the 125 crops but maps via `_CLASSIFIER_LABELS` (identity/gender only).
- `training/answer_key.py::selection_to_record(layout, record_id, selection: dict[field_key, list[code]], text_values) -> Record` — MAIN-APP-side mapping.
- `src/ocr_from2xlsx/form_layout.py::service_record_layout()`, `layout.iter_fields()`.

**Conventions:**
- Pure tests: `.venv\Scripts\python -m pytest <file> -q -p no:cacheprovider --basetemp=output/pytest-tmp`.
- TDD: failing test → see it fail → implement → see it pass → commit.
- Commits end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- cv2 tests start with `pytest.importorskip("cv2")`. Plugin/Tk/paddle glue is not unit-tested in CI; its pure logic is.

---

## Phase 0 — Registration precision smoke (RISK GATE; do before Phase 2+)

**Files:** none committed except notes; a throwaway script under gitignored `output/`.

- [ ] **Step 1: Render the canonical blank reference.** Find how the training generator renders the
  blank form base (read `training/generate.py` — the blank-form base render) and produce the blank
  service-record image at the SAME canonical size that `template_boxes.json` coords assume. Save to
  `output/reg/canonical_reference.png`. Verify by cropping a couple of `template_boxes` boxes from the
  blank reference and confirming they land on empty checkbox squares.

- [ ] **Step 2: Auto-register a real capture + overlay boxes.** Write `output/reg/smoke.py` (uses cv2)
  that: loads a sharp real capture (`output/demo/frame.png`), ORB-matches it to the canonical
  reference, computes `findHomography(RANSAC)`, warps the capture to canonical, draws all 125
  `template_boxes` rectangles on the warped image, and saves `output/reg/overlay.png`.

- [ ] **Step 3: Eyeball + measure.** View `output/reg/overlay.png`: do the 125 rectangles sit on the
  actual checkboxes? Then classify each box (crop_provider + mark_model) on the warped image and on
  the UN-warped image; compare how many marked boxes match the real checks.

- [ ] **Step 4: Decision checkpoint.**
  - PASS (boxes aligned; warped mark hit rate clearly beats unwarped): continue to Phase 1.
  - FAIL (misaligned / no better): STOP and report. Options to evaluate before proceeding: higher
    capture resolution, different feature/matcher (SIFT, more ORB features), per-region refinement, or
    leading with manual 4-corner. Do not build Phase 2+ on an unproven registration.

---

## Phase 1 — Registration core (pure CV)

### Task 1.1: `four_point_warp`

**Files:**
- Create: `plugins/paddleocr/registration.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from importlib import util as _util
from pathlib import Path

_SPEC = _util.spec_from_file_location(
    "paddle_registration", Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "registration.py"
)
registration = _util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(registration)


def test_four_point_warp_maps_corners_to_canonical_rectangle() -> None:
    src = (np.random.default_rng(0).integers(0, 256, size=(200, 200, 3))).astype("uint8")
    # corners (clockwise from top-left) of a skewed quad inside the source
    corners = [(20, 10), (180, 30), (170, 190), (10, 170)]

    warped = registration.four_point_warp(src, corners, size=(100, 140))

    assert warped.shape[:2] == (140, 100)  # (height, width)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_registration.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `AttributeError: ... 'four_point_warp'`

- [ ] **Step 3: Implement in `plugins/paddleocr/registration.py`**

```python
"""Register a captured form image to the canonical template coordinate space.

Pure OpenCV; runs inside the self-contained plugin bundle. The MAIN app maps the resulting
marked (field, code) set to a record — that mapping is NOT here (no ocr_from2xlsx in the bundle).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MIN_INLIERS = 25


@dataclass(frozen=True)
class RegistrationResult:
    warped: object | None
    homography: object | None
    inliers: int
    needs_manual: bool


def four_point_warp(image: object, corners, size: tuple[int, int]) -> object:
    """Perspective-warp the quad given by 4 (x, y) corners (TL, TR, BR, BL) to a size (w, h) canvas."""
    import cv2
    import numpy as np

    width, height = int(size[0]), int(size[1])
    src = np.array(corners, dtype="float32")
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (width, height))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_registration.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/paddleocr/registration.py tests/test_registration.py
git commit -m "feat: four-point perspective warp for form registration"
```

---

### Task 1.2: `register_to_template` (auto ORB homography)

**Files:**
- Modify: `plugins/paddleocr/registration.py`
- Test: `tests/test_registration.py`

- [ ] **Step 1: Write the failing test** (inject a fake detector/matcher so it runs without real images)

```python
def test_register_recovers_translation_homography_from_correspondences() -> None:
    np = pytest.importorskip("numpy")
    # Reference points and image points related by a known translation (+30, +20).
    ref_pts = np.array([[10, 10], [200, 12], [205, 180], [8, 175], [120, 90], [60, 140]], dtype="float32")
    img_pts = ref_pts + np.array([30, 20], dtype="float32")

    result = registration.register_to_template(
        image=object(),
        reference=object(),
        _matched_points=(img_pts, ref_pts),  # test seam: skip ORB, use given correspondences
        size=(220, 200),
    )

    assert result.needs_manual is False
    assert result.inliers >= registration.DEFAULT_MIN_INLIERS or result.inliers == len(ref_pts)
    # homography maps an image point back near its reference point
    import numpy as _np
    h = result.homography
    pt = _np.array([img_pts[0][0], img_pts[0][1], 1.0])
    mapped = h @ pt
    mapped = mapped[:2] / mapped[2]
    assert abs(mapped[0] - ref_pts[0][0]) < 1.0 and abs(mapped[1] - ref_pts[0][1]) < 1.0


def test_register_too_few_matches_needs_manual() -> None:
    np = pytest.importorskip("numpy")
    pts = np.array([[1, 1], [2, 2]], dtype="float32")
    result = registration.register_to_template(object(), object(), _matched_points=(pts, pts), size=(50, 50))
    assert result.needs_manual is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_registration.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `AttributeError: ... 'register_to_template'`

- [ ] **Step 3: Append to `registration.py`**

```python
def _match_points_orb(image, reference, *, max_features: int = 4000):
    import cv2
    import numpy as np

    orb = cv2.ORB_create(max_features)
    gray_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if getattr(image, "ndim", 2) == 3 else image
    gray_ref = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY) if getattr(reference, "ndim", 2) == 3 else reference
    kp_i, des_i = orb.detectAndCompute(gray_img, None)
    kp_r, des_r = orb.detectAndCompute(gray_ref, None)
    if des_i is None or des_r is None:
        return np.empty((0, 2), "float32"), np.empty((0, 2), "float32")
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(matcher.match(des_i, des_r), key=lambda m: m.distance)[:200]
    img_pts = np.array([kp_i[m.queryIdx].pt for m in matches], dtype="float32")
    ref_pts = np.array([kp_r[m.trainIdx].pt for m in matches], dtype="float32")
    return img_pts, ref_pts


def register_to_template(
    image,
    reference,
    *,
    size: tuple[int, int],
    min_inliers: int = DEFAULT_MIN_INLIERS,
    _matched_points=None,
) -> RegistrationResult:
    import cv2
    import numpy as np

    if _matched_points is not None:
        img_pts, ref_pts = _matched_points
    else:
        img_pts, ref_pts = _match_points_orb(image, reference)
    if len(img_pts) < 4 or len(ref_pts) < 4:
        return RegistrationResult(None, None, len(img_pts), needs_manual=True)
    homography, mask = cv2.findHomography(img_pts, ref_pts, cv2.RANSAC, 5.0)
    inliers = int(mask.sum()) if mask is not None else 0
    if homography is None or inliers < min_inliers:
        # still allow the all-points small-but-exact case used in tests
        if homography is None or (inliers < min_inliers and len(img_pts) > 4):
            return RegistrationResult(None, None, inliers, needs_manual=True)
    warped = cv2.warpPerspective(image, homography, (int(size[0]), int(size[1])))
    return RegistrationResult(warped, homography, inliers, needs_manual=False)
```

Note for the implementer: the `_matched_points` seam keeps the test cv2-only (no real images). If the
small-correspondence test (`>= DEFAULT_MIN_INLIERS or == len`) is awkward, lower `DEFAULT_MIN_INLIERS`
for the test via a kwarg instead of special-casing; keep the production default at 25.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_registration.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/paddleocr/registration.py tests/test_registration.py
git commit -m "feat: ORB homography registration with needs-manual signal"
```

---

## Phase 2 — Full-form marked set + record mapping

### Task 2.1: Plugin emits the FULL marked `(field, code)` set

**Files:**
- Modify: `plugins/paddleocr/main.py` (`classifier_mark_fn` / mark flow) to collect all marked boxes
- Test: `tests/test_paddle_full_marks.py`

- [ ] **Step 1: Write the failing test** (load plugin main via importlib like the other plugin tests;
  inject a fake crop provider/model through the function params)

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_main_fullmarks", _MODULE)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)


def test_classifier_mark_fn_returns_all_marked_field_codes(monkeypatch, tmp_path) -> None:
    # Stub the crop provider to yield three boxes, and the model to mark two of them.
    class _FakeProvider:
        def __init__(self, _path): ...
        def crop(self, _image):
            return {("service.a", "x1"): "r1", ("service.a", "x2"): "r2", ("identity", "patient"): "r3"}

    monkeypatch.setattr(plugin_main.crop_provider, "GeometryCropProvider", _FakeProvider)
    monkeypatch.setattr(plugin_main.mark_model, "load_model", lambda _p: {"threshold": 0.5})
    monkeypatch.setattr(plugin_main.mark_model, "is_marked_by_model", lambda region, _m: region in {"r1", "r3"})
    monkeypatch.setattr(plugin_main, "_existing_path", lambda _p: Path("model.json"))

    marked = plugin_main.marked_boxes_from_classifier(str(tmp_path / "img.png"), template_boxes_path="t.json", model_path="m.json")

    assert sorted(marked) == [("identity", "patient"), ("service.a", "x1")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_full_marks.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `AttributeError: ... 'marked_boxes_from_classifier'`

- [ ] **Step 3: Add `marked_boxes_from_classifier` to `plugins/paddleocr/main.py`**

```python
def marked_boxes_from_classifier(
    image_path: str,
    template_boxes_path: str | os.PathLike[str] | None = None,
    model_path: str | os.PathLike[str] | None = None,
) -> list[tuple[str, str]]:
    """Classify every template box and return ALL marked (field, code) pairs (not just identity/gender)."""
    template_path = Path(template_boxes_path) if template_boxes_path is not None else _HERE / "template_boxes.json"
    model = mark_model.load_model(model_path) if _existing_path(model_path) is not None else None
    marked: list[tuple[str, str]] = []
    for key, region in crop_provider.GeometryCropProvider(template_path).crop(image_path).items():
        if mark_model.is_marked_by_model(region, model):
            marked.append(key)
    return marked
```

Then in `run()` / the response assembly, attach the full marked set to the response so the main app
can map it: add `record["ocr"]["marked_boxes"] = [[field, code] for field, code in marked]` (keep the
existing `classifier_mark_fn` identity/gender behavior for backward compatibility). Keep this purely
additive to the `ocr_plugin.v1` payload.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_full_marks.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/paddleocr/main.py tests/test_paddle_full_marks.py
git commit -m "feat: plugin emits full marked checkbox set"
```

---

### Task 2.2: Main app maps marked boxes → full record

**Files:**
- Create: `src/ocr_from2xlsx/mark_mapping.py`
- Test: `tests/test_mark_mapping.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from ocr_from2xlsx.form_layout import service_record_layout
from ocr_from2xlsx.mark_mapping import marked_boxes_to_selection, apply_marked_boxes


def test_marked_boxes_to_selection_groups_by_field() -> None:
    marked = [["identity", "patient"], ["cancer", "lung_cancer"], ["cancer", "breast_cancer"]]

    selection = marked_boxes_to_selection(marked)

    assert selection["identity"] == ["patient"]
    assert sorted(selection["cancer"]) == ["breast_cancer", "lung_cancer"]


def test_apply_marked_boxes_respects_single_choice() -> None:
    layout = service_record_layout()
    # identity is single-choice: two marks must collapse to at most one
    selection = marked_boxes_to_selection([["identity", "patient"], ["identity", "family_caregiver"]])

    record = apply_marked_boxes(layout, "scan-0001", selection, text_values={})

    assert record.identity in {"patient", "family_caregiver"}  # single value, not both
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_mark_mapping.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/ocr_from2xlsx/mark_mapping.py`**

```python
"""Map a plugin's marked (field, code) set into a full service_record.v1 via the shared layout."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import FormLayout
from training.answer_key import selection_to_record


def marked_boxes_to_selection(marked_boxes: Iterable[Sequence[str]]) -> dict[str, list[str]]:
    selection: dict[str, list[str]] = defaultdict(list)
    for pair in marked_boxes:
        field, code = pair[0], pair[1]
        if code not in selection[field]:
            selection[field].append(code)
    return dict(selection)


def apply_marked_boxes(
    layout: FormLayout,
    record_id: str,
    selection: dict[str, list[str]],
    text_values: dict[str, str],
) -> Record:
    # selection_to_record applies single-choice (choices[0]) and multi-choice (set) constraints.
    return selection_to_record(layout, record_id, selection, text_values)
```

Note: if importing `training.answer_key` from `src/` is undesirable (src importing training), move
`selection_to_record` into `src/ocr_from2xlsx/form_layout.py` (or a new `record_build.py`) and have
`training/answer_key.py` re-export it. Confirm the existing import direction and pick the cleaner one;
keep one source of truth for the constraint logic.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_mark_mapping.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/mark_mapping.py tests/test_mark_mapping.py
git commit -m "feat: map marked checkbox set to full service record"
```

---

### Task 2.3: Scan/prepare flow uses the marked set for the full record

**Files:**
- Modify: `src/ocr_from2xlsx/scan.py` (and/or `prepare_records.py`) to fold `record.ocr.marked_boxes` into the record via `apply_marked_boxes`
- Test: `tests/test_scan_full_record.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.form_template import FormTemplate
from ocr_from2xlsx.scan import prepare_records_from_images


class _MarkedBackend:
    def extract(self, prepared) -> dict:
        return {
            "service_date": "2025-06-25", "identity": "", "gender": "", "name": None,
            "medical_record_no": None,
            "ocr": {"backend": "fake", "raw_text": "", "warnings": [],
                    "marked_boxes": [["identity", "patient"], ["cancer", "lung_cancer"]]},
        }


def test_marked_boxes_populate_full_record(tmp_path: Path) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n")
    template = FormTemplate.load("service_record.v1")

    batch = prepare_records_from_images([image], tmp_path / "out", template, _MarkedBackend())

    record = batch.records[0]
    assert record.identity == "patient"
    assert "lung_cancer" in set(record.patient_fields.cancers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_scan_full_record.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL (marked_boxes not folded into the record).

- [ ] **Step 3: Implement** in `scan.py`: after `normalize_raw_record`, if the raw OCR payload has
  `marked_boxes`, build the selection and merge into the record via `apply_marked_boxes`, preserving
  any text fields (service_date/name/mrn) the backend already produced. Keep it behind a guard so
  records without `marked_boxes` are unchanged.

```python
from ocr_from2xlsx.mark_mapping import apply_marked_boxes, marked_boxes_to_selection
...
marked = (raw_record.get("ocr") or {}).get("marked_boxes")
if marked:
    selection = marked_boxes_to_selection(marked)
    text_values = {"service_date": raw_record.get("service_date") or "",
                   "name": raw_record.get("name") or "",
                   "medical_record_no": raw_record.get("medical_record_no") or ""}
    record = apply_marked_boxes(template_layout, record.record_id, selection, text_values)
    # re-apply the unconfirmed-name warning as the existing flow does
```

Confirm how to obtain the `FormLayout` for the template (e.g. `service_record_layout()`); keep the
existing `record_id`, source, and warning handling.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_scan_full_record.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/scan.py tests/test_scan_full_record.py
git commit -m "feat: fold full marked checkbox set into the prepared record"
```

---

## Phase 3 — Plugin registration wiring + app manual 4-corner

### Task 3.1: Plugin registers before cropping

**Files:**
- Modify: `plugins/paddleocr/main.py` (register the image to canonical before `crop`/`marked_boxes_from_classifier`)
- Test: `tests/test_paddle_registration_wiring.py`

- [ ] **Step 1: Write the failing test** (assert the plugin attempts registration and, on
  `needs_manual`, surfaces it / falls back safely without crashing — inject a fake registration)

```python
import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_main_regwire", _MODULE)
plugin_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plugin_main)


def test_register_for_marks_returns_needs_manual_flag(monkeypatch, tmp_path) -> None:
    # No canonical reference / cv2 path available -> safe needs_manual or None, never raises.
    result = plugin_main.register_image_for_marks(str(tmp_path / "missing.png"))
    assert result is None or hasattr(result, "needs_manual")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_registration_wiring.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `AttributeError: ... 'register_image_for_marks'`

- [ ] **Step 3: Implement** `register_image_for_marks(image_path)` in `main.py`: resolve the canonical
  reference (bundled `canonical_reference.png` next to the plugin), `import cv2`; on any failure (no
  cv2, no reference, exception) return `None` (caller falls back to using the raw image, current
  behavior). When it returns a confident `RegistrationResult`, classify on `result.warped`; emit
  `record.ocr.needs_manual_registration = True` when `needs_manual`. Wire it before
  `marked_boxes_from_classifier`. Keep everything cv2/asset-guarded so the plugin never crashes.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_registration_wiring.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/paddleocr/main.py tests/test_paddle_registration_wiring.py
git commit -m "feat: register form before checkbox classification (plugin)"
```

---

### Task 3.2: Ship the canonical reference + build script

**Files:**
- Create (generated, committed if small): `plugins/paddleocr/canonical_reference.png`
- Modify: `build/build_paddle_plugin.py` (bundle `canonical_reference.png` and `registration.py`)
- Test (modify): `tests/test_build_paddle_plugin.py`

- [ ] Generate the canonical blank-form reference (Phase 0 Step 1) into
  `plugins/paddleocr/canonical_reference.png`. If it is large (>~2 MB), keep it gitignored and generate
  it in the bundle build instead; otherwise commit it as the bundle baseline (mirrors `template_boxes.json`).
- [ ] Update `build/build_paddle_plugin.py` to copy `registration.py` and `canonical_reference.png`
  into the bundle; extend `tests/test_build_paddle_plugin.py` to assert both are bundled.
- [ ] Commit.

```bash
git add plugins/paddleocr/canonical_reference.png build/build_paddle_plugin.py tests/test_build_paddle_plugin.py
git commit -m "build: ship registration module and canonical reference"
```

---

### Task 3.3: App manual 4-corner fallback

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (on `needs_manual_registration`, prompt a 4-corner pick on the preview, re-run)

No CI test (Tk + cv2 + plugin); manual verification in Phase 4. Pure corner-ordering logic, if any, is
unit-tested.

- [ ] **Step 1:** Add `order_quad_corners(points) -> [TL, TR, BR, BL]` to `registration.py` with a unit
  test (sum/diff heuristic), so corner ordering is testable without Tk.

```python
def order_quad_corners(points):
    import numpy as np
    pts = np.array(points, dtype="float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return [tuple(pts[s.argmin()]), tuple(pts[d.argmin()]), tuple(pts[s.argmax()]), tuple(pts[d.argmax()])]
```

- [ ] **Step 2:** In `app.py`, when recognition reports `needs_manual_registration`, show a Toplevel
  with the captured image and let the user click 4 corners (collect clicks, `order_quad_corners`,
  `four_point_warp` to canonical), save the warped image, and re-run recognition on it. Cancel → keep
  current state, no write.

- [ ] **Step 3:** Verify the suite still passes (import-safety): `.venv\Scripts\python -m pytest -q -p no:cacheprovider --basetemp=output/pytest-tmp`.

- [ ] **Step 4: Commit**

```bash
git add src/ocr_from2xlsx/registration.py plugins/paddleocr/registration.py src/ocr_from2xlsx/app.py tests/test_registration.py
git commit -m "feat: manual 4-corner registration fallback in app"
```

(`order_quad_corners` lives in the plugin `registration.py`; the app imports the plugin module the
same way the scan path already reaches plugin helpers, or duplicate the tiny pure function in a
shared `src` util — pick one and keep a single source.)

---

## Phase 4 — Mark-accuracy measurement + docs

### Task 4.1: Post-registration mark accuracy measurement

**Files:**
- Create: `training/eval_marks_registered.py` (or reuse `training/eval_marks.py`)
- Test: `tests/test_eval_marks_registered.py` (pure scoring)

- [ ] Add a pure scorer: given predicted marked `(field, code)` set and a ground-truth set, report
  precision/recall/F1 and per-field hits. TDD it. Then (marker, `.venv-paddle`) run it on a real
  registered capture with a hand-labeled ground truth and record numbers.
- [ ] **Decision:** if post-registration mark accuracy is below target, harvest real checkbox crops
  (`training/harvest_corrections`) and retrain (`training/retrain`, eval-gate); record the measured
  outcome in the PR. Do NOT force a metric — mark the limitation if unmet.

### Task 4.2: Docs, OpenSpec, verification, archive, PR

- [ ] **README**: registration + full-form checkbox extraction; manual 4-corner fallback; that
  accuracy depends on registration precision and real-mark generalization.
- [ ] **CHANGELOG `[Unreleased]`**: registration core, full marked-set emission + mapping, app manual
  fallback, mark-accuracy measurement (with adopt/defer outcome).
- [ ] **Merge delta** from `openspec/changes/add-form-registration/specs/record-preparation/spec.md`
  into `openspec/specs/record-preparation/spec.md`.
- [ ] **Verify**: `.venv\Scripts\python -W error -m pytest -q -p no:cacheprovider --basetemp=output/pytest-tmp`
  and `.venv\Scripts\python -m policy_check --repo .` green. Manually: build the plugin bundle, run a
  real capture end-to-end, confirm the full form fills; record numbers + the Phase 0 overlay in the PR.
- [ ] **Archive** the OpenSpec change to
  `openspec/changes/archive/2026-06-14-add-form-registration/` (rename narrative `proposal.md` →
  `README.md`, add a concise archived `proposal.md`), matching the existing convention.
- [ ] **Commit, push, PR** against `feature/bootstrap-ocr-design`:

```bash
git push -u origin wt/bootstrap-ocr-design/form-registration
gh pr create --base feature/bootstrap-ocr-design --title "feat: form registration + full-checkbox extraction (#22)" --body "<fill PR template: Phase 0 overlay + post-registration mark accuracy numbers, manual-fallback note, test plan incl. real-capture verification, policy checklist checked>"
```

---

## Self-Review Notes

- **Spec coverage:** registration + manual fallback (Phase 0/1/3.3), full-form checkbox extraction
  (Phase 2: plugin emits marked set 2.1, main app maps 2.2/2.3), plugin/app wiring (Phase 3),
  mark-accuracy measurement + retrain decision (Phase 4.1), docs/policy (4.2). Phase 0 honours the
  spec's "precision smoke before the loop" gate.
- **Architecture correction baked in:** mapping (`form_layout`/`selection_to_record`) is MAIN-APP-side
  (Phase 2.2/2.3) because the plugin venv has no `ocr_from2xlsx`; the plugin only emits the marked
  `(field, code)` set (2.1). This is the most important thing for the implementer to get right.
- **Placeholder scan:** no TBD/TODO; implementer notes flag the two real decisions (where
  `selection_to_record` should live to avoid `src`→`training` import; where `order_quad_corners` is
  shared) rather than leaving them vague.
- **Type consistency:** marked set is `list[(field, code)]` / `[[field, code]]` throughout;
  `RegistrationResult(warped, homography, inliers, needs_manual)` used consistently; `four_point_warp(
  image, corners, size=(w,h))` and `register_to_template(image, reference, *, size, min_inliers)`
  identical across tasks.
- **Known risk (Phase 0):** if registration can't hit checkbox-level precision, the gate STOPS the
  work before Phase 2+ — the plan does not assume success.
