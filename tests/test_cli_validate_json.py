from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_validate_json_missing_input_returns_error(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    src_path = repo_root / "src"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(src_path)
    )
    missing_path = tmp_path / "missing.json"

    result = subprocess.run(
        [sys.executable, "-m", "ocr_from2xlsx", "validate-json", "--input", str(missing_path)],
        env=env,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    stderr = result.stderr.strip()
    assert stderr.startswith(b"error: ")
    assert len(stderr.splitlines()) == 1
