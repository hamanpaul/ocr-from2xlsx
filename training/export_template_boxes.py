"""Export service-record checkbox template boxes for plugin crop providers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ocr_from2xlsx.form_layout import service_record_layout
from training.layout_render import option_mark_box, render_sheet_template, sheet_geometry


def export_template_boxes(
    xlsx_path: str | Path,
    output_path: str | Path,
    sheet_name: str = "服務紀錄表",
) -> dict[str, Any]:
    layout = service_record_layout()
    geom = sheet_geometry(xlsx_path, sheet_name=sheet_name)
    rendered = render_sheet_template(geom)
    boxes = [
        {
            "field": field.key,
            "code": option.code,
            "box": [
                float(coord)
                for coord in option_mark_box(layout, geom, field.key, option.code, rendered=rendered)
            ],
        }
        for field, option in layout.iter_options()
    ]
    payload = {"template_id": layout.template_id, "boxes": boxes}

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export service-record checkbox template boxes as JSON.")
    parser.add_argument("xlsx_path", help="Path to the blank service-record workbook.")
    parser.add_argument("output_path", help="Path to write template_boxes.json.")
    parser.add_argument("--sheet-name", default="服務紀錄表", help="Workbook sheet name to read.")
    args = parser.parse_args(argv)

    export_template_boxes(args.xlsx_path, args.output_path, sheet_name=args.sheet_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
