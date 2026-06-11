# Handwritten Name Rec Finetune Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A repeatable CPU finetune engine that produces a name-only PP-OCRv5_mobile_rec model, gates it on a fixed holdout, deploys it atomically, and lets the plugin use it for handwritten name crops.

**Architecture:** Thin command wrappers around the official PaddleOCR trainer (vendored at a pinned tag, gitignored). Synthetic name corpora are generated with the repo's existing handwriting fonts/augmentation into PaddleOCR rec label format. A gate (`exact-match up AND char accuracy not worse`) controls atomic deployment to the user runtime dir; the plugin resolves the model dir env → runtime → bundle and falls back to current behavior when absent or failing.

**Tech Stack:** Python 3.12, `.venv-paddle` (paddlepaddle 3.0 CPU + paddleocr pip) for training/inference, `.venv` for pure tests, PIL for rendering, official PaddleOCR repo for `tools/train.py` / `tools/export_model.py`.

**Branch:** `wt/bootstrap-ocr-design/name-rec-training` (already created). Spec: `docs/superpowers/specs/2026-06-11-name-rec-finetune-design.md`. OpenSpec: `openspec/changes/add-name-rec-finetune/`.

**Conventions you must follow:**
- Pure tests run with `.venv\Scripts\python -m pytest <file> -q -p no:cacheprovider --basetemp=output/pytest-tmp` (the basetemp flag works around a sandbox temp-dir permission issue).
- TDD: write the failing test, see it fail, implement, see it pass, commit.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- `training/vendor/` and `training/out/` are gitignored (Task 1 adds the vendor ignore).

---

### Task 1: PaddleOCR trainer fetch script

**Files:**
- Create: `training/fetch_paddleocr_train.py`
- Modify: `.gitignore` (add `training/vendor/`)
- Test: `tests/test_fetch_paddleocr_train.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

from training.fetch_paddleocr_train import (
    DEFAULT_CONFIG_RELPATH,
    DEFAULT_TAG,
    DEFAULT_WEIGHTS_URL,
    build_clone_command,
    vendor_paths,
)


def test_vendor_paths_are_rooted_under_training_vendor() -> None:
    paths = vendor_paths(Path("training"))

    assert paths["repo"] == Path("training") / "vendor" / "PaddleOCR"
    assert paths["weights"] == Path("training") / "vendor" / "PP-OCRv5_mobile_rec_pretrained.pdparams"


def test_build_clone_command_pins_tag_and_is_shallow() -> None:
    command = build_clone_command(Path("training/vendor/PaddleOCR"), tag="v3.1.0")

    assert command[:3] == ["git", "clone", "--depth"]
    assert "--branch" in command and "v3.1.0" in command
    assert command[-1].endswith("PaddleOCR")


def test_default_constants_are_concrete() -> None:
    assert DEFAULT_TAG.startswith("v")
    assert DEFAULT_WEIGHTS_URL.startswith("https://")
    assert DEFAULT_CONFIG_RELPATH.endswith(".yml")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_fetch_paddleocr_train.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError: No module named 'training.fetch_paddleocr_train'`

- [ ] **Step 3: Write the implementation**

```python
"""Fetch the official PaddleOCR training repo (pinned tag) and pretrained rec weights."""
from __future__ import annotations

import argparse
import subprocess
import urllib.request
from pathlib import Path

DEFAULT_TAG = "v3.1.0"
DEFAULT_REPO_URL = "https://github.com/PaddlePaddle/PaddleOCR.git"
DEFAULT_WEIGHTS_URL = (
    "https://paddleocr.bj.bcebos.com/PP-OCRv5/chinese/PP-OCRv5_mobile_rec_pretrained.pdparams"
)
DEFAULT_CONFIG_RELPATH = "configs/rec/PP-OCRv5/PP-OCRv5_mobile_rec.yml"


def vendor_paths(training_dir: str | Path) -> dict[str, Path]:
    vendor = Path(training_dir) / "vendor"
    return {
        "vendor": vendor,
        "repo": vendor / "PaddleOCR",
        "weights": vendor / "PP-OCRv5_mobile_rec_pretrained.pdparams",
    }


def build_clone_command(repo_dir: Path, *, tag: str = DEFAULT_TAG, repo_url: str = DEFAULT_REPO_URL) -> list[str]:
    return ["git", "clone", "--depth", "1", "--branch", tag, repo_url, str(repo_dir)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch PaddleOCR trainer repo and pretrained rec weights.")
    parser.add_argument("--tag", default=DEFAULT_TAG, help="PaddleOCR repo tag to pin")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--weights-url", default=DEFAULT_WEIGHTS_URL)
    parser.add_argument("--training-dir", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args(argv)

    paths = vendor_paths(args.training_dir)
    paths["vendor"].mkdir(parents=True, exist_ok=True)
    if not paths["repo"].exists():
        subprocess.run(build_clone_command(paths["repo"], tag=args.tag, repo_url=args.repo_url), check=True)
    else:
        print(f"repo already present: {paths['repo']}")
    if not paths["weights"].exists():
        print(f"downloading {args.weights_url}")
        urllib.request.urlretrieve(args.weights_url, paths["weights"])
    else:
        print(f"weights already present: {paths['weights']}")
    config = paths["repo"] / DEFAULT_CONFIG_RELPATH
    print(f"config: {config} exists={config.exists()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

Also append to `.gitignore`:

```
training/vendor/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_fetch_paddleocr_train.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add training/fetch_paddleocr_train.py tests/test_fetch_paddleocr_train.py .gitignore
git commit -m "feat: add pinned PaddleOCR trainer fetch script"
```

---

### Task 2: Name corpus generator (pure parts)

**Files:**
- Create: `training/gen_names.py`
- Test: `tests/test_gen_names.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import random
from pathlib import Path

