# Restyle Review UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `ReviewApp` a single themed appearance (light + dark) and a branded toolbar with one dominant `確認寫入` primary action, without changing layout or behavior.

**Architecture:** A new pure `theme.py` holds light/dark `Palette` tokens, `apply_theme()` (base `clam` + named ttk styles), a `ThemeManager` (mode + persistence + non-ttk widget recolour), and a cached `load_icon()`. `app.py` gains thin wiring: build the manager, construct a branded `tk.Frame` toolbar with icon-only secondary `tk.Button`s + tooltips and an accent `確認寫入` primary, register owned non-ttk widgets for recolour, and add a `檢視` dark-mode toggle. Config persistence becomes read-modify-write so `theme_mode` and `preview_rotation` coexist.

**Tech Stack:** Python 3.12, tkinter/ttk (`clam`), Pillow (already a dep), PyInstaller. No new runtime dependency.

**Verification note:** Real Tk works in this environment (`clam` present), so real-Tk tests run (not skipped). Run everything through `.venv/Scripts/python.exe`.

---

## File Structure

- Create: `src/ocr_from2xlsx/theme.py` — palettes, contrast util, `apply_theme`, `ThemeManager`, `load_icon`. One responsibility: appearance.
- Create: `src/ocr_from2xlsx/assets/icons/*.png` — generated line icons (open, import, prev, next, confirm, moon).
- Create: `build/make_icons.py` — regenerates the icon PNGs with Pillow (offline, reproducible).
- Modify: `src/ocr_from2xlsx/app.py` — config refactor, toolbar band, theming wiring, dark toggle, relabel.
- Modify: `build/ocr-from2xlsx.spec`, `pyproject.toml` — bundle icons.
- Modify: `CHANGELOG.md`, `README.md`.
- Test: `tests/test_theme.py` (Tk-free + real-Tk), `tests/test_app_theme.py` (real-Tk toolbar/wiring), `tests/test_app_config.py` (config merge).

---

## Task 1: Palette tokens + contrast utility (Tk-free)

**Files:**
- Create: `src/ocr_from2xlsx/theme.py`
- Test: `tests/test_theme.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py
import pytest
from ocr_from2xlsx import theme
from ocr_from2xlsx.theme import LIGHT, DARK, contrast_ratio

REQUIRED_TOKENS = [
    "brand", "on_brand", "accent", "on_accent", "bg", "surface",
    "border", "text", "text_muted",
    "success_bg", "success_fg", "warning_bg", "warning_fg",
    "danger_bg", "danger_fg",
]

@pytest.mark.parametrize("pal", [LIGHT, DARK])
def test_palette_exposes_required_tokens(pal):
    for tok in REQUIRED_TOKENS:
        assert isinstance(getattr(pal, tok), str) and getattr(pal, tok).startswith("#")

@pytest.mark.parametrize("pal", [LIGHT, DARK])
def test_body_text_pairs_meet_aa(pal):
    assert contrast_ratio(pal.text, pal.surface) >= 4.5
    assert contrast_ratio(pal.text, pal.bg) >= 4.5
    assert contrast_ratio(pal.text_muted, pal.surface) >= 4.5
    assert contrast_ratio(pal.on_brand, pal.brand) >= 4.5
    assert contrast_ratio(pal.on_accent, pal.accent) >= 4.5

def test_type_and_spacing_scales():
    assert theme.FONT_BODY == 14
    assert theme.SPACE == 8
```

