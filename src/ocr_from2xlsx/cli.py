from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
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
        help_text = self.format_help()
        if self.description and self.description not in help_text:
            help_text = f"{self.description}\n\n{help_text}"
        _write_help_text(help_text, file)


def _resolve_template(template_id: str):
    from ocr_from2xlsx.form_template import service_record_template

    if template_id == "service_record.v1":
        return service_record_template()
    raise ValueError(f"Unsupported template_id: {template_id!r}")


def _resolve_name_crop_path(record, output_dir: Path) -> str | None:
    crop_value = getattr(record.ocr, "name_crop", None)
    if crop_value:
        crop_path = Path(crop_value)
        if not crop_path.is_absolute():
            crop_path = output_dir / crop_path
        try:
            crop_path.resolve(strict=False).relative_to(output_dir.resolve(strict=False))
        except ValueError:
            crop_path = None
        else:
            if crop_path.is_file():
                return str(crop_path)
    prepared_image = record.source.preprocessed_image_path
    if not prepared_image:
        return None
    prepared_path = Path(prepared_image)
    crop_path = prepared_path.with_name(f"{prepared_path.stem}-name.png")
    if not crop_path.is_absolute():
        crop_path = output_dir / crop_path
    return str(crop_path) if crop_path.is_file() else None


def build_parser() -> argparse.ArgumentParser:
    parser = LfHelpArgumentParser(
        prog="ocr-from2xlsx",
        description="Prepare PDF records or import normalized service-record JSON into the monthly report XLSX.",
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
    import_parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Force writable-only blockers to import incomplete records.",
    )
    import_parser.add_argument(
        "--allow-unconfirmed-name",
        action="store_true",
        help="DEV ONLY: write records whose name is still machine-suggested (name.unconfirmed) "
             "without GUI confirmation; the unconfirmed warning is retained in the report. "
             "Deployment should require GUI confirmation instead.",
    )
    prepare_parser = subparsers.add_parser(
        "prepare-records",
        help="Prepare normalized JSON records from PDF inputs.",
        description="Prepare normalized JSON records from PDF inputs.",
    )
    prepare_parser.add_argument("--input", required=True, action="append", help="Input PDF path.")
    prepare_parser.add_argument("--output", required=True, help="Output JSON path.")
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
    prepare_parser.add_argument(
        "--template-id",
        default="service_record.v1",
        help="Form template identifier (currently only service_record.v1 is supported).",
    )
    prepare_parser.add_argument(
        "--name-agent-config",
        help="Optional TOML config for the handwritten-name agent; absent or disabled = no-op.",
    )
    subparsers.add_parser("app", help="Launch the native desktop review UI.")
    parser.set_defaults(command="app")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from ocr_from2xlsx import __version__

        print(__version__)
        return 0
    if args.command == "sample-json":
        from ocr_from2xlsx.json_io import dump_batch
        from ocr_from2xlsx.sample_data import generate_sample_batch

        batch = generate_sample_batch(count=args.count, template_name=args.template_name)
        output_path = Path(args.output)
        dump_batch(batch, output_path)
        print(output_path)
        return 0
    if args.command == "validate-json":
        from ocr_from2xlsx.json_io import load_batch
        from ocr_from2xlsx.validation import validate_batch

        try:
            batch = load_batch(Path(args.input))
        except (OSError, json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        results = validate_batch(batch)
        blocker_count = sum(len(result.blockers) for result in results.values())
        warning_count = sum(len(result.warnings) for result in results.values())
        print(f"records={len(batch.records)} blockers={blocker_count} warnings={warning_count}")
        return 1 if blocker_count else 0
    if args.command == "import-json":
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
                    result = session.accept_scan(
                        record,
                        force=args.allow_incomplete,
                        allow_unconfirmed_name=args.allow_unconfirmed_name,
                    )
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
            if args.name_agent_config:
                from ocr_from2xlsx.correction_store import (
                    default_correction_store_path,
                    roster_from_store,
                )
                from ocr_from2xlsx.name_agent import NullNameAgent, build_agent, load_config
                from ocr_from2xlsx.name_suggestion import suggest_name

                config = load_config(Path(args.name_agent_config))
                if config.enabled:
                    agent = build_agent(config)
                    if not isinstance(agent, NullNameAgent):
                        output_dir = output_path.parent
                        roster = roster_from_store(default_correction_store_path(output_path))
                        for record in batch.records:
                            if record.name:
                                continue
                            crop_path = _resolve_name_crop_path(record, output_dir)
                            if not crop_path:
                                continue
                            name, warnings = suggest_name(
                                crop_path=crop_path,
                                agent=agent,
                                roster=roster,
                                ocr_raw=record.ocr.raw_text or "",
                            )
                            if name:
                                record.name = name
                            for warning in warnings:
                                if warning not in record.ocr.warnings:
                                    record.ocr.warnings.append(warning)
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
    if args.command == "app":
        from ocr_from2xlsx.app import run_app

        return run_app()
    parser.print_help()
    return 0
