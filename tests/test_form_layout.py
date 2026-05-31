from __future__ import annotations

from ocr_from2xlsx.form_layout import Field, FormLayout, Option, Section, service_record_layout


def _tiny_layout() -> FormLayout:
    """Minimal layout for testing accessors."""
    return FormLayout(
        sections=(
            Section(
                key="personal",
                fields=(
                    Field(
                        key="gender",
                        kind="single_choice",
                        options=(
                            Option(code="female", label="女", cell="B25"),
                            Option(code="male", label="男", cell="C25"),
                        ),
                    ),
                    Field(key="name", kind="text", options=()),
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
    
    # iter field keys
    field_keys = list(layout.iter_fields())
    assert field_keys == ["gender", "name"]


def test_iter_options_and_options_by_code() -> None:
    layout = _tiny_layout()
    
    # iter_options returns (field_key, option_code) pairs
    option_pairs = list(layout.iter_options())
    assert option_pairs == [("gender", "female"), ("gender", "male")]
    
    # options_by_code returns dict[code, Option] for a field
    gender_opts = layout.options_by_code("gender")
    assert gender_opts["female"].cell == "B25"
    
    # options_by_code for text field returns empty dict
    name_opts = layout.options_by_code("name")
    assert name_opts == {}
