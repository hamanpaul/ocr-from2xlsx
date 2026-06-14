"""Local Ollama-compatible VLM client.

``make_ollama_vlm_fn`` returns a ``vlm_fn(crop_path, section) -> tile_json`` that
POSTs the crop + a terse, schema-guided prompt to ``/api/chat`` and parses the
JSON reply. Two empirical lessons from Phase 0 with a 2B model drive the design:

* Keep the prompt terse — verbose preambles / confidence fields make the small
  model return an empty template.
* Keep each call to at most ``MAX_OPTIONS_PER_CALL`` options — longer option lists
  make the model return empty. Large sections are chunked over the same crop.

Options and handwritten values are asked separately. Any failure (no server,
timeout, bad JSON) degrades to an empty result so recognition never crashes.
The HTTP POST is injectable for tests.
"""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ocr_from2xlsx.recognition.layout import Option, Section, ValueSpec

PostFn = Callable[[str, dict[str, Any]], dict[str, Any]]

MAX_OPTIONS_PER_CALL = 12


def build_options_prompt(options: tuple[Option, ...]) -> str:
    lines = [
        "For each option, is its checkbox ticked/marked on the form?",
        'Return ONLY JSON: {"options":[{"id":"<id>","marked":true_or_false}]}.',
        "Options:",
    ]
    lines.extend(f"  {opt.id} = {opt.label}" for opt in options)
    return "\n".join(lines)


def build_values_prompt(values: tuple[ValueSpec, ...]) -> str:
    lines = [
        "Read each handwritten field from the form exactly as written.",
        'Return ONLY JSON: {"values":[{"id":"<id>","text":"<text, empty string if blank>"}]}.',
        "Fields:",
    ]
    lines.extend(f"  {value.id} ({value.parser})" for value in values)
    return "\n".join(lines)


def _default_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def make_ollama_vlm_fn(
    host: str, model: str, *, post_fn: PostFn = _default_post
) -> Callable[[str, Section], dict[str, Any]]:
    url = host.rstrip("/") + "/api/chat"

    def _ask(image_b64: str, prompt: str) -> dict[str, Any]:
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        }
        body = post_fn(url, payload)
        parsed = json.loads(body.get("message", {}).get("content", "") or "{}")
        return parsed if isinstance(parsed, dict) else {}

    def vlm_fn(crop_path: str, section: Section) -> dict[str, Any]:
        result: dict[str, Any] = {"options": [], "values": []}
        try:
            image_b64 = base64.b64encode(Path(crop_path).read_bytes()).decode("ascii")
            for chunk in _chunks(list(section.options), MAX_OPTIONS_PER_CALL):
                parsed = _ask(image_b64, build_options_prompt(tuple(chunk)))
                result["options"].extend(parsed.get("options", []) or [])
            if section.values:
                parsed = _ask(image_b64, build_values_prompt(section.values))
                result["values"].extend(parsed.get("values", []) or [])
        except Exception:  # noqa: BLE001 - degrade on any client/parse error
            return {"options": [], "values": []}
        return result

    return vlm_fn
