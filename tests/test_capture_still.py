from __future__ import annotations
 
import builtins
import sys
from types import SimpleNamespace
 
import pytest
 
from ocr_from2xlsx import capture as capture_module
from ocr_from2xlsx.capture import negotiate_max_resolution


class _FakeCap:
    def __init__(self, max_w: int, max_h: int) -> None:
        self._max_w = max_w
        self._max_h = max_h
        self._w = 640
        self._h = 480

    def set(self, prop: int, value: float) -> bool:
        if prop == 3:
            self._w = min(int(value), self._max_w)
        elif prop == 4:
            self._h = min(int(value), self._max_h)
        return True

    def get(self, prop: int) -> float:
        if prop == 3:
            return float(self._w)
        if prop == 4:
            return float(self._h)
        return 0.0


class _FakeStillCapture:
    def __init__(self, *, opened: bool, frames: list[object] | None = None) -> None:
        self._opened = opened
        self._frames = list(frames or [])
        self.released = False

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True

    def set(self, prop: int, value: float) -> bool:
        return True

    def read(self) -> tuple[bool, object | None]:
        if self._frames:
            return True, self._frames.pop(0)
        return False, None


class _GrayFrame:
    ndim = 2

    def __init__(self, brightness: float) -> None:
        self._brightness = brightness

    def mean(self) -> float:
        return self._brightness


class _ExclusiveHandleCapture(_FakeStillCapture):
    def __init__(
        self,
        factory: "_ExclusiveHandleFactory",
        *,
        backend: int | None,
        opened: bool,
        frames: list[object] | None = None,
    ) -> None:
        super().__init__(opened=opened, frames=frames)
        self.factory = factory
        self.backend = backend
        if opened:
            self.factory.active_handles += 1

    def release(self) -> None:
        if self._opened and not self.released:
            self.factory.active_handles -= 1
        super().release()


class _ExclusiveHandleFactory:
    def __init__(self, high_resolution_backend: int) -> None:
        self.high_resolution_backend = high_resolution_backend
        self.active_handles = 0
        self.calls: list[tuple[int, ...]] = []
        self.instances: list[_ExclusiveHandleCapture] = []

    def __call__(self, index: int, backend: int | None = None) -> _ExclusiveHandleCapture:
        self.calls.append((index,) if backend is None else (index, backend))
        opened = backend is None or self.active_handles == 0
        frames = ["high-res-frame"] if backend == self.high_resolution_backend else ["low-res-frame"]
        capture = _ExclusiveHandleCapture(
            self,
            backend=backend,
            opened=opened,
            frames=frames if opened else None,
        )
        self.instances.append(capture)
        return capture


class _HandleScopedResolutionCapture(_FakeStillCapture):
    def __init__(
        self,
        *,
        backend: int | None,
        opened: bool,
        max_resolution: tuple[int, int],
    ) -> None:
        super().__init__(opened=opened)
        self.backend = backend
        self.max_resolution = max_resolution
        self.width = 640
        self.height = 480
        self.set_calls: list[tuple[int, int]] = []

    def set(self, prop: int, value: float) -> bool:
        self.set_calls.append((prop, int(value)))
        if prop == capture_module.CAP_PROP_FRAME_WIDTH:
            self.width = min(int(value), self.max_resolution[0])
        elif prop == capture_module.CAP_PROP_FRAME_HEIGHT:
            self.height = min(int(value), self.max_resolution[1])
        return True

    def get(self, prop: int) -> float:
        if prop == capture_module.CAP_PROP_FRAME_WIDTH:
            return float(self.width)
        if prop == capture_module.CAP_PROP_FRAME_HEIGHT:
            return float(self.height)
        return 0.0

    def read(self) -> tuple[bool, object | None]:
        return True, f"frame-{self.width}x{self.height}"


class _HandleScopedResolutionFactory:
    def __init__(self, resolutions_by_open: dict[int | None, list[tuple[int, int]]]) -> None:
        self.resolutions_by_open = {
            backend: list(resolutions)
            for backend, resolutions in resolutions_by_open.items()
        }
        self.open_counts: dict[int | None, int] = {}
        self.calls: list[tuple[int, ...]] = []
        self.instances: list[_HandleScopedResolutionCapture] = []

    def __call__(self, index: int, backend: int | None = None) -> _HandleScopedResolutionCapture:
        self.calls.append((index,) if backend is None else (index, backend))
        open_count = self.open_counts.get(backend, 0)
        self.open_counts[backend] = open_count + 1
        resolutions = self.resolutions_by_open[backend]
        max_resolution = (
            resolutions[open_count] if open_count < len(resolutions) else resolutions[-1]
        )
        capture = _HandleScopedResolutionCapture(
            backend=backend,
            opened=True,
            max_resolution=max_resolution,
        )
        self.instances.append(capture)
        return capture


