# Proposal: Restyle the review app — themed appearance + branded toolbar

**Change ID:** `restyle-review-ui`
**Created:** 2026-07-01
**Status:** Draft

---

## Problem Statement

`ReviewApp` (`app.py`) runs on the stock ttk look (`vista`) with no theming layer: colours,
fonts, and spacing are whatever each platform's default theme paints, and there is no dark
mode for the operator's long, low-light correction sessions. The result reads as "陽春" —
plain and undesigned — and there is no single source of truth for appearance, so any future
polish has to be hand-tuned per widget.

The toolbar is a flat row of five equal-weight text buttons (`開啟報表`, `匯入資料夾`,
`上一筆`, `下一筆`, `確認並寫入`). Every button looks the same, so the one action the
operator runs on every single record — write the row — has no more visual weight than the
rarely-used ones, and the row is wordy. Nothing signals which controls are usable in the
current state at a glance beyond the ttk default disabled greying.

Affected: the cancer-resource-center operator keying scanned paper service-records into Excel
all day — the same high-volume hot loop the recent keyboard/exception-first work targeted.

## Proposed Solution

Give the app a **single themed appearance system** and a **branded toolbar with one obvious
primary action**, without restructuring the window layout or changing any recognition, write,
or navigation behavior.

- **Design tokens + `ttk.Style` theming (no new dependency).** A new pure `theme.py` holds
  colour / typography / spacing tokens in a light and a dark `Palette`, and an
  `apply_theme(root, style, palette)` that switches the base theme to `clam` (the only built-in
  theme that honours custom colours broadly) and configures every ttk widget style and a set of
  named styles (`Toolbar.TFrame`, `Primary.TButton`, `Section.TLabelframe`, …) from those tokens.
- **Light + dark mode, persisted and toggleable.** A `ThemeManager` tracks the current mode,
  re-applies the palette on switch, and recolours the handful of non-ttk `tk` widgets the app
  owns (the form `Canvas`, the continuous-capture banner, the status/badge `tk.Label`s). The
  choice persists in the existing `config.json` and defaults to light on first run. Entry points:
  a `檢視(V)` menu checkbutton and a small toggle at the right of the toolbar band.
- **Branded toolbar band + single primary CTA.** A colour-branded `tk.Frame` band sits below the
  native menu bar. Secondary actions (`開啟報表`, `匯入`, `上一筆`, `下一筆`) become **icon-only**
  buttons with hover tooltips (including their keyboard shortcuts); the primary action becomes a
  prominent accent-coloured block button relabelled **`確認寫入`** (from `確認並寫入`) with a
  check icon and an `⏎` hint. This matches the "one primary CTA per screen, secondary
  subordinate" principle and mirrors the existing `Enter`-to-confirm shortcut.
- **Discoverability preserved.** Icon-only toolbar buttons keep hover tooltips, and the full-text
  equivalents remain in the `檔案`/`編輯` menus, so no action becomes harder to find. Toolbar
  hit-areas stay ≥44px.

Appearance is the only thing that changes: **the enable/disable state machine is untouched.**
`上一筆`/`下一筆` stay gated on having records; `確認寫入`/`強制寫入` keep their current
behavior (clickable except mid-continuous-capture, surfacing a clear error when the work file or
name is missing — the deliberate `#confirm-required-fields` decision). The redesign only gives
those states a clearer themed disabled look.

Icons ship as Fluent System Icons (line style, MIT) PNGs under `assets/icons/`, bundled the same
way as `assets/shutter.wav`. No emoji are used as icons.

## Scope

### In Scope
- New pure `src/ocr_from2xlsx/theme.py`: light/dark `Palette` tokens (colour, typography scale,
  spacing), `apply_theme()`, `ThemeManager` (mode + persistence + registered-widget recolour),
  and a cached `load_icon()` helper.
- App-wide restyle via those tokens: form (entries, labels, checkbuttons, LabelFrames, scrollbar),
  footer status/badge/progress, continuous-capture banner, and the two-pane body — all inherit
  the new tokens and gain dark-mode variants. **No re-layout.**
- Light/dark toggle: `檢視` menu checkbutton + toolbar toggle, persisted in `config.json`
  (default light), with the config write made read-modify-write so it coexists with
  `preview_rotation`.
