from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_plugin_main", _MODULE_PATH)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)

run = plugin_main.run

CONTRACT = "ocr_plugin.v1"


def _fake_ocr_fn(image_path):
    # Returns OCR lines like field_extract expects; ignores the image.
    def line(text, x=0.0, y=0.0):
        return {"text": text, "box": [[x, y], [x + 50, y], [x + 50, y + 10], [x, y + 10]]}

    return [
        line("癌症資源中心服務紀錄表", y=0),
        line("服務年/月/日：114.06.25", y=20),
        line("姓名/病歷號", x=0, y=50),
        line("葉心安", x=120, y=50),
        line("6250712919", x=260, y=50),
        line("病人", x=10, y=80),
        line("女性", x=10, y=110),
    ]


def _fake_mark_fn(image_path, lines):
    return {"病人", "女性"}


def test_run_builds_contract_response_with_extracted_fields():
    request = {
        "contract_version": CONTRACT,
        "template_id": "service_record.v1",
        "page": {"image_path": "ignored.png", "document_name": "scan.pdf", "page_number": 1},
    }

    response = run(request, ocr_fn=_fake_ocr_fn, mark_fn=_fake_mark_fn)

    assert response["contract_version"] == CONTRACT
    record = response["record"]
    assert record["service_date"] == "2025-06-25"  # ROC 114 + 1911 = 2025
    assert record["identity"] == "patient"
    assert record["gender"] == "female"
    assert record["name"] == "葉心安"
    assert record["medical_record_no"] == "6250712919"
    assert record["ocr"]["backend"] == "paddleocr"
    assert isinstance(record["ocr"]["raw_text"], str)
    assert "癌症資源中心服務紀錄表" in record["ocr"]["raw_text"]


def test_run_rejects_wrong_contract_version():
    request = {"contract_version": "nope", "page": {"image_path": "x.png"}}
    try:
        run(request, ocr_fn=_fake_ocr_fn, mark_fn=_fake_mark_fn)
    except ValueError as exc:
        assert "contract_version" in str(exc)
    else:
        raise AssertionError("expected ValueError")
