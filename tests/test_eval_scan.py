from __future__ import annotations

from training.eval_scan import score_fields


def test_score_fields_counts_exact_field_matches() -> None:
    predicted = {"service_date": "2025-06-25", "identity": "patient", "gender": "female", "name": None}
    expected = {"service_date": "2025-06-25", "identity": "patient", "gender": "male", "name": "葉心安"}

    metrics = score_fields(predicted, expected)

    assert metrics["total"] == 4
    assert metrics["correct"] == 2  # service_date + identity
    assert metrics["per_field"]["gender"] is False
    assert metrics["per_field"]["service_date"] is True


def test_score_fields_treats_empty_and_none_as_equal() -> None:
    predicted = {"name": ""}
    expected = {"name": None}

    metrics = score_fields(predicted, expected)

    assert metrics["per_field"]["name"] is True


def test_score_fields_only_scores_expected_keys() -> None:
    predicted = {"service_date": "2025-06-25", "gender": "female"}
    expected = {"service_date": "2025-06-25"}

    metrics = score_fields(predicted, expected)

    assert metrics["total"] == 1
    assert metrics["correct"] == 1
    assert "gender" not in metrics["per_field"]
