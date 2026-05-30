"""Pure, dependency-free field extraction from PaddleOCR full-page results.

An OCR line is a dict: {"text": str, "box": [[x, y], [x, y], [x, y], [x, y]]}.
Only text and box centers are used, so this module is unit-testable without PaddleOCR.
"""
from __future__ import annotations

import re
from typing import Any

_ROC_DATE = re.compile(r"(\d{2,3})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})")
# Fallback for OCR that merges month+day into one 4-digit run, e.g. "114、0625".
_ROC_DATE_MMDD = re.compile(r"(\d{2,3})\D{1,3}(\d{2})(\d{2})(?!\d)")
_DATE_ANCHOR = ("服務年", "年/月/日", "年月日")
_NAME_ANCHOR = "姓名"
# A medical-record-no token: >=4 chars of letters/digits/hyphen, must contain at least one digit.
_MRN_TOKEN = re.compile(r"(?=[A-Za-z0-9\-]{4,})[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*")
# Fragments that mark a line as form chrome (identity checkboxes, labels) rather than a value.
_NAME_NOISE = ("□", "病人", "親友", "照顧者", "民眾", "病歷號", "姓名", "數量")


def _has_cjk(text: str) -> bool:
    return any(0x4E00 <= ord(ch) <= 0x9FFF for ch in text)


def normalize_roc_date(text: str) -> str | None:
    """Convert a ROC-calendar date string to ISO format (YYYY-MM-DD).

    Day is validated as 1..31 without per-month or leap-year checks (v1 simplification).
    """
    match = _ROC_DATE.search(text or "") or _ROC_DATE_MMDD.search(text or "")
    if not match:
        return None
    roc_year, month, day = (int(part) for part in match.groups())
    year = roc_year + 1911
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _center(box: list[list[float]]) -> tuple[float, float]:
    xs = [pt[0] for pt in box]
    ys = [pt[1] for pt in box]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _find_anchor(lines: list[dict[str, Any]], needles: tuple[str, ...] | str):
    needle_tuple = (needles,) if isinstance(needles, str) else needles
    for line in lines:
        text = str(line.get("text") or "")
        if any(needle in text for needle in needle_tuple):
            return line
    return None


def extract_service_date(lines: list[dict[str, Any]]) -> str | None:
    """Return the service date as ISO YYYY-MM-DD, or None if not found.

    Assumes the date value and its label land on the same OCR line (true for
    high-confidence scans); returns None for human review otherwise.
    """
    anchor = _find_anchor(lines, _DATE_ANCHOR)
    if anchor is None:
        return None
    return normalize_roc_date(str(anchor.get("text") or ""))


def _name_mrn_from_value(value: str) -> tuple[str | None, str | None]:
    value = value.strip()
    if not value or any(token in value for token in _NAME_NOISE):
        return (None, None)
    mrn_match = _MRN_TOKEN.search(value)
    mrn = mrn_match.group(0) if mrn_match else None
    name = value.replace(mrn, "").strip() if mrn else value
    # Only accept a value that carries a medical-record-no or a plausibly-CJK name;
    # this rejects stray single marks (e.g. an OCR'd checkmark "V") on the same row.
    if not mrn and not _has_cjk(name):
        return (None, None)
    return (name or None, mrn)


def extract_name_and_mrn(lines: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    anchor = _find_anchor(lines, _NAME_ANCHOR)
    if anchor is None:
        return (None, None)
    ax, ay = _center(anchor["box"])
    candidates = []
    for line in lines:
        if line is anchor:
            continue
        cx, cy = _center(line["box"])
        if cx > ax and abs(cy - ay) <= 15:
            candidates.append((cx, str(line.get("text") or "")))
    candidates.sort(key=lambda item: item[0])
    for _, value in candidates:
        name, mrn = _name_mrn_from_value(value)
        if name or mrn:
            return (name, mrn)
    return (None, None)


def extract_fields(lines: list[dict[str, Any]]) -> dict[str, Any]:
    name, mrn = extract_name_and_mrn(lines)
    return {
        "service_date": extract_service_date(lines),
        "name": name,
        "medical_record_no": mrn,
    }
