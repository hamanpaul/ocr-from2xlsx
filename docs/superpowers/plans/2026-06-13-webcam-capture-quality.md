# Webcam Capture Quality + Recognition Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the webcam into a usable scan input: capture a high-quality still (autofocus + native max resolution + sharpness gate), run it through the existing OCR plugin into a `service_record.v1` batch, fill the review form, then layer optional conditioning and name/MRN recognition improvements — each adopted only if measured to help.

**Architecture:** A reusable, mostly-pure capture-quality core in `capture.py` (sharpness measure + gate decision are pure; the cv2 capture is thin and guarded). A bridge `prepare_records_from_images` mirrors the existing `prepare_records_from_paths` but treats an already-rendered still as the preprocessed page, reusing `normalize_raw_record`/`Batch` so the app and importer consume it unchanged. The app gains a manual "擷取並辨識" button and a `scan` CLI. Phase B (conditioning) and Phase C (name/MRN) are gated on an eval harness that scores a committed captured-form fixture.

**Tech Stack:** Python 3.12; `.venv` for pure tests (has cv2 4.13 + numpy via the `[camera]` extra on this machine, but tests that need cv2/numpy use `pytest.importorskip` so a clean CI skips them); `.venv-paddle` for the OCR plugin + eval harness (marker tests); OpenCV for capture/conditioning; existing PaddleOCR plugin unchanged in contract.

