from __future__ import annotations

import sys
from types import SimpleNamespace

from ocr_from2xlsx import capture as capture_module
from ocr_from2xlsx.capture import decide_camera_selection, enumerate_cameras


def test_enumerate_cameras_uses_injected_opener() -> None:
    openable = {0, 2}

    found = enumerate_cameras(max_probe=4, opener=lambda index: index in openable)

    assert found == [0, 2]


def test_enumerate_cameras_default_opener_without_cv2_returns_empty(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def no_cv2(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_cv2)

    assert enumerate_cameras(max_probe=3) == []


def test_open_camera_capture_uses_lightweight_probe_budget(monkeypatch) -> None:
    observed: list[tuple[int, int]] = []
    sentinel = object()

    def fake_iter(cv2: object, index: int, *, read_attempts: int = 0):
        observed.append((index, read_attempts))
        yield sentinel

    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace())
    monkeypatch.setattr(capture_module, "_iter_open_camera_captures", fake_iter)

    assert capture_module.open_camera_capture(4) is sentinel
    assert observed == [(4, capture_module.DEFAULT_CAMERA_PROBE_READS)]
    assert capture_module.DEFAULT_CAMERA_PROBE_READS < capture_module.DEFAULT_CAMERA_STARTUP_READS


class _FakeProbeCapture:
    def __init__(
        self,
        *,
        opened: bool,
        frames: list[object] | None = None,
        failed_reads_before_frame: int = 0,
    ) -> None:
        self._opened = opened
        self._frames = list(frames or [])
        self._failed_reads_before_frame = failed_reads_before_frame
        self.read_calls = 0
        self.released = False

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True

    def read(self) -> tuple[bool, object | None]:
        self.read_calls += 1
        if self._failed_reads_before_frame > 0:
            self._failed_reads_before_frame -= 1
            return False, None
        if self._frames:
            return True, self._frames.pop(0)
        return False, None


def test_open_camera_capture_stops_probe_after_first_successful_frame(monkeypatch) -> None:
    capture = _FakeProbeCapture(
        opened=True,
        frames=["frame"],
        failed_reads_before_frame=1,
    )

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(VideoCapture=lambda index, backend=None: capture),
    )

    assert capture_module.open_camera_capture(4) is capture
    assert capture.read_calls == 2


def test_enumerate_cameras_default_opener_uses_directshow_on_windows(monkeypatch) -> None:
    calls: list[tuple[int, ...]] = []
    directshow_capture = _FakeProbeCapture(opened=True, frames=["frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeProbeCapture:
        calls.append((index,) if backend is None else (index, backend))
        return directshow_capture

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            VideoCapture=fake_video_capture,
        ),
    )

    assert enumerate_cameras(max_probe=1) == [0]
    # DirectShow only — the slow/flaky MSMF backend is never probed on Windows.
    assert calls == [(0, 700)]
    assert directshow_capture.released is True


def test_enumerate_cameras_default_opener_requires_readable_frame(monkeypatch) -> None:
    calls: list[tuple[int, ...]] = []

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeProbeCapture:
        calls.append((index,) if backend is None else (index, backend))
        return _FakeProbeCapture(opened=True)  # opens but never yields a frame

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            CAP_DSHOW=700,
            VideoCapture=fake_video_capture,
        ),
    )

    # A camera that opens but never produces a frame is not reported as available.
    assert enumerate_cameras(max_probe=1) == []
    # DirectShow is tried first (probe budget then startup budget); finding nothing, the
    # MSMF/default fallback pass also runs and likewise rejects the frameless camera.
    assert calls[:2] == [(0, 700), (0, 700)]
    assert (0,) in calls  # default-backend fallback was attempted


def test_enumerate_cameras_falls_back_to_msmf_when_directshow_blind(monkeypatch) -> None:
    calls: list[tuple[int, int | None]] = []

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeProbeCapture:
        calls.append((index, backend))
        if backend == 600:  # CAP_MSMF — the only backend that sees this UVC webcam
            return _FakeProbeCapture(opened=True, frames=["frame"])
        return _FakeProbeCapture(opened=False)  # DirectShow / default are blind to it

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(CAP_DSHOW=700, CAP_MSMF=600, VideoCapture=fake_video_capture),
    )

    # DirectShow can't see this MSMF-only camera (the Windows Camera path); the fallback finds it.
    assert enumerate_cameras(max_probe=1) == [0]
    assert (0, 700) in calls  # DirectShow tried first
    assert (0, 600) in calls  # Media Foundation fallback found it


def test_enumerate_cameras_default_opener_accepts_slow_start_plain_backend(
    monkeypatch,
) -> None:
    calls: list[tuple[int, ...]] = []
    first_capture = _FakeProbeCapture(
        opened=True,
        frames=["frame"],
        failed_reads_before_frame=capture_module.DEFAULT_CAMERA_PROBE_READS + 1,
    )
    second_capture = _FakeProbeCapture(
        opened=True,
        frames=["frame"],
        failed_reads_before_frame=capture_module.DEFAULT_CAMERA_PROBE_READS + 1,
    )
    captures = iter([first_capture, second_capture])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeProbeCapture:
        calls.append((index,) if backend is None else (index, backend))
        return next(captures)

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            VideoCapture=fake_video_capture,
        ),
    )

    assert enumerate_cameras(max_probe=1) == [0]
    assert calls == [(0,), (0,)]
    assert first_capture.released is True
    assert second_capture.released is True


def test_decide_camera_selection_branches() -> None:
    assert decide_camera_selection([]) == ("none",)
    assert decide_camera_selection([1]) == ("auto", 1)
    assert decide_camera_selection([0, 1, 3]) == ("choose", (0, 1, 3))
