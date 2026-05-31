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


def test_constructor_annotations_accept_sequences() -> None:
    """Verify that constructor signatures advertise support for list/sequence inputs.
    
    This is a regression test for the API contract: the implementation accepts
    lists/sequences and coerces them to tuples internally, so the public
    constructor signature should reflect that callers can pass lists.
    """
    import inspect
    from collections.abc import Sequence
    
    # Field(options=...) should accept Sequence, not just tuple
    field_sig = inspect.signature(Field)
    options_param = field_sig.parameters["options"]
    options_annotation = options_param.annotation
    
    # The annotation should allow Sequence[Option] (or similar), not just tuple[Option, ...]
    # We check that it's not strictly tuple by looking at the annotation string representation
    # or by checking if it's a Sequence type hint
    assert options_annotation != "tuple[Option, ...]", (
        f"Field.options annotation should accept sequences, not tuple-only: {options_annotation}"
    )
    
    # Section(fields=...) should accept Sequence, not just tuple
    section_sig = inspect.signature(Section)
    fields_param = section_sig.parameters["fields"]
    fields_annotation = fields_param.annotation
    
    assert fields_annotation != "tuple[Field, ...]", (
        f"Section.fields annotation should accept sequences, not tuple-only: {fields_annotation}"
    )
    
    # FormLayout(sections=...) should accept Sequence, not just tuple
    layout_sig = inspect.signature(FormLayout)
    sections_param = layout_sig.parameters["sections"]
    sections_annotation = sections_param.annotation
    
    assert sections_annotation != "tuple[Section, ...]", (
        f"FormLayout.sections annotation should accept sequences, not tuple-only: {sections_annotation}"
    )


def test_field_options_has_default_in_constructor_and_dataclass_metadata() -> None:
    """Verify that Field.options has a default both in constructor and dataclass metadata.
    
    Regression test: Field.__init__ has options=() default, so dataclass metadata
    should also report a default (not MISSING). Both normal construction and
    dataclass introspection must agree on the public contract.
    """
    import dataclasses
    import inspect
    
    # Constructor signature should show a default
    field_sig = inspect.signature(Field)
    options_param = field_sig.parameters["options"]
    assert options_param.default is not inspect.Parameter.empty, (
        "Field.__init__(options=...) should have a default value in signature"
    )
    
    # Dataclass metadata should also show a default (not MISSING)
    field_info = next(f for f in dataclasses.fields(Field) if f.name == "options")
    has_default = (
        field_info.default is not dataclasses.MISSING
        or field_info.default_factory is not dataclasses.MISSING
    )
    assert has_default, (
        "Field.options dataclass field should have a default or default_factory"
    )


def test_text_field_with_options_raises_error() -> None:
    """Verify that text fields with non-empty options raise ValueError."""
    try:
        Field(
            key="name",
            title="姓名",
            kind="text",
            record_path="name",
            anchor_cell="B23",
            options=(Option(label="N/A", code="na", cell="B24"),),
        )
        assert False, "Expected ValueError for text field with options"
    except ValueError as e:
        assert "text" in str(e).lower() or "options" in str(e).lower()


def test_single_choice_field_without_options_raises_error() -> None:
    """Verify that single_choice fields without options raise ValueError."""
    try:
        Field(
            key="status",
            title="狀態",
            kind="single_choice",
            record_path="status",
            anchor_cell="A1",
            options=(),
        )
        assert False, "Expected ValueError for single_choice field without options"
    except ValueError as e:
        assert "single_choice" in str(e).lower() or "options" in str(e).lower()


def test_multi_choice_field_without_options_raises_error() -> None:
    """Verify that multi_choice fields without options raise ValueError."""
    try:
        Field(
            key="interests",
            title="興趣",
            kind="multi_choice",
            record_path="interests",
            anchor_cell="A10",
            options=(),
        )
        assert False, "Expected ValueError for multi_choice field without options"
    except ValueError as e:
        assert "multi_choice" in str(e).lower() or "options" in str(e).lower()
