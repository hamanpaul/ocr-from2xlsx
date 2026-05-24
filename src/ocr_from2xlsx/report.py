from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ImportReportItem:
    record_id: str
    status: str
    row_number: int | None = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportReport:
    items: list[ImportReportItem] = field(default_factory=list)

    def add(self, item: ImportReportItem) -> None:
        self.items.append(item)

    def write_json(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(item) for item in self.items]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def write_csv(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["record_id", "status", "row_number", "blockers", "warnings"])
            for item in self.items:
                row_number = "" if item.row_number is None else item.row_number
                writer.writerow(
                    [
                        item.record_id,
                        item.status,
                        row_number,
                        ";".join(item.blockers),
                        ";".join(item.warnings),
                    ]
                )
