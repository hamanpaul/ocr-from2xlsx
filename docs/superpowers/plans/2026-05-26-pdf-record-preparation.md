# PDF Record Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fixed-layout PDF/image preparation flow that emits normalized `Batch`/`Record` JSON from source documents and feeds the existing `validate-json` and `import-json` pipeline.

**Architecture:** Add an upstream `prepare-records` boundary in front of the existing JSON validation/import flow. The new boundary renders PDF pages or images into prepared page objects, applies a fixed service-record template, obtains field values through a replaceable OCR backend interface, normalizes them into the existing schema, and verifies the result against a manually curated gold fixture for the provided reference PDF.

**Tech Stack:** Python 3.12+, pypdf, PyMuPDF, pytest, openpyxl, PyInstaller, OpenSpec change `openspec/changes/add-pdf-record-preprocessing/`

---

## Spec Reference

Read and stay aligned with:

- `openspec/changes/add-pdf-record-preprocessing/proposal.md`
- `openspec/changes/add-pdf-record-preprocessing/design.md`
- `openspec/changes/add-pdf-record-preprocessing/specs/record-preparation/spec.md`

Important constraints:

- Keep `Batch` / `Record` JSON as the only downstream contract.
- Preserve workbook safety: `prepare-records` must not write XLSX files directly.
- Treat one PDF page or one image as one record for this iteration.
- Preserve source provenance and OCR metadata in optional fields.
- Make the OCR backend replaceable; use deterministic fixture-backed extraction in tests.
- Keep the provided `tests/fixtures/pdf/for testing only.pdf` as the canonical regression document.

## File Structure

Create or modify the following files:

```text
src/ocr_from2xlsx/
  capture.py                    Keep document sources; extend page metadata if needed.
  cli.py                        Add prepare-records command.
  domain.py                     Extend SourceInfo/OcrInfo for provenance and OCR metadata.
  json_io.py                    Reuse existing load/dump helpers; no new final format.
  normalizer.py                 Convert extracted field maps into Record objects.
  ocr_backend.py                Define backend protocol and deterministic fixture backend.
  prepare_records.py            Orchestrate source loading, preprocessing, OCR, and normalization.
  preprocess.py                 Render PDF pages / normalize images into PreparedPage objects.
  form_template.py              Fixed template metadata and field-zone definitions for the service record.
tests/
  test_json_io.py               Provenance/OCR metadata round-trip coverage.
  test_capture.py               Existing PDF source coverage stays intact.
  test_preprocess.py            Prepared-page rendering and template assignment tests.
  test_prepare_records.py       Fixture-driven normalization pipeline tests.
  test_cli.py                   prepare-records CLI coverage.
  test_e2e.py                   prepare-records -> import-json regression path.
  fixtures/pdf/
    for testing only.pdf
    for testing only.expected.json
    for testing only.ocr.json
pyproject.toml                  Add preprocessing dependencies.
README.md                       Document prepare-records usage.
CHANGELOG.md                    Add Unreleased entry for the new preparation flow.
```

Keep responsibilities narrow:

- `preprocess.py` owns file-to-page rendering only.
- `form_template.py` owns template IDs and field zones only.
- `ocr_backend.py` owns OCR backend protocol and fixture lookup only.
- `prepare_records.py` owns orchestration only.
- `normalizer.py` owns raw-field-to-`Record` mapping only.

## Task 1: Extend the normalized schema for provenance and OCR metadata

**Files:**
- Modify: `src/ocr_from2xlsx/domain.py`
- Test: `tests/test_json_io.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_json_io.py`:

