from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Callable

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.json_io import load_batch


@dataclass(frozen=True, slots=True)
class PdfPage:
    document_path: Path
    page_number: int
    width_points: float
    height_points: float


class JsonRecordSource:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def records(self) -> Iterator[Record]:
        yield from load_batch(self.path).records


class ImageFolderSource:
    _extensions = {".png", ".jpg", ".jpeg", ".bmp"}

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)

    def image_paths(self) -> list[Path]:
        paths = [
            path
            for path in self.folder.iterdir()
            if path.is_file() and path.suffix.lower() in self._extensions
        ]
        return sorted(paths, key=lambda path: (path.name.casefold(), path.name))


class PdfDocumentSource:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def pages(self) -> list[PdfPage]:
        from pypdf import PdfReader

        reader = PdfReader(str(self.path))
        pages: list[PdfPage] = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append(
                PdfPage(
                    document_path=self.path,
                    page_number=index,
                    width_points=float(page.mediabox.width),
                    height_points=float(page.mediabox.height),
                )
            )
        return pages


class UvcCameraSource:
    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index

    def is_available(self) -> bool:
        try:
            import cv2
        except ImportError:
            return False
        capture = cv2.VideoCapture(self.camera_index)
        try:
            return bool(capture.isOpened())
        finally:
            capture.release()


def _default_camera_opener(index: int) -> bool:
    try:
        import cv2
    except ImportError:
        return False
    capture = cv2.VideoCapture(index)
    try:
        return bool(capture.isOpened())
    finally:
        capture.release()


def enumerate_cameras(
    max_probe: int = 5,
    opener: Callable[[int], bool] | None = None,
) -> list[int]:
    """Probe indices 0..max_probe-1 and return those that open. opener is injectable for tests."""
    probe = opener if opener is not None else _default_camera_opener
    return [index for index in range(max_probe) if probe(index)]


def decide_camera_selection(indices: list[int]) -> tuple:
    """Pure decision: () -> none, single -> auto, multiple -> choose."""
    if not indices:
        return ("none",)
    if len(indices) == 1:
        return ("auto", indices[0])
    return ("choose", tuple(indices))
