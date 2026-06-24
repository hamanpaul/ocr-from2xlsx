"""Score recognized fields against ground truth for a captured-form fixture.

The pure `score_fields` is the measurement basis for the scan path's "measure-then-decide" rollout:
run a fixture image through the plugin (raw / enhanced / SCAN_DOC_PREPROCESS), feed each resulting
record here, and compare per-field accuracy before adopting any conditioning into the default flow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCORED_FIELDS = ("service_date", "identity", "gender", "name", "medical_record_no")


def _norm(value: object) -> object:
    """Treat empty string and None as the same 'absent' value."""
    return None if value in (None, "") else value


def score_fields(predicted: dict, expected: dict) -> dict:
    per_field = {}
    for key in SCORED_FIELDS:
        if key in expected:
            per_field[key] = _norm(predicted.get(key)) == _norm(expected.get(key))
    correct = sum(1 for value in per_field.values() if value)
    return {"total": len(per_field), "correct": correct, "per_field": per_field}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a recognized record against ground truth.")
    parser.add_argument("--predicted", required=True, help="record JSON (the plugin's record)")
    parser.add_argument("--expected", required=True, help="ground-truth fields JSON")
    args = parser.parse_args(argv)
    predicted = json.loads(Path(args.predicted).read_text(encoding="utf-8"))
    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    metrics = score_fields(predicted.get("record", predicted), expected)
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
