"""Compose the local Vision-LLM recognition into an ``OcrBackend``.

``VisionOcrBackend.extract(page) -> dict`` returns a ``service_record.v1`` field
dict (same shape ``PluginOcrBackend`` returns; the prepare-records wrapper adds
record_id/source/review). The model call is injected as ``vlm_fn`` and the crop
step as ``tiler`` so the composition is unit-tested without a model or image.
"""
from __future__ import annotations

from typing import Any, Callable

from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED
from ocr_from2xlsx.preprocess import PreparedPage
from ocr_from2xlsx.recognition.confidence import collect_confidence
from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT, Section
from ocr_from2xlsx.recognition.mapping import apply_tile_result, empty_record_fields
from ocr_from2xlsx.recognition.name_mrn import parse_mrn, parse_name, snap_name

VlmFn = Callable[[str, Section], dict[str, Any]]
TilerFn = Callable[[str, tuple[Section, ...]], dict[str, str]]


class VisionOcrBackend:
    def __init__(
        self,
        vlm_fn: VlmFn,
        tiler: TilerFn,
        roster: list[str] | None = None,
        layout: tuple[Section, ...] = SERVICE_RECORD_V1_LAYOUT,
        model_name: str = "qwen3.5-vl-2b",
    ) -> None:
        self.vlm_fn = vlm_fn
        self.tiler = tiler
        self.roster = roster or []
        self.layout = layout
        self.model_name = model_name

    def extract(self, page: PreparedPage) -> dict[str, object]:
        crops = self.tiler(str(page.image_path), self.layout)
        fields = empty_record_fields()
        tiles: list[dict[str, Any]] = []
        name_text = ""
        mrn_text = ""
        for section in self.layout:
            crop = crops.get(section.key)
            if crop is None:
                continue
            result = self.vlm_fn(crop, section)
            tiles.append(result)
            apply_tile_result(fields, self.layout, result)
            for value in result.get("values", []):
                if value.get("id") == "name":
                    name_text = value.get("text") or ""
                elif value.get("id") == "medical_record_no":
                    mrn_text = value.get("text") or ""
        fields["name"] = snap_name(parse_name(name_text), self.roster)
        fields["medical_record_no"] = parse_mrn(mrn_text)
        field_conf, warnings = collect_confidence(tiles)
        if fields["name"]:
            warnings.append(NAME_UNCONFIRMED)
        fields["ocr"] = {
            "backend": "vision-llm",
            "model": self.model_name,
            "raw_text": "",
            "warnings": warnings,
            "field_confidences": field_conf,
        }
        return fields
