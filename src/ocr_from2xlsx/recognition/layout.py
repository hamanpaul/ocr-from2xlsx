"""Recognition layout for the service-record form.

Each ``Option`` ties a checkbox to a record field + canonical code (codes match
``ocr_from2xlsx.constants`` so the workbook writer accepts them unchanged). Each
``ValueSpec`` ties a handwritten region to a field + parser. Section ``band``
fractions are best-guess for the fixed (IPEVO) upright layout and are tuned in
Phase 0 — tests assert behaviour derived from the config, never pixel values, so
tuning never breaks tests.

Section A consultation/supply/referral catalogs (the intricate "資源中心" grid,
including the nested ``services.consultation`` dict) are deferred to Phase 0 when
the form is readable at full resolution; constants currently expose those codes
as label-less sets, so v1 covers the fully-grounded Section B/C demographics,
identity/gender, dates, name and medical-record-no.
"""
from __future__ import annotations

from dataclasses import dataclass

from ocr_from2xlsx.constants import (
    AGE_GROUP_LABELS,
    CANCER_LABELS,
    CHANNEL_LABELS,
    DISEASE_STATUS_LABELS,
    GENDER_LABELS,
    IDENTITY_LABELS,
    NATIONALITY_LABELS,
    SOURCE_LABELS,
)


@dataclass(frozen=True, slots=True)
class Option:
    id: str
    label: str
    field: str  # dotted target, e.g. "identity" or "patient_fields.cancers"
    code: str  # value written when the box is marked
    kind: str = "single"  # "single" (one per field) or "multi" (list field)


@dataclass(frozen=True, slots=True)
class ValueSpec:
    id: str
    field: str
    parser: str  # "date" | "int" | "name" | "mrn"


@dataclass(frozen=True, slots=True)
class Section:
    key: str
    band: tuple[float, float, float, float]  # x0, y0, x1, y1 in 0..1
    options: tuple[Option, ...] = ()
    values: tuple[ValueSpec, ...] = ()


def band_pixels(
    band: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    """Scale 0..1 band fractions to integer pixel coordinates."""
    x0, y0, x1, y1 = band
    return (int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height))


def _options(prefix: str, field: str, labels: dict[str, str], kind: str = "single") -> tuple[Option, ...]:
    return tuple(Option(f"{prefix}.{code}", label, field, code, kind) for code, label in labels.items())


_CANCER_ITEMS = list(CANCER_LABELS.items())  # ordered by code, 1..25


def _cancer_column(column: int) -> tuple[Option, ...]:
    # The 癌別 grid is a row-major 5x5: column c (1..5) holds cancers c, c+5, c+10, c+15, c+20.
    # Splitting the full-width grid into per-column crops gives the small VLM enough resolution.
    indices = [column - 1 + 5 * row for row in range(5)]
    return tuple(
        Option(f"cancer.{code}", label, "patient_fields.cancers", code, "multi")
        for code, label in (_CANCER_ITEMS[i] for i in indices)
    )


# Bands calibrated against output/reg/filled_upright.png (upright 2448x3264) in
# Phase 0 by cropping + inspecting each region. Section groupings follow the
# physical layout: the 身分 row spans full width; 性別/國籍/年齡 stack in a narrow
# left column; 管道/疾病狀態/來源 sit in Section C above the 癌別 grid.
SERVICE_RECORD_V1_LAYOUT: tuple[Section, ...] = (
    Section(
        "service_date",
        (0.0, 0.02, 0.45, 0.09),
        values=(ValueSpec("service_date", "service_date", "date"),),
    ),
    Section(
        "identity",
        (0.0, 0.40, 1.0, 0.47),
        options=_options("identity", "identity", IDENTITY_LABELS),
    ),
    Section(
        "name_mrn",
        (0.13, 0.40, 0.45, 0.47),
        values=(
            ValueSpec("name", "name", "name"),
            ValueSpec("medical_record_no", "medical_record_no", "mrn"),
        ),
    ),
    Section(
        "gender_nationality_age",
        (0.04, 0.47, 0.37, 0.66),
        options=(
            *_options("gender", "gender", GENDER_LABELS),
            *_options("nationality", "patient_fields.nationality", NATIONALITY_LABELS),
            *_options("age_group", "patient_fields.age_group", AGE_GROUP_LABELS),
        ),
    ),
    Section(
        "patient_status",
        (0.0, 0.655, 0.82, 0.745),
        options=(
            *_options("channel", "patient_fields.channel", CHANNEL_LABELS),
            *_options("disease_status", "patient_fields.disease_status", DISEASE_STATUS_LABELS),
            *_options("source", "patient_fields.source", SOURCE_LABELS),
        ),
    ),
    # 癌別 grid split into 5 per-column crops (row-major 5x5) — the full-width
    # crop was too wide for the 2B model; narrow columns restore the resolution.
    Section("cancers_c1", (0.13, 0.735, 0.274, 0.875), options=_cancer_column(1)),
    Section("cancers_c2", (0.274, 0.735, 0.418, 0.875), options=_cancer_column(2)),
    Section("cancers_c3", (0.418, 0.735, 0.562, 0.875), options=_cancer_column(3)),
    Section("cancers_c4", (0.562, 0.735, 0.706, 0.875), options=_cancer_column(4)),
    Section("cancers_c5", (0.706, 0.735, 0.85, 0.875), options=_cancer_column(5)),
)


# --- Section A 服務評估統計 (consultation grid) ----------------------------------
# Labels/codes are reused from form_layout (the review-UI source of truth) so they
# never drift. Each consultation category is one full-width row; bands calibrated
# against filled_upright.png. supplies / referrals / outcomes rows are a follow-up.
_SECTION_A_BANDS: dict[str, tuple[float, float, float, float]] = {
    "services.consultation.health_medical": (0.13, 0.138, 1.0, 0.168),
    "services.consultation.symptom_side_effect": (0.13, 0.168, 1.0, 0.196),
    "services.consultation.nutrition_diet": (0.13, 0.196, 1.0, 0.216),
    "services.consultation.psychosocial_emotion": (0.13, 0.216, 1.0, 0.246),
    "services.consultation.financial_social": (0.13, 0.246, 1.0, 0.278),
    "services.consultation.care_support": (0.13, 0.288, 1.0, 0.318),
    "services.supplies": (0.13, 0.322, 1.0, 0.344),
    "services.internal_referrals": (0.13, 0.344, 1.0, 0.376),
    "services.external_referrals": (0.13, 0.376, 1.0, 0.399),
    "services.referral_outcomes": (0.13, 0.399, 1.0, 0.420),
}


def _section_a_sections() -> tuple[Section, ...]:
    from ocr_from2xlsx.form_layout import service_record_layout

    section_a = next(s for s in service_record_layout().sections if s.id == "A")
    sections: list[Section] = []
    for field in section_a.fields:
        band = _SECTION_A_BANDS.get(field.record_path or "")
        if band is None:
            continue
        options = tuple(
            Option(f"{field.key}.{opt.code}", opt.label, field.record_path, opt.code, "multi")
            for opt in field.options
        )
        sections.append(Section(field.key.replace(".", "_"), band, options=options))
    return tuple(sections)


SERVICE_RECORD_V1_LAYOUT = SERVICE_RECORD_V1_LAYOUT + _section_a_sections()
