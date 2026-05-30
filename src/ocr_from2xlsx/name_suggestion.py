"""Pure orchestration of name suggestion and confirmation write-back."""
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.correction_store import Correction, append_correction, roster_from_store
from ocr_from2xlsx.name_agent import NameAgent
from ocr_from2xlsx.name_roster import roster_match

NAME_UNCONFIRMED = "name.unconfirmed"


def suggest_name(
    crop_path: str,
    agent: NameAgent,
    roster: list[str],
    ocr_raw: str = "",
) -> tuple[str, list[str]]:
    """Return (suggested_name, warnings). Never treats the name as confirmed."""
    agent_value = agent.suggest(crop_path) if crop_path else None
    candidate = (agent_value or ocr_raw or "").strip()
    match = roster_match(candidate, roster) if candidate else None
    name = match or (agent_value or "").strip()
    return (name, [NAME_UNCONFIRMED])


def confirm_name(
    store_path: Path | str,
    record_id: str,
    final_value: str,
    *,
    crop_path: str | None = None,
    ocr_raw: str = "",
    agent_suggestion: str | None = None,
    roster_suggestion: str | None = None,
    source: str = "",
    timestamp: str = "",
) -> list[str]:
    """Persist a human confirmation/correction and return the updated roster."""
    append_correction(
        store_path,
        Correction(
            field="name",
            final_value=final_value,
            record_id=record_id,
            crop_path=crop_path,
            ocr_raw=ocr_raw,
            agent_suggestion=agent_suggestion,
            roster_suggestion=roster_suggestion,
            source=source,
            timestamp=timestamp,
        ),
    )
    return roster_from_store(store_path)
