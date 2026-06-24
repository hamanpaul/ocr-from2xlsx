# tests/test_app_continuous_capture.py
from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx.app import ReviewApp


def test_shutter_sound_path_points_at_bundled_asset():
    path = ReviewApp._shutter_sound_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "shutter.wav"


def test_play_shutter_never_raises_without_asset(monkeypatch):
    monkeypatch.setattr(ReviewApp, "_shutter_sound_path", staticmethod(lambda: None))
    app = ReviewApp.__new__(ReviewApp)
    # Must be a silent no-op when there is no asset / no audio backend.
    ReviewApp._play_shutter(app)


# ---------------------------------------------------------------------------
# Task 6: Session state, buttons, start/cancel/undo
# ---------------------------------------------------------------------------
from types import SimpleNamespace


def _bare_app():
    app = ReviewApp.__new__(ReviewApp)
    app.editing = False
    app._camera_index = 4
    app._camera_capture = None
    app._camera_after_id = None
    app._preview_rotation = 0
    app._status_log = []
    app._status_var = None
    app._status_log_path = None
    app._autocapture_active = False
    app._autocapture_detector = None
    app._autocapture_output_dir = None
    app._autocapture_prev_gray = None
    app._autocapture_baseline_gray = None
    app._autocapture_need_baseline = False
    app._autocapture_stills = []
    app._autocapture_baseline_samples = []
    return app


def test_start_continuous_capture_opens_session(monkeypatch, tmp_path):
    app = _bare_app()
    monkeypatch.setattr("ocr_from2xlsx.app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr("ocr_from2xlsx.capture.require_camera_support", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askokcancel", lambda *a, **k: True)
    monkeypatch.setattr(app, "_has_live_camera_preview", lambda: True)  # don't start a real camera
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is True
    assert app._autocapture_output_dir == tmp_path
    assert app._autocapture_detector is not None


def test_start_blocked_when_editing(monkeypatch):
    app = _bare_app()
    app.editing = True
    errors = []
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showerror", lambda t, m: errors.append((t, m)))
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is False
    assert errors and errors[0][0] == "尚未保存"


