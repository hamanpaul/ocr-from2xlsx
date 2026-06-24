from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_plugin_docpre", _MODULE_PATH)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)


def test_docpre_model_availability_requires_both_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    cache_home = tmp_path / "models"
    official_models = cache_home / "official_models"
    monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(cache_home))
    official_models.mkdir(parents=True)

    assert plugin_main._doc_preprocess_models_available() is False

    for name in plugin_main._DOC_PREPROCESS_MODEL_NAMES[:-1]:
        model_dir = official_models / name
        model_dir.mkdir()
        (model_dir / "marker.txt").write_text("ok", encoding="utf-8")
        assert plugin_main._doc_preprocess_models_available() is False

    model_dir = official_models / plugin_main._DOC_PREPROCESS_MODEL_NAMES[-1]
    model_dir.mkdir()
    (model_dir / "marker.txt").write_text("ok", encoding="utf-8")

    assert plugin_main._doc_preprocess_models_available() is True


def test_docpre_enabled_requires_opt_in_and_required_models(monkeypatch) -> None:
    monkeypatch.delenv("SCAN_DOC_PREPROCESS", raising=False)
    monkeypatch.setattr(plugin_main, "_doc_preprocess_models_available", lambda: True)

    assert plugin_main._doc_preprocess_enabled() is False

    monkeypatch.setenv("SCAN_DOC_PREPROCESS", "1")
    monkeypatch.setattr(plugin_main, "_doc_preprocess_models_available", lambda: False)

    assert plugin_main._doc_preprocess_enabled() is False

    monkeypatch.setattr(plugin_main, "_doc_preprocess_models_available", lambda: True)

    assert plugin_main._doc_preprocess_enabled() is True


def test_paddle_ocr_fn_only_enables_doc_flags_when_opted_in_and_models_available(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def predict(self, image_path: str):
            return []

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=FakePaddleOCR))
    monkeypatch.delenv("SCAN_DOC_PREPROCESS", raising=False)

    plugin_main._paddle_ocr_fn("ignored.png")

    assert calls[-1]["use_doc_orientation_classify"] is False
    assert calls[-1]["use_doc_unwarping"] is False
    assert calls[-1]["use_textline_orientation"] is True

    monkeypatch.setenv("SCAN_DOC_PREPROCESS", "true")
    monkeypatch.setattr(plugin_main, "_doc_preprocess_models_available", lambda: False)

    plugin_main._paddle_ocr_fn("ignored.png")

    assert calls[-1]["use_doc_orientation_classify"] is False
    assert calls[-1]["use_doc_unwarping"] is False
    assert calls[-1]["use_textline_orientation"] is True

    monkeypatch.setattr(plugin_main, "_doc_preprocess_models_available", lambda: True)

    plugin_main._paddle_ocr_fn("ignored.png")

    assert calls[-1]["use_doc_orientation_classify"] is True
    assert calls[-1]["use_doc_unwarping"] is True
    assert calls[-1]["use_textline_orientation"] is True
