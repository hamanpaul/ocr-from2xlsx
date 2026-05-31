from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

Kind = Literal["text", "single_choice", "multi_choice"]


@dataclass(frozen=True, slots=True)
class Option:
    code: str
    label: str
    cell: str


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    kind: Kind
    options: tuple[Option, ...] = ()


@dataclass(frozen=True, slots=True)
class Section:
    key: str
    fields: tuple[Field, ...]


@dataclass(frozen=True, slots=True)
class FormLayout:
    sections: tuple[Section, ...]

    def iter_fields(self) -> Iterator[str]:
        for section in self.sections:
            for fld in section.fields:
                yield fld.key

    def field_by_key(self, key: str) -> Field | None:
        for section in self.sections:
            for fld in section.fields:
                if fld.key == key:
                    return fld
        return None

    def iter_options(self) -> Iterator[tuple[str, str]]:
        for section in self.sections:
            for fld in section.fields:
                for opt in fld.options:
                    yield (fld.key, opt.code)

    def options_by_code(self, field_key: str) -> dict[str, Option]:
        fld = self.field_by_key(field_key)
        if fld is None:
            return {}
        return {opt.code: opt for opt in fld.options}


def service_record_layout() -> FormLayout:
    raise NotImplementedError("service_record_layout not yet implemented")