- Branded toolbar band with icon-only secondary buttons + tooltips and a single accent primary
  button relabelled `確認寫入`; the `編輯` menu item label follows suit.
- Icon assets under `assets/icons/` plus packaging updates (`.spec` datas, `pyproject`
  package-data).
- Tests: Tk-free unit tests for `theme.py` (token contrast, style registration, mode toggle +
  persistence); real-Tk tests (skip with no display) for the themed toolbar band, icon-only
  buttons + tooltips, primary-CTA style, and disabled visual states.

### Out of Scope
- Any window-layout restructure — the two-pane `PanedWindow`, form field order/grouping, footer
  arrangement, and menu structure stay as-is (the "整體版面重排" option was explicitly declined).
- Any change to the enable/disable **rules** for toolbar actions (only their visual treatment
  changes).
- Recognition, validation, capture, the workbook write path, `service_record.v1`, and keyboard
  shortcuts — all unchanged.
- Theming the native OS menu bar (Windows draws it; it cannot be recoloured — see Risks).
- New icon-font or third-party theme libraries (`ttkbootstrap`/`sv-ttk`) — declined to keep the
  PyInstaller build dependency-free.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| `src/ocr_from2xlsx/theme.py` | Yes (new) | Pure `Palette` (LIGHT/DARK) + type/spacing constants; `apply_theme(root, style, palette)`; `ThemeManager` (mode, toggle, persistence, registered non-ttk widget recolour); cached `load_icon(name, size)`. No cv2/workbook imports. |
| `src/ocr_from2xlsx/app.py::ReviewApp` | Yes | Build a `ThemeManager`; call `apply_theme` on init; replace the toolbar row with a branded band of icon-only secondary buttons (`tk.Button`, tooltip via existing `_Tooltip`) + an accent `確認寫入` primary; register the `Canvas`/banner/`tk.Label` badges for recolour; add the `檢視` dark-mode checkbutton + toolbar toggle. Relabel the `編輯` `確認並寫入` menu item to `確認寫入`. |
| `config.json` persistence (`_config_path` / `_save_preview_rotation`) | Yes | Refactor to read-modify-write helpers (`_load_config` / `_update_config`) so `theme_mode` and `preview_rotation` coexist instead of overwriting one another. |
| `src/ocr_from2xlsx/assets/icons/*.png` | Yes (new) | Fluent System Icons (line, MIT) for open-report, import-folder, prev, next, confirm, and the dark-mode toggle, at the sizes the toolbar renders. |
| `build/ocr-from2xlsx.spec`, `pyproject.toml` | Yes | Add the icons dir to PyInstaller `datas` and to `tool.setuptools.package-data`. |
| Recognition / validation / capture / `workbook.py` / `service_record.v1` / shortcuts | No | Reused unchanged. |
| `openspec/specs/record-confirmation` scenarios referencing 「確認並寫入」 | Doc-only | Refer to the same action, now labelled `確認寫入`; synced on archive. |

## Architecture Considerations

Follows the repo's "pure, testable core + thin Tk wrapper" pattern. `theme.py` operates on plain
data (palettes, style names, a mode string) and a `ttk.Style`, so token contrast, style
registration, and mode toggling are unit-testable with no display — mirroring `review_nav.py` and
`_wheel_scroll_units`. `app.py` gains only thin wiring: it builds the `ThemeManager`, constructs
the toolbar band, and registers the few `tk` (non-ttk) widgets it already owns for recolour on
mode switch. Toolbar buttons are `tk.Button` (which honour `bg`/`fg`/`activebackground` reliably
on the coloured band) while all form widgets are ttk styled from the tokens — a clean split
between the branded band and the themed body. Because `app.py` is already large (~2.7k lines), the
appearance logic lands in `theme.py` rather than bloating it further.

## Success Criteria

- [ ] The whole app renders from one token source in both light and dark mode; switching mode via
  the `檢視` checkbutton or the toolbar toggle re-themes every surface (form, footer, banner,
  badges, body) and the choice survives a restart (persisted in `config.json` alongside
  `preview_rotation`).
- [ ] The toolbar shows one obviously-primary accent `確認寫入` button (with check icon + `⏎`
  hint) and icon-only secondary buttons whose tooltips name the action and its shortcut; the
  full-text equivalents remain in the menus; hit-areas are ≥44px; no emoji are used as icons.
