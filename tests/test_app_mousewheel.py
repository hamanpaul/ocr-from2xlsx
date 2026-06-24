from ocr_from2xlsx.app import _wheel_scroll_units


def test_wheel_up_scrolls_toward_top():
    assert _wheel_scroll_units(120) == -1
    assert _wheel_scroll_units(240) == -2


def test_wheel_down_scrolls_toward_bottom():
    assert _wheel_scroll_units(-120) == 1
    assert _wheel_scroll_units(-240) == 2


def test_small_touchpad_delta_still_scrolls_one_unit():
    assert _wheel_scroll_units(40) == -1
    assert _wheel_scroll_units(-40) == 1


def test_zero_delta_does_not_scroll():
    assert _wheel_scroll_units(0) == 0
