from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.correction_store import load_corrections, roster_from_store
from ocr_from2xlsx.name_suggestion import confirm_name, suggest_name


class _FakeAgent:
    def __init__(self, value):
        self._value = value

    def suggest(self, crop_path):
        return self._value


def test_suggest_prefers_roster_match_over_agent():
    name, warnings = suggest_name(
        crop_path="x.png", agent=_FakeAgent("葉心女"), roster=["葉心安"], ocr_raw=""
    )
    assert name == "葉心安"
    assert "name.unconfirmed" in warnings


def test_suggest_uses_agent_when_no_roster_match():
    name, warnings = suggest_name(
        crop_path="x.png", agent=_FakeAgent("陳大文"), roster=["葉心安"], ocr_raw=""
    )
    assert name == "陳大文"
    assert "name.unconfirmed" in warnings


def test_suggest_uses_ocr_raw_when_agent_missing():
    name, warnings = suggest_name(
        crop_path="x.png", agent=_FakeAgent(None), roster=[], ocr_raw="王小明"
    )
    assert name == "王小明"
    assert "name.unconfirmed" in warnings


def test_suggest_empty_when_no_candidate_returns_no_warnings():
    name, warnings = suggest_name(
        crop_path="", agent=_FakeAgent(None), roster=[], ocr_raw=""
    )
    assert name == ""
    assert warnings == []


def test_confirm_name_writes_store_and_grows_roster(tmp_path: Path):
    store = tmp_path / "corrections.jsonl"
    roster = confirm_name(
        store_path=store,
        record_id="pdf-0001",
        final_value="葉心安",
        crop_path="pdf-0001-name.png",
        ocr_raw="",
        agent_suggestion="葉心女",
        roster_suggestion=None,
        source="for testing only.pdf#1",
        timestamp="2026-05-30T00:00:00+08:00",
    )
    assert "葉心安" in roster
    assert roster_from_store(store) == ["葉心安"]
    assert load_corrections(store)[0].final_value == "葉心安"
