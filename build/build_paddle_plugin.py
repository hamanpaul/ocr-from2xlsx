"""Assemble a portable, offline PaddleOCR plugin bundle at dist/plugins/paddleocr/.

Bundle layout:
  dist/plugins/paddleocr/
    python/      copy of the paddle venv (.venv-paddle) — interpreter + paddleocr + deps
    models/official_models/<model>/   bundled mobile + textline models
    main.py, field_extract.py, mark_detect.py, mark_model.py, crop_provider.py, plugin.json

Run with any python: `python build/build_paddle_plugin.py`
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_VENV = REPO / ".venv-paddle"
SRC_PLUGIN = REPO / "plugins" / "paddleocr"
MODELS_SRC = Path.home() / ".paddlex" / "official_models"
NEEDED_MODELS = ["PP-OCRv5_mobile_det", "PP-OCRv5_mobile_rec", "PP-LCNet_x1_0_textline_ori"]
OUT = REPO / "dist" / "plugins" / "paddleocr"
SOURCE_PYTHON_PLACEHOLDER = "__PYTHON__"
BUNDLED_PYTHON = "python\\Scripts\\python.exe"


def _copy_models(dest_models: Path) -> None:
    for name in NEEDED_MODELS:
        src = MODELS_SRC / name
        if not src.is_dir():
            raise SystemExit(f"Missing model dir (run the plugin once to download it): {src}")
        shutil.copytree(src, dest_models / name, dirs_exist_ok=True)


def _copy_manifest() -> None:
    manifest_path = SRC_PLUGIN / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    command = manifest.get("command")
    if isinstance(command, list) and command and command[0] == SOURCE_PYTHON_PLACEHOLDER:
        manifest["command"] = [BUNDLED_PYTHON, *command[1:]]
    (OUT / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if not SRC_VENV.is_dir():
        raise SystemExit(f"Missing source venv: {SRC_VENV}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    print(f"copying venv {SRC_VENV} -> {OUT / 'python'} (large, please wait)")
    shutil.copytree(SRC_VENV, OUT / "python", dirs_exist_ok=True)
    _copy_models(OUT / "models" / "official_models")
    for name in [
        "main.py",
        "field_extract.py",
        "mark_detect.py",
        "name_crop.py",
        "mark_features.py",
        "mark_model.py",
        "crop_provider.py",
    ]:
        shutil.copy2(SRC_PLUGIN / name, OUT / name)
    _copy_manifest()
    for name in ["template_boxes.json", "mark_model.json"]:
        src = SRC_PLUGIN / name
        if src.exists():
            shutil.copy2(src, OUT / name)
    name_rec_src = SRC_PLUGIN / "name_rec"
    if name_rec_src.is_dir():
        shutil.copytree(name_rec_src, OUT / "name_rec", dirs_exist_ok=True)
    print(f"bundle ready: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
