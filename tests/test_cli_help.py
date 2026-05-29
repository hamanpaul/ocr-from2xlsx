from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_help_output_uses_lf_line_endings() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    src_path = repo_root / "src"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(src_path)
    )
    result = subprocess.run(
        [sys.executable, "-m", "ocr_from2xlsx", "--help"],
        env=env,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert b"\r\n" not in result.stdout
    assert b"\n" in result.stdout
    assert b"Prepare PDF records or import normalized service-record JSON into the monthly report XLSX." in result.stdout
    assert b"Import normalized JSON records into a working XLSX." in result.stdout