```python
def test_batch_json_round_trip_keeps_pdf_source_and_ocr_metadata(tmp_path: Path) -> None:
    batch = Batch(
        source_batch=SourceBatch(
            created_at="2026-05-26T09:00:00+08:00",
            source_type="prepare_records",
            template_name="service_record.v1",
        ),
        records=[make_record()],
    )
    record = batch.records[0]
    record.source.kind = "pdf_page"
    record.source.document_path = "tests/fixtures/pdf/for testing only.pdf"
    record.source.page_number = 1
    record.source.preprocessed_image_path = "tmp/scan-0001.png"
    record.source.template_id = "service_record.v1"
    record.ocr.backend = "fixture"
    record.ocr.model = "manual-gold"
    record.ocr.field_confidences = {"name": 0.99, "service_date": 0.95}

    path = tmp_path / "prepared.json"
    dump_batch(batch, path)
    loaded = load_batch(path)

    assert loaded.records[0].source.kind == "pdf_page"
    assert loaded.records[0].source.document_path == "tests/fixtures/pdf/for testing only.pdf"
    assert loaded.records[0].source.page_number == 1
    assert loaded.records[0].source.preprocessed_image_path == "tmp/scan-0001.png"
    assert loaded.records[0].source.template_id == "service_record.v1"
    assert loaded.records[0].ocr.backend == "fixture"
    assert loaded.records[0].ocr.model == "manual-gold"
    assert loaded.records[0].ocr.field_confidences == {"name": 0.99, "service_date": 0.95}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_json_io.py::test_batch_json_round_trip_keeps_pdf_source_and_ocr_metadata
```

Expected: FAIL with an `AttributeError` or constructor error because `SourceInfo` and `OcrInfo` do not yet expose the new fields.

- [ ] **Step 3: Write the minimal implementation**

Update `src/ocr_from2xlsx/domain.py` with the new optional fields and parsers:

```python
def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an int")
    return value


def _require_float_map(value: Any, field_name: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    result: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings")
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{field_name}.{key} must be a number")
        result[key] = float(item)
    return result


@dataclass(slots=True)
class SourceInfo:
    kind: str | None = None
    document_path: str | None = None
    page_number: int | None = None
    image_path: str | None = None
    preprocessed_image_path: str | None = None
    capture_time: str | None = None
    template_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceInfo":
        data = _require_dict(data, "source")
        return cls(
            kind=_optional_string(data.get("kind"), "source.kind"),
            document_path=_optional_string(data.get("document_path"), "source.document_path"),
            page_number=_optional_int(data.get("page_number"), "source.page_number"),
            image_path=_optional_string(data.get("image_path"), "source.image_path"),
            preprocessed_image_path=_optional_string(
                data.get("preprocessed_image_path"),
                "source.preprocessed_image_path",
            ),
            capture_time=_optional_string(data.get("capture_time"), "source.capture_time"),
            template_id=_optional_string(data.get("template_id"), "source.template_id"),
        )


@dataclass(slots=True)
class OcrInfo:
    backend: str = ""
    model: str = ""
    confidence: float | None = None
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)
    field_confidences: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OcrInfo":
        data = _require_dict(data, "ocr")
        return cls(
            backend=_lenient_string(data.get("backend"), "ocr.backend"),
            model=_lenient_string(data.get("model"), "ocr.model"),
            confidence=_optional_float(data.get("confidence"), "ocr.confidence"),
            raw_text=_lenient_string(data.get("raw_text"), "ocr.raw_text"),
            warnings=_require_list(data.get("warnings"), "ocr.warnings", item_type=str),
            field_confidences=_require_float_map(data.get("field_confidences"), "ocr.field_confidences"),
        )
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_json_io.py::test_batch_json_round_trip_keeps_pdf_source_and_ocr_metadata
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/ocr_from2xlsx/domain.py tests/test_json_io.py
git commit -m "feat: add record provenance metadata"
```

## Task 2: Add page preparation and fixed-template metadata

**Files:**
- Create: `src/ocr_from2xlsx/preprocess.py`
- Create: `src/ocr_from2xlsx/form_template.py`
- Modify: `pyproject.toml`
- Test: `tests/test_preprocess.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_preprocess.py` with:

