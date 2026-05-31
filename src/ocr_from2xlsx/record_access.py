"""Read/write a Record by a dotted path (the form_layout record_path).

Walks attributes via getattr; when the current node is a dict (e.g. Services.consultation),
uses key access. A path of None is a no-op on set and returns None on get (form-only fields).
"""
from __future__ import annotations

from typing import Any


def get_by_path(record: Any, path: str | None) -> Any:
    if not path:
        return None
    node: Any = record
    for part in path.split("."):
        if node is None:
            return None
        node = node.get(part) if isinstance(node, dict) else getattr(node, part)
    return node


def set_by_path(record: Any, path: str | None, value: Any) -> None:
    if not path:
        return
    parts = path.split(".")
    node: Any = record
    for part in parts[:-1]:
        node = node[part] if isinstance(node, dict) else getattr(node, part)
    last = parts[-1]
    if isinstance(node, dict):
        node[last] = value
    else:
        if not hasattr(node, last):
            raise AttributeError(f"Record has no field for path part {last!r}")
        setattr(node, last, value)
