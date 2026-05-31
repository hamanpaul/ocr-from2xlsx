from pathlib import Path

from ocr_from2xlsx.form_layout import service_record_layout

from training.layout_render import cell_box, sheet_geometry


_XLSX = Path(__file__).resolve().parents[1] / "115年整年月報表統計_單案統計加總版(下拉式)(空白).xlsx"


def test_cell_boxes_are_ordered_and_in_bounds():
    geom = sheet_geometry(_XLSX)

    c4 = cell_box("C4", geom)
    d4 = cell_box("D4", geom)
    c5 = cell_box("C5", geom)

    assert c4[0] >= 0 and c4[1] >= 0 and c4[2] > c4[0] and c4[3] > c4[1]
    assert d4[0] >= 0 and d4[1] >= 0 and d4[2] > d4[0] and d4[3] > d4[1]
    assert c5[0] >= 0 and c5[1] >= 0 and c5[2] > c5[0] and c5[3] > c5[1]

    assert d4[0] > c4[0]
    assert c5[1] > c4[1]

    assert c4[2] <= geom.width
    assert c4[3] <= geom.height
    assert d4[2] <= geom.width
    assert d4[3] <= geom.height
    assert c5[2] <= geom.width
    assert c5[3] <= geom.height


def test_every_layout_option_cell_has_a_box():
    geom = sheet_geometry(_XLSX)

    for field, option in service_record_layout().iter_options():
        x0, y0, x1, y1 = cell_box(option.cell, geom)
        assert x1 > x0, (field.key, option.cell)
        assert y1 > y0, (field.key, option.cell)
