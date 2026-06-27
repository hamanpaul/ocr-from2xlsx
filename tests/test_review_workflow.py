from __future__ import annotations

from ocr_from2xlsx.review_workflow import record_badge_state


def test_record_badge_state_written_takes_priority():
    assert record_badge_state(0, {0}, set()) == "written"
    assert record_badge_state(1, {0}, {1}) == "blocked"
    assert record_badge_state(2, {0}, {1}) == "pending"
    assert record_badge_state(0, {0}, {0}) == "written"
