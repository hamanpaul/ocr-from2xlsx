from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx.ocr_plugin import (
    OCR_PLUGIN_CONTRACT_VERSION,
    PluginManifestError,
    PluginUnavailableError,
    build_request,
    load_manifest,
    parse_response,
    resolve_plugin_dir,
)


def test_build_request_has_contract_and_page() -> None:
    request = build_request(
        template_id="service_record.v1",
        image_path="/abs/page-0001.png",
        document_name="for testing only.pdf",
        page_number=1,
    )

    assert request == {
        "contract_version": OCR_PLUGIN_CONTRACT_VERSION,
        "template_id": "service_record.v1",
        "page": {
            "image_path": "/abs/page-0001.png",
            "document_name": "for testing only.pdf",
            "page_number": 1,
        },
    }


def test_parse_response_returns_record() -> None:
    payload = {
        "contract_version": OCR_PLUGIN_CONTRACT_VERSION,
        "record": {"name": "AI test", "service_date": "2026-05-26"},
    }

    record = parse_response(payload)

    assert record == {"name": "AI test", "service_date": "2026-05-26"}


def test_parse_response_rejects_wrong_contract_version() -> None:
    with pytest.raises(ValueError, match="contract_version"):
        parse_response({"contract_version": "nope", "record": {}})


def test_parse_response_requires_record_object() -> None:
    with pytest.raises(ValueError, match="record"):
        parse_response({"contract_version": OCR_PLUGIN_CONTRACT_VERSION, "record": "x"})


def test_resolve_plugin_dir_prefers_explicit_arg(tmp_path: Path, monkeypatch) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    monkeypatch.setenv("OCR_PLUGIN_DIR", str(env_dir))

    assert resolve_plugin_dir(explicit_dir=explicit) == explicit


def test_resolve_plugin_dir_uses_env_when_no_arg(tmp_path: Path, monkeypatch) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    monkeypatch.setenv("OCR_PLUGIN_DIR", str(env_dir))

    assert resolve_plugin_dir(explicit_dir=None) == env_dir


def test_resolve_plugin_dir_raises_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    missing = tmp_path / "nope"

    with pytest.raises(PluginUnavailableError):
        resolve_plugin_dir(explicit_dir=missing, default_dir=tmp_path / "also_missing")


def test_load_manifest_reads_command(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"contract_version":"ocr_plugin.v1","command":["python","main.py"]}',
        encoding="utf-8",
    )

    manifest = load_manifest(plugin_dir)

    assert manifest.command == ["python", "main.py"]


def test_load_manifest_rejects_missing_file(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()

    with pytest.raises(PluginManifestError, match="plugin.json"):
        load_manifest(plugin_dir)


def test_load_manifest_rejects_empty_command(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"contract_version":"ocr_plugin.v1","command":[]}', encoding="utf-8"
    )

    with pytest.raises(PluginManifestError, match="command"):
        load_manifest(plugin_dir)
