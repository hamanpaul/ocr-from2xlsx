from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
SPEC_PATH = BUILD_DIR / "ocr-from2xlsx.spec"
EXE_PATH = DIST_DIR / "ocr-from2xlsx.exe"
README_PATH = ROOT / "README.md"
HELP_MARKER = "ocr-from2xlsx-help"


def _clean_dir(path: Path, *, keep: set[str] | None = None) -> None:
    if not path.exists():
        return
    for entry in path.iterdir():
        if keep and entry.name in keep:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _clean_egg_info(root: Path) -> None:
    for entry in root.glob("*.egg-info"):
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _extract_help_block(readme_text: str, marker: str) -> str:
    begin = f'<!-- BEGIN: cli-help marker="{marker}" -->'
    end = f'<!-- END: cli-help marker="{marker}" -->'
    start_index = readme_text.find(begin)
    if start_index == -1:
        raise ValueError(f"README help marker start not found: {marker}")
    start_index += len(begin)
    end_index = readme_text.find(end, start_index)
    if end_index == -1:
        raise ValueError(f"README help marker end not found: {marker}")
    block = readme_text[start_index:end_index]
    return block.strip("\n")


def _normalize_help_output(output: str) -> str:
    return output.replace("\r\n", "\n").strip("\n")


def main() -> int:
    try:
        # Keep the portable VLM model bundle AND the PaddleOCR plugin (the default OCR
        # engine) so re-packaging does not wipe them.
        _clean_dir(DIST_DIR, keep={"vlm", "plugins"})
        _clean_dir(
            BUILD_DIR,
            keep={
                "package.py",
                "ocr-from2xlsx.spec",
                "build_paddle_plugin.py",
                "build_vlm_runtime.py",
                "make_shutter_wav.py",
                "phase0_vlm_bakeoff.py",
                "splash.png",
            },
        )
        _clean_egg_info(ROOT)
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", str(SPEC_PATH)],
            cwd=ROOT,
            check=True,
        )
        if not EXE_PATH.is_file():
            raise FileNotFoundError(f"Expected executable missing: {EXE_PATH}")
        # Ship the default OCR engine (PaddleOCR plugin) beside the exe. Build it if missing
        # and the paddle venv is present; otherwise warn (the app falls back to the VLM).
        plugin_dir = DIST_DIR / "plugins" / "paddleocr"
        if not plugin_dir.is_dir():
            if (ROOT / ".venv-paddle").is_dir():
                print("building PaddleOCR plugin bundle (dist/plugins/paddleocr) ...")
                subprocess.run(
                    [sys.executable, str(BUILD_DIR / "build_paddle_plugin.py")],
                    cwd=ROOT,
                    check=True,
                )
            else:
                print(
                    "WARNING: dist/plugins/paddleocr missing and .venv-paddle not found — "
                    "the packaged app will fall back to the (slow) VLM. Run "
                    "build/build_paddle_plugin.py to ship PaddleOCR as the default engine."
                )
        help_result = subprocess.run(
            [str(EXE_PATH), "--help"],
            capture_output=True,
            check=False,
        )
        if help_result.returncode != 0:
            raise RuntimeError(f"Help command failed with code {help_result.returncode}")
        help_output = help_result.stdout.decode("utf-8", errors="replace")
        if "\r\n" in help_output:
            raise RuntimeError("Help output contains CRLF line endings")
        readme_text = README_PATH.read_text(encoding="utf-8")
        expected_help = _normalize_help_output(_extract_help_block(readme_text, HELP_MARKER))
        actual_help = _normalize_help_output(help_output)
        if actual_help != expected_help:
            raise RuntimeError("Help output does not match README marker block")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