def test_negotiate_reads_back_device_max_without_importing_cv2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def fail_on_cv2(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "cv2":
            raise AssertionError("negotiate_max_resolution should not import cv2")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_on_cv2)
    cap = _FakeCap(max_w=3264, max_h=2448)

    width, height = negotiate_max_resolution(cap, request=(10000, 10000))
 
    assert (width, height) == (3264, 2448)


def test_capture_still_reports_missing_opencv_with_install_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def fail_on_cv2(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "cv2":
            raise ImportError("no cv2")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "cv2", raising=False)
    monkeypatch.setattr(builtins, "__import__", fail_on_cv2)

    with pytest.raises(RuntimeError, match="OpenCV.*pip install"):
        capture_module.capture_still(4)


def test_capture_still_defaults_to_heavy_warmup_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts_seen: list[int] = []
    calls: list[tuple[int, ...]] = []
    capture = _FakeStillCapture(opened=True)

    def fake_read_capture_frame(cap: object, *, attempts: int) -> object | None:
        attempts_seen.append(attempts)
        return "frame"

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        return capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "_read_capture_frame", fake_read_capture_frame)
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(capture_module, "negotiate_max_resolution", lambda cap: (1920, 1080))

    result = capture_module.capture_still(4)

    assert result is not None
    assert attempts_seen == [capture_module.DEFAULT_CAMERA_STARTUP_READS]
    assert calls == [(4,), (4,)]
    assert capture.released is True


def test_capture_still_avoids_full_warmup_on_later_lower_resolution_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts_seen: list[tuple[object, int]] = []
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeStillCapture(opened=True)
    directshow_capture = _FakeStillCapture(opened=True)

    def fake_read_capture_frame(cap: object, *, attempts: int) -> object | None:
        attempts_seen.append((cap, attempts))
        return "plain-frame" if cap is plain_capture else "later-frame"

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        return plain_capture if backend is None else directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "_read_capture_frame", fake_read_capture_frame)
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(
        capture_module,
        "negotiate_max_resolution",
        lambda cap: (1920, 1080) if cap is plain_capture else (1280, 720),
    )

    result = capture_module.capture_still(4, warmup_frames=25)

    assert result is not None
    assert result.frame == "plain-frame"
    assert attempts_seen[0] == (plain_capture, 25)
    assert all(
        cap is not directshow_capture or attempts < 25 for cap, attempts in attempts_seen[1:]
    )
    assert calls == [(4,), (4, 700), (4,)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


def test_capture_still_selects_higher_resolution_backend_before_full_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts_seen: list[tuple[object, int]] = []
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeStillCapture(opened=True)
    directshow_capture = _FakeStillCapture(opened=True)

    def fake_read_capture_frame(cap: object, *, attempts: int) -> object | None:
        attempts_seen.append((cap, attempts))
        return "low-res-frame" if cap is plain_capture else "high-res-frame"

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        return plain_capture if backend is None else directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "_read_capture_frame", fake_read_capture_frame)
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(
        capture_module,
        "negotiate_max_resolution",
        lambda cap: (1280, 720) if cap is plain_capture else (3264, 2448),
    )

    result = capture_module.capture_still(4, warmup_frames=25)

    assert result is not None
    assert result.frame == "high-res-frame"
    assert result.resolution == (3264, 2448)
    assert not any(cap is plain_capture and attempts == 25 for cap, attempts in attempts_seen)
    assert any(cap is directshow_capture and attempts == 25 for cap, attempts in attempts_seen)
    assert calls == [(4,), (4, 700), (4, 700)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


def test_capture_still_reopens_highest_resolution_backend_after_releasing_probe_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directshow_backend = 700
    factory = _ExclusiveHandleFactory(high_resolution_backend=directshow_backend)

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=directshow_backend,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=factory,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(
        capture_module,
        "negotiate_max_resolution",
        lambda cap: (3264, 2448) if cap.backend == directshow_backend else (1280, 720),
    )

    result = capture_module.capture_still(4, warmup_frames=1)

    assert result is not None
    assert result.frame == "high-res-frame"
    assert result.resolution == (3264, 2448)
    assert factory.calls == [(4,), (4, directshow_backend), (4, directshow_backend)]
    assert factory.active_handles == 0
    assert all(capture.released is True for capture in factory.instances)


def test_capture_still_renegotiates_resolution_on_reopened_final_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directshow_backend = 700
    factory = _HandleScopedResolutionFactory(
        {
            None: [(1280, 720)],
            directshow_backend: [(3264, 2448), (1920, 1080)],
        }
    )

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=directshow_backend,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=factory,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)

    result = capture_module.capture_still(4, warmup_frames=1)

    assert result is not None
    assert result.frame == "frame-1920x1080"
    assert result.resolution == (1920, 1080)
    assert factory.calls == [(4,), (4, directshow_backend), (4, directshow_backend)]
    assert factory.instances[-1].set_calls[:2] == [
        (capture_module.CAP_PROP_FRAME_WIDTH, 10000),
        (capture_module.CAP_PROP_FRAME_HEIGHT, 10000),
    ]


