"""Build a configured ``VisionOcrBackend`` from host/model/rotate/roster.

The impure composition (Pillow tiler + Ollama client) lives here so
``recognition.backend`` stays model-free for its unit tests.
"""
from __future__ import annotations

import os
from pathlib import Path

from ocr_from2xlsx.recognition.backend import VisionOcrBackend
from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT, Section
from ocr_from2xlsx.recognition.llama_client import make_ollama_vlm_fn
from ocr_from2xlsx.recognition.tiling import crop_sections

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3-vl:2b"


def vision_config_from_env() -> tuple[str, str, int]:
    """Resolve (host, model, rotate) from env with sensible defaults."""
    host = os.environ.get("OCR_VLM_HOST") or DEFAULT_HOST
    model = os.environ.get("OCR_VLM_MODEL") or DEFAULT_MODEL
    try:
        rotate = int(os.environ.get("OCR_VLM_ROTATE") or 0)
    except ValueError:
        rotate = 0
    return host, model, rotate


def dewarp_from_env() -> bool:
    """Opt-in (#59): perspective-correct the form before tiling when ``OCR_VLM_DEWARP`` is
    truthy. Default off — enable after validating on real field photos, since a mis-detected
    quad on a cluttered photo could warp worse than the safe no-op fallback."""
    return (os.environ.get("OCR_VLM_DEWARP") or "").strip().lower() in {"1", "true", "yes", "on"}


def build_vision_ocr_backend(
    *,
    work_dir: str | os.PathLike[str],
    host: str = DEFAULT_HOST,
    model: str = DEFAULT_MODEL,
    rotate: int = 0,
    roster: list[str] | None = None,
    layout: tuple[Section, ...] = SERVICE_RECORD_V1_LAYOUT,
    correct_perspective: bool | None = None,
) -> VisionOcrBackend:
    work = Path(work_dir)
    dewarp = dewarp_from_env() if correct_perspective is None else correct_perspective

    def tiler(image_path: str, sections: tuple[Section, ...]) -> dict[str, str]:
        return crop_sections(image_path, sections, work, rotate=rotate, correct_perspective=dewarp)

    return VisionOcrBackend(
        vlm_fn=make_ollama_vlm_fn(host, model),
        tiler=tiler,
        roster=roster or [],
        layout=layout,
        model_name=model,
    )
