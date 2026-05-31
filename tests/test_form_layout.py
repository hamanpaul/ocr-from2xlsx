from __future__ import annotations

from ocr_from2xlsx.form_layout import Field, FormLayout, Option, Section, service_record_layout


def _tiny_layout() -> FormLayout:
    """Minimal layout for testing accessors."""
    return FormLayout(
        template_id="t",
        sections=(
            Section(
                id="B",
                title="綜合身份統計",
                fields=(
                    Field(
                        key="gender",
                        title="性別",
                        kind="single_choice",
                        record_path="gender",
                        anchor_cell="A25",
                        options=(
                            Option(label="女性", code="female", cell="B25"),
                            Option(label="男性", code="male", cell="B26"),
                        ),
                    ),
                    Field(
                        key="name",
                        title="姓名",
                        kind="text",
                        record_path="name",
                        anchor_cell="B23",
                        options=(),
                    ),
                    Field(
                        key="page_num",
                        title="頁碼",
                        kind="text",
                        record_path=None,
                        anchor_cell="Z1",
                        options=(),
                    ),
                ),
            ),
        ),
    )


def test_field_by_key_and_iter() -> None:
    layout = _tiny_layout()
    
    # field_by_key lookups
    assert layout.field_by_key("gender").kind == "single_choice"
    assert layout.field_by_key("name").options == ()
    assert layout.field_by_key("missing") is None
    
    # iter_fields yields Field objects
    field_keys = [f.key for f in layout.iter_fields()]
    assert field_keys == ["gender", "name", "page_num"]


def test_field_with_no_record_counterpart() -> None:
    layout = _tiny_layout()
    
    # Fields can have record_path=None when no Record counterpart exists
    page_num = layout.field_by_key("page_num")
    assert page_num is not None
    assert page_num.record_path is None


def test_iter_options_and_options_by_code() -> None:
    layout = _tiny_layout()
    
    # iter_options returns (Field, Option) pairs
    option_pairs = [(f.key, o.code) for f, o in layout.iter_options()]
    assert option_pairs == [("gender", "female"), ("gender", "male")]
    
    # options_by_code returns dict[code, Option] for a field
    gender_opts = layout.options_by_code("gender")
    assert gender_opts["female"].cell == "B25"
    
    # options_by_code for text field returns empty dict
    name_opts = layout.options_by_code("name")
    assert name_opts == {}


def test_options_by_code_fails_on_missing_field() -> None:
    layout = _tiny_layout()
    
    # options_by_code should raise KeyError for unknown field keys
    try:
        layout.options_by_code("missing")
        assert False, "Expected KeyError but call succeeded"
    except KeyError as e:
        assert "missing" in str(e)
