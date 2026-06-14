"""Phase 0 bake-off harness for the offline VLM recognition.

A manual spike (NOT production code) to choose the model / band fractions / prompt
on real hardware. It crops the layout's section bands from a captured form, sends
each crop to a local Ollama-compatible server, assembles the service_record.v1 via
the pure recognition core, and prints the record plus per-section + total latency.

Design: docs/superpowers/specs/2026-06-14-offline-vlm-assisted-recognition-design.md

Usage (needs a local Ollama running, e.g. `ollama serve` + `ollama pull qwen2.5vl:3b`):

    .venv/Scripts/python.exe build/phase0_vlm_bakeoff.py \\
        --image output/reg/filled_cam.png --rotate 90 --model qwen2.5vl:3b

Try several --model values and record per-section accuracy (vs a hand label) and
latency into the spec's Phase 0 section. --rotate turns the sideways camera image
upright (90 = clockwise quarter turn).
"""
from __future__ import annotations

import argparse
import base64
import json
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.preprocess import PreparedPage
from ocr_from2xlsx.recognition.backend import VisionOcrBackend
from ocr_from2xlsx.recognition.layout import Section, band_pixels


def make_tiler(rotate: int, out_dir: Path):
    def tiler(image_path: str, layout: tuple[Section, ...]) -> dict[str, str]:
        image = Image.open(image_path).convert("RGB")
        if rotate:
            image = image.rotate(-rotate, expand=True)  # PIL rotates CCW; negate for clockwise
        width, height = image.size
        crops: dict[str, str] = {}
        for section in layout:
            crop_path = out_dir / f"{section.key}.png"
            image.crop(band_pixels(section.band, width, height)).save(crop_path)
            crops[section.key] = str(crop_path)
        return crops

    return tiler


def build_prompt(section: Section) -> str:
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


def make_vlm_fn(host: str, model: str, timing: list[tuple[str, float]]):
    url = host.rstrip("/") + "/api/chat"

    def vlm_fn(crop_path: str, section: Section) -> dict:
        image_b64 = base64.b64encode(Path(crop_path).read_bytes()).decode("ascii")
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "messages": [{"role": "user", "content": build_prompt(section), "images": [image_b64]}],
        }
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                body = json.loads(response.read().decode("utf-8"))
            result = json.loads(body.get("message", {}).get("content", "{}"))
            if not isinstance(result, dict):
                result = {"options": [], "values": []}
        except Exception as exc:  # noqa: BLE001 - spike: degrade, never crash the run
            print(f"  [warn] {section.key}: {exc}")
            result = {"options": [], "values": []}
        timing.append((section.key, time.perf_counter() - start))
        return result

    return vlm_fn


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 VLM recognition bake-off")
    parser.add_argument("--image", required=True, help="captured form image")
    parser.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270])
    parser.add_argument("--model", default="qwen2.5vl:3b", help="Ollama model tag")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--roster", default="", help="comma-separated confirmed names")
    args = parser.parse_args()

    out_dir = Path(tempfile.mkdtemp(prefix="phase0_"))
    roster = [name for name in args.roster.split(",") if name]
    timing: list[tuple[str, float]] = []
    backend = VisionOcrBackend(
        vlm_fn=make_vlm_fn(args.host, args.model, timing),
        tiler=make_tiler(args.rotate, out_dir),
        roster=roster,
        model_name=args.model,
    )
    page = PreparedPage(
        image_path=Path(args.image),
        source=SourceInfo(document_path=args.image, page_number=1),
        template_id="service_record.v1",
    )

    start = time.perf_counter()
    record = backend.extract(page)
    total = time.perf_counter() - start

    print(json.dumps(record, ensure_ascii=False, indent=2))
    print("\n--- latency ---")
    for key, seconds in timing:
        print(f"  {key:24s} {seconds:6.1f}s")
    print(f"  {'TOTAL':24s} {total:6.1f}s")
    print(f"\nsection crops written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
