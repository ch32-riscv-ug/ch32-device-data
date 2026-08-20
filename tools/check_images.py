#!/usr/bin/env python3
"""READMEが参照する画像の必要一覧と、各リポジトリでの有無を報告する。

READMEは画像の存在を確認してから節を出すのではなく、**決まった名前の画像を
常に参照**します。よって「どの名前の画像を作ればよいか」はデータから機械的に
決まります。このツールがその一覧です。

  image/architecture_<SERIES>.png       シリーズごとの内部ブロック図
  image/pinout_<PART>_<PACKAGE>.png     ピン配置図。ピン配置が実際に異なる
                                        単位で1枚（同一配置の型番は共有し、
                                        名前はその中で最小の型番を使う）

パッケージの外形寸法図はチップに依らないため各リポジトリには置かず、
WCH-common に1枚ずつ置いて全リポジトリから参照します。

  WCH-common/image/package_<PACKAGE>.png

実行: uv run python tools/check_images.py [--missing]
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent


def load(name):
    with (REPO / "tables" / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pinout_groups():
    """{(family, filename): [part_number, ...]} — 実際に異なる配置ごとに1枚。"""
    pads = defaultdict(dict)
    for r in load("pins"):
        pads[r["part_number"]][r["pin"]] = r["pad"]
    groups = defaultdict(list)
    for p in load("products"):
        signature = tuple(sorted(pads[p["part_number"]].items()))
        groups[(p["family"], p["series"], p["package"], signature)].append(
            p["part_number"])
    out = {}
    for (family, _, package, _), parts in groups.items():
        lead = sorted(parts)[0]
        out[(family, f"pinout_{lead}_{package}.png")] = sorted(parts)
    return out


def required():
    """{family: {filename: 説明}}"""
    need = defaultdict(dict)
    for s in load("series"):
        need[s["family"]][f"architecture_{s['series']}.png"] = (
            f"{s['series']} internal block diagram")
    for (family, name), parts in pinout_groups().items():
        need[family][name] = "pinout: " + ", ".join(parts)
    for p in load("packages"):
        need["WCH-common"][f"package_{p['package']}.png"] = (
            f"{p['package']} package outline"
            + (f" ({p['body_size']})" if p.get("body_size") else ""))
    return need


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--missing", action="store_true",
                    help="未作成のファイルだけを出す")
    args = ap.parse_args()

    need = required()
    total = missing_total = 0
    for family in sorted(need):
        image_dir = MIRRORS / family / "image"
        have = {p.name for p in image_dir.iterdir()} if image_dir.is_dir() else set()
        rows = sorted(need[family].items())
        missing = [(n, d) for n, d in rows if n not in have]
        total += len(rows)
        missing_total += len(missing)
        extra = sorted(h for h in have
                       if h not in need[family] and not h.startswith("."))
        print(f"== {family}: 必要 {len(rows)} / 未作成 {len(missing)}")
        for name, description in (missing if args.missing else rows):
            mark = " " if name in have else "*"
            print(f"  {mark} {name:44} {description}")
        if extra:
            print(f"    参照されない既存ファイル: {', '.join(extra)}")
    print(f"\n合計: 必要 {total} / 未作成 {missing_total}")


if __name__ == "__main__":
    main()
