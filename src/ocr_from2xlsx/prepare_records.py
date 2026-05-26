from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ocr_from2xlsx.capture import PdfDocumentSource
from ocr_from2xlsx.domain import Batch, SourceBatch
from ocr_from2xlsx.form_template import FormTemplate
from ocr_from2xlsx.normalizer import normalize_raw_record
from ocr_from2xlsx.ocr_backend import OcrBackend
from ocr_from2xlsx.preprocess import prepare_pdf_page


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
    for input_path in input_paths:
        page = PdfDocumentSource(input_path).pages()[0]
        prepared = prepare_pdf_page(page, output_dir=output_dir, template=template)
        raw_record = backend.extract(prepared)
        raw_record.setdefault("source", {})
        raw_record["source"].update(
            {
                "kind": prepared.source.kind,
                "document_path": prepared.source.document_path,
                "page_number": prepared.source.page_number,
                "preprocessed_image_path": prepared.image_path.name,
                "template_id": prepared.source.template_id,
            }
        )
        records.append(normalize_raw_record(raw_record))
    return Batch(
        source_batch=SourceBatch(
            created_at=created_at,
            source_type="prepare_records",
            template_name=template.template_id,
        ),
        records=records,
    )
