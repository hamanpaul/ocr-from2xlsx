"""Appearance/theming core for the review app.

Pure, testable design tokens (`Palette`, light + dark), a `contrast_ratio`
utility, `apply_theme` (base `clam` + named ttk styles), a `ThemeManager`
(mode + persistence hook + non-ttk widget recolour), and a cached `load_icon`.

Kept out of `app.py` so appearance is a single, unit-testable responsibility.
No cv2 / workbook imports at module top; Pillow is imported lazily in
`load_icon` (it is already a runtime dependency for the image preview).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --- typography / spacing scales -------------------------------------------

FONT_FAMILY = "Microsoft JhengHei UI"  # renders Traditional Chinese + Latin on Windows
FONT_BODY = 14      # base / body text
FONT_INPUT = 15     # form entry text (slightly larger for data entry)
FONT_SECTION = 15   # section (LabelFrame) headers, bold
SPACE = 8           # base spacing unit (4 / 8 rhythm)


# --- palette ----------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    name: str
    brand: str
    on_brand: str
    brand_hover: str
    accent: str
    on_accent: str
    accent_hover: str
    accent_disabled: str
    on_accent_disabled: str
    bg: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_muted: str
    disabled_fg: str
    focus: str
    success_bg: str
    success_fg: str
    warning_bg: str
    warning_fg: str
    danger_bg: str
    danger_fg: str


LIGHT = Palette(
    name="light",
    brand="#0F5F5B", on_brand="#FFFFFF", brand_hover="#0B4A47",
    accent="#FFB703", on_accent="#3D2C00", accent_hover="#E5A400",
    accent_disabled="#D8DEDD", on_accent_disabled="#7C8785",
    bg="#F4F6F7", surface="#FFFFFF", surface_alt="#EAF0EF",
    border="#D7E0DF", text="#1B2A29", text_muted="#4F5D5B",
    disabled_fg="#9BA7A5", focus="#1A857F",
    success_bg="#D4EDDA", success_fg="#1E4620",
    warning_bg="#FFF3CD", warning_fg="#6B5200",
    danger_bg="#F8D7DA", danger_fg="#842029",
)

DARK = Palette(
    name="dark",
    brand="#0C3F3C", on_brand="#FFFFFF", brand_hover="#12514D",
    accent="#FFB703", on_accent="#3D2C00", accent_hover="#E5A400",
    accent_disabled="#3A3A3A", on_accent_disabled="#8A9795",
    bg="#1E1E1E", surface="#252526", surface_alt="#2D2D30",
    border="#3A3A3A", text="#E6E6E6", text_muted="#B7BFBE",
    disabled_fg="#6E7A78", focus="#4FD1C5",
    success_bg="#14331C", success_fg="#8FE0A9",
    warning_bg="#3A2F00", warning_fg="#F2CE5B",
    danger_bg="#3B1518", danger_fg="#F5A3AB",
)

PALETTES = {"light": LIGHT, "dark": DARK}


# --- contrast ---------------------------------------------------------------

def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = (_srgb_to_linear(x) for x in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colours (>= 1.0)."""
    l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# --- apply_theme ------------------------------------------------------------

