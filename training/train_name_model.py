"""Thin CPU finetune/export wrapper over the vendored official PaddleOCR trainer."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_CONFIG_RELPATH = "configs/rec/PP-OCRv5/PP-OCRv5_mobile_rec.yml"


def _posix(path: Path) -> str:
    return Path(path).as_posix()


def build_train_command(
    *,
    vendor_repo: Path,
    corpus_dir: Path,
    save_dir: Path,
    pretrained: Path,
    dict_path: Path,
    epochs: int,
    batch_size: int = 16,
    config_relpath: str = DEFAULT_CONFIG_RELPATH,
) -> list[str]:
    return [
        str(Path(vendor_repo) / "tools" / "train.py"),
        "-c",
        str(Path(vendor_repo) / config_relpath),
        "-o",
        "Global.use_gpu=false",
        f"Global.epoch_num={int(epochs)}",
        f"Global.save_model_dir={_posix(save_dir)}",
        f"Global.pretrained_model={_posix(pretrained)}",
        f"Global.character_dict_path={_posix(dict_path)}",
        f"Train.dataset.data_dir={_posix(corpus_dir)}",
        f"Train.dataset.label_file_list=[{_posix(Path(corpus_dir) / 'train.txt')}]",
        f"Eval.dataset.data_dir={_posix(corpus_dir)}",
        f"Eval.dataset.label_file_list=[{_posix(Path(corpus_dir) / 'validation.txt')}]",
        f"Train.loader.batch_size_per_card={int(batch_size)}",
        f"Eval.loader.batch_size_per_card={int(batch_size)}",
    ]


def build_export_command(
    *,
    vendor_repo: Path,
    checkpoint: Path,
    dict_path: Path,
    inference_dir: Path,
    config_relpath: str = DEFAULT_CONFIG_RELPATH,
) -> list[str]:
    return [
        str(Path(vendor_repo) / "tools" / "export_model.py"),
        "-c",
        str(Path(vendor_repo) / config_relpath),
        "-o",
        "Global.use_gpu=false",
        f"Global.pretrained_model={_posix(checkpoint)}",
        f"Global.character_dict_path={_posix(dict_path)}",
        f"Global.save_inference_dir={_posix(inference_dir)}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finetune and export the name-only rec model (CPU).")
    parser.add_argument("--corpus", required=True, help="Corpus dir containing train.txt/validation.txt/images/")
    parser.add_argument("--save-dir", required=True)
    parser.add_argument("--inference-dir", required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--vendor", default="training/vendor/PaddleOCR")
    parser.add_argument("--pretrained", default="training/vendor/PP-OCRv5_mobile_rec_pretrained")
    parser.add_argument("--dict", default="training/vendor/PaddleOCR/ppocr/utils/dict/ppocrv5_dict.txt")
    args = parser.parse_args(argv)

    train_command = [sys.executable] + build_train_command(
        vendor_repo=Path(args.vendor),
        corpus_dir=Path(args.corpus),
        save_dir=Path(args.save_dir),
        pretrained=Path(args.pretrained),
        dict_path=Path(args.dict),
        epochs=args.epochs,
        batch_size=args.batch_size,
    )
    subprocess.run(train_command, check=True)
    export_command = [sys.executable] + build_export_command(
        vendor_repo=Path(args.vendor),
        checkpoint=Path(args.save_dir) / "latest",
        dict_path=Path(args.dict),
        inference_dir=Path(args.inference_dir),
    )
    subprocess.run(export_command, check=True)
    print(f"exported: {args.inference_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
