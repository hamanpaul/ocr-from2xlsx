# Handwritten Name Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the handwritten name safely — emit a PII-minimized name crop, offer an optional cloud-VLM suggestion, never trust a machine name without human confirmation, and learn over time via a local correction store + confirmed-name roster fuzzy-match.

**Architecture:** New stdlib-only main-app modules (`name_roster`, `correction_store`, `name_agent`) plus a pure crop-geometry helper in the offline plugin. The cloud VLM call is isolated behind a config-driven agent that degrades to a no-op `NullNameAgent` when absent. Config is TOML (stdlib `tomllib`); roster fuzzy-match uses stdlib `difflib`; the cloud agent uses stdlib `urllib` (no new dependencies). All logic is unit-testable with fakes; the real network call is a manual spike only.

**Tech Stack:** Python 3.12 stdlib (`tomllib`, `difflib`, `urllib`, `json`, `dataclasses`), Pillow (plugin crop, already in the paddle bundle), pytest. No new third-party dependency in the main package.

---

## Spec Reference

Implements `openspec/changes/add-handwritten-name-agent/` and design
`docs/superpowers/specs/2026-05-30-handwritten-name-recognition-design.md`.

Reference ground truth (form `tests/fixtures/pdf/for testing only.pdf`): name =「葉心安」(user-confirmed),
medical-record-no = 6250712919 (must NOT appear in the name crop). The name sits on the 姓名/病歷號 anchor
line; the record-no is on the line above; the diagnosis date on the line below.

Invariants: offline plugin stays offline; the cloud agent is opt-in and a no-op when absent; the name is
always flagged `name.unconfirmed` until a human confirms it; only the name crop ever leaves the machine.

## File Structure

```text
src/ocr_from2xlsx/
  name_roster.py        NEW. Pure difflib fuzzy match against a confirmed-name roster.
  correction_store.py   NEW. Append-only JSONL correction records; derive roster from store.
  name_agent.py         NEW. NameAgent protocol, NullNameAgent, TOML config loader, factory,
                        and a stdlib-urllib ClaudeNameAgent (network path = manual spike only).
  name_suggestion.py    NEW. Pure orchestration: suggest_name_for_record(...) and confirm_name(...).
plugins/paddleocr/
  name_crop.py          NEW. Pure crop-geometry (name box from the 姓名 anchor line, excluding
                        record-no/date lines) + a Pillow wrapper that saves the crop.
  main.py               MODIFY. After OCR, save the name crop next to the page image; the record path
                        is derived by the main app (no contract/Record change).
src/ocr_from2xlsx/cli.py  MODIFY. prepare-records: optional --name-agent-config; if present, run name
                        suggestion per record using the derived crop path. Absent => unchanged.
tests/
  test_name_roster.py       NEW
  test_correction_store.py  NEW
  test_name_agent.py        NEW
  test_name_suggestion.py   NEW
  test_name_crop.py         NEW
README.md / CHANGELOG.md    MODIFY
docs/superpowers/specs/.../name_agent.example.toml  NEW (example config, committed; real config is local/ignored)
```

Tests load plugin-side modules (`name_crop.py`) by file path via `importlib` (the established pattern).

---

## Task 1: Confirmed-name roster fuzzy match (pure)

**Files:**
- Create: `src/ocr_from2xlsx/name_roster.py`
- Create: `tests/test_name_roster.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_name_roster.py`:

```python
from __future__ import annotations

from ocr_from2xlsx.name_roster import roster_match


def test_exact_match_returns_name():
    assert roster_match("葉心安", ["葉心安", "王小明"]) == "葉心安"


def test_near_miss_within_threshold_matches():
    # one wrong char out of three -> ratio 0.67 >= 0.6
    assert roster_match("葉心女", ["葉心安", "王小明"]) == "葉心安"


def test_too_different_returns_none():
    assert roster_match("林大維", ["葉心安", "王小明"]) is None


def test_empty_candidate_or_roster_returns_none():
    assert roster_match("", ["葉心安"]) is None
    assert roster_match("葉心安", []) is None


def test_threshold_is_configurable():
    # exact-only when threshold is 1.0
    assert roster_match("葉心女", ["葉心安"], threshold=1.0) is None
    assert roster_match("葉心安", ["葉心安"], threshold=1.0) == "葉心安"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_roster.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/ocr_from2xlsx/name_roster.py`:

