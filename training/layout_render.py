"""Geometry helpers for training layout rendering."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path
import re
from typing import Optional

from openpyxl import load_workbook
from ocr_from2xlsx.form_layout import FormLayout

_CELL_RE = re.compile(r"^([A-Z]+)([1-9]\d*)$")

EXCEL_DEFAULT_COLUMN_WIDTH = 8.43
EXCEL_DEFAULT_ROW_HEIGHT = 15.0
EXCEL_POINTS_TO_PX = 96.0 / 72.0
EXCEL_COLUMN_WIDTH_TO_PX = 7.0
EXCEL_COLUMN_PADDING_PX = 5.0
TRAINING_SHEET_NAME = "服務紀錄表"
TRAINING_MAX_COL = 6
TRAINING_MAX_ROW = 52


@dataclass(frozen=True, slots=True)
class SheetGeometry:
    col_x: tuple[float, ...]
    row_y: tuple[float, ...]
    width: float
    height: float


def _col_index(letter: str) -> int:
    letter = letter.strip().upper()
    if not letter or not letter.isalpha():
        raise ValueError(f"invalid column letter: {letter!r}")
    value = 0
    for char in letter:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def _split_cell(cell: str) -> tuple[int, int]:
    match = _CELL_RE.fullmatch(cell.strip().upper())
    if not match:
        raise ValueError(f"invalid cell reference: {cell!r}")
    col_letter, row_text = match.groups()
    return _col_index(col_letter), int(row_text)


def _col_px(width: float | None) -> float:
    source = EXCEL_DEFAULT_COLUMN_WIDTH if width is None else float(width)
    return max(1.0, source * EXCEL_COLUMN_WIDTH_TO_PX + EXCEL_COLUMN_PADDING_PX)


def _row_px(height: float | None) -> float:
    source = EXCEL_DEFAULT_ROW_HEIGHT if height is None else float(height)
    return max(1.0, source * EXCEL_POINTS_TO_PX)


def sheet_geometry(xlsx_path: Path | str) -> SheetGeometry:
    wb = load_workbook(filename=str(xlsx_path), data_only=True)
    ws = wb[TRAINING_SHEET_NAME]

    col_x = [0.0]
    for col_num in range(1, TRAINING_MAX_COL + 1):
        letter = chr(ord("A") + col_num - 1)
        dim = ws.column_dimensions.get(letter)
        col_x.append(col_x[-1] + _col_px(None if dim is None else dim.width))

    row_y = [0.0]
    for row_num in range(1, TRAINING_MAX_ROW + 1):
        dim = ws.row_dimensions.get(row_num)
        row_y.append(row_y[-1] + _row_px(None if dim is None else dim.height))

    return SheetGeometry(col_x=tuple(col_x), row_y=tuple(row_y), width=col_x[-1], height=row_y[-1])


def cell_box(cell: str, geom: SheetGeometry) -> tuple[float, float, float, float]:
    col, row = _split_cell(cell)
    if not (1 <= col <= TRAINING_MAX_COL and 1 <= row <= TRAINING_MAX_ROW):
        raise ValueError(f"cell out of bounds: {cell!r}")
    return geom.col_x[col - 1], geom.row_y[row - 1], geom.col_x[col], geom.row_y[row]


def _pixel_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    left = floor(x0)
    top = floor(y0)
    right = max(left, ceil(x1) - 1)
    bottom = max(top, ceil(y1) - 1)
    return left, top, right, bottom


def draw_base_form(layout: FormLayout, geom: SheetGeometry, font_path: Optional[str] = None):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (max(1, ceil(geom.width)), max(1, ceil(geom.height))), color=255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 12) if font_path else ImageFont.load_default()
    drawn_cells: set[str] = set()

    for _, option in layout.iter_options():
        left, top, right, bottom = _pixel_box(cell_box(option.cell, geom))
        if option.cell not in drawn_cells:
            draw.rectangle((left, top, right, bottom), outline=0, width=1)
            drawn_cells.add(option.cell)
        if option.label:
            draw.text((left + 2, top + 1), option.label, fill=0, font=font)

    return image
