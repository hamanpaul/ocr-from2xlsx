from pathlib import Path
from types import SimpleNamespace

import ocr_from2xlsx.scan as scan
from ocr_from2xlsx.domain import Batch, SourceBatch


def _fake_batch(record_id: str) -> Batch:
    return Batch(
        source_batch=SourceBatch(created_at="t", source_type="x", template_name="service_record.v1"),
        records=[SimpleNamespace(record_id=record_id)],
    )


def test_prepare_records_from_folder_routes_merges_and_reports_progress(tmp_path, monkeypatch):
    folder = tmp_path / "in"
    folder.mkdir()
    for name in ("a.png", "b.jpg", "c.pdf", "skip.txt"):
        (folder / name).write_bytes(b"x")

    image_calls: list[list[str]] = []
    pdf_calls: list[list[str]] = []
    monkeypatch.setattr(
        scan,
        "prepare_records_from_images",
        lambda paths, *a, **k: image_calls.append([Path(p).name for p in paths]) or _fake_batch("scan-0001"),
    )
    monkeypatch.setattr(
        "ocr_from2xlsx.prepare_records.prepare_records_from_paths",
        lambda paths, *a, **k: pdf_calls.append([Path(p).name for p in paths]) or _fake_batch("pdf-0001"),
    )

    progress: list[tuple[int, int, str]] = []
    template = SimpleNamespace(template_id="service_record.v1")
    batch = scan.prepare_records_from_folder(
        folder,
        tmp_path / "out",
        template,
        backend=object(),
        on_progress=lambda done, total, name: progress.append((done, total, name)),
    )

    # .txt ignored; images routed to from_images, pdf to from_paths; ids made unique
    assert image_calls == [["a.png"], ["b.jpg"]]
    assert pdf_calls == [["c.pdf"]]
    assert [r.record_id for r in batch.records] == ["batch-0001", "batch-0002", "batch-0003"]
    assert batch.source_batch.source_type == "batch_folder"
    assert len(progress) == 3 and progress[-1][1] == 3


def test_prepare_records_from_folder_empty_folder(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    template = SimpleNamespace(template_id="service_record.v1")
    batch = scan.prepare_records_from_folder(folder, tmp_path / "out", template, backend=object())
    assert batch.records == []
