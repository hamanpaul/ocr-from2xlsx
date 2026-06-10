from __future__ import annotations

import json
import math

import pytest

from plugins.paddleocr.mark_features import FEATURE_NAMES, extract_features
from plugins.paddleocr.mark_model import (
    is_marked_by_model,
    predict_proba,
    score_features,
)
from training.eval_gate import choose_operating_point, decide_candidate


def _filled(width: int, height: int, value: int) -> list[list[int]]:
    return [[value for _ in range(width)] for _ in range(height)]


def _tick_crop() -> list[list[int]]:
    crop = _filled(8, 8, 255)
    for row, col in ((1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (5, 4), (6, 3)):
        crop[row][col] = 0
    return crop


def _model(**overrides):
    model = {
        "version": 1,
        "feature_names": list(FEATURE_NAMES),
        "mean": [0.0] * len(FEATURE_NAMES),
        "std": [1.0] * len(FEATURE_NAMES),
        "coef": [0.0] * len(FEATURE_NAMES),
        "intercept": -0.5,
        "threshold": 0.5,
    }
    model.update(overrides)
    return model


def test_empty_crop_returns_zeroes_with_stable_feature_names() -> None:
    features = extract_features([])

    assert tuple(features) == FEATURE_NAMES
    assert features == {name: 0.0 for name in FEATURE_NAMES}
    json.dumps(features)


def test_blank_filled_and_tick_like_crops_have_expected_core_features() -> None:
    blank = extract_features(_filled(4, 4, 255))
    filled = extract_features(_filled(4, 4, 0))
    tick = extract_features(_tick_crop())

    assert blank["dark_ratio"] == 0.0
    assert filled["dark_ratio"] == 1.0
    assert tick["diag_ratio"] > 0.0
    assert -1.0 <= tick["centroid_dx"] <= 1.0
    assert -1.0 <= tick["centroid_dy"] <= 1.0
    assert tick["rows_with_ink"] > 0.0
    assert tick["cols_with_ink"] > 0.0


def test_score_and_probability_use_standardized_linear_sigmoid() -> None:
    feature_map = {name: 0.0 for name in FEATURE_NAMES}
    feature_map["dark_ratio"] = 0.75
    feature_map["ink_w"] = 0.25
    model = _model(
        mean=[0.5 if name == "dark_ratio" else 0.0 for name in FEATURE_NAMES],
        std=[0.5 if name == "dark_ratio" else 1.0 for name in FEATURE_NAMES],
        coef=[
            2.0 if name == "dark_ratio" else -4.0 if name == "ink_w" else 0.0
            for name in FEATURE_NAMES
        ],
        intercept=-0.25,
        threshold=0.6,
    )

    expected_score = ((0.75 - 0.5) / 0.5) * 2.0 + 0.25 * -4.0 - 0.25
    expected_probability = 1.0 / (1.0 + math.exp(-expected_score))

    assert score_features(model, feature_map) == pytest.approx(expected_score)
    assert predict_proba(model, feature_map) == pytest.approx(expected_probability)
    assert is_marked_by_model(_filled(2, 2, 0), model) == (expected_probability >= 0.6)


def test_invalid_model_feature_name_or_length_mismatch_raises_value_error() -> None:
    feature_map = {name: 0.0 for name in FEATURE_NAMES}

    bad_names = _model(feature_names=["wrong"] + list(FEATURE_NAMES[1:]))
    with pytest.raises(ValueError, match="feature_names"):
        score_features(bad_names, feature_map)

    bad_length = _model(coef=[1.0])
    with pytest.raises(ValueError, match="coef"):
        score_features(bad_length, feature_map)

    missing_feature = dict(feature_map)
    del missing_feature["row_transitions"]
    with pytest.raises(ValueError, match="row_transitions"):
        score_features(_model(), missing_feature)


def test_model_rejects_non_finite_numbers_bad_std_and_negative_threshold() -> None:
    feature_map = {name: 0.0 for name in FEATURE_NAMES}

    with pytest.raises(ValueError, match="threshold"):
        score_features(_model(threshold=-0.1), feature_map)
    with pytest.raises(ValueError, match="threshold"):
        score_features(_model(threshold=float("nan")), feature_map)
    with pytest.raises(ValueError, match="std"):
        score_features(_model(std=[0.0] * len(FEATURE_NAMES)), feature_map)
    with pytest.raises(ValueError, match="coef"):
        score_features(_model(coef=[float("nan")] * len(FEATURE_NAMES)), feature_map)
    with pytest.raises(ValueError, match="intercept"):
        score_features(_model(intercept=float("inf")), feature_map)


def test_threshold_above_one_is_supported_as_reject_all_sentinel() -> None:
    assert is_marked_by_model(_filled(2, 2, 0), _model(threshold=1.1)) is False


def test_is_marked_by_model_without_model_uses_legacy_fallback() -> None:
    assert is_marked_by_model(_filled(3, 3, 0), model=None) is True
    assert is_marked_by_model(_filled(3, 3, 255), model=None) is False


def test_choose_operating_point_picks_highest_recall_safe_threshold() -> None:
    result = choose_operating_point(
        [(1, 0.90), (0, 0.80), (1, 0.70), (1, 0.40), (0, 0.30)],
        min_precision=0.75,
    )

    assert result["threshold"] == pytest.approx(0.40)
    assert result["precision"] == pytest.approx(0.75)
    assert result["recall"] == pytest.approx(1.0)
    assert result["tp"] == 3
    assert result["fp"] == 1
    assert result["fn"] == 0


def test_choose_operating_point_returns_reject_all_when_no_threshold_is_safe() -> None:
    result = choose_operating_point([(0, 0.90), (1, 0.10)], min_precision=0.99)

    assert result["threshold"] > 0.90
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["tp"] == 0
    assert result["fp"] == 0
    assert result["fn"] == 1


def test_decide_candidate_accepts_only_recall_gain_with_safe_precision() -> None:
    current = {"precision": 1.0, "recall": 0.50}

    accepted = decide_candidate(current, {"precision": 0.99, "recall": 0.60})
    unsafe = decide_candidate(current, {"precision": 0.98, "recall": 0.70})
    no_gain = decide_candidate(current, {"precision": 1.0, "recall": 0.50})

    assert accepted["adopt"] is True
    assert unsafe["adopt"] is False
    assert "precision" in unsafe["reason"]
    assert no_gain["adopt"] is False
    assert "recall" in no_gain["reason"]


def test_decide_candidate_adopts_safe_candidate_over_unsafe_current() -> None:
    degenerate_current = {"precision": 0.31, "recall": 1.0}

    adopted = decide_candidate(degenerate_current, {"precision": 1.0, "recall": 0.91})
    still_unsafe = decide_candidate(degenerate_current, {"precision": 0.98, "recall": 1.0})

    assert adopted["adopt"] is True
    assert "unsafe" in str(adopted["reason"])
    assert still_unsafe["adopt"] is False
    assert "precision" in str(still_unsafe["reason"])


def test_decide_candidate_rejects_non_finite_safety_metrics() -> None:
    current = {"precision": 1.0, "recall": 0.50}

    for candidate in (
        {"precision": float("nan"), "recall": 0.60},
        {"precision": 1.0, "recall": float("inf")},
    ):
        result = decide_candidate(current, candidate)
        assert result["adopt"] is False
        assert "finite" in str(result["reason"])

    result = decide_candidate({"precision": 1.0, "recall": float("nan")}, {"precision": 1.0, "recall": 0.60})
    assert result["adopt"] is False
    assert "finite" in str(result["reason"])
