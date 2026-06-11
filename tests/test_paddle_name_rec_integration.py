from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_plugin_main_namerec", _MODULE_PATH)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)


def _make_model_dir(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "inference.pdmodel").write_text("stub", encoding="utf-8")
    return path


def test_resolve_name_rec_dir_prefers_env_then_runtime_then_bundle(tmp_path: Path, monkeypatch) -> None:
    env_dir = _make_model_dir(tmp_path / "env-model")
    home = tmp_path / "home"
    runtime_dir = _make_model_dir(home / "name_rec")

    monkeypatch.setenv("NAME_REC_MODEL_DIR", str(env_dir))
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(home))
    monkeypatch.setattr(plugin_main, "_HERE", tmp_path / "no-bundle")
    assert plugin_main._resolve_name_rec_dir() == env_dir

    monkeypatch.delenv("NAME_REC_MODEL_DIR")
    assert plugin_main._resolve_name_rec_dir() == runtime_dir

    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path / "empty-home"))
    assert plugin_main._resolve_name_rec_dir() is None


def test_apply_name_suggestion_fills_name_only_when_non_empty() -> None:
    record = {"name": "", "ocr": {"warnings": []}}

    plugin_main.apply_name_suggestion(record, "王小明")
    assert record["name"] == "王小明"

    plugin_main.apply_name_suggestion(record, "")
    assert record["name"] == "王小明"

    plugin_main.apply_name_suggestion(record, None)
    assert record["name"] == "王小明"


def test_name_rec_failure_returns_none(monkeypatch, tmp_path: Path) -> None:
    model_dir = _make_model_dir(tmp_path / "model")

    def boom(_crop: str, _model_dir: str) -> str:
        raise OSError("broken model")

    monkeypatch.setattr(plugin_main, "_paddle_name_rec", boom)
    assert plugin_main.recognize_name_safe(str(tmp_path / "crop.png"), str(model_dir)) is None
