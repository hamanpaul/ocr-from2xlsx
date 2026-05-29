from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.ocr_plugin import PluginManifestError, PluginUnavailableError
from ocr_from2xlsx.plugin_backend import PluginOcrBackend
from ocr_from2xlsx.preprocess import PreparedPage

_FIXTURE = Path(__file__).parent / "fixtures" / "plugin"


def _prepared_page(tmp_path: Path) -> PreparedPage:
    image_path = tmp_path / "for testing only-page-0001.png"
    image_path.write_bytes(b"\x89PNG\r\n")
    return PreparedPage(
        image_path=image_path,
        template_id="service_record.v1",
        source=SourceInfo(
            kind="pdf_page",
            document_path="tests/fixtures/pdf/for testing only.pdf",
            page_number=1,
            preprocessed_image_path=image_path.name,
            template_id="service_record.v1",
        ),
    )


def _install_plugin(tmp_path: Path, script: str = "echo_plugin.py") -> Path:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    shutil.copy(_FIXTURE / script, plugin_dir / script)
    command = [sys.executable, script]
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"contract_version": "ocr_plugin.v1", "command": command}),
        encoding="utf-8",
    )
    return plugin_dir


def test_extract_returns_record_from_plugin(tmp_path: Path) -> None:
    plugin_dir = _install_plugin(tmp_path)
    backend = PluginOcrBackend(plugin_dir)

    record = backend.extract(_prepared_page(tmp_path))

    assert record["name"] == "Plugin Echo"
    assert record["medical_record_no"] == "PLUGIN-OK"
    assert record["record_id"] == "plugin-0001"


def test_resolve_raises_when_no_plugin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)

    with pytest.raises(PluginUnavailableError):
        PluginOcrBackend.resolve(
            explicit_dir=None, default_dir=tmp_path / "missing"
        )


def test_resolve_finds_explicit_dir(tmp_path: Path) -> None:
    plugin_dir = _install_plugin(tmp_path)

    backend = PluginOcrBackend.resolve(explicit_dir=plugin_dir)

    assert backend.extract(_prepared_page(tmp_path))["name"] == "Plugin Echo"


def test_extract_raises_on_plugin_failure(tmp_path: Path) -> None:
    plugin_dir = _install_plugin(tmp_path, script="bad_exit_plugin.py")
    backend = PluginOcrBackend(plugin_dir)

    with pytest.raises(RuntimeError, match="boom: plugin failed"):
        backend.extract(_prepared_page(tmp_path))


def test_constructor_raises_without_manifest(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "empty"
    plugin_dir.mkdir()

    with pytest.raises(PluginManifestError):
        PluginOcrBackend(plugin_dir)


def test_extract_uses_committed_fixture_manifest_with_python_placeholder(tmp_path: Path) -> None:
    # Exercises the committed fixture plugin.json (command uses the "__PYTHON__" placeholder),
    # confirming PluginOcrBackend substitutes sys.executable and round-trips.
    backend = PluginOcrBackend(_FIXTURE)

    record = backend.extract(_prepared_page(tmp_path))

    assert record["name"] == "Plugin Echo"
