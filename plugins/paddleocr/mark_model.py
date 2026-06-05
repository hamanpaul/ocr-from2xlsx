"""Plugin-safe checkbox mark model scoring."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from .mark_detect import is_marked
    from .mark_features import FEATURE_NAMES, extract_features
except ImportError:  # pragma: no cover - supports file-location plugin imports.
    from mark_detect import is_marked  # type: ignore
    from mark_features import FEATURE_NAMES, extract_features  # type: ignore


def _validate_model(model: Mapping[str, Any]) -> None:
    if list(model.get("feature_names", [])) != list(FEATURE_NAMES):
        raise ValueError("model feature_names do not match expected mark features")

    expected = len(FEATURE_NAMES)
    for key in ("mean", "std", "coef"):
        values = model.get(key)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError(f"model {key} must be a sequence")
        if len(values) != expected:
            raise ValueError(f"model {key} length mismatch")
        for index, value in enumerate(values):
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(f"model {key}[{index}] must be finite")
            if key == "std" and numeric <= 0.0:
                raise ValueError(f"model std[{index}] must be greater than zero")

    if "intercept" not in model:
        raise ValueError("model intercept is required")
    if not math.isfinite(float(model["intercept"])):
        raise ValueError("model intercept must be finite")
    if "threshold" not in model:
        raise ValueError("model threshold is required")
    threshold = float(model["threshold"])
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("model threshold must be finite and non-negative")


def load_model(path: str | Path) -> dict[str, Any]:
    """Load and validate a JSON mark model."""
    with Path(path).open("r", encoding="utf-8") as file:
        model = json.load(file)
    if not isinstance(model, dict):
        raise ValueError("model JSON must be an object")
    _validate_model(model)
    return model


def score_features(model: Mapping[str, Any], feature_map: Mapping[str, float]) -> float:
    """Return the standardized linear score before sigmoid."""
    _validate_model(model)
    score = float(model["intercept"])
    for index, name in enumerate(FEATURE_NAMES):
        std = float(model["std"][index])
        if name not in feature_map:
            raise ValueError(f"feature_map is missing feature {name!r}")
        value = float(feature_map[name])
        if not math.isfinite(value):
            raise ValueError(f"feature_map feature {name!r} must be finite")
        standardized = (value - float(model["mean"][index])) / std
        score += standardized * float(model["coef"][index])
    return score


def predict_proba(model: Mapping[str, Any], feature_map: Mapping[str, float]) -> float:
    """Return sigmoid probability for extracted feature values."""
    score = score_features(model, feature_map)
    if score >= 0:
        exp_neg = math.exp(-score)
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(score)
    return exp_pos / (1.0 + exp_pos)


def is_marked_by_model(
    region: Sequence[Sequence[float]],
    model: Mapping[str, Any] | None = None,
) -> bool:
    """Classify a crop, falling back to legacy detection when no model is loaded."""
    if model is None:
        return is_marked(region)
    probability = predict_proba(model, extract_features(region))
    return probability >= float(model["threshold"])