def test_start_warns_without_selected_camera(monkeypatch):
    app = _bare_app()
    app._camera_index = None
    warnings = []
    monkeypatch.setattr("ocr_from2xlsx.capture.require_camera_support", lambda: None)
    monkeypatch.setattr(app, "_clear_inactive_camera_selection", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showwarning", lambda t, m: warnings.append((t, m)))
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is False
    assert warnings == [("連續拍照", "請先選擇可用的攝影機。")]


def test_start_prompts_clear_desk_and_enters_need_baseline(monkeypatch, tmp_path):
    app = _bare_app()
    monkeypatch.setattr("ocr_from2xlsx.app.filedialog.askdirectory", lambda **k: str(tmp_path))
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askokcancel", lambda *a, **k: True)
    monkeypatch.setattr(app, "_has_live_camera_preview", lambda: True)
    ReviewApp._start_continuous_capture(app)
    assert app._autocapture_active is True
    assert app._autocapture_need_baseline is True
    assert app._autocapture_detector.state == "need_baseline"


def test_observe_grabs_baseline_then_arms(monkeypatch):
    import numpy as np
    from ocr_from2xlsx.autocapture import AutoCaptureDetector
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_need_baseline = True
    app._autocapture_detector = AutoCaptureDetector()
    still_frame = np.zeros((48, 64), dtype="uint8")
    need = app._autocapture_detector.config.baseline_stable_frames  # 3
    # Feed need-1 frames → still in baseline mode
    for i in range(need - 1):
        took = ReviewApp._observe_autocapture_frame(app, still_frame)
        assert took is False, f"frame {i+1} should return False (still collecting baseline)"
        assert app._autocapture_need_baseline is True, f"should still need baseline after frame {i+1}"
        assert app._autocapture_detector.state == "need_baseline"
    # Feed the Nth frame → baseline established, detector armed
    took = ReviewApp._observe_autocapture_frame(app, still_frame)
    assert took is False
    assert app._autocapture_need_baseline is False
    assert app._autocapture_baseline_gray is not None
    assert app._autocapture_detector.state == "armed"


def test_reset_baseline_requests_regrab(monkeypatch):
    app = _bare_app()
    app._autocapture_active = True
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.askokcancel", lambda *a, **k: True)
    ReviewApp._reset_baseline(app)
    assert app._autocapture_need_baseline is True


def test_cancel_continuous_capture(monkeypatch):
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_stills = [Path("a.png")]
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    ReviewApp._cancel_continuous_capture(app)
    assert app._autocapture_active is False


def test_undo_last_capture_deletes_and_decrements(tmp_path):
    app = _bare_app()
    app._autocapture_active = True
    f1 = tmp_path / "scan-capture.png"
    f2 = tmp_path / "scan-capture-2.png"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    app._autocapture_stills = [f1, f2]
    ReviewApp._undo_last_continuous_capture(app)
    assert app._autocapture_stills == [f1]
    assert not f2.exists()
    assert f1.exists()


# ---------------------------------------------------------------------------
# Task 7: Auto-capture observe + perform (camera wiring)
# ---------------------------------------------------------------------------
import sys

from ocr_from2xlsx.autocapture import CAPTURE, DISARMED, AutoCaptureDetector


def test_observe_delegates_to_perform_on_capture(monkeypatch):
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_detector = SimpleNamespace(config=SimpleNamespace(roi_fraction=1.0), observe=lambda m: CAPTURE)
    monkeypatch.setattr("ocr_from2xlsx.capture.measure_sharpness", lambda f: 100.0)
    called = []
    monkeypatch.setattr(app, "_perform_autocapture", lambda: called.append(True) or True)
    import numpy as np
    took_over = ReviewApp._observe_autocapture_frame(app, np.zeros((48, 64), dtype="uint8"))
    assert took_over is True
    assert called == [True]


def test_perform_autocapture_saves_still_and_marks_captured(monkeypatch, tmp_path):
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.capture import CaptureResult

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    app._autocapture_prev_gray = None
    shutters = []
    monkeypatch.setattr(
        capture_module, "capture_still",
        lambda *a, **k: CaptureResult(frame="frame", resolution=(1920, 1080), sharpness=180.0, brightness=128.0, passed=True),
    )
    import numpy as np
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(
        imencode=lambda ext, f: (True, np.frombuffer(b"\x89PNG\r\n", dtype="uint8")),
    ))
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_start_camera", lambda i: None)
    monkeypatch.setattr(app, "_play_shutter", lambda: shutters.append(True))
    monkeypatch.setattr(app, "_flash_preview", lambda: None)

    took_over = ReviewApp._perform_autocapture(app)

    assert took_over is True
    assert len(app._autocapture_stills) == 1
    assert app._autocapture_stills[0].is_file()
    assert app._autocapture_detector.state == DISARMED
    assert shutters == [True]


def test_perform_autocapture_skips_blurry(monkeypatch, tmp_path):
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.capture import CaptureResult

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    monkeypatch.setattr(
        capture_module, "capture_still",
        lambda *a, **k: CaptureResult(frame="frame", resolution=(1920, 1080), sharpness=12.0, brightness=128.0, passed=False),
    )
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_start_camera", lambda i: None)

    ReviewApp._perform_autocapture(app)

    assert app._autocapture_stills == []


def test_perform_autocapture_stops_session_when_no_camera(monkeypatch, tmp_path):
    import ocr_from2xlsx.capture as capture_module

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    monkeypatch.setattr(capture_module, "capture_still", lambda *a, **k: None)
    monkeypatch.setattr(app, "_stop_camera", lambda: None)

    ReviewApp._perform_autocapture(app)

    assert app._autocapture_active is False


