from __future__ import annotations

import random
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from training.gen_names import read_label_file, render_corpus


def test_render_corpus_writes_images_and_three_disjoint_label_files(tmp_path: Path) -> None:
    summary = render_corpus(
        tmp_path,
        rng=random.Random(0),
        total=12,
        validation_fraction=0.25,
        holdout_fraction=0.25,
        augment=False,
    )

    train = read_label_file(tmp_path / "train.txt")
    validation = read_label_file(tmp_path / "validation.txt")
    holdout = read_label_file(tmp_path / "holdout.txt")

    assert summary == {"train": 6, "validation": 3, "holdout": 3}
    labels = [label for _, label in train + validation + holdout]
    assert len(set(labels)) == 12
    for image_rel, _ in train + validation + holdout:
        assert (tmp_path / image_rel).is_file()


def test_render_corpus_image_is_grayscale_with_ink(tmp_path: Path) -> None:
    from PIL import Image

    render_corpus(tmp_path, rng=random.Random(1), total=2, validation_fraction=0.0, holdout_fraction=0.5, augment=False)
    image_rel, _ = read_label_file(tmp_path / "train.txt")[0]
    with Image.open(tmp_path / image_rel) as image:
        assert image.mode == "L"
        assert image.height >= 32 and image.width >= image.height
        pixel_iter = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        assert min(pixel_iter) < 128  # some ink present