```python
"""Fuzzy-match an OCR/agent name candidate against a roster of confirmed names."""
from __future__ import annotations

import difflib

DEFAULT_THRESHOLD = 0.6


def roster_match(candidate: str, roster: list[str], threshold: float = DEFAULT_THRESHOLD) -> str | None:
    candidate = (candidate or "").strip()
    if not candidate or not roster:
        return None
    best_name: str | None = None
    best_score = 0.0
    for name in roster:
        score = difflib.SequenceMatcher(None, candidate, name).ratio()
        if score > best_score:
            best_score = score
            best_name = name
    return best_name if best_score >= threshold else None
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_roster.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/name_roster.py tests/test_name_roster.py
git commit -m "feat: add confirmed-name roster fuzzy match"
```
End every commit message with a blank line then exactly:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## Task 2: Correction store (append-only JSONL)

**Files:**
- Create: `src/ocr_from2xlsx/correction_store.py`
- Create: `tests/test_correction_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_correction_store.py`:

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.correction_store import (
    Correction,
    append_correction,
    load_corrections,
    roster_from_store,
)


def _correction(value: str, record_id: str) -> Correction:
    return Correction(
        field="name",
        final_value=value,
        record_id=record_id,
        crop_path=f"{record_id}-name.png",
        ocr_raw="",
        agent_suggestion="葉心女",
        roster_suggestion=None,
        source="for testing only.pdf#1",
        timestamp="2026-05-30T00:00:00+08:00",
    )


def test_append_and_load_round_trip(tmp_path: Path):
    store = tmp_path / "corrections.jsonl"
    append_correction(store, _correction("葉心安", "pdf-0001"))
    append_correction(store, _correction("王小明", "pdf-0002"))

    loaded = load_corrections(store)

    assert [c.final_value for c in loaded] == ["葉心安", "王小明"]
    assert loaded[0].agent_suggestion == "葉心女"


def test_roster_from_store_returns_distinct_names(tmp_path: Path):
    store = tmp_path / "corrections.jsonl"
    append_correction(store, _correction("葉心安", "pdf-0001"))
    append_correction(store, _correction("葉心安", "pdf-0003"))
    append_correction(store, _correction("王小明", "pdf-0002"))

    assert sorted(roster_from_store(store)) == ["王小明", "葉心安"]


