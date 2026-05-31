# Form-Layout Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared, render-agnostic, hand-curated form-layout model (`src/ocr_from2xlsx/form_layout.py`) describing every section/field/option of the 服務紀錄表 form, bound to `constants.py` codes and to the `service_record.v1` Record path, validated against the real blank sheet.

**Architecture:** Pure-stdlib dataclasses (`Option`, `Field`, `Section`, `FormLayout`) plus a `service_record_layout()` builder containing the full curated option data (cell + label + code). A test validates the model against the repo's blank `服務紀錄表` sheet with two-way coverage. No geometry/pixels; consumers (confirmation UI, training generator) import this model instead of hard-coding the form.

**Tech Stack:** Python 3.12 stdlib only for the module; `openpyxl` (already a dep) for the validation test that reads the blank xlsx.

---

## Spec Reference

Implements `openspec/changes/add-form-layout-model/` and design
`docs/superpowers/specs/2026-05-31-form-layout-model-design.md`.

Source sheet: `115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx` → sheet `服務紀錄表` (A1:F52). Every option
is a cell whose text is `□<label>`. Codes come from `src/ocr_from2xlsx/constants.py`. Record paths target
`service_record.v1` (`Record` in `domain.py`).

Invariants: the module is pure stdlib (no paddle/PIL/openpyxl import in `form_layout.py` itself); codes reuse
constants (no parallel set); the validation test is the correctness gate — fix the layout to match the sheet,
never weaken the test.

## File Structure

```text
src/ocr_from2xlsx/form_layout.py   NEW. Dataclasses + service_record_layout() with full curated data.
tests/test_form_layout.py          NEW. Accessor tests + model↔sheet two-way coverage validation (openpyxl).
CHANGELOG.md                       MODIFY.
```

---

## Task 1: Dataclasses + accessors (pure)

**Files:**
- Create: `src/ocr_from2xlsx/form_layout.py`
- Create: `tests/test_form_layout.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_form_layout.py`:

