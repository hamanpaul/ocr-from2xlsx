from __future__ import annotations

from typing import Any, Iterable

from ocr_from2xlsx.confirm_form import apply_form_state
from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.form_layout import FormLayout


def selection_to_record(
    layout: FormLayout,
    record_id: str,
    selection: dict[str, list[str]],
    text_values: dict[str, str],
) -> Record:
    record = Record.from_dict({"record_id": record_id})
    state: dict[str, Any] = {}

    for field in layout.iter_fields():
        if field.kind == "text":
            state[field.key] = text_values.get(field.key, "")
        elif field.kind == "single_choice":
            choices = selection.get(field.key, [])
            state[field.key] = choices[0] if choices else ""
        elif field.kind == "multi_choice":
            state[field.key] = set(selection.get(field.key, []))
        else:
            raise TypeError(f"Unsupported field kind: {field.kind!r}")

    apply_form_state(layout, record, state)
    return record


def build_answer_batch(
    records_with_images: Iterable[tuple[Record, str]],
    created_at: str,
    template_name: str = "service_record.v1",
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for record, source_image in records_with_images:
        payload = record.to_dict()
        payload["training"] = True
        payload["source_image"] = source_image
        records.append(payload)

    return {
        "schema_version": template_name,
        "source_batch": {
            "created_at": created_at,
            "source_type": "training_synthetic",
            "template_name": template_name,
        },
        "records": records,
    }
