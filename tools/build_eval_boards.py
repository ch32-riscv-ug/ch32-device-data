#!/usr/bin/env python3
"""評価ボードの資料と回路図 → tables/eval_boards.csv

**WCH の配布物ではなく EVT 同梱**なので `documents.csv`（ダウンロード URL 付きの
文書カタログ）には入らない。mirror の `EVT/PUB/` にあり、3 種類が混ざっている:

    EVT/PUB/CH32V30x Evaluation Board Reference-EN.pdf   family の説明書（英）
    EVT/PUB/CH32V30x评估板说明书.pdf                       family の説明書（中）
    EVT/PUB/CH32V30xSCH.pdf                              family の回路図 PDF
    EVT/PUB/SCHPCB/CH32V307VCT6-R1/*.SchDoc              **型番ごと**のボード

最後のものが一番効く——「自分の型番に評価ボードはあるか、版はどれか」に答える。
80 枚あって、`kind = board` の行が持つ。

**ボードの名前は型番とは別の綴りで、そのままでは結合できない。** 80 枚のうち
27 枚が素の一致では外れる。外れ方は5通り:

    CH32V203CCT-R0          温度グレードの桁が落ちている（CCT6）
    CH32F&V208C-R0          CH32F208C と共用の板。F 系は対象外なので V 側だけ採る
    CH32V103C_R0            版の区切りが `_`。package までしか書かない
    CH32V4x7RET-R0          `x` はワイルドカード。V407RET6 と V467RET6 の両方
    CH32H417MEU6-UHSIF-R0   用途違いの派生板（UHSIF 専用）

比較表の略記（`products.csv` の `listed_as`）と同じ形だが、
`build_tables.resolve_full_names` はそのままでは使えない——あちらは末尾の補完を
**2 文字まで**に絞っていて、`CH32V208C` から `CH32V208CBU6` の 3 文字が届かない。
板は package 単位で作られるので**複数の型番に当たるのが正常**で、比較表の
「1 つに寄せたい」とは要件が違う。ここでは 3 文字まで補い、当たった型番は全部返す。

**それでも決められない 3 枚は `parts` を空にする。** `CH32V006K8U6` と
`CH32V203K6T6` は catalogue に無い型番（廃番か綴り違い）、
`CH32X035USBPD_CH211` は companion chip 込みの USB-PD リファレンス板。
無理に近い型番へ寄せると嘘になる。名前は `board` 列に残るので人が見れば辿れる。

`path` は mirror の中での位置。URL は組み立てない——EVT 同梱物の raw URL の形を
確かめていないので、組み立てるのは README 生成側の仕事にする。

実行:
    uv run tools/build_eval_boards.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "board", "parts", "revision", "kind", "path",
           "#", "confidence", "basis"]
# EVT に入っているファイルそのもの。数え違いはあっても解釈の余地は無い。
CONFIDENCE = "confirmed"

PUB = "EVT/PUB"
# CH32V307VCT6-R1 / CH32V103C_R0 / CH32H417MEU6-UHSIF-R0
# 版は `R` + 数字だけ。`-USB` のような尾は版ではないので下の REST で拾う。
BOARD = re.compile(r"^(?P<name>CH32[A-Za-z0-9&]+?)"
                   r"(?:[-_](?P<extra>[A-Za-z][A-Za-z0-9]*))?"
                   r"[-_]R(?P<revision>\d+)$")
# 版が付かない板。`CH32V4x7VET-USB`・`CH32X035USBPD_CH211`
REST = re.compile(r"^(?P<name>CH32[A-Za-z0-9&]+?)[-_](?P<extra>[A-Za-z][A-Za-z0-9]*)$")
# 型番を1つ決めきれない板の名前が指す範囲。**比較表の略記より広く補える**
# 必要がある——`CH32V208C` に対して catalogue は `CH32V208CBU6` で、落ちている
# のは 3 文字（`build_tables.resolve_full_names` は 2 文字まで）。板は package
# 単位で作られるので、同じ package の型番が複数当たるのは正常。
TRAILING = 3
# 説明書と回路図。CH32V006 だけ `-EN` を付けない。
MANUAL_EN = re.compile(r"Evaluation\s+Board\s+Reference(?:-EN)?\.pdf$", re.IGNORECASE)
MANUAL_ZH = re.compile(r"评估板说明书\.pdf$")
SCHEMATIC = re.compile(r"SCH\.pdf$", re.IGNORECASE)
# CH32F208C と共用の板。F 系（Cortex-M3）は対象外なので V 側の名前に直す。
SHARED = re.compile(r"^CH32F&(?P<rest>[A-Za-z0-9]+)$")


def resolve(name: str, parts: set[str]) -> list[str]:
    """ボードの名前が指す型番。決められなければ空。

    `CH32F&V208C` は F 系（Cortex-M3）との共用板。F 系は対象外なので V 側だけ。
    小文字 `x` はワイルドカード（`CH32V4x7RET` は V407 と V467 の両方）。
    末尾は温度グレードの桁や package の綴りが落ちているので 3 文字まで補う。
    **当たった型番は全部返す**——板は package 単位で作られるので、
    `CH32V103C` が C6T6/C8T6/C8U6 を指すのは正しい。
    """
    shared = SHARED.match(name)
    if shared:
        name = "CH32" + shared.group("rest")
    if name in parts:
        return [name]
    pattern = re.compile("^" + name.replace("x", "[A-Za-z0-9]")
                         + f"[A-Za-z0-9]{{0,{TRAILING}}}$")
    return sorted(p for p in parts if pattern.match(p))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    with (args.out / "families.csv").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    with (args.out / "products.csv").open(newline="", encoding="utf-8") as f:
        catalogue = {r["part_number"] for r in csv.DictReader(f)}

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        pub = args.mirrors / family / PUB
        if not pub.is_dir():
            notes.append(f"{family}: {PUB} が無い")
            continue
        for path in sorted(pub.iterdir()):
            if not path.is_file():
                continue
            kind = ("board-manual:en" if MANUAL_EN.search(path.name) else
                    "board-manual:zh" if MANUAL_ZH.search(path.name) else
                    "schematic-pdf" if SCHEMATIC.search(path.name) else None)
            if kind:
                rows.append({"family": family, "board": "", "parts": "",
                             "revision": "", "kind": kind,
                             "path": f"{PUB}/{path.name}"})
        # 型番ごとの板。CH32V003 だけ dir を作らず直下にファイルを置く。
        schpcb = pub / "SCHPCB"
        if not schpcb.is_dir():
            notes.append(f"{family}: {PUB}/SCHPCB が無い")
            continue
        boards = sorted(p for p in schpcb.iterdir() if p.is_dir())
        loose = sorted(p for p in schpcb.iterdir() if p.is_file())
        if loose and not boards:
            # 名前から `-1v1` のような版の尾を落として1枚に畳む。
            flat = sorted({re.sub(r"-\d+v\d+$", "", p.stem) for p in loose})
            boards = []
            for name in flat:
                rows.append(dict(_board_row(family, name, schpcb, catalogue, notes),
                                 path=f"{PUB}/SCHPCB"))
        for board in boards:
            rows.append(_board_row(family, board.name, board, catalogue, notes))

    for row in rows:
        row.setdefault("confidence", CONFIDENCE)
        row.setdefault("basis", f"evt({row['family']}:{PUB})")
    rows.sort(key=lambda r: (r["family"], r["kind"], r["board"], r["path"]))
    dest = args.out / "eval_boards.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    tally = collections.Counter(r["kind"] for r in rows)
    unresolved = sum(1 for r in rows if r["kind"] == "board" and not r["parts"])
    print(f"{dest}: {len(rows)} 行  {dict(tally)}"
          f"  型番を決められない board {unresolved}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


def _board_row(family: str, name: str, where: Path,
               catalogue: set[str], notes: list[str]) -> dict:
    found = BOARD.match(name) or REST.match(name)
    stem = found.group("name") if found else name
    revision = found.groupdict().get("revision") or "" if found else ""
    extra = (found.groupdict().get("extra") or "") if found else ""
    parts = resolve(stem, catalogue)
    if not parts:
        notes.append(f"{family}: ボード {name} の型番を決められない"
                     f"（{stem} に当たる型番が catalogue に無い）")
    return {
        "family": family,
        "board": name,
        "parts": ";".join(parts),
        # `R1` の 1。`USB` のように版でないものはそのまま置く。
        "revision": revision,
        # 用途違いの派生板は名前の途中にそれが出る（`-UHSIF-`）。
        "kind": "board-variant" if extra else "board",
        "path": f"{PUB}/SCHPCB/{name}" if where.is_dir() else f"{PUB}/SCHPCB",
    }


if __name__ == "__main__":
    raise SystemExit(main())