```python
from pathlib import Path

from ocr_from2xlsx.capture import PdfDocumentSource
from ocr_from2xlsx.form_template import service_record_template
from ocr_from2xlsx.preprocess import prepare_pdf_page


def test_prepare_pdf_page_renders_png_and_assigns_template(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(fixture_path).pages()[0]

    prepared = prepare_pdf_page(page, output_dir=tmp_path, template=service_record_template())

    assert prepared.template_id == "service_record.v1"
    assert prepared.source.document_path == "tests/fixtures/pdf/for testing only.pdf"
    assert prepared.source.page_number == 1
    assert prepared.source.preprocessed_image_path == "for testing only-page-0001.png"
    assert prepared.image_path.exists()
    assert prepared.image_path.suffix.lower() == ".png"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_preprocess.py::test_prepare_pdf_page_renders_png_and_assigns_template
```

Expected: FAIL with `ModuleNotFoundError` because `preprocess.py` and `form_template.py` do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Update `pyproject.toml` and create the new modules:

```toml
dependencies = [
  "openpyxl>=3.1.5",
  "pypdf>=5.6",
  "PyMuPDF>=1.25",
]
```

```python
# src/ocr_from2xlsx/form_template.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FormTemplate:
    template_id: str
    page_size_points: tuple[float, float]
    zones: dict[str, tuple[float, float, float, float]]


def service_record_template() -> FormTemplate:
    return FormTemplate(
        template_id="service_record.v1",
        page_size_points=(595.44, 841.68),
        zones={
            "service_date": (58.0, 92.0, 180.0, 132.0),
            "name": (200.0, 132.0, 360.0, 174.0),
            "medical_record_no": (365.0, 132.0, 515.0, 174.0),
        },
    )
```

```python
# src/ocr_from2xlsx/preprocess.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from ocr_from2xlsx.capture import PdfPage
from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.form_template import FormTemplate

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAGE_SIZE_TOLERANCE_POINTS = 1.0


def _repo_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _validate_page_size(page: PdfPage, template: FormTemplate) -> None:
    template_width, template_height = template.page_size_points
    if (
        abs(page.width_points - template_width) > _PAGE_SIZE_TOLERANCE_POINTS
        or abs(page.height_points - template_height) > _PAGE_SIZE_TOLERANCE_POINTS
    ):
        raise ValueError(
            "PDF page size does not match template "
            f"{template.template_id!r}: expected {template.page_size_points}, "
            f"got {(page.width_points, page.height_points)}"
        )


@dataclass(frozen=True, slots=True)
class PreparedPage:
    image_path: Path
    source: SourceInfo
    template_id: str


def _output_image_path(page: PdfPage, output_dir: Path) -> Path:
    base_name = f"{page.document_path.stem}-page-{page.page_number:04d}.png"
    candidate = output_dir / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = output_dir / f"{page.document_path.stem}-page-{page.page_number:04d}-{suffix}.png"
        if not candidate.exists():
            return candidate
        suffix += 1


def prepare_pdf_page(page: PdfPage, output_dir: Path | str, template: FormTemplate) -> PreparedPage:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _validate_page_size(page, template)
    image_path = _output_image_path(page, output_dir)
    with fitz.open(page.document_path) as document:
        pixmap = document.load_page(page.page_number - 1).get_pixmap(dpi=200)
        pixmap.save(image_path)
    return PreparedPage(
        image_path=image_path,
        template_id=template.template_id,
        source=SourceInfo(
            kind="pdf_page",
            document_path=_repo_relative_path(page.document_path),
            page_number=page.page_number,
            preprocessed_image_path=image_path.name,
            template_id=template.template_id,
        ),
    )
```

Add these focused tests to `tests/test_preprocess.py` after the first red/green test:

