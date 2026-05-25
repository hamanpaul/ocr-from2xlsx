"""OCR-to-XLSX service-record import prototype."""

import sys
from importlib.metadata import PackageNotFoundError, version as metadata_version
from pathlib import Path


def _resolve_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        version_file = Path(meipass) / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    try:
        return metadata_version("ocr-from2xlsx")
    except PackageNotFoundError:
        if meipass:
            return "0.0.0"
        raise


__version__ = _resolve_version()
