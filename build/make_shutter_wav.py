# build/make_shutter_wav.py
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parents[1] / "src" / "ocr_from2xlsx" / "assets" / "shutter.wav"


def _click(samples: list[float], start_s: float, dur_s: float, amp: float, seed: int) -> None:
    rng = random.Random(seed)  # seeded → reproducible committed asset
    start = int(start_s * RATE)
    n = int(dur_s * RATE)
    for i in range(n):
        idx = start + i
        if idx >= len(samples):
            break
        env = math.exp(-i / (n * 0.25))  # fast mechanical decay
        noise = rng.random() * 2.0 - 1.0
        tone = math.sin(2 * math.pi * 2200 * i / RATE)
        samples[idx] += amp * env * (0.7 * noise + 0.3 * tone)


def main() -> int:
    total = int(0.22 * RATE)
    samples = [0.0] * total
    _click(samples, 0.00, 0.045, 0.9, seed=1)  # mirror-up click
    _click(samples, 0.11, 0.060, 1.0, seed=2)  # shutter click ("ka-chak")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        frames = bytearray()
        for value in samples:
            clamped = max(-1.0, min(1.0, value))
            frames += struct.pack("<h", int(clamped * 32767))
        handle.writeframes(bytes(frames))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
