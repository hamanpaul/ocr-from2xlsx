from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from ocr_from2xlsx.capture import PdfPage
from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.form_template import FormTemplate


def _repo_relative_path(path: Path) -> str:
    return path.resolve().relative_to(Path.cwd().resolve()).as_posix()


@dataclass(frozen=True, slots=True)
class PreparedPage:
    image_path: Path
    source: SourceInfo
    template_id: str


def prepare_pdf_page(page: PdfPage, output_dir: Path | str, template: FormTemplate) -> PreparedPage:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"{page.document_path.stem}-page-{page.page_number:04d}.png"
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
