from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from ocr_from2xlsx.ocr_plugin import (
    PluginManifest,
    build_request,
    load_manifest,
    parse_response,
    resolve_plugin_dir,
)
from ocr_from2xlsx.preprocess import PreparedPage

_PYTHON_PLACEHOLDER = "__PYTHON__"


class PluginExecutionError(RuntimeError):
    """Raised when the plugin subprocess fails or returns invalid output."""


def scan_doc_preprocess_env_overrides() -> dict[str, str] | None:
    value = os.environ.get("SCAN_DOC_PREPROCESS")
    if value is None or value.strip().lower() not in {"1", "true"}:
        return None
    return {"SCAN_DOC_PREPROCESS": value}


class PluginOcrBackend:
    def __init__(
        self,
        plugin_dir: Path | str,
        *,
        env_overrides: Mapping[str, str] | None = None,
    ) -> None:
        self.plugin_dir = Path(plugin_dir)
        self.manifest: PluginManifest = load_manifest(self.plugin_dir)
        self.env_overrides = dict(env_overrides or {})

    @classmethod
    def resolve(
        cls,
        explicit_dir: Path | str | None = None,
        default_dir: Path | str | None = None,
        *,
        env_overrides: Mapping[str, str] | None = None,
    ) -> "PluginOcrBackend":
        plugin_dir = resolve_plugin_dir(explicit_dir=explicit_dir, default_dir=default_dir)
        return cls(plugin_dir, env_overrides=env_overrides)

    def _command(self) -> list[str]:
        parts = [
            sys.executable if part == _PYTHON_PLACEHOLDER else part
            for part in self.manifest.command
        ]
        if parts:
            parts[0] = self._resolve_executable(parts[0])
        return parts

    def _resolve_executable(self, executable: str) -> str:
        # A relative path with directory parts (e.g. a bundled interpreter
        # "python\\Scripts\\python.exe") must be resolved against the plugin dir:
        # the OS resolves a relative executable against the parent process's cwd,
        # not the child's cwd. Absolute paths and bare names (PATH lookup) pass through.
        if Path(executable).is_absolute():
            return executable
        if "/" in executable or "\\" in executable:
            return str((self.plugin_dir / executable).resolve())
        return executable

    def extract(self, page: PreparedPage) -> dict[str, object]:
        request = build_request(
            template_id=page.template_id,
            image_path=str(Path(page.image_path).resolve()),
            document_name=Path(page.source.document_path or "").name,
            page_number=page.source.page_number or 0,
        )
        env = os.environ.copy()
        env.pop("SCAN_DOC_PREPROCESS", None)
        if self.env_overrides:
            env.update(self.env_overrides)
        try:
            completed = subprocess.run(
                self._command(),
                cwd=str(self.plugin_dir),
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except OSError as exc:
            raise PluginExecutionError(f"Failed to launch OCR plugin: {exc}") from exc
        if completed.returncode != 0:
            raise PluginExecutionError(
                f"OCR plugin exited with {completed.returncode}: {completed.stderr.strip()}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise PluginExecutionError(
                f"OCR plugin returned invalid JSON: {exc}; stderr={completed.stderr.strip()}"
            ) from exc
        return parse_response(payload)
