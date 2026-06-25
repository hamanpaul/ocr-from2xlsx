from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

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
    on_progress: "Callable[[int, int, str], None] | None" = None,
    should_cancel: "Callable[[], bool] | None" = None,
) -> Batch:
    """Prepare normalized records from still images (one Record per image).

    ``on_progress(current, total, name)`` is called as each image begins
    (``current`` is the 1-based index of the image being processed, not a
    completed count), matching ``prepare_records_from_folder``. ``should_cancel``,
    when supplied, is checked before each image; a True return stops early and
    returns the records prepared so far (a partial batch).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    records = []

    paths = [Path(path) for path in image_paths]
    total = len(paths)
    for sequence, image_path in enumerate(paths, start=1):
        if should_cancel is not None and should_cancel():
            break
        if on_progress is not None:
            on_progress(sequence, total, image_path.name)
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


_BATCH_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def prepare_records_from_folder(
    folder: Path | str,
    output_dir: Path | str,
    template: FormTemplate,
    backend: OcrBackend,
    created_at: str | None = None,
    on_progress: "Callable[[int, int, str], None] | None" = None,
    should_cancel: "Callable[[], bool] | None" = None,
) -> Batch:
    """Batch-recognise every image/PDF in ``folder`` into one normalized Batch.

    Routes each file through the existing image / PDF preparers, merges the
    records with unique ids, and reports progress via ``on_progress(current,
    total, name)`` as each file begins (``current`` is the 1-based index of the
    file being processed, not a completed count). The per-record source PNGs the
    preparers emit let the review UI show the original page on the left.
    """
    from ocr_from2xlsx.prepare_records import prepare_records_from_paths

    folder = Path(folder)
    created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
    files = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in _BATCH_IMAGE_SUFFIXES | {".pdf"}
    )
    records: list = []
    total = len(files)
    for index, path in enumerate(files, start=1):
        if should_cancel is not None and should_cancel():
            break
        if on_progress is not None:
            on_progress(index, total, path.name)
        if path.suffix.lower() == ".pdf":
            sub = prepare_records_from_paths([path], output_dir, template, backend, created_at=created_at)
        else:
            sub = prepare_records_from_images([path], output_dir, template, backend, created_at=created_at)
        records.extend(sub.records)
    for index, record in enumerate(records, start=1):
        record.record_id = f"batch-{index:04d}"
    return Batch(
        source_batch=SourceBatch(
            created_at=created_at,
            source_type="batch_folder",
            template_name=template.template_id,
        ),
        records=records,
    )
