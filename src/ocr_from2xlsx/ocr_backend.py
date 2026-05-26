from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ocr_from2xlsx.preprocess import PreparedPage


class OcrBackend(Protocol):
    def extract(self, page: PreparedPage) -> dict[str, object]:
        ...


@dataclass(slots=True)
class FixtureOcrBackend:
    pages: dict[tuple[str, int], dict[str, object]]

    @classmethod
    def from_path(cls, path: Path | str) -> "FixtureOcrBackend":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        pages = {
            (item["document_name"], item["page_number"]): item["record"]
            for item in payload["pages"]
        }
        return cls(pages=pages)

    def extract(self, page: PreparedPage) -> dict[str, object]:
        key = (Path(page.source.document_path or "").name, page.source.page_number or 0)
        record = dict(self.pages[key])
        ocr = dict(record.get("ocr", {}))
        ocr.setdefault("backend", "fixture")
        ocr.setdefault("model", "manual-gold")
        record["ocr"] = ocr
        return record
