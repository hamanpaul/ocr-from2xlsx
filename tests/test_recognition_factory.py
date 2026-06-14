from PIL import Image

from ocr_from2xlsx.recognition.backend import VisionOcrBackend
from ocr_from2xlsx.recognition.factory import build_vision_ocr_backend, vision_config_from_env


def test_factory_builds_configured_backend(tmp_path):
    backend = build_vision_ocr_backend(work_dir=tmp_path, model="m", roster=["阿明"])
    assert isinstance(backend, VisionOcrBackend)
    assert backend.model_name == "m"
    assert backend.roster == ["阿明"]


def test_factory_tiler_crops_real_layout(tmp_path):
    image = tmp_path / "frame.png"
    Image.new("RGB", (200, 400), "white").save(image)
    backend = build_vision_ocr_backend(work_dir=tmp_path)
    crops = backend.tiler(str(image), backend.layout)
    assert set(crops) == {section.key for section in backend.layout}


def test_vision_config_from_env_defaults(monkeypatch):
    for var in ("OCR_VLM_HOST", "OCR_VLM_MODEL", "OCR_VLM_ROTATE"):
        monkeypatch.delenv(var, raising=False)
    host, model, rotate = vision_config_from_env()
    assert host.startswith("http")
    assert model == "qwen3-vl:2b"
    assert rotate == 0


def test_vision_config_from_env_overrides(monkeypatch):
    monkeypatch.setenv("OCR_VLM_HOST", "http://box:1234")
    monkeypatch.setenv("OCR_VLM_MODEL", "qwen3-vl:7b")
    monkeypatch.setenv("OCR_VLM_ROTATE", "90")
    host, model, rotate = vision_config_from_env()
    assert (host, model, rotate) == ("http://box:1234", "qwen3-vl:7b", 90)