import pytest

from training.gen_names import (
    GIVEN_CHARS,
    SURNAMES,
    filter_names_to_dict,
    sample_names,
    split_batches,
    write_label_file,
    read_label_file,
)


def test_pools_are_reasonably_sized_and_unique() -> None:
    assert len(SURNAMES) >= 80
    assert len(set(SURNAMES)) == len(SURNAMES)
    assert len(GIVEN_CHARS) >= 300
    assert len(set(GIVEN_CHARS)) == len(GIVEN_CHARS)


def test_sample_names_is_seed_reproducible_and_unique() -> None:
    first = sample_names(random.Random(7), 200)
    second = sample_names(random.Random(7), 200)

    assert first == second
    assert len(set(first)) == len(first)
    assert all(2 <= len(name) <= 4 for name in first)
    assert all(name[0] in SURNAMES for name in first)


def test_split_batches_are_disjoint_and_cover_all() -> None:
    names = sample_names(random.Random(0), 100)
    train, validation, holdout = split_batches(names, validation_fraction=0.1, holdout_fraction=0.1)

    assert len(train) + len(validation) + len(holdout) == len(names)
    assert set(train).isdisjoint(validation)
    assert set(train).isdisjoint(holdout)
    assert set(validation).isdisjoint(holdout)
    assert len(holdout) == 10


def test_filter_names_to_dict_drops_oov_names() -> None:
    kept = filter_names_to_dict(["王明", "王珺"], dict_chars={"王", "明"})

    assert kept == ["王明"]


def test_label_file_roundtrip_and_path_safety(tmp_path: Path) -> None:
    rows = [("images/name-0001.png", "王小明"), ("images/name-0002.png", "陳美玲")]
    label_path = tmp_path / "train.txt"

    write_label_file(label_path, rows)

    assert read_label_file(label_path) == rows
    with pytest.raises(ValueError, match="relative"):
        write_label_file(label_path, [("../escape.png", "王小明")])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_gen_names.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError: No module named 'training.gen_names'`

- [ ] **Step 3: Write the implementation (pure parts)**

```python
"""Synthetic handwritten Chinese name corpus generator (PaddleOCR rec label format)."""
from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Iterable, Sequence

SURNAMES = tuple(
    "陳林黃張李王吳劉蔡楊許鄭謝郭洪曾邱廖賴徐周葉蘇莊江呂何羅高蕭潘朱簡鍾彭游詹胡施沈余盧梁趙顏"
    "柯翁魏孫戴范方宋鄧杜傅侯曹溫薛丁馬蔣唐卓藍馮姚石董紀歐程連古汪湯姜田康鄒白塗尤巫韓龔嚴袁鐘"
    "黎金阮陸倪夏童邵柳錢"
)

GIVEN_CHARS = tuple(
    "明華志偉雅婷怡君淑芬美玲俊宏家豪建宏冠宇宗翰哲瑋柏翰彥廷承恩宥廷品妤詠晴子涵思妤心安宜蓁"
    "佳穎欣怡雅雯郁婷孟儒崇恩政勳文雄金龍秀英麗珠玉蘭素珍春嬌阿寶坤山進財福來添丁萬得水木火土"
    "國強建國中正治平安康健勇敢誠信義禮智仁愛和平喜樂恩慈良善真美聖潔光輝榮耀偉大尊貴富強盛旺"
    "發達興隆昌泰祥瑞吉慶豐收滿堂紅梅蘭竹菊松柏楓桂荷蓮薇芳菲翠綠青藍紫白黑金銀珠寶玉石琴棋書"
    "畫詩詞歌賦琪琳瑜珊珮瑩瓊瑤璇璟曉晨旭日月星辰宇宙乾坤山川河海江湖風雲雷電雨雪霜露虹霞煙波"
    "濤浪潮汐泉溪潭瀑些奇妙玄真元亨利貞天地人和春夏秋冬東南西北中央左右前後上下高低長短大小多"
    "少新舊好妮娜莉莎蒂芙妃姿婉柔媛婕妶嫻淑慧穎聰敏捷靈巧妙慧黠睿哲彬彪虎豹龍鳳麟龜鶴燕鶯鵬雁"
    "鴻雀鵑凰羽毛皮革骨肉血氣神魂魄心肝脾肺腎腦髓筋脈絡膚髮膽識量度衡規矩準繩墨硯筆紙簡冊卷軸"
)


def sample_names(rng: random.Random, count: int) -> list[str]:
    """Sample unique 2-4 char names: 1-char surname + 1-3 given chars (mostly 2)."""
    names: list[str] = []
    seen: set[str] = set()
    while len(names) < count:
        surname = rng.choice(SURNAMES)
        given_len = rng.choices([1, 2, 3], weights=[15, 80, 5])[0]
        given = "".join(rng.choice(GIVEN_CHARS) for _ in range(given_len))
        name = surname + given
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def split_batches(
    names: Sequence[str],
    *,
    validation_fraction: float = 0.1,
    holdout_fraction: float = 0.1,
) -> tuple[list[str], list[str], list[str]]:
    """Slice an already-unique name list into disjoint train/validation/holdout."""
    total = len(names)
    holdout_count = int(total * holdout_fraction)
    validation_count = int(total * validation_fraction)
    holdout = list(names[:holdout_count])
    validation = list(names[holdout_count : holdout_count + validation_count])
    train = list(names[holdout_count + validation_count :])
    return train, validation, holdout


