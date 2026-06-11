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

_MD_SPEC = _importlib_util.spec_from_file_location(
    "paddleocr_plugin_mark_detect", _HERE / "mark_detect.py"
)
mark_detect = _importlib_util.module_from_spec(_MD_SPEC)
assert _MD_SPEC and _MD_SPEC.loader
sys.modules.setdefault(_MD_SPEC.name, mark_detect)
_MD_SPEC.loader.exec_module(mark_detect)
sys.modules.setdefault("mark_detect", mark_detect)

_MF_SPEC = _importlib_util.spec_from_file_location(
    "paddleocr_plugin_mark_features", _HERE / "mark_features.py"
)
mark_features = _importlib_util.module_from_spec(_MF_SPEC)
assert _MF_SPEC and _MF_SPEC.loader
sys.modules.setdefault("mark_features", mark_features)
_MF_SPEC.loader.exec_module(mark_features)

_MM_SPEC = _importlib_util.spec_from_file_location(
    "paddleocr_plugin_mark_model", _HERE / "mark_model.py"
)
mark_model = _importlib_util.module_from_spec(_MM_SPEC)
assert _MM_SPEC and _MM_SPEC.loader
sys.modules.setdefault(_MM_SPEC.name, mark_model)
_MM_SPEC.loader.exec_module(mark_model)

_CP_SPEC = _importlib_util.spec_from_file_location(
    "paddleocr_plugin_crop_provider", _HERE / "crop_provider.py"
)
crop_provider = _importlib_util.module_from_spec(_CP_SPEC)
assert _CP_SPEC and _CP_SPEC.loader
sys.modules.setdefault(_CP_SPEC.name, crop_provider)
_CP_SPEC.loader.exec_module(crop_provider)

_NC_SPEC = _importlib_util.spec_from_file_location(
    "paddleocr_plugin_name_crop", _HERE / "name_crop.py"
)
name_crop = _importlib_util.module_from_spec(_NC_SPEC)
assert _NC_SPEC and _NC_SPEC.loader
_NC_SPEC.loader.exec_module(name_crop)

CONTRACT_VERSION = "ocr_plugin.v1"

OcrFn = Callable[[str], list[dict[str, Any]]]
MarkFn = Callable[[str, list[dict[str, Any]]], set[str]]

_CLASSIFIER_LABELS = {
    ("identity", "patient"): "病人",
    ("identity", "family_caregiver"): "親友及照顧者",
    ("identity", "public_other"): "一般民眾及其他",
    ("gender", "female"): "女性",
    ("gender", "male"): "男性",
}


def run(request: dict[str, Any], ocr_fn: OcrFn, mark_fn: MarkFn) -> dict[str, Any]:
    if request.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported contract_version: {request.get('contract_version')!r}; "
            f"expected {CONTRACT_VERSION!r}"
        )
    page = request.get("page") or {}
    image_path = str(page.get("image_path") or "")
    lines = ocr_fn(image_path)
    marked_labels = mark_fn(image_path, lines)
    fields = field_extract.extract_fields(lines, marked_labels)
    raw_text = "\n".join(str(line.get("text") or "") for line in lines)
    record: dict[str, Any] = {
        "service_date": fields["service_date"],
        "identity": fields["identity"],
        "name": fields["name"],
        "medical_record_no": fields["medical_record_no"],
        "gender": fields["gender"],
        "ocr": {
            "backend": "paddleocr",
            "model": "PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec",
            "raw_text": raw_text,
            "warnings": [],
        },
    }
    return {"contract_version": CONTRACT_VERSION, "record": record}


