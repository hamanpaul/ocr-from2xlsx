from __future__ import annotations

import random

from ocr_from2xlsx.form_layout import service_record_layout

from training.sampler import FieldOptions, choice_fields, generate_until_coverage, sample_selection


def _option_codes(fields):
    return [code for field in fields for code in field.codes]


def _per_field_coverage(fields, selections):
    coverage = {(field.key, code): 0 for field in fields for code in field.codes}
    for selection in selections:
        for field in fields:
            for code in selection.get(field.key, []):
                coverage[(field.key, code)] += 1
    return coverage


def test_choice_fields_are_single_or_multi_with_options() -> None:
    fields = choice_fields(service_record_layout())

    assert fields
    assert all(field.kind in {"single_choice", "multi_choice"} for field in fields)
    assert all(field.codes for field in fields)


def test_sample_respects_ratio_singlecap_and_min_one() -> None:
    fields = choice_fields(service_record_layout())
    total_codes = sum(len(field.codes) for field in fields)
    lower = max(1, int(total_codes * 0.10) - 1)
    upper = min(total_codes, int(total_codes * 0.50) + 1)

    rng = random.Random(1)
    for _ in range(200):
        selection = sample_selection(fields, rng)
        marked = sum(len(codes) for codes in selection.values())

        assert lower <= marked <= upper
        assert all(codes for codes in selection.values())

        for field in fields:
            selected = selection.get(field.key, [])
            assert len(selected) <= len(field.codes)
            assert len(selected) == len(set(selected))
            assert all(code in field.codes for code in selected)
            if field.kind == "single_choice" and selected:
                assert len(selected) == 1


def test_generate_until_coverage_marks_every_option_at_least_min() -> None:
    fields = choice_fields(service_record_layout())
    rng = random.Random(1)

    selections = generate_until_coverage(fields, rng, min_per_option=5)
    coverage = {code: 0 for code in _option_codes(fields)}

    for selection in selections:
        for codes in selection.values():
            for code in codes:
                coverage[code] += 1

    assert all(count >= 5 for count in coverage.values())
    assert len(selections) < 1000


def test_generate_until_coverage_tracks_duplicate_codes_per_field() -> None:
    fields = (
        FieldOptions(key="field_a", kind="single_choice", codes=("other",)),
        FieldOptions(key="field_b", kind="single_choice", codes=("other",)),
    )

    selections = generate_until_coverage(fields, random.Random(1), min_per_option=2, max_images=10)
    coverage = _per_field_coverage(fields, selections)

    assert len(selections) >= 4
    assert all(count >= 2 for count in coverage.values())


def test_generate_until_coverage_satisfies_duplicate_raw_codes_independently() -> None:
    fields = (
        FieldOptions(key="field_a", kind="single_choice", codes=("other", "alpha")),
        FieldOptions(key="field_b", kind="multi_choice", codes=("other", "beta")),
    )

    selections = generate_until_coverage(fields, random.Random(2), min_per_option=2, max_images=20)
    coverage = _per_field_coverage(fields, selections)

    assert all(count >= 2 for count in coverage.values())


def test_sample_selection_clamps_target_to_feasible_marks() -> None:
    fields = (
        FieldOptions(key="field_a", kind="single_choice", codes=("a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9", "a10", "a11")),
        FieldOptions(key="field_b", kind="single_choice", codes=("b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9", "b10", "b11")),
    )

    class RecordingRandom(random.Random):
        def __init__(self) -> None:
            super().__init__(0)
            self.randint_args: list[tuple[int, int]] = []

        def randint(self, a: int, b: int) -> int:
            self.randint_args.append((a, b))
            return a

    rng = RecordingRandom()
    selection = sample_selection(fields, rng)

    assert rng.randint_args == [(2, 2)]
    assert sum(len(codes) for codes in selection.values()) == 2
