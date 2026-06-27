"""Recognition backend selection (#61 outcome): the app defaults to the PaddleOCR
plugin (fast, reads structured fields); the VLM is opt-in via OCR_BACKEND=vision."""
from __future__ import annotations

import pytest

import ocr_from2xlsx.cli as cli
import ocr_from2xlsx.plugin_backend as plugin_backend
import ocr_from2xlsx.recognition.vlm_server as vlm_server
from ocr_from2xlsx.app import ReviewApp
from ocr_from2xlsx.ocr_plugin import PluginUnavailableError


def _app():
    return ReviewApp.__new__(ReviewApp)


def _set_plugin(monkeypatch, result):
    def _resolve(cls, *a, **k):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(plugin_backend.PluginOcrBackend, "resolve", classmethod(_resolve))


def _set_vision(monkeypatch, available=True):
    monkeypatch.setattr(vlm_server, "vision_runtime_available", lambda *_a, **_k: available)
    monkeypatch.setattr(vlm_server, "ensure_server", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "_build_vision_backend", lambda *_a, **_k: "VISION")


def test_default_prefers_paddle_plugin(monkeypatch):
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    _set_plugin(monkeypatch, "PLUGIN")
    _set_vision(monkeypatch, available=True)  # available, but plugin must win by default
    assert _app()._resolve_recognition_backend(None, None) == "PLUGIN"


def test_vision_is_opt_in(monkeypatch):
    monkeypatch.setenv("OCR_BACKEND", "vision")
    _set_plugin(monkeypatch, "PLUGIN")
    _set_vision(monkeypatch, available=True)
    assert _app()._resolve_recognition_backend(None, None) == "VISION"


def test_default_falls_back_to_vision_when_plugin_missing(monkeypatch):
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    _set_plugin(monkeypatch, PluginUnavailableError("no plugin"))
    _set_vision(monkeypatch, available=True)
    assert _app()._resolve_recognition_backend(None, None) == "VISION"


def test_explicit_plugin_surfaces_error_when_missing(monkeypatch):
    monkeypatch.setenv("OCR_BACKEND", "plugin")
    _set_plugin(monkeypatch, PluginUnavailableError("no plugin"))
    _set_vision(monkeypatch, available=True)  # must NOT silently fall back when forced
    with pytest.raises(PluginUnavailableError):
        _app()._resolve_recognition_backend(None, None)


def test_default_reraises_when_plugin_missing_and_no_vision(monkeypatch):
    monkeypatch.delenv("OCR_BACKEND", raising=False)
    _set_plugin(monkeypatch, PluginUnavailableError("no plugin"))
    _set_vision(monkeypatch, available=False)
    with pytest.raises(PluginUnavailableError):
        _app()._resolve_recognition_backend(None, None)
