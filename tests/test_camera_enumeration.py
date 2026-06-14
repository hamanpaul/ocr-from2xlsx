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


def test_enumerate_cameras_default_opener_falls_back_to_directshow(monkeypatch) -> None:
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeProbeCapture(opened=False)
    directshow_capture = _FakeProbeCapture(opened=True, frames=["frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeProbeCapture:
        calls.append((index,) if backend is None else (index, backend))
        if backend is None:
            return plain_capture
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
    assert calls == [(0,), (0, 700)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


def test_enumerate_cameras_default_opener_skips_backend_that_opens_but_cannot_read(
    monkeypatch,
) -> None:
    calls: list[tuple[int, ...]] = []
    plain_capture = _FakeProbeCapture(opened=True)
    directshow_capture = _FakeProbeCapture(opened=True, frames=["frame"])

    def fake_video_capture(index: int, backend: int | None = None) -> _FakeProbeCapture:
        calls.append((index,) if backend is None else (index, backend))
        if backend is None:
            return plain_capture
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
    assert calls == [(0,), (0, 700)]
    assert plain_capture.released is True
    assert directshow_capture.released is True


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
