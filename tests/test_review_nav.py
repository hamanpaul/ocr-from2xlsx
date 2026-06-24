from __future__ import annotations

from ocr_from2xlsx.review_nav import (
    next_flagged_key,
    option_index_for_digit,
    prev_flagged_key,
)

ORDER = ["service_date", "identity", "name", "gender", "cancer"]


def test_next_flagged_cycles_only_flagged_in_order():
    assert next_flagged_key(ORDER, {"name", "gender"}, "service_date") == "name"
    assert next_flagged_key(ORDER, {"name", "gender"}, "name") == "gender"


def test_next_flagged_wraps_around():
    assert next_flagged_key(ORDER, {"name", "gender"}, "gender") == "name"


def test_next_flagged_from_none_returns_first_flagged():
    assert next_flagged_key(ORDER, {"gender", "name"}, None) == "name"


def test_next_flagged_single_flag_wraps_to_itself():
    assert next_flagged_key(ORDER, {"name"}, "name") == "name"


def test_next_flagged_empty_returns_none():
    assert next_flagged_key(ORDER, set(), "name") is None


def test_next_flagged_ignores_flags_not_in_order():
    assert next_flagged_key(ORDER, {"ghost"}, "name") is None


def test_prev_flagged_cycles_backwards_and_wraps():
    assert prev_flagged_key(ORDER, {"name", "gender"}, "gender") == "name"
    assert prev_flagged_key(ORDER, {"name", "gender"}, "name") == "gender"
    assert prev_flagged_key(ORDER, {"identity", "cancer"}, "identity") == "cancer"


def test_prev_flagged_empty_returns_none():
    assert prev_flagged_key(ORDER, set(), "name") is None


def test_option_index_for_digit_maps_one_based_to_zero_based():
    assert option_index_for_digit("1", 3) == 0
    assert option_index_for_digit("3", 3) == 2


def test_option_index_for_digit_rejects_out_of_range_and_non_digits():
    assert option_index_for_digit("4", 3) is None
    assert option_index_for_digit("0", 3) is None
    assert option_index_for_digit("a", 3) is None
    assert option_index_for_digit("", 3) is None
    assert option_index_for_digit("12", 3) is None
