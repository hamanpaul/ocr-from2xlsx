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
    Section(
        "cancers",
        (0.0, 0.74, 1.0, 0.87),
        options=_options("cancer", "patient_fields.cancers", CANCER_LABELS, kind="multi"),
    ),
)
