"""Holdout evaluation for name rec models: exact-match and character accuracy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Iterable, Sequence

from training.gen_names import read_label_file

RecognizeFn = Callable[[Path], str]


def edit_distance(left: str, right: str) -> int:
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + cost))
        previous = current
    return previous[-1]


def char_accuracy(truth: str, prediction: str) -> float:
    longest = max(len(truth), len(prediction))
    if longest == 0:
        return 1.0
    return 1.0 - edit_distance(truth, prediction) / longest


def score_predictions(pairs: Sequence[tuple[str, str]]) -> dict[str, float | int]:
    if not pairs:
        return {"count": 0, "exact_match": 0.0, "char_accuracy": 0.0}
    exact = sum(1 for truth, prediction in pairs if truth == prediction)
    accuracy = sum(char_accuracy(truth, prediction) for truth, prediction in pairs)
    return {
        "count": len(pairs),
        "exact_match": exact / len(pairs),
        "char_accuracy": accuracy / len(pairs),
    }


def evaluate_label_file(
    label_path: str | Path,
    recognize: RecognizeFn,
) -> dict[str, float | int]:
    label_file = Path(label_path)
    root = label_file.parent
    pairs: list[tuple[str, str]] = []
    for image_rel, truth in read_label_file(label_file):
        pairs.append((truth, recognize(root / image_rel)))
    return score_predictions(pairs)


def paddle_recognize_fn(model_dir: str | Path | None) -> RecognizeFn:
    """Build a recognizer from a model dir (None = pip default PP-OCRv5_mobile_rec baseline)."""
    from paddleocr import TextRecognition

    if model_dir is None:
        model = TextRecognition(model_name="PP-OCRv5_mobile_rec")
    else:
        model = TextRecognition(model_dir=str(model_dir), model_name="PP-OCRv5_mobile_rec")

    def _recognize(image_path: Path) -> str:
        results = model.predict(str(image_path))
        if not results:
            return ""
        return str(results[0].get("rec_text") or "")

    return _recognize


def write_report(metrics: dict[str, float | int], output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = ["# Name rec evaluation", ""]
    for key in sorted(metrics):
        lines.append(f"- {key}: {metrics[key]}")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a name rec model on a label file.")
    parser.add_argument("label_file", help="holdout.txt style label file")
    parser.add_argument("--model-dir", help="inference model dir (omit for pip baseline)")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    metrics = evaluate_label_file(args.label_file, paddle_recognize_fn(args.model_dir))
    write_report(metrics, args.output_dir)
    print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
