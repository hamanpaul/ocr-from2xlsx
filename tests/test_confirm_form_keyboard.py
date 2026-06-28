from __future__ import annotations

import tkinter as tk

import pytest

from ocr_from2xlsx import app as app_module
from ocr_from2xlsx.form_layout import service_record_layout


def _form():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    root.withdraw()
    form = app_module.ConfirmForm(root, service_record_layout())
    return root, form


def test_flagged_keys_and_count_in_layout_order():
    root, form = _form()
    try:
        form.set_flagged_fields({"gender": "low-confidence", "name": "unconfirmed"})
        assert form.flagged_keys() == ["name", "gender"]
        assert form.flagged_count() == 2
    finally:
        root.destroy()


def test_focus_first_flagged_returns_first_flagged_key():
    root, form = _form()
    try:
        form.set_flagged_fields({"gender": "low-confidence", "name": "unconfirmed"})
        assert form.focus_first_flagged() == "name"
        assert form._current_focus == "name"
    finally:
        root.destroy()


def test_focus_first_flagged_falls_back_to_first_editable_when_none_flagged():
    root, form = _form()
    try:
        form.set_flagged_fields({})
        assert form.focus_first_flagged() == "service_date"
        assert form._current_focus == "service_date"
    finally:
        root.destroy()


def test_focus_next_and_prev_flagged_cycle_and_wrap():
    root, form = _form()
    try:
        form.set_flagged_fields({"name": "unconfirmed", "gender": "low-confidence"})
        form.focus_first_flagged()  # name
        assert form.focus_next_flagged() == "gender"
        assert form.focus_next_flagged() == "name"   # wrap
        assert form.focus_prev_flagged() == "gender"  # wrap back
    finally:
        root.destroy()


def test_focus_next_flagged_noop_when_none_flagged():
    root, form = _form()
    try:
        form.set_flagged_fields({})
        assert form.focus_next_flagged() is None
    finally:
        root.destroy()


def test_focus_bolds_active_field_label_and_reverts_previous():
    import tkinter.font as tkfont

    root, form = _form()
    try:
        form.set_flagged_fields({"name": "unconfirmed", "gender": "low-confidence"})
        form.focus_first_flagged()  # name
        assert tkfont.Font(font=form._field_labels["name"].cget("font")).cget("weight") == "bold"
        form.focus_next_flagged()  # gender — name reverts, gender bolds
        assert tkfont.Font(font=form._field_labels["name"].cget("font")).cget("weight") == "normal"
        assert tkfont.Font(font=form._field_labels["gender"].cget("font")).cget("weight") == "bold"
        # Foreground (flagged red) is untouched by the bold emphasis.
        assert str(form._field_labels["gender"].cget("foreground")) == "#b00020"
    finally:
        root.destroy()


def test_set_zoom_reclamps_origin_so_zoom_out_has_no_edge_gap():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    root.withdraw()
    try:
        from PIL import Image

        viewer = app_module.ImageViewer(root)
        # Deterministic fit-base space (#57 renders from full-res PIL; zoom/pan math works in
        # fit-base coords): a 200px image fitted into a 100px pane → fit-base size 100.
        viewer._refresh_view_size = lambda: None
        viewer.mode = "static"
        viewer._pil_image = Image.new("RGB", (200, 200))
        viewer._fit_scale = 0.5
        viewer._image_size = (100, 100)
        viewer._view_size = (100, 100)
        viewer.set_zoom(4)
        viewer.pan_to(1000, 1000)  # pan hard to the bottom-right; clamps to the max origin
        max_at_4 = list(viewer.origin)
        viewer.set_zoom(2)  # zooming out must re-clamp, not leave the stale (too-large) origin
        assert viewer.origin[0] <= max_at_4[0] and viewer.origin[1] <= max_at_4[1]
        # origin must stay within the larger window's valid range (no dark edge gap)
        from ocr_from2xlsx.image_viewer import clamp_origin
        assert viewer.origin[0] == clamp_origin(viewer.origin[0], 100, viewer._view_size[0], 2)
    finally:
        root.destroy()


def test_clean_record_clears_active_field_bold():
    import tkinter.font as tkfont

    root, form = _form()
    try:
        form.set_flagged_fields({"name": "unconfirmed"})
        form.focus_first_flagged()  # name -> bold
        assert tkfont.Font(font=form._field_labels["name"].cget("font")).cget("weight") == "bold"
        # Navigating to a clean (0-flagged) record clears flags and the active-field bold,
        # so no stale bold title lingers with nothing focused.
        form.set_flagged_fields({})
        form.clear_active_label()
        assert tkfont.Font(font=form._field_labels["name"].cget("font")).cget("weight") == "normal"
        assert form._active_label_path is None
    finally:
        root.destroy()


