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
        allow_unconfirmed_name: bool = False,
        overwrite_row: int | None = None,
        relaxed: bool = False,
    ) -> AcceptResult:
        result = validate_record(record, self.existing_duplicate_keys)
        if relaxed:
            return self._accept_relaxed(
                record,
                result,
                force=force,
                human_confirmed=human_confirmed,
                overwrite_row=overwrite_row,
            )
        blockers = list(result.blockers)
        warnings = list(result.warnings)
        if (
            not human_confirmed
            and not allow_unconfirmed_name
            and NAME_UNCONFIRMED in record.ocr.warnings
            and NAME_UNCONFIRMED not in blockers
        ):
            blockers.append(NAME_UNCONFIRMED)
        if allow_unconfirmed_name and NAME_UNCONFIRMED in record.ocr.warnings and NAME_UNCONFIRMED not in warnings:
            warnings.append(NAME_UNCONFIRMED)
        duplicate_key = None
        if _duplicate_key_is_usable(record):
            duplicate_key = record.duplicate_key()
            # On an overwrite we are replacing an existing row (often the record's own
            # prior write), so its key already being present is expected — not a dup.
            if overwrite_row is None and duplicate_key in self.batch_duplicate_keys:
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

        row_number = self.writer.write_record(record, row=overwrite_row)
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

    def _accept_relaxed(
        self,
        record: Record,
        result,
        *,
        force: bool,
        human_confirmed: bool,
        overwrite_row: int | None,
    ) -> AcceptResult:
        """Human-reviewed write (the GUI's 確認並寫入 / 強制寫入). The operator has eyeballed
        the record on screen, so the ONLY hard requirement is a name — 確認並寫入 enforces it,
        強制寫入 (``force``) waives even that. Every other validation finding (invalid/blank
        date, missing demographics, duplicates) is demoted to a warning and the record is
        written as-is, with optional fields left blank. A loaded workbook is implied."""
        warnings = list(result.warnings)
        if (not record.name or not record.name.strip()) and not force:
            blockers = ["name.required"]
            self.report.add(
                ImportReportItem(
                    record_id=record.record_id,
                    status="blocked",
                    row_number=None,
                    blockers=blockers,
                    warnings=warnings,
                )
            )
            return AcceptResult(
                record_id=record.record_id,
                status="blocked",
                row_number=None,
                blockers=blockers,
                warnings=warnings,
            )
        # Demote every strict blocker to a warning: the human confirmed the record, so it is
        # recorded for the report but never withheld.
        for blocker in result.blockers:
            if blocker not in warnings:
                warnings.append(blocker)
        duplicate_key = None
        if _duplicate_key_is_usable(record):
            duplicate_key = record.duplicate_key()
            if overwrite_row is None and duplicate_key in self.batch_duplicate_keys:
                if "duplicate.in_batch" not in warnings:
                    warnings.append("duplicate.in_batch")
        row_number = self.writer.write_record(record, row=overwrite_row)
        self.writer.save()
        if human_confirmed:
            record.ocr.warnings = [w for w in record.ocr.warnings if w != NAME_UNCONFIRMED]
            warnings = [w for w in warnings if w != NAME_UNCONFIRMED]
        if duplicate_key is not None:
            self.batch_duplicate_keys.add(duplicate_key)
        self.report.add(
            ImportReportItem(
                record_id=record.record_id,
                status="written",
                row_number=row_number,
                blockers=[],
                warnings=warnings,
            )
        )
        return AcceptResult(
            record_id=record.record_id,
            status="written",
            row_number=row_number,
            blockers=[],
            warnings=warnings,
        )

    def accept_scan_batch(
        self,
        batch: Batch,
        force: bool = False,
        allow_unconfirmed_name: bool = False,
    ) -> list[AcceptResult]:
        results: list[AcceptResult] = []
        for record in batch.records:
            results.append(self.accept_scan(record, force=force, allow_unconfirmed_name=allow_unconfirmed_name))
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
