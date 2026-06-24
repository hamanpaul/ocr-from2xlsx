from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ocr_from2xlsx import cli
from ocr_from2xlsx.capture import CaptureResult


class _FakeBackend:
    def extract(self, prepared) -> dict[str, object]:
        return {
            "service_date": "2025-06-25",
            "identity": "patient",
            "gender": "female",
            "ocr": {"backend": "fake", "raw_text": str(prepared.image_path), "warnings": []},
        }


def test_scan_cli_writes_batch_from_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n")
    output = tmp_path / "prepared.json"

    monkeypatch.setattr(cli, "_resolve_scan_backend", lambda args: _FakeBackend())

    exit_code = cli.main(["scan", "--image", str(image), "--output", str(output)])

    assert exit_code == 0
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["records"][0]["record_id"] == "scan-0001"
    assert payload["records"][0]["source"]["kind"] == "camera_still"
    assert capsys.readouterr().out == f"{output}\n"


def test_scan_cli_uses_unique_output_name_when_output_json_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n")
    output = tmp_path / "prepared.json"
    output.write_text('{"legacy": true}', encoding="utf-8")

    monkeypatch.setattr(cli, "_resolve_scan_backend", lambda args: _FakeBackend())

    exit_code = cli.main(["scan", "--image", str(image), "--output", str(output)])

    unique_output = tmp_path / "prepared-2.json"
    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == '{"legacy": true}'
    assert unique_output.is_file()
    payload = json.loads(unique_output.read_text(encoding="utf-8"))
    assert payload["records"][0]["record_id"] == "scan-0001"
    assert capsys.readouterr().out == f"{unique_output}\n"


def test_scan_help_lists_image_and_camera(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["scan", "--help"])

    out = capsys.readouterr().out
    assert "--image" in out
    assert "--camera" in out


def test_resolve_scan_backend_explicitly_passes_scan_docpre_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    resolved_backend = object()

    def fake_resolve(
        explicit_dir=None,
        default_dir=None,
        *,
        env_overrides=None,
    ):
        calls.append(
            {
                "explicit_dir": explicit_dir,
                "default_dir": default_dir,
                "env_overrides": env_overrides,
            }
        )
        return resolved_backend

    monkeypatch.setenv("SCAN_DOC_PREPROCESS", "1")
    monkeypatch.setattr("ocr_from2xlsx.plugin_backend.PluginOcrBackend.resolve", fake_resolve)

    backend = cli._resolve_scan_backend(SimpleNamespace(ocr_plugin_dir="plugin-dir"))

    assert backend is resolved_backend
    assert calls == [
        {
            "explicit_dir": "plugin-dir",
            "default_dir": None,
            "env_overrides": {"SCAN_DOC_PREPROCESS": "1"},
        }
    ]


def test_scan_cli_reports_missing_camera(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import ocr_from2xlsx.capture as capture_module

    output = tmp_path / "prepared.json"
    monkeypatch.setattr(
        cli,
        "_resolve_scan_backend",
        lambda args: (_ for _ in ()).throw(AssertionError("backend should not resolve")),
    )
    monkeypatch.setattr(capture_module, "capture_still", lambda *args, **kwargs: None)

    exit_code = cli.main(["scan", "--output", str(output)])

    assert exit_code == 1
    assert "no camera available" in capsys.readouterr().err


def test_scan_cli_reports_missing_opencv_with_install_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import builtins

    original_import = builtins.__import__
    output = tmp_path / "prepared.json"
    monkeypatch.setattr(
        cli,
        "_resolve_scan_backend",
        lambda args: (_ for _ in ()).throw(AssertionError("backend should not resolve")),
    )
    monkeypatch.delitem(sys.modules, "cv2", raising=False)

    def no_cv2(
        name: str,
        globals: object | None = None,
        locals: object | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "cv2":
            raise ImportError("no cv2")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", no_cv2)

    exit_code = cli.main(["scan", "--output", str(output)])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "OpenCV" in err
    assert "pip install" in err
    assert "no camera available" not in err


def test_scan_cli_reports_blurry_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import ocr_from2xlsx.capture as capture_module

    output = tmp_path / "prepared.json"
    monkeypatch.setattr(
        cli,
        "_resolve_scan_backend",
        lambda args: (_ for _ in ()).throw(AssertionError("backend should not resolve")),
    )
    monkeypatch.setattr(
        capture_module,
        "capture_still",
        lambda *args, **kwargs: CaptureResult(
            frame=object(),
            resolution=(1920, 1080),
            sharpness=10.0,
            brightness=128.0,
            passed=False,
        ),
    )

    exit_code = cli.main(["scan", "--output", str(output), "--min-sharpness", "100"])

    assert exit_code == 1
    assert "too blurry" in capsys.readouterr().err


def test_scan_cli_captures_webcam_when_frame_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import ocr_from2xlsx.capture as capture_module

    output = tmp_path / "prepared.json"

    def fake_imwrite(path: str, frame: object) -> bool:
        Path(path).write_bytes(b"\x89PNG\r\n")
        return True

    monkeypatch.setattr(cli, "_resolve_scan_backend", lambda args: _FakeBackend())
    monkeypatch.setattr(
        capture_module,
        "capture_still",
        lambda *args, **kwargs: CaptureResult(
            frame=object(),
            resolution=(1920, 1080),
            sharpness=180.0,
            brightness=128.0,
            passed=True,
        ),
    )
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=fake_imwrite))

    exit_code = cli.main(["scan", "--output", str(output)])

    assert exit_code == 0
    assert output.is_file()
    assert (tmp_path / "scan-capture.png").is_file()
    assert capsys.readouterr().out == f"{output}\n"


def test_scan_cli_uses_unique_capture_name_when_output_dir_has_existing_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ocr_from2xlsx.capture as capture_module

    output = tmp_path / "prepared.json"
    original_capture = tmp_path / "scan-capture.png"
    original_capture.write_bytes(b"older capture")

    def fake_imwrite(path: str, frame: object) -> bool:
        Path(path).write_bytes(b"new capture")
        return True

    monkeypatch.setattr(cli, "_resolve_scan_backend", lambda args: _FakeBackend())
    monkeypatch.setattr(
        capture_module,
        "capture_still",
        lambda *args, **kwargs: CaptureResult(
            frame=object(),
            resolution=(1920, 1080),
            sharpness=180.0,
            brightness=128.0,
            passed=True,
        ),
    )
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=fake_imwrite))

    exit_code = cli.main(["scan", "--output", str(output)])

    assert exit_code == 0
    assert original_capture.read_bytes() == b"older capture"
    assert (tmp_path / "scan-capture-2.png").read_bytes() == b"new capture"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["records"][0]["source"]["image_path"] == "scan-capture-2.png"
    assert payload["records"][0]["source"]["preprocessed_image_path"] == "scan-capture-2.png"


def test_scan_cli_reports_capture_write_error_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import ocr_from2xlsx.capture as capture_module

    output = tmp_path / "prepared.json"

    monkeypatch.setattr(
        cli,
        "_resolve_scan_backend",
        lambda args: (_ for _ in ()).throw(AssertionError("backend should not resolve")),
    )
    monkeypatch.setattr(
        capture_module,
        "capture_still",
        lambda *args, **kwargs: CaptureResult(
            frame=object(),
            resolution=(1920, 1080),
            sharpness=180.0,
            brightness=128.0,
            passed=True,
        ),
    )
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=lambda path, frame: False))

    exit_code = cli.main(["scan", "--output", str(output)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("error: Failed to write captured image: ")
    assert "Traceback" not in captured.err
    assert not output.exists()
