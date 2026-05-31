"""Render-agnostic model for form-layout templates.

This module defines a shared data model for form layouts that is independent
of any specific rendering format (e.g., Excel). It provides a hierarchical
structure of sections, fields, and options that can be used to represent
form templates and their metadata.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Iterator, Literal

Kind = Literal["text", "single_choice", "multi_choice"]


@dataclass(frozen=True, slots=True)
class Option:
    label: str
    code: str
    cell: str


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    title: str
    kind: Kind
    record_path: str | None
    anchor_cell: str
    options: tuple[Option, ...] = field(default_factory=tuple)

    def __init__(
        self,
        key: str,
        title: str,
        kind: Kind,
        record_path: str | None,
        anchor_cell: str,
        options: Sequence[Option] = (),
    ) -> None:
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "record_path", record_path)
        object.__setattr__(self, "anchor_cell", anchor_cell)
        object.__setattr__(self, "options", tuple(options))
        # Validate kind-options invariants
        if kind == "text" and self.options:
            raise ValueError(f"text field must have empty options, got {len(self.options)}")
        if kind in ("single_choice", "multi_choice") and not self.options:
            raise ValueError(f"{kind} field requires at least one option")
        # Reject duplicate option codes
        codes = [opt.code for opt in self.options]
        if len(codes) != len(set(codes)):
            seen = set()
            for code in codes:
                if code in seen:
                    raise ValueError(f"Duplicate option code: {code!r}")
                seen.add(code)


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    title: str
    fields: tuple[Field, ...]

    def __init__(self, id: str, title: str, fields: Sequence[Field]) -> None:
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "fields", tuple(fields))


@dataclass(frozen=True, slots=True)
class FormLayout:
    template_id: str
    sections: tuple[Section, ...]

    def __init__(self, template_id: str, sections: Sequence[Section]) -> None:
        object.__setattr__(self, "template_id", template_id)
        object.__setattr__(self, "sections", tuple(sections))
        # Reject duplicate field keys
        keys = [fld.key for sec in self.sections for fld in sec.fields]
        if len(keys) != len(set(keys)):
            seen = set()
            for key in keys:
                if key in seen:
                    raise ValueError(f"Duplicate field key: {key!r}")
                seen.add(key)

    def iter_fields(self) -> Iterator[Field]:
        for section in self.sections:
            for fld in section.fields:
                yield fld

    def field_by_key(self, key: str) -> Field | None:
        for section in self.sections:
            for fld in section.fields:
                if fld.key == key:
                    return fld
        return None

    def iter_options(self) -> Iterator[tuple[Field, Option]]:
        for section in self.sections:
            for fld in section.fields:
                for opt in fld.options:
                    yield (fld, opt)

    def options_by_code(self, field_key: str) -> dict[str, Option]:
        fld = self.field_by_key(field_key)
        if fld is None:
            raise KeyError(field_key)
        return {opt.code: opt for opt in fld.options}


def service_record_layout() -> FormLayout:
    raise NotImplementedError("service_record_layout not yet implemented")