def test_capture_still_keeps_plain_backend_when_later_backend_is_not_higher_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, ...]] = []
    default_capture = _FakeStillCapture(opened=True, frames=["frame"])
    directshow_capture = _FakeStillCapture(opened=True, frames=["wrong-frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        if backend is None:
            return default_capture
        return directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(
        capture_module,
        "negotiate_max_resolution",
        lambda cap: (1920, 1080) if cap is default_capture else (1280, 720),
    )

    result = capture_module.capture_still(4, warmup_frames=1)

    assert result is not None
    assert result.frame == "frame"
    assert result.resolution == (1920, 1080)
    assert result.sharpness == 180.0
    assert result.brightness == 128.0
    assert calls == [(4,), (4, 700), (4,)]
    assert directshow_capture.released is True
    assert default_capture.released is True


def test_capture_still_falls_back_to_directshow_when_plain_backend_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeStillCapture(opened=False)
    directshow_capture = _FakeStillCapture(opened=True, frames=["frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        if backend is None:
            return plain_capture
        return directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(capture_module, "negotiate_max_resolution", lambda cap: (1920, 1080))

    result = capture_module.capture_still(4, warmup_frames=1)

    assert result is not None
    assert result.resolution == (1920, 1080)
    assert result.sharpness == 180.0
    assert result.brightness == 128.0
    assert calls == [(4,), (4, 700), (4, 700)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


def test_capture_still_falls_back_to_directshow_when_plain_backend_yields_no_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeStillCapture(opened=True)
    directshow_capture = _FakeStillCapture(opened=True, frames=["frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        if backend is None:
            return plain_capture
        return directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(capture_module, "negotiate_max_resolution", lambda cap: (1920, 1080))

    result = capture_module.capture_still(4, warmup_frames=1)

    assert result is not None
    assert result.resolution == (1920, 1080)
    assert result.sharpness == 180.0
    assert result.brightness == 128.0
    assert calls == [(4,), (4, 700), (4,), (4, 700)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


def test_capture_still_prefers_later_backend_when_it_negotiates_higher_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeStillCapture(opened=True, frames=["low-res-frame"])
    directshow_capture = _FakeStillCapture(opened=True, frames=["high-res-frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        if backend is None:
            return plain_capture
        return directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(
        capture_module,
        "negotiate_max_resolution",
        lambda cap: (1280, 720) if cap is plain_capture else (3264, 2448),
    )

    result = capture_module.capture_still(4, warmup_frames=1)

    assert result is not None
    assert result.frame == "high-res-frame"
    assert result.resolution == (3264, 2448)
    assert result.sharpness == 180.0
    assert result.brightness == 128.0
    assert calls == [(4,), (4, 700), (4, 700)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


def test_capture_still_prefers_passing_capture_over_higher_resolution_backend_that_fails_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeStillCapture(opened=True, frames=["passing-frame"])
    directshow_capture = _FakeStillCapture(opened=True, frames=["failing-frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeStillCapture:
        calls.append((index,) if backend is None else (index, backend))
        if backend is None:
            return plain_capture
        return directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=fake_video_capture,
            cvtColor=lambda frame, code: SimpleNamespace(mean=lambda: 128.0),
        ),
    )
    monkeypatch.setattr(
        capture_module,
        "measure_sharpness",
        lambda frame: 180.0 if frame == "passing-frame" else 80.0,
    )
    monkeypatch.setattr(
        capture_module,
        "negotiate_max_resolution",
        lambda cap: (1920, 1080) if cap is plain_capture else (3264, 2448),
    )

    result = capture_module.capture_still(4, min_sharpness=100.0, warmup_frames=1)

    assert result is not None
    assert result.frame == "passing-frame"
    assert result.resolution == (1920, 1080)
    assert result.sharpness == 180.0
    assert result.brightness == 128.0
    assert result.passed is True
    assert calls == [(4,), (4, 700), (4, 700), (4,)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


def test_capture_still_uses_grayscale_frame_directly_for_brightness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gray_frame = _GrayFrame(brightness=64.0)
    capture = _FakeStillCapture(opened=True, frames=[gray_frame])

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_PROP_AUTOFOCUS=39,
            COLOR_BGR2GRAY=6,
            VideoCapture=lambda index, backend=None: capture,
            cvtColor=lambda frame, code: (_ for _ in ()).throw(
                AssertionError("grayscale frames should not be converted")
            ),
        ),
    )
    monkeypatch.setattr(capture_module, "measure_sharpness", lambda frame: 180.0)
    monkeypatch.setattr(capture_module, "negotiate_max_resolution", lambda cap: (1920, 1080))

    result = capture_module.capture_still(4, warmup_frames=1)

    assert result is not None
    assert result.resolution == (1920, 1080)
    assert result.sharpness == 180.0
    assert result.brightness == 64.0
