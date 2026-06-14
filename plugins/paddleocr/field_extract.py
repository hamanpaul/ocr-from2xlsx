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
# A run of 6+ consecutive digits (handwritten pure-numeric MRN).
_DIGIT_RUN = re.compile(r"\d{6,}")
# Fragments that mark a line as form chrome (identity checkboxes, labels) rather than a value.
_NAME_NOISE = ("□", "病人", "親友", "照顧者", "民眾", "病歷號", "姓名", "數量")
_NAME_ROW_TOLERANCE = 15
_MRN_ABOVE_TOLERANCE = 70
IDENTITY_BY_LABEL = {
    "病人": "patient",
    "親友及照顧者": "family_caregiver",
    "一般民眾及其他": "public_other",
}
GENDER_BY_LABEL = {
    "女性": "female",
    "男性": "male",
}


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


def _find_name_anchor(lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _find_anchor(lines, _NAME_ANCHOR)


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


def _name_from_candidates(texts: list[str]) -> str | None:
    best = ""
    for text in texts:
        if any(token in text for token in _NAME_NOISE):
            continue
        cjk = "".join(ch for ch in text if _has_cjk(ch))
        if len(cjk) < 2:
            continue
        if len(cjk) > len(best):
            best = cjk
    return best or None


def _mrn_from_candidates(texts: list[str]) -> str | None:
    best = ""
    for text in texts:
        candidates = list(_DIGIT_RUN.findall(text))
        token = _MRN_TOKEN.search(text)
        if token:
            candidates.append(token.group(0))
        for run in candidates:
            if len(run) > len(best):
                best = run
    return best or None


def _resolve_choice(marked_labels, mapping):
    for label, code in mapping.items():
        if label in marked_labels:
            return code
    return ""


def extract_identity(marked_labels) -> str:
    return _resolve_choice(marked_labels or set(), IDENTITY_BY_LABEL)


def extract_gender(marked_labels) -> str:
    return _resolve_choice(marked_labels or set(), GENDER_BY_LABEL)


def extract_name_anchor(lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    anchor = _find_name_anchor(lines)
    if anchor is None:
        return None
    return {
        "text": str(anchor.get("text") or ""),
        "box": [[float(pt[0]), float(pt[1])] for pt in anchor["box"]],
    }


def extract_name_and_mrn(lines: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    anchor = _find_name_anchor(lines)
    if anchor is None:
        return (None, None)
    ax, ay = _center(anchor["box"])
    name_texts = []
    mrn_texts = []
    for line in lines:
        if line is anchor:
            continue
        cx, cy = _center(line["box"])
        if cx <= ax:
            continue
        text = str(line.get("text") or "")
        if abs(cy - ay) <= _NAME_ROW_TOLERANCE:
            name_texts.append(text)
            mrn_texts.append(text)
            continue
        if ay - _MRN_ABOVE_TOLERANCE <= cy < ay:
            mrn_texts.append(text)
    return (_name_from_candidates(name_texts), _mrn_from_candidates(mrn_texts))


def extract_fields(lines: list[dict[str, Any]], marked_labels=None) -> dict[str, Any]:
    name, mrn = extract_name_and_mrn(lines)
    return {
        "service_date": extract_service_date(lines),
        "name": name,
        "medical_record_no": mrn,
        "identity": extract_identity(marked_labels),
        "gender": extract_gender(marked_labels),
        "name_anchor": extract_name_anchor(lines),
    }
