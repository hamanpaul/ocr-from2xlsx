"""Fetch the official PaddleOCR training repo (pinned tag) and pretrained rec weights."""
from __future__ import annotations

import argparse
import subprocess
import urllib.request
from pathlib import Path

DEFAULT_TAG = "v3.1.0"
DEFAULT_REPO_URL = "https://github.com/PaddlePaddle/PaddleOCR.git"
DEFAULT_WEIGHTS_URL = (
    "https://paddleocr.bj.bcebos.com/PP-OCRv5/chinese/PP-OCRv5_mobile_rec_pretrained.pdparams"
)
DEFAULT_CONFIG_RELPATH = "configs/rec/PP-OCRv5/PP-OCRv5_mobile_rec.yml"


def vendor_paths(training_dir: str | Path) -> dict[str, Path]:
    vendor = Path(training_dir) / "vendor"
    return {
        "vendor": vendor,
        "repo": vendor / "PaddleOCR",
        "weights": vendor / "PP-OCRv5_mobile_rec_pretrained.pdparams",
    }


def build_clone_command(repo_dir: Path, *, tag: str = DEFAULT_TAG, repo_url: str = DEFAULT_REPO_URL) -> list[str]:
    return ["git", "clone", "--depth", "1", "--branch", tag, repo_url, str(repo_dir)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch PaddleOCR trainer repo and pretrained rec weights.")
    parser.add_argument("--tag", default=DEFAULT_TAG, help="PaddleOCR repo tag to pin")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--weights-url", default=DEFAULT_WEIGHTS_URL)
    parser.add_argument("--training-dir", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args(argv)

    paths = vendor_paths(args.training_dir)
    paths["vendor"].mkdir(parents=True, exist_ok=True)
    if not paths["repo"].exists():
        subprocess.run(build_clone_command(paths["repo"], tag=args.tag, repo_url=args.repo_url), check=True)
    else:
        print(f"repo already present: {paths['repo']}")
    if not paths["weights"].exists():
        print(f"downloading {args.weights_url}")
        urllib.request.urlretrieve(args.weights_url, paths["weights"])
    else:
        print(f"weights already present: {paths['weights']}")
    config = paths["repo"] / DEFAULT_CONFIG_RELPATH
    print(f"config: {config} exists={config.exists()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
