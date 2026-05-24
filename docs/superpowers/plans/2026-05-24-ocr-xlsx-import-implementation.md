# OCR XLSX Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Python prototype of a native Windows tool that converts service-record OCR JSON into confirmed rows in the workbook `個案總表` sheet while preserving the original XLSX layout and styles.

**Architecture:** Implement Rust-friendly Python modules with clean JSON/file-path boundaries: domain schema, sample-data generator, validator, workbook writer, session controller, capture/OCR adapters, CLI, and Tkinter UI. The first executable flow uses fake/imported OCR results and image/JSON simulation while keeping the capture adapter interface ready for UVC cameras.

**Tech Stack:** Python 3.12+, Tkinter, openpyxl, pytest, PyInstaller, optional OpenCV camera adapter isolated behind an adapter interface.

---

## Spec Reference

Read and keep aligned with `docs/superpowers/specs/2026-05-24-ocr-xlsx-import-design.md`.

Important constraints:

- Do not open a localhost server or any listening port.
- Never overwrite the source template XLSX.
- Only write values into `個案總表`; preserve sheet names, styles, formulas, column widths, row heights, and merged ranges.
- Save the working XLSX after each confirmed record.
- Treat changing to the next scan as confirmation only when the current record has no blocking errors and the user is not editing.
- Generate about 100 test JSON records before validating the workbook flow.

## File Structure

Create this structure:

```text
src/ocr_from2xlsx/
  __init__.py                  Package version.
  __main__.py                  `python -m ocr_from2xlsx` entrypoint.
  app.py                       Tkinter desktop UI; no network server.
  capture.py                   Capture source interfaces: JSON, image folder, UVC adapter shell.
  cli.py                       CLI commands for sample generation, validation, and workbook import.
  constants.py                 Stable code lists and workbook column mapping.
  domain.py                    Dataclasses, enum-like constants, duplicate key, month calculation.
  json_io.py                   Batch JSON load/dump with schema version checks.
  normalizer.py                Converts raw/fake OCR payloads into normalized records.
  report.py                    Import report dataclasses and JSON/CSV writers.
  sample_data.py               Deterministic 100-record sample generator.
  session.py                   Review/write workflow state machine.
  validation.py                Blocking errors, warnings, duplicate detection.
  workbook.py                  XLSX copy/write/save/finalize logic.
tests/
  fixtures.py                  Test workbook factory and shared helpers.
  test_json_io.py
  test_sample_data.py
  test_validation.py
  test_workbook.py
  test_session.py
  test_cli.py
scripts/
  build-windows.ps1            PyInstaller build command.
```

Keep modules small and independent. `domain.py`, `json_io.py`, `validation.py`, `workbook.py`, and `session.py` must not import Tkinter.

## Task 1: Python Package Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/ocr_from2xlsx/__init__.py`
- Create: `src/ocr_from2xlsx/__main__.py`
- Create: `src/ocr_from2xlsx/cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `.paul-project.yml`
- Test: shell commands

- [ ] **Step 1: Create package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ocr-from2xlsx"
version = "0.0.0"
description = "Portable OCR-to-XLSX service-record import prototype"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "openpyxl>=3.1.5",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pyinstaller>=6.8",
]
camera = [
  "opencv-python>=4.10",
]

[project.scripts]
ocr-from2xlsx = "ocr_from2xlsx.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create initial package files**

Create `src/ocr_from2xlsx/__init__.py`:

```python
"""OCR-to-XLSX service-record import prototype."""

__version__ = "0.0.0"
```

Create `src/ocr_from2xlsx/__main__.py`:

```python
from ocr_from2xlsx.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

Create `src/ocr_from2xlsx/cli.py`:

```python
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr-from2xlsx",
        description="Import normalized service-record JSON into the monthly report XLSX.",
    )
    parser.add_argument("--version", action="store_true", help="Print package version and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from ocr_from2xlsx import __version__

        print(__version__)
        return 0
    parser.print_help()
    return 0
```

- [ ] **Step 3: Update policy metadata for CLI help sync**

Replace `.paul-project.yml` with:

```yaml
policy_profile: flat
policy_version: 1.0.0
code_paths:
  - ".paul-project.yml"
  - "VERSION"
  - "**/*.py"
  - "**/*.rs"
  - "**/*.sh"
  - "src/**"
  - "scripts/**"
  - "pyproject.toml"
  - "Cargo.toml"
  - "Cargo.lock"
  - ".github/**"
cli:
  - command: "ocr-from2xlsx"
    help_args: ["--help"]
    reflected_in: "README.md"
    marker: "ocr-from2xlsx-help"
```

- [ ] **Step 4: Update README CLI section**

Replace `README.md` with:

````markdown
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

<!-- ocr-from2xlsx-help:start -->
```text
usage: ocr-from2xlsx [-h] [--version]

Import normalized service-record JSON into the monthly report XLSX.

options:
  -h, --help  show this help message and exit
  --version   Print package version and exit.
```
<!-- ocr-from2xlsx-help:end -->

## Version

`VERSION` is the single source of truth for repository versioning. Update it together with `CHANGELOG.md` according to the selected `policy_profile`.
````

- [ ] **Step 5: Update CHANGELOG**

Replace `CHANGELOG.md` with:

```markdown
# Changelog

本專案所有重大變更都會記錄在此檔案。

格式基於 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-TW/1.1.0/)，
本專案遵循 hamanpaul project policy v1.0.0。

## [Unreleased]

### Added
- 以 `hamanpaul/new-project-template` 建立專案骨架。
- 導入 `hamanpaul/paulsha-conventions` policy metadata、agent convention files 與 Policy Check workflow。
- 新增 OCR-to-XLSX 服務紀錄匯入工具設計規格。
- 新增 Python package scaffold 與 CLI entrypoint。
```

- [ ] **Step 6: Install dependencies**

Run:

```powershell
python -m pip install -e ".[dev]"
```

Expected: command exits 0 and installs `ocr-from2xlsx`.

- [ ] **Step 7: Verify CLI help**

Run:

```powershell
ocr-from2xlsx --help
python -m ocr_from2xlsx --version
```

Expected:

```text
usage: ocr-from2xlsx [-h] [--version]
```

and:

```text
0.0.0
```

- [ ] **Step 8: Run tests baseline**

Run:

```powershell
pytest -q
```

Expected: `no tests ran` or `0 passed`; no import error.

- [ ] **Step 9: Commit**

```powershell
git add pyproject.toml src README.md CHANGELOG.md .paul-project.yml
git commit -m "feat: scaffold Python package"
```

## Task 2: Domain Schema and JSON I/O

**Files:**
- Create: `src/ocr_from2xlsx/constants.py`
- Create: `src/ocr_from2xlsx/domain.py`
- Create: `src/ocr_from2xlsx/json_io.py`
- Create: `tests/test_json_io.py`

- [ ] **Step 1: Write failing JSON round-trip tests**

Create `tests/test_json_io.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx.domain import (
    Batch,
    OcrInfo,
    PatientFields,
    Record,
    ReviewInfo,
    Services,
    SourceBatch,
)
from ocr_from2xlsx.json_io import dump_batch, load_batch


def make_record(record_id: str = "scan-0001") -> Record:
    return Record(
        record_id=record_id,
        service_date="2026-03-15",
        identity="patient",
        name="王小明",
        medical_record_no="A123456",
        gender="female",
        patient_fields=PatientFields(
            nationality="local",
            age_group="51_60",
            channel="internal_referral",
            disease_status="treating",
            source="outpatient",
            cancers=["breast_cancer"],
            newly_diagnosed_within_year=True,
        ),
        services=Services(
            consultation={"health_medical": ["screening_prevention"]},
            supplies=["wig_hat"],
            internal_referrals=[],
            external_referrals=[],
            referral_outcomes=[],
        ),
        ocr=OcrInfo(confidence=0.93, raw_text="raw", warnings=[]),
        review=ReviewInfo(status="pending", edited_by_user=False),
    )


def test_batch_json_round_trip(tmp_path: Path) -> None:
    batch = Batch(
        source_batch=SourceBatch(
            created_at="2026-05-24T15:30:00+08:00",
            source_type="json_import",
            template_name="template.xlsx",
        ),
        records=[make_record()],
    )
    path = tmp_path / "records.json"

    dump_batch(batch, path)
    loaded = load_batch(path)

    assert loaded.schema_version == "service_record.v1"
    assert loaded.records[0].name == "王小明"
    assert loaded.records[0].patient_fields.cancers == ["breast_cancer"]
    assert loaded.records[0].duplicate_key() == (
        "2026-03-15",
        "王小明",
        "A123456",
        "health_medical:screening_prevention|supplies:wig_hat",
    )


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    path.write_text('{"schema_version":"wrong","source_batch":{},"records":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported schema_version"):
        load_batch(path)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_json_io.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing symbols.

- [ ] **Step 3: Create constants**

Create `src/ocr_from2xlsx/constants.py`:

```python
SCHEMA_VERSION = "service_record.v1"

