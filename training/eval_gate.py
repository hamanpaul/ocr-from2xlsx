"""Pure operating-point and candidate adoption gate for mark models."""
from __future__ import annotations

import math
from typing import Mapping, Sequence


def _finite_metric(value: float, name: str) -> tuple[float, str | None]:
    metric = float(value)
    if not math.isfinite(metric):
        return metric, f"{name} must be finite"
    return metric, None


def _metrics_at_threshold(
    labels_scores: Sequence[tuple[int, float]],
    threshold: float,
) -> dict[str, float | int]:
    tp = fp = fn = 0
    for label, score in labels_scores:
        positive = score >= threshold
        if positive and label:
            tp += 1
        elif positive and not label:
            fp += 1
        elif not positive and label:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
    }


def choose_operating_point(
    labels_scores: Sequence[tuple[int, float]],
    min_precision: float = 0.99,
) -> dict[str, float | int]:
    """Choose the highest-recall threshold satisfying precision safety."""
    min_precision, error = _finite_metric(min_precision, "min_precision")
    if error is not None:
        raise ValueError(error)
    if not labels_scores:
        return _metrics_at_threshold([], 1.0)

    thresholds = sorted({float(score) for _, score in labels_scores}, reverse=True)
    safe = [
        _metrics_at_threshold(labels_scores, threshold)
        for threshold in thresholds
        if _metrics_at_threshold(labels_scores, threshold)["precision"] >= min_precision
    ]
    if not safe:
        reject_threshold = max(float(score) for _, score in labels_scores) + 1.0
        return _metrics_at_threshold(labels_scores, reject_threshold)

    return max(
        safe,
        key=lambda metrics: (
            float(metrics["recall"]),
            float(metrics["precision"]),
            -float(metrics["threshold"]),
        ),
    )


def decide_candidate(
    current_metrics: Mapping[str, float],
    candidate_metrics: Mapping[str, float],
    min_precision: float = 0.99,
) -> dict[str, object]:
    """Adopt only candidates that improve recall while preserving precision."""
    min_precision, error = _finite_metric(min_precision, "min_precision")
    if error is not None:
        return {"adopt": False, "reason": error}
    candidate_precision, error = _finite_metric(candidate_metrics.get("precision", 0.0), "candidate precision")
    if error is not None:
        return {"adopt": False, "reason": error}
    current_recall, error = _finite_metric(current_metrics.get("recall", 0.0), "current recall")
    if error is not None:
        return {"adopt": False, "reason": error}
    candidate_recall, error = _finite_metric(candidate_metrics.get("recall", 0.0), "candidate recall")
    if error is not None:
        return {"adopt": False, "reason": error}

    if candidate_precision < min_precision:
        return {
            "adopt": False,
            "reason": "candidate precision is below the minimum precision threshold",
        }
    if candidate_recall <= current_recall:
        return {
            "adopt": False,
            "reason": "candidate recall does not improve on current recall",
        }
    return {"adopt": True, "reason": "candidate recall improves with safe precision"}
