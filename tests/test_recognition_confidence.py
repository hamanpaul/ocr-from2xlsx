from ocr_from2xlsx.recognition.confidence import collect_confidence


def test_low_confidence_and_empty_flagged():
    tiles = [
        {
            "options": [{"id": "identity.patient", "marked": True, "confidence": 0.4}],
            "values": [{"id": "service_date", "text": "", "confidence": 0.0}],
        }
    ]
    field_conf, warnings = collect_confidence(tiles, threshold=0.6)
    assert field_conf["identity.patient"] == 0.4
    assert any("identity.patient" in w for w in warnings)
    assert any("service_date" in w for w in warnings)


def test_high_confidence_not_warned():
    tiles = [
        {
            "options": [{"id": "gender.female", "marked": True, "confidence": 0.95}],
            "values": [{"id": "service_date", "text": "114.06.25", "confidence": 0.9}],
        }
    ]
    field_conf, warnings = collect_confidence(tiles, threshold=0.6)
    assert field_conf["gender.female"] == 0.95
    assert field_conf["service_date"] == 0.9
    assert warnings == []


def test_unmarked_options_are_not_scored():
    tiles = [{"options": [{"id": "identity.patient", "marked": False, "confidence": 0.2}], "values": []}]
    field_conf, warnings = collect_confidence(tiles, threshold=0.6)
    assert field_conf == {}
    assert warnings == []