IDENTITIES = {"patient", "family_caregiver", "public_other"}
GENDERS = {"female", "male", "other"}
REVIEW_STATUSES = {"pending", "confirmed", "skipped", "forced", "written"}
SOURCE_TYPES = {"camera", "image_folder", "json_import", "manual"}

PATIENT_ENUMS = {
    "nationality": {"local", "foreign"},
    "age_group": {"20_under", "21_30", "31_40", "41_50", "51_60", "61_70", "71_over"},
    "channel": {
        "self_known",
        "introduced",
        "active_followup",
        "internal_referral",
        "external_referral",
        "activity",
        "other",
    },
    "disease_status": {
        "undiagnosed",
        "diagnosed_not_treated",
        "diagnosed_refused",
        "treating",
        "recurrence_treating",
        "followup",
        "palliative",
    },
    "source": {"outpatient", "inpatient", "emergency"},
}

SERVICE_CATEGORIES = {
    "health_medical": {
        "screening_prevention",
        "disease_treatment_knowledge",
        "doctor_patient_communication",
        "healthy_lifestyle",
        "second_opinion",
        "transfer_registration",
        "palliative_patient_rights",
        "other",
    },
    "symptom_side_effect": {
        "treatment_side_effect",
        "wound_care",
        "pain_management",
        "fatigue_strength",
        "integrated_care",
        "sexuality_fertility",
        "other",
    },
    "nutrition_diet": {"diet_conditioning", "nutrition_products", "health_food", "other"},
    "psychosocial_emotion": {
        "emotional_support",
        "disease_adaptation",
        "family_communication",
        "loss_grief",
        "spiritual_care",
        "other",
    },
    "financial_social": {
        "financial_welfare",
        "nutrition_subsidy",
        "transportation_subsidy",
        "housing_subsidy",
        "insurance",
        "school_work",
        "rehab_supplies_aids",
        "other",
    },
    "care_support": {
        "peer_experience",
        "long_term_care",
        "caregiver_support",
        "relationship_social",
        "discharge_planning",
        "other",
    },
}

SUPPLY_CODES = {"wig_hat", "other_care_supplies", "nutrition_products", "other_equipment"}
RESOURCE_CODES = {
    "wig_hat",
    "other_care_supplies",
    "social_welfare",
    "peer_volunteer_group",
    "psychology",
    "nutrition",
    "long_term_care",
    "rehabilitation",
    "care_information",
    "other_activity",
}
OUTCOME_CODES = {
    "received_wig_hat",
    "received_other_supplies",
    "received_financial_aid",
    "received_service_help",
}
```

- [ ] **Step 4: Create domain dataclasses**

Create `src/ocr_from2xlsx/domain.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from ocr_from2xlsx.constants import SCHEMA_VERSION


def _none_if_empty(value: Any) -> Any:
    return None if value == "" else value


@dataclass(slots=True)
class SourceInfo:
    image_path: str | None = None
    capture_time: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceInfo":
        data = data or {}
        return cls(image_path=_none_if_empty(data.get("image_path")), capture_time=_none_if_empty(data.get("capture_time")))


@dataclass(slots=True)
class PatientFields:
    nationality: str | None = None
    age_group: str | None = None
    channel: str | None = None
    disease_status: str | None = None
    source: str | None = None
    cancers: list[str] = field(default_factory=list)
    newly_diagnosed_within_year: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PatientFields":
        data = data or {}
        return cls(
            nationality=_none_if_empty(data.get("nationality")),
            age_group=_none_if_empty(data.get("age_group")),
            channel=_none_if_empty(data.get("channel")),
            disease_status=_none_if_empty(data.get("disease_status")),
            source=_none_if_empty(data.get("source")),
            cancers=list(data.get("cancers") or []),
            newly_diagnosed_within_year=data.get("newly_diagnosed_within_year"),
        )


@dataclass(slots=True)
class Services:
    consultation: dict[str, list[str]] = field(default_factory=dict)
    supplies: list[str] = field(default_factory=list)
    internal_referrals: list[str] = field(default_factory=list)
    external_referrals: list[str] = field(default_factory=list)
    referral_outcomes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Services":
        data = data or {}
        consultation = {
            str(category): list(values or [])
            for category, values in (data.get("consultation") or {}).items()
        }
        return cls(
            consultation=consultation,
            supplies=list(data.get("supplies") or []),
            internal_referrals=list(data.get("internal_referrals") or []),
            external_referrals=list(data.get("external_referrals") or []),
            referral_outcomes=list(data.get("referral_outcomes") or []),
        )

    def summary(self) -> str:
        parts: list[str] = []
        for category in sorted(self.consultation):
            for code in sorted(self.consultation[category]):
                parts.append(f"{category}:{code}")
        for name, values in [
            ("supplies", self.supplies),
            ("internal", self.internal_referrals),
            ("external", self.external_referrals),
            ("outcomes", self.referral_outcomes),
        ]:
            for code in sorted(values):
                parts.append(f"{name}:{code}")
        return "|".join(parts)


@dataclass(slots=True)
class OcrInfo:
    confidence: float | None = None
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OcrInfo":
        data = data or {}
        return cls(
            confidence=data.get("confidence"),
            raw_text=str(data.get("raw_text") or ""),
            warnings=list(data.get("warnings") or []),
        )


@dataclass(slots=True)
class ReviewInfo:
    status: str = "pending"
    edited_by_user: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReviewInfo":
        data = data or {}
        return cls(status=str(data.get("status") or "pending"), edited_by_user=bool(data.get("edited_by_user", False)))