```python
def test_prepare_pdf_page_uses_repo_relative_document_path_outside_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(fixture_path).pages()[0]

    monkeypatch.chdir(tmp_path)

    prepared = prepare_pdf_page(page, output_dir=tmp_path / "prepared", template=service_record_template())

    assert prepared.source.document_path == "tests/fixtures/pdf/for testing only.pdf"


def test_prepare_pdf_page_allocates_unique_image_path_for_collisions(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    source_one = tmp_path / "one" / fixture_path.name
    source_two = tmp_path / "two" / fixture_path.name
    source_one.parent.mkdir(parents=True)
    source_two.parent.mkdir(parents=True)
    shutil.copyfile(fixture_path, source_one)
    shutil.copyfile(fixture_path, source_two)

    output_dir = tmp_path / "prepared"
    first_page = PdfDocumentSource(source_one).pages()[0]
    second_page = PdfDocumentSource(source_two).pages()[0]

    first_prepared = prepare_pdf_page(first_page, output_dir=output_dir, template=service_record_template())
    second_prepared = prepare_pdf_page(second_page, output_dir=output_dir, template=service_record_template())

    assert first_prepared.image_path.name == "for testing only-page-0001.png"
    assert second_prepared.image_path != first_prepared.image_path
    assert first_prepared.image_path.exists()
    assert second_prepared.image_path.exists()
    assert second_prepared.source.preprocessed_image_path != first_prepared.source.preprocessed_image_path


def test_prepare_pdf_page_rejects_mismatched_template_size(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    page = PdfDocumentSource(fixture_path).pages()[0]
    template = FormTemplate(template_id="service_record.v1", page_size_points=(620.0, 800.0), zones={})

    with pytest.raises(ValueError, match="template"):
        prepare_pdf_page(page, output_dir=tmp_path, template=template)
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_preprocess.py::test_prepare_pdf_page_renders_png_and_assigns_template
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pyproject.toml src/ocr_from2xlsx/preprocess.py src/ocr_from2xlsx/form_template.py tests/test_preprocess.py
git commit -m "feat: add pdf page preparation"
```

## Task 3: Build the fixture-driven preparation pipeline and gold fixtures

**Files:**
- Create: `src/ocr_from2xlsx/ocr_backend.py`
- Create: `src/ocr_from2xlsx/prepare_records.py`
- Modify: `src/ocr_from2xlsx/normalizer.py`
- Create: `tests/test_prepare_records.py`
- Create: `tests/fixtures/pdf/for testing only.expected.json`
- Create: `tests/fixtures/pdf/for testing only.ocr.json`

- [ ] **Step 1: Write the failing test**

Create `tests/test_prepare_records.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from ocr_from2xlsx.form_template import service_record_template
from ocr_from2xlsx.ocr_backend import FixtureOcrBackend
from ocr_from2xlsx.prepare_records import prepare_records_from_paths


def test_prepare_records_from_pdf_matches_gold_fixture(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    pdf_path = fixture_dir / "for testing only.pdf"
    ocr_path = fixture_dir / "for testing only.ocr.json"
    expected_path = fixture_dir / "for testing only.expected.json"

    batch = prepare_records_from_paths(
        input_paths=[pdf_path],
        output_dir=tmp_path,
        template=service_record_template(),
        backend=FixtureOcrBackend.from_path(ocr_path),
        created_at="2026-05-26T00:00:00+08:00",
    )

    assert batch.to_dict() == json.loads(expected_path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_prepare_records.py::test_prepare_records_from_pdf_matches_gold_fixture
```

Expected: FAIL because the fixture backend and preparation pipeline do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create the fixtures and the orchestration code:

```json
// tests/fixtures/pdf/for testing only.ocr.json
{
  "pages": [
    {
      "document_name": "for testing only.pdf",
      "page_number": 1,
      "record": {
        "record_id": "pdf-0001",
        "service_date": "2026-05-26",
        "identity": "patient",
        "name": "AI test",
        "medical_record_no": "TRAINING-ONLY",
        "gender": "female",
        "patient_fields": {
          "nationality": "local",
          "age_group": "51_60",
          "channel": "internal_referral",
          "disease_status": "treating",
          "source": "outpatient",
          "cancers": ["breast_cancer"],
          "newly_diagnosed_within_year": false
        },
        "services": {
          "consultation": {
            "health_medical": ["screening_prevention"]
          },
          "supplies": [],
          "internal_referrals": [],
          "external_referrals": [],
          "referral_outcomes": []
        },
        "ocr": {
          "confidence": 0.98,
          "raw_text": "AI test, training only",
          "warnings": [],
          "field_confidences": {
            "name": 0.99,
            "service_date": 0.97
          }
        }
      }
    }
  ]
}
```

