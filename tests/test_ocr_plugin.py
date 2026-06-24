from __future__ import annotations

import json
from pathlib import Path

import pytest

import ocr_from2xlsx.ocr_plugin as ocr_plugin_module
from ocr_from2xlsx.ocr_plugin import (
    OCR_PLUGIN_CONTRACT_VERSION,
    PluginManifestError,
    PluginUnavailableError,
    build_request,
    load_manifest,
    parse_response,
    resolve_plugin_dir,
)


def _write_manifest(plugin_dir: Path, command: list[str] | None = None) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    parts = command or ["python", "main.py"]
    (plugin_dir / "plugin.json").write_text(
        json.dumps(
            {"contract_version": "ocr_plugin.v1", "command": parts},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _set_module_file(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    module_file = repo_root / "src" / "ocr_from2xlsx" / "ocr_plugin.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ocr_plugin_module, "__file__", str(module_file))


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


def test_resolve_plugin_dir_prefers_built_bundle_in_source_checkout(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    _set_module_file(monkeypatch, repo_root)
    source_dir = repo_root / "plugins" / "paddleocr"
    _write_manifest(source_dir)
    built_dir = repo_root / "dist" / "plugins" / "paddleocr"
    _write_manifest(built_dir)

    assert resolve_plugin_dir(explicit_dir=None) == built_dir


def test_resolve_plugin_dir_in_source_mode_anchors_built_bundle_to_module_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    _set_module_file(monkeypatch, repo_root)
    built_dir = repo_root / "dist" / "plugins" / "paddleocr"
    _write_manifest(built_dir)

    assert resolve_plugin_dir(explicit_dir=None) == built_dir


def test_resolve_plugin_dir_falls_back_to_repo_source_plugin_when_bundle_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    _set_module_file(monkeypatch, repo_root)
    source_dir = repo_root / "plugins" / "paddleocr"
    _write_manifest(source_dir)

    assert resolve_plugin_dir(explicit_dir=None) == source_dir


def test_resolve_plugin_dir_in_source_mode_falls_back_to_repo_plugin_from_other_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    _set_module_file(monkeypatch, repo_root)
    source_dir = repo_root / "plugins" / "paddleocr"
    _write_manifest(source_dir)

    assert resolve_plugin_dir(explicit_dir=None) == source_dir


def test_resolve_plugin_dir_falls_back_to_repo_source_when_bundle_has_no_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    repo_root = tmp_path / "repo"
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    _set_module_file(monkeypatch, repo_root)
    source_dir = repo_root / "plugins" / "paddleocr"
    _write_manifest(source_dir)
    (repo_root / "dist" / "plugins" / "paddleocr").mkdir(parents=True)

    assert resolve_plugin_dir(explicit_dir=None) == source_dir


def test_resolve_plugin_dir_env_override_beats_detected_bundles(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    (tmp_path / "plugins" / "paddleocr").mkdir(parents=True)
    (tmp_path / "dist" / "plugins" / "paddleocr").mkdir(parents=True)
    monkeypatch.setenv("OCR_PLUGIN_DIR", str(env_dir))

    assert resolve_plugin_dir(explicit_dir=None) == env_dir


def test_resolve_plugin_dir_raises_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    missing = tmp_path / "nope"

    with pytest.raises(PluginUnavailableError):
        resolve_plugin_dir(explicit_dir=missing, default_dir=tmp_path / "also_missing")


def test_repo_source_plugin_manifest_uses_python_placeholder() -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "plugins" / "paddleocr")

    assert manifest.command == ["__PYTHON__", "main.py"]


def test_load_manifest_reads_command(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"contract_version":"ocr_plugin.v1","command":["python","main.py"]}',
        encoding="utf-8",
    )

    manifest = load_manifest(plugin_dir)

    assert manifest.command == ["python", "main.py"]
    assert manifest.contract_version == "ocr_plugin.v1"


def test_load_manifest_rejects_missing_file(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()

    with pytest.raises(PluginManifestError, match="plugin.json"):
        load_manifest(plugin_dir)


def test_load_manifest_rejects_wrong_contract_version(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"contract_version":"ocr_plugin.v9","command":["python","main.py"]}',
        encoding="utf-8",
    )

    with pytest.raises(PluginManifestError, match="contract_version"):
        load_manifest(plugin_dir)


def test_resolve_plugin_dir_raises_when_env_points_to_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OCR_PLUGIN_DIR", str(tmp_path / "gone"))

    with pytest.raises(PluginUnavailableError):
        resolve_plugin_dir(explicit_dir=None)


def test_load_manifest_rejects_empty_command(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"contract_version":"ocr_plugin.v1","command":[]}', encoding="utf-8"
    )

    with pytest.raises(PluginManifestError, match="command"):
        load_manifest(plugin_dir)
