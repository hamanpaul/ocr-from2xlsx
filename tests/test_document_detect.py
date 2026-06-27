"""Deterministic synthetic tests for the form perspective correction (#59).

CV verification is done with known synthetic distortions (apply a known warp, then
assert detection + un-warp recovers the layout) rather than real photos, so it is
reproducible in CI; real-photo accuracy is validated separately on the holdout set.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from PIL import Image

from ocr_from2xlsx.recognition.document_detect import (
    deskew_pil,
    find_document_quad,
    order_quad,
    warp_document,
)


def test_order_quad_orders_tl_tr_br_bl():
    # Scrambled input; expect [top-left, top-right, bottom-right, bottom-left].
    scrambled = [[100, 100], [10, 90], [90, 10], [5, 5]]
    out = order_quad(scrambled)
    assert out.tolist() == [[5, 5], [90, 10], [100, 100], [10, 90]]


def _form_with_marker(w=400, h=560, mx_frac=0.5, my_frac=0.2):
    """A white 'form' on nothing yet — a black square marker at (mx_frac, my_frac)."""
    form = np.full((h, w, 3), 255, np.uint8)
    mx, my = int(mx_frac * w), int(my_frac * h)
    cv2.rectangle(form, (mx - 16, my - 16), (mx + 16, my + 16), (0, 0, 0), -1)
    return form


def _scene_with_skewed_form(canvas=(800, 1000), dst_quad=None):
    """Place the white form onto a dark background via a known perspective skew."""
    form = _form_with_marker()
    fh, fw = form.shape[:2]
    cw, ch = canvas
    src = np.float32([[0, 0], [fw - 1, 0], [fw - 1, fh - 1], [0, fh - 1]])
    dst = np.float32(dst_quad or [[130, 95], [650, 150], [600, 890], [95, 845]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    # borderValue dark grey -> the form (white) sits on a dark frame, like a photo on a desk.
    scene = cv2.warpPerspective(form, matrix, (cw, ch), borderValue=(40, 40, 40))
    return scene


def test_find_and_warp_recovers_marker_position():
    scene = _scene_with_skewed_form()
    quad = find_document_quad(scene)
    assert quad is not None, "the skewed white form should be detected against the dark frame"

    recovered = warp_document(scene, quad)
    assert recovered is not None
    rh, rw = recovered.shape[:2]

    # Locate the black marker in the recovered (flattened) form, ignoring a thin border.
    gray = cv2.cvtColor(recovered, cv2.COLOR_BGR2GRAY)
    y0, y1 = int(0.05 * rh), int(0.95 * rh)
    x0, x1 = int(0.05 * rw), int(0.95 * rw)
    ys, xs = np.where(gray[y0:y1, x0:x1] < 60)
    assert len(xs) > 0, "marker should survive the un-warp"
    cx = (xs.mean() + x0) / rw
    cy = (ys.mean() + y0) / rh

    # Marker was at normalized (0.5, 0.2) on the form; recovery must land near there
    # (generous tolerance for detection slop). Pre-fix the skewed band would miss it entirely.
    assert abs(cx - 0.5) < 0.08, f"cx={cx}"
    assert abs(cy - 0.2) < 0.08, f"cy={cy}"


def test_deskew_pil_is_identity_when_no_quad():
    # Uniform image: no edges -> no quad -> deskew returns the SAME object (safe fallback).
    blank = Image.new("RGB", (300, 400), (180, 180, 180))
    assert deskew_pil(blank) is blank


def test_deskew_pil_warps_when_form_present():
    scene = _scene_with_skewed_form()
    pil = Image.fromarray(scene[:, :, ::-1])  # BGR -> RGB
    out = deskew_pil(pil)
    assert out is not pil  # a quad was found and warped
    # Output is the flattened form: aspect close to the 400x560 form (~0.71), not the 0.8 scene.
    ratio = out.width / out.height
    assert 0.5 < ratio < 0.95, f"unexpected recovered aspect {ratio}"


def test_crop_sections_correct_perspective_runs_and_falls_back(tmp_path):
    from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT
    from ocr_from2xlsx.recognition.tiling import crop_sections

    # (a) skewed form -> deskew path produces a crop per section.
    scene_path = tmp_path / "scene.png"
    Image.fromarray(_scene_with_skewed_form()[:, :, ::-1]).save(scene_path)
    crops = crop_sections(scene_path, SERVICE_RECORD_V1_LAYOUT, tmp_path / "a", correct_perspective=True)
    assert set(crops) == {s.key for s in SERVICE_RECORD_V1_LAYOUT}
    for path in crops.values():
        assert (tmp_path / "a").joinpath(path).exists() or __import__("os").path.exists(path)

    # (b) no detectable quad -> falls back to the plain image, still crops, no crash.
    blank_path = tmp_path / "blank.png"
    Image.new("RGB", (600, 800), (200, 200, 200)).save(blank_path)
    crops_fb = crop_sections(blank_path, SERVICE_RECORD_V1_LAYOUT, tmp_path / "b", correct_perspective=True)
    assert set(crops_fb) == {s.key for s in SERVICE_RECORD_V1_LAYOUT}


# --- hardening regressions (from the #59 adversarial review) -----------------------------

def test_inner_table_is_not_mistaken_for_the_page():
    # Full-frame white page (no detectable outer edge) with a centred inner table box.
    # The largest 4-gon is the inner box, but it does not reach the frame edges, so it must
    # be rejected (page-bounding gate) rather than warped to — which would drop outer fields.
    page = np.full((1000, 800, 3), 255, np.uint8)
    cv2.rectangle(page, (160, 190), (640, 810), (0, 0, 0), 4)  # centred inner table, margins all sides
    assert find_document_quad(page) is None
    pil = Image.fromarray(page)
    assert deskew_pil(pil) is pil  # safe fallback, not a wrong warp


def test_order_quad_diamond_keeps_four_distinct_corners():
    # A ~45deg diamond used to collapse a corner with the x+y / y-x trick; the top/bottom-two
    # ordering must keep all four corners distinct so the warp is non-degenerate.
    diamond = [[100, 0], [200, 100], [100, 200], [0, 100]]
    out = order_quad(diamond)
    assert len({tuple(p) for p in out.tolist()}) == 4


def test_warp_rejects_landscape_aspect():
    # A landscape quad would transpose the portrait layout bands -> must return None.
    img = np.zeros((400, 800, 3), np.uint8)
    landscape = [[0, 0], [800, 0], [800, 400], [0, 400]]
    assert warp_document(img, landscape) is None


def test_deskew_pil_falls_back_on_exception(monkeypatch):
    from ocr_from2xlsx.recognition import document_detect as dd

    def _boom(*_a, **_k):
        raise RuntimeError("cv2 blew up")

    monkeypatch.setattr(dd, "find_document_quad", _boom)
    img = Image.new("RGB", (300, 400), (180, 180, 180))
    assert dd.deskew_pil(img) is img  # exception swallowed -> input returned, batch survives


def test_env_float_bad_value_falls_back_to_default(monkeypatch):
    from ocr_from2xlsx.recognition import document_detect as dd

    monkeypatch.setenv("SCAN_DEWARP_MIN_AREA", "not-a-number")
    assert dd._env_float("SCAN_DEWARP_MIN_AREA", 0.35) == 0.35


def test_is_full_frame_guard():
    from ocr_from2xlsx.recognition.document_detect import _is_full_frame

    assert _is_full_frame([[0, 0], [800, 0], [800, 1000], [0, 1000]], 800, 1000) is True
    assert _is_full_frame([[120, 95], [650, 150], [600, 890], [95, 845]], 800, 1000) is False


# --- fixed-camera corner calibration (#59 follow-up) -------------------------------------

def test_calibration_round_trip(tmp_path, monkeypatch):
    from ocr_from2xlsx.recognition import document_detect as dd

    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    assert dd.load_calibration() is None  # nothing saved yet
    corners = [[0.12, 0.10], [0.88, 0.15], [0.85, 0.95], [0.10, 0.90]]
    saved = dd.save_calibration(corners)
    assert saved.exists()
    assert dd.load_calibration() == corners


def test_load_calibration_rejects_invalid(tmp_path, monkeypatch):
    from ocr_from2xlsx.recognition import document_detect as dd

    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    p = dd.calibration_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"corners_norm": [[0.1,0.2],[1.5,0.2],[0.9,0.9],[0.1,0.9]]}', encoding="utf-8")
    assert dd.load_calibration() is None  # out-of-range coordinate
    p.write_text("not valid json", encoding="utf-8")
    assert dd.load_calibration() is None
    p.write_text('{"corners_norm": [[0.1,0.2],[0.9,0.2]]}', encoding="utf-8")
    assert dd.load_calibration() is None  # wrong number of corners


def test_warp_enforce_aspect_false_allows_landscape():
    img = np.zeros((400, 800, 3), np.uint8)
    landscape = [[0, 0], [800, 0], [800, 400], [0, 400]]
    assert warp_document(img, landscape) is None  # default gate rejects landscape
    assert warp_document(img, landscape, enforce_aspect=False) is not None  # calibration trusts it


def test_deskew_with_calibration_warps_using_marked_corners():
    # The form was placed on the scene via this dst quad (see _scene_with_skewed_form);
    # supplying those corners as calibration must flatten it WITHOUT auto-detection.
    scene = _scene_with_skewed_form()
    pil = Image.fromarray(scene[:, :, ::-1])
    cw, ch = 800, 1000
    dst = [[130, 95], [650, 150], [600, 890], [95, 845]]
    calib = [[x / cw, y / ch] for x, y in dst]
    out = deskew_pil(pil, calibration=calib)
    assert out is not pil  # warped via calibration

    gray = cv2.cvtColor(np.asarray(out)[:, :, ::-1], cv2.COLOR_BGR2GRAY)
    rh, rw = gray.shape[:2]
    y0, y1, x0, x1 = int(0.05 * rh), int(0.95 * rh), int(0.05 * rw), int(0.95 * rw)
    ys, xs = np.where(gray[y0:y1, x0:x1] < 60)
    assert len(xs) > 0
    cx = (xs.mean() + x0) / rw
    cy = (ys.mean() + y0) / rh
    assert abs(cx - 0.5) < 0.08 and abs(cy - 0.2) < 0.08  # marker recovered to its position
