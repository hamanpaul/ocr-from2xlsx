"""OCR-to-XLSX service-record import prototype."""

from importlib.metadata import PackageNotFoundError, version as metadata_version
from pathlib import Path


def _resolve_version() -> str:
    try:
        return metadata_version("ocr-from2xlsx")
    except PackageNotFoundError:
        version_file = Path(__file__).resolve().parents[2] / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return "0.0.0"


__version__ = _resolve_version()
