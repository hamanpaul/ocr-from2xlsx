# OCR Plugin Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the main app obtain OCR results from an external, portable OCR plugin via a stable subprocess + JSON contract, while keeping the existing `FixtureOcrBackend` as the default and degrading gracefully when no plugin is installed.

**Architecture:** Add a `PluginOcrBackend` that implements the existing `OcrBackend` Protocol (`extract(page) -> dict`). It locates a plugin directory (CLI arg → `OCR_PLUGIN_DIR` env → default `plugins/paddleocr` next to the executable), reads a `plugin.json` manifest describing the launch command, then for each prepared page sends a `ocr_plugin.v1` request on stdin and parses a response on stdout. The plugin returns a raw record dict identical in shape to the OCR fixture's `record`, so the downstream `normalizer → validation → session → workbook` pipeline is untouched. `prepare-records` gains `--ocr-backend {fixture,plugin}` and `--ocr-plugin-dir`.

**Tech Stack:** Python 3.12, stdlib `subprocess`/`json`, pytest. No new third-party dependency in this sub-project (PaddleOCR lives in the plugin, built in sub-project 2).

---

## Spec Reference

Keep aligned with `docs/superpowers/specs/2026-05-29-paddleocr-plugin-ocr-design.md`, section "子專案 1：OCR 外掛架構".

Key constraints:
- Do not change the `OcrBackend` Protocol, `prepare_records`, `preprocess`, `session`, or `workbook` behavior.
- `FixtureOcrBackend` and all existing tests stay green.
- No network, no open port. The plugin is a local subprocess.
- The contract `record` shape matches the existing OCR fixture `record` (see `tests/fixtures/pdf/for testing only.ocr.json`).

## File Structure

```text
src/ocr_from2xlsx/
  ocr_plugin.py        NEW. Contract constants, request/response (de)serialization, plugin-dir resolution, exceptions.
  plugin_backend.py    NEW. PluginOcrBackend implementing OcrBackend Protocol via subprocess.
  cli.py               MODIFY. prepare-records: --ocr-backend / --ocr-plugin-dir; make --ocr-fixture conditional.
tests/
  fixtures/plugin/
    echo_plugin.py     NEW. Fake plugin: reads request on stdin, writes fixed response on stdout.
    echo_plugin.json   NEW. Manifest pointing at echo_plugin.py.
    bad_exit_plugin.py NEW. Fake plugin that exits non-zero (error-path test).
  test_ocr_plugin.py   NEW. Unit tests for contract + resolution + exceptions.
  test_plugin_backend.py NEW. PluginOcrBackend tests using the fake plugins.
  test_cli.py          MODIFY. prepare-records --ocr-backend plugin happy/err paths.
README.md              MODIFY. Plugin usage section + refreshed CLI help block.
CHANGELOG.md           MODIFY. [Unreleased] entries.
```

Keep `ocr_plugin.py` (pure data/IO contract, no subprocess) separate from `plugin_backend.py` (process launching) so the contract can be unit-tested without spawning processes and reused by the plugin side later.

---

## Task 1: Plugin Contract Module

