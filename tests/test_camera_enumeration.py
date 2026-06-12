from __future__ import annotations

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


def test_decide_camera_selection_branches() -> None:
    assert decide_camera_selection([]) == ("none",)
    assert decide_camera_selection([1]) == ("auto", 1)
    assert decide_camera_selection([0, 1, 3]) == ("choose", (0, 1, 3))
