from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import copyfileobj
from urllib.request import urlopen

GOOGLE_FONTS_COMMIT = "fafaa09e4abf799c185f85e9b6eacb7db31ca5ed"


@dataclass(frozen=True, slots=True)
class FontSource:
    family: str
    filename: str
    repo_path: str
    license_path: str

    @property
    def download_url(self) -> str:
        return f"https://raw.githubusercontent.com/google/fonts/{GOOGLE_FONTS_COMMIT}/{self.repo_path}"

    @property
    def license_url(self) -> str:
        return f"https://raw.githubusercontent.com/google/fonts/{GOOGLE_FONTS_COMMIT}/{self.license_path}"


CURATED_HANDWRITING_FONTS: tuple[FontSource, ...] = (
    FontSource(
        family="Architects Daughter",
        filename="ArchitectsDaughter-Regular.ttf",
        repo_path="ofl/architectsdaughter/ArchitectsDaughter-Regular.ttf",
        license_path="ofl/architectsdaughter/OFL.txt",
    ),
    FontSource(
        family="Caveat",
        filename="Caveat[wght].ttf",
        repo_path="ofl/caveat/Caveat[wght].ttf",
        license_path="ofl/caveat/OFL.txt",
    ),
    FontSource(
        family="Gloria Hallelujah",
        filename="GloriaHallelujah.ttf",
        repo_path="ofl/gloriahallelujah/GloriaHallelujah.ttf",
        license_path="ofl/gloriahallelujah/OFL.txt",
    ),
    FontSource(
        family="Indie Flower",
        filename="IndieFlower-Regular.ttf",
        repo_path="ofl/indieflower/IndieFlower-Regular.ttf",
        license_path="ofl/indieflower/OFL.txt",
    ),
    FontSource(
        family="Shadows Into Light",
        filename="ShadowsIntoLight.ttf",
        repo_path="ofl/shadowsintolight/ShadowsIntoLight.ttf",
        license_path="ofl/shadowsintolight/OFL.txt",
    ),
)


def _fonts_dir() -> Path:
    return Path(__file__).resolve().parent / "fonts"


def _download(url: str, destination: Path) -> None:
    with urlopen(url) as response, destination.open("wb") as handle:
        copyfileobj(response, handle)


def write_sources(fonts_dir: Path, sources: tuple[FontSource, ...] = CURATED_HANDWRITING_FONTS) -> Path:
    lines = [
        "# Curated handwriting font sources",
        "",
        "Downloaded by `training/fetch_fonts.py` from the Google Fonts repository.",
        "",
        "| Family | File | Font URL | License |",
        "| --- | --- | --- | --- |",
    ]
    for source in sources:
        lines.append(
            f"| {source.family} | {source.filename} | {source.download_url} | {source.license_url} |"
        )
    target = fonts_dir / "SOURCES.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main() -> int:
    fonts_dir = _fonts_dir()
    fonts_dir.mkdir(parents=True, exist_ok=True)

    for source in CURATED_HANDWRITING_FONTS:
        destination = fonts_dir / source.filename
        if destination.exists():
            print(f"skipping {source.filename}")
            continue
        print(f"downloading {source.filename}")
        _download(source.download_url, destination)

    write_sources(fonts_dir)
    print(f"wrote {fonts_dir / 'SOURCES.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
