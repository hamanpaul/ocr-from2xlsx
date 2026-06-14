"""Bridge recognition warnings to review-form fields for highlighting.

The VLM warnings key fields by option/value id (e.g. ``identity.patient``); the
review form keys by record field path (e.g. ``identity``). This maps one to the
other via the layout so the UI can mark the right field. Pure logic.
"""
from __future__ import annotations

from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED
from ocr_from2xlsx.recognition.layout import Section


def _id_to_field(layout: tuple[Section, ...]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for section in layout:
        for option in section.options:
            mapping[option.id] = option.field
        for value in section.values:
            mapping[value.id] = value.field
    return mapping


def flagged_fields(warnings: list[str], layout: tuple[Section, ...]) -> dict[str, str]:
    """Map recognition warnings to ``{record_field: reason}`` for UI highlighting."""
    id_field = _id_to_field(layout)
    flags: dict[str, str] = {}
    for warning in warnings:
        if warning == NAME_UNCONFIRMED:
            flags["name"] = "unconfirmed"
        elif warning.startswith("low-confidence:"):
            field_id = warning.split(":")[1]
            flags[id_field.get(field_id, field_id)] = "low-confidence"
        elif warning.startswith("empty:"):
            field_id = warning.split(":", 1)[1]
            flags[id_field.get(field_id, field_id)] = "empty"
    return flags
