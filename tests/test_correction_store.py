from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.correction_store import (
    Correction,
    append_correction,
    load_corrections,
    roster_from_store,
)


def _correction(value: str, record_id: str) -> Correction:
    return Correction(
        field="name",
        final_value=value,
        record_id=record_id,
        crop_path=f"{record_id}-name.png",
        ocr_raw="",
        agent_suggestion="葉心女",
        roster_suggestion=None,
        source="for testing only.pdf#1",
        timestamp="2026-05-30T00:00:00+08:00",
    )


def test_append_and_load_round_trip(tmp_path: Path):
    store = tmp_path / "corrections.jsonl"
    append_correction(store, _correction("葉心安", "pdf-0001"))
    append_correction(store, _correction("王小明", "pdf-0002"))

    loaded = load_corrections(store)

    assert [c.final_value for c in loaded] == ["葉心安", "王小明"]
    assert loaded[0].agent_suggestion == "葉心女"


def test_roster_from_store_returns_distinct_names(tmp_path: Path):
    store = tmp_path / "corrections.jsonl"
    append_correction(store, _correction("葉心安", "pdf-0001"))
    append_correction(store, _correction("葉心安", "pdf-0003"))
    append_correction(store, _correction("王小明", "pdf-0002"))

    assert sorted(roster_from_store(store)) == ["王小明", "葉心安"]


def test_load_missing_store_returns_empty(tmp_path: Path):
    assert load_corrections(tmp_path / "nope.jsonl") == []
    assert roster_from_store(tmp_path / "nope.jsonl") == []


def test_load_ignores_unknown_json_keys(tmp_path: Path):
    store = tmp_path / "corrections.jsonl"
    store.write_text(
        (
            '{"field":"name","final_value":"葉心安","record_id":"pdf-0001",'
            '"crop_path":"pdf-0001-name.png","ocr_raw":"","agent_suggestion":"葉心女",'
            '"roster_suggestion":null,"source":"for testing only.pdf#1",'
            '"timestamp":"2026-05-30T00:00:00+08:00","extra":"ignored"}\n'
        ),
        encoding="utf-8",
    )

    loaded = load_corrections(store)

    assert len(loaded) == 1
    assert loaded[0].final_value == "葉心安"