- [ ] **Step 2: Run test to verify it fails** — `.venv/Scripts/python.exe -m pytest tests/test_theme.py -q` → FAIL (no module `theme`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/ocr_from2xlsx/theme.py
from __future__ import annotations

from dataclasses import dataclass

FONT_FAMILY = "Microsoft JhengHei UI"
FONT_CAPTION = 12
FONT_BODY = 14
FONT_INPUT = 15
FONT_SECTION = 15
FONT_HEADING = 18
SPACE = 8  # base spacing unit (4/8 rhythm)


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


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = (_srgb_to_linear(x) for x in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)
```

- [ ] **Step 4: Run test to verify it passes** — `.venv/Scripts/python.exe -m pytest tests/test_theme.py -q` → PASS.

- [ ] **Step 5: Commit** — deferred to the end per the session pipeline (single feature commit).

---

## Task 2: `apply_theme` (real Tk)

**Files:** Modify `src/ocr_from2xlsx/theme.py`; Test `tests/test_theme.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py (append)
import tkinter as tk
from tkinter import ttk

def _root_or_skip():
    try:
        r = tk.Tk(); r.withdraw(); return r
    except tk.TclError:
        pytest.skip("no display")

def test_apply_theme_sets_clam_and_named_styles():
    r = _root_or_skip()
    try:
        style = ttk.Style()
        theme.apply_theme(r, style, LIGHT)
        assert style.theme_use() == "clam"
        assert style.lookup("Primary.TButton", "background") == LIGHT.accent
        assert style.lookup("Toolbar.TFrame", "background") == LIGHT.brand
        assert style.lookup("Section.TLabelframe.Label", "foreground") == LIGHT.text
        theme.apply_theme(r, style, DARK)
        assert style.lookup("Primary.TButton", "background") == DARK.accent
    finally:
        r.destroy()
```

- [ ] **Step 2: Run** → FAIL (`apply_theme` missing).

- [ ] **Step 3: Implement** (append to `theme.py`)

```python
def apply_theme(root, style, palette: Palette) -> None:
    style.theme_use("clam")
    base = (FONT_FAMILY, FONT_BODY)
    root.configure(background=palette.bg)
    style.configure(".", background=palette.bg, foreground=palette.text,
                    fieldbackground=palette.surface, bordercolor=palette.border,
                    font=base)
    style.configure("TFrame", background=palette.bg)
    style.configure("TLabel", background=palette.bg, foreground=palette.text, font=base)
    style.configure("Muted.TLabel", background=palette.bg, foreground=palette.text_muted)
    style.configure("FieldTitle.TLabel", background=palette.bg,
                    foreground=palette.text_muted, font=(FONT_FAMILY, FONT_CAPTION))
    style.configure("TEntry", fieldbackground=palette.surface, foreground=palette.text,
                    bordercolor=palette.border, insertcolor=palette.text,
                    padding=4, font=(FONT_FAMILY, FONT_INPUT))
    style.map("TEntry", bordercolor=[("focus", palette.focus)])
    style.configure("TButton", background=palette.surface_alt, foreground=palette.text,
                    bordercolor=palette.border, focusthickness=2,
                    focuscolor=palette.focus, padding=(10, 6))
    style.map("TButton",
              background=[("active", palette.border), ("disabled", palette.surface_alt)],
              foreground=[("disabled", palette.disabled_fg)])
    style.configure("Primary.TButton", background=palette.accent,
                    foreground=palette.on_accent, bordercolor=palette.accent,
                    font=(FONT_FAMILY, FONT_BODY, "bold"), padding=(16, 8))
    style.map("Primary.TButton",
              background=[("active", palette.accent_hover), ("disabled", palette.accent_disabled)],
              foreground=[("disabled", palette.on_accent_disabled)])
    style.configure("TCheckbutton", background=palette.bg, foreground=palette.text)
    style.map("TCheckbutton", background=[("active", palette.bg)])
    style.configure("TLabelframe", background=palette.bg, bordercolor=palette.border)
    style.configure("TLabelframe.Label", background=palette.bg, foreground=palette.text)
    style.configure("Section.TLabelframe", background=palette.bg, bordercolor=palette.border)
    style.configure("Section.TLabelframe.Label", background=palette.bg,
                    foreground=palette.text, font=(FONT_FAMILY, FONT_SECTION, "bold"))
    style.configure("TSeparator", background=palette.border)
    style.configure("TPanedwindow", background=palette.bg)
    style.configure("Vertical.TScrollbar", background=palette.surface_alt,
                    troughcolor=palette.bg, bordercolor=palette.border,
                    arrowcolor=palette.text_muted)
    for name, bg, fg in (
        ("Status.Success.TLabel", palette.success_bg, palette.success_fg),
        ("Status.Warning.TLabel", palette.warning_bg, palette.warning_fg),
        ("Status.Danger.TLabel", palette.danger_bg, palette.danger_fg),
    ):
        style.configure(name, background=bg, foreground=fg)
```

- [ ] **Step 4: Run** → PASS.

---

## Task 3: `ThemeManager` (headless via fakes)

**Files:** Modify `theme.py`; Test `tests/test_theme.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py (append)
class _FakeStyle:
    def __init__(self): self.calls = []
    def theme_use(self, *a): self.calls.append(("theme_use", a)); return a[0] if a else "clam"
    def configure(self, *a, **k): self.calls.append(("configure", a, k))
    def map(self, *a, **k): self.calls.append(("map", a, k))
    def lookup(self, *a, **k): return ""

class _FakeWidget:
    def __init__(self): self.cfg = {}
    def configure(self, **k): self.cfg.update(k)

class _FakeRoot(_FakeWidget):
    pass

def test_manager_toggle_and_recolor_and_callback():
    seen = []
    mgr = theme.ThemeManager(_FakeRoot(), _FakeStyle(), mode="light",
                             on_change=seen.append)
    w = _FakeWidget()
    mgr.register(w, role="canvas")
    assert w.cfg["background"] == LIGHT.bg
    mgr.toggle()
    assert mgr.mode == "dark"
    assert w.cfg["background"] == DARK.bg
    assert seen == ["dark"]

def test_manager_defaults_invalid_mode_to_light():
    mgr = theme.ThemeManager(_FakeRoot(), _FakeStyle(), mode="bogus")
    assert mgr.mode == "light"
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** (append to `theme.py`)

```python
class ThemeManager:
    _ROLES = {
        "canvas": lambda p: (p.bg, p.text),
        "surface": lambda p: (p.surface, p.text),
        "banner": lambda p: (p.surface_alt, p.text_muted),
        "toolbar": lambda p: (p.brand, p.on_brand),
    }

    def __init__(self, root, style, mode="light", on_change=None):
        self._root = root
        self._style = style
        self._mode = mode if mode in PALETTES else "light"
        self._registered = []
        self._on_change = on_change

    @property
    def mode(self):
        return self._mode

    @property
    def palette(self):
        return PALETTES[self._mode]

    def apply(self):
        apply_theme(self._root, self._style, self.palette)
        for widget, role in self._registered:
            self._paint(widget, role)

    def register(self, widget, role="surface"):
        self._registered.append((widget, role))
        self._paint(widget, role)

    def set_mode(self, mode):
        if mode not in PALETTES:
            return
        self._mode = mode
        self.apply()
        if self._on_change:
            self._on_change(mode)

    def toggle(self):
        self.set_mode("dark" if self._mode == "light" else "light")

    def _paint(self, widget, role):
        bg, fg = self._ROLES.get(role, self._ROLES["surface"])(self.palette)
        try:
            widget.configure(background=bg)
        except Exception:
            pass
        try:
            widget.configure(foreground=fg)
        except Exception:
            pass
```

- [ ] **Step 4: Run** → PASS. (Note: `register` paints immediately; `apply()` repaints all — the toggle test relies on `set_mode`→`apply`.)

---

## Task 4: `load_icon` (real Tk, needs icons from Task 7 or a stub)

**Files:** Modify `theme.py`; Test `tests/test_theme.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py (append)
def test_load_icon_missing_returns_none():
    r = _root_or_skip()
    try:
        assert theme.load_icon("does-not-exist", 24) is None
    finally:
        r.destroy()

def test_load_icon_existing_returns_image_and_caches():
    r = _root_or_skip()
    try:
        img1 = theme.load_icon("confirm", 24)
        assert img1 is not None
        img2 = theme.load_icon("confirm", 24)
        assert img1 is img2  # cached
    finally:
        r.destroy()
        theme._ICON_CACHE.clear()
```

- [ ] **Step 2: Run** → FAIL (function missing; `confirm` icon added in Task 7).

- [ ] **Step 3: Implement** (append to `theme.py`)

```python
from pathlib import Path

_ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
_ICON_CACHE = {}


def load_icon(name, size=24):
    key = (name, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = _ICON_DIR / f"{name}.png"
    if not path.is_file():
        return None
    try:
        from PIL import Image, ImageTk
        img = Image.open(path).convert("RGBA")
        if img.size != (size, size):
            img = img.resize((size, size), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
    except Exception:
        return None
    _ICON_CACHE[key] = photo
    return photo
```

- [ ] **Step 4:** Run after Task 7 has generated `confirm.png` → PASS.

---

## Task 5: Config persistence is read-modify-write

**Files:** Modify `src/ocr_from2xlsx/app.py` (`_load_config`/`_update_config`, rewire rotation + theme); Test `tests/test_app_config.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app_config.py
from ocr_from2xlsx.app import ReviewApp

def test_config_merge_preserves_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    ReviewApp._update_config(preview_rotation=90)
    ReviewApp._update_config(theme_mode="dark")
    data = ReviewApp._load_config()
    assert data["preview_rotation"] == 90
    assert data["theme_mode"] == "dark"

def test_load_config_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    assert ReviewApp._load_config() == {}
```

- [ ] **Step 2: Run** → FAIL (`_update_config`/`_load_config` missing).

- [ ] **Step 3: Implement** — in `app.py`, add classmethods and rewire:

```python
    @classmethod
    def _load_config(cls) -> dict:
        import json
        try:
            return json.loads(cls._config_path().read_text(encoding="utf-8"))
        except Exception:
            return {}

    @classmethod
    def _update_config(cls, **values) -> None:
        import json
        try:
            path = cls._config_path()
            data = cls._load_config()
            data.update(values)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    @classmethod
    def _load_preview_rotation(cls) -> int:
        try:
            return int(cls._load_config().get("preview_rotation", 0)) % 360
        except Exception:
            return 0

    def _save_preview_rotation(self) -> None:
        self._update_config(preview_rotation=self._preview_rotation)

    @classmethod
    def _load_theme_mode(cls) -> str:
        mode = cls._load_config().get("theme_mode", "light")
        return mode if mode in ("light", "dark") else "light"
```

- [ ] **Step 4: Run** → PASS. Also run existing rotation-related tests to confirm no regression.

---

## Task 6: Generate line icons with Pillow

**Files:** Create `build/make_icons.py`; output `src/ocr_from2xlsx/assets/icons/*.png`.

- [ ] **Step 1:** Write `build/make_icons.py` that draws 6 white-on-transparent line icons at 48×48 (rendered down at load): `open` (document), `import` (folder + down arrow), `prev` (chevron-left), `next` (chevron-right), `confirm` (check), `moon` (dark-mode). Use `PIL.ImageDraw` with stroke width 3, rounded caps. White glyph so it reads on the teal band; the primary/confirm icon is drawn dark (`#3D2C00`) for the amber button.

- [ ] **Step 2:** Run `.venv/Scripts/python.exe build/make_icons.py` and confirm 6 PNGs exist under `src/ocr_from2xlsx/assets/icons/`.

- [ ] **Step 3:** Now Task 4's `test_load_icon_existing_returns_image_and_caches` passes.

(Deviation note: the spec named Fluent System Icons; to stay offline and dependency-free we generate equivalent simple line icons. Recorded in the change's proposal/CHANGELOG.)

---

## Task 7: Branded toolbar band + icon-only buttons + primary CTA (real Tk)

**Files:** Modify `app.py` `_build_ui` toolbar block (around `app.py:827-852`) and the `編輯` menu label (`app.py:806`); Test `tests/test_app_theme.py`.

- [ ] **Step 1: Write the failing test** (mirror existing real-Tk app tests; skip on `tk.TclError`)

```python
# tests/test_app_theme.py
import tkinter as tk
import pytest
from ocr_from2xlsx.app import ReviewApp

def _app_or_skip():
    try:
        app = ReviewApp()
    except tk.TclError:
        pytest.skip("no display")
    app.withdraw()
    return app

def test_toolbar_has_primary_confirm_and_icononly_secondary():
    app = _app_or_skip()
    try:
        assert app._confirm_btn.cget("text") == "確認寫入"
        # secondary buttons are icon-only (no text), each has a tooltip
        for b in (app._open_btn, app._import_btn, app._prev_btn, app._next_btn):
            assert b.cget("text") == ""
            assert b.image  # an icon is set
    finally:
        app.destroy()

def test_prev_next_disabled_without_records():
    app = _app_or_skip()
    try:
        app.records = []
        app._update_toolbar_states()
        assert str(app._prev_btn["state"]) == "disabled"
        assert str(app._next_btn["state"]) == "disabled"
    finally:
        app.destroy()
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** — replace the toolbar block. Band is a `tk.Frame(bg=brand)`; secondary buttons are icon-only `tk.Button` (flat, brand bg, tooltip via `_Tooltip`); the primary is `ttk.Button(style="Primary.TButton", text="確認寫入")` OR a `tk.Button` styled amber. Keep `_register(...)` wiring intact so `_update_toolbar_states()` is unchanged. Store button refs (`self._open_btn`, `_import_btn`, `_prev_btn`, `_next_btn`, `_confirm_btn`). Relabel `編輯` menu item to `確認寫入`. Give secondary `tk.Button`s `width`/`height`/`padx`/`pady` so the hit-area ≥44px. (Full code written during execution; the icon load uses `theme.load_icon` and holds refs on `self`.)

- [ ] **Step 4: Run** → PASS.

---

## Task 8: Theming wiring + dark-mode toggle (real Tk)

**Files:** Modify `app.py` `__init__`/`_build_ui`; Test `tests/test_app_theme.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app_theme.py (append)
def test_theme_toggle_switches_mode_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path))
    app = _app_or_skip()
    try:
        assert app.theme.mode == "light"
        app._toggle_theme()
        assert app.theme.mode == "dark"
        assert ReviewApp._load_config().get("theme_mode") == "dark"
    finally:
        app.destroy()
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** — in `__init__`, after building UI: create `self.theme = ThemeManager(self, ttk.Style(), mode=self._load_theme_mode(), on_change=lambda m: self._update_config(theme_mode=m))`, `self.theme.apply()`, register owned non-ttk widgets (`self._form_canvas` role="canvas", `self._autocapture_banner` role="banner", `self._badge_label` role handled by status logic, footer `tk.Label`s). Add `_toggle_theme()` calling `self.theme.toggle()`; add a `檢視` menu checkbutton bound to it and a toolbar toggle button (moon icon). Ensure the toolbar band frame is registered role="toolbar" (or built from brand token directly).

