from __future__ import annotations

from ocr_from2xlsx.image_viewer import (
    anchored_origin,
    clamp_origin,
    clamp_zoom,
    field_region,
    map_band_to_raw,
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


def test_field_region_is_full_width_row_band():
    # Field bands now span the full form width and frame the whole row (label + options),
    # derived from the 服務紀錄表 row geometry (#review-field-align).
    cancers = field_region("patient_fields.cancers")
    assert cancers is not None
    x0, y0, x1, y1 = cancers
    assert (x0, x1) == (0.0, 1.0)
    assert 0.0 <= y0 < y1 <= 1.0
    assert y1 - y0 > 0.05  # the 5-row 癌別 grid is a tall band


def test_field_region_vertical_order_follows_the_form():
    # service_date (top) is above identity (middle) is above cancers (bottom).
    top = field_region("service_date")[1]
    mid = field_region("identity")[1]
    bottom = field_region("patient_fields.cancers")[1]
    assert top < mid < bottom


def test_map_band_to_raw_identity_quad_is_noop():
    full_frame = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    band = (0.0, 0.4, 1.0, 0.6)
    assert map_band_to_raw(band, full_frame) == band


def test_map_band_to_raw_scales_into_form_quad():
    # Form occupies x[0.1,0.9], y[0.2,0.8] of the raw photo (no skew). The flattened
    # top-half band maps into the top half of that sub-rectangle.
    quad = [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]]
    x0, y0, x1, y1 = map_band_to_raw((0.0, 0.0, 1.0, 0.5), quad)
    assert abs(x0 - 0.1) < 1e-9 and abs(x1 - 0.9) < 1e-9
    assert abs(y0 - 0.2) < 1e-9 and abs(y1 - 0.5) < 1e-9  # 0.2 + 0.5*(0.8-0.2)


def test_map_band_to_raw_is_corner_order_independent():
    quad_tl_first = [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]]
    quad_shuffled = [[0.9, 0.8], [0.1, 0.2], [0.1, 0.8], [0.9, 0.2]]
    band = (0.0, 0.0, 1.0, 0.5)
    assert map_band_to_raw(band, quad_tl_first) == map_band_to_raw(band, quad_shuffled)
