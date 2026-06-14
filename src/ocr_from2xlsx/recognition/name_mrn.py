"""Parse handwritten name / medical-record-no from a VLM tile value, and snap the
name to the local roster. Reuses ``name_roster.roster_match`` (DRY). Pure logic.
"""
from __future__ import annotations

import re

from ocr_from2xlsx.name_roster import roster_match

# A name is a run of 2-4 CJK characters; a medical-record-no is a run of >= 6 digits.
_CJK_RUN = re.compile(r"[㐀-鿿]{2,4}")
_DIGIT_RUN = re.compile(r"\d{6,}")


def parse_name(text: str) -> str:
    match = _CJK_RUN.search(text or "")
    return match.group(0) if match else ""


def parse_mrn(text: str) -> str:
    match = _DIGIT_RUN.search(text or "")
    return match.group(0) if match else ""


def snap_name(name: str, roster: list[str]) -> str:
    """Return the nearest confirmed roster name, or the input when none is close."""
    if not name:
        return name
    return roster_match(name, roster) or name
