from ocr_from2xlsx.recognition.llama_client import normalize_tile_json


def test_proper_options_structure_passes_through():
    out = normalize_tile_json({"options": [{"id": "a", "marked": True}], "values": []})
    assert out == {"options": [{"id": "a", "marked": True}], "values": []}


def test_bare_option_object_is_wrapped():
    # the 2B model sometimes returns a single option object without the wrapper
    out = normalize_tile_json({"id": "identity.patient", "marked": True})
    assert out == {"options": [{"id": "identity.patient", "marked": True}], "values": []}


def test_bare_value_object_is_wrapped():
    out = normalize_tile_json({"id": "name", "text": "葉心安"})
    assert out == {"options": [], "values": [{"id": "name", "text": "葉心安"}]}


def test_list_of_option_objects_is_wrapped():
    out = normalize_tile_json([{"id": "a", "marked": True}, {"id": "b", "marked": False}])
    assert out["options"] == [{"id": "a", "marked": True}, {"id": "b", "marked": False}]
    assert out["values"] == []


def test_garbage_becomes_empty():
    assert normalize_tile_json("") == {"options": [], "values": []}
    assert normalize_tile_json(["病人"]) == {"options": [], "values": []}
    assert normalize_tile_json(None) == {"options": [], "values": []}
