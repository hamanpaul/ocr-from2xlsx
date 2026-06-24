# Implementation Tasks: App UX defaults (default-to-app + webcam autodetect)

**Change ID:** `add-app-ux-defaults`

All implementation uses TDD with focused tests before production code.

## Phase 1: Default-to-app CLI + windowed exe (#18)

- [x] Add fail-first test: `cli.main([])` invokes the app (monkeypatched `run_app`) and returns 0;
  `main(["--version"])` and an explicit subcommand still behave unchanged.
- [x] Implement: `parser.set_defaults(command="app")` in `cli.build_parser()`; verify `--version`
  short-circuits first and explicit subcommands still override `command`.
- [x] Add fail-first test asserting `build/ocr-from2xlsx.spec` has `console=False`; set it.

## Phase 2: Camera enumeration + selection logic (#19, pure)

- [x] Add fail-first tests for `enumerate_cameras(max_probe, opener)` with an injected fake opener
  (subset of indices openable; cv2-absent default opener returns `[]`) and for
  `decide_camera_selection(indices)` covering none / auto / choose branches.
- [x] Implement both in `src/ocr_from2xlsx/capture.py` (default opener cv2-guarded).

## Phase 3: App webcam integration (glue, cv2-guarded)

- [x] Wire `_init_camera()` into app startup: enumerate -> decide -> placeholder / auto-start /
  selection dialog; `_start_camera(index)` runs an `after()` frame loop rendering
  `cv2.imencode('.ppm')` bytes into the left preview; release/cancel on close; add a
  "選擇攝影機" toolbar button. All behind `import cv2` guards with graceful degradation.

## Phase 4: Package opencv into the exe (#19)

- [x] Add `"cv2"` to `build/ocr-from2xlsx.spec` `hiddenimports` (plus `collect_dynamic_libs('cv2')`
  if needed); update the Phase 1 spec test to also assert the `cv2` hiddenimport.
- [x] Document the build prerequisite (`pip install -e ".[dev,camera]"` before `build/package.py`).

## Phase 5: Docs, policy, and verification

- [x] README: bare-exe-opens-app behavior, windowed note (CLI via `python -m ocr_from2xlsx <subcommand>`), webcam
  autodetect/selection, packaging needs `[camera]`. CHANGELOG `[Unreleased]`. Base OpenSpec specs.
- [x] `python -W error -m pytest -q`, `python -m policy_check --repo .`, and
  `pip install -e ".[dev,camera]"` + `python build/package.py` all green; packaged exe launch
  smoke-tested in this environment, with remaining hardware-specific single/multi/no-camera notes
  recorded in the PR.

## Completion Checklist

- [x] All phases complete and quality gates green
- [x] Ready for `/openspec-archive add-app-ux-defaults`