**Files:**
- Create: `src/ocr_from2xlsx/ocr_plugin.py`
- Create: `tests/test_ocr_plugin.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ocr_plugin.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx.ocr_plugin import (
    OCR_PLUGIN_CONTRACT_VERSION,
    PluginManifestError,
    PluginUnavailableError,
    build_request,
    load_manifest,
    parse_response,
    resolve_plugin_dir,
)


def test_build_request_has_contract_and_page() -> None:
    request = build_request(
        template_id="service_record.v1",
        image_path="/abs/page-0001.png",
        document_name="for testing only.pdf",
        page_number=1,
    )

    assert request == {
        "contract_version": OCR_PLUGIN_CONTRACT_VERSION,
        "template_id": "service_record.v1",
        "page": {
            "image_path": "/abs/page-0001.png",
            "document_name": "for testing only.pdf",
            "page_number": 1,
        },
    }


def test_parse_response_returns_record() -> None:
    payload = {
        "contract_version": OCR_PLUGIN_CONTRACT_VERSION,
        "record": {"name": "AI test", "service_date": "2026-05-26"},
    }

    record = parse_response(payload)

    assert record == {"name": "AI test", "service_date": "2026-05-26"}


def test_parse_response_rejects_wrong_contract_version() -> None:
    with pytest.raises(ValueError, match="contract_version"):
        parse_response({"contract_version": "nope", "record": {}})


def test_parse_response_requires_record_object() -> None:
    with pytest.raises(ValueError, match="record"):
        parse_response({"contract_version": OCR_PLUGIN_CONTRACT_VERSION, "record": "x"})


def test_resolve_plugin_dir_prefers_explicit_arg(tmp_path: Path, monkeypatch) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    monkeypatch.setenv("OCR_PLUGIN_DIR", str(env_dir))

    assert resolve_plugin_dir(explicit_dir=explicit) == explicit


def test_resolve_plugin_dir_uses_env_when_no_arg(tmp_path: Path, monkeypatch) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    monkeypatch.setenv("OCR_PLUGIN_DIR", str(env_dir))

    assert resolve_plugin_dir(explicit_dir=None) == env_dir


def test_resolve_plugin_dir_raises_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)
    missing = tmp_path / "nope"

    with pytest.raises(PluginUnavailableError):
        resolve_plugin_dir(explicit_dir=missing, default_dir=tmp_path / "also_missing")


def test_load_manifest_reads_command(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"contract_version":"ocr_plugin.v1","command":["python","main.py"]}',
        encoding="utf-8",
    )

    manifest = load_manifest(plugin_dir)

    assert manifest.command == ["python", "main.py"]


def test_load_manifest_rejects_missing_file(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()

    with pytest.raises(PluginManifestError, match="plugin.json"):
        load_manifest(plugin_dir)


def test_load_manifest_rejects_empty_command(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        '{"contract_version":"ocr_plugin.v1","command":[]}', encoding="utf-8"
    )

    with pytest.raises(PluginManifestError, match="command"):
        load_manifest(plugin_dir)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ocr_plugin.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_from2xlsx.ocr_plugin'`.

- [ ] **Step 3: Implement the contract module**

Create `src/ocr_from2xlsx/ocr_plugin.py`:

```python
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OCR_PLUGIN_CONTRACT_VERSION = "ocr_plugin.v1"
DEFAULT_PLUGIN_SUBDIR = Path("plugins") / "paddleocr"
MANIFEST_NAME = "plugin.json"


class PluginUnavailableError(RuntimeError):
    """Raised when no OCR plugin directory can be located."""


class PluginManifestError(RuntimeError):
    """Raised when a plugin directory has no valid manifest."""


@dataclass(slots=True)
class PluginManifest:
    contract_version: str
    command: list[str]


def build_request(
    template_id: str, image_path: str, document_name: str, page_number: int
) -> dict[str, Any]:
    return {
        "contract_version": OCR_PLUGIN_CONTRACT_VERSION,
        "template_id": template_id,
        "page": {
            "image_path": image_path,
            "document_name": document_name,
            "page_number": page_number,
        },
    }


def parse_response(payload: dict[str, Any]) -> dict[str, Any]:
    version = payload.get("contract_version")
    if version != OCR_PLUGIN_CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported plugin contract_version: {version!r}; "
            f"expected {OCR_PLUGIN_CONTRACT_VERSION!r}"
        )
    record = payload.get("record")
    if not isinstance(record, dict):
        raise ValueError("Plugin response 'record' must be an object")
    return record


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def resolve_plugin_dir(
    explicit_dir: Path | str | None = None,
    default_dir: Path | str | None = None,
) -> Path:
    if explicit_dir is not None:
        candidate = Path(explicit_dir)
        if candidate.is_dir():
            return candidate
        raise PluginUnavailableError(f"Plugin directory not found: {candidate}")

    env_value = os.environ.get("OCR_PLUGIN_DIR")
    if env_value:
        candidate = Path(env_value)
        if candidate.is_dir():
            return candidate
        raise PluginUnavailableError(
            f"OCR_PLUGIN_DIR points to a missing directory: {candidate}"
        )

    default_candidate = (
        Path(default_dir) if default_dir is not None else _app_base_dir() / DEFAULT_PLUGIN_SUBDIR
    )
    if default_candidate.is_dir():
        return default_candidate
    raise PluginUnavailableError(
        "No OCR plugin found. Pass --ocr-plugin-dir, set OCR_PLUGIN_DIR, "
        f"or install the plugin at {default_candidate}."
    )


def load_manifest(plugin_dir: Path | str) -> PluginManifest:
    manifest_path = Path(plugin_dir) / MANIFEST_NAME
    if not manifest_path.is_file():
        raise PluginManifestError(f"Missing {MANIFEST_NAME} in plugin: {plugin_dir}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginManifestError(f"Invalid {MANIFEST_NAME}: {exc}") from exc
    command = data.get("command")
    if not isinstance(command, list) or not command or not all(
        isinstance(part, str) for part in command
    ):
        raise PluginManifestError(
            f"{MANIFEST_NAME} 'command' must be a non-empty list of strings"
        )
    return PluginManifest(
        contract_version=str(data.get("contract_version") or ""),
        command=[str(part) for part in command],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ocr_plugin.py -q`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/ocr_plugin.py tests/test_ocr_plugin.py
