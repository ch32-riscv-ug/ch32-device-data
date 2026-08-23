#!/usr/bin/env python3
"""family が持つ周辺の一覧 → tables/features.csv

**比較表からは作れない**（A6 の調査）。datasheet の比較表は「シリーズ内で差が
ある列」しか持たないので、シリーズ共通の周辺は列ごと存在しない——CH32V307 の
属性は 6 種しかなく、USBHS も Ethernet も行が無い（実際には両方ある）。
「属性が無い＝その機能が無い」は誤りで、そこからフラグは導けない。

**機能説明の章（1.4）は別物で、その family が持つ周辺を節見出しとして並べる。**

    1.4.8  Programmable Fast Interrupt Controller (PFIC)
    1.4.19 Controller Area Network (CAN)
    1.4.26 2-wire SDI Serial Debug Interface

見出しの一覧がそのまま周辺の一覧になる。**節番号は言語に依らない**ので、
中英の対応付けは番号で厳密に取れる（比較表のように値の並びで推測しなくてよい）。
両版が同じ番号を持てば confirmed、片方だけなら reference。

**これは datasheet が覆う series の事実で、型番の事実ではない。** 1 つの family が
datasheet を複数持つことがあり（CH32V006 は V002/V004/V006/V007 の 4 冊）、
**節番号は 1 冊の中でしか一意でない**——別々の冊子の `1.4.17` は別のものを指す。
そこで行の主キーは family ではなく **datasheet が覆う series の組**にする
（`operating_conditions.csv` と同じ持ち方）。型番で欠ける周辺があるかどうかは
比較表（`product_attributes.csv`）側の差分で、両方を見ないと決まらない。
`granularity` 列にそれを明記する。

書き込み方式（worklist の A8）もここに出る——`2-wire SDI Serial Debug Interface`
と `1-wire SDI` が見出しとして立っている。

実行:
    uv run tools/build_features.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")
# 機能説明の章は必ず前の方にある。ここまで見れば足りる。
MAX_PAGES = 40

COLUMNS = ["series", "family", "section", "feature", "feature_zh", "granularity",
           "#", "confidence", "basis", "datasheet"]

#   1.4.19 Controller Area Network (CAN)
# 表の中の数字の並び（"1.8 3.6"）を拾わないよう、題に文字を要求する。
HEADING = re.compile(r"^(?P<section>\d+(?:\.\d+){1,3})\s+(?P<title>.*[A-Za-z一-鿿].*)$")
# **章番号は決め打ちできない。** 機能説明は CH32L103 で 1.4、CH32V103 で 1.5。
# 題で章を見つけて、その子節を採る。
DESCRIPTION = re.compile(r"^(?:Functional\s+Description|功能概述|功能描述|功能说明)\b",
                         re.IGNORECASE)
# 表の中の数字の並びが見出しの形をして混ざる。CH32V103 の ADC 表は
# `1.5 239.5 1/f` と `1.5 0.11 0（不推荐）` を出し、**本物の `1.5 功能概述` を
# 上書きしていた**。題が数だけで始まるものは見出しではない
# （`2-wire SDI Serial Debug Interface` は数の直後が `-` なので残る）。
NUMERIC_ROW = re.compile(r"^[\d.]+(?:\s|$)")
# 題の末尾に付く頁番号や罫線の残り。
TRAILING = re.compile(r"\s*[.·…]{2,}\s*\d+\s*$")


def read_headings(path: Path) -> tuple[str, dict[str, str]]:
    """(機能説明の章番号, {子節番号: 題})。読めなければ ("", {})。

    同じ番号が2回出たら目次と本文の両方に出ているので、後に出た本文側を採る。
    """
    seen: dict[str, str] = {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:MAX_PAGES]:
            for line in (page.extract_text() or "").splitlines():
                heading = HEADING.match(line.strip())
                if not heading:
                    continue
                title = TRAILING.sub("", heading.group("title")).strip()
                if title and not NUMERIC_ROW.match(title):
                    seen[heading.group("section")] = title
            page.flush_cache()
    chapter = next((s for s, t in seen.items() if DESCRIPTION.match(t)), "")
    if not chapter:
        return "", {}
    return chapter, {s: t for s, t in seen.items()
                     if s.startswith(f"{chapter}.") and s != chapter}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    with (args.out / "products.csv").open(newline="", encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    by_datasheet: dict[str, str] = {}
    covers: dict[str, set[str]] = {}
    for product in products:
        by_datasheet.setdefault(product["datasheet"], product["family"])
        covers.setdefault(product["datasheet"], set()).add(product["series"])

    rows: list[dict] = []
    notes: list[str] = []
    for datasheet, family in sorted(by_datasheet.items()):
        editions: dict[str, dict[str, str]] = {}
        chapters: dict[str, str] = {}
        for lang in ("zh", "en"):
            path = args.mirrors / family / f"datasheet_{lang}" / datasheet
            if path.exists():
                chapter, found = read_headings(path)
                if found:
                    editions[lang] = found
                    chapters[lang] = chapter
        if len(set(chapters.values())) > 1:
            notes.append(f"{datasheet}: 機能説明の章番号が版で違う "
                         f"({chapters})——節番号での対応付けはできない")
        if not editions:
            notes.append(f"{datasheet}: 機能説明の節見出しが読めない")
            continue
        zh, en = editions.get("zh", {}), editions.get("en", {})
        # **節番号が言語に依らないのは規約であって保証ではない。** CH32V208 は
        # 英語版が通信系を 2.5.15.1〜6 と入れ子にし、中文版は同じものを 2.5.19〜
        # と平らに振る。番号で対応が取れないだけなのに reference が並ぶと
        # 「その機能が片方の版にしか無い」と読めてしまう。**どちらなのかは題を
        # 突き合わせないと決まらない**ので、断定せず数だけ出す。
        if zh and en and set(zh) != set(en):
            notes.append(f"{datasheet}: 節番号が両版で揃わない"
                         f"（一致 {len(set(zh) & set(en))} / zhのみ "
                         f"{len(set(zh) - set(en))} / enのみ {len(set(en) - set(zh))}）"
                         "——片方に無いのか、番号の振り方が違うだけなのかは"
                         "この表からは決まらない")
        for section in sorted(set(zh) | set(en),
                              key=lambda s: [int(n) for n in s.split(".")]):
            if section in zh and section in en:
                confidence = "confirmed"
                basis = "+".join(f"{datasheet}:{lang}({chapters[lang]})"
                                 for lang in ("zh", "en"))
            else:
                only = "zh" if section in zh else "en"
                confidence = "reference"
                basis = f"{datasheet}:{only}({chapters[only]})"
            rows.append({
                "series": ";".join(sorted(covers[datasheet])),
                "family": family,
                "section": section,
                # 表示は英語版。無ければ空にして、原文は feature_zh に残す。
                "feature": en.get(section, ""),
                "feature_zh": zh.get(section, ""),
                # **その datasheet が覆う series の事実**。型番ごとの有無は
                # 比較表側の差分と併せて読む。
                "granularity": "series",
                "confidence": confidence,
                "basis": basis,
                "datasheet": datasheet,
            })

    rows.sort(key=lambda r: (r["series"], [int(n) for n in r["section"].split(".")]))
    dest = args.out / "features.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    seen = sorted({r["series"] for r in rows})
    from collections import Counter
    print(f"{dest}: {len(rows)} 行  series 群 {len(seen)}  "
          f"{dict(Counter(r['confidence'] for r in rows))}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
