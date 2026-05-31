"""Round-trip a Record <-> a Tkinter-free form-state using form_layout + record_access."""
from __future__ import annotations

from typing import Any

from ocr_from2xlsx.form_layout import FormLayout
from ocr_from2xlsx.record_access import get_by_path, set_by_path

_BOOL_TRUE_CODE = "true"
_NEWLY_DIAGNOSED_PATH = "patient_fields.newly_diagnosed_within_year"


def _is_bool_field(record_path: str | None) -> bool:
    return record_path == _NEWLY_DIAGNOSED_PATH


def record_to_form_state(layout: FormLayout, record: Any) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for field in layout.iter_fields():
        value = get_by_path(record, field.record_path)
        if field.kind == "text":
            state[field.key] = "" if value is None else str(value)
        elif field.kind == "multi_choice":
            state[field.key] = set(value or [])
        elif field.kind == "single_choice":
            if _is_bool_field(field.record_path):
                state[field.key] = _BOOL_TRUE_CODE if value is True else ""
            else:
                state[field.key] = "" if value is None else str(value)
        else:
            raise TypeError(f"Unsupported field kind: {field.kind!r}")
    return state


def apply_form_state(layout: FormLayout, record: Any, state: dict[str, Any]) -> None:
    for field in layout.iter_fields():
        if field.key not in state or field.record_path is None:
            continue

        value = state[field.key]
        if field.kind == "text":
            set_by_path(record, field.record_path, "" if value is None else str(value))
        elif field.kind == "multi_choice":
            if not isinstance(value, set):
                raise TypeError(f"multi_choice field {field.key!r} must be set[str]")
            set_by_path(record, field.record_path, sorted(value))
        elif field.kind == "single_choice":
            if _is_bool_field(field.record_path):
                set_by_path(record, field.record_path, value == _BOOL_TRUE_CODE)
            else:
                set_by_path(record, field.record_path, "" if value is None else str(value))
        else:
            raise TypeError(f"Unsupported field kind: {field.kind!r}")