- [ ] **Step 4: Run** → PASS.

---

## Task 9: Packaging (icons into the bundle)

**Files:** Modify `build/ocr-from2xlsx.spec`, `pyproject.toml`.

- [ ] **Step 1:** In `.spec` `datas`, add every generated icon (or a small loop collecting `src/ocr_from2xlsx/assets/icons/*.png` → `ocr_from2xlsx/assets/icons`).
- [ ] **Step 2:** In `pyproject.toml` `[tool.setuptools.package-data]`, add `"assets/icons/*.png"` to the `ocr_from2xlsx` list.
- [ ] **Step 3:** `.venv/Scripts/python.exe build/verify_roundtrip.py` (write path unaffected but confirms no import/theme break). Full exe rebuild (`python build/package.py`) attempted; if the heavy PyInstaller build can't complete in this environment, note it in the PR (icons follow the proven asset-bundling pattern).

---

## Task 10: Docs + full verification

**Files:** `CHANGELOG.md`, `README.md`.

- [ ] **Step 1:** CHANGELOG `[Unreleased]` `### Added`/`### Changed` bullets: themed light/dark appearance, branded toolbar with single primary `確認寫入` (renamed from `確認並寫入`), icon-only secondary buttons with tooltips, dark-mode toggle in `檢視`.
- [ ] **Step 2:** README: update wording/screenshots referencing the toolbar and `確認並寫入`.
- [ ] **Step 3:** `.venv/Scripts/python.exe -W error -m pytest -q` → all green (731+ new tests).
- [ ] **Step 4:** `.venv/Scripts/python.exe -m policy_check --repo .` (+ `--pr-*` flags) → green.

---

## Task 11: Ship

- [ ] Stage all; single feature commit on `feature/ui-redesign`; push; open PR with the repo template checklist and CHANGELOG reference.

---

## Self-Review

- **Spec coverage:** token theme (Task 1-2, 8) ✓; light/dark persisted+default (Task 3,5,8) ✓; branded toolbar single primary (Task 7) ✓; icon-only + tooltip + menu fallback + ≥44px + no emoji (Task 6,7) ✓; disabled-visual without changing rules (Task 7 test + unchanged `_update_toolbar_states`) ✓.
- **Placeholder scan:** Task 7 impl says "full code during execution" — acceptable because the toolbar edit is an in-place restructure of an existing block; signatures (`self._confirm_btn`, `_prev_btn`, `theme.load_icon`) are fixed here.
- **Type consistency:** `ThemeManager(root, style, mode, on_change)`, `register(widget, role)`, `set_mode`/`toggle`, `load_icon(name, size)`, `_load_config`/`_update_config`/`_load_theme_mode` — used consistently across tasks.
