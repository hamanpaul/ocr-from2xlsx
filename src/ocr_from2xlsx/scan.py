from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import fitz

from ocr_from2xlsx.domain import Batch, SourceBatch, SourceInfo
from ocr_from2xlsx.form_template import FormTemplate
from ocr_from2xlsx.name_suggestion import NAME_UNCONFIRMED
from ocr_from2xlsx.normalizer import normalize_raw_record
from ocr_from2xlsx.ocr_backend import OcrBackend
from ocr_from2xlsx.preprocess import PreparedPage


def _append_unique_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def next_output_artifact_path(output_dir: Path | str, filename: str) -> Path:
    output_dir = Path(output_dir)
    template = Path(filename)
    candidate = output_dir / template.name
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = output_dir / f"{template.stem}-{suffix}{template.suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def _copy_image_to_output(image_path: Path, output_dir: Path) -> Path:
    candidate = output_dir / image_path.name
    try:
        if image_path.resolve() == candidate.resolve():
            return candidate
    except OSError:
        pass

    if not candidate.exists():
        shutil.copyfile(image_path, candidate)
        return candidate

    suffix = 2
    while True:
        candidate = output_dir / f"{image_path.stem}-{suffix}{image_path.suffix}"
        if not candidate.exists():
            shutil.copyfile(image_path, candidate)
            return candidate
        suffix += 1


def _copy_preview_to_output(image_path: Path) -> Path:
    if image_path.suffix.lower() == ".png":
        return image_path

    candidate = image_path.with_suffix(".png")
    suffix = 2
    while candidate.exists():
        candidate = image_path.with_name(f"{image_path.stem}-{suffix}.png")
        suffix += 1

    try:
        preview = fitz.Pixmap(str(image_path))
        preview.save(candidate)
    except Exception as exc:
        raise OSError(f"unable to write preview image: {candidate}") from exc
    return candidate


def prepare_records_from_images(
    image_paths: list[Path | str],
    output_dir: Path | str,
    template: FormTemplate,
    backend: OcrBackend,
    created_at: str | None = None,
) -> Batch:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    records = []

    for sequence, image_path in enumerate((Path(path) for path in image_paths), start=1):
        local_image = _copy_image_to_output(image_path, output_dir)
        preview_image = _copy_preview_to_output(local_image)
        prepared = PreparedPage(
            image_path=local_image,
            template_id=template.template_id,
            source=SourceInfo(
                kind="camera_still",
                document_path=image_path.name,
                page_number=sequence,
                image_path=local_image.name,
                preprocessed_image_path=preview_image.name,
                template_id=template.template_id,
            ),
        )
        raw_record = backend.extract(prepared)
        if not raw_record.get("record_id"):
            raw_record["record_id"] = f"scan-{sequence:04d}"
        source = raw_record.get("source")
        if source is None:
            source = {}
        elif not isinstance(source, dict):
            raise ValueError("source must be an object")
        source.update(
            {
                "kind": prepared.source.kind,
                "document_path": prepared.source.document_path,
                "page_number": prepared.source.page_number,
                "image_path": prepared.source.image_path,
                "preprocessed_image_path": prepared.source.preprocessed_image_path,
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
            source_type="scan_records",
            template_name=template.template_id,
        ),
        records=records,
    )
