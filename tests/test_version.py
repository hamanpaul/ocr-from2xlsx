from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

import ocr_from2xlsx


def _fixture_init_path(fixture_name: str) -> Path:
    return (
        Path(__file__).parent
        / "fixtures"
        / fixture_name
        / "src"
        / "ocr_from2xlsx"
        / "__init__.py"
    )


def test_resolve_version_prefers_version_file(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_init = _fixture_init_path("with_version")
    monkeypatch.setattr(ocr_from2xlsx, "__file__", str(fixture_init))
    monkeypatch.setattr(ocr_from2xlsx, "metadata_version", lambda _: "9.9.9")

    assert ocr_from2xlsx._resolve_version() == "1.2.3"


def test_resolve_version_raises_when_metadata_missing_and_version_file_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_init = _fixture_init_path("no_version")
    monkeypatch.setattr(ocr_from2xlsx, "__file__", str(fixture_init))

    def raise_missing_version(_: str) -> str:
        raise PackageNotFoundError("ocr-from2xlsx")

    monkeypatch.setattr(ocr_from2xlsx, "metadata_version", raise_missing_version)

    with pytest.raises(PackageNotFoundError):
        ocr_from2xlsx._resolve_version()