- [ ] `上一筆`/`下一筆` show the themed disabled style when there are no records, and
  `確認寫入`/`強制寫入` keep their exact current enable/disable behavior (only the disabled
  visual changes).
- [ ] `theme.py` has Tk-free unit tests (text-token contrast ≥ 4.5:1, expected named styles
  registered, mode toggle flips palette and persists) and the toolbar/CTA/disabled-visual surface
  has real-Tk tests that skip cleanly with no display.
- [ ] `python -W error -m pytest -q` and `python -m policy_check --repo .` green; the exe rebuilds
  and `build/verify_roundtrip.py` passes with icons/theme loading from the bundle; CHANGELOG
  `[Unreleased]` and the `app-appearance` spec synced on archive.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Native Windows menu bar can't be recoloured/darkened, so it stays light in dark mode | High | Low | Accept and document; brand/dark styling lives in the toolbar band below it; the menu bar is a thin, familiar OS strip. |
| `clam` restyle regresses a widget's readability (e.g. selected combobox, scrollbar) in light or dark | Med | Med | Token contrast asserted in unit tests; both themes exercised in real-Tk tests and a manual light+dark pass before merge. |
| `tk.Button` on the coloured band renders inconsistently across DPI / high-contrast OS settings | Med | Med | Fixed hit-area + explicit `bg`/`fg`/`active*`/`disabledforeground`; verify at 100%/200% DPI; keep menu text fallback. |
| Icon PNGs fail to resolve from the PyInstaller bundle (like a mis-bundled asset) | Med | High | Resolve via the proven `Path(__file__)/assets` pattern; add to `.spec` datas; assert load in a packaged-exe smoke via `verify_roundtrip`; fall back to text label if an icon is missing. |
| Config write refactor drops the existing `preview_rotation` on upgrade | Low | Med | Read-modify-write merge with an explicit test that saving `theme_mode` preserves `preview_rotation` and vice-versa. |
| Relabel `確認並寫入`→`確認寫入` desyncs docs/specs/tests referencing the old string | Med | Low | Grep and update the label references (menu, README, spec scenarios) in the same change; behavior is identical. |

---

## Archive Information

**Archived:** 2026-07-01
**Outcome:** Successfully implemented

### Files Modified
- `src/ocr_from2xlsx/theme.py` (new — `Palette` LIGHT/DARK, `contrast_ratio`, `apply_theme`, `ThemeManager`, `load_icon`)
- `src/ocr_from2xlsx/app.py` (config read-modify-write; branded toolbar band + icon-only buttons + `確認寫入` primary; `ThemeManager` wiring + `_toggle_theme` + `檢視` toggle; theme-aware banner/badge; `Section.TLabelframe` on form groups; `確認並寫入`→`確認寫入` strings)
- `src/ocr_from2xlsx/assets/icons/*.png` (new — generated line glyphs) + `build/make_icons.py` (new generator)
- `build/ocr-from2xlsx.spec`, `pyproject.toml`, `.gitignore` (bundle + track icons)
- `tests/test_theme.py`, `tests/test_app_theme.py`, `tests/test_app_config.py` (new); `tests/test_app_navigation.py` (icon-only toolbar + relabel)
- `CHANGELOG.md`, `README.md`, `docs/superpowers/plans/2026-07-01-restyle-review-ui.md` (new)

### Specs Updated
- `openspec/specs/app-appearance/spec.md` — created (new capability): single themed token source; persisted light/dark mode; branded toolbar with a single primary action; icon-only secondary actions with discoverable labels; visual disabled state without changing enablement rules.
- `openspec/specs/record-confirmation/spec.md` — confirm-shortcut scenario relabelled `確認並寫入`→`確認寫入`.

### Verification
- `python -W error -m pytest -q`: 751 passed, 2 skipped (pre-existing). `build/verify_roundtrip.py`: PASS (real template, 14 images preserved). Exe rebuilt via `build/package.py` (exit 0, icons bundled, `--help` marker in sync).
- Subagent code review ("Needs changes") — all Important findings fixed (interpreter-safe icon cache; unwired styles wired/removed; icon generator tracked; banner/badge dark tokens) and re-verified by tests. Interactive operator GUI session at 100%/200% DPI deferred (behavior covered by real-Tk automated tests).