def _existing_path(value: str | os.PathLike[str] | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_file() else None


def classifier_mark_fn(
    image_path: str,
    template_boxes_path: str | os.PathLike[str] | None = None,
    model_path: str | os.PathLike[str] | None = None,
) -> set[str]:
    template_path = Path(template_boxes_path) if template_boxes_path is not None else _HERE / "template_boxes.json"
    model = mark_model.load_model(model_path) if _existing_path(model_path) is not None else None
    labels: set[str] = set()
    for key, region in crop_provider.GeometryCropProvider(template_path).crop(image_path).items():
        if mark_model.is_marked_by_model(region, model):
            label = _CLASSIFIER_LABELS.get(key)
            if label is not None:
                labels.add(label)
    return labels


def _user_runtime_dir() -> Path:
    home = os.environ.get("OCR_FROM2XLSX_HOME")
    return Path(home) if home else Path.home() / ".ocr_from2xlsx"


def _resolve_mark_model_path() -> Path | None:
    # Resolution order: env override, user runtime weights (retraining writes
    # here), then the bundled baseline.
    env_path = _existing_path(os.environ.get("MARK_MODEL_PATH"))
    if env_path is not None:
        return env_path
    runtime_path = _existing_path(_user_runtime_dir() / "mark_model.json")
    if runtime_path is not None:
        return runtime_path
    return _existing_path(_HERE / "mark_model.json")


def _existing_dir(value: str | os.PathLike[str] | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    try:
        if not path.is_dir():
            return None
    except (OSError, PermissionError):
        return None
    try:
        has_any = any(path.iterdir())
    except (OSError, PermissionError):
        return None
    return path if has_any else None


def _resolve_name_rec_dir() -> Path | None:
    # Resolution order mirrors mark weights: env override, user runtime, bundle.
    env_dir = _existing_dir(os.environ.get("NAME_REC_MODEL_DIR"))
    if env_dir is not None:
        return env_dir
    runtime_dir = _existing_dir(_user_runtime_dir() / "name_rec")
    if runtime_dir is not None:
        return runtime_dir
    return _existing_dir(_HERE / "name_rec")


def apply_name_suggestion(record: dict[str, Any], name: str | None) -> None:
    if isinstance(name, str) and name.strip():
        record["name"] = name.strip()


def _paddle_name_rec(crop_path: str, model_dir: str) -> str:
    from paddleocr import TextRecognition

    model = TextRecognition(model_dir=model_dir, model_name="PP-OCRv5_mobile_rec")
    results = model.predict(crop_path)
    if not results:
        return ""
    return str(results[0].get("rec_text") or "")


def recognize_name_safe(crop_path: str, model_dir: str) -> str | None:
    try:
        return _paddle_name_rec(crop_path, model_dir)
    except (ImportError, ModuleNotFoundError, ValueError, OSError, RuntimeError, IndexError, KeyError, TypeError):
        # Treat missing optional PaddleOCR/name-rec dependencies and any
        # unexpected output-shape errors from the optional recognition path as
        # safe fallbacks — do not let them crash the whole plugin.
        return None


def _runtime_mark_fn() -> MarkFn:
    template_path = _existing_path(os.environ.get("MARK_TEMPLATE_BOXES"))
    if template_path is None:
        template_path = _existing_path(_HERE / "template_boxes.json")
    model_path = _resolve_mark_model_path()
    if template_path is None or model_path is None:
        # Without trained weights the per-crop is_marked fallback flags every
        # printed checkbox glyph as marked, so geometry needs weights.
        return mark_detect.detect_marked_labels

    def _classify(image_path: str, _lines: list[dict[str, Any]]) -> set[str]:
        try:
            return classifier_mark_fn(image_path, template_path, model_path)
        except (ValueError, OSError):
            return mark_detect.detect_marked_labels(image_path, _lines)

    return _classify


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
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    _configure_offline_models()
    request = json.loads(sys.stdin.read())
    page = request.get("page") or {}
    image_path = str(page.get("image_path") or "")
    lines = _paddle_ocr_fn(image_path) if image_path else []
    response = run(request, ocr_fn=lambda _path: lines, mark_fn=_runtime_mark_fn())
    if image_path:
        from pathlib import Path as _Path

        crop_out = _Path(image_path).with_name(_Path(image_path).stem + "-name.png")
        saved = name_crop.save_name_crop(image_path, lines, str(crop_out))
        if saved:
            response["record"]["ocr"]["name_crop"] = _Path(saved).name
            name_rec_dir = _resolve_name_rec_dir()
            if name_rec_dir is not None:
                suggestion = recognize_name_safe(str(crop_out), str(name_rec_dir))
                apply_name_suggestion(response["record"], suggestion)
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