```json
// tests/fixtures/pdf/for testing only.expected.json
{
  "schema_version": "service_record.v1",
  "source_batch": {
    "created_at": "2026-05-26T00:00:00+08:00",
    "source_type": "prepare_records",
    "template_name": "service_record.v1"
  },
  "records": [
    {
      "record_id": "pdf-0001",
      "service_date": "2026-05-26",
      "identity": "patient",
      "name": "AI test",
      "medical_record_no": "TRAINING-ONLY",
      "gender": "female",
      "source": {
        "kind": "pdf_page",
        "document_path": "tests/fixtures/pdf/for testing only.pdf",
        "page_number": 1,
        "image_path": null,
        "preprocessed_image_path": "for testing only-page-0001.png",
        "capture_time": null,
        "template_id": "service_record.v1"
      },
      "patient_fields": {
        "nationality": "local",
        "age_group": "51_60",
        "channel": "internal_referral",
        "disease_status": "treating",
        "source": "outpatient",
        "cancers": ["breast_cancer"],
        "newly_diagnosed_within_year": false
      },
      "services": {
        "consultation": {
          "health_medical": ["screening_prevention"]
        },
        "supplies": [],
        "internal_referrals": [],
        "external_referrals": [],
        "referral_outcomes": []
      },
      "discharge_followup": null,
      "notes": "",
      "ocr": {
        "backend": "fixture",
        "model": "manual-gold",
        "confidence": 0.98,
        "raw_text": "AI test, training only",
        "warnings": [],
        "field_confidences": {
          "name": 0.99,
          "service_date": 0.97
        }
      },
      "review": {
        "status": "pending",
        "edited_by_user": false
      }
    }
  ]
}
```

```python
# src/ocr_from2xlsx/ocr_backend.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ocr_from2xlsx.preprocess import PreparedPage


class OcrBackend(Protocol):
    def extract(self, page: PreparedPage) -> dict[str, object]:
        ...


@dataclass(slots=True)
class FixtureOcrBackend:
    pages: dict[tuple[str, int], dict[str, object]]

    @classmethod
    def from_path(cls, path: Path | str) -> "FixtureOcrBackend":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        pages = {
            (item["document_name"], item["page_number"]): item["record"]
            for item in payload["pages"]
        }
        return cls(pages=pages)

    def extract(self, page: PreparedPage) -> dict[str, object]:
        key = (Path(page.source.document_path or "").name, page.source.page_number or 0)
        record = dict(self.pages[key])
        ocr = dict(record.get("ocr", {}))
        ocr.setdefault("backend", "fixture")
        ocr.setdefault("model", "manual-gold")
        record["ocr"] = ocr
        return record
```

```python
# src/ocr_from2xlsx/normalizer.py
from __future__ import annotations

from typing import Any

from ocr_from2xlsx.domain import Record


def normalize_raw_record(raw: dict[str, Any]) -> Record:
    return Record.from_dict(raw)
```

```python
# src/ocr_from2xlsx/prepare_records.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ocr_from2xlsx.capture import PdfDocumentSource
from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.form_template import FormTemplate
from ocr_from2xlsx.normalizer import normalize_raw_record
from ocr_from2xlsx.ocr_backend import OcrBackend
from ocr_from2xlsx.preprocess import prepare_pdf_page


def prepare_records_from_paths(
    input_paths: list[Path | str],
    output_dir: Path | str,
    template: FormTemplate,
    backend: OcrBackend,
    created_at: str | None = None,
) -> Batch:
    records = []
    output_dir = Path(output_dir)
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    for input_path in input_paths:
        page = PdfDocumentSource(input_path).pages()[0]
        prepared = prepare_pdf_page(page, output_dir=output_dir, template=template)
        raw_record = backend.extract(prepared)
        raw_record.setdefault("source", {})
        raw_record["source"].update(
            {
                "kind": prepared.source.kind,
                "document_path": prepared.source.document_path,
                "page_number": prepared.source.page_number,
                "preprocessed_image_path": prepared.image_path.name,
                "template_id": prepared.source.template_id,
            }
        )
        records.append(normalize_raw_record(raw_record))
    return Batch(
        source_batch=SourceBatch(
            created_at=created_at,
            source_type="prepare_records",
            template_name=template.template_id,
        ),
        records=records,
    )
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_prepare_records.py::test_prepare_records_from_pdf_matches_gold_fixture
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/ocr_from2xlsx/ocr_backend.py src/ocr_from2xlsx/prepare_records.py src/ocr_from2xlsx/normalizer.py tests/test_prepare_records.py "tests/fixtures/pdf/for testing only.expected.json" "tests/fixtures/pdf/for testing only.ocr.json"
git commit -m "feat: add fixture-driven record preparation"
```