```python
from __future__ import annotations

from ocr_from2xlsx.form_layout import (
    Field,
    FormLayout,
    Option,
    Section,
    service_record_layout,
)


def _tiny_layout() -> FormLayout:
    return FormLayout(
        template_id="t",
        sections=(
            Section(
                id="B",
                title="綜合身份統計",
                fields=(
                    Field(
                        key="gender",
                        title="性別",
                        kind="single_choice",
                        record_path="gender",
                        anchor_cell="A25",
                        options=(
                            Option(label="女性", code="female", cell="B25"),
                            Option(label="男性", code="male", cell="B26"),
                        ),
                    ),
                    Field(
                        key="name",
                        title="姓名",
                        kind="text",
                        record_path="name",
                        anchor_cell="B23",
                    ),
                ),
            ),
        ),
    )


def test_field_by_key_and_iter():
    layout = _tiny_layout()
    assert layout.field_by_key("gender").kind == "single_choice"
    assert layout.field_by_key("name").options == ()
    assert layout.field_by_key("missing") is None
    assert [f.key for f in layout.iter_fields()] == ["gender", "name"]


def test_iter_options_and_options_by_code():
    layout = _tiny_layout()
    pairs = [(f.key, o.code) for f, o in layout.iter_options()]
    assert pairs == [("gender", "female"), ("gender", "male")]
    by_code = layout.options_by_code("gender")
    assert by_code["female"].cell == "B25"
    assert layout.options_by_code("name") == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_form_layout.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement dataclasses + accessors**

Create `src/ocr_from2xlsx/form_layout.py` (Task 2 appends `service_record_layout()` to the same file):

```python
"""Shared, render-agnostic model of the 服務紀錄表 form.

Pure stdlib. Sections -> fields (text / single_choice / multi_choice) -> options (label, code, cell).
Each field declares its path in the service_record.v1 Record (or None when the form field has no
Record counterpart). Codes reuse ocr_from2xlsx.constants. No pixel geometry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

Kind = Literal["text", "single_choice", "multi_choice"]


@dataclass(frozen=True, slots=True)
class Option:
    label: str
    code: str
    cell: str


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    title: str
    kind: Kind
    record_path: str | None
    anchor_cell: str
    options: tuple[Option, ...] = ()


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    title: str
    fields: tuple[Field, ...]


@dataclass(frozen=True, slots=True)
class FormLayout:
    template_id: str
    sections: tuple[Section, ...]

    def iter_fields(self) -> Iterator[Field]:
        for section in self.sections:
            yield from section.fields

    def field_by_key(self, key: str) -> Field | None:
        for fld in self.iter_fields():
            if fld.key == key:
                return fld
        return None

    def iter_options(self) -> Iterator[tuple[Field, Option]]:
        for fld in self.iter_fields():
            for option in fld.options:
                yield (fld, option)

    def options_by_code(self, field_key: str) -> dict[str, Option]:
        fld = self.field_by_key(field_key)
        if fld is None:
            return {}
        return {option.code: option for option in fld.options}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_form_layout.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/form_layout.py tests/test_form_layout.py
git commit -m "feat: add form-layout dataclasses and accessors"
```
End every commit message with a blank line then exactly:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## Task 2: `service_record_layout()` with full curated data

**Files:**
- Modify: `src/ocr_from2xlsx/form_layout.py` (append the builder + data)
- Modify: `tests/test_form_layout.py` (add content tests)

The option data below was transcribed from the `服務紀錄表` sheet (cell → `□label`) and bound to
`constants.py` codes. Cell layout per field:

- **identity** (single, record `identity`, anchor A23): `病人`→patient `B23`; `親友及照顧者`→family_caregiver `C23`; `一般民眾及其他`→public_other `D23`.
- **gender** (single, record `gender`, anchor A25): `女性`→female `B25`; `男性`→male `B26`; `其他`→other `B27`.
- **nationality** (single, record `patient_fields.nationality`, anchor A28): `本國籍`→local `B28`; `外國籍`→foreign `B29`.
- **age** (single, record `patient_fields.age_group`, anchor A30): `20歲以下`→20_under `B30`; `21-30歲`→21_30 `B31`; `31-40歲`→31_40 `B32`; `41-50歲`→41_50 `B33`; `51-60歲`→51_60 `B34`; `61-70歲`→61_70 `B35`; `71歲以上`→71_over `B36`.
- **channel** (single, record `patient_fields.channel`, anchor A38): `1.自行得知`→self_known `B38`; `2.病友或家屬介紹`→introduced `C38`; `3.主動關懷或追蹤`→active_followup `D38`; `4.院內轉介`→internal_referral `E38`; `5.院外轉介`→external_referral `F38`; `6.活動課程接觸`→activity `B39`; `7.其他`→other `C39`.
- **disease_status** (single, record `patient_fields.disease_status`, anchor A40): `1.尚未確診`→undiagnosed `B40`; `2.確診，尚未治療`→diagnosed_not_treated `C40`; `3.確診，拒絕治療`→diagnosed_refused `D40`; `4.治療中`→treating `E40`; `5.復發治療中`→recurrence_treating `F40`; `6.追蹤期`→followup `B41`; `7.緩和治療`→palliative `C41`.
- **source** (single, record `patient_fields.source`, anchor A42): `1.門診`→outpatient `B42`; `2.住院`→inpatient `C42`; `3.急診`→emergency `D42`.
- **cancer** (multi, record `patient_fields.cancers`, anchor A43), cells row43 B–F, row44 B–F, row45 B–F, row46 B–F, row47 B–F (1..25): brain_cancer B43, nasopharyngeal_cancer C43, oral_cancer D43, hypopharyngeal_cancer E43, laryngeal_cancer F43, thyroid_cancer B44, esophageal_cancer C44, breast_cancer D44, lung_cancer E44, liver_cancer F44, colorectal_cancer B45, stomach_cancer C45, pancreatic_cancer D45, kidney_cancer E45, bladder_cancer F45, ovarian_cancer B46, endometrial_cancer C46, cervical_cancer D46, prostate_cancer E46, lymphoma F46, leukemia B47, skin_cancer C47, multiple_myeloma D47, sarcoma E47, other F47. (Labels are the sheet's `N.中文`; bind to `CANCER_LABELS` in constants.)
- **newly_diagnosed** (single, record `patient_fields.newly_diagnosed_within_year`, anchor A48): one option `一年內新診斷個案`→`true` `A48` (checked ⇒ Record value True; see Task 2 Step 3 note).
- **consultation.health_medical** (multi, record `services.consultation.health_medical`, anchor B4): screening_prevention C4, disease_treatment_knowledge D4, doctor_patient_communication E4, healthy_lifestyle F4, second_opinion C5, transfer_registration D5, palliative_patient_rights E5, other F5.
- **consultation.symptom_side_effect** (multi, record `services.consultation.symptom_side_effect`, anchor B6): treatment_side_effect C6, wound_care D6, pain_management E6, fatigue_strength F6, integrated_care C7, sexuality_fertility D7, other E7.
- **consultation.nutrition_diet** (multi, record `services.consultation.nutrition_diet`, anchor B8): diet_conditioning C8, nutrition_products D8, health_food E8, other F8.
- **consultation.psychosocial_emotion** (multi, record `services.consultation.psychosocial_emotion`, anchor B10): emotional_support C10, disease_adaptation D10, family_communication E10, loss_grief F10, spiritual_care C11, other D11.
- **consultation.financial_social** (multi, record `services.consultation.financial_social`, anchor B12): financial_welfare C12, nutrition_subsidy D12, transportation_subsidy E12, housing_subsidy F12, insurance C13, school_work D13, rehab_supplies_aids E13, other F13.
- **consultation.care_support** (multi, record `services.consultation.care_support`, anchor B14): peer_experience C14, long_term_care D14, caregiver_support E14, relationship_social F14, discharge_planning C15, other D15.
- **supplies** (multi, record `services.supplies`, anchor A16): wig_hat B16, other_care_supplies C16, nutrition_products D16, other_equipment E16.
- **internal_referrals** (multi, record `services.internal_referrals`, anchor A17): wig_hat B17, other_care_supplies C17, social_welfare D17, peer_volunteer_group E17, psychology F17, nutrition B18, long_term_care C18, rehabilitation D18, care_information E18, other_activity F18.
- **external_referrals** (multi, record `services.external_referrals`, anchor A19): wig_hat B19, other_care_supplies C19, social_welfare D19, peer_volunteer_group E19, psychology F19, nutrition B20, long_term_care C20, rehabilitation D20, care_information E20, other_activity F20.
- **referral_outcomes** (multi, record `services.referral_outcomes`, anchor A21): received_wig_hat B21, received_other_supplies C21, received_financial_aid D21, received_service_help E21.
- **text fields**: service_date (record `service_date`, anchor A2); name (record `name`, anchor B23); medical_record_no (record `medical_record_no`, anchor B23); diagnosis_date (record `null`, anchor A24).

Section grouping: top = [service_date]; A `服務評估統計` = [the 6 consultation fields, supplies, internal_referrals, external_referrals, referral_outcomes]; B `綜合身份統計` = [identity, name, medical_record_no, diagnosis_date, gender, nationality, age]; C `病人基本資料統計` = [channel, disease_status, source, cancer, newly_diagnosed].

- [ ] **Step 1: Write failing content tests**

Add to `tests/test_form_layout.py`:

```python
def test_layout_covers_expected_fields():
    layout = service_record_layout()
    keys = {f.key for f in layout.iter_fields()}
    assert {"service_date", "identity", "name", "medical_record_no", "gender",
            "nationality", "age", "channel", "disease_status", "source", "cancer",
            "newly_diagnosed", "supplies", "internal_referrals", "external_referrals",
            "referral_outcomes"} <= keys
    assert "consultation.health_medical" in keys


def test_choice_option_counts_and_record_paths():
    layout = service_record_layout()
    assert len(layout.field_by_key("cancer").options) == 25
    assert len(layout.field_by_key("age").options) == 7
    assert layout.field_by_key("age").record_path == "patient_fields.age_group"
    assert layout.field_by_key("identity").record_path == "identity"
    assert layout.field_by_key("cancer").record_path == "patient_fields.cancers"
    assert layout.field_by_key("consultation.health_medical").record_path == "services.consultation.health_medical"
    assert layout.field_by_key("diagnosis_date").record_path is None


def test_option_codes_are_constants_legal():
    from ocr_from2xlsx import constants
    layout = service_record_layout()
    assert {o.code for _, o in layout.iter_options() if _.key == "identity"} <= constants.IDENTITIES
    assert {o.code for _, o in layout.iter_options() if _.key == "gender"} <= constants.GENDERS
    assert layout.options_by_code("cancer").keys() <= set(constants.CANCER_LABELS)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_form_layout.py -q -k "layout or codes or counts"`
Expected: FAIL (`service_record_layout` not defined).

- [ ] **Step 3: Implement `service_record_layout()`**

Append `service_record_layout()` to `src/ocr_from2xlsx/form_layout.py`, encoding the data above. Use this
shape (transcribe every field/option from the data tables; this snippet shows the exact pattern for two
representative fields — replicate it for ALL fields listed above):

```python
def _opts(*items: tuple[str, str, str]) -> tuple[Option, ...]:
    return tuple(Option(label=label, code=code, cell=cell) for label, code, cell in items)


def service_record_layout() -> FormLayout:
    top = Section(
        id="top",
        title="表頭",
        fields=(
            Field(key="service_date", title="服務年/月/日", kind="text",
                  record_path="service_date", anchor_cell="A2"),
        ),
    )
    section_b = Section(
        id="B",
        title="綜合身份統計",
        fields=(
            Field(key="identity", title="身分", kind="single_choice", record_path="identity",
                  anchor_cell="A23", options=_opts(
                      ("病人", "patient", "B23"),
                      ("親友及照顧者", "family_caregiver", "C23"),
                      ("一般民眾及其他", "public_other", "D23"))),
            Field(key="name", title="姓名", kind="text", record_path="name", anchor_cell="B23"),
            Field(key="medical_record_no", title="病歷號", kind="text",
                  record_path="medical_record_no", anchor_cell="B23"),
            Field(key="diagnosis_date", title="診斷日", kind="text", record_path=None, anchor_cell="A24"),
            Field(key="gender", title="性別", kind="single_choice", record_path="gender",
                  anchor_cell="A25", options=_opts(
                      ("女性", "female", "B25"), ("男性", "male", "B26"), ("其他", "other", "B27"))),
            # ... nationality, age (transcribe from the data tables above) ...
        ),
    )
    # ... build `top`, section A (consultation x6, supplies, internal/external referrals, outcomes),
    #     section_b (above), section C (channel, disease_status, source, cancer, newly_diagnosed) ...
    return FormLayout(template_id="service_record.v1", sections=(top, section_a, section_b, section_c))
```

Notes:
- `newly_diagnosed` is a single checkbox: model it as `kind="single_choice"` with one
  `Option(label="一年內新診斷個案", code="true", cell="A48")`. Consumers interpret a checked box as the
  Record boolean `patient_fields.newly_diagnosed_within_year = True`.
- Transcribe EVERY field/option from the Task 2 data tables — do not abbreviate. The Task 3 validation test
  will fail if any cell/label/code is wrong; fix the layout (never weaken the test).

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_form_layout.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/form_layout.py tests/test_form_layout.py
git commit -m "feat: add curated service-record form layout"
```

---

## Task 3: Model↔sheet two-way coverage validation

**Files:**
- Modify: `tests/test_form_layout.py`

- [ ] **Step 1: Write the validation test**

Add to `tests/test_form_layout.py`:

```python
import re
from pathlib import Path

import pytest

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover
    load_workbook = None

_XLSX = Path(__file__).resolve().parents[1] / "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"
_SHEET = "服務紀錄表"


def _sheet_cells() -> dict[str, str]:
    wb = load_workbook(_XLSX, read_only=True)
    try:
        ws = wb[_SHEET]
        cells: dict[str, str] = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value not in (None, ""):
                    cells[cell.coordinate] = str(cell.value)
        return cells
    finally:
        wb.close()


@pytest.mark.skipif(load_workbook is None or not _XLSX.is_file(),
                    reason="blank service-record xlsx / openpyxl not available")
def test_every_modeled_option_matches_its_sheet_cell():
    from ocr_from2xlsx.form_layout import service_record_layout

    cells = _sheet_cells()
    layout = service_record_layout()
    for fld, option in layout.iter_options():
        if option.cell == "A48":  # newly_diagnosed: the label lives in the section/row text
            continue
        text = cells.get(option.cell, "")
        # the bare label (sheet shows "□<label>"); match the label's core (drop leading "□"/number dot)
        core = re.sub(r"^[□\s]*", "", option.label)
        assert core[:3] in text or option.label in text, (
            f"{fld.key} option {option.code}: label {option.label!r} not found in cell "
            f"{option.cell}={text!r}"
        )


@pytest.mark.skipif(load_workbook is None or not _XLSX.is_file(),
                    reason="blank service-record xlsx / openpyxl not available")
def test_every_sheet_checkbox_option_is_modeled():
    from ocr_from2xlsx.form_layout import service_record_layout

    cells = _sheet_cells()
    modeled_cells = {o.cell for _, o in service_record_layout().iter_options()}
    # every cell whose text contains a checkbox glyph "□" must be represented in the model
    sheet_option_cells = {coord for coord, text in cells.items() if "□" in text}
    missing = sheet_option_cells - modeled_cells
    assert not missing, f"sheet checkbox cells not in model: {sorted(missing)}"
```

- [ ] **Step 2: Run to verify (it exercises the curated data)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_form_layout.py -q`
Expected: PASS. If `test_every_sheet_checkbox_option_is_modeled` reports missing cells, those are options
present on the sheet but absent from `service_record_layout()` — ADD them (correct the layout). If
`test_every_modeled_option_matches_its_sheet_cell` fails, a cell/label is wrong — fix the layout. NOTE: the
sheet has some `□` cells that are NOT per-record options (e.g. `B23` also holds 姓名/病歷號; gender 數量
columns C25/D25/C26/D26/C27/D27 are aggregate counts, not record options). For those aggregate-count cells,
exclude them by listing their coordinates in an explicit `_NON_OPTION_CHECKBOX_CELLS` set in the test with a
comment explaining each — do NOT model them as options and do NOT delete the test; document the exclusion.

- [ ] **Step 3: Commit**

```powershell
git add tests/test_form_layout.py
git commit -m "test: validate form layout against the real sheet"
```

---

## Task 4: Docs + policy

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: CHANGELOG** — under `## [Unreleased]` `### Added`:

```markdown
- 新增共用表單版面模型 `form_layout`（區塊/欄位/選項 + 代碼 + record_path），供確認 UI 與訓練資料產生器共用；附對照「服務紀錄表」分頁的雙向涵蓋驗證測試。
```

- [ ] **Step 2: Tests + policy**

```powershell
.venv\Scripts\python -W error -m pytest -q
.venv\Scripts\python build/package.py
python -m policy_check --repo .
```
Expected: all pass; policy 0 failures.

- [ ] **Step 3: Commit**

```powershell
git add CHANGELOG.md
git commit -m "docs: document shared form-layout model"
```

---

## Self-Review Notes

- **Spec coverage:** structured model (Task 1) ✓; full field/option/code + record_path (Task 2) ✓; reuse constants (Task 2 codes are constants codes) ✓; model↔sheet two-way coverage validation (Task 3) ✓; no geometry (none added) ✓; docs/policy (Task 4) ✓.
- **Type consistency:** `Option(label, code, cell)`, `Field(key, title, kind, record_path, anchor_cell, options)`, `Section(id, title, fields)`, `FormLayout(template_id, sections)` and accessors `iter_fields/field_by_key/iter_options/options_by_code` are used identically across tasks and tests.
- **Known curation risk (flag for implementer/reviewer):** the A-區 consultation/supplies/referrals/outcomes label↔code bindings are not present as a single dict in `constants.py`; Task 2 hand-binds them per the data tables. The Task 3 sheet test verifies label@cell and no-missing-options but cannot by itself prove each A-區 code is the semantically correct one for its label — the implementer/reviewer must confirm the A-區 code bindings against `constants.SERVICE_CATEGORIES`/`SUPPLY_CODES`/`RESOURCE_CODES`/`OUTCOME_CODES` membership and the Chinese labels. Fields backed by a constants label dict (identity/gender/nationality/age/channel/disease_status/source/cancer) can additionally be asserted code↔label against those dicts — add such assertions if practical.
- **Aggregate-count cells:** gender 數量 columns and the 病人/姓名 shared cell are `□`-bearing but not per-record options; Task 3 documents excluding them explicitly rather than modeling or deleting the test.
```
