# add-app-ux-defaults

Make the tool usable for non-technical end users: launching `ocr-from2xlsx` with no arguments opens
the desktop app directly (GitHub #18), the packaged exe is windowed (no console window), and the app
auto-detects a webcam on startup — connecting the single camera, or prompting a choice when several
are present (GitHub #19) — with opencv bundled into the exe so it works for shipped users and
gracefully degrading to the existing JSON flow when opencv is absent.

Design: `docs/superpowers/specs/2026-06-12-app-ux-defaults-design.md`.