**Branch:** `wt/bootstrap-ocr-design/webcam-capture-quality` (current; builds on PR #20's webcam preview — if #20 has merged into `feature/bootstrap-ocr-design`, rebase onto it; otherwise this branch already descends from #20). Spec: `docs/superpowers/specs/2026-06-13-webcam-capture-quality-design.md`. OpenSpec: `openspec/changes/add-webcam-capture-quality/`.

**Conventions:**
- Pure tests: `.venv\Scripts\python -m pytest <file> -q -p no:cacheprovider --basetemp=output/pytest-tmp`.
- TDD: failing test → see it fail → implement → see it pass → commit.
- Commits end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- cv2/Tk/paddle code is not unit-tested in CI; its pure logic IS. Tests needing cv2/numpy start with `pytest.importorskip("cv2")` (mirrors `tests/test_gen_names_render.py` using `importorskip("PIL.Image")`).
- Phase B and Phase C are **measure-then-decide**: adopt into the default flow only if the eval harness shows improvement; otherwise keep opt-in and record the conclusion. Do NOT force a metric.

---

## Phase A — Capture quality + webcam→OCR→form bridge

### Task A1: Pure sharpness gate decision

**Files:**
- Modify: `src/ocr_from2xlsx/capture.py` (append)
- Test: `tests/test_capture_quality.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from ocr_from2xlsx.capture import DEFAULT_MIN_SHARPNESS, passes_sharpness_gate


def test_passes_sharpness_gate_boundary() -> None:
    assert passes_sharpness_gate(187.6, min_sharpness=100.0) is True
    assert passes_sharpness_gate(18.5, min_sharpness=100.0) is False
    # boundary is inclusive
    assert passes_sharpness_gate(100.0, min_sharpness=100.0) is True


def test_default_min_sharpness_is_reasonable() -> None:
    # Demo: blurry capture measured 18.5, sharp capture 187.6; default sits between.
    assert 50.0 <= DEFAULT_MIN_SHARPNESS <= 150.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_capture_quality.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ImportError: cannot import name 'passes_sharpness_gate'`

- [ ] **Step 3: Append to `src/ocr_from2xlsx/capture.py`**

```python
DEFAULT_MIN_SHARPNESS = 100.0


def passes_sharpness_gate(sharpness: float, *, min_sharpness: float = DEFAULT_MIN_SHARPNESS) -> bool:
    """Pure gate: a frame is sharp enough for OCR when its sharpness meets the threshold."""
    return float(sharpness) >= float(min_sharpness)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_capture_quality.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/capture.py tests/test_capture_quality.py
git commit -m "feat: pure webcam sharpness gate decision"
```

---

### Task A2: Sharpness measurement (cv2/numpy)

**Files:**
- Modify: `src/ocr_from2xlsx/capture.py` (append)
- Test: `tests/test_capture_sharpness_measure.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from ocr_from2xlsx.capture import measure_sharpness


def test_sharp_image_scores_higher_than_blurred() -> None:
    rng = np.random.default_rng(0)
    sharp = (rng.integers(0, 256, size=(200, 200))).astype("uint8")
    blurred = cv2.GaussianBlur(sharp, (0, 0), sigmaX=4)

    assert measure_sharpness(sharp) > measure_sharpness(blurred)


def test_measure_accepts_color_or_gray() -> None:
    color = np.zeros((50, 50, 3), dtype="uint8")
    gray = np.zeros((50, 50), dtype="uint8")
    # Flat images have ~zero Laplacian variance and must not raise.
    assert measure_sharpness(color) >= 0.0
    assert measure_sharpness(gray) >= 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_capture_sharpness_measure.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ImportError: cannot import name 'measure_sharpness'` (or SKIP if cv2/numpy absent)

- [ ] **Step 3: Append to `src/ocr_from2xlsx/capture.py`**

```python
def measure_sharpness(image) -> float:
    """Variance of the Laplacian — higher means sharper/more detail. Accepts gray or BGR."""
    import cv2

    gray = image
    if hasattr(image, "ndim") and image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_capture_sharpness_measure.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/capture.py tests/test_capture_sharpness_measure.py
git commit -m "feat: measure frame sharpness via variance of Laplacian"
```

---

### Task A3: Capture a still at native max resolution with autofocus

**Files:**
- Modify: `src/ocr_from2xlsx/capture.py` (append `CaptureResult`, `negotiate_max_resolution`, `capture_still`)
- Test: `tests/test_capture_still.py`

cv2 + camera hardware can't run in CI. Test the resolution-negotiation read-back logic with a fake
capture object; `capture_still` end-to-end is manually verified (Task A7).

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from ocr_from2xlsx.capture import negotiate_max_resolution


class _FakeCap:
    """Mimics cv2.VideoCapture set/get clamping to a device maximum."""

    def __init__(self, max_w: int, max_h: int) -> None:
        self._max_w, self._max_h = max_w, max_h
        self._w, self._h = 640, 480

    def set(self, prop: int, value: float) -> bool:
        # cv2.CAP_PROP_FRAME_WIDTH == 3, CAP_PROP_FRAME_HEIGHT == 4
        if prop == 3:
            self._w = min(int(value), self._max_w)
        elif prop == 4:
            self._h = min(int(value), self._max_h)
        return True

    def get(self, prop: int) -> float:
        if prop == 3:
            return float(self._w)
        if prop == 4:
            return float(self._h)
        return 0.0


def test_negotiate_reads_back_device_max_not_requested() -> None:
    cap = _FakeCap(max_w=3264, max_h=2448)

    width, height = negotiate_max_resolution(cap, request=(10000, 10000))

    assert (width, height) == (3264, 2448)  # clamped to device max, read back
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_capture_still.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ImportError: cannot import name 'negotiate_max_resolution'`

- [ ] **Step 3: Append to `src/ocr_from2xlsx/capture.py`**

```python
from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True, slots=True)
class CaptureResult:
    frame: object | None
    resolution: tuple[int, int]
    sharpness: float
    brightness: float
    passed: bool


def negotiate_max_resolution(cap, *, request: tuple[int, int] = (10000, 10000)) -> tuple[int, int]:
    """Pull the camera's native max: request an oversized resolution, read back the actual."""
    import cv2

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, request[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, request[1])
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return width, height


