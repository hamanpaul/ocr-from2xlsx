"""Locate and launch a bundled Ollama runtime for the vision backend.

A portable release ships the app exe next to a ``vlm/`` folder holding
``ollama(.exe)`` + a ``models/`` store with only the default model. On startup the
vision path calls :func:`ensure_server`: if nothing answers at the configured host
it launches the bundled ``ollama serve`` (with ``OLLAMA_MODELS`` pointed at the
bundled store). Everything degrades to a no-op when no runtime is bundled and no
server is already running, so the app still works for manual entry.

Resolution order mirrors the mark/name model pattern: explicit env override →
user runtime (``OCR_FROM2XLSX_HOME``) → bundled (next to the exe / repo ``dist``).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_EXE_NAME = "ollama.exe" if os.name == "nt" else "ollama"


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3] / "dist"


def _default_roots() -> list[Path]:
    roots: list[Path] = []
    home = os.environ.get("OCR_FROM2XLSX_HOME")
    if home:
        roots.append(Path(home))
    roots.append(Path.home() / ".ocr_from2xlsx")
    roots.append(_bundle_root())
    return roots


def resolve_ollama(roots: list[Path] | None = None) -> tuple[Path | None, Path | None]:
    """Return ``(ollama_exe, models_dir)`` using env → user → bundle, else ``(None, None)``.

    ``roots`` (when given) replaces the default search roots entirely — used by tests
    to stay hermetic regardless of any real ``dist/vlm`` bundle on this machine.
    """
    env_exe = os.environ.get("OCR_VLM_OLLAMA_EXE")
    if env_exe and Path(env_exe).is_file():
        env_models = os.environ.get("OCR_VLM_OLLAMA_MODELS")
        models = Path(env_models) if env_models and Path(env_models).is_dir() else None
        return Path(env_exe), models
    for root in (roots if roots is not None else _default_roots()):
        candidate = root / "vlm" / _EXE_NAME
        if candidate.is_file():
            models = root / "vlm" / "models"
            return candidate, (models if models.is_dir() else None)
    return None, None


def server_is_up(host: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 - any failure means "not reachable"
        return False


def vision_runtime_available(host: str) -> bool:
    """True when vision recognition can run: a server is already up, or a bundled
    runtime is resolvable (so the app can launch one). Lets the shipped exe default
    to vision without an env flag."""
    if server_is_up(host):
        return True
    exe, _ = resolve_ollama()
    return exe is not None


def ensure_server(host: str, *, wait_seconds: float = 30.0) -> subprocess.Popen | None:
    """Ensure a server answers at ``host``; launch the bundled one if needed.

    Returns the spawned process (so the caller can terminate it), or ``None`` when a
    server was already up or no bundled runtime is available.
    """
    if server_is_up(host):
        return None
    exe, models = resolve_ollama()
    if exe is None:
        return None
    env = dict(os.environ)
    if models is not None:
        env["OLLAMA_MODELS"] = str(models)
    try:
        proc = subprocess.Popen(
            [str(exe), "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if server_is_up(host):
            return proc
        if proc.poll() is not None:
            return None  # the server exited before coming up
        time.sleep(0.5)
    return proc