git commit -m "feat: add OCR plugin contract module"
```

---

## Task 2: PluginOcrBackend

**Files:**
- Create: `src/ocr_from2xlsx/plugin_backend.py`
- Create: `tests/fixtures/plugin/echo_plugin.py`
- Create: `tests/fixtures/plugin/echo_plugin.json`
- Create: `tests/fixtures/plugin/bad_exit_plugin.py`
- Create: `tests/test_plugin_backend.py`

- [ ] **Step 1: Create the fake plugin fixtures**

Create `tests/fixtures/plugin/echo_plugin.py`:

```python
"""Fake OCR plugin for tests: echoes a deterministic record from the request."""
from __future__ import annotations

import json
import sys


def main() -> int:
    request = json.loads(sys.stdin.read())
    page = request.get("page", {})
    response = {
        "contract_version": request.get("contract_version"),
        "record": {
            "record_id": f"plugin-{page.get('page_number', 0):04d}",
            "service_date": "2026-05-26",
            "identity": "patient",
            "name": "Plugin Echo",
            "medical_record_no": "PLUGIN-OK",
            "gender": "female",
            "patient_fields": {
                "nationality": "local",
                "age_group": "51_60",
                "channel": "internal_referral",
                "disease_status": "treating",
                "source": "outpatient",
                "cancers": ["breast_cancer"],
                "newly_diagnosed_within_year": False,
            },
            "services": {"consultation": {"health_medical": ["screening_prevention"]}},
            "ocr": {"confidence": 0.91, "raw_text": page.get("image_path", "")},
        },
    }
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `tests/fixtures/plugin/echo_plugin.json`:

```json
{
  "contract_version": "ocr_plugin.v1",
  "command": ["__PYTHON__", "echo_plugin.py"]
}
```

Create `tests/fixtures/plugin/bad_exit_plugin.py`:

```python
"""Fake OCR plugin that fails, to test error handling."""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("boom: plugin failed\n")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: `__PYTHON__` is a placeholder the backend replaces with the current interpreter so the
manifest stays interpreter-agnostic. This is implemented in Step 3.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_plugin_backend.py`:

```python
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.ocr_plugin import PluginManifestError, PluginUnavailableError
from ocr_from2xlsx.plugin_backend import PluginOcrBackend
from ocr_from2xlsx.preprocess import PreparedPage

_FIXTURE = Path(__file__).parent / "fixtures" / "plugin"


def _prepared_page(tmp_path: Path) -> PreparedPage:
    image_path = tmp_path / "for testing only-page-0001.png"
    image_path.write_bytes(b"\x89PNG\r\n")
    return PreparedPage(
        image_path=image_path,
        template_id="service_record.v1",
        source=SourceInfo(
            kind="pdf_page",
            document_path="tests/fixtures/pdf/for testing only.pdf",
            page_number=1,
            preprocessed_image_path=image_path.name,
            template_id="service_record.v1",
        ),
    )


def _install_plugin(tmp_path: Path, script: str = "echo_plugin.py") -> Path:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    shutil.copy(_FIXTURE / script, plugin_dir / script)
    command = [sys.executable, script]
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"contract_version": "ocr_plugin.v1", "command": command}),
        encoding="utf-8",
    )
    return plugin_dir


def test_extract_returns_record_from_plugin(tmp_path: Path) -> None:
    plugin_dir = _install_plugin(tmp_path)
    backend = PluginOcrBackend(plugin_dir)

    record = backend.extract(_prepared_page(tmp_path))

    assert record["name"] == "Plugin Echo"
    assert record["medical_record_no"] == "PLUGIN-OK"
    assert record["record_id"] == "plugin-0001"


def test_resolve_raises_when_no_plugin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OCR_PLUGIN_DIR", raising=False)

    with pytest.raises(PluginUnavailableError):
        PluginOcrBackend.resolve(
            explicit_dir=None, default_dir=tmp_path / "missing"
        )


def test_resolve_finds_explicit_dir(tmp_path: Path) -> None:
    plugin_dir = _install_plugin(tmp_path)

    backend = PluginOcrBackend.resolve(explicit_dir=plugin_dir)

    assert backend.extract(_prepared_page(tmp_path))["name"] == "Plugin Echo"


def test_extract_raises_on_plugin_failure(tmp_path: Path) -> None:
    plugin_dir = _install_plugin(tmp_path, script="bad_exit_plugin.py")
    backend = PluginOcrBackend(plugin_dir)

    with pytest.raises(RuntimeError, match="boom: plugin failed"):
        backend.extract(_prepared_page(tmp_path))


def test_constructor_raises_without_manifest(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "empty"
    plugin_dir.mkdir()

    with pytest.raises(PluginManifestError):
        PluginOcrBackend(plugin_dir)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_plugin_backend.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocr_from2xlsx.plugin_backend'`.