# ---------------------------------------------------------------------------
# Task 8: Finish session → batch recognize → review
# ---------------------------------------------------------------------------
def test_finish_routes_stills_to_batch_and_loads_review(monkeypatch, tmp_path):
    import ocr_from2xlsx.scan as scan
    from ocr_from2xlsx.domain import Batch, SourceBatch

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    s1 = tmp_path / "scan-capture.png"
    s2 = tmp_path / "scan-capture-2.png"
    s1.write_bytes(b"x"); s2.write_bytes(b"y")
    app._autocapture_stills = [s1, s2]

    seen = {}
    def fake_prepare(stills, out, template, backend, on_progress=None):
        seen["stills"] = list(stills)
        if on_progress:
            on_progress(2, 2, "scan-capture-2.png")
        return Batch(source_batch=SourceBatch(created_at="t", source_type="scan_records", template_name="service_record.v1"), records=[])
    monkeypatch.setattr(scan, "prepare_records_from_images", fake_prepare)
    monkeypatch.setattr("ocr_from2xlsx.cli._resolve_template", lambda name: SimpleNamespace(template_id=name))
    monkeypatch.setattr(app, "_resolve_recognition_backend", lambda *a, **k: object())
    monkeypatch.setattr(app, "_open_processing_modal", lambda msg: None)
    monkeypatch.setattr(app, "_set_modal_message", lambda m, msg: None)
    monkeypatch.setattr(app, "_close_processing_modal", lambda m: None)
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.json_io.dump_batch", lambda batch, path: Path(path).write_text("{}"))
    loaded = {}
    monkeypatch.setattr(app, "_set_loaded_records", lambda records, path: loaded.update(path=path))
    monkeypatch.setattr("ocr_from2xlsx.app.JsonRecordSource", lambda path: SimpleNamespace(records=lambda: iter([SimpleNamespace(record_id="batch-0001")])))
    infos = []
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda t, m: infos.append((t, m)))

    ReviewApp._finish_continuous_capture(app)

    assert seen["stills"] == [s1, s2]
    assert app._autocapture_active is False
    assert loaded.get("path") == tmp_path / "scan-prepared.json"
    assert any(t == "辨識完成" for t, _ in infos)
    assert app._autocapture_stills == []  # consumed on success


def test_finish_with_no_captures_warns_and_skips(monkeypatch, tmp_path):
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_stills = []
    warnings = []
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showwarning", lambda t, m: warnings.append((t, m)))
    monkeypatch.setattr(
        "ocr_from2xlsx.scan.prepare_records_from_images",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not recognize")),
    )
    ReviewApp._finish_continuous_capture(app)
    assert app._autocapture_active is False
    assert warnings and "沒有可辨識" in warnings[0][1]


# ---------------------------------------------------------------------------
# Carried-over branch tests: STALLED and imwrite-failure paths
# ---------------------------------------------------------------------------


def test_perform_autocapture_stalled_after_retry_limit(monkeypatch, tmp_path):
    """After retry_limit (3) blurry captures the detector reaches STALLED and the
    status message contains the stalled/too-blurry text."""
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.autocapture import AutoCaptureDetector, AutoCaptureConfig
    from ocr_from2xlsx.capture import CaptureResult

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    retry_limit = app._autocapture_detector.config.retry_limit  # 3

    monkeypatch.setattr(
        capture_module,
        "capture_still",
        lambda *a, **k: CaptureResult(
            frame="frame",
            resolution=(1920, 1080),
            sharpness=12.0,
            brightness=128.0,
            passed=False,
        ),
    )
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_start_camera", lambda i: None)

    for _ in range(retry_limit):
        ReviewApp._perform_autocapture(app)

    assert app._autocapture_stills == []
    # The last status message must contain the STALLED text
    assert any("連續多張太模糊" in msg for msg in app._status_log)
    from ocr_from2xlsx.autocapture import PAUSED
    assert app._autocapture_detector.state == PAUSED


def test_perform_autocapture_imwrite_failure_restarts_camera(monkeypatch, tmp_path):
    """When capture_still passes but cv2.imwrite returns False, no still is
    appended and the camera preview is restarted (_start_camera called)."""
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.autocapture import AutoCaptureDetector
    from ocr_from2xlsx.capture import CaptureResult

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    app._autocapture_detector = AutoCaptureDetector()
    app._autocapture_prev_gray = None

    monkeypatch.setattr(
        capture_module,
        "capture_still",
        lambda *a, **k: CaptureResult(
            frame="frame",
            resolution=(1920, 1080),
            sharpness=180.0,
            brightness=128.0,
            passed=True,
        ),
    )
    # cv2.imencode returns (False, None) to simulate a write failure
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(imencode=lambda ext, f: (False, None)),
    )
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    camera_starts = []
    monkeypatch.setattr(app, "_start_camera", lambda i: camera_starts.append(i))

    ReviewApp._perform_autocapture(app)

    assert app._autocapture_stills == []
    assert camera_starts, "_start_camera must be called to restart the preview"
    assert any("無法寫入擷取影像" in msg for msg in app._status_log)


