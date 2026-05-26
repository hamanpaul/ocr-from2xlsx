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
