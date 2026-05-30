"""PaddleOCR plugin entry implementing the ocr_plugin.v1 contract.

Runs under its own bundled venv (paddleocr installed). The pure orchestration `run()` takes an
injectable `ocr_fn` so it can be unit-tested without PaddleOCR. `main()` wires the real engine.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent

import importlib.util as _importlib_util

_FE_SPEC = _importlib_util.spec_from_file_location(
    "paddleocr_plugin_field_extract", _HERE / "field_extract.py"
)
field_extract = _importlib_util.module_from_spec(_FE_SPEC)
assert _FE_SPEC and _FE_SPEC.loader
_FE_SPEC.loader.exec_module(field_extract)

CONTRACT_VERSION = "ocr_plugin.v1"

OcrFn = Callable[[str], list[dict[str, Any]]]


def run(request: dict[str, Any], ocr_fn: OcrFn) -> dict[str, Any]:
    if request.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported contract_version: {request.get('contract_version')!r}; "
            f"expected {CONTRACT_VERSION!r}"
        )
    page = request.get("page") or {}
    image_path = str(page.get("image_path") or "")
    lines = ocr_fn(image_path)
    fields = field_extract.extract_fields(lines)
    raw_text = "\n".join(str(line.get("text") or "") for line in lines)
    record: dict[str, Any] = {
        "service_date": fields["service_date"],
        "name": fields["name"],
        "medical_record_no": fields["medical_record_no"],
        "ocr": {
            "backend": "paddleocr",
            "model": "PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec",
            "raw_text": raw_text,
            "warnings": [],
        },
    }
    return {"contract_version": CONTRACT_VERSION, "record": record}


def _configure_offline_models() -> None:
    # Make PaddleX load models from the bundled cache and never phone home.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    bundled_models = _HERE / "models"
    if bundled_models.is_dir():
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(bundled_models))


def _paddle_ocr_fn(image_path: str) -> list[dict[str, Any]]:
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
    )
    lines: list[dict[str, Any]] = []
    for res in ocr.predict(image_path):
        texts = res.get("rec_texts", [])
        polys = res.get("rec_polys", res.get("dt_polys", []))
        for text, poly in zip(texts, polys):
            box = [[float(pt[0]), float(pt[1])] for pt in poly]
            lines.append({"text": text, "box": box})
    return lines


def main() -> int:
    # Force UTF-8 on the contract pipes regardless of the OS console codepage, so the
    # JSON request/response always round-trips CJK cleanly.
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    _configure_offline_models()
    request = json.loads(sys.stdin.read())
    response = run(request, ocr_fn=_paddle_ocr_fn)
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
