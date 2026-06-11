from __future__ import annotations

import json
from pathlib import Path

from training.retrain_name import decide_name_candidate, deploy_model_dir, append_audit, runtime_name_rec_dir
from training.harvest_name_corrections import corrections_to_label_rows


def test_decide_name_candidate_requires_exact_up_and_char_acc_not_worse() -> None:
    current = {"exact_match": 0.50, "char_accuracy": 0.80}

    adopt = decide_name_candidate(current, {"exact_match": 0.60, "char_accuracy": 0.80})
    worse_char = decide_name_candidate(current, {"exact_match": 0.60, "char_accuracy": 0.79})
    no_gain = decide_name_candidate(current, {"exact_match": 0.50, "char_accuracy": 0.90})

    assert adopt["adopt"] is True
    assert worse_char["adopt"] is False and "char_accuracy" in worse_char["reason"]
    assert no_gain["adopt"] is False and "exact_match" in no_gain["reason"]


def test_deploy_model_dir_replaces_atomically_and_keeps_old_on_failure(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "inference.pdmodel").write_text("v2", encoding="utf-8")
    target = tmp_path / "runtime" / "name_rec"
    target.mkdir(parents=True)
    (target / "inference.pdmodel").write_text("v1", encoding="utf-8")

    deploy_model_dir(candidate, target)

    assert (target / "inference.pdmodel").read_text(encoding="utf-8") == "v2"
    assert not (tmp_path / "runtime" / "name_rec.old").exists()


def test_append_audit_writes_jsonl(tmp_path: Path) -> None:
    audit = tmp_path / "name_audit.jsonl"

    append_audit(audit, {"adopt": True, "reason": "test"})
    append_audit(audit, {"adopt": False, "reason": "worse"})

    lines = audit.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["adopt"] for line in lines] == [True, False]


def test_runtime_name_rec_dir_honors_env_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path / "home"))
    assert runtime_name_rec_dir() == tmp_path / "home" / "name_rec"


def test_corrections_to_label_rows_skips_missing_or_invalid_crops(tmp_path: Path) -> None:
    crop = tmp_path / "rec-1-name.png"
    crop.write_bytes(b"png")
    corrections = tmp_path / "name_corrections.jsonl"
    rows = [
        {"field": "name", "final_value": "王小明", "crop_path": str(crop)},
        {"field": "name", "final_value": "陳美玲", "crop_path": str(tmp_path / "missing.png")},
        {"field": "name", "final_value": "", "crop_path": str(crop)},
        {"field": "other", "final_value": "x", "crop_path": str(crop)},
    ]
    corrections.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    label_rows = corrections_to_label_rows(corrections)

    assert label_rows == [(str(crop), "王小明")]
