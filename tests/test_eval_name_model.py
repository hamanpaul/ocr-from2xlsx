from __future__ import annotations

import json
from pathlib import Path

from training.eval_name_model import char_accuracy, edit_distance, score_predictions, write_report


def test_edit_distance_basics() -> None:
    assert edit_distance("王小明", "王小明") == 0
    assert edit_distance("王小明", "王大明") == 1
    assert edit_distance("王小明", "") == 3
    assert edit_distance("", "陳") == 1


def test_char_accuracy_is_one_minus_normalized_edit_distance() -> None:
    assert char_accuracy("王小明", "王小明") == 1.0
    assert char_accuracy("王小明", "王大明") == 1.0 - 1.0 / 3.0
    assert char_accuracy("", "") == 1.0


def test_score_predictions_aggregates_exact_match_and_char_accuracy() -> None:
    pairs = [("王小明", "王小明"), ("陳美玲", "陳美月"), ("林志偉", "")]

    metrics = score_predictions(pairs)

    assert metrics["count"] == 3
    assert metrics["exact_match"] == 1 / 3
    assert 0.0 < metrics["char_accuracy"] < 1.0


def test_write_report_emits_json_and_markdown(tmp_path: Path) -> None:
    metrics = {"count": 2, "exact_match": 0.5, "char_accuracy": 0.75}

    write_report(metrics, tmp_path)

    loaded = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert loaded == metrics
    assert "exact_match" in (tmp_path / "report.md").read_text(encoding="utf-8")
