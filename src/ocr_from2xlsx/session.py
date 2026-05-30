from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ocr_from2xlsx.domain import Batch, Record
from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED
from ocr_from2xlsx.report import ImportReport, ImportReportItem
from ocr_from2xlsx.validation import validate_record
from ocr_from2xlsx.workbook import WorkbookWriter

_NON_WRITABLE_BLOCKERS = {
    "service_date.invalid",
    "identity.invalid",
    "gender.invalid",
    NAME_UNCONFIRMED,
}
_NON_WRITABLE_PREFIXES = ("service.",)


def _has_non_writable_blockers(blockers: list[str]) -> bool:
    for blocker in blockers:
        if blocker in _NON_WRITABLE_BLOCKERS:
            return True
        if blocker.startswith(_NON_WRITABLE_PREFIXES):
            return True
    return False


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

    def accept_scan(
        self,
        record: Record,
        force: bool = False,
        human_confirmed: bool = False,
    ) -> AcceptResult:
        result = validate_record(record, self.existing_duplicate_keys)
        blockers = list(result.blockers)
        warnings = list(result.warnings)
        if not human_confirmed and NAME_UNCONFIRMED in record.ocr.warnings and NAME_UNCONFIRMED not in blockers:
            blockers.append(NAME_UNCONFIRMED)
        duplicate_key = None
        if _duplicate_key_is_usable(record):
            duplicate_key = record.duplicate_key()
            if duplicate_key in self.batch_duplicate_keys:
                blockers.append("duplicate.in_batch")

        if blockers:
            if force and _has_non_writable_blockers(blockers):
                if "force.non_writable" not in blockers:
                    blockers.append("force.non_writable")
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
            if not force:
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

        row_number = self.writer.write_record(record)
        self.writer.save()
        if human_confirmed:
            record.ocr.warnings = [warning for warning in record.ocr.warnings if warning != NAME_UNCONFIRMED]
            warnings = [warning for warning in warnings if warning != NAME_UNCONFIRMED]
        if duplicate_key is not None:
            self.batch_duplicate_keys.add(duplicate_key)
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

    def accept_scan_batch(self, batch: Batch, force: bool = False) -> list[AcceptResult]:
        results: list[AcceptResult] = []
        for record in batch.records:
            results.append(self.accept_scan(record, force=force))
        return results

    def write_report(self, json_path: Path | str, csv_path: Path | str) -> None:
        self.report.write_json(json_path)
        self.report.write_csv(csv_path)

    def close(self) -> None:
        self.writer.close()

    def __enter__(self) -> "ImportSession":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
