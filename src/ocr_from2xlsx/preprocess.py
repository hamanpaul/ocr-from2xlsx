from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from ocr_from2xlsx.capture import PdfPage
from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.form_template import FormTemplate

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAGE_SIZE_TOLERANCE_POINTS = 1.0


def _repo_relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _validate_page_size(page: PdfPage, template: FormTemplate) -> None:
    template_width, template_height = template.page_size_points
    if (
        abs(page.width_points - template_width) > _PAGE_SIZE_TOLERANCE_POINTS
        or abs(page.height_points - template_height) > _PAGE_SIZE_TOLERANCE_POINTS
    ):
        raise ValueError(
            "PDF page size does not match template "
            f"{template.template_id!r}: expected {template.page_size_points}, "
            f"got {(page.width_points, page.height_points)}"
        )


def _output_image_path(page: PdfPage, output_dir: Path) -> Path:
    base_name = f"{page.document_path.stem}-page-{page.page_number:04d}.png"
    candidate = output_dir / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = output_dir / f"{page.document_path.stem}-page-{page.page_number:04d}-{suffix}.png"
        if not candidate.exists():
            return candidate
        suffix += 1


@dataclass(frozen=True, slots=True)
class PreparedPage:
    image_path: Path
    source: SourceInfo
    template_id: str


def prepare_pdf_page(page: PdfPage, output_dir: Path | str, template: FormTemplate) -> PreparedPage:
    output_dir = Path(output_dir)
    _validate_page_size(page, template)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = _output_image_path(page, output_dir)
    with fitz.open(page.document_path) as document:
        pixmap = document.load_page(page.page_number - 1).get_pixmap(dpi=200)
        pixmap.save(image_path)
    return PreparedPage(
        image_path=image_path,
        template_id=template.template_id,
        source=SourceInfo(
            kind="pdf_page",
            document_path=_repo_relative_path(page.document_path),
            page_number=page.page_number,
            preprocessed_image_path=image_path.name,
            template_id=template.template_id,
        ),
    )