def test_unflagged_labels_are_deemphasized_when_some_field_flagged():
    root, form = _form()
    try:
        form.set_flagged_fields({"name": "unconfirmed"})
        assert form._field_labels["name"].cget("text").startswith("⚠")
        assert str(form._field_labels["name"].cget("foreground")) == "#b00020"
        assert str(form._field_labels["gender"].cget("foreground")) == "#9aa0a6"
    finally:
        root.destroy()


def test_no_flag_keeps_labels_normal():
    root, form = _form()
    try:
        form.set_flagged_fields({})
        assert form._field_labels["name"].cget("text") == "姓名"
        # set_flagged_fields({}) resets foreground to "" (no de-emphasis when nothing flagged).
        assert str(form._field_labels["name"].cget("foreground")) == ""
    finally:
        root.destroy()


def test_number_key_selects_single_choice_option_and_clears_others():
    root, form = _form()
    try:
        handled = form._single_choice_select_by_digit["identity"]("2")
        assert handled is True
        assert form.single_choice_fields["identity"].get() == "family_caregiver"
        option_vars = form._single_choice_option_vars["identity"]
        assert option_vars["family_caregiver"].get() is True
        assert option_vars["patient"].get() is False
    finally:
        root.destroy()


def test_number_key_out_of_range_does_nothing():
    root, form = _form()
    try:
        handled = form._single_choice_select_by_digit["identity"]("7")
        assert handled is False
        assert form.single_choice_fields["identity"].get() == ""
    finally:
        root.destroy()


def test_digit_typed_in_text_field_stays_text():
    root, form = _form()
    try:
        assert "medical_record_no" not in form._single_choice_select_by_digit
        assert "service_date" not in form._single_choice_select_by_digit
    finally:
        root.destroy()


def test_space_toggle_multi_choice_option():
    root, form = _form()
    try:
        form.toggle_multi_choice_option("cancer", "lung_cancer")
        assert form.collect()["cancer"] == {"lung_cancer"}
        form.toggle_multi_choice_option("cancer", "lung_cancer")
        assert form.collect()["cancer"] == set()
    finally:
        root.destroy()


def test_flagged_count_excludes_non_navigable_keys():
    # flagged_fields() can fall back to a raw field-id that is not a navigable field
    # (e.g. an unmapped low-confidence id). The "待確認 N" badge must count only fields
    # the reviewer can jump to, so flagged_count() must equal len(flagged_keys()).
    root, form = _form()
    try:
        form.set_flagged_fields({"name": "unconfirmed", "ghost_field_id": "low-confidence"})
        assert form.flagged_keys() == ["name"]
        assert form.flagged_count() == len(form.flagged_keys()) == 1
    finally:
        root.destroy()


def _click_checkbox(root, label):
    from tkinter import ttk

    stack = [root]
    while stack:
        widget = stack.pop()
        for child in widget.winfo_children():
            if isinstance(child, ttk.Checkbutton) and child.cget("text") == label:
                child.invoke()
                return True
            stack.append(child)
    return False


def test_single_choice_click_sets_its_own_field_not_the_last():
    # #single-choice-select-binding: each single-choice checkbox's command must set ITS OWN
    # field's value. The command lambda used `_select` as a free variable, which late-bound to
    # the LAST single-choice field — so a real mouse click set the wrong field and the clicked
    # field's value never made it into collect()/the XLSX. Drive real checkbox clicks here
    # (unit tests that set the StringVar directly missed this).
    root, form = _form()
    try:
        assert _click_checkbox(root, "病人"), "identity 病人 checkbox not found"
        assert _click_checkbox(root, "女性"), "gender 女性 checkbox not found"
        assert _click_checkbox(root, "1.門診"), "source 1.門診 checkbox not found"
        state = form.collect()
        assert state["identity"] == "patient"
        assert state["gender"] == "female"
        assert state["source"] == "outpatient"
        # clicking again clears that field (toggle), without touching the others
        assert _click_checkbox(root, "病人")
        state2 = form.collect()
        assert state2["identity"] == ""
        assert state2["gender"] == "female"
        assert state2["source"] == "outpatient"
    finally:
        root.destroy()
