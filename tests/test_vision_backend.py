from pathlib import Path

from ocr_from2xlsx.domain import SourceInfo
from ocr_from2xlsx.preprocess import PreparedPage
from ocr_from2xlsx.recognition.backend import VisionOcrBackend
from ocr_from2xlsx.recognition.layout import Section


def _page(tmp_path: Path) -> PreparedPage:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x")
    return PreparedPage(image_path=image, source=SourceInfo(document_path="frame.png", page_number=1), template_id="service_record.v1")


def _fake_tiler(image_path, layout):
    return {section.key: f"{section.key}.png" for section in layout}


def _fake_vlm(crop_path: str, section: Section) -> dict:
    if section.key == "identity":
        return {"options": [{"id": "identity.patient", "marked": True}], "values": []}
    if section.key == "gender_nationality_age":
        return {"options": [{"id": "gender.female", "marked": True}], "values": []}
    if section.key == "service_date":
        return {"options": [], "values": [{"id": "service_date", "text": "114.06.25"}]}
    if section.key == "name_mrn":
        return {
            "options": [],
            "values": [
                {"id": "name", "text": "葉心安"},
                {"id": "medical_record_no", "text": "病入6250712919"},
            ],
        }
    return {"options": [], "values": []}


def test_backend_builds_full_record(tmp_path):
    backend = VisionOcrBackend(vlm_fn=_fake_vlm, tiler=_fake_tiler, roster=[])
    record = backend.extract(_page(tmp_path))
    assert record["identity"] == "patient"
    assert record["gender"] == "female"
    assert record["service_date"] == "2025-06-25"
    assert record["name"] == "葉心安"
    assert record["medical_record_no"] == "6250712919"
    assert record["ocr"]["backend"] == "vision-llm"
    assert "name.unconfirmed" in record["ocr"]["warnings"]


def test_backend_snaps_name_to_roster(tmp_path):
    def near_miss_vlm(crop_path, section):
        if section.key == "name_mrn":
            return {"options": [], "values": [{"id": "name", "text": "葉心妄", "confidence": 0.6}]}
        return {"options": [], "values": []}

    backend = VisionOcrBackend(vlm_fn=near_miss_vlm, tiler=_fake_tiler, roster=["葉心安"])
    record = backend.extract(_page(tmp_path))
    assert record["name"] == "葉心安"


def test_backend_output_parses_as_domain_record(tmp_path):
    from ocr_from2xlsx.domain import Record

    backend = VisionOcrBackend(vlm_fn=_fake_vlm, tiler=_fake_tiler, roster=[])
    record = backend.extract(_page(tmp_path))
    record["record_id"] = "scan-0001"
    parsed = Record.from_dict(record)
    assert parsed.identity == "patient"
    assert parsed.gender == "female"
    assert parsed.medical_record_no == "6250712919"
