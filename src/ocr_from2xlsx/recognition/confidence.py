"""Derive per-field confidence and review warnings from per-tile VLM results.

Output feeds ``OcrInfo.field_confidences`` and ``OcrInfo.warnings`` so the review
UI can mark unfilled / low-confidence fields visibly distinct. Pure logic.
"""
from __future__ import annotations

from typing import Any


def collect_confidence(
    tiles: list[dict[str, Any]], threshold: float = 0.6
) -> tuple[dict[str, float], list[str]]:
    field_conf: dict[str, float] = {}
    warnings: list[str] = []
    for tile in tiles:
        for entry in tile.get("options", []):
            if not entry.get("marked"):
                continue
            fid = entry.get("id", "")
            conf = _confidence(entry)
            field_conf[fid] = conf
            if conf < threshold:
                warnings.append(f"low-confidence:{fid}:{conf:.2f}")
        for entry in tile.get("values", []):
            fid = entry.get("id", "")
            if not (entry.get("text") or "").strip():
                warnings.append(f"empty:{fid}")
                continue
            conf = _confidence(entry)
            field_conf[fid] = conf
            if conf < threshold:
                warnings.append(f"low-confidence:{fid}:{conf:.2f}")
    return field_conf, warnings


def _confidence(entry: dict[str, Any]) -> float:
    # The model no longer emits confidence; absent => treat as high (not flagged).
    raw = entry.get("confidence")
    return 1.0 if raw is None else float(raw)