## Task 4: Expose the preparation flow through the CLI

**Files:**
- Modify: `src/ocr_from2xlsx/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_cli.py`:

```python
def test_prepare_records_cli_writes_batch_json_from_pdf_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    output_json = tmp_path / "prepared.json"

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(output_json),
            "--ocr-fixture",
            str(fixture_dir / "for testing only.ocr.json"),
        ]
    )

    assert exit_code == 0
    assert output_json.exists()
    captured = capsys.readouterr()
    assert captured.out == f"{output_json}\n"
```

Add these focused failure-path tests in the same file:

```python
def test_prepare_records_cli_requires_ocr_fixture(capsys) -> None:
    exit_code = main(
        [
            "prepare-records",
            "--input",
            "tests/fixtures/pdf/for testing only.pdf",
            "--output",
            "prepared.json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "the following arguments are required: --ocr-fixture" in captured.err


def test_prepare_records_cli_rejects_unknown_template_id(tmp_path: Path, capsys) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(tmp_path / "prepared.json"),
            "--ocr-fixture",
            str(fixture_dir / "for testing only.ocr.json"),
            "--template-id",
            "unknown-template",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Unsupported template_id" in captured.err


def test_prepare_records_cli_reports_malformed_ocr_fixture_without_traceback(
    tmp_path: Path, capsys
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    bad_fixture = tmp_path / "bad-fixture.json"
    bad_fixture.write_text("{\"pages\": [{}]}", encoding="utf-8")

    exit_code = main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(tmp_path / "prepared.json"),
            "--ocr-fixture",
            str(bad_fixture),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_cli.py::test_prepare_records_cli_writes_batch_json_from_pdf_fixture
```

Expected: FAIL because `prepare-records` is not yet a recognized CLI command.

- [ ] **Step 3: Write the minimal implementation**

Update `src/ocr_from2xlsx/cli.py`:

```python
prepare_parser = subparsers.add_parser(
    "prepare-records",
    help="Prepare normalized JSON records from PDF inputs.",
    description="Prepare normalized JSON records from PDF inputs.",
)
prepare_parser.add_argument("--input", required=True, action="append", help="Input PDF path.")
prepare_parser.add_argument("--output", required=True, help="Output JSON path.")
prepare_parser.add_argument(
    "--ocr-fixture",
    required=True,
    help="Fixture OCR payload path required for the current deterministic implementation.",
)
prepare_parser.add_argument(
    "--template-id",
    default="service_record.v1",
    help="Form template identifier.",
)
```

Add the command handler:

```python
def _resolve_template(template_id: str):
    from ocr_from2xlsx.form_template import service_record_template

    if template_id != "service_record.v1":
        raise ValueError(f"Unsupported template_id: {template_id!r}")
    return service_record_template()


if args.command == "prepare-records":
    from pathlib import Path

    from ocr_from2xlsx.json_io import dump_batch
    from ocr_from2xlsx.ocr_backend import FixtureOcrBackend
    from ocr_from2xlsx.prepare_records import prepare_records_from_paths

    try:
        template = _resolve_template(args.template_id)
        batch = prepare_records_from_paths(
            input_paths=[Path(value) for value in args.input],
            output_dir=Path(args.output).parent,
            template=template,
            backend=FixtureOcrBackend.from_path(Path(args.ocr_fixture)),
        )
        output_path = Path(args.output)
        dump_batch(batch, output_path)
    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(output_path)
    return 0
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_cli.py::test_prepare_records_cli_writes_batch_json_from_pdf_fixture
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/ocr_from2xlsx/cli.py tests/test_cli.py
git commit -m "feat: add prepare-records cli"
```