- [ ] **Step 4: Implement the backend**

Create `src/ocr_from2xlsx/plugin_backend.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ocr_from2xlsx.ocr_plugin import (
    PluginManifest,
    build_request,
    load_manifest,
    parse_response,
    resolve_plugin_dir,
)
from ocr_from2xlsx.preprocess import PreparedPage

_PYTHON_PLACEHOLDER = "__PYTHON__"


class PluginExecutionError(RuntimeError):
    """Raised when the plugin subprocess fails or returns invalid output."""


class PluginOcrBackend:
    def __init__(self, plugin_dir: Path | str) -> None:
        self.plugin_dir = Path(plugin_dir)
        self.manifest: PluginManifest = load_manifest(self.plugin_dir)

    @classmethod
    def resolve(
        cls,
        explicit_dir: Path | str | None = None,
        default_dir: Path | str | None = None,
    ) -> "PluginOcrBackend":
        plugin_dir = resolve_plugin_dir(explicit_dir=explicit_dir, default_dir=default_dir)
        return cls(plugin_dir)

    def _command(self) -> list[str]:
        return [
            sys.executable if part == _PYTHON_PLACEHOLDER else part
            for part in self.manifest.command
        ]

    def extract(self, page: PreparedPage) -> dict[str, object]:
        request = build_request(
            template_id=page.template_id,
            image_path=str(Path(page.image_path).resolve()),
            document_name=Path(page.source.document_path or "").name,
            page_number=page.source.page_number or 0,
        )
        try:
            completed = subprocess.run(
                self._command(),
                cwd=str(self.plugin_dir),
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except OSError as exc:
            raise PluginExecutionError(f"Failed to launch OCR plugin: {exc}") from exc
        if completed.returncode != 0:
            raise PluginExecutionError(
                f"OCR plugin exited with {completed.returncode}: {completed.stderr.strip()}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise PluginExecutionError(
                f"OCR plugin returned invalid JSON: {exc}; stderr={completed.stderr.strip()}"
            ) from exc
        return parse_response(payload)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_plugin_backend.py -q`
Expected: `5 passed`.

- [ ] **Step 6: Commit**

```powershell
git add src/ocr_from2xlsx/plugin_backend.py tests/test_plugin_backend.py tests/fixtures/plugin
git commit -m "feat: add subprocess-based OCR plugin backend"
```

---

## Task 3: Wire prepare-records to the plugin backend

**Files:**
- Modify: `src/ocr_from2xlsx/cli.py` (the `prepare-records` subparser and its `main()` branch)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

Add to `tests/test_cli.py` (top imports as needed: `json`, `shutil`, `sys`, `Path`):