def test_load_missing_store_returns_empty(tmp_path: Path):
    assert load_corrections(tmp_path / "nope.jsonl") == []
    assert roster_from_store(tmp_path / "nope.jsonl") == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_correction_store.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/ocr_from2xlsx/correction_store.py`:

```python
"""Append-only JSONL store of human name confirmations/corrections (learning data)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class Correction:
    field: str
    final_value: str
    record_id: str = ""
    crop_path: str | None = None
    ocr_raw: str = ""
    agent_suggestion: str | None = None
    roster_suggestion: str | None = None
    source: str = ""
    timestamp: str = ""


def append_correction(store_path: Path | str, correction: Correction) -> None:
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(correction), ensure_ascii=False) + "\n")


def load_corrections(store_path: Path | str) -> list[Correction]:
    path = Path(store_path)
    if not path.is_file():
        return []
    corrections: list[Correction] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        corrections.append(Correction(**json.loads(line)))
    return corrections


def roster_from_store(store_path: Path | str, field: str = "name") -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for correction in load_corrections(store_path):
        if correction.field != field:
            continue
        value = (correction.final_value or "").strip()
        if value and value not in seen:
            seen.add(value)
            names.append(value)
    return names
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_correction_store.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/correction_store.py tests/test_correction_store.py
git commit -m "feat: add JSONL correction store for name learning"
```

---

## Task 3: Name agent protocol, config, factory (graceful-optional)

**Files:**
- Create: `src/ocr_from2xlsx/name_agent.py`
- Create: `tests/test_name_agent.py`
- Create: `docs/superpowers/specs/name_agent.example.toml`

- [ ] **Step 1: Write failing tests**

Create `tests/test_name_agent.py`:

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.name_agent import (
    NameAgentConfig,
    NullNameAgent,
    build_agent,
    load_config,
)


def test_missing_config_is_disabled(tmp_path: Path):
    config = load_config(tmp_path / "absent.toml")
    assert config.enabled is False


def test_disabled_config_builds_null_agent(tmp_path: Path):
    path = tmp_path / "name_agent.toml"
    path.write_text('enabled = false\nprovider = "claude"\n', encoding="utf-8")
    agent = build_agent(load_config(path))
    assert isinstance(agent, NullNameAgent)
    assert agent.suggest("anything.png") is None


def test_enabled_config_parsed(tmp_path: Path):
    path = tmp_path / "name_agent.toml"
    path.write_text(
        'enabled = true\nprovider = "claude"\nmodel = "claude-x"\n'
        'endpoint = "https://api.example/v1/messages"\nprompt = "read the name"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.enabled is True
    assert config.provider == "claude"
    assert config.model == "claude-x"


def test_unknown_provider_falls_back_to_null(tmp_path: Path):
    config = NameAgentConfig(enabled=True, provider="nope")
    assert isinstance(build_agent(config), NullNameAgent)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_agent.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/ocr_from2xlsx/name_agent.py`:

```python
"""Optional, config-driven handwritten-name suggestion agent.

