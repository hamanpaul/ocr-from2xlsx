"""Plugin-safe crop providers for checkbox mark regions."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Region = list[list[int]]
CropMap = dict[tuple[str, str], Region]


class CropProvider(Protocol):
    def crop(self, image: object) -> CropMap:
        """Return grayscale crops keyed by ``(field, code)``."""


@dataclass(frozen=True, slots=True)
class _TemplateBox:
    field: str
    code: str
    box: tuple[float, float, float, float]


def _load_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"unable to read template boxes JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid template boxes JSON: {exc.msg}") from exc


def _validate_box(raw: Any, index: int) -> tuple[float, float, float, float]:
    if not isinstance(raw, list | tuple) or len(raw) != 4:
        raise ValueError(f"boxes[{index}].box must contain exactly four numbers")
    try:
        x0, y0, x1, y1 = (float(value) for value in raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"boxes[{index}].box must contain only numbers") from exc
    if not all(math.isfinite(value) for value in (x0, y0, x1, y1)):
        raise ValueError(f"boxes[{index}].box must contain finite numbers")
    if min(x0, y0, x1, y1) < 0:
        raise ValueError(f"boxes[{index}].box coordinates must be non-negative")
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"boxes[{index}].box coordinates must be strictly increasing")
    return (x0, y0, x1, y1)


def _validate_template(data: Any) -> tuple[str, tuple[_TemplateBox, ...]]:
    if not isinstance(data, dict):
        raise ValueError("template boxes JSON must be an object")
    template_id = data.get("template_id")
    if not isinstance(template_id, str) or not template_id:
        raise ValueError("template boxes JSON must contain a non-empty template_id")
    boxes = data.get("boxes")
    if not isinstance(boxes, list):
        raise ValueError("template boxes JSON must contain a boxes list")

    parsed: list[_TemplateBox] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(boxes):
        if not isinstance(item, dict):
            raise ValueError(f"boxes[{index}] must be an object")
        field = item.get("field")
        code = item.get("code")
        if not isinstance(field, str) or not field:
            raise ValueError(f"boxes[{index}].field must be a non-empty string")
        if not isinstance(code, str) or not code:
            raise ValueError(f"boxes[{index}].code must be a non-empty string")
        key = (field, code)
        if key in seen:
            raise ValueError(f"duplicate template box for {field}.{code}")
        seen.add(key)
        parsed.append(_TemplateBox(field=field, code=code, box=_validate_box(item.get("box"), index)))
    return template_id, tuple(parsed)


def _open_grayscale_image(image: object) -> Any:
    if isinstance(image, str | Path):
        from PIL import Image

        with Image.open(image) as source:
            return source.convert("L")
    if hasattr(image, "convert"):
        return image.convert("L")
    return image


def _region_from_crop(crop: Any) -> Region:
    width, height = crop.size
    pixel_iter = crop.get_flattened_data() if hasattr(crop, "get_flattened_data") else crop.getdata()
    data = list(pixel_iter)
    return [
        [int(data[y * width + x]) for x in range(width)]
        for y in range(height)
    ]


class GeometryCropProvider:
    """Crop fixed template boxes from an already-aligned image."""

    def __init__(self, template_boxes_path: str | Path) -> None:
        self.template_boxes_path = Path(template_boxes_path)
        self.template_id, self.boxes = _validate_template(_load_json(self.template_boxes_path))

    def crop(self, image: object) -> CropMap:
        gray = _open_grayscale_image(image)
        width, height = gray.size
        crops: CropMap = {}
        for item in self.boxes:
            x0, y0, x1, y1 = item.box
            pixel_box = (
                int(math.floor(x0)),
                int(math.floor(y0)),
                int(math.ceil(x1)),
                int(math.ceil(y1)),
            )
            if pixel_box[0] < 0 or pixel_box[1] < 0 or pixel_box[2] > width or pixel_box[3] > height:
                raise ValueError(
                    f"template box for {item.field}.{item.code} is outside image bounds "
                    f"{(width, height)}: {pixel_box}"
                )
            crops[(item.field, item.code)] = _region_from_crop(gray.crop(pixel_box))
        return crops
