from pathlib import Path

from ocr_from2xlsx.form_layout import service_record_layout

from training.layout_render import cell_box, option_mark_box, render_sheet_template, sheet_geometry, text_entry_box


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


def test_text_entry_boxes_follow_workbook_line_layout():
    layout = service_record_layout()
    geom = sheet_geometry(_XLSX)

    name_box = text_entry_box(layout, geom, "name")
    mrn_box = text_entry_box(layout, geom, "medical_record_no")
    service_date_box = text_entry_box(layout, geom, "service_date")
    diagnosis_date_box = text_entry_box(layout, geom, "diagnosis_date")
    rendered = render_sheet_template(geom)

    b23 = cell_box("B23", geom)
    assert name_box != mrn_box
    assert b23[0] < name_box[0] < b23[2]
    assert b23[0] < mrn_box[0] < b23[2]
    assert name_box[2] <= b23[2]
    assert mrn_box[2] <= b23[2]
    assert mrn_box[3] <= name_box[1]

    assert service_date_box[0] > rendered.line_boxes[("A2", 0)].box[2]
    assert diagnosis_date_box[0] > rendered.line_boxes[("A24", 0)].box[2]
    assert service_date_box[2] > service_date_box[0]
    assert diagnosis_date_box[2] > diagnosis_date_box[0]


def test_option_mark_box_is_checkbox_subbox_not_full_cell():
    layout = service_record_layout()
    geom = sheet_geometry(_XLSX)

    patient_mark_box = option_mark_box(layout, geom, "identity", "patient")
    patient_cell = cell_box("B23", geom)

    assert patient_mark_box != patient_cell
    assert patient_cell[0] <= patient_mark_box[0] < patient_mark_box[2] <= patient_cell[2]
    assert patient_cell[1] <= patient_mark_box[1] < patient_mark_box[3] <= patient_cell[3]
    assert (patient_mark_box[2] - patient_mark_box[0]) < (patient_cell[2] - patient_cell[0])
    assert (patient_mark_box[3] - patient_mark_box[1]) < (patient_cell[3] - patient_cell[1])


def test_option_mark_box_tracks_checkbox_position_within_line():
    layout = service_record_layout()
    geom = sheet_geometry(_XLSX)
    rendered = render_sheet_template(geom)

    mark_box = option_mark_box(layout, geom, "newly_diagnosed", "true", rendered=rendered)
    line_box = rendered.line_boxes[("A48", 0)].box
    cell = cell_box("A48", geom)

    assert mark_box[0] > line_box[0]
    assert mark_box[0] > cell[0] + (cell[2] - cell[0]) / 2
