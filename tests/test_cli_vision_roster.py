from ocr_from2xlsx.cli import _vision_name_roster
from ocr_from2xlsx.correction_store import (
    Correction,
    append_correction,
    default_correction_store_path,
)


def test_vision_name_roster_none_and_missing(tmp_path):
    assert _vision_name_roster(None) == []
    assert _vision_name_roster(tmp_path / "batch.json") == []  # no store on disk yet


def test_vision_name_roster_loads_confirmed_names(tmp_path):
    batch = tmp_path / "batch.json"
    store = default_correction_store_path(batch)
    append_correction(store, Correction(field="name", final_value="葉心安"))
    append_correction(store, Correction(field="name", final_value="王小明"))
    roster = _vision_name_roster(batch)
    assert "葉心安" in roster and "王小明" in roster