def test_perform_autocapture_writes_to_cjk_output_dir(monkeypatch, tmp_path):
    import numpy as np
    import ocr_from2xlsx.capture as capture_module
    from ocr_from2xlsx.autocapture import AutoCaptureDetector
    from ocr_from2xlsx.capture import CaptureResult

    cjk_dir = tmp_path / "表單辨識"
    cjk_dir.mkdir()
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = cjk_dir
    app._autocapture_detector = AutoCaptureDetector()
    app._autocapture_prev_gray = None
    monkeypatch.setattr(
        capture_module, "capture_still",
        lambda *a, **k: CaptureResult(frame="frame", resolution=(1920, 1080), sharpness=180.0, brightness=128.0, passed=True),
    )
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(
        imencode=lambda ext, f: (True, np.frombuffer(b"\x89PNG\r\n", dtype="uint8")),
    ))
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_start_camera", lambda i: None)
    monkeypatch.setattr(app, "_play_shutter", lambda: None)
    monkeypatch.setattr(app, "_flash_preview", lambda: None)

    ReviewApp._perform_autocapture(app)

    assert len(app._autocapture_stills) == 1
    assert app._autocapture_stills[0].is_file()
    assert "表單辨識" in str(app._autocapture_stills[0])


# ---------------------------------------------------------------------------
# Task 4: Finish data recovery + "辨識完成" dialog
# ---------------------------------------------------------------------------
def test_finish_works_after_camera_loss_when_stills_exist(monkeypatch, tmp_path):
    import ocr_from2xlsx.scan as scan
    from ocr_from2xlsx.domain import Batch, SourceBatch

    app = _bare_app()
    app._autocapture_active = False  # camera-loss set this False, but stills remain
    app._autocapture_output_dir = tmp_path
    s1 = tmp_path / "scan-capture.png"; s1.write_bytes(b"x")
    app._autocapture_stills = [s1]
    monkeypatch.setattr(scan, "prepare_records_from_images",
                        lambda *a, **k: Batch(source_batch=SourceBatch(created_at="t", source_type="scan_records", template_name="service_record.v1"), records=[]))
    monkeypatch.setattr("ocr_from2xlsx.cli._resolve_template", lambda name: SimpleNamespace(template_id=name))
    monkeypatch.setattr(app, "_resolve_recognition_backend", lambda *a, **k: object())
    monkeypatch.setattr(app, "_open_processing_modal", lambda msg: None)
    monkeypatch.setattr(app, "_set_modal_message", lambda m, msg: None)
    monkeypatch.setattr(app, "_close_processing_modal", lambda m: None)
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.json_io.dump_batch", lambda batch, path: Path(path).write_text("{}"))
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showinfo", lambda *a, **k: None)
    loaded = {}
    monkeypatch.setattr(app, "_set_loaded_records", lambda records, path: loaded.update(path=path))
    monkeypatch.setattr("ocr_from2xlsx.app.JsonRecordSource",
                        lambda path: SimpleNamespace(records=lambda: iter([SimpleNamespace(record_id="batch-0001")])))

    ReviewApp._finish_continuous_capture(app)
    assert loaded.get("path") == tmp_path / "scan-prepared.json"


def test_finish_recognition_error_preserves_stills_for_retry(monkeypatch, tmp_path):
    import ocr_from2xlsx.scan as scan
    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    s1 = tmp_path / "scan-capture.png"; s1.write_bytes(b"x")
    app._autocapture_stills = [s1]
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr(app, "_resolve_recognition_backend", lambda *a, **k: object())
    monkeypatch.setattr("ocr_from2xlsx.cli._resolve_template", lambda name: SimpleNamespace(template_id=name))
    monkeypatch.setattr(app, "_open_processing_modal", lambda msg: None)
    monkeypatch.setattr(app, "_close_processing_modal", lambda m: None)
    errors = []
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showerror", lambda t, m: errors.append((t, m)))
    monkeypatch.setattr(scan, "prepare_records_from_images",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("backend down")))
    ReviewApp._finish_continuous_capture(app)
    assert app._autocapture_stills == [s1]  # preserved → retryable
    assert errors and errors[0][0] == "批次辨識失敗"