def apply_theme(root, style, palette: Palette) -> None:
    """Switch to the ``clam`` base and (re)configure every widget + named style
    from ``palette``. Safe to call repeatedly to change mode."""
    style.theme_use("clam")
    base = (FONT_FAMILY, FONT_BODY)
    try:
        root.configure(background=palette.bg)
    except Exception:
        pass

    style.configure(
        ".", background=palette.bg, foreground=palette.text,
        fieldbackground=palette.surface, bordercolor=palette.border, font=base,
    )
    style.configure("TFrame", background=palette.bg)
    style.configure("Toolbar.TFrame", background=palette.brand)
    style.configure("TLabel", background=palette.bg, foreground=palette.text, font=base)
    style.configure(
        "TEntry", fieldbackground=palette.surface, foreground=palette.text,
        bordercolor=palette.border, insertcolor=palette.text, padding=4,
        font=(FONT_FAMILY, FONT_INPUT),
    )
    style.map("TEntry", bordercolor=[("focus", palette.focus)])
    style.configure(
        "TButton", background=palette.surface_alt, foreground=palette.text,
        bordercolor=palette.border, focuscolor=palette.focus, padding=(10, 6),
    )
    style.map(
        "TButton",
        background=[("active", palette.border), ("disabled", palette.surface_alt)],
        foreground=[("disabled", palette.disabled_fg)],
    )
    style.configure(
        "Primary.TButton", background=palette.accent, foreground=palette.on_accent,
        bordercolor=palette.accent, font=(FONT_FAMILY, FONT_BODY, "bold"),
        padding=(16, 8),
    )
    style.map(
        "Primary.TButton",
        background=[("active", palette.accent_hover), ("disabled", palette.accent_disabled)],
        foreground=[("disabled", palette.on_accent_disabled)],
    )
    # Icon-only secondary buttons that sit on the branded toolbar band.
    style.configure(
        "Toolbar.TButton", background=palette.brand, foreground=palette.on_brand,
        bordercolor=palette.brand, relief="flat", padding=10,
        focuscolor=palette.on_brand,
    )
    style.map(
        "Toolbar.TButton",
        background=[("active", palette.brand_hover), ("disabled", palette.brand)],
        foreground=[("disabled", palette.on_accent_disabled)],
    )
    style.configure("TCheckbutton", background=palette.bg, foreground=palette.text)
    style.map("TCheckbutton", background=[("active", palette.bg)])
    style.configure("TLabelframe", background=palette.bg, bordercolor=palette.border)
    style.configure("TLabelframe.Label", background=palette.bg, foreground=palette.text)
    style.configure("Section.TLabelframe", background=palette.bg, bordercolor=palette.border)
    style.configure(
        "Section.TLabelframe.Label", background=palette.bg,
        foreground=palette.text, font=(FONT_FAMILY, FONT_SECTION, "bold"),
    )
    style.configure("TSeparator", background=palette.border)
    style.configure("TPanedwindow", background=palette.bg)
    style.configure(
        "Vertical.TScrollbar", background=palette.surface_alt,
        troughcolor=palette.bg, bordercolor=palette.border,
        arrowcolor=palette.text_muted,
    )


# --- ThemeManager -----------------------------------------------------------

class ThemeManager:
    """Owns the current mode; re-applies the palette and recolours registered
    non-ttk (``tk``) widgets on switch. ``on_change(mode)`` fires after a switch
    (used to persist the choice)."""

    # Roles for the non-ttk (tk) widgets the app registers for recolour on mode switch.
    # (ttk widgets re-theme via the styles, so only these plain-tk surfaces need this.)
    _ROLES = {
        "canvas": lambda p: (p.bg, p.text),
        "surface": lambda p: (p.surface, p.text),
        "banner": lambda p: (p.surface_alt, p.text_muted),
    }

    def __init__(self, root, style, mode="light", on_change=None):
        self._root = root
        self._style = style
        self._mode = mode if mode in PALETTES else "light"
        self._registered: list[tuple[object, str]] = []
        self._on_change = on_change

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def palette(self) -> Palette:
        return PALETTES[self._mode]

    def apply(self) -> None:
        apply_theme(self._root, self._style, self.palette)
        for widget, role in self._registered:
            self._paint(widget, role)

    def register(self, widget, role="surface") -> None:
        self._registered.append((widget, role))
        self._paint(widget, role)

    def set_mode(self, mode) -> None:
        if mode not in PALETTES:
            return
        self._mode = mode
        self.apply()
        if self._on_change:
            self._on_change(mode)

    def toggle(self) -> None:
        self.set_mode("dark" if self._mode == "light" else "light")

    def _paint(self, widget, role) -> None:
        bg, fg = self._ROLES.get(role, self._ROLES["surface"])(self.palette)
        try:
            widget.configure(background=bg)
        except Exception:
            pass
        try:
            widget.configure(foreground=fg)
        except Exception:
            pass


# --- icons ------------------------------------------------------------------

_ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
# Cache the *decoded/resized PIL image* (interpreter-independent) keyed by (name, size).
# A ``PhotoImage`` must NOT be cached across roots: it is bound to the interpreter that
# created it, and a recreated root can reuse the previous root's ``id()``, so a root-keyed
# PhotoImage cache would hand back an image tied to a destroyed interpreter (TclError).
_PIL_CACHE: dict[tuple[str, int], object] = {}


def load_icon(name, size=24):
    """Return a fresh ``PhotoImage`` for ``assets/icons/<name>.png`` at ``size``, or
    ``None`` if the file is missing / cannot be loaded. The decoded PIL image is cached;
    a new ``PhotoImage`` is built per call, so callers MUST keep the returned reference
    alive (e.g. ``widget.image = load_icon(...)``) — Tk does not."""
    path = _ICON_DIR / f"{name}.png"
    if not path.is_file():
        return None
    key = (name, size)
    try:
        from PIL import Image, ImageTk

        pil = _PIL_CACHE.get(key)
        if pil is None:
            pil = Image.open(path).convert("RGBA")
            if pil.size != (size, size):
                pil = pil.resize((size, size), Image.LANCZOS)
            _PIL_CACHE[key] = pil
        return ImageTk.PhotoImage(pil)
    except Exception:
        return None
