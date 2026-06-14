"""Map per-tile VLM results into a ``service_record.v1`` field dict.

The dict shape matches what ``ocr_from2xlsx.domain.Record.from_dict`` consumes, so
the vision backend can build a record without any new schema. Pure logic — no
model, no image libraries.
"""
from __future__ import annotations

import re
from typing import Any

from ocr_from2xlsx.recognition.layout import Section

_DATE_SPLIT = re.compile(r"[^0-9]+")


def empty_record_fields() -> dict[str, Any]:
    """A blank ``service_record.v1`` field dict (no record_id/source/ocr yet)."""
    return {
        "service_date": "",
        "identity": "",
        "name": "",
        "medical_record_no": "",
        "gender": "",
        "patient_fields": {
            "nationality": None,
            "age_group": None,
            "channel": None,
            "disease_status": None,
            "source": None,
            "cancers": [],
            "newly_diagnosed_within_year": None,
        },
        "services": {
            "consultation": {},
            "supplies": [],
            "internal_referrals": [],
            "external_referrals": [],
            "referral_outcomes": [],
        },
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
    """Convert a ROC-calendar date like "114.06.25" to ISO "2025-06-25"."""
    parts = [p for p in _DATE_SPLIT.split(text or "") if p]
    if len(parts) >= 3:
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return ""
        return f"{year + 1911:04d}-{month:02d}-{day:02d}"
    return ""


def apply_tile_result(
    fields: dict[str, Any], layout: tuple[Section, ...], tile_json: dict[str, Any]
) -> None:
    """Fold one tile's ``{options, values}`` JSON into ``fields`` in place."""
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
            if not text:
                continue
        _set_dotted(fields, spec.field, text)