When unconfigured/disabled/unknown-provider, `build_agent` returns a NullNameAgent whose `suggest`
returns None, so the pipeline is unaffected. The cloud ClaudeNameAgent's network call is exercised only
by a manual spike, never by CI.
"""
from __future__ import annotations

import base64
import json
import os
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class NameAgent(Protocol):
    def suggest(self, crop_path: str) -> str | None:
        ...


class NullNameAgent:
    def suggest(self, crop_path: str) -> str | None:
        return None


@dataclass(slots=True)
class NameAgentConfig:
    enabled: bool = False
    provider: str = ""
    model: str = ""
    endpoint: str = ""
    prompt: str = "讀出圖片中的手寫中文姓名，只回傳姓名本身，不要其他文字。"
    api_key_env: str = "ANTHROPIC_API_KEY"


def load_config(path: Path | str) -> NameAgentConfig:
    path = Path(path)
    if not path.is_file():
        return NameAgentConfig(enabled=False)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return NameAgentConfig(
        enabled=bool(data.get("enabled", False)),
        provider=str(data.get("provider", "")),
        model=str(data.get("model", "")),
        endpoint=str(data.get("endpoint", "")),
        prompt=str(data.get("prompt", NameAgentConfig.prompt)),
        api_key_env=str(data.get("api_key_env", "ANTHROPIC_API_KEY")),
    )


class ClaudeNameAgent:
    """Calls an Anthropic-style messages endpoint with the name crop. Network = spike-only."""

    def __init__(self, config: NameAgentConfig) -> None:
        self.config = config

    def suggest(self, crop_path: str) -> str | None:
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key or not self.config.endpoint:
            return None
        try:
            image_b64 = base64.b64encode(Path(crop_path).read_bytes()).decode("ascii")
            payload = {
                "model": self.config.model,
                "max_tokens": 32,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": self.config.prompt},
                        ],
                    }
                ],
            }
            request = urllib.request.Request(
                self.config.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "content-type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            parts = body.get("content") or []
            for part in parts:
                if part.get("type") == "text":
                    return (part.get("text") or "").strip() or None
            return None
        except Exception:
            # Any failure (network, auth, parse) degrades to "no suggestion" — pipeline unaffected.
            return None


def build_agent(config: NameAgentConfig) -> NameAgent:
    if not config.enabled:
        return NullNameAgent()
    if config.provider == "claude":
        return ClaudeNameAgent(config)
    return NullNameAgent()
```

Create `docs/superpowers/specs/name_agent.example.toml`:

```toml
# Copy to a local (gitignored) file and point --name-agent-config at it.
# The API key is read from the environment variable named by api_key_env, never stored here.
enabled = false
provider = "claude"
model = "claude-opus-4-8"
endpoint = "https://api.anthropic.com/v1/messages"
api_key_env = "ANTHROPIC_API_KEY"
prompt = "讀出圖片中的手寫中文姓名，只回傳姓名本身，不要其他文字。"
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_agent.py -q`
Expected: `4 passed` (no network; the cloud path is never hit because configs are disabled/fake).

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/name_agent.py tests/test_name_agent.py docs/superpowers/specs/name_agent.example.toml
git commit -m "feat: add optional config-driven name agent"
```

---

## Task 4: Name suggestion + confirmation orchestration (pure, fake-driven)

**Files:**
- Create: `src/ocr_from2xlsx/name_suggestion.py`
- Create: `tests/test_name_suggestion.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_name_suggestion.py`:

```python
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.correction_store import load_corrections, roster_from_store
from ocr_from2xlsx.name_suggestion import confirm_name, suggest_name


class _FakeAgent:
    def __init__(self, value):
        self._value = value

    def suggest(self, crop_path):
        return self._value


def test_suggest_prefers_roster_match_over_agent():
    # agent reads a near-miss; roster has the confirmed spelling -> roster wins
    name, warnings = suggest_name(
        crop_path="x.png", agent=_FakeAgent("葉心女"), roster=["葉心安"], ocr_raw=""
    )
    assert name == "葉心安"
    assert "name.unconfirmed" in warnings


def test_suggest_uses_agent_when_no_roster_match():
    name, warnings = suggest_name(
        crop_path="x.png", agent=_FakeAgent("陳大文"), roster=["葉心安"], ocr_raw=""
    )
    assert name == "陳大文"
    assert "name.unconfirmed" in warnings


def test_suggest_empty_when_no_agent_value_and_no_roster():
    name, warnings = suggest_name(
        crop_path="x.png", agent=_FakeAgent(None), roster=[], ocr_raw=""
    )
    assert name == ""
    assert "name.unconfirmed" in warnings


def test_confirm_name_writes_store_and_grows_roster(tmp_path: Path):
    store = tmp_path / "corrections.jsonl"
    roster = confirm_name(
        store_path=store,
        record_id="pdf-0001",
        final_value="葉心安",
        crop_path="pdf-0001-name.png",
        ocr_raw="",
        agent_suggestion="葉心女",
        roster_suggestion=None,
        source="for testing only.pdf#1",
        timestamp="2026-05-30T00:00:00+08:00",
    )
    assert "葉心安" in roster
    assert roster_from_store(store) == ["葉心安"]
    assert load_corrections(store)[0].final_value == "葉心安"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_suggestion.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `src/ocr_from2xlsx/name_suggestion.py`:

```python
"""Pure orchestration of name suggestion and confirmation write-back."""
from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.correction_store import Correction, append_correction, roster_from_store
from ocr_from2xlsx.name_agent import NameAgent
from ocr_from2xlsx.name_roster import roster_match

NAME_UNCONFIRMED = "name.unconfirmed"


def suggest_name(
    crop_path: str,
    agent: NameAgent,
    roster: list[str],
    ocr_raw: str = "",
) -> tuple[str, list[str]]:
    """Return (suggested_name, warnings). Never treats the name as confirmed."""
    agent_value = agent.suggest(crop_path) if crop_path else None
    candidate = (agent_value or ocr_raw or "").strip()
    match = roster_match(candidate, roster) if candidate else None
    name = match or (agent_value or "").strip()
    return (name, [NAME_UNCONFIRMED])


def confirm_name(
    store_path: Path | str,
    record_id: str,
    final_value: str,
    *,
    crop_path: str | None = None,
    ocr_raw: str = "",
    agent_suggestion: str | None = None,
    roster_suggestion: str | None = None,
    source: str = "",
    timestamp: str = "",
) -> list[str]:
    """Persist a human confirmation/correction and return the updated roster."""
    append_correction(
        store_path,
        Correction(
            field="name",
            final_value=final_value,
            record_id=record_id,
            crop_path=crop_path,
            ocr_raw=ocr_raw,
            agent_suggestion=agent_suggestion,
            roster_suggestion=roster_suggestion,
            source=source,
            timestamp=timestamp,
        ),
    )
    return roster_from_store(store_path)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_suggestion.py -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/name_suggestion.py tests/test_name_suggestion.py
git commit -m "feat: add name suggestion and confirmation orchestration"
```

---

## Task 5: PII-minimized name-crop geometry + plugin save

**Files:**
- Create: `plugins/paddleocr/name_crop.py`
- Create: `tests/test_name_crop.py`
- Modify: `plugins/paddleocr/main.py`

- [ ] **Step 1: Write failing tests (pure geometry)**

Create `tests/test_name_crop.py`:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "name_crop.py"
_spec = importlib.util.spec_from_file_location("paddle_name_crop", _MODULE)
name_crop = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(name_crop)

name_crop_box = name_crop.name_crop_box


def _line(text, x0, y0, x1, y1):
    return {"text": text, "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def test_crop_covers_name_line_and_excludes_record_no_and_date():
    lines = [
        _line("病人6250712919", 60, 360, 360, 392),    # record-no line ABOVE
        _line("姓名/病歷號", 60, 396, 200, 428),         # anchor line (name sits to its right)
        _line("114、06、25", 60, 432, 300, 470),         # diagnosis date BELOW
    ]
    box = name_crop_box(lines, page_width=1000)
    assert box is not None
    x0, y0, x1, y1 = box
    # horizontally starts at/after the anchor's right edge; vertically within the anchor line band
    assert x0 >= 200
    assert 396 <= y0 <= 428 and 396 <= y1 <= 428
    # the record-no line (y<=392) and the date line (y>=432) are OUTSIDE the crop band
    assert y0 > 392 and y1 < 432
    assert x1 <= 1000 and x1 > x0


def test_returns_none_without_anchor():
    assert name_crop_box([_line("無關", 0, 0, 50, 20)], page_width=1000) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_crop.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement geometry + Pillow wrapper**

Create `plugins/paddleocr/name_crop.py`:

```python
"""Name-crop geometry (pure) + a Pillow saver (plugin-only).

