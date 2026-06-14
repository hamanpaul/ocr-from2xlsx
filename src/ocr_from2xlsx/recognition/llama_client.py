"""Local Ollama-compatible VLM client.

``make_ollama_vlm_fn`` returns a ``vlm_fn(crop_path, section) -> tile_json`` that
POSTs the crop + a schema-guided prompt to ``/api/chat`` and parses the JSON
reply. Any failure (no server, timeout, bad JSON) degrades to an empty result so
recognition never crashes the run. The HTTP POST is injectable for tests.
"""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ocr_from2xlsx.recognition.layout import Section

PostFn = Callable[[str, dict[str, Any]], dict[str, Any]]


def build_section_prompt(section: Section) -> str:
    lines = [
        "You are reading ONE cropped section of a Taiwanese cancer-resource-center service form.",
        "For each option id, decide whether its checkbox is marked (a tick, cross, or fill).",
        "Also read each handwritten value exactly as written.",
        'Return ONLY JSON: {"options":[{"id":"...","marked":true,"confidence":0.0}],'
        '"values":[{"id":"...","text":"...","confidence":0.0}]}',
    ]
    if section.options:
        lines.append("Options:")
        lines.extend(f"  {opt.id} = {opt.label}" for opt in section.options)
    if section.values:
        lines.append("Values:")
        lines.extend(f"  {value.id} ({value.parser})" for value in section.values)
    return "\n".join(lines)


def _default_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def make_ollama_vlm_fn(
    host: str, model: str, *, post_fn: PostFn = _default_post
) -> Callable[[str, Section], dict[str, Any]]:
    url = host.rstrip("/") + "/api/chat"

    def vlm_fn(crop_path: str, section: Section) -> dict[str, Any]:
        try:
            image_b64 = base64.b64encode(Path(crop_path).read_bytes()).decode("ascii")
            payload = {
                "model": model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "user", "content": build_section_prompt(section), "images": [image_b64]}
                ],
            }
            body = post_fn(url, payload)
            result = json.loads(body.get("message", {}).get("content", "{}"))
            if not isinstance(result, dict):
                return {"options": [], "values": []}
            result.setdefault("options", [])
            result.setdefault("values", [])
            return result
        except Exception:  # noqa: BLE001 - degrade on any client/parse error
            return {"options": [], "values": []}

    return vlm_fn
