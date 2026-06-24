"""Assemble a portable Ollama + model bundle next to the app exe (release stage).

Copies the locally-installed Ollama runtime and ONLY the default model's blobs
(not other tags) into ``dist/vlm/`` so the shipped app can launch its own
``ollama serve`` against ``dist/vlm/models`` — no separate install needed.

This is a local copy (no download): it reuses the Ollama install + model store on
this machine. Run after `ollama pull qwen3-vl:2b`.

Usage:
    .venv/Scripts/python.exe build/build_vlm_runtime.py [--model qwen3-vl:2b]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OLLAMA_HOME = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
DEFAULT_MODELS = Path.home() / ".ollama" / "models"


def _manifest_path(models: Path, model: str) -> Path:
    name, _, tag = model.partition(":")
    tag = tag or "latest"
    return models / "manifests" / "registry.ollama.ai" / "library" / name / tag


def _blob_file(models: Path, digest: str) -> Path:
    return models / "blobs" / digest.replace(":", "-")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble portable Ollama+model bundle")
    parser.add_argument("--model", default="qwen3-vl:2b")
    parser.add_argument("--ollama-home", type=Path, default=DEFAULT_OLLAMA_HOME)
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    parser.add_argument("--out", type=Path, default=REPO / "dist" / "vlm")
    args = parser.parse_args()

    manifest_src = _manifest_path(args.models, args.model)
    if not manifest_src.is_file():
        print(f"error: model manifest not found: {manifest_src} (run `ollama pull {args.model}`)")
        return 2
    ollama_exe = args.ollama_home / "ollama.exe"
    if not ollama_exe.is_file():
        print(f"error: ollama runtime not found under {args.ollama_home}")
        return 2

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "models" / "blobs").mkdir(parents=True)

    # 1) runtime: copy ollama.exe + lib (GPU/CPU runners)
    shutil.copy2(ollama_exe, out / "ollama.exe")
    lib = args.ollama_home / "lib"
    if lib.is_dir():
        shutil.copytree(lib, out / "lib")

    # 2) model: manifest + its config + layer blobs only
    manifest = json.loads(manifest_src.read_text(encoding="utf-8"))
    digests = [manifest["config"]["digest"], *[layer["digest"] for layer in manifest["layers"]]]
    total = 0
    for digest in digests:
        src = _blob_file(args.models, digest)
        if not src.is_file():
            print(f"error: missing blob {src}")
            return 2
        shutil.copy2(src, out / "models" / "blobs" / src.name)
        total += src.stat().st_size
    dest_manifest = out / "models" / Path(*manifest_src.parts[manifest_src.parts.index("manifests"):])
    dest_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_src, dest_manifest)

    size_gb = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e9
    print(f"bundle ready: {out}  (model blobs {total/1e9:.2f}GB, total {size_gb:.2f}GB)")
    print(f"  app will launch: {out / 'ollama.exe'} serve  (OLLAMA_MODELS={out / 'models'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
