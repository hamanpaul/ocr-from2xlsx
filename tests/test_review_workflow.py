from __future__ import annotations

from ocr_from2xlsx.review_workflow import (
    correction_mode_controls,
    rank_roster_candidates,
    record_badge_state,
    scan_mode_controls,
)


def test_modes_are_correct_and_disjoint():
    corr = set(correction_mode_controls())
    scan = set(scan_mode_controls())
    assert corr == {
        "prev_record", "next_record", "confirm", "force_write",
        "zoom_in_static", "zoom_out_static", "zoom_reset_static", "progress",
    }
    assert {"capture_recognize", "import_folder_batch", "choose_camera", "rotate"} <= scan
    assert corr.isdisjoint(scan)


def test_record_badge_state_written_takes_priority():
    assert record_badge_state(0, {0}, set()) == "written"
    assert record_badge_state(1, {0}, {1}) == "blocked"
    assert record_badge_state(2, {0}, {1}) == "pending"
    assert record_badge_state(0, {0}, {0}) == "written"


def test_rank_roster_exact_first_then_similar():
    roster = ["王小明", "王大明", "李四", "王小明"]
    out = rank_roster_candidates("王小明", roster)
    assert out[0] == "王小明"
    assert out[1] == "王大明"
    assert out.index("李四") > out.index("王大明")


def test_rank_roster_empty_query_keeps_order_deduped():
    assert rank_roster_candidates("", ["a", "a", "b"]) == ["a", "b"]


def test_rank_roster_limit_and_empty_roster():
    assert rank_roster_candidates("x", [], 5) == []
    assert len(rank_roster_candidates("王", ["王a", "王b", "王c", "王d"], 2)) == 2
