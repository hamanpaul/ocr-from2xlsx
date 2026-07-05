# Implementation Tasks: Restyle the review app — themed appearance + branded toolbar

**Change ID:** `restyle-review-ui`

All implementation used TDD with fail-first tests before production code. The pure theme core
(Phase 1) and the config refactor (Phase 2) landed first (no Tk); the Tk surfaces (Phases 3–4)
followed with real-Tk tests that skip cleanly when no display is available.

## Phase 1: Pure theme core (`theme.py`, no window)

- [x] 1.1 Fail-first Tk-free tests: `LIGHT`/`DARK` expose all required tokens; text/on-colour pairs
  meet WCAG AA (≥4.5:1); type/spacing scales are the documented values.
- [x] 1.2 `Palette` dataclass + `LIGHT`/`DARK` + typography/spacing constants; no Tk/cv2 at import.
- [x] 1.3 Fail-first real-Tk tests for `apply_theme`: base becomes `clam`; expected named styles
  (`Toolbar.TFrame`, `Toolbar.TButton`, `Primary.TButton`, `Section.TLabelframe(.Label)`, `TEntry`
  font) are configured from the palette.
- [x] 1.4 Implement `apply_theme()`.
- [x] 1.5 Fail-first tests for `ThemeManager` via fakes: mode init, `toggle`/`set_mode`, registered
  non-ttk widget recolour, `on_change` callback.
- [x] 1.6 Implement `ThemeManager` + `load_icon`. NOTE: `load_icon` caches the interpreter-independent
  **PIL image** keyed by `(name, size)` and returns a fresh `PhotoImage` per call (a PhotoImage is
  bound to its root; a root-`id()` cache is unsafe because ids are recycled — fixed after review).

**Quality Gate:**
- [x] Palette/contrast/scale tests pass headless; `apply_theme`/`ThemeManager`/`load_icon` tests pass
  under real Tk and skip cleanly with no display.

## Phase 2: Config persistence is read-modify-write

- [x] 2.1 Fail-first tests: saving `theme_mode` preserves `preview_rotation` and vice-versa; missing
  file loads as empty; `_load_theme_mode` defaults to light and rejects bogus values.
- [x] 2.2 `_load_config()` / `_update_config()` (read-modify-write, `OSError`-safe); rotation + theme
  routed through them.

**Quality Gate:**
- [x] Config round-trip tests pass; existing `preview_rotation` persistence still works.

## Phase 3: Branded toolbar band, icon-only buttons, primary CTA

- [x] 3.1 Fail-first real-Tk tests: band styled branded; secondary actions icon-only with tooltips;
  primary is `確認寫入` (Primary style) invoking `_confirm_current`; prev/next disabled without records.
- [x] 3.2 Toolbar band in `_build_ui`: branded `ttk.Frame`; icon-only `ttk.Button`s (Toolbar style)
  wired through existing `_register` keys with `_Tooltip`s; accent `確認寫入` primary; dark toggle
  (moon). `_update_toolbar_states()` rules unchanged. `編輯` menu item relabelled `確認寫入`.

**Quality Gate:**
- [x] Toolbar band / icon-only + tooltip / primary-CTA / disabled-visual tests pass under real Tk.

## Phase 4: App-wide theming + dark-mode toggle

- [x] 4.1 Fail-first tests: `檢視` dark-mode checkbutton + toolbar toggle flip mode; owned non-ttk
  widgets (form `Canvas`, capture banner) recolour on toggle; `theme_mode` persists; opens in saved mode.
- [x] 4.2 Wire `ThemeManager` in `__init__` (persisted mode, register owned tk widgets, `apply`),
  `_toggle_theme`, `檢視` checkbutton + toolbar toggle. Banner + neutral badge chip made theme-aware
  (dark tokens in dark mode; written/blocked keep strong high-contrast colours). Section style wired
  onto form group LabelFrames.

**Quality Gate:**
- [x] Toggle + recolour + persistence + section-style tests pass under real Tk.

## Phase 5: Icon assets & packaging

- [x] 5.1 `build/make_icons.py` generates 6 line-glyph PNGs (open/import/prev/next/confirm/moon) with
  Pillow into `assets/icons/` (offline, reproducible; whitelisted in `.gitignore` beside
  `make_shutter_wav.py`). NOTE: generated at 96×96 and downscaled by `load_icon` (plan said 48×48;
  harmless). Deviation from the proposal's "Fluent System Icons": generated equivalents to stay
  offline + dependency-free.
- [x] 5.2 Icons dir added to `build/ocr-from2xlsx.spec` `datas` and `pyproject` `package-data`.
- [x] 5.3 `build/verify_roundtrip.py` PASS (real template, 14 images preserved); exe rebuilt via
  `build/package.py` (exit 0, `--help` marker check passed) with icons bundled.

**Quality Gate:**
- [x] Packaged exe builds; write-path roundtrip passes.

## Phase 6: Integration, docs & verification

- [x] 6.1 CHANGELOG `[Unreleased]` Added (light/dark theme) + Changed (toolbar restyle + `確認寫入`
  relabel); README toolbar/shortcut/overwrite wording + dark-mode note; CLI help unchanged.
- [x] 6.2 `python -W error -m pytest -q`: 751 passed, 2 skipped (pre-existing). `policy_check --repo .`
  green (PR-context rules simulated at commit time).
- [x] 6.3 Behavior verified by the real-Tk automated suite (Tk available; tests ran, not skipped):
  toolbar band + icon-only buttons + tooltips, primary CTA, prev/next disabled-without-records, theme
  toggle + persistence, non-ttk recolour, banner/badge dark tokens. NOTE: a separate interactive
  operator GUI session at 100%/200% DPI was NOT run in this environment — recommended as a pre-release
  smoke check.
- [x] 6.4 Base OpenSpec spec (`openspec/specs/app-appearance/spec.md`) created on archive.

**Quality Gate:**
- [x] Full suite + roundtrip green; docs updated; light/dark exercised by real-Tk tests; ready to archive.

## Completion Checklist

- [x] All phases complete and quality gates green
- [x] CHANGELOG `[Unreleased]`, README updated
- [x] Ready for `/openspec-archive restyle-review-ui`
