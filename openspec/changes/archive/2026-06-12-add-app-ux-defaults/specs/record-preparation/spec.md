# record-preparation Specification (Delta)

## ADDED

### Requirement: Bare invocation launches the desktop app

The CLI SHALL launch the desktop review app when invoked with no subcommand, while preserving
`--version`, `--help`, and all explicit subcommands, and the packaged executable SHALL be windowed
(no console window) so non-technical users can open it by double-clicking.

#### Scenario: No-argument invocation opens the app
- **WHEN** `ocr-from2xlsx` is invoked with no subcommand and no `--version`
- **THEN** the desktop review app is launched

#### Scenario: Version and explicit subcommands are unaffected
- **WHEN** `--version` or an explicit subcommand (e.g. `import-json`) is invoked
- **THEN** the prior behavior is preserved and the app is not launched

### Requirement: App auto-detects a webcam on startup with graceful degradation

The app SHALL detect available cameras at startup, automatically connecting and previewing when
exactly one is present, prompting the user to choose when several are present, and keeping the
existing JSON-driven flow when none are present or when opencv is unavailable.

#### Scenario: Single camera connects automatically
- **WHEN** exactly one camera is detected at startup
- **THEN** the app connects to it and shows a live preview

#### Scenario: Multiple cameras prompt a choice
- **WHEN** more than one camera is detected
- **THEN** the app prompts the user to select which camera to connect

#### Scenario: No camera or opencv preserves the existing flow
- **WHEN** no camera is detected or opencv is unavailable
- **THEN** the app keeps the existing preview placeholder and JSON import flow without error
