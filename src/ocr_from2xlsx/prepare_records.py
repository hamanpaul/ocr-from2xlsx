from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ocr_from2xlsx.capture import PdfDocumentSource
from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.form_template import FormTemplate
from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED
from ocr_from2xlsx.normalizer import normalize_raw_record
from ocr_from2xlsx.ocr_backend import OcrBackend
from ocr_from2xlsx.preprocess import prepare_pdf_page


def _append_unique_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def prepare_records_from_paths(
    input_paths: list[Path | str],
    output_dir: Path | str,
    template: FormTemplate,
    backend: OcrBackend,
    created_at: str | None = None,
) -> Batch:
    output_dir = Path(output_dir)
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    records = []
    sequence = 0
    for input_path in input_paths:
        for page in PdfDocumentSource(input_path).pages():
            sequence += 1
            prepared = prepare_pdf_page(page, output_dir=output_dir, template=template)
            raw_record = backend.extract(prepared)
            # OCR backends (e.g. the PaddleOCR plugin) may not assign a record_id;
            # generate a stable per-page id while preserving any backend-supplied one.
            if not raw_record.get("record_id"):
                raw_record["record_id"] = f"pdf-{sequence:04d}"
            if "source" in raw_record:
                source = raw_record["source"]
                if not isinstance(source, dict):
                    raise ValueError("source must be an object")
            else:
                source = {}
            source.update(
                {
                    "kind": prepared.source.kind,
                    "document_path": prepared.source.document_path,
                    "page_number": prepared.source.page_number,
                    "preprocessed_image_path": prepared.image_path.name,
                    "template_id": prepared.source.template_id,
                }
            )
            raw_record["source"] = source
            record = normalize_raw_record(raw_record)
            if record.name:
                _append_unique_warning(record.ocr.warnings, NAME_UNCONFIRMED)
            records.append(record)
    return Batch(
        source_batch=SourceBatch(
            created_at=created_at,
            source_type="prepare_records",
            template_name=template.template_id,
        ),
        records=records,
    )
