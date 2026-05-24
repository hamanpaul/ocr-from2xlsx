from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

import ocr_from2xlsx


def test_resolve_version_raises_when_version_file_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_init = (
        Path(__file__).parent / "fixtures" / "no_version" / "pkg" / "__init__.py"
    )
    monkeypatch.setattr(ocr_from2xlsx, "__file__", str(fixture_init))

    def raise_missing_version(_: str) -> str:
        raise PackageNotFoundError("ocr-from2xlsx")

    monkeypatch.setattr(ocr_from2xlsx, "metadata_version", raise_missing_version)

    with pytest.raises(FileNotFoundError):
        ocr_from2xlsx._resolve_version()
