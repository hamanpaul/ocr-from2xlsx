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
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.preprocess import PreparedPage
from ocr_from2xlsx.recognition.backend import VisionOcrBackend
from ocr_from2xlsx.recognition.layout import Section
from ocr_from2xlsx.recognition.llama_client import make_ollama_vlm_fn
from ocr_from2xlsx.recognition.tiling import crop_sections


def _timed(vlm_fn: Callable[[str, Section], dict], timing: list[tuple[str, float]]):
    def wrapped(crop_path: str, section: Section) -> dict[str, Any]:
        start = time.perf_counter()
        result = vlm_fn(crop_path, section)
        timing.append((section.key, time.perf_counter() - start))
        return result

    return wrapped


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
        vlm_fn=_timed(make_ollama_vlm_fn(args.host, args.model), timing),
        tiler=lambda image_path, layout: crop_sections(image_path, layout, out_dir, rotate=args.rotate),
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
