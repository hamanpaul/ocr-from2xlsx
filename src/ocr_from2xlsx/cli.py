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
    subparsers = parser.add_subparsers(dest="command", parser_class=LfHelpArgumentParser)
    sample_parser = subparsers.add_parser(
        "sample-json",
        help="Generate deterministic sample service-record JSON.",
        description="Generate deterministic sample service-record JSON.",
    )
    sample_parser.add_argument("--output", required=True, help="Output path for the JSON file.")
    sample_parser.add_argument("--count", type=int, default=100, help="Number of records to generate.")
    sample_parser.add_argument(
        "--template-name",
        default="template.xlsx",
        help="Template name to store in source_batch.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from ocr_from2xlsx import __version__

        print(__version__)
        return 0
    if args.command == "sample-json":
        from pathlib import Path

        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.sample_data import generate_sample_batch

        batch = generate_sample_batch(count=args.count, template_name=args.template_name)
        output_path = Path(args.output)
        dump_batch(batch, output_path)
        print(output_path)
        return 0
    parser.print_help()
    return 0
