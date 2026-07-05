# app-appearance Specification (Delta)

**Change ID:** `restyle-review-ui`
**Affects:** the review window's visual appearance (`ReviewApp` in `app.py`) and its new theming
core (`theme.py`); no change to recognition, write, navigation, or action-enablement behavior.

## ADDED

### Requirement: Render the app from a single themed token source

The system SHALL derive the review window's colours, typography, and spacing from a single set of
design tokens and apply them across every surface (toolbar, form fields and labels, group frames,
scrollbar, footer status/badge/progress, continuous-capture banner, and the source-image pane),
so the interface is visually consistent and centrally adjustable rather than relying on the
platform default ttk theme.

#### Scenario: Every surface uses the token theme
- **WHEN** the review window is shown
- **THEN** its widgets are styled from the token theme (not the stock platform ttk defaults), using
  the token colours, type scale, and spacing consistently across the toolbar, form, footer, banner,
  and image pane

#### Scenario: Token text pairs are legible
- **WHEN** any themed text is rendered on its themed background
- **THEN** the foreground/background token pair meets a WCAG contrast ratio of at least 4.5:1 for
  body text

### Requirement: Offer a persisted light and dark appearance mode

The system SHALL provide a light and a dark appearance mode, selectable by the reviewer, defaulting
to light on first run and remembering the last choice across restarts. The dark mode SHALL use
tonal dark variants (not a naive colour inversion) that preserve the required text contrast.

#### Scenario: Reviewer switches to dark mode
- **WHEN** the reviewer selects dark mode from the `檢視` menu or the toolbar toggle
- **THEN** every themed surface re-renders in the dark palette with contrast preserved, without
  restarting the app

#### Scenario: Mode choice persists across restarts
- **WHEN** the reviewer has selected a mode and later relaunches the app
- **THEN** the app opens in the last-selected mode, and this preference coexists with the existing
  saved preview-rotation preference (neither overwrites the other)

#### Scenario: Default mode on first run
- **WHEN** the app runs with no saved appearance preference
- **THEN** it opens in light mode

### Requirement: Present a branded toolbar with a single primary action

The system SHALL present the toolbar as a colour-branded band below the native menu bar in which
the record-write action is the single visually dominant primary control — an accent-coloured block
button labelled `確認寫入` with a confirm icon and a shortcut hint — while the other toolbar
actions are visually subordinate.

#### Scenario: Primary action is visually dominant
- **WHEN** the toolbar is shown
- **THEN** the `確認寫入` button is rendered in the accent style as the one prominent primary
  control, and the secondary actions are visually subordinate to it

#### Scenario: Primary action keeps its behavior
- **WHEN** the reviewer activates `確認寫入`
- **THEN** it performs the same confirm-and-write action as before the relabel (formerly
  `確認並寫入`), including the existing blocked-write guards

### Requirement: Use icon-only secondary actions with discoverable labels

The system SHALL render the secondary toolbar actions (`開啟報表`, `匯入`, `上一筆`, `下一筆`) as
icon-only buttons that each show a hover tooltip naming the action and its keyboard shortcut where
one exists, keep a touch/click hit-area of at least 44px, and retain a full-text equivalent in the
menus so no action becomes less discoverable. Icons SHALL be vector-derived assets, not emoji.

#### Scenario: Tooltip names an icon-only action
- **WHEN** the reviewer hovers an icon-only toolbar button
- **THEN** a tooltip appears naming the action, and its keyboard shortcut when the action has one

#### Scenario: Full-text equivalent remains in the menus
- **WHEN** an action is shown icon-only in the toolbar
- **THEN** the same action is still available as a full-text item in the `檔案`/`編輯` menus

#### Scenario: Icons are not emoji
- **WHEN** toolbar icons are rendered
- **THEN** they are drawn from bundled vector-derived icon assets, not emoji glyphs

### Requirement: Reflect action availability visually without changing when actions are enabled

The system SHALL give toolbar controls a clear themed disabled appearance when their action is
unavailable, using the existing enablement rules unchanged: `上一筆`/`下一筆` are available only
when records exist, and `確認寫入`/`強制寫入` follow the current capture-state machine (available
except during a live continuous-capture session, surfacing an explanatory error when the work file
or name is missing). The redesign changes only the visual treatment of these states, not when a
control is enabled.

#### Scenario: Navigation disabled without records
- **WHEN** no records are loaded
- **THEN** `上一筆` and `下一筆` render in the themed disabled style and cannot be activated

#### Scenario: Confirm keeps its existing availability
- **WHEN** a record is under review and no continuous-capture session is live
- **THEN** `確認寫入` is enabled, and pressing it with a missing work file or name still surfaces
  the existing explanatory error rather than being silently disabled
