from __future__ import annotations

import json

import pytest

from ocr_from2xlsx.form_layout import Field, FormLayout, Option, Section
from training.eval_metrics import compare_mark_sets, compare_records, compare_sets, prf


def test_prf_zero_denominators_returns_zeroes() -> None:
    result = prf(tp=0, fp=0, fn=0)

    assert result == {
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    json.dumps(result)


def test_prf_returns_expected_fractions() -> None:
    result = prf(tp=2, fp=1, fn=3)

    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 3
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 5)
    expected_f1 = 2 * (2 / 3) * (2 / 5) / ((2 / 3) + (2 / 5))
    assert result["f1"] == pytest.approx(expected_f1)
    json.dumps(result)


def test_compare_sets_reports_stable_lists() -> None:
    gold = {"a", "b", "c"}
    pred = {"b", "c", "d"}

    result = compare_sets(gold, pred)

    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["true_positive"] == ["b", "c"]
    assert result["false_positive"] == ["d"]
    assert result["false_negative"] == ["a"]
    json.dumps(result)


def test_compare_sets_sorts_json_scalar_mixed_types_stably() -> None:
    result = compare_sets({None, 1, "a"}, {"a", 2})

    assert result["true_positive"] == ["a"]
    assert result["false_positive"] == [2]
    assert result["false_negative"] == [None, 1]
    json.dumps(result)


def test_compare_mark_sets_reports_aggregate_and_per_field() -> None:
    gold = {("field_a", "x"), ("field_a", "y"), ("field_b", "m")}
    pred = {("field_a", "y"), ("field_b", "n")}

    result = compare_mark_sets(gold, pred)

    aggregate = result["aggregate"]
    assert aggregate["tp"] == 1
    assert aggregate["fp"] == 1
    assert aggregate["fn"] == 2

    per_field = result["per_field"]
    assert per_field["field_a"]["tp"] == 1
    assert per_field["field_a"]["fp"] == 0
    assert per_field["field_a"]["fn"] == 1
    assert per_field["field_b"]["tp"] == 0
    assert per_field["field_b"]["fp"] == 1
    assert per_field["field_b"]["fn"] == 1
    json.dumps(result)


def test_compare_records_skips_none_paths_and_micro_averages() -> None:
    layout = FormLayout(
        template_id="tiny",
        sections=(
            Section(
                id="S",
                title="Tiny",
                fields=(
                    Field(
                        key="name",
                        title="Name",
                        kind="text",
                        record_path="name",
                        anchor_cell="A1",
                    ),
                    Field(
                        key="gender",
                        title="Gender",
                        kind="single_choice",
                        record_path="gender",
                        anchor_cell="A2",
                        options=(
                            Option(label="Female", code="female", cell="B2"),
                            Option(label="Male", code="male", cell="B3"),
                        ),
                    ),
                    Field(
                        key="allergies",
                        title="Allergies",
                        kind="multi_choice",
                        record_path="details.allergies",
                        anchor_cell="A3",
                        options=(
                            Option(label="Peanut", code="peanut", cell="B4"),
                            Option(label="Shellfish", code="shellfish", cell="B5"),
                        ),
                    ),
                    Field(
                        key="languages",
                        title="Languages",
                        kind="multi_choice",
                        record_path="languages",
                        anchor_cell="A4",
                        options=(
                            Option(label="English", code="en", cell="B6"),
                            Option(label="French", code="fr", cell="B7"),
                            Option(label="Spanish", code="es", cell="B8"),
                        ),
                    ),
                    Field(
                        key="page_num",
                        title="Page",
                        kind="text",
                        record_path=None,
                        anchor_cell="Z1",
                    ),
                ),
            ),
        ),
    )

    gold_record = {
        "name": "Alice",
        "gender": "female",
        "details": {"allergies": ["peanut", "shellfish"]},
        "languages": ["en", "fr"],
    }
    pred_record = {
        "name": "Alice",
        "gender": "male",
        "details": {"allergies": ["peanut"]},
        "languages": ["en", "es"],
    }

    result = compare_records(layout, gold_record, pred_record)

    assert "page_num" not in result["fields"]
    assert result["fields"]["name"]["match"] is True
    assert result["fields"]["gender"]["match"] is False
    assert result["fields"]["allergies"]["metrics"]["tp"] == 1
    assert result["fields"]["languages"]["metrics"]["fp"] == 1

    assert result["scalar"] == {"total": 2, "correct": 1, "accuracy": 0.5}
    assert result["multi_choice"]["tp"] == 2
    assert result["multi_choice"]["fp"] == 1
    assert result["multi_choice"]["fn"] == 2
    assert result["multi_choice"]["precision"] == pytest.approx(2 / 3)
    assert result["multi_choice"]["recall"] == pytest.approx(1 / 2)
    json.dumps(result)