```python
def _install_echo_plugin(tmp_path):
    import json as _json
    import shutil as _shutil
    import sys as _sys
    from pathlib import Path as _Path

    fixture = _Path(__file__).parent / "fixtures" / "plugin"
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    _shutil.copy(fixture / "echo_plugin.py", plugin_dir / "echo_plugin.py")
    (plugin_dir / "plugin.json").write_text(
        _json.dumps(
            {"contract_version": "ocr_plugin.v1", "command": [_sys.executable, "echo_plugin.py"]}
        ),
        encoding="utf-8",
    )
    return plugin_dir


def test_prepare_records_with_plugin_backend(tmp_path):
    import json as _json
    from pathlib import Path as _Path

    from ocr_from2xlsx.cli import main

    plugin_dir = _install_echo_plugin(tmp_path)
    pdf = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    output = tmp_path / "prepared.json"

    code = main(
        [
            "prepare-records",
            "--input",
            str(pdf),
            "--output",
            str(output),
            "--ocr-backend",
            "plugin",
            "--ocr-plugin-dir",
            str(plugin_dir),
        ]
    )

    assert code == 0
    data = _json.loads(output.read_text(encoding="utf-8"))
    assert data["records"][0]["name"] == "Plugin Echo"


def test_prepare_records_plugin_missing_reports_error(tmp_path, capsys):
    from pathlib import Path as _Path

    from ocr_from2xlsx.cli import main

    pdf = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    output = tmp_path / "prepared.json"

    code = main(
        [
            "prepare-records",
            "--input",
            str(pdf),
            "--output",
            str(output),
            "--ocr-backend",
            "plugin",
            "--ocr-plugin-dir",
            str(tmp_path / "no-plugin-here"),
        ]
    )

    assert code == 2
    assert "plugin" in capsys.readouterr().err.lower()


def test_prepare_records_fixture_backend_still_default(tmp_path):
    import json as _json
    from pathlib import Path as _Path

    from ocr_from2xlsx.cli import main

    pdf = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    fixture = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.ocr.json"
    output = tmp_path / "prepared.json"

    code = main(
        [
            "prepare-records",
            "--input",
            str(pdf),
            "--output",
            str(output),
            "--ocr-fixture",
            str(fixture),
        ]
    )

    assert code == 0
    data = _json.loads(output.read_text(encoding="utf-8"))
    assert data["records"][0]["name"] == "AI test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -k "plugin or fixture_backend"`
Expected: FAIL — `--ocr-backend` is an unrecognized argument.

- [ ] **Step 3: Update the prepare-records subparser**

In `src/ocr_from2xlsx/cli.py`, inside `build_parser()`, change the `prepare-records` arguments. Replace the existing `--ocr-fixture` line:

```python
    prepare_parser.add_argument(
        "--ocr-fixture",
        required=True,
        help="Fixture OCR payload path required for deterministic preparation.",
    )
```

with:

```python
    prepare_parser.add_argument(
        "--ocr-backend",
        choices=["fixture", "plugin"],
        default="fixture",
        help="OCR source: 'fixture' (default, deterministic) or 'plugin' (external portable OCR).",
    )
    prepare_parser.add_argument(
        "--ocr-fixture",
        help="Fixture OCR payload path (required when --ocr-backend fixture).",
    )
    prepare_parser.add_argument(
        "--ocr-plugin-dir",
        help="OCR plugin directory (overrides OCR_PLUGIN_DIR; used when --ocr-backend plugin).",
    )
```

- [ ] **Step 4: Update the prepare-records branch in `main()`**

In `src/ocr_from2xlsx/cli.py`, replace the whole `if args.command == "prepare-records":` block with:

```python
    if args.command == "prepare-records":
        from pathlib import Path

        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.prepare_records import prepare_records_from_paths

        try:
            template = _resolve_template(args.template_id)
            if args.ocr_backend == "plugin":
                from ocr_from2xlsx.ocr_plugin import PluginUnavailableError
                from ocr_from2xlsx.plugin_backend import PluginOcrBackend

                try:
                    backend = PluginOcrBackend.resolve(explicit_dir=args.ocr_plugin_dir)
                except PluginUnavailableError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
            else:
                from ocr_from2xlsx.ocr_backend import FixtureOcrBackend

                if not args.ocr_fixture:
                    print(
                        "error: --ocr-fixture is required when --ocr-backend fixture",
                        file=sys.stderr,
                    )
                    return 2
                backend = FixtureOcrBackend.from_path(Path(args.ocr_fixture))

            batch = prepare_records_from_paths(
                input_paths=[Path(value) for value in args.input],
                output_dir=Path(args.output).parent,
                template=template,
                backend=backend,
            )
            output_path = Path(args.output)
            dump_batch(batch, output_path)
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            RuntimeError,
        ) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(output_path)
        return 0
```

Adding `RuntimeError` ensures plugin runtime failures (`PluginExecutionError`) surface as exit code 2
with a message, not a traceback.

