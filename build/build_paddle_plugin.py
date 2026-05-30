"""Assemble a portable, offline PaddleOCR plugin bundle at dist/plugins/paddleocr/.

Bundle layout:
  dist/plugins/paddleocr/
    python/      copy of the paddle venv (.venv-paddle) — interpreter + paddleocr + deps
    models/official_models/<model>/   bundled mobile + textline models
    main.py, field_extract.py, mark_detect.py, plugin.json

Run with any python: `python build/build_paddle_plugin.py`
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_VENV = REPO / ".venv-paddle"
SRC_PLUGIN = REPO / "plugins" / "paddleocr"
MODELS_SRC = Path.home() / ".paddlex" / "official_models"
NEEDED_MODELS = ["PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec", "PP-LCNet_x1_0_textline_ori"]
OUT = REPO / "dist" / "plugins" / "paddleocr"


def _copy_models(dest_models: Path) -> None:
    for name in NEEDED_MODELS:
        src = MODELS_SRC / name
        if not src.is_dir():
            raise SystemExit(f"Missing model dir (run the plugin once to download it): {src}")
        shutil.copytree(src, dest_models / name, dirs_exist_ok=True)


def main() -> int:
    if not SRC_VENV.is_dir():
        raise SystemExit(f"Missing source venv: {SRC_VENV}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    print(f"copying venv {SRC_VENV} -> {OUT / 'python'} (large, please wait)")
    shutil.copytree(SRC_VENV, OUT / "python", dirs_exist_ok=True)
    _copy_models(OUT / "models" / "official_models")
    for name in ["main.py", "field_extract.py", "mark_detect.py", "plugin.json"]:
        shutil.copy2(SRC_PLUGIN / name, OUT / name)
    print(f"bundle ready: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
