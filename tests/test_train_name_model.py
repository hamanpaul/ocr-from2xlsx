from __future__ import annotations

from pathlib import Path

from training.train_name_model import build_export_command, build_train_command


def test_build_train_command_pins_cpu_paths_and_epochs() -> None:
    command = build_train_command(
        vendor_repo=Path("training/vendor/PaddleOCR"),
        corpus_dir=Path("training/out/namev1"),
        save_dir=Path("training/out/namev1/model"),
        pretrained=Path("training/vendor/PP-OCRv5_mobile_rec_pretrained"),
        dict_path=Path("training/vendor/PaddleOCR/ppocr/utils/dict/ppocrv5_dict.txt"),
        epochs=20,
        batch_size=16,
    )

    text = " ".join(command)
    assert command[0].endswith("train.py")
    assert "Global.use_gpu=false" in text
    assert "Global.epoch_num=20" in text
    assert "train.txt" in text and "validation.txt" in text
    assert "batch_size_per_card=16" in text


def test_build_export_command_targets_inference_dir() -> None:
    command = build_export_command(
        vendor_repo=Path("training/vendor/PaddleOCR"),
        checkpoint=Path("training/out/namev1/model/latest"),
        dict_path=Path("training/vendor/PaddleOCR/ppocr/utils/dict/ppocrv5_dict.txt"),
        inference_dir=Path("training/out/namev1/inference"),
    )

    text = " ".join(command)
    assert command[0].endswith("export_model.py")
    assert "Global.save_inference_dir=" in text
