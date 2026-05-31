from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor
from random import Random

from ocr_from2xlsx.form_layout import FormLayout


@dataclass(frozen=True, slots=True)
class FieldOptions:
    key: str
    kind: str
    codes: tuple[str, ...]


def choice_fields(layout: FormLayout) -> tuple[FieldOptions, ...]:
    fields: list[FieldOptions] = []
    for field in layout.iter_fields():
        if field.kind not in {"single_choice", "multi_choice"}:
            continue
        codes = tuple(opt.code for opt in field.options)
        if codes:
            fields.append(FieldOptions(key=field.key, kind=field.kind, codes=codes))
    return tuple(fields)


def _weighted_choice(items: Sequence[tuple[str, str]], weights: Sequence[float], rng: Random) -> tuple[str, str]:
    total = sum(weights)
    pick = rng.random() * total
    upto = 0.0
    for item, weight in zip(items, weights):
        upto += weight
        if pick <= upto:
            return item
    return items[-1]


def sample_selection(
    fields: Sequence[FieldOptions],
    rng: Random,
    *,
    min_ratio: float = 0.10,
    max_ratio: float = 0.50,
    coverage: dict[str, int] | None = None,
) -> dict[str, list[str]]:
    fields = tuple(fields)
    total_codes = sum(len(field.codes) for field in fields)
    if total_codes <= 0:
        return {}

    lower = max(1, ceil(total_codes * min_ratio))
    upper = max(lower, floor(total_codes * max_ratio))
    target = rng.randint(lower, upper)

    remaining: dict[str, list[str]] = {field.key: list(field.codes) for field in fields}
    kinds = {field.key: field.kind for field in fields}
    selection: dict[str, list[str]] = {}

    while target > 0:
        candidates: list[tuple[str, str]] = []
        weights: list[float] = []

        for field in fields:
            codes = remaining.get(field.key, [])
            if not codes:
                continue
            for code in codes:
                candidates.append((field.key, code))
                if coverage is None:
                    weights.append(1.0)
                else:
                    weights.append(1.0 / (coverage.get(code, 0) + 1.0))

        if not candidates:
            break

        field_key, code = _weighted_choice(candidates, weights, rng)
        selection.setdefault(field_key, []).append(code)
        target -= 1

        if kinds[field_key] == "single_choice":
            remaining[field_key] = []
        else:
            remaining[field_key].remove(code)

    return selection


def generate_until_coverage(
    fields: Sequence[FieldOptions],
    rng: Random,
    *,
    min_per_option: int = 5,
    max_images: int = 1000,
) -> list[dict[str, list[str]]]:
    fields = tuple(fields)
    coverage = {code: 0 for field in fields for code in field.codes}
    selections: list[dict[str, list[str]]] = []

    for _ in range(max_images):
        if all(count >= min_per_option for count in coverage.values()):
            break
        selection = sample_selection(fields, rng, coverage=coverage)
        if not selection:
            break
        selections.append(selection)
        for codes in selection.values():
            for code in codes:
                coverage[code] += 1

    return selections
