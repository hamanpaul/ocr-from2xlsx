from __future__ import annotations

import argparse
import sys
from typing import TextIO


def _write_help_text(help_text: str, file: TextIO | None = None) -> None:
    output = file if file is not None else sys.stdout
    if output is sys.stdout and hasattr(sys.stdout, "buffer"):
        encoding = sys.stdout.encoding or "utf-8"
        errors = sys.stdout.errors or "strict"
        sys.stdout.buffer.write(help_text.encode(encoding, errors))
        return
    output.write(help_text)


class LfHelpArgumentParser(argparse.ArgumentParser):
    def print_help(self, file: TextIO | None = None) -> None:
        _write_help_text(self.format_help(), file)


def build_parser() -> argparse.ArgumentParser:
    parser = LfHelpArgumentParser(
        prog="ocr-from2xlsx",
        description="Import normalized service-record JSON into the monthly report XLSX.",
    )
    parser.add_argument("--version", action="store_true", help="Print package version and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from ocr_from2xlsx import __version__

        print(__version__)
        return 0
    parser.print_help()
    return 0
