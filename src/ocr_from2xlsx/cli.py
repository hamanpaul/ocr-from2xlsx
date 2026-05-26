from __future__ import annotations

import argparse
import json
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


def _resolve_template(template_id: str):
    from ocr_from2xlsx.form_template import service_record_template

    if template_id == "service_record.v1":
        return service_record_template()
    raise ValueError(f"unknown template id: {template_id}")


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
    validate_parser = subparsers.add_parser(
        "validate-json",
        help="Validate normalized service-record JSON.",
        description="Validate normalized service-record JSON.",
    )
    validate_parser.add_argument("--input", required=True, help="Input JSON path.")
    import_parser = subparsers.add_parser(
        "import-json",
        help="Import normalized JSON records into a working XLSX.",
        description="Import normalized JSON records into a working XLSX.",
    )
    import_parser.add_argument("--input", required=True, help="Input JSON path.")
    import_parser.add_argument("--template", required=True, help="Template XLSX path.")
    import_parser.add_argument("--working", required=True, help="Working XLSX output path.")
    import_parser.add_argument("--report-json", required=True, help="Import report JSON path.")
    import_parser.add_argument("--report-csv", required=True, help="Import report CSV path.")
    prepare_parser = subparsers.add_parser(
        "prepare-records",
        help="Prepare normalized JSON records from PDF or image inputs.",
        description="Prepare normalized JSON records from PDF or image inputs.",
    )
    prepare_parser.add_argument("--input", required=True, action="append", help="Input PDF or image path.")
    prepare_parser.add_argument("--output", required=True, help="Output JSON path.")
    prepare_parser.add_argument(
        "--ocr-fixture",
        required=True,
        help="Fixture OCR payload path required for deterministic preparation.",
    )
    prepare_parser.add_argument(
        "--template-id",
        default="service_record.v1",
        help="Form template identifier (currently only service_record.v1 is supported).",
    )
    subparsers.add_parser("app", help="Launch the native desktop review UI.")
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
    if args.command == "validate-json":
        from pathlib import Path

        from ocr_from2xlsx.json_io import load_batch
        from ocr_from2xlsx.validation import validate_batch

        try:
            batch = load_batch(Path(args.input))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        results = validate_batch(batch)
        blocker_count = sum(len(result.blockers) for result in results.values())
        warning_count = sum(len(result.warnings) for result in results.values())
        print(f"records={len(batch.records)} blockers={blocker_count} warnings={warning_count}")
        return 1 if blocker_count else 0
    if args.command == "import-json":
        from pathlib import Path

        from ocr_from2xlsx.json_io import load_batch
        from ocr_from2xlsx.session import ImportSession

        accepted_count = 0
        blocked_count = 0
        may_have_imports = False
        try:
            batch = load_batch(Path(args.input))
            with ImportSession.start(Path(args.template), Path(args.working)) as session:
                for record in batch.records:
                    may_have_imports = True
                    result = session.accept_scan(record)
                    if result.status == "blocked":
                        blocked_count += 1
                    if result.status in {"forced", "written"}:
                        accepted_count += 1
                    may_have_imports = accepted_count > 0
                try:
                    session.write_report(Path(args.report_json), Path(args.report_csv))
                except OSError as exc:
                    message = f"error: {exc}; report writing did not complete"
                    if accepted_count > 0:
                        message = (
                            f"error: {exc}; working XLSX may contain imported records "
                            "but report writing did not complete"
                        )
                    print(message, file=sys.stderr)
                    return 2
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            message = f"error: {exc}"
            if may_have_imports or accepted_count > 0:
                message += "; working XLSX may contain imported records"
            print(message, file=sys.stderr)
            return 2
        print(Path(args.working))
        return 1 if blocked_count else 0
    if args.command == "prepare-records":
        from pathlib import Path

        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.ocr_backend import FixtureOcrBackend
        from ocr_from2xlsx.prepare_records import prepare_records_from_paths

        try:
            template = _resolve_template(args.template_id)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        batch = prepare_records_from_paths(
            input_paths=[Path(value) for value in args.input],
            output_dir=Path(args.output).parent,
            template=template,
            backend=FixtureOcrBackend.from_path(Path(args.ocr_fixture)),
        )
        output_path = Path(args.output)
        dump_batch(batch, output_path)
        print(output_path)
        return 0
    if args.command == "app":
        from ocr_from2xlsx.app import run_app

        return run_app()
    parser.print_help()
    return 0
