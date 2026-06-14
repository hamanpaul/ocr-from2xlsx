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
            cv2 = _import_cv2()
        except CameraDependencyError:
            return False
        capture = _open_camera_capture(cv2, self.camera_index)
        if capture is None:
            return False
        try:
            return True
        finally:
            capture.release()


def _camera_backends(cv2: object) -> list[int | None]:
    backends: list[int | None] = [None]
    directshow = getattr(cv2, "CAP_DSHOW", None)
    if directshow is not None:
        backends.append(directshow)
    return backends


def _enumeration_backend(cv2: object) -> int | None:
    # Enumeration probes several indices, so it must be fast AND reliable. On Windows
    # the default (MSMF) backend blocks for seconds on absent indices and is flaky for
    # index-based access (cameras reported "not found"); DirectShow opens present
    # indices quickly and fails absent ones instantly. Probe with DirectShow when it
    # is available, falling back to the default backend on other platforms.
    return getattr(cv2, "CAP_DSHOW", None)


DEFAULT_CAMERA_PROBE_READS = 8
DEFAULT_CAMERA_STARTUP_READS = 80
CAMERA_SUPPORT_INSTALL_GUIDANCE = "pip install .[camera] or pip install opencv-python"
CAMERA_DEPENDENCY_MESSAGE = (
    "OpenCV is not installed. "
    f"Install camera support with: {CAMERA_SUPPORT_INSTALL_GUIDANCE}"
)


class CameraDependencyError(RuntimeError):
    """Raised when optional camera dependencies are unavailable."""


def _import_cv2() -> object:
    try:
        import cv2
    except ImportError as exc:
        raise CameraDependencyError(CAMERA_DEPENDENCY_MESSAGE) from exc
    return cv2


def require_camera_support() -> None:
    _import_cv2()


def _read_capture_frame(
    capture: object,
    *,
    attempts: int,
    stop_on_success: bool = False,
) -> object | None:
    frame = None
    for _ in range(max(1, attempts)):
        try:
            ok, candidate = capture.read()
        except Exception:
            return frame
        if ok and candidate is not None:
            frame = candidate
            if stop_on_success:
                break
    return frame


def _iter_open_camera_captures(
    cv2: object,
    index: int,
    *,
    read_attempts: int = 0,
) -> Iterator[object]:
    for backend in _camera_backends(cv2):
        capture = _open_backend_camera_capture(
            cv2,
            index,
            backend,
            read_attempts=read_attempts,
        )
        if capture is not None:
            yield capture


def _open_backend_camera_capture(
    cv2: object,
    index: int,
    backend: int | None,
    *,
    read_attempts: int = 0,
) -> object | None:
    capture = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
    try:
        if not capture.isOpened():
            capture.release()
            return None
        if read_attempts > 0 and _read_capture_frame(
            capture,
            attempts=read_attempts,
            stop_on_success=True,
        ) is None:
            capture.release()
            return None
        return capture
    except Exception:
        try:
            capture.release()
        except Exception:
            pass
        return None


def _open_camera_capture(
    cv2: object,
    index: int,
    *,
    read_attempts: int = DEFAULT_CAMERA_PROBE_READS,
) -> object | None:
    return next(
        _iter_open_camera_captures(
            cv2,
            index,
            read_attempts=read_attempts,
        ),
        None,
    )


def open_camera_capture(index: int) -> object | None:
    try:
        cv2 = _import_cv2()
    except CameraDependencyError:
        return None
    capture = _open_camera_capture(
        cv2,
        index,
        read_attempts=DEFAULT_CAMERA_PROBE_READS,
    )
    if capture is not None or DEFAULT_CAMERA_PROBE_READS >= DEFAULT_CAMERA_STARTUP_READS:
        return capture
    return _open_camera_capture(
        cv2,
        index,
        read_attempts=DEFAULT_CAMERA_STARTUP_READS,
    )


def _default_camera_opener(index: int) -> bool:
    # Fast, reliable enumeration probe: DirectShow only on Windows (the MSMF default
    # backend blocks for seconds on absent indices). Keeps the two-tier slow-start
    # budget so cameras slow to produce their first frame are still detected, but never
    # pays the MSMF cost that made enumeration hang and miss cameras.
    try:
        cv2 = _import_cv2()
    except CameraDependencyError:
        return False
    backend = _enumeration_backend(cv2)
    for attempts in (DEFAULT_CAMERA_PROBE_READS, DEFAULT_CAMERA_STARTUP_READS):
        capture = _open_backend_camera_capture(cv2, index, backend, read_attempts=attempts)
        if capture is not None:
            capture.release()
            return True
        if DEFAULT_CAMERA_PROBE_READS >= DEFAULT_CAMERA_STARTUP_READS:
            break
    return False


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


