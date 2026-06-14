from __future__ import annotations

import json
from pathlib import Path

import build.build_paddle_plugin as build_paddle_plugin


def test_build_bundle_includes_runtime_modules(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    src_plugin = repo / "plugins" / "paddleocr"
    src_plugin.mkdir(parents=True)
    (src_plugin / "main.py").write_text("main", encoding="utf-8")
    (src_plugin / "field_extract.py").write_text("field", encoding="utf-8")
    (src_plugin / "mark_detect.py").write_text("mark", encoding="utf-8")
    (src_plugin / "name_crop.py").write_text("crop", encoding="utf-8")
    (src_plugin / "mark_features.py").write_text("features", encoding="utf-8")
    (src_plugin / "mark_model.py").write_text("model", encoding="utf-8")
    (src_plugin / "crop_provider.py").write_text("provider", encoding="utf-8")
    (src_plugin / "template_boxes.json").write_text("{}", encoding="utf-8")
    (src_plugin / "mark_model.json").write_text("{}", encoding="utf-8")
    (src_plugin / "name_rec").mkdir()
    (src_plugin / "name_rec" / "inference.pdmodel").write_text("name-rec", encoding="utf-8")
    (src_plugin / "plugin.json").write_text(
        json.dumps(
            {
                "contract_version": "ocr_plugin.v1",
                "command": ["__PYTHON__", "main.py"],
            }
        ),
        encoding="utf-8",
    )

    src_venv = repo / ".venv-paddle"
    src_venv.mkdir()
    models_src = tmp_path / "models"
    for name in build_paddle_plugin.NEEDED_MODELS:
        (models_src / name).mkdir(parents=True)

    out = tmp_path / "dist" / "plugins" / "paddleocr"

    monkeypatch.setattr(build_paddle_plugin, "REPO", repo)
    monkeypatch.setattr(build_paddle_plugin, "SRC_VENV", src_venv)
    monkeypatch.setattr(build_paddle_plugin, "SRC_PLUGIN", src_plugin)
    monkeypatch.setattr(build_paddle_plugin, "MODELS_SRC", models_src)
    monkeypatch.setattr(build_paddle_plugin, "OUT", out)

    assert build_paddle_plugin.main() == 0
    assert (out / "mark_detect.py").exists()
    assert (out / "name_crop.py").exists()
    assert (out / "mark_features.py").exists()
    assert (out / "mark_model.py").exists()
    assert (out / "crop_provider.py").exists()
    assert (out / "template_boxes.json").exists()
    assert (out / "mark_model.json").exists()
    assert (out / "name_rec" / "inference.pdmodel").exists()
    assert json.loads((out / "plugin.json").read_text(encoding="utf-8"))["command"] == [
        "python\\Scripts\\python.exe",
        "main.py",
    ]