## Task 5: Add the end-to-end PDF regression path and final verification

**Files:**
- Modify: `tests/test_e2e.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write the failing end-to-end regression test**

Add this test to `tests/test_e2e.py`:

```python
def test_end_to_end_prepare_records_then_import_json(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "pdf"
    prepared_json = tmp_path / "prepared.json"
    template_path = tmp_path / "template.xlsx"
    working_path = tmp_path / "working.xlsx"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    create_workbook_template(template_path)

    assert main(
        [
            "prepare-records",
            "--input",
            str(fixture_dir / "for testing only.pdf"),
            "--output",
            str(prepared_json),
            "--ocr-fixture",
            str(fixture_dir / "for testing only.ocr.json"),
        ]
    ) == 0

    assert main(
        [
            "import-json",
            "--input",
            str(prepared_json),
            "--template",
            str(template_path),
            "--working",
            str(working_path),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    ) == 0

    wb = _load_workbook(working_path)
    try:
        ws = wb[WORKBOOK_SHEET]
        name_col = _column_for_header(ws, BASIC_COLUMN_BY_FIELD["name"])
        assert ws.cell(row=2, column=name_col).value == "AI test"
    finally:
        wb.close()
```

- [ ] **Step 2: Run the regression test to verify it fails**

Run:

```powershell
py -3.12 -W error -m pytest -q tests\test_e2e.py::test_end_to_end_prepare_records_then_import_json
```

Expected: FAIL until the prepared fixture content, CLI path, and workbook import all line up.

- [ ] **Step 3: Make the minimal supporting updates**

Update `README.md` usage so the new front-end stage is explicit:

````markdown
## Usage

1. Prepare normalized JSON from PDF inputs.
2. Validate or review the prepared records.
3. Write confirmed records into the `個案總表` sheet.
4. Save the working XLSX after each confirmed record.
5. Export a final XLSX and import report.
```powershell
ocr-from2xlsx prepare-records --input "tests\fixtures\pdf\for testing only.pdf" --output prepared.json --ocr-fixture "tests\fixtures\pdf\for testing only.ocr.json"
```
````

Update `CHANGELOG.md`:

```markdown
### Added
- 新增 `prepare-records` 前處理流程，將固定版型 PDF 轉成 normalized JSON 後再交給既有匯入流程。
- 新增 `for testing only.pdf` 的人工標註 gold fixture 與端到端 regression 測試。
```

- [ ] **Step 4: Run the full verification suite**

Run:

```powershell
py -3.12 -W error -m pytest -q
py -3.12 build\package.py
py -3.12 -m policy_check --repo .
```

Expected:

- `pytest`: all tests PASS
- `build\package.py`: build succeeds and produces `dist\ocr-from2xlsx.exe`
- `policy_check`: 0 failures

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_e2e.py README.md CHANGELOG.md
git commit -m "test: add pdf preparation regression path"
```

## Self-Review Checklist

- Task 1 covers provenance and OCR metadata requirements.
- Task 2 covers fixed-layout PDF page preparation.
- Task 3 covers deterministic OCR/gold fixture support.
- Task 4 covers the new `prepare-records` CLI boundary.
- Task 5 covers compatibility with the existing import flow plus final verification.

- Placeholder scan complete: no `TODO`, `TBD`, or vague "handle later" steps remain.
- Type consistency check:
  - `SourceInfo.kind`, `document_path`, `page_number`, `preprocessed_image_path`, and `template_id` are introduced before later tasks use them.
  - `FixtureOcrBackend` and `prepare_records_from_paths()` are defined before the CLI task references them.
  - `prepare-records` is the only new public command name used across tasks, docs, and tests.
