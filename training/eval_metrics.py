from __future__ import annotations

from typing import Any, Iterable

from ocr_from2xlsx.form_layout import FormLayout
from ocr_from2xlsx.record_access import get_by_path


def _stable_sorted(items: Iterable[Any]) -> list[Any]:
    return sorted(items, key=lambda item: (type(item).__name__, repr(item)))


def prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def compare_sets(gold: Iterable[Any], pred: Iterable[Any]) -> dict[str, Any]:
    gold_set = set(gold)
    pred_set = set(pred)
    true_positive = gold_set & pred_set
    false_positive = pred_set - gold_set
    false_negative = gold_set - pred_set
    metrics = prf(len(true_positive), len(false_positive), len(false_negative))
    metrics.update(
        {
            "true_positive": _stable_sorted(true_positive),
            "false_positive": _stable_sorted(false_positive),
            "false_negative": _stable_sorted(false_negative),
        }
    )
    return metrics


def compare_mark_sets(
    gold_marks: Iterable[tuple[str, str]],
    pred_marks: Iterable[tuple[str, str]],
) -> dict[str, Any]:
    gold_set = set(gold_marks)
    pred_set = set(pred_marks)
    aggregate = compare_sets(gold_set, pred_set)

    gold_by_field: dict[str, set[str]] = {}
    pred_by_field: dict[str, set[str]] = {}
    for field_key, code in gold_set:
        gold_by_field.setdefault(field_key, set()).add(code)
    for field_key, code in pred_set:
        pred_by_field.setdefault(field_key, set()).add(code)

    per_field: dict[str, dict[str, Any]] = {}
    for field_key in sorted(set(gold_by_field) | set(pred_by_field)):
        per_field[field_key] = compare_sets(
            gold_by_field.get(field_key, set()),
            pred_by_field.get(field_key, set()),
        )

    return {"aggregate": aggregate, "per_field": per_field}


def compare_records(layout: FormLayout, gold_record: Any, pred_record: Any) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    scalar_total = 0
    scalar_correct = 0
    multi_tp = 0
    multi_fp = 0
    multi_fn = 0

    for field in layout.iter_fields():
        if field.record_path is None:
            continue
        gold_value = get_by_path(gold_record, field.record_path)
        pred_value = get_by_path(pred_record, field.record_path)

        if field.kind in ("text", "single_choice"):
            if field.kind == "single_choice":
                gold_codes = field.selected_codes(gold_value)
                pred_codes = field.selected_codes(pred_value)
                gold_scalar = gold_codes[0] if gold_codes else None
                pred_scalar = pred_codes[0] if pred_codes else None
            else:
                gold_scalar = gold_value
                pred_scalar = pred_value
            match = gold_scalar == pred_scalar
            fields[field.key] = {
                "kind": field.kind,
                "gold": gold_scalar,
                "pred": pred_scalar,
                "match": match,
            }
            scalar_total += 1
            if match:
                scalar_correct += 1
            continue

        if field.kind == "multi_choice":
            gold_codes = set(field.selected_codes(gold_value))
            pred_codes = set(field.selected_codes(pred_value))
            metrics = compare_sets(gold_codes, pred_codes)
            fields[field.key] = {
                "kind": field.kind,
                "gold": sorted(gold_codes),
                "pred": sorted(pred_codes),
                "metrics": metrics,
            }
            multi_tp += metrics["tp"]
            multi_fp += metrics["fp"]
            multi_fn += metrics["fn"]
            continue

        raise ValueError(f"Unsupported field kind: {field.kind!r}")

    scalar_accuracy = scalar_correct / scalar_total if scalar_total else 0.0
    return {
        "fields": fields,
        "scalar": {
            "total": scalar_total,
            "correct": scalar_correct,
            "accuracy": scalar_accuracy,
        },
        "multi_choice": prf(multi_tp, multi_fp, multi_fn),
    }
