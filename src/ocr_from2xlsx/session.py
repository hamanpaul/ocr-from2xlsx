from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ocr_from2xlsx.domain import Record
from ocr_from2xlsx.report import ImportReport, ImportReportItem
from ocr_from2xlsx.validation import validate_record
from ocr_from2xlsx.workbook import WorkbookWriter


def _duplicate_key_is_usable(record: Record) -> bool:
    if not record.service_date:
        return False
    try:
        date.fromisoformat(record.service_date)
    except (TypeError, ValueError):
        return False
    if not record.name or not record.name.strip():
        return False
    if not record.medical_record_no or not record.medical_record_no.strip():
        return False
    return True


@dataclass(slots=True)
class AcceptResult:
    record_id: str
    status: str
    row_number: int | None
    blockers: list[str]
    warnings: list[str]


class ImportSession:
    def __init__(self, writer: WorkbookWriter, report: ImportReport | None = None) -> None:
        self.writer = writer
        self.report = report or ImportReport()
        self.batch_duplicate_keys: set[tuple[str, str, str, str]] = set()
        self.existing_duplicate_keys = writer.existing_duplicate_keys()

    @classmethod
    def start(cls, template_path: Path | str, working_path: Path | str) -> "ImportSession":
        writer = WorkbookWriter.create_from_template(template_path, working_path)
        return cls(writer)

    def accept_scan(self, record: Record, force: bool = False) -> AcceptResult:
        result = validate_record(record, self.existing_duplicate_keys)
        blockers = list(result.blockers)
        warnings = list(result.warnings)
        duplicate_key = None
        if _duplicate_key_is_usable(record):
            duplicate_key = record.duplicate_key()
            if duplicate_key in self.batch_duplicate_keys:
                blockers.append("duplicate.in_batch")

        if blockers and not force:
            report_item = ImportReportItem(
                record_id=record.record_id,
                status="blocked",
                row_number=None,
                blockers=blockers,
                warnings=warnings,
            )
            self.report.add(report_item)
            return AcceptResult(
                record_id=record.record_id,
                status="blocked",
                row_number=None,
                blockers=blockers,
                warnings=warnings,
            )

        if duplicate_key is not None:
            self.batch_duplicate_keys.add(duplicate_key)

        row_number = self.writer.write_record(record)
        self.writer.save()
        status = "forced" if blockers else "written"
        report_item = ImportReportItem(
            record_id=record.record_id,
            status=status,
            row_number=row_number,
            blockers=blockers,
            warnings=warnings,
        )
        self.report.add(report_item)
        return AcceptResult(
            record_id=record.record_id,
            status=status,
            row_number=row_number,
            blockers=blockers,
            warnings=warnings,
        )

    def write_report(self, json_path: Path | str, csv_path: Path | str) -> None:
        self.report.write_json(json_path)
        self.report.write_csv(csv_path)

    def close(self) -> None:
        self.writer.close()

    def __enter__(self) -> "ImportSession":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