def capture_still(
    index: int = 0,
    *,
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
    warmup_frames: int = 80,
) -> CaptureResult | None:
    """Capture a single still: autofocus on, native max resolution, warm up, measure quality.

    Returns None when the camera cannot be opened or no frame is read. cv2-guarded.
    """
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        return None
    try:
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        width, height = negotiate_max_resolution(cap)
        frame = None
        for _ in range(max(1, warmup_frames)):
            ok, candidate = cap.read()
            if ok:
                frame = candidate
    finally:
        cap.release()
    if frame is None:
        return None
    sharpness = measure_sharpness(frame)
    import cv2 as _cv2

    brightness = float(_cv2.cvtColor(frame, _cv2.COLOR_BGR2GRAY).mean())
    return CaptureResult(
        frame=frame,
        resolution=(width, height),
        sharpness=sharpness,
        brightness=brightness,
        passed=passes_sharpness_gate(sharpness, min_sharpness=min_sharpness),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_capture_still.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/capture.py tests/test_capture_still.py
git commit -m "feat: capture still at native max resolution with autofocus and quality"
```

---

### Task A4: Bridge — recognize a still image into a batch

**Files:**
- Create: `src/ocr_from2xlsx/scan.py`
- Test: `tests/test_scan_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.form_template import FormTemplate
from ocr_from2xlsx.scan import prepare_records_from_images


class _FakeBackend:
    """OcrBackend stub: returns a canned raw record regardless of the prepared page."""

    def extract(self, prepared) -> dict:
        return {
            "service_date": "2025-06-25",
            "identity": "patient",
            "gender": "female",
            "name": None,
            "medical_record_no": None,
            "ocr": {"backend": "fake", "raw_text": "癌症資源中心服務紀錄表", "warnings": []},
        }


def test_prepare_records_from_images_builds_batch_with_image_source(tmp_path: Path) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n")  # content irrelevant to the fake backend
    out_dir = tmp_path / "out"
    template = FormTemplate.load("service_record.v1")

    batch = prepare_records_from_images([image], out_dir, template, _FakeBackend(), created_at="2026-06-13T00:00:00+08:00")

    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.service_date == "2025-06-25"
    assert record.record_id  # stable id assigned
    # the still is copied next to the output so the review UI can preview it
    assert (out_dir / "shot.png").is_file()
    assert record.source.kind == "camera_still"
    assert record.source.preprocessed_image_path == "shot.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_scan_bridge.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_from2xlsx.scan'`

- [ ] **Step 3: Create `src/ocr_from2xlsx/scan.py`**

```python
"""Bridge a captured/still image through the OCR backend into a normalized batch.

Mirrors prepare_records.prepare_records_from_paths, but the still IS the preprocessed page —
no PDF render. The image is copied next to the output so the review UI can resolve its preview.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from ocr_from2xlsx.domain import Batch, SourceBatch, SourceInfo
from ocr_from2xlsx.form_template import FormTemplate
from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED
from ocr_from2xlsx.normalizer import normalize_raw_record
from ocr_from2xlsx.ocr_backend import OcrBackend
from ocr_from2xlsx.preprocess import PreparedPage


def _append_unique_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def prepare_records_from_images(
    image_paths: list[Path | str],
    output_dir: Path | str,
    template: FormTemplate,
    backend: OcrBackend,
    created_at: str | None = None,
) -> Batch:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    records = []
    for sequence, image_path in enumerate(image_paths, start=1):
        image_path = Path(image_path)
        local_image = output_dir / image_path.name
        if image_path.resolve() != local_image.resolve():
            shutil.copyfile(image_path, local_image)
        prepared = PreparedPage(
            image_path=local_image,
            template_id=template.template_id,
            source=SourceInfo(
                kind="camera_still",
                document_path=image_path.name,
                page_number=sequence,
                preprocessed_image_path=local_image.name,
                template_id=template.template_id,
            ),
        )
        raw_record = backend.extract(prepared)
        if not raw_record.get("record_id"):
            raw_record["record_id"] = f"scan-{sequence:04d}"
        source = raw_record.get("source") if isinstance(raw_record.get("source"), dict) else {}
        source.update(
            {
                "kind": prepared.source.kind,
                "document_path": prepared.source.document_path,
                "page_number": prepared.source.page_number,
                "preprocessed_image_path": prepared.source.preprocessed_image_path,
                "template_id": prepared.source.template_id,
            }
        )
        raw_record["source"] = source
        record = normalize_raw_record(raw_record)
        if record.name:
            _append_unique_warning(record.ocr.warnings, NAME_UNCONFIRMED)
        records.append(record)
    return Batch(
        source_batch=SourceBatch(
            created_at=created_at,
            source_type="scan_records",
            template_name=template.template_id,
        ),
        records=records,
    )
```

Note for the implementer: confirm `SourceInfo` accepts `kind="camera_still"` (it is a free string in
`domain.py`; if it is an enum/validated set, add `camera_still` there and update its test). Confirm
`FormTemplate.load("service_record.v1")` is the loader used by `cli._resolve_template`; if the loader
has a different name, use that and keep the test in sync.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_scan_bridge.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/scan.py tests/test_scan_bridge.py
git commit -m "feat: bridge a still image through OCR into a normalized batch"
```

---

### Task A5: `scan` CLI subcommand

**Files:**
- Modify: `src/ocr_from2xlsx/cli.py` (add `scan` subparser + handler)
- Test: `tests/test_cli_scan.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx import cli


def test_scan_cli_writes_batch_from_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n")
    output = tmp_path / "prepared.json"

    class _FakeBackend:
        def extract(self, prepared) -> dict:
            return {"service_date": "2025-06-25", "identity": "patient", "gender": "female",
                    "ocr": {"backend": "fake", "raw_text": "x", "warnings": []}}

    # Avoid resolving a real OCR plugin in the test.
    monkeypatch.setattr(cli, "_resolve_scan_backend", lambda args: _FakeBackend())

    exit_code = cli.main(["scan", "--image", str(image), "--output", str(output)])

    assert exit_code == 0
    assert output.is_file()


def test_scan_help_lists_image_and_camera(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["scan", "--help"])
    out = capsys.readouterr().out
    assert "--image" in out and "--camera" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cli_scan.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL (no `scan` subcommand / no `_resolve_scan_backend`)

- [ ] **Step 3: Implement in `src/ocr_from2xlsx/cli.py`**

Add the subparser in `build_parser()` just before `parser.set_defaults(command="app")`:

```python
    scan_parser = subparsers.add_parser(
        "scan",
        help="Capture a webcam still (or read an image) and recognize it into normalized JSON.",
        description="Capture a webcam still (or read an image) and recognize it into normalized JSON.",
    )
    scan_parser.add_argument("--output", required=True, help="Output JSON path.")
    scan_parser.add_argument("--image", help="Recognize this image file instead of capturing.")
    scan_parser.add_argument("--camera", type=int, default=0, help="Webcam index when capturing.")
    scan_parser.add_argument("--template-id", default="service_record.v1")
    scan_parser.add_argument("--ocr-backend", choices=["plugin"], default="plugin")
    scan_parser.add_argument("--ocr-plugin-dir", help="OCR plugin directory (else OCR_PLUGIN_DIR/default).")
    scan_parser.add_argument(
        "--min-sharpness", type=float, default=None,
        help="Reject captures below this sharpness (default: capture.DEFAULT_MIN_SHARPNESS).",
    )
```

Add a backend resolver + handler. Near the other backend resolution in `main()`:

```python
def _resolve_scan_backend(args):
    from ocr_from2xlsx.ocr_backend import PluginOcrBackend

    return PluginOcrBackend.resolve(explicit_dir=args.ocr_plugin_dir)
```

In `main()`, add the `scan` branch (before the `app` branch):

```python
    if args.command == "scan":
        from ocr_from2xlsx.capture import DEFAULT_MIN_SHARPNESS, capture_still
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.scan import prepare_records_from_images

        template = _resolve_template(args.template_id)
        backend = _resolve_scan_backend(args)
        output_path = Path(args.output)
        output_dir = output_path.parent

        if args.image:
            image_path = Path(args.image)
        else:
            import cv2  # noqa: F401  (only needed when capturing)

            min_sharpness = args.min_sharpness if args.min_sharpness is not None else DEFAULT_MIN_SHARPNESS
            result = capture_still(args.camera, min_sharpness=min_sharpness)
            if result is None:
                print("scan: no camera available", file=sys.stderr)
                return 1
            if not result.passed:
                print(
                    f"scan: capture too blurry (sharpness {result.sharpness:.1f} < {min_sharpness:.1f}); "
                    "improve focus/lighting/distance and retry",
                    file=sys.stderr,
                )
                return 1
            output_dir.mkdir(parents=True, exist_ok=True)
            image_path = output_dir / "scan-capture.png"
            import cv2

            cv2.imwrite(str(image_path), result.frame)

        batch = prepare_records_from_images([image_path], output_dir, template, backend)
        dump_batch(batch, output_path)
        print(output_path)
        return 0
```

(Reuse the existing `_resolve_template` helper. If `dump_batch` lives elsewhere, import it from there —
it is used by the `sample-json` branch.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_cli_scan.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `2 passed`

- [ ] **Step 5: Regenerate the README CLI-help marker**

The root help now lists `scan`. Regenerate the `<!-- BEGIN: cli-help -->` block in `README.md` to
match `ocr-from2xlsx --help` (policy R-16). Then commit.

```bash
git add src/ocr_from2xlsx/cli.py tests/test_cli_scan.py README.md
git commit -m "feat: add scan CLI for webcam/image recognition"
```

---

### Task A6: App "擷取並辨識" button

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (toolbar button + handler; reuse `loaded_json_path` load path)

No CI test (Tk + cv2 + plugin). The handler delegates to the tested `capture_still` + bridge; manual
verification in Task A7.

- [ ] **Step 1: Add the toolbar button**

In `_build_ui`, after the "選擇攝影機" button, add:

```python
        ttk.Button(toolbar, text="擷取並辨識", command=self._capture_and_recognize).pack(
            side=tk.LEFT, padx=4
        )
```

- [ ] **Step 2: Implement the handler**

Add to `ReviewApp` (near `_load_json`):

```python
    def _capture_and_recognize(self) -> None:
        from ocr_from2xlsx.capture import DEFAULT_MIN_SHARPNESS, capture_still

        self._stop_camera()  # release the live-preview handle before grabbing a still
        result = capture_still(min_sharpness=DEFAULT_MIN_SHARPNESS)
        if result is None:
            messagebox.showwarning("擷取並辨識", "找不到可用的攝影機。")
            self._init_camera()
            return
        if not result.passed:
            messagebox.showwarning(
                "擷取並辨識",
                f"畫面太模糊（清晰度 {result.sharpness:.0f}）。請調整對焦/光線/距離後重試。",
            )
            self._init_camera()
            return
        try:
            self._recognize_capture(result.frame)
        except Exception as error:  # noqa: BLE001 - surface, never crash the app
            messagebox.showerror("擷取並辨識", f"辨識失敗：{error}")
        self._init_camera()

    def _recognize_capture(self, frame) -> None:
        import cv2

        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.ocr_backend import PluginOcrBackend
        from ocr_from2xlsx.scan import prepare_records_from_images

        out_dir = Path(filedialog.askdirectory(title="選擇辨識輸出資料夾") or "")
        if str(out_dir) == ".":
            return
        image_path = out_dir / "scan-capture.png"
        cv2.imwrite(str(image_path), frame)
        backend = PluginOcrBackend.resolve()
        template = service_record_layout_template()  # see note below
        batch = prepare_records_from_images([image_path], out_dir, template, backend)
        json_path = out_dir / "scan-prepared.json"
        dump_batch(batch, json_path)
        self.records = list(JsonRecordSource(json_path).records())
        self.loaded_json_path = json_path
        self.current_index = 0 if self.records else -1
        self._show_current_record()  # reuse the existing record→form population
```

Implementer notes:
- Use the same template resolver the CLI uses (`cli._resolve_template("service_record.v1")` or the
  equivalent loader). Replace `service_record_layout_template()` with the actual call; do not invent a
  new helper.
- Use the existing method the app already calls after `_load_json` to populate the form for
  `current_index` (read `app.py` around `_load_json`/navigation and call that exact method instead of
  `_show_current_record` if it is named differently).
- `PluginOcrBackend.resolve()` needs a built plugin bundle (see Task A7); on failure it raises and the
  `except` shows an error — acceptable.

- [ ] **Step 3: Verify the suite still passes (import-safety)**

Run: `.venv\Scripts\python -m pytest -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: all pass (no window opens; handler is lazy-imported).

- [ ] **Step 4: Commit**

```bash
git add src/ocr_from2xlsx/app.py
git commit -m "feat: app capture-and-recognize button"
```

---

### Task A7: Manual end-to-end verification (Phase A)

**Files:** none (verification; record results in the PR).

- [ ] Build the plugin bundle so the app/CLI can run OCR:
  `.venv\Scripts\python build/build_paddle_plugin.py` (produces `dist/plugins/paddleocr`). Confirm the
  local `plugins/paddleocr/name_rec/` model is included if present.
- [ ] CLI on a known-good still: capture or pass `--image` of a sharp, filled, well-lit form:
  `.venv\Scripts\python -m ocr_from2xlsx scan --image <good.png> --output output\scan\prepared.json --ocr-plugin-dir dist\plugins\paddleocr`
  Confirm `service_date`/`identity`/`gender` are recognized in the JSON.
- [ ] App: launch, click "擷取並辨識" with the form positioned well; confirm the form fills. Confirm a
  blurry capture is rejected with the retry prompt.
- [ ] Record the recognized fields + sharpness numbers in the PR body.

---

## Phase B — Optional conditioning (adopt only if measured to help)

### Task B1: OpenCV enhancement function

**Files:**
- Create: `src/ocr_from2xlsx/document_condition.py`
- Test: `tests/test_document_condition.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from ocr_from2xlsx.document_condition import enhance


def test_enhance_returns_gray_uint8_same_or_larger() -> None:
    src = (np.random.default_rng(0).integers(0, 256, size=(100, 150, 3))).astype("uint8")

    out = enhance(src)

    assert out.dtype == np.uint8
    assert out.ndim == 2  # grayscale
    assert out.shape[0] >= 100 and out.shape[1] >= 150  # never downscales below input
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_document_condition.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError` (or SKIP without cv2)

- [ ] **Step 3: Create `src/ocr_from2xlsx/document_condition.py`**

```python
"""Optional OpenCV enhancement for captured document images (grayscale + contrast + denoise)."""
from __future__ import annotations

MIN_LONG_EDGE = 2000


def enhance(image):
    """Grayscale, upscale small captures, CLAHE contrast, light denoise. Returns a uint8 gray array."""
    import cv2

    gray = image
    if hasattr(image, "ndim") and image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    long_edge = max(height, width)
    if long_edge < MIN_LONG_EDGE:
        scale = MIN_LONG_EDGE / float(long_edge)
        gray = cv2.resize(gray, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.fastNlMeansDenoising(gray, h=7)
    return gray
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_document_condition.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/document_condition.py tests/test_document_condition.py
git commit -m "feat: optional OpenCV document enhancement"
```

---

### Task B2: Plugin doc-orientation/unwarp toggle for the scan path

**Files:**
- Modify: `plugins/paddleocr/main.py` (read an env/request flag; pass to `_paddle_ocr_fn`)
- Test: `tests/test_paddle_docpre_flag.py`

- [ ] **Step 1: Write the failing test** (string/contract-level, no paddle)

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_plugin_docpre", _MODULE_PATH)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)


def test_docpre_enabled_reads_env(monkeypatch) -> None:
    monkeypatch.delenv("SCAN_DOC_PREPROCESS", raising=False)
    assert plugin_main._doc_preprocess_enabled() is False
    monkeypatch.setenv("SCAN_DOC_PREPROCESS", "1")
    assert plugin_main._doc_preprocess_enabled() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_docpre_flag.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `AttributeError: ... '_doc_preprocess_enabled'`

- [ ] **Step 3: Implement in `plugins/paddleocr/main.py`**

```python
def _doc_preprocess_enabled() -> bool:
    return os.environ.get("SCAN_DOC_PREPROCESS", "").strip() in {"1", "true", "True"}
```

Thread it into the real engine `_paddle_ocr_fn` so orientation/unwarp turn on only when enabled:

```python
    use_doc = _doc_preprocess_enabled()
    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=use_doc,
        use_doc_unwarping=use_doc,
        use_textline_orientation=True,
    )
```

The scan bridge sets `SCAN_DOC_PREPROCESS=1` in the plugin subprocess env when invoking OCR for the
scan path (leave the existing PDF/prepare-records path untouched, so scans are unchanged).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_docpre_flag.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/paddleocr/main.py tests/test_paddle_docpre_flag.py
git commit -m "feat: gated doc orientation/unwarp for the scan path"
```

---

### Task B3: Measure conditioning with the eval harness, then decide

**Files:** uses the eval harness (Task D1). No new production code unless adopted.

- [ ] Run the eval harness on the fixture image three ways: (a) raw, (b) `enhance` applied,
  (c) `SCAN_DOC_PREPROCESS=1`. Record per-field scores.
- [ ] **Decision:** wire `enhance`/the flag into the default scan path ONLY for the variant(s) that
  improve the score. If none improve, keep them opt-in (a `--enhance` / env flag) and write the
  measured conclusion into the PR and the design doc's "成功準則". Do NOT adopt an unmeasured change.

---

## Phase C — Handwritten name + MRN recognition improvements

### Task C1: Name-anchor location + MRN extraction on captured lines

**Files:**
- Modify: `plugins/paddleocr/field_extract.py` and/or `plugins/paddleocr/name_crop.py`
- Test: `tests/test_paddle_field_extract_scan.py`

- [ ] **Step 1: Capture a real fixture of OCR lines.** From the Phase A good-capture run, dump the
  plugin's `lines` (text + boxes) for the fixture form to `tests/fixtures/scan/lines.json` (a list of
  `{"text": ..., "box": [[x,y]...]}`). This is real recognizer output, used as a deterministic fixture.

- [ ] **Step 2: Write the failing test** against that fixture (adjust the expected values to the real
  ground truth of your fixture form):

```python
from __future__ import annotations

import json
from pathlib import Path

from plugins_paddle_field_extract import extract_fields  # see loader note

_LINES = json.loads((Path(__file__).resolve().parent / "fixtures" / "scan" / "lines.json").read_text(encoding="utf-8"))


def test_scan_lines_recover_mrn_and_name_anchor() -> None:
    fields = extract_fields(_LINES, marked_labels=set())
    # Ground truth from the committed fixture form:
    assert fields["medical_record_no"]  # MRN now recovered (was None pre-change)
    # name handling: either a name value or a name crop anchor was located
    assert fields["name"] is not None or fields.get("name_anchor") is not None
```

Loader note: `field_extract.py` is loaded by the plugin via importlib, not a package import. In the
test, load it the same way the other plugin tests do (see `tests/test_paddle_field_extract.py` for the
exact `spec_from_file_location` pattern) instead of the placeholder import above.

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_field_extract_scan.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL (MRN/name not currently recovered on this fixture).

- [ ] **Step 4: Implement the extraction improvements** in `field_extract.py`/`name_crop.py` driven by
  what the fixture shows is missing (e.g. broaden the MRN anchor tokens / digit-run acceptance; widen
  the name-anchor search to where this form places the handwritten name). Keep changes minimal and
  covered by the fixture test; do not regress the existing `tests/test_paddle_field_extract.py`.

- [ ] **Step 5: Run both field-extract test files to verify pass + no regression**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_field_extract.py tests/test_paddle_field_extract_scan.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: all pass.

- [ ] **Step 6: Decision + commit.** If the fixture-driven changes cannot recover name/MRN without
  regressing the existing tests, STOP forcing it: keep the change minimal, mark the limitation in the
  PR and design doc, and leave name/MRN as human-filled. Commit whatever is genuinely achieved.

```bash
git add plugins/paddleocr/field_extract.py plugins/paddleocr/name_crop.py tests/test_paddle_field_extract_scan.py tests/fixtures/scan/lines.json
git commit -m "feat: improve name-anchor/MRN recovery on captured forms"
```

---

## Cross-cutting

### Task D1: Eval harness on a captured-form fixture

**Files:**
- Create: `training/eval_scan.py`
- Create: `tests/fixtures/scan/` ground truth (`expected.json`) + a committed good-capture image
- Test: `tests/test_eval_scan.py`

- [ ] **Step 1: Write the failing test** (pure scoring, no paddle)

```python
from __future__ import annotations

from training.eval_scan import score_fields


def test_score_fields_counts_exact_field_matches() -> None:
    predicted = {"service_date": "2025-06-25", "identity": "patient", "gender": "female", "name": None}
    expected = {"service_date": "2025-06-25", "identity": "patient", "gender": "male", "name": "葉心安"}

    metrics = score_fields(predicted, expected)

    assert metrics["total"] == 4
    assert metrics["correct"] == 2  # service_date + identity
    assert metrics["per_field"]["gender"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_eval_scan.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `training/eval_scan.py`**

```python
"""Score recognized fields against ground truth for a captured-form fixture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCORED_FIELDS = ("service_date", "identity", "gender", "name", "medical_record_no")


def score_fields(predicted: dict, expected: dict) -> dict:
    per_field = {}
    for key in SCORED_FIELDS:
        if key in expected:
            per_field[key] = (predicted.get(key) or None) == (expected.get(key) or None)
    correct = sum(1 for value in per_field.values() if value)
    return {"total": len(per_field), "correct": correct, "per_field": per_field}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a recognized record against ground truth.")
    parser.add_argument("--predicted", required=True, help="record JSON (the plugin's record)")
    parser.add_argument("--expected", required=True, help="ground-truth fields JSON")
    args = parser.parse_args(argv)
    predicted = json.loads(Path(args.predicted).read_text(encoding="utf-8"))
    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    metrics = score_fields(predicted.get("record", predicted), expected)
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_eval_scan.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit** (commit the scorer now; the image fixture + `expected.json` land with Task A7/C1 captures)

```bash
git add training/eval_scan.py tests/test_eval_scan.py
git commit -m "feat: scan field-accuracy eval harness"
```

---

### Task D2: Docs, OpenSpec base spec, verification, archive, PR

- [ ] **README**: document the `scan` CLI and the app "擷取並辨識" button, the autofocus + native-max-
  resolution capture, the sharpness gate (retake on blur), and that opencv must be installed
  (`pip install -e ".[dev,camera]"`) and the plugin bundle built for OCR. Regenerate the cli-help marker.
- [ ] **CHANGELOG `[Unreleased]`**: one entry for webcam capture quality + scan bridge (#19 follow-up),
  plus Phase B/C outcomes (adopted or deferred-with-reason).
- [ ] **Merge delta into base spec**: append the two `### Requirement:` blocks from
  `openspec/changes/add-webcam-capture-quality/specs/record-preparation/spec.md` into
  `openspec/specs/record-preparation/spec.md`.
- [ ] **Verification battery**:

```powershell
.venv\Scripts\python -W error -m pytest -q -p no:cacheprovider --basetemp=output/pytest-tmp
.venv\Scripts\python -m policy_check --repo .
```
Expected: all green, policy 0 failures. (Marker/paddle eval harness + manual webcam steps recorded in PR.)

- [ ] **Archive the OpenSpec change**: tick `tasks.md`, move `openspec/changes/add-webcam-capture-quality/`
  to `openspec/changes/archive/2026-06-13-add-webcam-capture-quality/` (rename narrative `proposal.md`
  to `README.md`, add a short archived `proposal.md`), matching the existing archive convention.
- [ ] **Commit, push, PR**:

```bash
git add -A
git commit -m "docs(openspec): archive add-webcam-capture-quality"
git push -u origin wt/bootstrap-ocr-design/webcam-capture-quality
gh pr create --base feature/bootstrap-ocr-design --title "feat: webcam capture quality + recognition bridge (#19)" --body "<fill PR template: summary with recognized-field numbers + sharpness, Phase B/C adopt-or-defer decisions, test plan incl. manual webcam verification, policy checklist all checked>"
```

---

## Self-Review Notes

- **Spec coverage:** capture quality + native-max resolution + sharpness gate (A1–A3); webcam/image →
  OCR → form bridge (A4–A6) and CLI/app consumers (A5/A6) — covers the "capture a high-quality still"
  and "recognize a captured image" requirements and both no-camera/blurry/OCR-fail fallbacks; optional
  conditioning measured-then-decided (B1–B3); name/MRN improvements measured (C1); eval harness (D1);
  docs/policy/archive (D2). Marks stay best-effort (no registration task) per the deferral.
- **Placeholder scan:** no TBD/TODO; every code step has concrete code. Implementer notes flag the two
  places to confirm against reality (`SourceInfo.kind` free-string; the exact template loader and the
  app's record→form method name) rather than leaving them vague.
- **Type consistency:** `CaptureResult(frame, resolution, sharpness, brightness, passed)` used the same
  way in A3/A5/A6; `capture_still(...) -> CaptureResult | None` consistently; `passes_sharpness_gate`
  and `DEFAULT_MIN_SHARPNESS` shared across A1/A3/A5/A6; `prepare_records_from_images(image_paths,
  output_dir, template, backend, created_at)` identical in A4/A5/A6; `score_fields(predicted, expected)`
  consistent in D1.
- **Risk/uncertainty:** the plugin subprocess interpreter requires a built bundle for the app/CLI OCR
  path (Task A7 builds it) — the demo proved recognition works on a good capture, so this is plumbing.
  Phase B/C are explicitly measure-then-decide so an autonomous run won't force an unmeasured change.
```
