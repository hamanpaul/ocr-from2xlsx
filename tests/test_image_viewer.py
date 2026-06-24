from __future__ import annotations

from ocr_from2xlsx.image_viewer import (
    anchored_origin,
    clamp_origin,
    clamp_zoom,
    field_region,
)


def test_clamp_zoom_bounds():
    assert clamp_zoom(0.2) == 1.0
    assert clamp_zoom(100.0) == 8.0
    assert clamp_zoom(2.5) == 2.5


def test_anchored_origin_keeps_cursor_point_fixed():
    # Zooming in (1->2) about a cursor 100px from the view's left edge moves the origin
    # right by 100*(1/1 - 1/2) = 50 image px so the same content stays under the cursor.
    assert anchored_origin(0.0, 100.0, 1.0, 2.0) == 50.0
    # Zooming back out restores the origin.
    assert anchored_origin(50.0, 100.0, 2.0, 1.0) == 0.0


def test_clamp_origin_keeps_image_in_view():
    assert clamp_origin(-10.0, 1000, 400, 1.0) == 0.0
    assert clamp_origin(999.0, 1000, 400, 1.0) == 600.0
    assert clamp_origin(100.0, 1000, 400, 1.0) == 100.0
    assert clamp_origin(999.0, 1000, 400, 2.0) == 800.0


def test_clamp_origin_when_image_smaller_than_view():
    assert clamp_origin(50.0, 200, 400, 1.0) == 0.0


def test_field_region_returns_section_band_or_none():
    band = field_region("identity")
    assert band is not None
    assert len(band) == 4
    assert all(0.0 <= v <= 1.0 for v in band)
    assert field_region("definitely_not_a_field") is None