@dataclass(slots=True)
class Record:
    record_id: str
    service_date: str
    identity: str
    name: str
    medical_record_no: str
    gender: str
    source: SourceInfo = field(default_factory=SourceInfo)
    birthdate: str | None = None
    patient_fields: PatientFields = field(default_factory=PatientFields)
    services: Services = field(default_factory=Services)
    discharge_followup: bool | None = None
    notes: str = ""
    ocr: OcrInfo = field(default_factory=OcrInfo)
    review: ReviewInfo = field(default_factory=ReviewInfo)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        return cls(
            record_id=str(data["record_id"]),
            source=SourceInfo.from_dict(data.get("source")),
            service_date=str(data.get("service_date") or ""),
            identity=str(data.get("identity") or ""),
            name=str(data.get("name") or ""),
            medical_record_no=str(data.get("medical_record_no") or ""),
            birthdate=_none_if_empty(data.get("birthdate")),
            gender=str(data.get("gender") or ""),
            patient_fields=PatientFields.from_dict(data.get("patient_fields")),
            services=Services.from_dict(data.get("services")),
            discharge_followup=data.get("discharge_followup"),
            notes=str(data.get("notes") or ""),
            ocr=OcrInfo.from_dict(data.get("ocr")),
            review=ReviewInfo.from_dict(data.get("review")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def service_month_label(self) -> str:
        parsed = date.fromisoformat(self.service_date)
        return f"{parsed.month}月"

    def duplicate_key(self) -> tuple[str, str, str, str]:
        return (self.service_date, self.name.strip(), self.medical_record_no.strip(), self.services.summary())


@dataclass(slots=True)
class SourceBatch:
    created_at: str
    source_type: str
    template_name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceBatch":
        return cls(
            created_at=str(data.get("created_at") or ""),
            source_type=str(data.get("source_type") or ""),
            template_name=str(data.get("template_name") or ""),
        )


@dataclass(slots=True)
class Batch:
    source_batch: SourceBatch
    records: list[Record]
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Batch":
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            source_batch=SourceBatch.from_dict(data.get("source_batch") or {}),
            records=[Record.from_dict(item) for item in data.get("records") or []],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 5: Create JSON I/O**

Create `src/ocr_from2xlsx/json_io.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from ocr_from2xlsx.constants import SCHEMA_VERSION
from ocr_from2xlsx.domain import Batch


def load_batch(path: Path | str) -> Batch:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {data.get('schema_version')!r}")
    return Batch.from_dict(data)


def dump_batch(batch: Batch, path: Path | str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(batch.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/test_json_io.py -q
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```powershell
git add src/ocr_from2xlsx/constants.py src/ocr_from2xlsx/domain.py src/ocr_from2xlsx/json_io.py tests/test_json_io.py
git commit -m "feat: add normalized service record schema"
```

## Task 3: Deterministic Sample JSON Generator

**Files:**
- Create: `src/ocr_from2xlsx/sample_data.py`
- Create: `tests/test_sample_data.py`
- Modify: `src/ocr_from2xlsx/cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing tests for sample data**

Create `tests/test_sample_data.py`:

```python
from __future__ import annotations

from ocr_from2xlsx.sample_data import generate_sample_batch


def test_generates_100_records_with_required_mix() -> None:
    batch = generate_sample_batch(count=100, template_name="template.xlsx")

    assert len(batch.records) == 100
    assert {record.identity for record in batch.records} == {"patient", "family_caregiver", "public_other"}
    assert {record.gender for record in batch.records} == {"female", "male", "other"}
    assert {record.service_date[5:7] for record in batch.records} == {
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
        "12",
    }


def test_sample_includes_duplicates_and_invalid_cases() -> None:
    batch = generate_sample_batch(count=100, template_name="template.xlsx")
    keys = [record.duplicate_key() for record in batch.records]
    missing_dates = [record for record in batch.records if not record.service_date]
    low_confidence = [record for record in batch.records if record.ocr.confidence is not None and record.ocr.confidence < 0.7]

    assert len(set(keys)) < len(keys)
    assert missing_dates
    assert low_confidence
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_sample_data.py -q
```

Expected: FAIL because `ocr_from2xlsx.sample_data` does not exist.

- [ ] **Step 3: Implement sample generator**

Create `src/ocr_from2xlsx/sample_data.py`:

```python
from __future__ import annotations

from datetime import datetime

from ocr_from2xlsx.domain import (
    Batch,
    OcrInfo,
    PatientFields,
    Record,
    ReviewInfo,
    Services,
    SourceBatch,
    SourceInfo,
)

NAMES = ["王小明", "陳美玲", "林志偉", "張雅婷", "李國華", "黃淑芬", "劉冠廷", "蔡佳蓉"]
GENDERS = ["female", "male", "other"]
IDENTITIES = ["patient", "family_caregiver", "public_other"]
CANCERS = ["breast_cancer", "lung_cancer", "colorectal_cancer", "liver_cancer", "other"]
AGE_GROUPS = ["20_under", "21_30", "31_40", "41_50", "51_60", "61_70", "71_over"]
CHANNELS = ["self_known", "introduced", "active_followup", "internal_referral", "external_referral", "activity", "other"]
DISEASE_STATUSES = ["undiagnosed", "diagnosed_not_treated", "diagnosed_refused", "treating", "recurrence_treating", "followup", "palliative"]
SOURCES = ["outpatient", "inpatient", "emergency"]


def _patient_fields(index: int, identity: str) -> PatientFields:
    if identity != "patient":
        return PatientFields()
    return PatientFields(
        nationality="local" if index % 5 else "foreign",
        age_group=AGE_GROUPS[index % len(AGE_GROUPS)],
        channel=CHANNELS[index % len(CHANNELS)],
        disease_status=DISEASE_STATUSES[index % len(DISEASE_STATUSES)],
        source=SOURCES[index % len(SOURCES)],
        cancers=[CANCERS[index % len(CANCERS)]],
        newly_diagnosed_within_year=index % 4 == 0,
    )


def _services(index: int) -> Services:
    consultation = {
        "health_medical": ["screening_prevention"] if index % 2 == 0 else ["disease_treatment_knowledge"],
        "symptom_side_effect": ["pain_management"] if index % 3 == 0 else [],
        "nutrition_diet": ["diet_conditioning"] if index % 5 == 0 else [],
        "psychosocial_emotion": ["emotional_support"] if index % 7 == 0 else [],
        "financial_social": ["financial_welfare"] if index % 11 == 0 else [],
        "care_support": ["caregiver_support"] if index % 13 == 0 else [],
    }
    return Services(
        consultation=consultation,
        supplies=["wig_hat"] if index % 6 == 0 else [],
        internal_referrals=["social_welfare"] if index % 8 == 0 else [],
        external_referrals=["care_information"] if index % 9 == 0 else [],
        referral_outcomes=["received_service_help"] if index % 10 == 0 else [],
    )


def _record(index: int) -> Record:
    month = index % 12 + 1
    identity = IDENTITIES[index % len(IDENTITIES)]
    name = NAMES[index % len(NAMES)]
    service_date = f"2026-{month:02d}-{index % 28 + 1:02d}"
    if index == 94:
        service_date = ""
    return Record(
        record_id=f"scan-{index + 1:04d}",
        source=SourceInfo(image_path=f"samples/scan-{index + 1:04d}.png", capture_time=None),
        service_date=service_date,
        identity=identity,
        name=name,
        medical_record_no=f"MR{100000 + index:06d}",
        gender=GENDERS[index % len(GENDERS)],
        patient_fields=_patient_fields(index, identity),
        services=_services(index),
        ocr=OcrInfo(confidence=0.55 if index in {95, 96} else 0.92, raw_text=f"fake raw text {index + 1}", warnings=[]),
        review=ReviewInfo(status="pending", edited_by_user=False),
    )


def generate_sample_batch(count: int = 100, template_name: str = "template.xlsx") -> Batch:
    records = [_record(index) for index in range(count)]
    if count >= 4:
        records[-1] = _record(0)
        records[-1].record_id = f"scan-{count:04d}"
    return Batch(
        source_batch=SourceBatch(
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            source_type="manual",
            template_name=template_name,
        ),
        records=records,
    )
```

- [ ] **Step 4: Add CLI subcommand for sample generation**

Replace `src/ocr_from2xlsx/cli.py` with:

```python
from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr-from2xlsx",
        description="Import normalized service-record JSON into the monthly report XLSX.",
    )
    parser.add_argument("--version", action="store_true", help="Print package version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    sample = subparsers.add_parser("sample-json", help="Generate deterministic sample service-record JSON.")
    sample.add_argument("--output", required=True, help="Output JSON path.")
    sample.add_argument("--count", type=int, default=100, help="Number of records to generate.")
    sample.add_argument("--template-name", default="template.xlsx", help="Template name stored in source metadata.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from ocr_from2xlsx import __version__

        print(__version__)
        return 0
    if args.command == "sample-json":
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.sample_data import generate_sample_batch

        dump_batch(generate_sample_batch(count=args.count, template_name=args.template_name), Path(args.output))
        print(args.output)
        return 0
    parser.print_help()
    return 0
```

- [ ] **Step 5: Update README help block**

Run:

```powershell
ocr-from2xlsx --help
ocr-from2xlsx sample-json --help
```

Replace the README help block between `<!-- ocr-from2xlsx-help:start -->` and `<!-- ocr-from2xlsx-help:end -->` with the actual `ocr-from2xlsx --help` output. Keep the marker comments.

- [ ] **Step 6: Update CHANGELOG**

Add under `### Added`:

```markdown
- 新增約 100 筆測試 JSON 產生器與 CLI subcommand。
```

- [ ] **Step 7: Run tests and generate sample**

Run:

```powershell
pytest tests/test_sample_data.py tests/test_json_io.py -q
ocr-from2xlsx sample-json --output output\sample-records.json --count 100
```

Expected: tests pass and `output\sample-records.json` exists.

- [ ] **Step 8: Commit**

```powershell
git add src/ocr_from2xlsx/sample_data.py src/ocr_from2xlsx/cli.py tests/test_sample_data.py README.md CHANGELOG.md
git commit -m "feat: generate sample service record JSON"
```

## Task 4: Validation and Duplicate Detection

**Files:**
- Create: `src/ocr_from2xlsx/validation.py`
- Create: `tests/test_validation.py`
- Modify: `src/ocr_from2xlsx/cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing validation tests**

Create `tests/test_validation.py`:

```python
from __future__ import annotations

from tests.test_json_io import make_record

from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.validation import validate_batch, validate_record


def test_patient_requires_patient_fields() -> None:
    record = make_record()
    record.patient_fields.age_group = None

    result = validate_record(record)

    assert "patient.age_group.required" in result.blockers


def test_non_patient_does_not_require_patient_fields() -> None:
    record = make_record()
    record.identity = "family_caregiver"
    record.patient_fields.age_group = None
    record.patient_fields.cancers = []

    result = validate_record(record)

    assert result.blockers == []


def test_duplicate_in_batch_blocks_second_record() -> None:
    first = make_record("scan-0001")
    second = make_record("scan-0002")
    batch = Batch(
        source_batch=SourceBatch(created_at="2026-05-24T00:00:00+08:00", source_type="manual", template_name="template.xlsx"),
        records=[first, second],
    )

    results = validate_batch(batch)

    assert results["scan-0001"].blockers == []
    assert "duplicate.in_batch" in results["scan-0002"].blockers


def test_low_confidence_is_warning_not_blocker() -> None:
    record = make_record()
    record.ocr.confidence = 0.55

    result = validate_record(record)

    assert result.blockers == []
    assert "ocr.low_confidence" in result.warnings
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_validation.py -q
```

Expected: FAIL because `validation.py` does not exist.

- [ ] **Step 3: Implement validation**

Create `src/ocr_from2xlsx/validation.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ocr_from2xlsx.constants import (
    GENDERS,
    IDENTITIES,
    OUTCOME_CODES,
    PATIENT_ENUMS,
    RESOURCE_CODES,
    REVIEW_STATUSES,
    SERVICE_CATEGORIES,
    SUPPLY_CODES,
)
from ocr_from2xlsx.domain import Batch, Record


@dataclass(slots=True)
class ValidationResult:
    record_id: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def can_auto_confirm(self) -> bool:
        return not self.blockers


def validate_record(record: Record, existing_duplicate_keys: set[tuple[str, str, str, str]] | None = None) -> ValidationResult:
    result = ValidationResult(record_id=record.record_id)

    try:
        date.fromisoformat(record.service_date)
    except ValueError:
        result.blockers.append("service_date.invalid")

    if record.identity not in IDENTITIES:
        result.blockers.append("identity.invalid")
    if record.gender not in GENDERS:
        result.blockers.append("gender.invalid")
    if record.review.status not in REVIEW_STATUSES:
        result.blockers.append("review.status.invalid")

    _validate_services(record, result)

    if record.identity == "patient":
        _validate_patient_fields(record, result)
    elif _has_patient_field_values(record):
        result.warnings.append("non_patient.patient_fields_present")

    if record.ocr.confidence is not None and record.ocr.confidence < 0.7:
        result.warnings.append("ocr.low_confidence")

    if existing_duplicate_keys and record.duplicate_key() in existing_duplicate_keys:
        result.blockers.append("duplicate.existing_workbook")

    return result


def validate_batch(batch: Batch, existing_duplicate_keys: set[tuple[str, str, str, str]] | None = None) -> dict[str, ValidationResult]:
    seen: set[tuple[str, str, str, str]] = set()
    results: dict[str, ValidationResult] = {}
    existing_duplicate_keys = existing_duplicate_keys or set()
    for record in batch.records:
        result = validate_record(record, existing_duplicate_keys)
        key = record.duplicate_key()
        if key in seen:
            result.blockers.append("duplicate.in_batch")
        seen.add(key)
        results[record.record_id] = result
    return results


def _validate_patient_fields(record: Record, result: ValidationResult) -> None:
    fields = record.patient_fields
    required = {
        "nationality": fields.nationality,
        "age_group": fields.age_group,
        "channel": fields.channel,
        "disease_status": fields.disease_status,
        "source": fields.source,
    }
    for name, value in required.items():
        if value is None:
            result.blockers.append(f"patient.{name}.required")
        elif value not in PATIENT_ENUMS[name]:
            result.blockers.append(f"patient.{name}.invalid")
    if not fields.cancers:
        result.blockers.append("patient.cancers.required")


def _has_patient_field_values(record: Record) -> bool:
    fields = record.patient_fields
    return any(
        [
            fields.nationality,
            fields.age_group,
            fields.channel,
            fields.disease_status,
            fields.source,
            fields.cancers,
            fields.newly_diagnosed_within_year is not None,
        ]
    )


def _validate_services(record: Record, result: ValidationResult) -> None:
    for category, codes in record.services.consultation.items():
        if category not in SERVICE_CATEGORIES:
            result.blockers.append(f"service.consultation.{category}.unknown")
            continue
        for code in codes:
            if code not in SERVICE_CATEGORIES[category]:
                result.blockers.append(f"service.consultation.{category}.{code}.invalid")
    for code in record.services.supplies:
        if code not in SUPPLY_CODES:
            result.blockers.append(f"service.supplies.{code}.invalid")
    for code in record.services.internal_referrals:
        if code not in RESOURCE_CODES:
            result.blockers.append(f"service.internal_referrals.{code}.invalid")
    for code in record.services.external_referrals:
        if code not in RESOURCE_CODES:
            result.blockers.append(f"service.external_referrals.{code}.invalid")
    for code in record.services.referral_outcomes:
        if code not in OUTCOME_CODES:
            result.blockers.append(f"service.referral_outcomes.{code}.invalid")
```

- [ ] **Step 4: Add CLI validation command**

Update `src/ocr_from2xlsx/cli.py` by adding this subparser in `build_parser()`:

```python
    validate = subparsers.add_parser("validate-json", help="Validate normalized service-record JSON.")
    validate.add_argument("--input", required=True, help="Input JSON path.")
```

Add this branch before `parser.print_help()` in `main()`:

```python
    if args.command == "validate-json":
        from ocr_from2xlsx.json_io import load_batch
        from ocr_from2xlsx.validation import validate_batch

        batch = load_batch(Path(args.input))
        results = validate_batch(batch)
        blocker_count = sum(len(result.blockers) for result in results.values())
        warning_count = sum(len(result.warnings) for result in results.values())
        print(f"records={len(batch.records)} blockers={blocker_count} warnings={warning_count}")
        return 1 if blocker_count else 0
```

- [ ] **Step 5: Update README help block and changelog**

Run:

```powershell
ocr-from2xlsx --help
```

Replace the README help block with the updated output. Add under `CHANGELOG.md` `### Added`:

```markdown
- 新增 JSON 驗證與重複單判斷。
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/test_validation.py tests/test_sample_data.py tests/test_json_io.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/ocr_from2xlsx/validation.py src/ocr_from2xlsx/cli.py tests/test_validation.py README.md CHANGELOG.md
git commit -m "feat: validate service record batches"
```

## Task 5: Workbook Writer and Format Preservation Tests

**Files:**
- Create: `src/ocr_from2xlsx/workbook.py`
- Create: `tests/fixtures.py`
- Create: `tests/test_workbook.py`
- Modify: `src/ocr_from2xlsx/constants.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add workbook mapping constants**

Append to `src/ocr_from2xlsx/constants.py`:

```python
WORKBOOK_SHEET = "個案總表"

BASIC_COLUMN_BY_FIELD = {
    "service_month": "服務月份",
    "service_date": "服務日期",
    "identity": "身分",
    "name": "姓名",
    "medical_record_no": "ID",
    "birthdate": "生日",
    "gender": "性別",
    "nationality": "國籍\n(病人才填)",
    "age_group": "年齡\n(病人才填)",
    "channel": "管道\n(病人才填)",
    "disease_status": "疾病狀態\n(病人才填)",
    "source": "來源\n(病人才填)",
    "newly_diagnosed_within_year": "一年內新診斷(病人才填)",
    "discharge_followup": "出院後關懷",
}

IDENTITY_LABELS = {
    "patient": "病人",
    "family_caregiver": "親友及照顧者",
    "public_other": "一般民眾及其他",
}

GENDER_LABELS = {"female": "女性", "male": "男性", "other": "其他"}
NATIONALITY_LABELS = {"local": "本國籍", "foreign": "外國籍"}
AGE_GROUP_LABELS = {
    "20_under": "20歲以下",
    "21_30": "21-30歲",
    "31_40": "31-40歲",
    "41_50": "41-50歲",
    "51_60": "51-60歲",
    "61_70": "61-70歲",
    "71_over": "71歲以上",
}
CHANNEL_LABELS = {
    "self_known": "1.自行得知",
    "introduced": "2.病友或家屬介紹",
    "active_followup": "3.主動關懷或追蹤",
    "internal_referral": "4.院內轉介",
    "external_referral": "5.院外轉介",
    "activity": "6.活動課程接觸",
    "other": "7.其他",
}
DISEASE_STATUS_LABELS = {
    "undiagnosed": "1.尚未確診",
    "diagnosed_not_treated": "2.確診，尚未治療",
    "diagnosed_refused": "3.確診，拒絕治療",
    "treating": "4.治療中",
    "recurrence_treating": "5.復發治療中",
    "followup": "6.追蹤期",
    "palliative": "7.緩和治療",
}
SOURCE_LABELS = {"outpatient": "1.門診", "inpatient": "2.住院", "emergency": "3.急診"}
CANCER_LABELS = {
    "brain_cancer": "1.腦癌",
    "nasopharyngeal_cancer": "2.鼻咽癌",
    "oral_cancer": "3.口腔癌",
    "hypopharyngeal_cancer": "4.下咽癌",
    "laryngeal_cancer": "5.喉癌",
    "thyroid_cancer": "6.甲狀腺癌",
    "esophageal_cancer": "7.食道癌",
    "breast_cancer": "8.乳癌",
    "lung_cancer": "9.肺癌",
    "liver_cancer": "10.肝癌",
    "colorectal_cancer": "11.結直腸癌",
    "stomach_cancer": "12.胃癌",
    "pancreatic_cancer": "13.胰臟癌",
    "kidney_cancer": "14.腎臟癌",
    "bladder_cancer": "15.膀胱癌",
    "ovarian_cancer": "16.卵巢癌",
    "endometrial_cancer": "17.子宮內膜癌",
    "cervical_cancer": "18.子宮頸癌",
    "prostate_cancer": "19.攝護腺癌",
    "lymphoma": "20.淋巴癌",
    "leukemia": "21.白血病",
    "skin_cancer": "22.皮膚癌",
    "multiple_myeloma": "23.多發性骨髓瘤",
    "sarcoma": "24.惡性肉瘤",
    "other": "25.其他",
}
```

- [ ] **Step 2: Write workbook tests**

Create `tests/fixtures.py`:

```python
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import PatternFill

HEADERS = [
    "序",
    "服務月份",
    "身分",
    "服務日期",
    "姓名",
    "ID",
    "生日",
    "性別",
    "是否曾經今年服務過",
    "國籍\n(病人才填)",
    "年齡\n(病人才填)",
    "管道\n(病人才填)",
    "疾病狀態\n(病人才填)",
    "來源\n(病人才填)",
    "癌別1\n(病人才填)",
    "癌別2\n(病人才填)",
    "癌別3\n(病人才填)",
    "一年內新診斷(病人才填)",
    "諮詢-健康與醫療系統1",
    "提供實體用品及設備1",
    "轉介或連結院內資源3",
    "轉介或連結院外資源9",
    "轉介或連結資源成果4",
]


def create_workbook_template(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "個案總表"
    wb.create_sheet("一月")
    for column, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=column, value=header)
        cell.fill = PatternFill("solid", fgColor="FFD966")
    for row in range(2, 7):
        ws.cell(row=row, column=1, value=row - 1)
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 12
    wb["一月"]["A1"] = "=SUM(個案總表!A2:A6)"
    wb.save(path)
```

Create `tests/test_workbook.py`:

```python
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from ocr_from2xlsx.workbook import WorkbookWriter
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


def test_writer_copies_template_and_writes_record(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)

    writer = WorkbookWriter.create_from_template(template, working)
    row_number = writer.write_record(make_record())
    writer.save()

    wb = load_workbook(working)
    ws = wb["個案總表"]
    assert row_number == 2
    assert ws["B2"].value == "3月"
    assert ws["C2"].value == "病人"
    assert ws["D2"].value == "2026-03-15"
    assert ws["E2"].value == "王小明"
    assert ws["F2"].value == "A123456"
    assert ws["G2"].value is None
    assert ws["H2"].value == "女性"
    assert ws["I2"].value is None
    assert ws["J2"].value == "本國籍"
    assert ws["K2"].value == "51-60歲"
    assert ws["O2"].value == "8.乳癌"
    assert ws["R2"].value == "是"
    assert ws["S2"].value == "1.癌症篩檢與預防"
    assert ws["T2"].value == "1.假髮/頭巾/毛帽用品"
    assert wb["一月"]["A1"].value == "=SUM(個案總表!A2:A6)"


def test_writer_preserves_style_and_column_width(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    before = load_workbook(template)
    before_fill = before["個案總表"]["B1"].fill.fgColor.rgb
    before_width = before["個案總表"].column_dimensions["B"].width

    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(make_record())
    writer.save()

    after = load_workbook(working)
    assert after["個案總表"]["B1"].fill.fgColor.rgb == before_fill
    assert after["個案總表"].column_dimensions["B"].width == before_width


def test_existing_duplicate_keys_include_service_summary(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    record = make_record()
    writer = WorkbookWriter.create_from_template(template, working)
    writer.write_record(record)
    writer.save()

    reopened = WorkbookWriter(working)

    assert record.duplicate_key() in reopened.existing_duplicate_keys()
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
pytest tests/test_workbook.py -q
```

Expected: FAIL because `WorkbookWriter` does not exist.

- [ ] **Step 4: Implement workbook writer**

Create `src/ocr_from2xlsx/workbook.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from ocr_from2xlsx.constants import (
    AGE_GROUP_LABELS,
    BASIC_COLUMN_BY_FIELD,
    CANCER_LABELS,
    CHANNEL_LABELS,
    DISEASE_STATUS_LABELS,
    GENDER_LABELS,
    IDENTITY_LABELS,
    NATIONALITY_LABELS,
    SOURCE_LABELS,
    WORKBOOK_SHEET,
)
from ocr_from2xlsx.domain import Record


LABEL_BY_CODE = {
    "screening_prevention": "1.癌症篩檢與預防",
    "disease_treatment_knowledge": "2.疾病及治療知識",
    "wig_hat": "1.假髮/頭巾/毛帽用品",
    "social_welfare": "3.社福資源",
    "care_information": "9.照護資訊",
    "received_service_help": "4.獲得服務協助",
}

SUMMARY_BY_HEADER_PREFIX_AND_LABEL = {
    ("諮詢-健康與醫療系統", "1.癌症篩檢與預防"): "health_medical:screening_prevention",
    ("諮詢-健康與醫療系統", "2.疾病及治療知識"): "health_medical:disease_treatment_knowledge",
    ("提供實體用品及設備", "1.假髮/頭巾/毛帽用品"): "supplies:wig_hat",
    ("轉介或連結院內資源", "3.社福資源"): "internal:social_welfare",
    ("轉介或連結院外資源", "9.照護資訊"): "external:care_information",
    ("轉介或連結資源成果", "4.獲得服務協助"): "outcomes:received_service_help",
}


class WorkbookWriter:
    def __init__(self, working_path: Path | str) -> None:
        self.working_path = Path(working_path)
        self.workbook = load_workbook(self.working_path)
        if WORKBOOK_SHEET not in self.workbook.sheetnames:
            raise ValueError(f"Missing sheet: {WORKBOOK_SHEET}")
        self.sheet = self.workbook[WORKBOOK_SHEET]
        self.header_map = self._build_header_map(self.sheet)

    @classmethod
    def create_from_template(cls, template_path: Path | str, working_path: Path | str) -> "WorkbookWriter":
        template_path = Path(template_path)
        working_path = Path(working_path)
        working_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, working_path)
        return cls(working_path)

    def write_record(self, record: Record) -> int:
        row = self._next_empty_row()
        self._set(row, BASIC_COLUMN_BY_FIELD["service_month"], record.service_month_label())
        self._set(row, BASIC_COLUMN_BY_FIELD["service_date"], record.service_date)
        self._set(row, BASIC_COLUMN_BY_FIELD["identity"], IDENTITY_LABELS[record.identity])
        self._set(row, BASIC_COLUMN_BY_FIELD["name"], record.name)
        self._set(row, BASIC_COLUMN_BY_FIELD["medical_record_no"], record.medical_record_no)
        self._set(row, BASIC_COLUMN_BY_FIELD["gender"], GENDER_LABELS[record.gender])

        if record.identity == "patient":
            fields = record.patient_fields
            self._set(row, BASIC_COLUMN_BY_FIELD["nationality"], NATIONALITY_LABELS.get(fields.nationality or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["age_group"], AGE_GROUP_LABELS.get(fields.age_group or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["channel"], CHANNEL_LABELS.get(fields.channel or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["disease_status"], DISEASE_STATUS_LABELS.get(fields.disease_status or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["source"], SOURCE_LABELS.get(fields.source or ""))
            self._set(row, BASIC_COLUMN_BY_FIELD["newly_diagnosed_within_year"], "是" if fields.newly_diagnosed_within_year else "否")
            for index, cancer in enumerate(fields.cancers[:3], start=1):
                self._set(row, f"癌別{index}\n(病人才填)", CANCER_LABELS.get(cancer, cancer))

        self._write_services(row, record)
        return row

    def save(self) -> None:
        self.workbook.calculation.fullCalcOnLoad = True
        self.workbook.calculation.forceFullCalc = True
        self.workbook.save(self.working_path)

    def existing_duplicate_keys(self) -> set[tuple[str, str, str, str]]:
        keys: set[tuple[str, str, str, str]] = set()
        service_date_col = self.header_map.get(BASIC_COLUMN_BY_FIELD["service_date"])
        name_col = self.header_map.get(BASIC_COLUMN_BY_FIELD["name"])
        id_col = self.header_map.get(BASIC_COLUMN_BY_FIELD["medical_record_no"])
        if not service_date_col or not name_col or not id_col:
            return keys
        for row in range(2, self.sheet.max_row + 1):
            service_date = self.sheet.cell(row=row, column=service_date_col).value
            name = self.sheet.cell(row=row, column=name_col).value
            medical_id = self.sheet.cell(row=row, column=id_col).value
            if service_date and name and medical_id:
                keys.add((str(service_date), str(name), str(medical_id), self._service_summary_from_row(row)))
        return keys

    def _write_services(self, row: int, record: Record) -> None:
        for category, codes in record.services.consultation.items():
            prefix = _consultation_prefix(category)
            for index, code in enumerate(codes, start=1):
                self._set_if_present(row, f"{prefix}{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.supplies, start=1):
            self._set_if_present(row, f"提供實體用品及設備{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.internal_referrals, start=1):
            self._set_if_present(row, f"轉介或連結院內資源{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.external_referrals, start=1):
            self._set_if_present(row, f"轉介或連結院外資源{index}", LABEL_BY_CODE.get(code, code))
        for index, code in enumerate(record.services.referral_outcomes, start=1):
            self._set_if_present(row, f"轉介或連結資源成果{index}", LABEL_BY_CODE.get(code, code))

    def _service_summary_from_row(self, row: int) -> str:
        parts: list[str] = []
        for header, column in self.header_map.items():
            value = self.sheet.cell(row=row, column=column).value
            if value in (None, ""):
                continue
            for (prefix, label), summary_part in SUMMARY_BY_HEADER_PREFIX_AND_LABEL.items():
                if header.startswith(prefix) and value == label:
                    parts.append(summary_part)
        return "|".join(sorted(parts))

    def _build_header_map(self, sheet: Worksheet) -> dict[str, int]:
        header_map: dict[str, int] = {}
        for cell in sheet[1]:
            if cell.value:
                header_map[str(cell.value)] = cell.column
        missing = [header for header in ["服務月份", "服務日期", "身分", "姓名", "ID", "性別"] if header not in header_map]
        if missing:
            raise ValueError(f"Missing required headers: {', '.join(missing)}")
        return header_map

    def _next_empty_row(self) -> int:
        name_col = self.header_map[BASIC_COLUMN_BY_FIELD["name"]]
        for row in range(2, self.sheet.max_row + 2):
            if self.sheet.cell(row=row, column=name_col).value in (None, ""):
                return row
        return self.sheet.max_row + 1

    def _set(self, row: int, header: str, value: object) -> None:
        column = self.header_map[header]
        self.sheet.cell(row=row, column=column, value=value)

    def _set_if_present(self, row: int, header: str, value: object) -> None:
        column = self.header_map.get(header)
        if column:
            self.sheet.cell(row=row, column=column, value=value)


def _consultation_prefix(category: str) -> str:
    return {
        "health_medical": "諮詢-健康與醫療系統",
        "symptom_side_effect": "諮詢-症狀與副作用照護",
        "nutrition_diet": "諮詢-營養與飲食",
        "psychosocial_emotion": "諮詢-社會心理情緒",
        "financial_social": "諮詢-經濟與社會資源",
        "care_support": "諮詢-照顧與支持",
    }[category]
```

- [ ] **Step 5: Update CHANGELOG**

Add under `### Added`:

```markdown
- 新增保留模板格式的 `個案總表` XLSX 寫入器。
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/test_workbook.py tests/test_validation.py tests/test_json_io.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/ocr_from2xlsx/workbook.py src/ocr_from2xlsx/constants.py tests/fixtures.py tests/test_workbook.py CHANGELOG.md
git commit -m "feat: write confirmed records to workbook"
```

## Task 6: Import Report and Session Workflow

**Files:**
- Create: `src/ocr_from2xlsx/report.py`
- Create: `src/ocr_from2xlsx/session.py`
- Create: `tests/test_session.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing session tests**

Create `tests/test_session.py`:

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.session import ImportSession
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


def test_auto_confirm_writes_and_saves_record(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    session = ImportSession.start(template, working)

    result = session.accept_scan(make_record())

    assert result.status == "written"
    assert result.row_number == 2
    assert working.exists()


def test_blocked_record_is_not_written(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    create_workbook_template(template)
    session = ImportSession.start(template, working)
    record = make_record()
    record.service_date = ""

    result = session.accept_scan(record)

    assert result.status == "blocked"
    assert result.row_number is None
    assert "service_date.invalid" in result.blockers
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_session.py -q
```

Expected: FAIL because `session.py` does not exist.

- [ ] **Step 3: Implement report model**

Create `src/ocr_from2xlsx/report.py`:

```python
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ImportReportItem:
    record_id: str
    status: str
    row_number: int | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportReport:
    items: list[ImportReportItem] = field(default_factory=list)

    def add(self, item: ImportReportItem) -> None:
        self.items.append(item)

    def write_json(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps({"items": [asdict(item) for item in self.items]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def write_csv(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["record_id", "status", "row_number", "blockers", "warnings"])
            writer.writeheader()
            for item in self.items:
                writer.writerow(
                    {
                        "record_id": item.record_id,
                        "status": item.status,
                        "row_number": item.row_number or "",
                        "blockers": ";".join(item.blockers),
                        "warnings": ";".join(item.warnings),
                    }
                )
```

- [ ] **Step 4: Implement session workflow**

Create `src/ocr_from2xlsx/session.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.report import ImportReport, ImportReportItem
from ocr_from2xlsx.validation import validate_record
from ocr_from2xlsx.workbook import WorkbookWriter


@dataclass(slots=True)
class AcceptResult:
    record_id: str
    status: str
    row_number: int | None
    blockers: list[str]
    warnings: list[str]


class ImportSession:
    def __init__(self, writer: WorkbookWriter) -> None:
        self.writer = writer
        self.report = ImportReport()
        self.batch_duplicate_keys: set[tuple[str, str, str, str]] = set()
        self.existing_duplicate_keys = writer.existing_duplicate_keys()

    @classmethod
    def start(cls, template_path: Path | str, working_path: Path | str) -> "ImportSession":
        return cls(WorkbookWriter.create_from_template(template_path, working_path))

    def accept_scan(self, record: Record, force: bool = False) -> AcceptResult:
        existing_keys = set(self.existing_duplicate_keys)
        if record.duplicate_key() in self.batch_duplicate_keys:
            validation = validate_record(record, existing_keys)
            validation.blockers.append("duplicate.in_batch")
        else:
            validation = validate_record(record, existing_keys)

        if validation.blockers and not force:
            item = ImportReportItem(
                record_id=record.record_id,
                status="blocked",
                blockers=validation.blockers,
                warnings=validation.warnings,
            )
            self.report.add(item)
            return AcceptResult(record.record_id, "blocked", None, validation.blockers, validation.warnings)

        row_number = self.writer.write_record(record)
        self.writer.save()
        self.batch_duplicate_keys.add(record.duplicate_key())
        status = "forced" if validation.blockers and force else "written"
        item = ImportReportItem(
            record_id=record.record_id,
            status=status,
            row_number=row_number,
            blockers=validation.blockers,
            warnings=validation.warnings,
        )
        self.report.add(item)
        return AcceptResult(record.record_id, status, row_number, validation.blockers, validation.warnings)

    def write_report(self, json_path: Path | str, csv_path: Path | str) -> None:
        self.report.write_json(json_path)
        self.report.write_csv(csv_path)
```

- [ ] **Step 5: Update CHANGELOG**

Add under `### Added`:

```markdown
- 新增每筆確認即寫入保存的匯入工作階段與報告模型。
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/test_session.py tests/test_workbook.py tests/test_validation.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/ocr_from2xlsx/report.py src/ocr_from2xlsx/session.py tests/test_session.py CHANGELOG.md
git commit -m "feat: add import session workflow"
```

## Task 7: CLI Import Flow

**Files:**
- Modify: `src/ocr_from2xlsx/cli.py`
- Create: `tests/test_cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write CLI tests**

Create `tests/test_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.cli import main
from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.json_io import dump_batch
from tests.fixtures import create_workbook_template
from tests.test_json_io import make_record


def test_import_json_cli_writes_workbook(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    records_json = tmp_path / "records.json"
    create_workbook_template(template)
    dump_batch(
        Batch(
            source_batch=SourceBatch(created_at="2026-05-24T00:00:00+08:00", source_type="json_import", template_name="template.xlsx"),
            records=[make_record()],
        ),
        records_json,
    )

    exit_code = main(
        [
            "import-json",
            "--input",
            str(records_json),
            "--template",
            str(template),
            "--working",
            str(working),
            "--report-json",
            str(report_json),
            "--report-csv",
            str(report_csv),
        ]
    )

    assert exit_code == 0
    assert working.exists()
    assert report_json.exists()
    assert report_csv.exists()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_cli.py -q
```

Expected: FAIL because `import-json` is not implemented.

- [ ] **Step 3: Implement CLI import command**

Update `src/ocr_from2xlsx/cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr-from2xlsx",
        description="Import normalized service-record JSON into the monthly report XLSX.",
    )
    parser.add_argument("--version", action="store_true", help="Print package version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    sample = subparsers.add_parser("sample-json", help="Generate deterministic sample service-record JSON.")
    sample.add_argument("--output", required=True, help="Output JSON path.")
    sample.add_argument("--count", type=int, default=100, help="Number of records to generate.")
    sample.add_argument("--template-name", default="template.xlsx", help="Template name stored in source metadata.")

    validate = subparsers.add_parser("validate-json", help="Validate normalized service-record JSON.")
    validate.add_argument("--input", required=True, help="Input JSON path.")

    import_json = subparsers.add_parser("import-json", help="Import confirmed JSON records into a working XLSX.")
    import_json.add_argument("--input", required=True, help="Input JSON path.")
    import_json.add_argument("--template", required=True, help="Source XLSX template path.")
    import_json.add_argument("--working", required=True, help="Working XLSX output path.")
    import_json.add_argument("--report-json", required=True, help="Import report JSON path.")
    import_json.add_argument("--report-csv", required=True, help="Import report CSV path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from ocr_from2xlsx import __version__

        print(__version__)
        return 0
    if args.command == "sample-json":
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.sample_data import generate_sample_batch

        dump_batch(generate_sample_batch(count=args.count, template_name=args.template_name), Path(args.output))
        print(args.output)
        return 0
    if args.command == "validate-json":
        from ocr_from2xlsx.json_io import load_batch
        from ocr_from2xlsx.validation import validate_batch

        batch = load_batch(Path(args.input))
        results = validate_batch(batch)
        blocker_count = sum(len(result.blockers) for result in results.values())
        warning_count = sum(len(result.warnings) for result in results.values())
        print(f"records={len(batch.records)} blockers={blocker_count} warnings={warning_count}")
        return 1 if blocker_count else 0
    if args.command == "import-json":
        from ocr_from2xlsx.json_io import load_batch
        from ocr_from2xlsx.session import ImportSession

        batch = load_batch(Path(args.input))
        session = ImportSession.start(Path(args.template), Path(args.working))
        for record in batch.records:
            session.accept_scan(record)
        session.write_report(Path(args.report_json), Path(args.report_csv))
        print(args.working)
        return 0
    parser.print_help()
    return 0
```

- [ ] **Step 4: Update README help and changelog**

Run:

```powershell
ocr-from2xlsx --help
```

Replace the README help block with the updated output. Add under `CHANGELOG.md` `### Added`:

```markdown
- 新增 JSON 到 XLSX 的 CLI 匯入流程。
```

- [ ] **Step 5: Run tests**

Run:

```powershell
pytest tests/test_cli.py tests/test_session.py tests/test_workbook.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/ocr_from2xlsx/cli.py tests/test_cli.py README.md CHANGELOG.md
git commit -m "feat: add JSON import CLI"
```

## Task 8: Capture and OCR Adapter Interfaces

**Files:**
- Create: `src/ocr_from2xlsx/capture.py`
- Create: `src/ocr_from2xlsx/normalizer.py`
- Create: `tests/test_capture.py`
- Create: `tests/test_normalizer.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write capture and normalizer tests**

Create `tests/test_normalizer.py`:

```python
from __future__ import annotations

from ocr_from2xlsx.normalizer import normalize_raw_record


def test_normalize_raw_record_builds_record() -> None:
    raw = {
        "record_id": "scan-0001",
        "service_date": "2026-03-15",
        "identity": "patient",
        "name": "王小明",
        "medical_record_no": "A123456",
        "gender": "female",
        "patient_fields": {"nationality": "local", "age_group": "51_60", "channel": "internal_referral", "disease_status": "treating", "source": "outpatient", "cancers": ["breast_cancer"], "newly_diagnosed_within_year": True},
        "services": {"consultation": {"health_medical": ["screening_prevention"]}, "supplies": [], "internal_referrals": [], "external_referrals": [], "referral_outcomes": []},
        "ocr": {"confidence": 0.91, "raw_text": "raw", "warnings": []},
    }

    record = normalize_raw_record(raw)

    assert record.record_id == "scan-0001"
    assert record.name == "王小明"
    assert record.patient_fields.cancers == ["breast_cancer"]
```

Create `tests/test_capture.py`:

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.capture import JsonRecordSource
from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.json_io import dump_batch
from tests.test_json_io import make_record


def test_json_record_source_yields_records(tmp_path: Path) -> None:
    path = tmp_path / "records.json"
    dump_batch(
        Batch(
            source_batch=SourceBatch(created_at="2026-05-24T00:00:00+08:00", source_type="json_import", template_name="template.xlsx"),
            records=[make_record()],
        ),
        path,
    )

    source = JsonRecordSource(path)

    assert [record.name for record in source.records()] == ["王小明"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_capture.py tests/test_normalizer.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement normalizer**

Create `src/ocr_from2xlsx/normalizer.py`:

```python
from __future__ import annotations

from typing import Any

from ocr_from2xlsx.domain import Record


def normalize_raw_record(raw: dict[str, Any]) -> Record:
    return Record.from_dict(raw)
```

- [ ] **Step 4: Implement capture sources**

Create `src/ocr_from2xlsx/capture.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.json_io import load_batch


class JsonRecordSource:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def records(self) -> Iterable[Record]:
        yield from load_batch(self.path).records


class ImageFolderSource:
    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)

    def image_paths(self) -> list[Path]:
        patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp"]
        paths: list[Path] = []
        for pattern in patterns:
            paths.extend(self.folder.glob(pattern))
        return sorted(paths)


class UvcCameraSource:
    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index

    def is_available(self) -> bool:
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError:
            return False
        capture = cv2.VideoCapture(self.camera_index)
        try:
            return bool(capture.isOpened())
        finally:
            capture.release()
```

- [ ] **Step 5: Update CHANGELOG**

Add under `### Added`:

```markdown
- 新增 JSON、圖片資料夾與 UVC 攝影機 capture adapter 邊界。
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/test_capture.py tests/test_normalizer.py tests/test_json_io.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/ocr_from2xlsx/capture.py src/ocr_from2xlsx/normalizer.py tests/test_capture.py tests/test_normalizer.py CHANGELOG.md
git commit -m "feat: add capture and OCR adapter boundaries"
```

## Task 9: Native Tkinter Review UI

**Files:**
- Create: `src/ocr_from2xlsx/app.py`
- Modify: `src/ocr_from2xlsx/cli.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add desktop app module**

Create `src/ocr_from2xlsx/app.py`:

```python
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ocr_from2xlsx.capture import JsonRecordSource
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.session import ImportSession


class ReviewApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OCR from Service Record to XLSX")
        self.geometry("1200x720")
        self.records: list[Record] = []
        self.current_index = -1
        self.session: ImportSession | None = None
        self.editing = False
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(toolbar, text="選擇模板 XLSX", command=self._choose_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="匯入 JSON", command=self._load_json).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="下一張 / 確認目前資料", command=self._next_record).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="強制寫入", command=self._force_write).pack(side=tk.LEFT, padx=4)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.preview = tk.Text(body, width=35)
        self.preview.insert("1.0", "攝影機或圖片預覽區\n第一版可用 JSON 模擬連續掃描。")
        body.add(self.preview)

        form = ttk.Frame(body)
        body.add(form)
        self.fields: dict[str, tk.StringVar] = {}
        for row, key in enumerate(["record_id", "service_date", "identity", "name", "medical_record_no", "gender"]):
            ttk.Label(form, text=key).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            entry = ttk.Entry(form, textvariable=var, width=40)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            entry.bind("<Key>", lambda _event: self._mark_editing())
            self.fields[key] = var

        self.status_list = tk.Listbox(body, width=50)
        body.add(self.status_list)

    def _choose_template(self) -> None:
        template = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not template:
            return
        output_dir = filedialog.askdirectory(title="選擇輸出資料夾")
        if not output_dir:
            return
        working = Path(output_dir) / "匯入中.xlsx"
        self.session = ImportSession.start(template, working)
        self.status_list.insert(tk.END, f"工作檔: {working}")

    def _load_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        self.records = list(JsonRecordSource(path).records())
        self.current_index = -1
        self.status_list.insert(tk.END, f"已載入 {len(self.records)} 筆 JSON")
        self._next_record()

    def _next_record(self) -> None:
        if self.session and self.current_index >= 0 and not self.editing:
            current = self.records[self.current_index]
            result = self.session.accept_scan(current)
            self.status_list.insert(tk.END, f"{current.record_id}: {result.status} row={result.row_number} blockers={result.blockers}")
        self.editing = False
        self.current_index += 1
        if self.current_index >= len(self.records):
            messagebox.showinfo("完成", "沒有更多資料。")
            return
        self._show_record(self.records[self.current_index])

    def _force_write(self) -> None:
        if not self.session or self.current_index < 0:
            return
        self._apply_form_to_record(self.records[self.current_index])
        result = self.session.accept_scan(self.records[self.current_index], force=True)
        self.status_list.insert(tk.END, f"{result.record_id}: {result.status} row={result.row_number} blockers={result.blockers}")
        self.editing = False

    def _show_record(self, record: Record) -> None:
        self.fields["record_id"].set(record.record_id)
        self.fields["service_date"].set(record.service_date)
        self.fields["identity"].set(record.identity)
        self.fields["name"].set(record.name)
        self.fields["medical_record_no"].set(record.medical_record_no)
        self.fields["gender"].set(record.gender)

    def _apply_form_to_record(self, record: Record) -> None:
        record.service_date = self.fields["service_date"].get()
        record.identity = self.fields["identity"].get()
        record.name = self.fields["name"].get()
        record.medical_record_no = self.fields["medical_record_no"].get()
        record.gender = self.fields["gender"].get()
        record.review.edited_by_user = True

    def _mark_editing(self) -> None:
        self.editing = True


def run_app() -> int:
    app = ReviewApp()
    app.mainloop()
    return 0
```

- [ ] **Step 2: Add CLI launch command**

Update `src/ocr_from2xlsx/cli.py` by adding this subparser:

```python
    subparsers.add_parser("app", help="Launch the native desktop review UI.")
```

Add this branch in `main()`:

```python
    if args.command == "app":
        from ocr_from2xlsx.app import run_app

        return run_app()
```

- [ ] **Step 3: Update README usage and changelog**

Add this to README Usage:

```markdown
Launch the native desktop UI:

```powershell
ocr-from2xlsx app
```
```

Add under `CHANGELOG.md` `### Added`:

```markdown
- 新增不開 localhost port 的 Tkinter 原生桌面審核介面。
```

- [ ] **Step 4: Manual UI smoke test**

Run:

```powershell
ocr-from2xlsx sample-json --output output\sample-records.json --count 5
ocr-from2xlsx app
```

Expected:

1. A native Windows desktop window opens.
2. Selecting a test template and `output\sample-records.json` loads records.
3. Pressing `下一張 / 確認目前資料` writes valid records into the working XLSX.
4. No browser opens and no localhost URL appears.

- [ ] **Step 5: Run automated tests**

Run:

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/ocr_from2xlsx/app.py src/ocr_from2xlsx/cli.py README.md CHANGELOG.md
git commit -m "feat: add native review UI"
```

## Task 10: Packaging and Policy Verification

**Files:**
- Create: `scripts/build-windows.ps1`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Create PyInstaller build script**

Create `scripts/build-windows.ps1`:

```powershell
$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
python -m pip install -e ".[dev]"
pyinstaller `
  --name ocr-from2xlsx `
  --onefile `
  --collect-submodules openpyxl `
  --clean `
  src\ocr_from2xlsx\__main__.py

Write-Host "Built dist\ocr-from2xlsx.exe"
```

- [ ] **Step 2: Update README packaging section**

Add under Install:

```markdown
Build a portable Windows executable:

```powershell
.\scripts\build-windows.ps1
```

The executable is written to `dist\ocr-from2xlsx.exe`.
```

- [ ] **Step 3: Update CHANGELOG**

Add under `### Added`:

```markdown
- 新增 Windows PyInstaller 打包腳本。
```

- [ ] **Step 4: Run full tests**

Run:

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Run policy check**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\haman\.copilot\session-state\365ef598-7c4f-407f-a29c-ee9635ec8d90\files\paulsha-conventions"
python -m policy_check --repo .
```

Expected:

```text
- fail: 0
```

- [ ] **Step 6: Build executable**

Run:

```powershell
.\scripts\build-windows.ps1
```

Expected: `dist\ocr-from2xlsx.exe` exists.

- [ ] **Step 7: Smoke test executable**

Run:

```powershell
.\dist\ocr-from2xlsx.exe --version
```

Expected:

```text
0.0.0
```

- [ ] **Step 8: Commit**

```powershell
git add scripts/build-windows.ps1 README.md CHANGELOG.md
git commit -m "chore: add Windows packaging script"
```

## Task 11: End-to-End Fixture Import

**Files:**
- Create: `tests/test_end_to_end.py`
- Modify: `README.md`

- [ ] **Step 1: Write end-to-end test**

Create `tests/test_end_to_end.py`:

```python
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from ocr_from2xlsx.json_io import dump_batch
from ocr_from2xlsx.sample_data import generate_sample_batch
from ocr_from2xlsx.session import ImportSession
from tests.fixtures import create_workbook_template


def test_end_to_end_import_keeps_template_and_writes_valid_records(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    working = tmp_path / "working.xlsx"
    report_json = tmp_path / "report.json"
    report_csv = tmp_path / "report.csv"
    sample_json = tmp_path / "sample.json"
    create_workbook_template(template)
    batch = generate_sample_batch(count=12, template_name=template.name)
    dump_batch(batch, sample_json)

    session = ImportSession.start(template, working)
    for record in batch.records:
        session.accept_scan(record)
    session.write_report(report_json, report_csv)

    workbook = load_workbook(working)
    assert "個案總表" in workbook.sheetnames
    assert "一月" in workbook.sheetnames
    assert workbook["個案總表"]["B2"].value is not None
    assert workbook["一月"]["A1"].value == "=SUM(個案總表!A2:A6)"
    assert report_json.exists()
    assert report_csv.exists()
```

- [ ] **Step 2: Run end-to-end test**

Run:

```powershell
pytest tests/test_end_to_end.py -q
```

Expected: test passes.

- [ ] **Step 3: Add README workflow example**

Add under Usage:

```markdown
Command-line smoke workflow:

```powershell
ocr-from2xlsx sample-json --output output\sample-records.json --count 100
ocr-from2xlsx validate-json --input output\sample-records.json
ocr-from2xlsx import-json --input output\sample-records.json --template path\to\template.xlsx --working output\匯入中.xlsx --report-json output\report.json --report-csv output\report.csv
```
```

- [ ] **Step 4: Run full verification**

Run:

```powershell
pytest -q
$env:PYTHONPATH = "C:\Users\haman\.copilot\session-state\365ef598-7c4f-407f-a29c-ee9635ec8d90\files\paulsha-conventions"
python -m policy_check --repo .
```

Expected: tests pass and policy check reports `fail: 0`.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_end_to_end.py README.md
git commit -m "test: add end-to-end import coverage"
```

## Task 12: Push and Review

**Files:**
- No code changes unless verification reveals a failing check.

- [ ] **Step 1: Inspect final status**

Run:

```powershell
git --no-pager status --short
git --no-pager log --oneline -12
```

Expected: no unexpected untracked source files. Ignored `.xlsx`, `output/`, `dist/`, and build artifacts may exist locally.

- [ ] **Step 2: Push branch**

Run:

```powershell
git push
```

Expected: `feature/bootstrap-ocr-design` updates on `git@github.com:hamanpaul/ocr-from2xlsx.git`.

- [ ] **Step 3: Request code review**

Use `superpowers:requesting-code-review` before claiming implementation complete. Provide reviewers:

```text
Review the Python prototype for the OCR-to-XLSX import workflow against docs/superpowers/specs/2026-05-24-ocr-xlsx-import-design.md. Focus on workbook format preservation, no localhost/server usage, validation behavior, and immediate save after each confirmed record.
```

## Self-Review Checklist

- Spec coverage:
  - Native desktop and no localhost: Task 9.
  - JSON schema: Task 2.
  - 100-record sample data: Task 3.
  - Validation and duplicates: Task 4.
  - Workbook-only data writes and format preservation: Task 5.
  - Save after each confirmed record: Task 6.
  - CLI for Rust-friendly core entrypoints: Task 7.
  - Capture/OCR adapter boundaries: Task 8.
  - Packaging: Task 10.
  - End-to-end verification: Task 11.
- Incomplete-marker scan: no unfinished task wording should remain in this file.
- Type consistency:
  - `Record`, `Batch`, `ImportSession`, `WorkbookWriter`, and `ValidationResult` names are consistent across tasks.
  - CLI commands are `sample-json`, `validate-json`, `import-json`, and `app`.
