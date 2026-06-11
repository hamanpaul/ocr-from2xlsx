"""Synthetic handwritten Chinese name corpus generator (PaddleOCR rec label format)."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable, Sequence

SURNAMES = tuple(
    "陳林黃張李王吳劉蔡楊許鄭謝郭洪曾邱廖賴徐周葉蘇莊江呂何羅高蕭潘朱簡鍾彭游詹胡施沈余盧梁趙顏"
    "柯翁魏孫戴范方宋鄧杜傅侯曹溫薛丁馬蔣唐卓藍馮姚石董紀歐程連古汪湯姜田康鄒白塗尤巫韓龔嚴袁鐘"
    "黎金阮陸倪夏童邵柳錢"
)

_GIVEN_CHARS_RAW = (
    "明華志偉雅婷怡君淑芬美玲俊宏家豪建宏冠宇宗翰哲瑋柏翰彥廷承恩宥廷品妤詠晴子涵思妤心安宜蓁"
    "佳穎欣怡雅雯郁婷孟儒崇恩政勳文雄金龍秀英麗珠玉蘭素珍春嬌阿寶坤山進財福來添丁萬得水木火土"
    "國強建國中正治平安康健勇敢誠信義禮智仁愛和平喜樂恩慈良善真美聖潔光輝榮耀偉大尊貴富強盛旺"
    "發達興隆昌泰祥瑞吉慶豐收滿堂紅梅蘭竹菊松柏楓桂荷蓮薇芳菲翠綠青藍紫白黑金銀珠寶玉石琴棋書"
    "畫詩詞歌賦琪琳瑜珊珮瑩瓊瑤璇璟曉晨旭日月星辰宇宙乾坤山川河海江湖風雲雷電雨雪霜露虹霞煙波"
    "濤浪潮汐泉溪潭瀑些奇妙玄真元亨利貞天地人和春夏秋冬東南西北中央左右前後上下高低長短大小多"
    "少新舊好妮娜莉莎蒂芙妃姿婉柔媛婕妶嫻淑慧穎聰敏捷靈巧妙慧黠睿哲彬彪虎豹龍鳳麟龜鶴燕鵯鵬雁"
    "鴻雀鵑凰羽毛皮革骨肉血氣神魂魄心肝脾肺腎腦髓筋脈絡膚髮膽識量度衡規矩準繩墨硯筆紙簡冊卷軸"
)

# preserve ordering while removing duplicate characters
GIVEN_CHARS = tuple(dict.fromkeys(_GIVEN_CHARS_RAW))


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
