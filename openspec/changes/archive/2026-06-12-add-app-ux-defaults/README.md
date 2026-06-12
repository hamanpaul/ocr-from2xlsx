# Proposal: Default-to-app UX and webcam autodetect

**Change ID:** `add-app-ux-defaults`
**Created:** 2026-06-12
**Status:** Archived

---

## Problem Statement

Make the tool usable for non-technical end users: launching `ocr-from2xlsx` with no arguments opens
the desktop app directly (GitHub #18), the packaged exe is windowed (no console window), and the app
auto-detects a webcam on startup — connecting the single camera, or prompting a choice when several
are present (GitHub #19) — with opencv bundled into the exe so it works for shipped users and
gracefully degrades to the existing JSON flow when opencv is absent.

## Archived Outcome

This change was implemented as:

- bare `ocr-from2xlsx` now defaults to the desktop app, with regression tests proving `--version`
  and explicit subcommands still behave as before;
- the PyInstaller spec is now windowed and bundles `cv2`, with spec regression coverage and packaging
  docs requiring `python -m pip install -e ".[dev,camera]"` before building;
- pure `capture.enumerate_cameras()` / `capture.decide_camera_selection()` helpers support
  injectable probing and drive the app's startup decision logic;
- `ReviewApp` now auto-detects cameras on startup, prompts when multiple cameras are present, offers
  a `選擇攝影機` toolbar action, runs a live preview loop, and falls back with bounded retry/status
  reporting when camera startup or preview fails;
- README, CHANGELOG, and the base OpenSpec spec now document the new default-to-app and webcam
  autodetect behavior.

Verification completed with `python -W error -m pytest -q` (**433 passed, 2 skipped**),
`python -m policy_check --repo .` (**16 pass, 0 fail, 0 warn**), a rebuilt
`dist/ocr-from2xlsx.exe`, and a packaged-app launch smoke test that started and cleaned up the
resulting process(es). Hardware-specific single/multi-camera behavior remains recorded in the PR as
the follow-up manual Windows verification item.

The accepted behavior is captured in `openspec/specs/record-preparation/spec.md`.

## Scope / Impact

- Affects end-user launch UX for the Windows desktop app and packaged executable.
- Preserves explicit CLI workflows via explicit subcommands (`python -m ocr_from2xlsx <subcommand>`).
- Introduces optional webcam preview behavior without changing the normalized JSON/workbook contracts.

## Success Criteria

- [x] Bare `ocr-from2xlsx` launches the app while `--version` and explicit subcommands remain intact.
- [x] The packaged exe is windowed and bundles OpenCV.
- [x] The app auto-detects cameras, prompts when multiple are present, and degrades gracefully when
  unavailable.
- [x] Docs, CHANGELOG, and base OpenSpec specs are updated; tests, policy, packaging, and launch
  smoke verification are green.

Design: `docs/superpowers/specs/2026-06-12-app-ux-defaults-design.md`.
Plan: `docs/superpowers/plans/2026-06-12-app-ux-defaults.md`.
