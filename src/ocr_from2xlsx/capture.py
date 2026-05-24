from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.json_io import load_batch


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
