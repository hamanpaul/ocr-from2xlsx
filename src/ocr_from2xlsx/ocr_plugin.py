from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OCR_PLUGIN_CONTRACT_VERSION = "ocr_plugin.v1"
DEFAULT_PLUGIN_SUBDIR = Path("plugins") / "paddleocr"
MANIFEST_NAME = "plugin.json"


class PluginUnavailableError(RuntimeError):
    """Raised when no OCR plugin directory can be located."""


class PluginManifestError(RuntimeError):
    """Raised when a plugin directory has no valid manifest."""


@dataclass(slots=True)
class PluginManifest:
    contract_version: str
    command: list[str]


def build_request(
    template_id: str, image_path: str, document_name: str, page_number: int
) -> dict[str, Any]:
    return {
        "contract_version": OCR_PLUGIN_CONTRACT_VERSION,
        "template_id": template_id,
        "page": {
            "image_path": image_path,
            "document_name": document_name,
            "page_number": page_number,
        },
    }


def parse_response(payload: dict[str, Any]) -> dict[str, Any]:
    version = payload.get("contract_version")
    if version != OCR_PLUGIN_CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported plugin contract_version: {version!r}; "
            f"expected {OCR_PLUGIN_CONTRACT_VERSION!r}"
        )
    record = payload.get("record")
    if not isinstance(record, dict):
        raise ValueError("Plugin response 'record' must be an object")
    return record


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def resolve_plugin_dir(
    explicit_dir: Path | str | None = None,
    default_dir: Path | str | None = None,
) -> Path:
    if explicit_dir is not None:
        candidate = Path(explicit_dir)
        if candidate.is_dir():
            return candidate
        raise PluginUnavailableError(f"Plugin directory not found: {candidate}")

    env_value = os.environ.get("OCR_PLUGIN_DIR")
    if env_value:
        candidate = Path(env_value)
        if candidate.is_dir():
            return candidate
        raise PluginUnavailableError(
            f"OCR_PLUGIN_DIR points to a missing directory: {candidate}"
        )

    default_candidate = (
        Path(default_dir) if default_dir is not None else _app_base_dir() / DEFAULT_PLUGIN_SUBDIR
    )
    if default_candidate.is_dir():
        return default_candidate
    raise PluginUnavailableError(
        "No OCR plugin found. Pass --ocr-plugin-dir, set OCR_PLUGIN_DIR, "
        f"or install the plugin at {default_candidate}."
    )


def load_manifest(plugin_dir: Path | str) -> PluginManifest:
    manifest_path = Path(plugin_dir) / MANIFEST_NAME
    if not manifest_path.is_file():
        raise PluginManifestError(f"Missing {MANIFEST_NAME} in plugin: {plugin_dir}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginManifestError(f"Invalid {MANIFEST_NAME}: {exc}") from exc
    command = data.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(part, str) for part in command
    ):
        raise PluginManifestError(
            f"{MANIFEST_NAME} 'command' must be a non-empty list of strings"
        )
    return PluginManifest(
        contract_version=str(data.get("contract_version") or ""),
        command=[str(part) for part in command],
    )
