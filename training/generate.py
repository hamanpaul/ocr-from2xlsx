"""Generate synthetic service-record images and workflow-aligned answer keys."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ocr_from2xlsx.form_layout import FormLayout, service_record_layout

from training.answer_key import build_answer_batch, selection_to_record
from training.handwriting import draw_mark, draw_text, list_handwriting_fonts
from training.layout_render import cell_box, draw_base_form, sheet_geometry
from training.sampler import choice_fields, generate_until_coverage

_NAMES = ("王小明", "陳美玲", "林志偉", "張雅婷", "李國華", "黃淑芬", "葉心安")
_PREFERRED_SYSTEM_FONT_NAMES = (
    "kaiu.ttf",
    "msjh.ttc",
    "mingliu.ttc",
    "DFKai-SB.ttf",
    "Arial Unicode MS.ttf",
)


def _text_values(rng: random.Random) -> dict[str, str]:
    roc_year = rng.randint(110, 115)
    return {
        "name": rng.choice(_NAMES),
        "medical_record_no": str(rng.randint(1_000_000_000, 9_999_999_999)),
        "service_date": f"{roc_year + 1911:04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
    }


def _system_font_candidates() -> Iterable[Path]:
    fonts_dir = Path(r"C:\Windows\Fonts")
    seen: set[Path] = set()

    for name in _PREFERRED_SYSTEM_FONT_NAMES:
        candidate = fonts_dir / name
        if candidate.is_file():
            seen.add(candidate)
            yield candidate

    if not fonts_dir.is_dir():
        return

    for candidate in sorted(fonts_dir.glob("*.*")):
        if candidate.suffix.lower() not in {".ttf", ".ttc"} or candidate in seen:
            continue
        yield candidate


def _select_text_font() -> str:
    from PIL import ImageFont

    fonts_dir = Path(__file__).resolve().parent / "fonts"
    for font_path in (*list_handwriting_fonts(fonts_dir), *_system_font_candidates()):
        try:
            ImageFont.truetype(str(font_path), size=24)
        except OSError:
            continue
        else:
            return str(font_path)
    raise RuntimeError("no usable training text font found in training/fonts or system fonts")


def _apply_augmentation(image, rng: random.Random):
    from PIL import ImageFilter

    rotated = image.rotate(
        rng.uniform(-1.2, 1.2),
        resample=image.Resampling.BICUBIC,
        expand=False,
        fillcolor=255,
    )
    blurred = rotated.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.0, 0.6)))

    pixels = blurred.load()
    speckles = max(1, (blurred.width * blurred.height) // 1_500)
    for _ in range(speckles):
        x = rng.randrange(blurred.width)
        y = rng.randrange(blurred.height)
        pixels[x, y] = max(0, pixels[x, y] - rng.randint(12, 48))
    return blurred


def _mark_selected_options(image, layout: FormLayout, geom, selection: dict[str, list[str]], rng: random.Random) -> None:
    for field_key, codes in selection.items():
        options_by_code = layout.options_by_code(field_key)
        for code in codes:
            draw_mark(image, cell_box(options_by_code[code].cell, geom), rng)


def _draw_text_fields(
    image,
    layout: FormLayout,
    geom,
    text_values: dict[str, str],
    text_font: str,
    rng: random.Random,
) -> None:
    for field in layout.iter_fields():
        if field.kind == "text" and field.key in text_values:
            draw_text(image, cell_box(field.anchor_cell, geom), text_values[field.key], text_font, rng)


def generate(
    xlsx_path: str,
    out_dir: str,
    *,
    min_per_option: int = 5,
    seed: int = 0,
    augment: bool = False,
) -> dict[str, Any]:
    layout = service_record_layout()
    geom = sheet_geometry(xlsx_path)
    rng = random.Random(seed)
    text_font = _select_text_font()
    out = Path(out_dir)
    images_dir = out / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    selections = generate_until_coverage(choice_fields(layout), rng, min_per_option=min_per_option)
    records_with_images: list[tuple[Any, str]] = []

    for index, selection in enumerate(selections, start=1):
        image = draw_base_form(layout, geom, font_path=text_font)
        _mark_selected_options(image, layout, geom, selection, rng)

        text_values = _text_values(rng)
        _draw_text_fields(image, layout, geom, text_values, text_font, rng)
        if augment:
            image = _apply_augmentation(image, rng)

        record_id = f"train-{index:04d}"
        relative_image = f"images/{record_id}.png"
        image.save(out / relative_image)
        records_with_images.append((selection_to_record(layout, record_id, selection, text_values), relative_image))

    batch = build_answer_batch(
        records_with_images,
        datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    answers_path = out / "answers.json"
    answers_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"images": len(records_with_images), "answers": str(answers_path)}


def main() -> None:
    parser = argparse.ArgumentParser(prog="training.generate")
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-per-option", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--augment", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            generate(
                args.xlsx,
                args.out,
                min_per_option=args.min_per_option,
                seed=args.seed,
                augment=args.augment,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
