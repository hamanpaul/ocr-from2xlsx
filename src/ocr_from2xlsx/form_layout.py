"""Render-agnostic model for form-layout templates.

This module defines a shared data model for form layouts that is independent
of any specific rendering format (e.g., Excel). It provides a hierarchical
structure of sections, fields, and options that can be used to represent
form templates and their metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    record_path: str
    anchor_cell: str
    options: tuple[Option, ...] = ()


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    title: str
    fields: tuple[Field, ...]


@dataclass(frozen=True, slots=True)
class FormLayout:
    template_id: str
    sections: tuple[Section, ...]

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
            return {}
        return {opt.code: opt for opt in fld.options}


def service_record_layout() -> FormLayout:
    raise NotImplementedError("service_record_layout not yet implemented")
