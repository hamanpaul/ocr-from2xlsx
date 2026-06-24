from ocr_from2xlsx.recognition.name_mrn import parse_mrn, parse_name, snap_name


def test_parse_name_keeps_cjk_run():
    assert parse_name("葉心安") == "葉心安"
    assert parse_name("V 葉心安") == "葉心安"  # strip stray mark prefix
    assert parse_name("123") == ""  # digits are not a name


def test_parse_mrn_keeps_long_digit_run():
    assert parse_mrn("病入6250712919") == "6250712919"
    assert parse_mrn("V") == ""
    assert parse_mrn("12345") == ""  # too short to be a record number


def test_snap_name_to_roster():
    assert snap_name("葉心妄", roster=["葉心安", "王小明"]) == "葉心安"  # near match snaps
    assert snap_name("陌生人", roster=["葉心安"]) == "陌生人"  # no close match -> keep
    assert snap_name("", roster=["葉心安"]) == ""  # empty stays empty
    assert snap_name("葉心安", roster=[]) == "葉心安"  # empty roster -> keep