def filter_names_to_dict(names: Iterable[str], dict_chars: set[str]) -> list[str]:
    """Drop names containing characters absent from the rec model dictionary."""
    return [name for name in names if all(char in dict_chars for char in name)]


def load_dict_chars(dict_path: str | Path) -> set[str]:
    chars: set[str] = set()
    for line in Path(dict_path).read_text(encoding="utf-8").splitlines():
        if line:
            chars.add(line.strip("\n"))
    return chars


def _validate_relative(path_text: str) -> None:
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"label image path must be relative without ..: {path_text}")


def write_label_file(label_path: str | Path, rows: Iterable[tuple[str, str]]) -> None:
    lines = []
    for image_rel, label in rows:
        _validate_relative(image_rel)
        if "\t" in label or "\n" in label:
            raise ValueError("label must not contain tab or newline")
        lines.append(f"{image_rel}\t{label}")
    path = Path(label_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_label_file(label_path: str | Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in Path(label_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        image_rel, _, label = line.partition("\t")
        _validate_relative(image_rel)
        rows.append((image_rel, label))
    return rows
```

(The rendering CLI half of this module is Task 3; do not add it yet.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_gen_names.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add training/gen_names.py tests/test_gen_names.py
git commit -m "feat: add name corpus sampling and rec label IO"
```

---

### Task 3: Name corpus rendering CLI

**Files:**
- Modify: `training/gen_names.py` (append rendering + main)
- Test: `tests/test_gen_names_render.py` (PIL-marked, runs in CI via Pillow in `.venv`)

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import random
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from training.gen_names import read_label_file, render_corpus


def test_render_corpus_writes_images_and_three_disjoint_label_files(tmp_path: Path) -> None:
    summary = render_corpus(
        tmp_path,
        rng=random.Random(0),
        total=12,
        validation_fraction=0.25,
        holdout_fraction=0.25,
        augment=False,
    )

    train = read_label_file(tmp_path / "train.txt")
    validation = read_label_file(tmp_path / "validation.txt")
    holdout = read_label_file(tmp_path / "holdout.txt")

    assert summary == {"train": 6, "validation": 3, "holdout": 3}
    labels = [label for _, label in train + validation + holdout]
    assert len(set(labels)) == 12
    for image_rel, _ in train + validation + holdout:
        assert (tmp_path / image_rel).is_file()


def test_render_corpus_image_is_grayscale_with_ink(tmp_path: Path) -> None:
    from PIL import Image

    render_corpus(tmp_path, rng=random.Random(1), total=2, validation_fraction=0.0, holdout_fraction=0.5, augment=False)
    image_rel, _ = read_label_file(tmp_path / "train.txt")[0]
    with Image.open(tmp_path / image_rel) as image:
        assert image.mode == "L"
        assert image.height >= 32 and image.width >= image.height
        pixel_iter = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        assert min(pixel_iter) < 128  # some ink present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_gen_names_render.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ImportError: cannot import name 'render_corpus'`

- [ ] **Step 3: Append the rendering implementation to `training/gen_names.py`**

```python
CANVAS_SIZE = (320, 64)  # width, height; matches rec input aspect comfortably


def _handwriting_font_paths() -> list[Path]:
    from training.generate import _resolve_text_font  # reuse font fallback logic indirectly
    from training.handwriting import list_handwriting_fonts

    fonts_dir = Path(__file__).resolve().parent / "fonts"
    fonts = [Path(p) for p in list_handwriting_fonts(fonts_dir)]
    if fonts:
        return fonts
    # System CJK fallback mirrors training.generate behaviour.
    windir = Path("C:/Windows/Fonts")
    for name in ("kaiu.ttf", "msjh.ttc", "mingliu.ttc"):
        candidate = windir / name
        if candidate.is_file():
            return [candidate]
    raise RuntimeError("no usable handwriting/CJK font found; run training/fetch_fonts.py")


def _render_name(name: str, font_path: Path, rng: random.Random, *, augment: bool):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", CANVAS_SIZE, color=255)
    draw = ImageDraw.Draw(image)
    size = rng.randint(34, 46)
    font = ImageFont.truetype(str(font_path), size=size)
    left, top, right, bottom = draw.textbbox((0, 0), name, font=font)
    x = rng.randint(4, max(5, CANVAS_SIZE[0] - (right - left) - 8)) - left
    y = (CANVAS_SIZE[1] - (bottom - top)) // 2 - top + rng.randint(-3, 3)
    draw.text((x, y), name, font=font, fill=rng.randint(0, 60))
    if augment:
        from training.generate import _apply_augmentation

        image = _apply_augmentation(image, rng)
    return image


def render_corpus(
    out_dir: str | Path,
    *,
    rng: random.Random,
    total: int,
    validation_fraction: float = 0.1,
    holdout_fraction: float = 0.1,
    augment: bool = True,
    dict_path: str | Path | None = None,
) -> dict[str, int]:
    out = Path(out_dir)
    images_dir = out / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    names = sample_names(rng, total)
    if dict_path is not None:
        names = filter_names_to_dict(names, load_dict_chars(dict_path))
    train, validation, holdout = split_batches(
        names, validation_fraction=validation_fraction, holdout_fraction=holdout_fraction
    )
    fonts = _handwriting_font_paths()

    def _emit(batch: list[str], label_name: str, *, batch_augment: bool) -> int:
        rows: list[tuple[str, str]] = []
        for index, name in enumerate(batch, start=1):
            font = rng.choice(fonts)
            image = _render_name(name, font, rng, augment=batch_augment)
            image_rel = f"images/{label_name.split('.')[0]}-{index:05d}.png"
            image.save(out / image_rel)
            rows.append((image_rel, name))
        write_label_file(out / label_name, rows)
        return len(rows)

    return {
        "train": _emit(train, "train.txt", batch_augment=augment),
        "validation": _emit(validation, "validation.txt", batch_augment=False),
        "holdout": _emit(holdout, "holdout.txt", batch_augment=False),
    }


def main(argv: list[str] | None = None) -> int:
    import json

    parser = argparse.ArgumentParser(prog="training.gen_names")
    parser.add_argument("--out", required=True)
    parser.add_argument("--total", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--validation-fraction", type=float, default=0.1)
    parser.add_argument("--holdout-fraction", type=float, default=0.1)
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument("--dict", help="rec dictionary file; names with OOV chars are dropped")
    args = parser.parse_args(argv)
    summary = render_corpus(
        args.out,
        rng=random.Random(args.seed),
        total=args.total,
        validation_fraction=args.validation_fraction,
        holdout_fraction=args.holdout_fraction,
        augment=not args.no_augment,
        dict_path=args.dict,
    )
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

Note: if `training.generate._resolve_text_font` import in `_handwriting_font_paths` is unused, remove that import line — only `list_handwriting_fonts` is needed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_gen_names.py tests/test_gen_names_render.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add training/gen_names.py tests/test_gen_names_render.py
git commit -m "feat: render synthetic handwritten name corpus"
```

---

### Task 4: Engine smoke (DECISION GATE — do this before Tasks 5+)

**Files:**
- No production files; results recorded in `openspec/changes/add-name-rec-finetune/tasks.md` notes and the eventual PR body.

- [ ] **Step 1: Fetch trainer and weights**

Run: `.venv-paddle\Scripts\python training/fetch_paddleocr_train.py`
Expected: clone succeeds, weights download succeeds, final line prints `config: ... exists=True`.
If the tag, weights URL, or config relpath 404s: consult `training/vendor/PaddleOCR/docs` for the
current PP-OCRv5 rec finetune doc, correct the constants in `training/fetch_paddleocr_train.py`
(keeping the tests green), and note the corrected values in the commit message.

- [ ] **Step 2: Generate a 50-name smoke corpus**

Run: `.venv-paddle\Scripts\python -m training.gen_names --out training\out\namesmoke --total 50 --seed 99 --dict training\vendor\PaddleOCR\ppocr\utils\dict\ppocrv5_dict.txt`
Expected: JSON summary like `{"train": 40, "validation": 5, "holdout": 5}` (counts may be lower if OOV names were dropped).
If the dict file lives at a different relpath in the pinned tag, locate it with
`Get-ChildItem training\vendor\PaddleOCR -Recurse -Filter *dict*.txt | Select-Object -First 10` and use that path.

- [ ] **Step 3: One-epoch finetune on CPU**

Run (from repo root; single line):
```powershell
.venv-paddle\Scripts\python training\vendor\PaddleOCR\tools\train.py -c training\vendor\PaddleOCR\configs\rec\PP-OCRv5\PP-OCRv5_mobile_rec.yml -o Global.use_gpu=false Global.epoch_num=1 Global.save_model_dir=training\out\namesmoke\model Global.pretrained_model=training\vendor\PP-OCRv5_mobile_rec_pretrained Global.character_dict_path=training\vendor\PaddleOCR\ppocr\utils\dict\ppocrv5_dict.txt Train.dataset.data_dir=training\out\namesmoke Train.dataset.label_file_list=[training\out\namesmoke\train.txt] Eval.dataset.data_dir=training\out\namesmoke Eval.dataset.label_file_list=[training\out\namesmoke\validation.txt] Train.loader.batch_size_per_card=8 Eval.loader.batch_size_per_card=8
```
Expected: training runs to completion of 1 epoch and writes checkpoints under `training\out\namesmoke\model`.
**Record the single-epoch wall time** — it calibrates Task 9's epoch budget.
Likely friction points (fix forward, keep notes): missing training-only pip deps in `.venv-paddle`
(install what the import errors name, e.g. `python -m pip install pyyaml lmdb rapidfuzz albumentations`),
`Global.use_gpu` vs `Global.device=cpu` naming in the pinned tag, Windows path separators in the
`label_file_list` override (use forward slashes if the parser rejects backslashes).

- [ ] **Step 4: Export inference model and reload via pip paddleocr**

```powershell
.venv-paddle\Scripts\python training\vendor\PaddleOCR\tools\export_model.py -c training\vendor\PaddleOCR\configs\rec\PP-OCRv5\PP-OCRv5_mobile_rec.yml -o Global.use_gpu=false Global.pretrained_model=training\out\namesmoke\model\latest Global.character_dict_path=training\vendor\PaddleOCR\ppocr\utils\dict\ppocrv5_dict.txt Global.save_inference_dir=training\out\namesmoke\inference
```

Then verify pip-side loading:

```powershell
.venv-paddle\Scripts\python -c "from paddleocr import TextRecognition; import json; m = TextRecognition(model_dir='training/out/namesmoke/inference', model_name='PP-OCRv5_mobile_rec'); r = m.predict('training/out/namesmoke/images/holdout-00001.png'); print(json.dumps([{'text': x['rec_text'], 'score': float(x['rec_score'])} for x in r], ensure_ascii=False))"
```
Expected: prints a recognized text (quality irrelevant after 1 epoch; loading is what's being proven).

- [ ] **Step 5: Decision checkpoint**

- PASS (train + export + pip reload all worked): tick the Phase 1 boxes in
  `openspec/changes/add-name-rec-finetune/tasks.md`, commit any constant corrections, continue to Task 5.
- FAIL (pipeline fundamentally broken on Windows CPU): STOP. Report findings to the user and evaluate
  the PaddleX finetune API as the alternative engine before touching Tasks 5+.

```bash
git add -A
git commit -m "chore: record name rec engine smoke results"
```

---

### Task 5: Train wrapper command builders

**Files:**
- Create: `training/train_name_model.py`
- Test: `tests/test_train_name_model.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path

from training.train_name_model import build_export_command, build_train_command


def test_build_train_command_pins_cpu_paths_and_epochs() -> None:
    command = build_train_command(
        vendor_repo=Path("training/vendor/PaddleOCR"),
        corpus_dir=Path("training/out/namev1"),
        save_dir=Path("training/out/namev1/model"),
        pretrained=Path("training/vendor/PP-OCRv5_mobile_rec_pretrained"),
        dict_path=Path("training/vendor/PaddleOCR/ppocr/utils/dict/ppocrv5_dict.txt"),
        epochs=20,
        batch_size=16,
    )

    text = " ".join(command)
    assert command[0].endswith("train.py")
    assert "Global.use_gpu=false" in text
    assert "Global.epoch_num=20" in text
    assert "train.txt" in text and "validation.txt" in text
    assert "batch_size_per_card=16" in text


def test_build_export_command_targets_inference_dir() -> None:
    command = build_export_command(
        vendor_repo=Path("training/vendor/PaddleOCR"),
        checkpoint=Path("training/out/namev1/model/latest"),
        dict_path=Path("training/vendor/PaddleOCR/ppocr/utils/dict/ppocrv5_dict.txt"),
        inference_dir=Path("training/out/namev1/inference"),
    )

    text = " ".join(command)
    assert command[0].endswith("export_model.py")
    assert "Global.save_inference_dir=" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_train_name_model.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
"""Thin CPU finetune/export wrapper over the vendored official PaddleOCR trainer."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_CONFIG_RELPATH = "configs/rec/PP-OCRv5/PP-OCRv5_mobile_rec.yml"


def _posix(path: Path) -> str:
    return Path(path).as_posix()


def build_train_command(
    *,
    vendor_repo: Path,
    corpus_dir: Path,
    save_dir: Path,
    pretrained: Path,
    dict_path: Path,
    epochs: int,
    batch_size: int = 16,
    config_relpath: str = DEFAULT_CONFIG_RELPATH,
) -> list[str]:
    return [
        str(Path(vendor_repo) / "tools" / "train.py"),
        "-c",
        str(Path(vendor_repo) / config_relpath),
        "-o",
        "Global.use_gpu=false",
        f"Global.epoch_num={int(epochs)}",
        f"Global.save_model_dir={_posix(save_dir)}",
        f"Global.pretrained_model={_posix(pretrained)}",
        f"Global.character_dict_path={_posix(dict_path)}",
        f"Train.dataset.data_dir={_posix(corpus_dir)}",
        f"Train.dataset.label_file_list=[{_posix(Path(corpus_dir) / 'train.txt')}]",
        f"Eval.dataset.data_dir={_posix(corpus_dir)}",
        f"Eval.dataset.label_file_list=[{_posix(Path(corpus_dir) / 'validation.txt')}]",
        f"Train.loader.batch_size_per_card={int(batch_size)}",
        f"Eval.loader.batch_size_per_card={int(batch_size)}",
    ]


def build_export_command(
    *,
    vendor_repo: Path,
    checkpoint: Path,
    dict_path: Path,
    inference_dir: Path,
    config_relpath: str = DEFAULT_CONFIG_RELPATH,
) -> list[str]:
    return [
        str(Path(vendor_repo) / "tools" / "export_model.py"),
        "-c",
        str(Path(vendor_repo) / config_relpath),
        "-o",
        "Global.use_gpu=false",
        f"Global.pretrained_model={_posix(checkpoint)}",
        f"Global.character_dict_path={_posix(dict_path)}",
        f"Global.save_inference_dir={_posix(inference_dir)}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finetune and export the name-only rec model (CPU).")
    parser.add_argument("--corpus", required=True, help="Corpus dir containing train.txt/validation.txt/images/")
    parser.add_argument("--save-dir", required=True)
    parser.add_argument("--inference-dir", required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--vendor", default="training/vendor/PaddleOCR")
    parser.add_argument("--pretrained", default="training/vendor/PP-OCRv5_mobile_rec_pretrained")
    parser.add_argument("--dict", default="training/vendor/PaddleOCR/ppocr/utils/dict/ppocrv5_dict.txt")
    args = parser.parse_args(argv)

    train_command = [sys.executable] + build_train_command(
        vendor_repo=Path(args.vendor),
        corpus_dir=Path(args.corpus),
        save_dir=Path(args.save_dir),
        pretrained=Path(args.pretrained),
        dict_path=Path(args.dict),
        epochs=args.epochs,
        batch_size=args.batch_size,
    )
    subprocess.run(train_command, check=True)
    export_command = [sys.executable] + build_export_command(
        vendor_repo=Path(args.vendor),
        checkpoint=Path(args.save_dir) / "latest",
        dict_path=Path(args.dict),
        inference_dir=Path(args.inference_dir),
    )
    subprocess.run(export_command, check=True)
    print(f"exported: {args.inference_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

If the smoke (Task 4) revealed different override key names (e.g. `Global.device=cpu`), update both
the builders and the tests accordingly in this task.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_train_name_model.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add training/train_name_model.py tests/test_train_name_model.py
git commit -m "feat: add name rec finetune/export wrapper"
```

---

### Task 6: Eval metrics and report

**Files:**
- Create: `training/eval_name_model.py`
- Test: `tests/test_eval_name_model.py`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import json
from pathlib import Path

from training.eval_name_model import char_accuracy, edit_distance, score_predictions, write_report


def test_edit_distance_basics() -> None:
    assert edit_distance("王小明", "王小明") == 0
    assert edit_distance("王小明", "王大明") == 1
    assert edit_distance("王小明", "") == 3
    assert edit_distance("", "陳") == 1


def test_char_accuracy_is_one_minus_normalized_edit_distance() -> None:
    assert char_accuracy("王小明", "王小明") == 1.0
    assert char_accuracy("王小明", "王大明") == 1.0 - 1.0 / 3.0
    assert char_accuracy("", "") == 1.0


def test_score_predictions_aggregates_exact_match_and_char_accuracy() -> None:
    pairs = [("王小明", "王小明"), ("陳美玲", "陳美月"), ("林志偉", "")]

    metrics = score_predictions(pairs)

    assert metrics["count"] == 3
    assert metrics["exact_match"] == 1 / 3
    assert 0.0 < metrics["char_accuracy"] < 1.0


def test_write_report_emits_json_and_markdown(tmp_path: Path) -> None:
    metrics = {"count": 2, "exact_match": 0.5, "char_accuracy": 0.75}

    write_report(metrics, tmp_path)

    loaded = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert loaded == metrics
    assert "exact_match" in (tmp_path / "report.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_eval_name_model.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_eval_name_model.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add training/eval_name_model.py tests/test_eval_name_model.py
git commit -m "feat: add name rec holdout evaluation"
```

---

### Task 7: Gate, atomic deploy, audit, corrections harvest

**Files:**
- Create: `training/retrain_name.py`
- Create: `training/harvest_name_corrections.py`
- Test: `tests/test_retrain_name.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_retrain_name.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `training/retrain_name.py`**

```python
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
    current_dir = target if (target / "inference.pdmodel").exists() or any(target.glob("*.pdmodel")) or target.is_dir() and any(target.iterdir()) else None

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
```

Simplify the messy `current_dir` line during implementation to:

```python
    current_dir = target if target.is_dir() and any(target.iterdir()) else None
```

- [ ] **Step 4: Write `training/harvest_name_corrections.py`**

```python
"""Convert confirmed name corrections (name_corrections.jsonl) into rec label rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def corrections_to_label_rows(corrections_path: str | Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    path = Path(corrections_path)
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("field") != "name":
            continue
        value = payload.get("final_value")
        crop = payload.get("crop_path")
        if not isinstance(value, str) or not value.strip():
            continue
        if not isinstance(crop, str) or not Path(crop).is_file():
            continue
        rows.append((crop, value.strip()))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append confirmed name corrections to a rec label file.")
    parser.add_argument("corrections", help="name_corrections.jsonl path")
    parser.add_argument("--output", required=True, help="Label txt to append to (absolute crop paths)")
    args = parser.parse_args(argv)

    rows = corrections_to_label_rows(args.corrections)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for crop, value in rows:
            handle.write(f"{Path(crop).as_posix()}\t{value}\n")
    print(json.dumps({"rows": len(rows)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

Note: these corrections rows use absolute crop paths, so pass this label file to the trainer with
`Train.dataset.data_dir=/` semantics or merge by copying crops into the corpus — for v1 the merge
step is: `Get-Content corrections.txt >> training\out\namev1\train.txt` only when crops were copied
under the corpus dir; otherwise keep it as a separate `label_file_list` entry (PaddleOCR accepts
multiple files). Keep whichever the smoke proved works; default to the separate-entry approach.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_retrain_name.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add training/retrain_name.py training/harvest_name_corrections.py tests/test_retrain_name.py
git commit -m "feat: add name rec gate, atomic deploy, and corrections harvest"
```

---

### Task 8: Plugin integration

**Files:**
- Modify: `plugins/paddleocr/main.py` (name model resolution + name fill in `main()`)
- Modify: `build/build_paddle_plugin.py` (bundle `name_rec/` when present)
- Test: `tests/test_paddle_name_rec_integration.py`
- Test (modify): `tests/test_build_paddle_plugin.py` (add `name_rec` copy expectation)

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "paddleocr" / "main.py"
_spec = importlib.util.spec_from_file_location("paddle_plugin_main_namerec", _MODULE_PATH)
plugin_main = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(plugin_main)


def _make_model_dir(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "inference.pdmodel").write_text("stub", encoding="utf-8")
    return path


def test_resolve_name_rec_dir_prefers_env_then_runtime_then_bundle(tmp_path: Path, monkeypatch) -> None:
    env_dir = _make_model_dir(tmp_path / "env-model")
    home = tmp_path / "home"
    runtime_dir = _make_model_dir(home / "name_rec")

    monkeypatch.setenv("NAME_REC_MODEL_DIR", str(env_dir))
    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(home))
    monkeypatch.setattr(plugin_main, "_HERE", tmp_path / "no-bundle")
    assert plugin_main._resolve_name_rec_dir() == env_dir

    monkeypatch.delenv("NAME_REC_MODEL_DIR")
    assert plugin_main._resolve_name_rec_dir() == runtime_dir

    monkeypatch.setenv("OCR_FROM2XLSX_HOME", str(tmp_path / "empty-home"))
    assert plugin_main._resolve_name_rec_dir() is None


def test_apply_name_suggestion_fills_name_only_when_non_empty() -> None:
    record = {"name": "", "ocr": {"warnings": []}}

    plugin_main.apply_name_suggestion(record, "王小明")
    assert record["name"] == "王小明"

    plugin_main.apply_name_suggestion(record, "")
    assert record["name"] == "王小明"

    plugin_main.apply_name_suggestion(record, None)
    assert record["name"] == "王小明"


def test_name_rec_failure_returns_none(monkeypatch, tmp_path: Path) -> None:
    model_dir = _make_model_dir(tmp_path / "model")

    def boom(_crop: str, _model_dir: str) -> str:
        raise OSError("broken model")

    monkeypatch.setattr(plugin_main, "_paddle_name_rec", boom)
    assert plugin_main.recognize_name_safe(str(tmp_path / "crop.png"), str(model_dir)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_name_rec_integration.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: FAIL with `AttributeError: ... has no attribute '_resolve_name_rec_dir'`

- [ ] **Step 3: Implement in `plugins/paddleocr/main.py`**

Add below `_resolve_mark_model_path()` (reuse the existing `_user_runtime_dir()` helper):

```python
def _existing_dir(value: str | os.PathLike[str] | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_dir() and any(path.iterdir()) else None


def _resolve_name_rec_dir() -> Path | None:
    # Resolution order mirrors mark weights: env override, user runtime, bundle.
    env_dir = _existing_dir(os.environ.get("NAME_REC_MODEL_DIR"))
    if env_dir is not None:
        return env_dir
    runtime_dir = _existing_dir(_user_runtime_dir() / "name_rec")
    if runtime_dir is not None:
        return runtime_dir
    return _existing_dir(_HERE / "name_rec")


def apply_name_suggestion(record: dict[str, Any], name: str | None) -> None:
    if isinstance(name, str) and name.strip():
        record["name"] = name.strip()


def _paddle_name_rec(crop_path: str, model_dir: str) -> str:
    from paddleocr import TextRecognition

    model = TextRecognition(model_dir=model_dir, model_name="PP-OCRv5_mobile_rec")
    results = model.predict(crop_path)
    if not results:
        return ""
    return str(results[0].get("rec_text") or "")


def recognize_name_safe(crop_path: str, model_dir: str) -> str | None:
    try:
        return _paddle_name_rec(crop_path, model_dir)
    except (ValueError, OSError, RuntimeError):
        return None
```

Wire it into `main()` right after the existing name-crop save block (the `if saved:` branch):

```python
        if saved:
            response["record"]["ocr"]["name_crop"] = _Path(saved).name
            name_rec_dir = _resolve_name_rec_dir()
            if name_rec_dir is not None:
                suggestion = recognize_name_safe(str(crop_out), str(name_rec_dir))
                apply_name_suggestion(response["record"], suggestion)
```

(`record.name` suggestions are re-marked `name.unconfirmed` downstream by `prepare_records`; no
warning handling is needed here. Confirm by reading `src/ocr_from2xlsx/prepare_records.py` — it tags
any backend-supplied name.)

- [ ] **Step 4: Update build script + its test**

In `tests/test_build_paddle_plugin.py`, find the bundle-contents test and extend the expected
optional copies with `name_rec`. Then in `build/build_paddle_plugin.py`, extend the optional asset
loop:

```python
    for name in ["template_boxes.json", "mark_model.json"]:
```

becomes

```python
    for name in ["template_boxes.json", "mark_model.json"]:
        ...  # existing file copy unchanged
    name_rec_dir = src_dir / "name_rec"
    if name_rec_dir.is_dir():
        shutil.copytree(name_rec_dir, bundle_dir / "name_rec", dirs_exist_ok=True)
```

(Adapt names to the actual variables in that script; read it first. The test asserts that when a
`name_rec/` dir with one file exists in the plugin source dir, the bundle contains it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_paddle_name_rec_integration.py tests/test_paddle_mark_model_integration.py tests/test_build_paddle_plugin.py -q -p no:cacheprovider --basetemp=output/pytest-tmp`
Expected: all pass (existing mark/bundle tests stay green)

- [ ] **Step 6: Commit**

```bash
git add plugins/paddleocr/main.py build/build_paddle_plugin.py tests/test_paddle_name_rec_integration.py tests/test_build_paddle_plugin.py
git commit -m "feat: plugin name suggestion via dedicated name rec model"
```

---

### Task 9: v1 production run

**Files:**
- Create (generated, committed): `plugins/paddleocr/name_rec/` (adopted inference model dir)
- Generated (gitignored): `training/out/namev1/`

- [ ] **Step 1: Generate the v1 corpora**

Seeds follow the project convention (train 0 / validation 5678 / holdout 1234 are TAKEN by the mark
project; name project uses its own fixed trio recorded here): train+split seed **20** in one
generation call (split_batches guarantees disjointness within the call).

Run: `.venv-paddle\Scripts\python -m training.gen_names --out training\out\namev1 --total 3000 --seed 20 --dict training\vendor\PaddleOCR\ppocr\utils\dict\ppocrv5_dict.txt`
Expected: summary near `{"train": 2400, "validation": 300, "holdout": 300}`.

- [ ] **Step 2: Finetune (budget by smoke timing)**

Pick `--epochs` so the run fits overnight based on the Task 4 single-epoch wall time (start with 20).

Run: `.venv-paddle\Scripts\python -m training.train_name_model --corpus training\out\namev1 --save-dir training\out\namev1\model --inference-dir training\out\namev1\inference --epochs 20`
Expected: exits 0, prints `exported: training\out\namev1\inference`.

- [ ] **Step 3: Baseline + candidate eval, then gate**

Run baseline first (for the PR numbers):
`.venv-paddle\Scripts\python -m training.eval_name_model training\out\namev1\holdout.txt --output-dir training\out\namev1\eval-baseline`

Then gate + deploy to a staging runtime dir:
`.venv-paddle\Scripts\python -m training.retrain_name training\out\namev1\inference --holdout training\out\namev1\holdout.txt --runtime-dir training\out\namev1\deploy\name_rec`
Expected: `"adopt": true` with candidate exact_match clearly above the pip baseline (baseline on
handwriting-font names is expected to be very low). If rejected: inspect
`training\out\namev1\deploy\name_audit.jsonl`, increase epochs/corpus, repeat — do NOT weaken the gate.

- [ ] **Step 4: Commit the adopted model as bundle baseline**

```powershell
Copy-Item -Recurse training\out\namev1\deploy\name_rec plugins\paddleocr\name_rec
git add plugins/paddleocr/name_rec
git commit -m "feat: ship v1 name rec bundle baseline"
```

If the model dir exceeds ~30 MB, stop and ask the user before committing (repo-size tradeoff).

---

### Task 10: Docs, OpenSpec, policy, PR

**Files:**
- Modify: `README.md` (new "Handwritten name model training" subsection under Training data generator)
- Modify: `CHANGELOG.md` (`[Unreleased]` Added entries)
- Modify: `openspec/changes/add-name-rec-finetune/tasks.md` (tick completed phases)

- [ ] **Step 1: README** — document the five commands (fetch, gen_names, train_name_model,
  eval_name_model, retrain_name + harvest_name_corrections), the `NAME_REC_MODEL_DIR` /
  `~/.ocr_from2xlsx/name_rec/` resolution order, and that suggestions stay `name.unconfirmed`.

- [ ] **Step 2: CHANGELOG `[Unreleased]` Added** — one entry for the training engine
  (fetch/gen/train/eval/gate/audit), one for the plugin name model resolution + bundle baseline,
  one for the corrections harvest. Mirror the mark-classifier entry style.

- [ ] **Step 3: Verification battery**

```powershell
.venv\Scripts\python -W error -m pytest -q -p no:cacheprovider --basetemp=output/pytest-tmp
.venv\Scripts\python -m policy_check --repo .
.venv\Scripts\python build/package.py
```
Expected: all green.

- [ ] **Step 4: Commit, push, PR**

```bash
git add -A
git commit -m "docs: document name rec training engine"
git push -u origin wt/bootstrap-ocr-design/name-rec-training
gh pr create --base feature/bootstrap-ocr-design --title "feat: handwritten name rec finetune training engine" --body "<fill PR template: summary with holdout exact-match/char-accuracy vs baseline, test plan checked, policy checklist checked>"
```

---

## Self-Review Notes

- Spec coverage: fetch/pin (Task 1), corpus + seeds + disjoint batches + OOV filter (Tasks 2-3),
  engine smoke gate (Task 4), train/export wrapper (Task 5), eval metrics (Task 6), gate + atomic
  deploy + audit + corrections harvest (Task 7), plugin resolution/fill/fallback + packaging
  (Task 8), v1 run + bundle baseline (Task 9), docs/policy (Task 10). Design's "engine smoke before
  building the loop" is honored by the Task 4 STOP rule.
- Known uncertainty: exact PaddleOCR tag/URL/override-key names may differ at the pinned tag; Tasks
  1/4/5 explicitly localize where to correct them (constants + builders + their tests).
- Type consistency: label rows are `(image_rel: str, label: str)` everywhere; metrics dicts use
  `exact_match` / `char_accuracy` / `count` in eval, gate, and audit alike.
