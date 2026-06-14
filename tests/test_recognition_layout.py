from ocr_from2xlsx.recognition.layout import SERVICE_RECORD_V1_LAYOUT, band_pixels


def test_band_pixels_scales_fractions_to_image_size():
    section = SERVICE_RECORD_V1_LAYOUT[0]
    x0, y0, x1, y1 = band_pixels(section.band, width=1000, height=2000)
    assert (x0, y0, x1, y1) == (
        int(section.band[0] * 1000),
        int(section.band[1] * 2000),
        int(section.band[2] * 1000),
        int(section.band[3] * 2000),
    )
    assert x0 < x1 and y0 < y1


def test_layout_covers_core_fields():
    fields = {opt.field for s in SERVICE_RECORD_V1_LAYOUT for opt in s.options}
    assert {"identity", "gender", "patient_fields.cancers"} <= fields


def test_every_band_is_within_unit_square():
    for section in SERVICE_RECORD_V1_LAYOUT:
        x0, y0, x1, y1 = section.band
        assert 0.0 <= x0 < x1 <= 1.0
        assert 0.0 <= y0 < y1 <= 1.0


def test_option_ids_are_unique():
    ids = [opt.id for s in SERVICE_RECORD_V1_LAYOUT for opt in s.options]
    assert len(ids) == len(set(ids))
