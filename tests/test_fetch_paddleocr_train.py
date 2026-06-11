from __future__ import annotations

from pathlib import Path

from training.fetch_paddleocr_train import (
    DEFAULT_CONFIG_RELPATH,
    DEFAULT_TAG,
    DEFAULT_WEIGHTS_URL,
    build_clone_command,
    vendor_paths,
)


def test_vendor_paths_are_rooted_under_training_vendor() -> None:
    paths = vendor_paths(Path("training"))

    assert paths["repo"] == Path("training") / "vendor" / "PaddleOCR"
    assert paths["weights"] == Path("training") / "vendor" / "PP-OCRv5_mobile_rec_pretrained.pdparams"


def test_build_clone_command_pins_tag_and_is_shallow() -> None:
    command = build_clone_command(Path("training/vendor/PaddleOCR"), tag="v3.1.0")

    assert command[:3] == ["git", "clone", "--depth"]
    assert "--branch" in command and "v3.1.0" in command
    assert command[-1].endswith("PaddleOCR")


def test_default_constants_are_concrete() -> None:
    assert DEFAULT_TAG.startswith("v")
    assert DEFAULT_WEIGHTS_URL.startswith("https://")
    assert DEFAULT_CONFIG_RELPATH.endswith(".yml")
