from __future__ import annotations

from pathlib import Path

from ocr_from2xlsx.form_template import service_record_template
from ocr_from2xlsx.scan import prepare_records_from_images


class _FakeBackend:
    def extract(self, prepared) -> dict[str, object]:
        return {
            "service_date": "2025-06-25",
            "identity": "patient",
            "gender": "female",
            "name": None,
            "medical_record_no": None,
            "ocr": {"backend": "fake", "raw_text": "癌症資源中心服務紀錄表", "warnings": []},
        }


class _NamedBackend:
    def extract(self, prepared) -> dict[str, object]:
        return {
            "record_id": "provided-id",
            "service_date": "2025-06-25",
            "identity": "patient",
            "gender": "female",
            "name": "王小明",
            "medical_record_no": None,
            "ocr": {"backend": "fake", "raw_text": "王小明", "warnings": ["existing-warning"]},
        }


def test_prepare_records_from_images_builds_batch_with_image_source(tmp_path: Path) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n")
    out_dir = tmp_path / "out"

    batch = prepare_records_from_images(
        [image],
        out_dir,
        service_record_template(),
        _FakeBackend(),
        created_at="2026-06-13T00:00:00+08:00",
    )

    assert len(batch.records) == 1
    record = batch.records[0]
    assert record.service_date == "2025-06-25"
    assert record.record_id == "scan-0001"
    assert (out_dir / "shot.png").is_file()
    assert record.source.kind == "camera_still"
    assert record.source.preprocessed_image_path == "shot.png"


def test_prepare_records_from_images_preserves_id_and_marks_name_unconfirmed(
    tmp_path: Path,
) -> None:
    image = tmp_path / "named.png"
    image.write_bytes(b"\x89PNG\r\n")

    batch = prepare_records_from_images(
        [image],
        tmp_path / "out",
        service_record_template(),
        _NamedBackend(),
        created_at="2026-06-13T00:00:00+08:00",
    )

    record = batch.records[0]
    assert record.record_id == "provided-id"
    assert record.ocr.warnings == ["existing-warning", "name.unconfirmed"]


def test_prepare_records_from_images_copies_png_preview_for_non_png_source(
    tmp_path: Path,
) -> None:
    image = tmp_path / "shot.bmp"
    image.write_bytes(
        bytes.fromhex(
            "424D3A000000000000003600000028000000010000000100000001001800000000000400"
            "0000130B0000130B00000000000000000000FFFFFF00"
        )
    )
    out_dir = tmp_path / "out"

    batch = prepare_records_from_images(
        [image],
        out_dir,
        service_record_template(),
        _FakeBackend(),
        created_at="2026-06-13T00:00:00+08:00",
    )

    record = batch.records[0]
    assert (out_dir / "shot.bmp").is_file()
    assert (out_dir / "shot.png").is_file()
    assert record.source.image_path == "shot.bmp"
    assert record.source.preprocessed_image_path == "shot.png"


def test_prepare_records_from_images_records_deduped_local_filename(
    tmp_path: Path,
) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n")
    out_dir = tmp_path / "out"
    (out_dir).mkdir()
    (out_dir / "shot.png").write_bytes(b"existing")

    batch = prepare_records_from_images(
        [image],
        out_dir,
        service_record_template(),
        _FakeBackend(),
        created_at="2026-06-13T00:00:00+08:00",
    )

    record = batch.records[0]
    assert (out_dir / "shot-2.png").is_file()
    assert record.source.document_path == "shot.png"
    assert record.source.image_path == "shot-2.png"
    assert record.source.preprocessed_image_path == "shot-2.png"