DEFAULT_MIN_SHARPNESS = 100.0


def _grayscale_image(image: object, cv2: object) -> object:
    if hasattr(image, "ndim") and image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def passes_sharpness_gate(
    sharpness: float,
    *,
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
) -> bool:
    """Return True when the measured sharpness meets the capture threshold."""
    return float(sharpness) >= float(min_sharpness)


def measure_sharpness(image: object) -> float:
    """Measure detail using the variance of the Laplacian."""
    import cv2

    gray = _grayscale_image(image, cv2)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


@dataclass(frozen=True, slots=True)
class CaptureResult:
    frame: object | None
    resolution: tuple[int, int]
    sharpness: float
    brightness: float
    passed: bool


@dataclass(frozen=True, slots=True)
class _CaptureCandidate:
    backend: int | None
    resolution: tuple[int, int]


CAP_PROP_FRAME_WIDTH = 3
CAP_PROP_FRAME_HEIGHT = 4


def _capture_preference_score(result: CaptureResult) -> tuple[int, int, int, int]:
    width = max(0, int(result.resolution[0]))
    height = max(0, int(result.resolution[1]))
    return (
        1 if result.passed else 0,
        width * height,
        width,
        height,
    )


def _resolution_score(resolution: tuple[int, int]) -> tuple[int, int, int]:
    width = max(0, int(resolution[0]))
    height = max(0, int(resolution[1]))
    return (width * height, width, height)


def _capture_resolution(cap: object) -> tuple[int, int]:
    width = int(cap.get(CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(CAP_PROP_FRAME_HEIGHT))
    return width, height


def _capture_resolution_or_default(
    cap: object,
    default: tuple[int, int],
) -> tuple[int, int]:
    try:
        return _capture_resolution(cap)
    except Exception:
        return default


def negotiate_max_resolution(
    cap: object,
    *,
    request: tuple[int, int] = (10000, 10000),
) -> tuple[int, int]:
    """Request an oversized frame and read back the actual device resolution."""
    cap.set(CAP_PROP_FRAME_WIDTH, request[0])
    cap.set(CAP_PROP_FRAME_HEIGHT, request[1])
    return _capture_resolution(cap)


def _rank_camera_capture_candidates(cv2: object, index: int) -> list[_CaptureCandidate]:
    candidates: list[_CaptureCandidate] = []
    for backend in _camera_backends(cv2):
        capture = _open_backend_camera_capture(cv2, index, backend)
        if capture is None:
            continue
        try:
            resolution = negotiate_max_resolution(capture)
            candidates.append(_CaptureCandidate(backend=backend, resolution=resolution))
        except Exception:
            pass
        finally:
            try:
                capture.release()
            except Exception:
                pass
    candidates.sort(key=lambda candidate: _resolution_score(candidate.resolution), reverse=True)
    return candidates


def capture_still(
    index: int = 0,
    *,
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
    warmup_frames: int = DEFAULT_CAMERA_STARTUP_READS,
) -> CaptureResult | None:
    """Capture a still image after autofocus and warmup."""
    cv2 = _import_cv2()

    best_result: CaptureResult | None = None
    best_score: tuple[int, int, int, int] | None = None
    candidates = _rank_camera_capture_candidates(cv2, index)
    for candidate in candidates:
        capture = _open_backend_camera_capture(cv2, index, candidate.backend)
        if capture is None:
            continue
        frame = None
        resolution = candidate.resolution
        try:
            try:
                resolution = negotiate_max_resolution(capture)
            except Exception:
                resolution = _capture_resolution_or_default(capture, resolution)
            capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
            frame = _read_capture_frame(capture, attempts=warmup_frames)
            if frame is not None:
                resolution = _capture_resolution_or_default(capture, resolution)
        finally:
            try:
                capture.release()
            except Exception:
                pass

        if frame is None:
            continue

        sharpness = measure_sharpness(frame)
        brightness = float(_grayscale_image(frame, cv2).mean())
        result = CaptureResult(
            frame=frame,
            resolution=resolution,
            sharpness=sharpness,
            brightness=brightness,
            passed=passes_sharpness_gate(sharpness, min_sharpness=min_sharpness),
        )
        score = _capture_preference_score(result)
        if result.passed:
            return result
        if best_result is None or score > best_score:
            best_result = result
            best_score = score
    return best_result
