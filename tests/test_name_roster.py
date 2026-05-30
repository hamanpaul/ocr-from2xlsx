from __future__ import annotations

from ocr_from2xlsx.name_roster import roster_match


def test_exact_match_returns_name():
    assert roster_match("葉心安", ["葉心安", "王小明"]) == "葉心安"


def test_near_miss_within_threshold_matches():
    # one wrong char out of three -> ratio 0.67 >= 0.6
    assert roster_match("葉心女", ["葉心安", "王小明"]) == "葉心安"


def test_too_different_returns_none():
    assert roster_match("林大維", ["葉心安", "王小明"]) is None


def test_empty_candidate_or_roster_returns_none():
    assert roster_match("", ["葉心安"]) is None
    assert roster_match("葉心安", []) is None


def test_threshold_is_configurable():
    assert roster_match("葉心女", ["葉心安"], threshold=1.0) is None
    assert roster_match("葉心安", ["葉心安"], threshold=1.0) == "葉心安"
