"""Pure navigation/selection helpers for the keyboard-first review form.

No Tk/cv2 imports: these operate on plain data (ordered field keys, a flagged
set, the current key, an option count), so they are fully unit-testable. The Tk
layer in ``app.py`` (ConfirmForm/ReviewApp) wires focus and key bindings to
these decisions, mirroring ``_wheel_scroll_units`` / ``decide_camera_selection``.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence


def next_flagged_key(
    order: Sequence[str], flagged: Iterable[str], current: str | None
) -> str | None:
    """Return the next flagged key after ``current`` in ``order``, wrapping once.

    Only keys present in both ``order`` and ``flagged`` count. ``current`` need
    not be flagged: the scan starts just after ``current`` (or at the start when
    ``current`` is ``None`` / not in ``order``). Returns ``None`` when nothing is
    flagged."""
    order_set = set(order)
    flagged_set = {key for key in flagged if key in order_set}
    if not flagged_set:
        return None
    n = len(order)
    start = order.index(current) + 1 if current in order else 0
    for offset in range(n):
        key = order[(start + offset) % n]
        if key in flagged_set:
            return key
    return None


def prev_flagged_key(
    order: Sequence[str], flagged: Iterable[str], current: str | None
) -> str | None:
    """Return the previous flagged key before ``current`` in ``order``, wrapping."""
    order_set = set(order)
    flagged_set = {key for key in flagged if key in order_set}
    if not flagged_set:
        return None
    n = len(order)
    start = order.index(current) - 1 if current in order else n - 1
    for offset in range(n):
        key = order[(start - offset) % n]
        if key in flagged_set:
            return key
    return None


def option_index_for_digit(char: str, option_count: int) -> int | None:
    """Map a digit char ``"1".."9"`` to a 0-based option index, else ``None``.

    Returns ``None`` for non-single-digit input or a digit outside
    ``1..option_count``."""
    if not isinstance(char, str) or len(char) != 1 or not char.isdigit():
        return None
    digit = int(char)
    if digit < 1 or digit > option_count:
        return None
    return digit - 1
