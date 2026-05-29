"""Fake OCR plugin that fails, to test error handling."""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("boom: plugin failed\n")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
