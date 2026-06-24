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


def test_image_viewer_resamples_from_original_when_zoomed():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tk: {exc}")
    root.withdraw()
    try:
        viewer = app_module.ImageViewer(root)
        original = tk.PhotoImage(master=root, width=40, height=40)
        fit = original.subsample(2, 2)  # 20x20 fit, base_scale 2 (#47)
        viewer.canvas.configure(width=20, height=20)
        viewer.show_image(fit, original=original, base_scale=2)

        # With a retained original, zooming re-samples a real crop (not None -> thumbnail).
        out = viewer._render_static(2)
        assert out is not None and out.width() >= 1
        # Without an original (or base_scale 1) it returns None so the caller uses thumbnail zoom.
        viewer._original = None
        assert viewer._render_static(2) is None
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