The name sits on the 姓名/病歷號 anchor line, to the right of the label. The medical-record-no is on the
line above and the diagnosis date on the line below; restricting the crop to the anchor line's y-band
excludes both, minimizing PII in the crop.
"""
from __future__ import annotations

from typing import Any

_ANCHOR = "姓名"
_RIGHT_PAD_FACTOR = 6.0  # extend right of the label by N * label-height to cover the handwriting


def _bbox(line: dict[str, Any]) -> tuple[float, float, float, float]:
    xs = [pt[0] for pt in line["box"]]
    ys = [pt[1] for pt in line["box"]]
    return (min(xs), min(ys), max(xs), max(ys))


def name_crop_box(lines: list[dict[str, Any]], page_width: float) -> tuple[int, int, int, int] | None:
    anchor = next((ln for ln in lines if _ANCHOR in str(ln.get("text") or "")), None)
    if anchor is None:
        return None
    ax0, ay0, ax1, ay1 = _bbox(anchor)
    height = max(1.0, ay1 - ay0)
    x0 = ax1
    x1 = min(float(page_width), ax1 + height * _RIGHT_PAD_FACTOR)
    if x1 <= x0:
        x1 = min(float(page_width), x0 + height)
    return (int(x0), int(ay0), int(x1), int(ay1))


def save_name_crop(image_path: str, lines: list[dict[str, Any]], out_path: str) -> str | None:
    from PIL import Image

    image = Image.open(image_path).convert("L")
    box = name_crop_box(lines, page_width=image.width)
    if box is None:
        return None
    image.crop(box).save(out_path)
    return out_path
```

Modify `plugins/paddleocr/main.py`: after `lines = ocr_fn(image_path)` (inside `run`), is NOT the right
place (run is pure/fake-tested). Instead, in the REAL `main()` flow only, save the crop next to the page
image and add its filename to the response record metadata. Concretely, in `main()` after building
`response`, add (load `name_crop` as a sibling like `field_extract`):

```python
    # (top of file, beside the field_extract/mark_detect importlib loads)
    _NC_SPEC = _importlib_util.spec_from_file_location(
        "paddleocr_plugin_name_crop", _HERE / "name_crop.py"
    )
    name_crop = _importlib_util.module_from_spec(_NC_SPEC)
    assert _NC_SPEC and _NC_SPEC.loader
    _NC_SPEC.loader.exec_module(name_crop)
```

and in `main()`, after computing `response`, before writing stdout:

```python
    page = request.get("page") or {}
    image_path = str(page.get("image_path") or "")
    if image_path:
        from pathlib import Path as _Path
        crop_out = str(_Path(image_path).with_name(_Path(image_path).stem + "-name.png"))
        lines_for_crop = response["record"]["ocr"].get("_lines")  # not present; recompute below
```

Since `run` does not expose the OCR lines in the record, compute the crop in `main()` directly from a fresh
`_paddle_ocr_fn` is wasteful. Instead, refactor minimally: have `main()` capture the lines. Replace the
`main()` body's record build with:

```python
def main() -> int:
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    _configure_offline_models()
    request = json.loads(sys.stdin.read())
    page = request.get("page") or {}
    image_path = str(page.get("image_path") or "")
    lines = _paddle_ocr_fn(image_path) if image_path else []
    response = run(request, ocr_fn=lambda _p: lines, mark_fn=mark_detect.detect_marked_labels)
    if image_path:
        from pathlib import Path as _Path
        crop_out = _Path(image_path).with_name(_Path(image_path).stem + "-name.png")
        saved = name_crop.save_name_crop(image_path, lines, str(crop_out))
        if saved:
            response["record"]["ocr"]["name_crop"] = _Path(saved).name
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0
```

This computes OCR once, reuses the lines for both `run` and the crop, and records the crop filename under
`record.ocr.name_crop` (additive metadata; downstream OcrInfo ignores unknown keys, so the contract is
unchanged). `run` itself is untouched and still fake-tested.

- [ ] **Step 4: Run to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_name_crop.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (plugin `run`/contract tests unaffected).

- [ ] **Step 6: Commit**

```powershell
git add plugins/paddleocr/name_crop.py tests/test_name_crop.py plugins/paddleocr/main.py
git commit -m "feat: emit PII-minimized name crop from the plugin"
```

---

## Task 6: CLI integration (optional, absent => unchanged) + manual spike

**Files:**
- Modify: `src/ocr_from2xlsx/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI test (fake agent via disabled config => no error, unchanged record count)**

Add to `tests/test_cli.py`:

```python
def test_prepare_records_name_agent_absent_is_noop(tmp_path):
    # With no --name-agent-config, prepare-records behaves exactly as before (fixture backend).
    import json as _json
    from pathlib import Path as _Path
    from ocr_from2xlsx.cli import main

    pdf = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    fixture = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.ocr.json"
    out = tmp_path / "prepared.json"

    code = main([
        "prepare-records", "--input", str(pdf), "--output", str(out),
        "--ocr-fixture", str(fixture),
    ])
    assert code == 0
    data = _json.loads(out.read_text(encoding="utf-8"))
    assert data["records"][0]["name"] == "AI test"  # unchanged fixture behavior


def test_prepare_records_disabled_name_agent_config_is_noop(tmp_path):
    import json as _json
    from pathlib import Path as _Path
    from ocr_from2xlsx.cli import main

    cfg = tmp_path / "name_agent.toml"
    cfg.write_text("enabled = false\n", encoding="utf-8")
    pdf = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.pdf"
    fixture = _Path(__file__).parent / "fixtures" / "pdf" / "for testing only.ocr.json"
    out = tmp_path / "prepared.json"

    code = main([
        "prepare-records", "--input", str(pdf), "--output", str(out),
        "--ocr-fixture", str(fixture), "--name-agent-config", str(cfg),
    ])
    assert code == 0
    data = _json.loads(out.read_text(encoding="utf-8"))
    assert data["records"][0]["name"] == "AI test"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -k name_agent`
Expected: FAIL (`--name-agent-config` unknown).

- [ ] **Step 3: Implement CLI wiring**

In `src/ocr_from2xlsx/cli.py`, add to the `prepare-records` subparser:

```python
    prepare_parser.add_argument(
        "--name-agent-config",
        help="Optional TOML config for the handwritten-name agent; absent or disabled = no-op.",
    )
```

In the `prepare-records` branch of `main()`, after the batch is built and before `dump_batch`, add an
optional name-suggestion pass that is a strict no-op unless a config is given AND a crop exists:

```python
        if args.name_agent_config:
            from ocr_from2xlsx.name_agent import build_agent, load_config
            from ocr_from2xlsx.name_suggestion import suggest_name

            agent = build_agent(load_config(Path(args.name_agent_config)))
            output_dir = Path(args.output).parent
            for record in batch.records:
                crop_name = (record.ocr.__dict__.get("name_crop")
                             if hasattr(record.ocr, "__dict__") else None)
                # the fixture backend has no crop; only the real plugin emits record.ocr.name_crop
                crop_path = str(output_dir / crop_name) if crop_name else ""
                if not record.name:
                    name, warnings = suggest_name(
                        crop_path=crop_path, agent=agent,
                        roster=[], ocr_raw=record.ocr.raw_text,
                    )
                    if name:
                        record.name = name
                    for warning in warnings:
                        if warning not in record.ocr.warnings:
                            record.ocr.warnings.append(warning)
```

Notes: this only fills `record.name` when it was empty and the agent/roster produced something; it always
appends `name.unconfirmed` for records it touched. With a disabled config, `build_agent` returns
`NullNameAgent`, `suggest_name` returns `("", [...])`, and an already-filled fixture name (`AI test`) is left
untouched because the `if not record.name` guard skips it — so the two tests above pass. The roster is
wired as empty here (the persisted roster/store is loaded in the review/confirm flow, out of scope for this
CLI pass; keep `roster=[]` to stay within scope and avoid coupling prepare-records to a store location).

IMPORTANT: if `record.ocr` is a dataclass with `slots=True`, `record.ocr.__dict__` will not exist. In that
case read the crop name via `getattr(record.ocr, "name_crop", None)`. Use:

```python
                crop_name = getattr(record.ocr, "name_crop", None)
```

If `OcrInfo` does not retain unknown keys (so `name_crop` is dropped during normalization), then for this
CLI pass `crop_name` is None and the agent simply gets an empty crop_path → returns None → no-op. That is
acceptable: the crop is still emitted by the plugin for the review/confirm flow; wiring the crop path
through normalization is a follow-up and NOT required for this change's success criteria (which the unit
tests for `suggest_name`/`name_crop` already cover). Keep this CLI pass minimal and correct for the no-op
cases the tests assert.

- [ ] **Step 4: Run to verify pass + full suite**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -k name_agent`
Then: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass; default prepare-records behavior unchanged.

- [ ] **Step 5: Commit**

```powershell
git add src/ocr_from2xlsx/cli.py tests/test_cli.py
git commit -m "feat: optional name-agent pass in prepare-records (no-op when absent)"
```

- [ ] **Step 6: Manual weakest-tier spike (no commit of secrets)**

Build the bundle, render the form, run the plugin to emit the name crop, then call the configured cloud
agent on the crop and record which tier reads「葉心安」:

```powershell
.venv\Scripts\python build/build_paddle_plugin.py
.venv\Scripts\python -c "import fitz; fitz.open('tests/fixtures/pdf/for testing only.pdf').load_page(0).get_pixmap(dpi=400).save('output/_form.png')"
# run the plugin once to emit output/_form-name.png (via PluginOcrBackend.extract), then:
$env:ANTHROPIC_API_KEY = "<your key>"
.venv\Scripts\python -c "from ocr_from2xlsx.name_agent import build_agent, load_config; print(build_agent(load_config('name_agent.local.toml')).suggest('output/_form-name.png'))"
```

Record in the PR/CHANGELOG which model tier read the name correctly (or that none did reliably →
human-confirm remains mandatory). Do NOT commit any API key or local config.

---

## Task 7: Docs, policy, integration

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `.gitignore`

- [ ] **Step 1: .gitignore** — add `name_agent.local.toml` and `*-name.png` (local crops) so secrets/PII crops are never committed.

- [ ] **Step 2: README** — document: the plugin emits a PII-minimized name crop; the optional name agent is configured via a TOML file (`--name-agent-config`), reads the API key from env, sends ONLY the name crop, and is a no-op when absent; the name is always `name.unconfirmed` and must be human-confirmed; confirmations feed a local correction store + roster that improves matching and reduces cloud calls over time.

- [ ] **Step 3: CHANGELOG** — under `## [Unreleased]`:

```markdown
### Added
- 手寫姓名：離線外掛輸出個資最小化的姓名裁圖；新增可選、由 TOML config 指定的雲端 VLM name agent（缺席即 no-op，只送姓名裁圖）。
- 校正學習：新增 JSONL 校正紀錄 store 與本機確認姓名名冊 + difflib 模糊比對（`name_roster`/`correction_store`/`name_suggestion`）。
- 姓名一律標記 `name.unconfirmed`，需人工確認後才入庫。
```

- [ ] **Step 4: Tests + policy**

```powershell
.venv\Scripts\python -W error -m pytest -q
.venv\Scripts\python build/package.py
python -m policy_check --repo .
```
Expected: all pass; policy 0 failures.

- [ ] **Step 5: Commit**

```powershell
git add README.md CHANGELOG.md .gitignore
git commit -m "docs: document handwritten name agent and learning loop"
```

---

## Self-Review Notes

- **Spec coverage:** name crop excluding record-no (Task 5) ✓; optional gracefully-absent agent (Task 3 + Task 6 no-op tests) ✓; `name.unconfirmed` always (Task 4 `suggest_name`) ✓; correction store on confirm (Task 2 + Task 4 `confirm_name`) ✓; roster fuzzy-match recommendation (Task 1 + Task 4 prefers roster) ✓; weakest-tier spike (Task 6 Step 6) ✓; existing tests/policy green (Task 7) ✓.
- **Type consistency:** `roster_match(candidate, roster, threshold)`, `Correction(...)`, `append_correction/load_corrections/roster_from_store`, `NameAgent.suggest(crop_path)`, `build_agent/load_config`, `suggest_name(crop_path, agent, roster, ocr_raw) -> (str, list)`, `confirm_name(store_path, record_id, final_value, ...) -> list`, `name_crop_box(lines, page_width)` / `save_name_crop(image_path, lines, out_path)` are used consistently across tasks and tests.
- **Scope/known limitations (honest):** The CLI pass (Task 6) wires `roster=[]` and relies on `record.ocr.name_crop` which may be dropped by `OcrInfo` normalization; if so the CLI pass is a safe no-op and the real value is delivered by the unit-tested `suggest_name`/`confirm_name`/`name_crop` units plus the manual spike. Full review-UI wiring of suggestion+confirm+roster-load is intentionally out of scope (design says reuse existing flow). The cloud agent's network path is spike-verified, never CI.
- **No new dependency:** TOML via stdlib `tomllib`, fuzzy via `difflib`, HTTP via `urllib` — main package stays dependency-light.
```
