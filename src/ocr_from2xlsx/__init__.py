"""OCR-to-XLSX service-record import prototype."""

from importlib.metadata import version as metadata_version
from pathlib import Path


def _resolve_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return metadata_version("ocr-from2xlsx")


__version__ = _resolve_version()