- [ ] **Step 5: Run the new tests and the full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_plugin_backend.py tests/test_ocr_plugin.py -q`
Expected: all pass, including `test_prepare_records_fixture_backend_still_default`.

Then run the full suite to confirm nothing regressed:

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all tests pass (existing fixture/e2e tests unchanged).

- [ ] **Step 6: Commit**

```powershell
git add src/ocr_from2xlsx/cli.py tests/test_cli.py
git commit -m "feat: add --ocr-backend plugin to prepare-records"
```

---

## Task 4: Docs, CLI-help sync, CHANGELOG, policy check

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Refresh the README CLI help block**

Run: `.venv\Scripts\python.exe -m ocr_from2xlsx prepare-records --help`

Copy the exact output between the README markers `<!-- ocr-from2xlsx-help:start -->` and
`<!-- ocr-from2xlsx-help:end -->` if those markers wrap the `prepare-records` help; otherwise
update the top-level help block the markers do wrap, using `.venv\Scripts\python.exe -m ocr_from2xlsx --help`.
Keep the marker comments intact.

- [ ] **Step 2: Add a README plugin usage section**

Add this section to `README.md` after the existing Usage section:

````markdown
## OCR plugin (portable, offline)

`prepare-records` can read OCR results from an external, portable OCR plugin instead of a fixture:

```powershell
ocr-from2xlsx prepare-records `
  --input "scan.pdf" `
  --output output\prepared.json `
  --ocr-backend plugin `
  --ocr-plugin-dir path\to\plugins\paddleocr
```

The plugin directory must contain a `plugin.json` manifest:

```json
{ "contract_version": "ocr_plugin.v1", "command": ["__PYTHON__", "main.py"] }
```

`__PYTHON__` is replaced with the running interpreter. The plugin receives an `ocr_plugin.v1`
request on stdin and returns `{ "contract_version": "ocr_plugin.v1", "record": { ... } }` on stdout.
If no plugin is found (via `--ocr-plugin-dir`, `OCR_PLUGIN_DIR`, or the default
`plugins/paddleocr` next to the executable), `prepare-records` exits with an error so you can fall
back to `--ocr-backend fixture` or the review UI. The PaddleOCR plugin itself is built separately
(see the design spec).
````

- [ ] **Step 3: Update CHANGELOG**

Add under `## [Unreleased]` `### Added` in `CHANGELOG.md`:

```markdown
- 新增 OCR 外掛契約（`ocr_plugin.v1`）與 `PluginOcrBackend`，可透過 subprocess 呼叫可攜式外部 OCR。
- `prepare-records` 新增 `--ocr-backend {fixture,plugin}` 與 `--ocr-plugin-dir`，外掛不存在時安全回報。
```

- [ ] **Step 4: Run policy check and full tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

Run: `python -m policy_check --repo .`
Expected: no failures. If `policy_check` is unavailable in the environment, note it in the PR and
skip; otherwise resolve any reported issues.

- [ ] **Step 5: Commit**

```powershell
git add README.md CHANGELOG.md
git commit -m "docs: document OCR plugin backend"
```

---

## Self-Review Notes

- **Spec coverage:** Plugin JSON contract (Task 1) ✓; `PluginOcrBackend` + plugin-dir resolution + fallback (Task 2) ✓; `prepare-records --ocr-backend/--ocr-plugin-dir`, fixture stays default (Task 3) ✓; fake-plugin contract tests, no real paddle (Tasks 2-3) ✓; existing tests/backends green (Task 3 Step 5) ✓; docs + CHANGELOG + CLI-help sync + policy (Task 4) ✓.
- **Out of scope (later sub-projects):** PaddleOCR engine + portable packaging (sub-project 2), form layout export from the `服務紀錄表` sheet (sub-project 3), checkbox/mark detection + webcam image registration (sub-project 4).
- **Type consistency:** `PluginManifest.command: list[str]`, `resolve_plugin_dir(explicit_dir, default_dir)`, `parse_response -> record dict`, `PluginOcrBackend(plugin_dir)` / `.resolve(...)` / `.extract(page) -> dict` are used identically across tasks.
- **Note:** `PluginExecutionError` and `PluginUnavailableError` both subclass `RuntimeError`. `test_extract_raises_on_plugin_failure` matches on `RuntimeError`. The CLI handles resolution failure (`PluginUnavailableError`) explicitly and also includes `RuntimeError` in its `except` tuple (Task 3 Step 4), so plugin runtime failures during `prepare-records` exit with code 2 and a message instead of a traceback.
```
