#!/usr/bin/env python3
"""SysTick の register 配置を family ごとに → tables/systick.csv

EVT の `core_riscv.h` が `SysTick_Type` として宣言している構造体を読む。**11 family
は同じ形だが CH32V103 だけ違い、その違いが millis()/micros()/delay() を黙って
壊す**という報告を受けて先出しした（R-24追補3 の E-1）。

    CH32V103   CTLR / CNTL0..3 / CNTH0..3 / CMPLR0..3 / CMPHR0..3  ← 全部 uint8_t
    他11family CTLR / SR / CNT / CMP

違いは3つある。

**status register が無い。** 他 family の `SR` に当たるものが CH32V103 には無く、
reference manual の表9-6 も CTLR/CNTL/CNTH/CMPLR/CMPHR の5本しか挙げない。

**compare が +0x0C と +0x10 に割れる。** 他 family の `CMP` は +0x10 にあるので、
+0x10 へ比較値を書くと **CH32V103 では上位32bit を書く**ことになり、一致しない。

**8bit 単位でしか書けない。** reference manual が両言語で
「此寄存器可按 8/16/32 位读取，但是只能以8位进行修改」/ "can be read in
8-bit/16-bit/32-bit mode, but can only be modified in 8-bit mode" と書いており、
WCH 自身が 16 個の `uint8_t` として宣言しているのはそのためである。32bit で書いた
比較値は入らない。`write_bits` 列がこれを言う。

CNT の幅も一定ではない（64bit: L103/V20x/V30x/X035、32bit: それ以外）。
CH32H417 は status を `ISR` と呼び、`only for SysTick0` というコメントがついている
（双核なので SysTick が複数ある）。

bit 定義はここに入れていない。`core_riscv.h` はどの family でも `STK_*` の bit を
1つも定義しておらず、reference manual にしか無い。CH32V103 の分は
docs/register-map-survey.ja.md に記録した。

実行:
    uv run tools/build_systick.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "block", "register", "offset", "address",
           "width_bits", "write_bits", "purpose", "note",
           "#", "confidence", "basis"]
BASIS = "evt(core_riscv.h)"
# 1資料のみ。reference manual の STK 章が second reading になる。
CONFIDENCE = "reference"

# 本体に波括弧を含めない。含めると直前の PFIC_Type の typedef から始まってしまい、
# PFIC の register が SysTick の配置として出てくる。
STRUCT = re.compile(r"typedef\s+struct\s*\{(?P<body>[^{}]*?)\}\s*SysTick_Type\s*;", re.S)
MEMBER = re.compile(r"(?:__I?O?\s+|volatile\s+|const\s+)*"
                    r"u?int(?P<width>8|16|32|64)_t\s+(?P<name>\w+)"
                    r"(?:\s*\[\s*(?P<count>\d+)\s*\])?\s*;")
# CH32H417 は SysTick を2本持つ（SysTick0 と SysTick1、双核なのでコアごと）。
# 1本だけ読むと SysTick1 が無いことになる。
POINTER = re.compile(r"#define\s+(?P<block>SysTick\d*)\s+\(\(\s*SysTick_Type\s*\*\s*\)\s*"
                     r"(?P<base>0[xX][0-9A-Fa-f]+|\w+)\s*\)")
# メンバーに付いた行末コメント。CH32H417 は ISR に "only for SysTick0" と書いていて、
# これは2本目には当てはまらないという意味なので落とせない。
TRAILING = re.compile(r"//\s*(?P<note>.+?)\s*$|/\*\s*(?P<block_note>.+?)\s*\*/")

# メンバー名から役割へ。名前が役割を言っているので推測は要らない。
PURPOSE = [
    (re.compile(r"^CTLR$"), "control"),
    (re.compile(r"^(SR|ISR)$"), "status"),
    (re.compile(r"^CNTL\d?$"), "counter_low"),
    (re.compile(r"^CNTH\d?$"), "counter_high"),
    (re.compile(r"^CNT$"), "counter"),
    (re.compile(r"^CMPLR\d?$"), "compare_low"),
    (re.compile(r"^CMPHR\d?$"), "compare_high"),
    (re.compile(r"^CMP$"), "compare"),
    (re.compile(r"^RESERVED"), "reserved"),
]


def purpose_of(name: str) -> str:
    for pattern, label in PURPOSE:
        if pattern.match(name):
            return label
    return ""


def read_family(header: Path) -> tuple[list[tuple[str, int]], list[dict]]:
    """(block名とbase address のリスト, register 行) を返す。"""
    text = header.read_text(errors="ignore")
    found = STRUCT.search(text)
    if not found:
        return [], []
    blocks: list[tuple[str, int]] = []
    for m in POINTER.finditer(text):
        base = m.group("base")
        if base.lower().startswith("0x"):
            blocks.append((m.group("block"), int(base, 16)))

    # CH32V103 は 32bit register を 4 つの uint8_t に分けて宣言する。連続する
    # NAME0..3 は 1 本の register なので畳む。畳まないと「8bit register が16本」
    # に見え、reference manual の表9-6（5本）と突き合わせられない。
    members: list[tuple[str, int, int, str]] = []  # (name, offset, width, note)
    offset = 0
    for line in found.group("body").splitlines():
        m = MEMBER.search(line)
        if not m:
            continue
        width = int(m.group("width"))
        count = int(m.group("count") or 1)
        trailing = TRAILING.search(line[m.end():])
        note = ""
        if trailing:
            note = trailing.group("note") or trailing.group("block_note") or ""
        members.append((m.group("name"), offset, width, note))
        offset += width // 8 * count

    rows: list[dict] = []
    index = 0
    while index < len(members):
        name, at, width, note = members[index]
        stem = re.sub(r"\d$", "", name)
        run = [members[index]]
        while (index + len(run) < len(members)
               and re.sub(r"\d$", "", members[index + len(run)][0]) == stem
               and members[index + len(run)][2] == width
               and name[-1:].isdigit()):
            run.append(members[index + len(run)])
        index += len(run)
        if purpose_of(stem) == "reserved":
            continue
        rows.append({
            "register": stem,
            "offset": f"{at:#04x}",
            "width_bits": width * len(run),
            "write_bits": width,
            "purpose": purpose_of(stem),
            "note": note,
            "_offset": at,
        })
    return blocks, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    with (args.out / "families.csv").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        headers = sorted((args.mirrors / family).glob("EVT/**/core_riscv.h"))
        if not headers:
            notes.append(f"{family}: core_riscv.h が無い")
            continue
        blocks, found = read_family(headers[0])
        if not found:
            notes.append(f"{family}: SysTick_Type が読めない")
            continue
        if not blocks:
            notes.append(f"{family}: SysTick の base address が読めない")
            blocks = [("SysTick", None)]
        if len(blocks) > 1:
            notes.append(f"{family}: SysTick が {len(blocks)} 本ある "
                         f"({', '.join(f'{n}@{b:#x}' for n, b in blocks)})")
        for block, base in blocks:
            for row in found:
                at = row["_offset"]
                rows.append({"family": family, "block": block,
                             **{k: v for k, v in row.items() if k != "_offset"},
                             "address": "" if base is None else f"{base + at:#010x}",
                             "confidence": CONFIDENCE, "basis": BASIS})

    dest = args.out / "systick.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    print(f"{dest}: {len(rows)} 行", file=sys.stderr)

    shapes: dict[tuple, list[str]] = {}
    for family in dict.fromkeys(r["family"] for r in rows):
        first = next(r["block"] for r in rows if r["family"] == family)
        shape = tuple((r["register"], r["offset"], r["width_bits"], r["write_bits"])
                      for r in rows
                      if r["family"] == family and r["block"] == first)
        shapes.setdefault(shape, []).append(family)
    print(f"  配置の種類: {len(shapes)}", file=sys.stderr)
    for shape, members in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
        print(f"    {' '.join(members)}", file=sys.stderr)
        print("      " + "  ".join(
            f"{name}@{at}:{w}b" + (f"(w{ww})" if ww != w else "")
            for name, at, w, ww in shape), file=sys.stderr)
    for note in notes:
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
