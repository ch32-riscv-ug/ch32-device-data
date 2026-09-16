#!/usr/bin/env python3
"""データシートの図が載っているページ → evidence/figures.csv

**生成 README からページ直リンクを張るための表**（worklist C2）。`#page=N` は
GitHub Pages が配る PDF で効くので、型番ごとに「ピン配置図がどの版面に在るか」を
持てば、パッケージ対応表から原典の該当ページへ直接送れる。

いまの `kind` は `pinout` だけ。ピン配置の章（zh `2.1 引脚排列` / en `2.1 Pinouts`）の
中で**図の見出しに刷られた型番**を拾い、その版面の番号を出す。同じ図が複数の型番を
代表することがある（`CH32V103Cx` は C6T6・C8T6・C8U6 の3つ、`CH32V303RxT6/CH32V303RCT7`
のようにスラッシュで連ねる版もある）ので、**伏字を展開した型番ごとに1行**にする。

**両版でページが違うのは当たり前**（版面の割り付けが違う）。したがって
`page_zh`・`page_en` は別の列で、食い違いではない。両版が図を持てば `confirmed`、
片版だけなら `reference`。

**2つ、素直に読むと落ちるところがある。**

  章の終わりは**行の順**で決まる  `CH32V003DS0.en` は p.13 の一番上に SOP8 の図
                                   （`CH32V003J4M6`）を置き、その下に `2.2 Pin
                                   Description` の見出しが来る。ページ本文をまとめて
                                   見てから語を探すと、この図が丸ごと落ちる。
  見出しの型番が語で割れる版がある `CH32V006DS0.zh` p.12 は `CH32V0 06F8P7` と
                                   2語に割れて出る（英語版は1語）。隣り合う語を
                                   繋いだ綴りも型番として試す（**間隔が近いときだけ**）。

読む面は bundle の `lines`（視覚行）と `words`（語）だけで、PDF は開かない。
ページの読み手は `pipeline/extract/bundle_pages.py`（sha 照合つき）。

実行:
    uv run pipeline/extract/datasheet/extract_figures.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402
import paths  # noqa: E402

COLUMNS = ["series", "part_number", "kind", "document",
           "page_zh", "page_en", "#", "confidence", "basis"]

# 章の見出し。`引脚分布`・`引脚图` は凍結tool `tools/extract_images.py` から引き継いだ
# 綴りで、**中文版の実際の綴りは `引脚排列`**（英語版しか読まない凍結tool では出番が
# 無かった）。全16冊の中文版がこの綴り。
PINOUT_CHAPTER = re.compile(r"^\d+\.\d+\s+(?:Pinouts?|引脚分布|引脚排列|引脚图)\s*$", re.I)
NEXT_CHAPTER = re.compile(r"^\d+\.\d+\s+\S")
# 見出しは1つの型番とは限らず、`CH32V303RxT6/CH32V303RCT7` のようにスラッシュで
# 連ねることがある。
PART_LABEL = re.compile(r"^CH32[A-Za-z0-9]{4,}(?:/CH32[A-Za-z0-9]{4,})*$")
# 語を繋いで型番として読むときの、語と語の間隔の上限（pt）。
JOIN_GAP = 4.0
# 繋ぐのは最大この数の語まで。
JOIN_WORDS = 3


def expand_label(label: str, parts: list[str]) -> list[str]:
    """図の見出し → 実在する型番。

    見出しは完全な型番とは限らない。伏字（`CH32V103Cx`）、温度グレードの桁を
    省いた形（`CH32V006E8R` が R6 を指す）がある。8文字はシリーズ名そのもの
    （`CH32L103`）なので展開しない——ページヘッダの「CH32L103 Datasheet」を
    見出しと取り違えるため。

    >>> expand_label("CH32V103Cx", ["CH32V103C6T6", "CH32V103C8T6", "CH32V103R8T6"])
    ['CH32V103C6T6', 'CH32V103C8T6']
    >>> expand_label("CH32L103", ["CH32L103C8T6"])
    []
    >>> expand_label("CH32V103C6T6", ["CH32V103C6T6"])
    ['CH32V103C6T6']
    """
    if label in parts:
        return [label]
    if len(label) <= 8:
        return []
    pattern = re.compile("^" + re.sub(r"[xX]", ".", label) + "[A-Z0-9]*$")
    return [p for p in parts if pattern.match(p)]


def word_lines(page: dict) -> list[tuple[float, list[dict]]]:
    """(上端, その行の語) を紙の上から順に。語は左から。

    `bundle_pages.text_lines` は行の綴りを持つが**語の座標を持たない**。見出しの
    型番は座標で隣り合わせを判定したい（割れた語を繋ぐ）ので、語から行を組む。
    """
    rows: dict[float, list[dict]] = collections.defaultdict(list)
    for word in page.get("words", []):
        x0, top, x1, bottom = word["bbox"]
        rows[round(top)].append({"text": word["text"], "x0": x0, "x1": x1,
                                 "top": top, "bottom": bottom})
    return [(top, sorted(rows[top], key=lambda w: w["x0"]))
            for top in sorted(rows)]


def labels_in(words: list[dict]) -> list[str]:
    """行の中の型番の綴り。隣り合う語を繋いだ形も試す。

    `CH32V006DS0.zh` p.12 は `CH32V0 06F8P7` と2語に割れる。繋ぐのは**間隔が
    `JOIN_GAP` 以内**のときだけで、離れた2つの図の見出しは繋がらない。繋いだ
    結果が実在の型番でなければ `expand_label` が空を返すので、余分な候補が
    行を増やすことはない。

    >>> labels_in([{"text": "CH32V0", "x0": 0, "x1": 34},
    ...            {"text": "06F8P7", "x0": 35, "x1": 70}])
    ['CH32V006F8P7']
    >>> labels_in([{"text": "CH32V006K8U7", "x0": 0, "x1": 60},
    ...            {"text": "CH32V006E8R6", "x0": 200, "x1": 260}])
    ['CH32V006K8U7', 'CH32V006E8R6']
    """
    found: list[str] = []
    for i, word in enumerate(words):
        joined = word["text"]
        if PART_LABEL.match(joined):
            found.append(joined)
        for j in range(i + 1, min(i + JOIN_WORDS, len(words))):
            if words[j]["x0"] - words[j - 1]["x1"] > JOIN_GAP:
                break
            joined += words[j]["text"]
            if PART_LABEL.match(joined) and joined not in found:
                found.append(joined)
    return found


def pinout_pages(bundle: str, parts: list[str]) -> dict[str, int]:
    """bundle → {型番: ピン配置章でその図が在る版面}。

    章の内と外は**行の順**で切り替える。見出しより上に在る図はまだ章の内側で、
    `CH32V003DS0.en` p.13 の SOP8 図（`2.2 Pin Description` の見出しより上）が
    それに当たる。
    """
    inside = False
    found: dict[str, int] = {}
    for page in bundle_pages.pages(bundle):
        for _, words in word_lines(page):
            text = " ".join(w["text"] for w in words).strip()
            if PINOUT_CHAPTER.match(text):
                inside = True
                continue
            if inside and NEXT_CHAPTER.match(text):
                inside = False
            if not inside:
                continue
            for label in labels_in(words):
                for token in label.split("/"):
                    for part in expand_label(token, parts):
                        found.setdefault(part, page["number"])
    return found


def bundle_name(document: str, lang: str) -> str:
    """目録の文書名（`CH32V103DS0.PDF`）と言語 → bundle 名（`CH32V103DS0.en`）。"""
    return f"{Path(document).stem}.{lang}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="override the output directory (tests)")
    args = ap.parse_args()

    products = paths.load("products")
    by_document: dict[str, list[dict]] = collections.defaultdict(list)
    for product in products:
        by_document[product["datasheet"]].append(product)
    editions = {row["document"]: row for row in bundle_pages.documents("datasheet")}

    rows: list[dict] = []
    notes: list[str] = []
    for document in sorted(by_document):
        catalogued = editions.get(document)
        if catalogued is None:
            notes.append(f"{document}: 目録に assigned な datasheet として無い")
            continue
        own = sorted(p["part_number"] for p in by_document[document])
        series_of = {p["part_number"]: p["series"] for p in by_document[document]}
        pages: dict[str, dict[str, int]] = {}
        for lang in ("zh", "en"):
            if not catalogued.get(f"version_{lang}"):
                continue
            pages[lang] = pinout_pages(bundle_name(document, lang), own)
        for part in own:
            where = {lang: found[part] for lang, found in pages.items()
                     if part in found}
            if not where:
                notes.append(f"{document}: {part} のピン配置図が両版とも見つからない")
                continue
            if len(where) < len(pages):
                missing = sorted(set(pages) - set(where))
                notes.append(f"{document}: {part} は "
                             f"{'/'.join(missing)} 版に図の見出しが無い")
            basis = "+".join(f"{document}:{lang}(p.{where[lang]})"
                             for lang in ("zh", "en") if lang in where)
            rows.append({
                "series": series_of[part], "part_number": part, "kind": "pinout",
                "document": document,
                "page_zh": where.get("zh", ""), "page_en": where.get("en", ""),
                "confidence": "confirmed" if len(where) > 1 else "reference",
                "basis": basis,
            })

    rows.sort(key=lambda r: (r["series"], r["part_number"], r["kind"]))
    dest = paths.table("figures", args.out)
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{dest}: {len(rows)} 行  文書 {len({r['document'] for r in rows})}"
          f"  {dict(tally)}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
