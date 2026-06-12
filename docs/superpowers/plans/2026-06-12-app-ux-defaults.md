# App UX Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bare `ocr-from2xlsx` opens the desktop app, the exe is windowed, and the app auto-detects/selects a webcam on startup with opencv bundled into the exe — degrading gracefully when opencv is absent.

**Architecture:** Two small, independent changes. (#18) `cli.build_parser()` defaults the subcommand to `app`, and the PyInstaller spec switches to windowed. (#19) Pure, injectable camera enumeration + selection helpers live in `capture.py` (TDD'd); the Tk app wires them into a cv2-guarded live-preview loop (thin glue, manually verified, consistent with the rest of `app.py`); the PyInstaller spec bundles `cv2`.

**Tech Stack:** Python 3.12, argparse CLI (`src/ocr_from2xlsx/cli.py`), Tkinter app (`src/ocr_from2xlsx/app.py`), opencv-python (optional `[camera]` extra, bundled into the exe), PyInstaller spec (`build/ocr-from2xlsx.spec`).

**Branch:** `wt/bootstrap-ocr-design/app-ux-defaults`. Spec: `docs/superpowers/specs/2026-06-12-app-ux-defaults-design.md`. OpenSpec: `openspec/changes/add-app-ux-defaults/`. Issues: #18, #19.

**Conventions:**
- Pure tests: `.venv\Scripts\python -m pytest <file> -q -p no:cacheprovider --basetemp=output/pytest-tmp`.
- TDD: failing test → see it fail → implement → see it pass → commit.
- Commits end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- cv2/Tk glue in `app.py` is not unit-tested in CI (no display, opencv optional); the *pure* logic it calls IS tested. This matches the existing `app.py` pattern (logic lives in tested pure helpers; the Tk shell is thin).

---

### Task 1: Default the CLI to the app subcommand (#18)

**Files:**
- Modify: `src/ocr_from2xlsx/cli.py:136` (after `subparsers.add_parser("app", ...)`)
- Test: `tests/test_cli_default_app.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import pytest

from ocr_from2xlsx import cli


def test_bare_invocation_launches_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("ocr_from2xlsx.app.run_app", lambda: calls.append("app") or 0)

    exit_code = cli.main([])

    assert exit_code == 0
    assert calls == ["app"]


def test_version_still_short_circuits(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr("ocr_from2xlsx.app.run_app", lambda: (_ for _ in ()).throw(AssertionError("app launched")))

    exit_code = cli.main(["--version"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip()  # printed a version, did not launch app


def test_explicit_subcommand_does_not_launch_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr("ocr_from2xlsx.app.run_app", lambda: (_ for _ in ()).throw(AssertionError("app launched")))
    output = tmp_path / "sample.json"

    exit_code = cli.main(["sample-json", "--output", str(output)])

    assert exit_code == 0
    assert output.is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_cli_default_app.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `test_bare_invocation_launches_app` FAILS (bare invocation currently does not call `run_app`).

- [ ] **Step 3: Implement the default**

In `src/ocr_from2xlsx/cli.py`, immediately after the line
`subparsers.add_parser("app", help="Launch the native desktop review UI.")` and before `return parser`:

```python
    parser.set_defaults(command="app")
    return parser
```

(`main()` already checks `args.version` first and has an `if args.command == "app":` branch that calls
`from ocr_from2xlsx.app import run_app; return run_app()`, so no change to `main()` is required.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_cli_default_app.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/cli.py tests/test_cli_default_app.py
git commit -m "feat: launch app by default on bare invocation (#18)"
```

---

### Task 2: Windowed exe + cv2 bundling in the PyInstaller spec (#18, #19)

**Files:**
- Modify: `build/ocr-from2xlsx.spec` (hiddenimports + console flag)
- Test: `tests/test_build_spec.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path


def test_spec_is_windowed_and_bundles_cv2() -> None:
    spec_text = (Path(__file__).resolve().parents[1] / "build" / "ocr-from2xlsx.spec").read_text(
        encoding="utf-8"
    )

    assert "console=False" in spec_text
    assert "console=True" not in spec_text
    assert "cv2" in spec_text  # opencv bundled so the shipped exe can use the webcam
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_build_spec.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL (`console=True` present, no `cv2`).

- [ ] **Step 3: Edit `build/ocr-from2xlsx.spec`**

Add the opencv collection near the top (after `PROJECT_ROOT = Path.cwd()`):

```python
from PyInstaller.utils.hooks import collect_dynamic_libs

cv2_binaries = collect_dynamic_libs("cv2")
```

Change the `Analysis(...)` call so `hiddenimports` includes cv2 and `binaries` includes the collected libs:

```python
    binaries=cv2_binaries,
    ...
    hiddenimports=["tkinter", "cv2"],
```

Change the `EXE(...)` flag:

```python
    console=False,
```

Note: if `collect_dynamic_libs("cv2")` raises in an env without opencv, the build env must install it
first (Task 4 documents `pip install -e ".[dev,camera]"`); the spec is only exercised by `package.py`,
not by the pure test above (which just reads the text).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_build_spec.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add build/ocr-from2xlsx.spec tests/test_build_spec.py
git commit -m "build: windowed exe and bundle opencv (#18, #19)"
```

---

### Task 3: Camera enumeration + selection logic (#19, pure)

**Files:**
- Modify: `src/ocr_from2xlsx/capture.py` (append helpers)
- Test: `tests/test_camera_enumeration.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from ocr_from2xlsx.capture import decide_camera_selection, enumerate_cameras


def test_enumerate_cameras_uses_injected_opener() -> None:
    openable = {0, 2}

    found = enumerate_cameras(max_probe=4, opener=lambda index: index in openable)

    assert found == [0, 2]


def test_enumerate_cameras_default_opener_without_cv2_returns_empty(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def no_cv2(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_cv2)

    assert enumerate_cameras(max_probe=3) == []


def test_decide_camera_selection_branches() -> None:
    assert decide_camera_selection([]) == ("none",)
    assert decide_camera_selection([1]) == ("auto", 1)
    assert decide_camera_selection([0, 1, 3]) == ("choose", (0, 1, 3))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_camera_enumeration.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ImportError: cannot import name 'enumerate_cameras'`.

- [ ] **Step 3: Append to `src/ocr_from2xlsx/capture.py`**

```python
from typing import Callable


def _default_camera_opener(index: int) -> bool:
    try:
        import cv2
    except ImportError:
        return False
    capture = cv2.VideoCapture(index)
    try:
        return bool(capture.isOpened())
    finally:
        capture.release()


def enumerate_cameras(
    max_probe: int = 5,
    opener: Callable[[int], bool] | None = None,
) -> list[int]:
    """Probe indices 0..max_probe-1 and return those that open. opener is injectable for tests."""
    probe = opener if opener is not None else _default_camera_opener
    return [index for index in range(max_probe) if probe(index)]


def decide_camera_selection(indices: list[int]) -> tuple:
    """Pure decision: () -> none, single -> auto, multiple -> choose."""
    if not indices:
        return ("none",)
    if len(indices) == 1:
        return ("auto", indices[0])
    return ("choose", tuple(indices))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_camera_enumeration.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/ocr_from2xlsx/capture.py tests/test_camera_enumeration.py
git commit -m "feat: camera enumeration and selection logic (#19)"
```

---

### Task 4: Wire the webcam into the app (#19, cv2-guarded glue)

**Files:**
- Modify: `src/ocr_from2xlsx/app.py` (toolbar button, `_init_camera`, `_start_camera`, `_stop_camera`, `_ask_camera`, `_on_close`)

No new CI test (Tk + cv2, no display); manual verification covers it. The pure logic it depends on is
tested in Task 3.

- [ ] **Step 1: Add a camera attribute set in `__init__`**

After `self._preview_image: tk.PhotoImage | None = None` (around `app.py:148`), add:

```python
        self._camera_capture = None  # cv2.VideoCapture when active
        self._camera_after_id: str | None = None
```

- [ ] **Step 2: Add the toolbar button**

In `_build_ui`, after the "強制寫入" button (around `app.py:167`), add:

```python
        ttk.Button(toolbar, text="選擇攝影機", command=self._choose_camera).pack(
            side=tk.LEFT, padx=4
        )
```

- [ ] **Step 3: Call `_init_camera()` at the end of `_build_ui`**

As the last line of `_build_ui` (after the `status_list` setup, around `app.py:215`):

```python
        self._init_camera()
```

- [ ] **Step 4: Implement the camera methods**

Add these methods to `ReviewApp` (near `_show_placeholder_preview`, around `app.py:384`):

```python
    def _init_camera(self) -> None:
        from ocr_from2xlsx.capture import decide_camera_selection, enumerate_cameras

        try:
            decision = decide_camera_selection(enumerate_cameras())
        except Exception:  # noqa: BLE001 - camera probing must never block startup
            self._show_placeholder_preview()
            return
        kind = decision[0]
        if kind == "auto":
            self._start_camera(decision[1])
        elif kind == "choose":
            index = self._ask_camera(list(decision[1]))
            if index is not None:
                self._start_camera(index)
            else:
                self._show_placeholder_preview()
        else:
            self._show_placeholder_preview()

    def _choose_camera(self) -> None:
        from ocr_from2xlsx.capture import enumerate_cameras

        indices = []
        try:
            indices = enumerate_cameras()
        except Exception:  # noqa: BLE001
            indices = []
        if not indices:
            self._push_status("找不到攝影機")
            return
        index = self._ask_camera(indices) if len(indices) > 1 else indices[0]
        if index is not None:
            self._start_camera(index)

    def _ask_camera(self, indices: list[int]) -> int | None:
        dialog = tk.Toplevel(self)
        dialog.title("選擇攝影機")
        dialog.transient(self)
        ttk.Label(dialog, text="偵測到多支攝影機，請選擇：").pack(padx=12, pady=(12, 4))
        listbox = tk.Listbox(dialog, height=min(6, len(indices)))
        for index in indices:
            listbox.insert(tk.END, f"攝影機 {index}")
        listbox.selection_set(0)
        listbox.pack(padx=12, pady=4, fill=tk.BOTH, expand=True)
        chosen: dict[str, int | None] = {"value": None}

        def _confirm() -> None:
            selection = listbox.curselection()
            chosen["value"] = indices[selection[0]] if selection else None
            dialog.destroy()

        ttk.Button(dialog, text="連接", command=_confirm).pack(padx=12, pady=(4, 12))
        dialog.grab_set()
        self.wait_window(dialog)
        return chosen["value"]

    def _start_camera(self, index: int) -> None:
        self._stop_camera()
        try:
            import cv2

            capture = cv2.VideoCapture(index)
            if not capture.isOpened():
                capture.release()
                self._push_status(f"無法開啟攝影機 {index}")
                self._show_placeholder_preview()
                return
            self._camera_capture = capture
            self._push_status(f"已連接攝影機 {index}")
            self._poll_camera_frame()
        except Exception:  # noqa: BLE001
            self._push_status("攝影機啟動失敗")
            self._show_placeholder_preview()

    def _poll_camera_frame(self) -> None:
        capture = self._camera_capture
        if capture is None:
            return
        try:
            import cv2

            ok, frame = capture.read()
            if ok:
                ok_encode, buffer = cv2.imencode(".ppm", frame)
                if ok_encode:
                    image = tk.PhotoImage(data=bytes(buffer))
                    self._preview_image = image
                    self.preview.configure(state="normal")
                    self.preview.delete("1.0", tk.END)
                    self.preview.image_create("1.0", image=image)
                    self.preview.configure(state="disabled")
        except Exception:  # noqa: BLE001
            self._stop_camera()
            self._show_placeholder_preview()
            return
        self._camera_after_id = self.after(33, self._poll_camera_frame)

    def _stop_camera(self) -> None:
        if self._camera_after_id is not None:
            try:
                self.after_cancel(self._camera_after_id)
            except Exception:  # noqa: BLE001
                pass
            self._camera_after_id = None
        if self._camera_capture is not None:
            try:
                self._camera_capture.release()
            except Exception:  # noqa: BLE001
                pass
            self._camera_capture = None
```

- [ ] **Step 5: Release the camera on close**

In `_on_close` (around `app.py:430`), add `self._stop_camera()` as the first line:

```python
    def _on_close(self) -> None:
        self._stop_camera()
        if self.session:
            self.session.close()
        self.destroy()
```

- [ ] **Step 6: Verify nothing regressed in the suite**

Run: `.venv\Scripts\python -m pytest -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: all pass (app.py glue is import-safe; no test opens a window).

- [ ] **Step 7: Commit**

```bash
git add src/ocr_from2xlsx/app.py
git commit -m "feat: webcam autodetect, selection, and live preview in app (#19)"
```

---

### Task 5: Docs, CHANGELOG, OpenSpec base specs

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `openspec/specs/record-preparation/spec.md`

- [ ] **Step 1: README**

Update the Usage / app section to state that running `ocr-from2xlsx` (or double-clicking the exe)
opens the app directly, that the exe is windowed so CLI users should use `python -m ocr_from2xlsx`
for stdout, and that the app auto-detects a webcam (prompting when several are present). In Packaging,
note `pip install -e ".[dev,camera]"` is required before `python build/package.py` so opencv is
bundled. If the `<!-- BEGIN: cli-help -->` block changed, regenerate it (it should NOT change here).

- [ ] **Step 2: CHANGELOG `[Unreleased]`**

Add under `### Added`:

```markdown
- 一般使用者體驗：裸跑 `ocr-from2xlsx`（或雙擊 exe）直接開啟桌面 app（#18），exe 改為 windowed
  （無 console 視窗；CLI 需 stdout 時改用 `python -m ocr_from2xlsx`）。
- app 啟動自動偵測攝影機：單支自動連接並即時預覽，多支彈出選擇對話框，無攝影機或未安裝 opencv 時
  優雅降級維持既有 JSON 流程；新增「選擇攝影機」按鈕（#19）。opencv 一併打包進 exe。
```

- [ ] **Step 3: Merge delta into base spec**

Append the two `### Requirement:` blocks from
`openspec/changes/add-app-ux-defaults/specs/record-preparation/spec.md` to
`openspec/specs/record-preparation/spec.md`.

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md openspec/specs/record-preparation/spec.md
git commit -m "docs: document default-to-app and webcam autodetect (#18, #19)"
```

---

### Task 6: Verification battery + archive + PR

- [ ] **Step 1: Pure suite + policy**

```powershell
.venv\Scripts\python -W error -m pytest -q -p no:cacheprovider --basetemp=output/pytest-tmp
.venv\Scripts\python -m policy_check --repo .
```
Expected: all pass, policy 0 failures.

- [ ] **Step 2: Packaged build with opencv**

```powershell
.venv\Scripts\python -m pip install -e ".[dev,camera]"
.venv\Scripts\python build/package.py
```
Expected: `dist/ocr-from2xlsx.exe` builds. Manually verify: double-click opens the app (no console
window); with a webcam connected it previews; with multiple it prompts; with none it falls back to
the placeholder. Record the manual result in the PR body.

- [ ] **Step 3: Archive the OpenSpec change**

Mark all `tasks.md` boxes `[x]`, then move `openspec/changes/add-app-ux-defaults/` to
`openspec/changes/archive/2026-06-12-add-app-ux-defaults/` (rename `proposal.md` narrative to
`README.md` and add a short archived `proposal.md`, matching the existing archive convention), and
confirm the delta was merged into the base spec in Task 5.

- [ ] **Step 4: Commit, push, PR**

```bash
git add -A
git commit -m "docs(openspec): archive add-app-ux-defaults"
git push -u origin wt/bootstrap-ocr-design/app-ux-defaults
gh pr create --base feature/bootstrap-ocr-design --title "feat: default-to-app and webcam autodetect (#18, #19)" --body "<fill PR template: summary, closes #18 and #19, test plan incl. manual exe verification, policy checklist all checked>"
```

---

## Self-Review Notes

- Spec coverage: #18 default-to-app (Task 1) + windowed exe (Task 2); #19 enumerate/select pure logic
  (Task 3), app glue (Task 4), opencv bundling (Task 2 + Task 4 docs); docs/policy (Tasks 5-6). All
  design "成功準則" map to tasks.
- Testability: the only CI-tested code is pure (`cli.main` with monkeypatched `run_app`,
  `enumerate_cameras`/`decide_camera_selection`, spec text). Tk + cv2 live paths are manually verified,
  consistent with the existing untested `app.py` Tk shell.
- Type consistency: `decide_camera_selection` returns `("none",)` / `("auto", index)` /
  `("choose", tuple)`; `_init_camera` matches on `decision[0]` and indexes `decision[1]` accordingly.
  `enumerate_cameras(max_probe, opener)` signature is identical in test, impl, and app call site.
- Known build risk: `collect_dynamic_libs("cv2")` requires opencv installed in the build env; Task 6
  installs `[camera]` before packaging. If cv2 fails to load in the frozen exe, fall back to
  `collect_all("cv2")` in the spec (noted in the design risk table).
