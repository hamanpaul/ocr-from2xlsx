from __future__ import annotations

import random
from pathlib import Path

import pytest

from training.gen_names import (
    GIVEN_CHARS,
    SURNAMES,
    filter_names_to_dict,
    sample_names,
    split_batches,
    write_label_file,
    read_label_file,
)


def test_pools_are_reasonably_sized_and_unique() -> None:
    assert len(SURNAMES) >= 80
    assert len(set(SURNAMES)) == len(SURNAMES)
    assert len(GIVEN_CHARS) >= 300
    assert len(set(GIVEN_CHARS)) == len(GIVEN_CHARS)


def test_sample_names_is_seed_reproducible_and_unique() -> None:
    first = sample_names(random.Random(7), 200)
    second = sample_names(random.Random(7), 200)

    assert first == second
    assert len(set(first)) == len(first)
    assert all(2 <= len(name) <= 4 for name in first)
    assert all(name[0] in SURNAMES for name in first)


def test_split_batches_are_disjoint_and_cover_all() -> None:
    names = sample_names(random.Random(0), 100)
    train, validation, holdout = split_batches(names, validation_fraction=0.1, holdout_fraction=0.1)

    assert len(train) + len(validation) + len(holdout) == len(names)
    assert set(train).isdisjoint(validation)
    assert set(train).isdisjoint(holdout)
    assert set(validation).isdisjoint(holdout)
    assert len(holdout) == 10


def test_filter_names_to_dict_drops_oov_names() -> None:
    kept = filter_names_to_dict(["王明", "王珺"], dict_chars={"王", "明"})

    assert kept == ["王明"]


def test_label_file_roundtrip_and_path_safety(tmp_path: Path) -> None:
    rows = [("images/name-0001.png", "王小明"), ("images/name-0002.png", "陳美玲")]
    label_path = tmp_path / "train.txt"

    write_label_file(label_path, rows)

    assert read_label_file(label_path) == rows
    with pytest.raises(ValueError, match="relative"):
        write_label_file(label_path, [("../escape.png", "王小明")])