# ---------------------------------------------------------------------------
# R6 hardening tests: stability gate, illumination-robust diff, no-records clear
# ---------------------------------------------------------------------------


def test_baseline_gate_restarts_on_motion(monkeypatch):
    """Feed 2 still frames, then a spatially different (motion) frame → samples reset;
    then 3 still frames → detector arms.

    Note: mean_normalized_diff removes DC (mean), so a uniform brightness shift alone
    does NOT count as motion — that is correct illumination-robust behavior. This test
    uses a frame with a different spatial pattern (not just a DC offset) to trigger the
    motion gate.
    """
    import numpy as np
    from ocr_from2xlsx.autocapture import AutoCaptureDetector

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_need_baseline = True
    app._autocapture_detector = AutoCaptureDetector()

    still_frame = np.zeros((48, 64), dtype="float64")
    # A frame with non-uniform content whose AC component differs from still_frame by
    # more than motion_thresh (2.0). Use alternating rows so AC ≠ 0.
    motion_frame = np.zeros((48, 64), dtype="float64")
    motion_frame[::2, :] = 10.0   # alternating rows → AC diff ≈ 5.0 > 2.0

    # Feed 2 still frames
    ReviewApp._observe_autocapture_frame(app, still_frame)
    ReviewApp._observe_autocapture_frame(app, still_frame)
    assert app._autocapture_need_baseline is True  # still collecting

    # Feed motion frame → samples should reset
    ReviewApp._observe_autocapture_frame(app, motion_frame)
    assert app._autocapture_need_baseline is True  # motion reset the run

    # Feed 3 still frames again (same content as motion_frame to be "still" vs prev)
    for _ in range(3):
        ReviewApp._observe_autocapture_frame(app, motion_frame)

    assert app._autocapture_need_baseline is False
    assert app._autocapture_baseline_gray is not None
    assert app._autocapture_detector.state == "armed"


def test_finish_zero_records_clears_stills(monkeypatch, tmp_path):
    """When prepare_records_from_images returns records=[] and JsonRecordSource also
    yields nothing, _finish_continuous_capture must clear _autocapture_stills."""
    import ocr_from2xlsx.scan as scan
    from ocr_from2xlsx.domain import Batch, SourceBatch

    app = _bare_app()
    app._autocapture_active = True
    app._autocapture_output_dir = tmp_path
    s1 = tmp_path / "scan-capture.png"
    s1.write_bytes(b"x")
    app._autocapture_stills = [s1]

    monkeypatch.setattr(
        scan,
        "prepare_records_from_images",
        lambda *a, **k: Batch(
            source_batch=SourceBatch(
                created_at="t",
                source_type="scan_records",
                template_name="service_record.v1",
            ),
            records=[],
        ),
    )
    monkeypatch.setattr("ocr_from2xlsx.cli._resolve_template", lambda name: SimpleNamespace(template_id=name))
    monkeypatch.setattr(app, "_resolve_recognition_backend", lambda *a, **k: object())
    monkeypatch.setattr(app, "_open_processing_modal", lambda msg: None)
    monkeypatch.setattr(app, "_set_modal_message", lambda m, msg: None)
    monkeypatch.setattr(app, "_close_processing_modal", lambda m: None)
    monkeypatch.setattr(app, "_stop_camera", lambda: None)
    monkeypatch.setattr("ocr_from2xlsx.json_io.dump_batch", lambda batch, path: Path(path).write_text("{}"))
    warnings = []
    monkeypatch.setattr("ocr_from2xlsx.app.messagebox.showwarning", lambda t, m: warnings.append((t, m)))
    # JsonRecordSource yields no records
    monkeypatch.setattr(
        "ocr_from2xlsx.app.JsonRecordSource",
        lambda path: SimpleNamespace(records=lambda: iter([])),
    )

    ReviewApp._finish_continuous_capture(app)

    assert app._autocapture_stills == []
    assert any("沒有可辨識" in t or "沒有可辨識" in m for t, m in warnings)
