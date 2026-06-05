from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")

from plugins.paddleocr.mark_features import FEATURE_NAMES

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_plugin_main_task5", _MODULE_PATH)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)

CONTRACT = "ocr_plugin.v1"


def _write_template(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "template_id": "tiny.v1",
                "boxes": [
                    {"field": "identity", "code": "patient", "box": [0.0, 0.0, 2.0, 2.0]},
                    {"field": "gender", "code": "female", "box": [2.0, 0.0, 4.0, 2.0]},
                    {"field": "identity", "code": "public_other", "box": [0.0, 2.0, 2.0, 4.0]},
                    {"field": "gender", "code": "male", "box": [2.0, 2.0, 4.0, 4.0]},
                    {"field": "service_type", "code": "consult", "box": [4.0, 0.0, 6.0, 2.0]},
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_dark_ratio_model(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "feature_names": list(FEATURE_NAMES),
                "mean": [0.0 for _ in FEATURE_NAMES],
                "std": [1.0 for _ in FEATURE_NAMES],
                "coef": [10.0 if name == "dark_ratio" else 0.0 for name in FEATURE_NAMES],
                "intercept": -5.0,
                "threshold": 0.5,
            }
        ),
        encoding="utf-8",
    )


def test_classifier_mark_fn_maps_selected_geometry_crops_to_field_extract_labels(tmp_path: Path) -> None:
    image_path = tmp_path / "marks.png"
    image = Image.new("L", (6, 4), color=255)
    for x in range(0, 4):
        for y in range(0, 2):
            image.putpixel((x, y), 0)
    for x in range(4, 6):
        for y in range(0, 2):
            image.putpixel((x, y), 0)
    image.save(image_path)
    template_path = tmp_path / "template_boxes.json"
    model_path = tmp_path / "mark_model.json"
    _write_template(template_path)
    _write_dark_ratio_model(model_path)

    labels = plugin_main.classifier_mark_fn(
        str(image_path),
        template_boxes_path=str(template_path),
        model_path=str(model_path),
    )

    assert labels == {"病人", "女性"}


def test_run_remains_injectable_and_consumes_mark_labels() -> None:
    def ocr_fn(_image_path: str) -> list[dict[str, object]]:
        return [
            {
                "text": "服務年/月/日：114.06.25",
                "box": [[0.0, 0.0], [100.0, 0.0], [100.0, 10.0], [0.0, 10.0]],
            },
            {
                "text": "姓名/病歷號",
                "box": [[0.0, 20.0], [100.0, 20.0], [100.0, 30.0], [0.0, 30.0]],
            },
            {
                "text": "王小明 123456",
                "box": [[120.0, 20.0], [220.0, 20.0], [220.0, 30.0], [120.0, 30.0]],
            },
        ]

    response = plugin_main.run(
        {"contract_version": CONTRACT, "page": {"image_path": "scan.png"}},
        ocr_fn=ocr_fn,
        mark_fn=lambda _image_path, _lines: {"親友及照顧者", "男性"},
    )

    assert response["record"]["identity"] == "family_caregiver"
    assert response["record"]["gender"] == "male"


def test_runtime_mark_fn_falls_back_to_ocr_label_detector_when_env_assets_absent(monkeypatch) -> None:
    monkeypatch.delenv("MARK_TEMPLATE_BOXES", raising=False)
    monkeypatch.delenv("MARK_MODEL_PATH", raising=False)
    calls: list[tuple[str, list[dict[str, object]]]] = []

    def fake_detect(image_path: str, lines: list[dict[str, object]]) -> set[str]:
        calls.append((image_path, lines))
        return {"fallback-label"}

    monkeypatch.setattr(plugin_main.mark_detect, "detect_marked_labels", fake_detect)

    mark_fn = plugin_main._runtime_mark_fn()
    lines = [{"text": "女性"}]

    assert mark_fn("scan.png", lines) == {"fallback-label"}
    assert calls == [("scan.png", lines)]


def test_runtime_mark_fn_falls_back_when_geometry_crop_is_incompatible(tmp_path: Path, monkeypatch) -> None:
    template_path = tmp_path / "template_boxes.json"
    template_path.write_text(
        json.dumps(
            {
                "template_id": "tiny.v1",
                "boxes": [
                    {"field": "identity", "code": "patient", "box": [0.0, 0.0, 100.0, 100.0]},
                ],
            }
        ),
        encoding="utf-8",
    )
    image_path = tmp_path / "small.png"
    Image.new("L", (2, 2), color=255).save(image_path)
    monkeypatch.setenv("MARK_TEMPLATE_BOXES", str(template_path))
    monkeypatch.delenv("MARK_MODEL_PATH", raising=False)
    calls: list[tuple[str, list[dict[str, object]]]] = []

    def fake_detect(image_path_arg: str, lines: list[dict[str, object]]) -> set[str]:
        calls.append((image_path_arg, lines))
        return {"fallback-label"}

    monkeypatch.setattr(plugin_main.mark_detect, "detect_marked_labels", fake_detect)
    lines = [{"text": "病人"}]

    assert plugin_main._runtime_mark_fn()(str(image_path), lines) == {"fallback-label"}
    assert calls == [(str(image_path), lines)]
