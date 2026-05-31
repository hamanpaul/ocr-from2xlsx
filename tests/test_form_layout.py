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


def test_dataclass_sequences_are_coerced_to_tuples() -> None:
    """Verify that passing lists to options/fields/sections doesn't allow mutation."""
    # Build layout with Python lists
    options_list = [
        Option(label="女性", code="female", cell="B25"),
        Option(label="男性", code="male", cell="B26"),
    ]
    fields_list = [
        Field(
            key="gender",
            title="性別",
            kind="single_choice",
            record_path="gender",
            anchor_cell="A25",
            options=options_list,
        ),
    ]
    sections_list = [
        Section(id="B", title="綜合身份統計", fields=fields_list),
    ]
    layout = FormLayout(template_id="t", sections=sections_list)
    
    # Stored attributes must be tuples, not lists
    assert isinstance(layout.sections, tuple)
    assert isinstance(layout.sections[0].fields, tuple)
    assert isinstance(layout.sections[0].fields[0].options, tuple)
    
    # Mutating original lists should not affect stored model
    original_gender_field = layout.sections[0].fields[0]
    original_options_count = len(original_gender_field.options)
    
    options_list.append(Option(label="其他", code="other", cell="B27"))
    fields_list.append(
        Field(key="name", title="姓名", kind="text", record_path="name", anchor_cell="B23")
    )
    sections_list.append(Section(id="C", title="另一節", fields=()))
    
    # Stored model should not change
    assert len(layout.sections) == 1
    assert len(layout.sections[0].fields) == 1
    assert len(layout.sections[0].fields[0].options) == original_options_count


def test_duplicate_option_code_raises_error() -> None:
    """Verify that duplicate Option.code values within a field raise ValueError."""
    try:
        Field(
            key="status",
            title="狀態",
            kind="single_choice",
            record_path="status",
            anchor_cell="A1",
            options=(
                Option(label="Active", code="active", cell="B1"),
                Option(label="Active (other)", code="active", cell="B2"),
            ),
        )
        assert False, "Expected ValueError for duplicate option code"
    except ValueError as e:
        assert "active" in str(e).lower() or "duplicate" in str(e).lower()


def test_duplicate_field_key_raises_error() -> None:
    """Verify that duplicate Field.key values across the layout raise ValueError."""
    try:
        FormLayout(
            template_id="t",
            sections=(
                Section(
                    id="A",
                    title="Section A",
                    fields=(
                        Field(key="id", title="ID", kind="text", record_path="id", anchor_cell="A1"),
                    ),
                ),
                Section(
                    id="B",
                    title="Section B",
                    fields=(
                        Field(key="id", title="ID (copy)", kind="text", record_path="id2", anchor_cell="A2"),
                    ),
                ),
            ),
        )
        assert False, "Expected ValueError for duplicate field key"
    except ValueError as e:
        assert "id" in str(e).lower() or "duplicate" in str(e).lower()
