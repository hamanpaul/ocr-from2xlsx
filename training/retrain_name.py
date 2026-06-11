"""Gate and deploy name rec model candidates with an audit trail."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from training.eval_name_model import evaluate_label_file, paddle_recognize_fn

RUNTIME_SUBDIR = "name_rec"
AUDIT_FILENAME = "name_audit.jsonl"


def runtime_name_rec_dir() -> Path:
    home = os.environ.get("OCR_FROM2XLSX_HOME")
    base = Path(home) if home else Path.home() / ".ocr_from2xlsx"
    return base / RUNTIME_SUBDIR


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def decide_name_candidate(
    current_metrics: Mapping[str, Any],
    candidate_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    current_exact = float(current_metrics.get("exact_match", 0.0))
    current_char = float(current_metrics.get("char_accuracy", 0.0))
    candidate_exact = float(candidate_metrics.get("exact_match", 0.0))
    candidate_char = float(candidate_metrics.get("char_accuracy", 0.0))
    if candidate_char < current_char:
        return {"adopt": False, "reason": "candidate char_accuracy regresses on current"}
    if candidate_exact <= current_exact:
        return {"adopt": False, "reason": "candidate exact_match does not improve on current"}
    return {"adopt": True, "reason": "candidate improves exact_match without char_accuracy regression"}


def deploy_model_dir(candidate_dir: str | Path, target_dir: str | Path) -> None:
    """Atomically replace target model dir: copy to .tmp, swap via rename, drop .old."""
    candidate = Path(candidate_dir)
    target = Path(target_dir)
    temp = target.with_name(target.name + ".tmp")
    old = target.with_name(target.name + ".old")
    for stale in (temp, old):
        if stale.exists():
            shutil.rmtree(stale)
    shutil.copytree(candidate, temp)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.rename(old)
    try:
        temp.rename(target)
    except OSError:
        if old.exists():
            old.rename(target)
        raise
    if old.exists():
        shutil.rmtree(old)


def append_audit(audit_path: str | Path, entry: Mapping[str, Any]) -> None:
    path = Path(audit_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(entry), ensure_ascii=False, sort_keys=True) + "\n")


def run_retrain_name(
    candidate_dir: str | Path,
    holdout_label_file: str | Path,
    *,
    runtime_dir: str | Path | None = None,
    created_at: str | None = None,
    audit_log: str | Path | None = None,
) -> dict[str, Any]:
    target = Path(runtime_dir) if runtime_dir is not None else runtime_name_rec_dir()
    current_dir = target if target.is_dir() and any(target.iterdir()) else None

    candidate_metrics = evaluate_label_file(holdout_label_file, paddle_recognize_fn(candidate_dir))
    current_metrics = evaluate_label_file(
        holdout_label_file,
        paddle_recognize_fn(current_dir if current_dir is not None else None),
    )
    current_metrics["source"] = "model" if current_dir is not None else "pip-baseline"

    decision = decide_name_candidate(current_metrics, candidate_metrics)
    adopt = bool(decision["adopt"])
    if adopt:
        deploy_model_dir(candidate_dir, target)

    entry: dict[str, Any] = {
        "created_at": created_at if created_at is not None else _now_utc(),
        "adopt": adopt,
        "reason": str(decision["reason"]),
        "current_metrics": current_metrics,
        "candidate_metrics": candidate_metrics,
        "model_dir": str(target),
    }
    audit_path = Path(audit_log) if audit_log is not None else target.parent / AUDIT_FILENAME
    append_audit(audit_path, entry)
    return {**entry, "audit_log": str(audit_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate a candidate name rec model and deploy when it improves.")
    parser.add_argument("candidate_dir", help="Exported inference model dir of the candidate")
    parser.add_argument("--holdout", required=True, help="holdout.txt label file (never trained on)")
    parser.add_argument("--runtime-dir", help="Target model dir (default: OCR_FROM2XLSX_HOME or ~/.ocr_from2xlsx/name_rec)")
    parser.add_argument("--audit-log")
    args = parser.parse_args(argv)

    result = run_retrain_name(
        args.candidate_dir,
        args.holdout,
        runtime_dir=args.runtime_dir,
        audit_log=args.audit_log,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["adopt"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
