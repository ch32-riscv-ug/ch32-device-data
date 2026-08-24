#!/usr/bin/env python3
"""機能から製品を探すための索引 → tables/feature_tags.csv

`features.csv` は datasheet の節見出しをそのまま持つので、綴りが版と family で
揺れる——`General DMA Controller` と `General-purpose DMA Controller` と
`General DMA controller` は同じ DMA。検索の入口にはこれを揃えた語が要る
（worklist の B5「org TOP の機能から探す」）。

**揃え方の一段目は資料自身が書いている。** 見出しの多くが括弧の中に略語を持つ:

    Analog-to-digital Converter (ADC)              → ADC
    LCD-TFT Display Controller (LTDC)              → LTDC
    Universal Serial Bus USB2.0 ... (USBHS)        → USBHS

146 種のうち 82 種がこれで決まる。残りと、資料側の綴り揺れ（`FPIC` と `PFIC` は
同じもの）だけを `curated/feature-tags.json` で決める。

**「役に立つ機能か」は判断しない。** 機能でないもの（群見出しの
`Communication interface`、CPU そのものの `RISC-V*`）だけ除き、あとは全部タグを
付ける。全 family が持つ機能かどうかは件数を見れば分かることで、こちらが
間引くと「無い」と読めてしまう。

**未登録の見出しは黙って捨てず数える。** 資料が新しい周辺を足したときに
気付けるようにするため。`parent` は上位のまとめで、`USBHS` は `USB` にも入る
——「USB が使えるか」で探す人と「USBHS が要る」人の両方に答える。

**節見出しだけでは偽陽性が出る。** 機能説明の章は datasheet 単位なので、
`CH32V20x_30xDS0` の Ethernet の節は V303/V305/V307/V317 の全部に付いてしまう
——**V303 に Ethernet は無い**。比較表はそこを型番単位で書き分けているので、
**その機能の行を持っているなら比較表を採る**:

    比較表にその機能のラベルがある   → 型番単位。値がある型番だけ載せる
                                       （無いことは `-` と書かれ、属性にならない）
    比較表にラベルが無い             → 節見出しに戻る。datasheet 単位

`precision` 列がどちらの読みかを言う。64 タグのうち 46 が比較表側で決まり、
残る 18 は比較表に行が無い——**そしてそれは CRC・DMA・EXTI・GPIO・PFIC・TIM の
ような「全 family が持つ」もの**で、比較表が差の無い行を持たないのと整合する。

ラベルとタグの対応は表を持たない。**タグ名がスラグのトークンとして現れる**
（`ETHERNET` は `communicationinterfaces_ethernet`）ので `_` で切って突き合わせる。
部分一致にしないのは `qspi` が `spi` に当たらないようにするため。

実行:
    uv run tools/build_feature_tags.py [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CURATED = REPO / "curated" / "feature-tags.json"

COLUMNS = ["tag", "parent", "series", "family", "precision", "features",
           "features_zh", "sections", "#", "confidence", "basis"]

# 括弧の中の略語。`(USBFS/OTG_FS)` や `(MAC+PHY)` も1つとして採る。
PAREN = re.compile(r"[（(]([A-Z][A-Za-z0-9+/_. ]{1,16})[)）]")
# 括弧の中が説明ごと入っていて、**頭が略語**の形。中文版の
# `串行2线调试接口（SDI Serial Debug Interface）` がこれ。2文字目以降も大文字だけ
# を要求するので、`(Cyclic Redundancy Check)` の `Cyclic` は当たらない。
PAREN_LEAD = re.compile(r"[（(]([A-Z][A-Z0-9+/_]{1,11})(?:\s|[)）])")
# CPU の節（`QingKe RISC-V4C Processor`）。core と ISA は cores.csv が持つ。
PROCESSOR = re.compile(r"RISC-V", re.IGNORECASE)


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def tags_for(title: str, curated: dict, unknown: collections.Counter) -> list[str]:
    """見出しが指す検索語。決められなければ空にして数える。"""
    flat = squash(title)
    if flat in curated["excluded"]:
        return []
    if PROCESSOR.search(title):
        # 綴りが `QingKe RISC-V4C` と `RISC-V3A` で違うので、まとめて弾く。
        return []
    named = curated["titles"].get(flat)
    if named:
        return [named] if isinstance(named, str) else list(named)
    found = PAREN.findall(title) or PAREN_LEAD.findall(title)
    if found:
        candidate = found[-1].strip()
        if candidate in curated["excluded"]:
            return []
        return [curated["aliases"].get(candidate, candidate)]
    unknown[title] += 1
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    curated = json.loads(CURATED.read_text(encoding="utf-8"))
    for key in ("aliases", "titles", "excluded", "parents"):
        curated[key] = {k: v for k, v in curated[key].items() if k != "_comment"}

    with (args.out / "features.csv").open(newline="", encoding="utf-8") as f:
        features = list(csv.DictReader(f))
    with (args.out / "series.csv").open(newline="", encoding="utf-8") as f:
        family_of = {r["series"]: r["family"] for r in csv.DictReader(f)}
    with (args.out / "products.csv").open(newline="", encoding="utf-8") as f:
        catalogue = list(csv.DictReader(f))
    with (args.out / "product_attributes.csv").open(newline="", encoding="utf-8") as f:
        attributes = list(csv.DictReader(f))

    # 型番 → その型番が載る datasheet、と series。
    sheet_of = {r["part_number"]: r["datasheet"] for r in catalogue}
    series_of = {r["part_number"]: r["series"] for r in catalogue}
    # datasheet → 比較表が持つラベルのトークン集合。「その機能の行があるか」。
    tokens_in: dict[str, set[str]] = collections.defaultdict(set)
    # (series, トークン) → その series の型番が実際に値を持つか。
    has: set[tuple[str, str]] = set()
    for row in attributes:
        sheet = sheet_of.get(row["part_number"])
        series = series_of.get(row["part_number"])
        for token in row["attribute"].split("_"):
            if sheet:
                tokens_in[sheet].add(token)
            if series:
                has.add((series, token))

    # (tag, series) ごとに、どの見出しから来たかを集める。
    #
    # **series は1つずつに展開する。** `features.csv` の `series` 列は
    # 「その datasheet が覆う群」で、CH32V203 は CH32V203DS0 と CH32V205DS0 の
    # 両方に載るため `CH32V203` と `CH32V203;CH32V205` の2つの群に現れる。
    # 索引としては「どの series が持つか」が要るので、群のままだと同じ series が
    # 2 行に割れて数えられない。
    found: dict[tuple[str, str], dict] = {}
    unknown: collections.Counter = collections.Counter()
    for row in features:
        title = row["feature"] or row["feature_zh"]
        if not title:
            continue
        for tag in tags_for(title, curated, unknown):
          for series in (s.strip() for s in row["series"].split(";") if s.strip()):
            key = (tag, series)
            entry = found.setdefault(key, {
                "tag": tag,
                "parent": curated["parents"].get(tag, ""),
                "series": series,
                "family": family_of.get(series, row["family"]),
                "titles": set(),
                "titles_zh": set(),
                "sections": set(),
                "sheets": set(),
                # 見出しが両版に在れば confirmed。片方だけなら reference。
                "confidence": row["confidence"],
                "datasheets": set(),
            })
            # 表示は英語版、原文は `_zh` 側に置く（表全体の作法）。
            if row["feature"]:
                entry["titles"].add(row["feature"])
            if row["feature_zh"]:
                entry["titles_zh"].add(row["feature_zh"])
            entry["sheets"].add(row["datasheet"])
            entry["sections"].add(row["section"])
            entry["datasheets"].add(row["datasheet"])
            # 同じタグに複数の節が寄るとき、1つでも片言語なら弱いほうを採る。
            if row["confidence"] == "reference":
                entry["confidence"] = "reference"

    rows = []
    dropped = collections.Counter()
    for entry in found.values():
        # 比較表がこの機能の行を持っているなら、そちらが型番単位で精密。
        token = entry["tag"].lower().replace("-", "")
        listed = any(token in tokens_in.get(sheet, set()) for sheet in entry["sheets"])
        if listed:
            if (entry["series"], token) not in has:
                # 比較表に行はあるのに、この series は値を持たない＝`-`（無い）。
                dropped[entry["tag"]] += 1
                continue
            precision = "part"
        else:
            precision = "datasheet"
        rows.append({
            "precision": precision,
            "tag": entry["tag"],
            "parent": entry["parent"],
            "series": entry["series"],
            "family": entry["family"],
            # 元の見出しを残す。綴りが揺れているので複数になることがある。
            "features": ";".join(sorted(entry["titles"])),
            "features_zh": ";".join(sorted(entry["titles_zh"])),
            "sections": ";".join(sorted(entry["sections"],
                                        key=lambda s: [int(n) for n in s.split(".")])),
            "confidence": entry["confidence"],
            "basis": "+".join(f"features({d})" for d in sorted(entry["datasheets"])),
        })
    rows.sort(key=lambda r: (r["tag"], r["series"]))

    dest = args.out / "feature_tags.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    tags = sorted({r["tag"] for r in rows})
    precise = sum(1 for r in rows if r["precision"] == "part")
    print(f"{dest}: {len(rows)} 行  タグ {len(tags)} 種"
          f"  比較表で決めた {precise} / 節見出しのみ {len(rows) - precise}",
          file=sys.stderr)
    if dropped:
        print("  - 節見出しにはあるが比較表が「無い」と書いている（偽陽性を外した）:",
              file=sys.stderr)
        for tag, count in dropped.most_common():
            print(f"      {tag} ×{count} series", file=sys.stderr)
    if unknown:
        print(f"  - **語彙に無い見出し {len(unknown)} 種**"
              "（curated/feature-tags.json に足すか excluded にする）:",
              file=sys.stderr)
        for title, count in unknown.most_common():
            print(f"      {title}  ×{count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
