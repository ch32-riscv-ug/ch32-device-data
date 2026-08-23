#!/usr/bin/env python3
"""割り込みベクタ表 → tables/interrupts.csv

**出所は reference manual ではなく EVT の device header。** ヘッダーの
`IRQn_Type` 列挙が番号・名前・1行説明を全部持っていて、コンパイルされる側の
定義そのものなので、RM の表を読むより確かで安い（worklist の A9 を
「RM 側・コスト高につき後回し」としていたのは、この材料を見落としていた）。

    typedef enum IRQn
    {
      NonMaskableInt_IRQn  = 2,    /* 2 Non Maskable Interrupt   */
      ...
    #ifdef CH32V30x_D8
      USBHS_IRQn           = 84,   /* USBHS global Interrupt     */
    #elif defined (CH32V30x_D8C)
      ...
    #endif
    } IRQn_Type;

**列挙の中身は variant で変わる。** CH32V20x は `_D6`/`_D8`/`_D8W`、CH32V30x は
`_D8`/`_D8C` で番号ごと入れ替わるので、`#if` の条件をそのまま `condition` 列に
持つ。どの型番がその macro を立てるかは `evt_variants.csv` が持っていて、
`clock_configs.condition` と同じ辿り方になる。

例外の番号（NMI・Break Point・Ecall）も同じ列挙にいる。`kind` 列で
`exception` と `irq` を分ける——RISC-V では前者は mcause の例外側で、
PFIC の割り込み番号とは意味が違う。

実行:
    uv run tools/build_interrupts.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "number", "name", "kind", "description", "condition",
           "#", "confidence", "basis"]
# EVT のヘッダーだけが言う。RM の表が second reading になる。
CONFIDENCE = "reference"

ENUM = re.compile(r"typedef\s+enum\s+IRQn\b(?P<body>.*?)\}\s*IRQn_Type\s*;", re.S)
#   USBHS_IRQn                  = 84,      /* USBHS global Interrupt  */
ENTRY = re.compile(r"^\s*(?P<name>\w+)_IRQn\s*=\s*(?P<number>\d+)\s*,?"
                   r"(?:\s*/\*(?P<description>.*?)\*/)?\s*$")
# 例外と割り込みの境目は**ヘッダー自身が横断幕で書いている**ので、名前を
# 並べずにそれを読む。名前で分けると CH32H417 の `SysTick0`/`SysTick1`（2 コア）や
# `HardFault`（他 family の `EXC` と同じ 3 番）を取りこぼす。
BANNER = re.compile(r"RISC-V\s+(?P<which>Processor\s+Exceptions|specific\s+Interrupt)"
                    r"\s+Numbers")
# **境目の番号は family で違う。** ほとんどは 16 番から周辺割り込みだが、
# CH32H417 は 32 番からで、16〜28 は IPC（コア間通信）と HSEM——2 コアなので
# プロセッサ側の枠がその分広い。番号で決め打つと 5 本を取り違える。
# 決め打つ代わりに「例外の番号は全部、割り込みの番号より小さい」ことだけ検査する。
IF = re.compile(r"^\s*#\s*(?P<kind>ifdef|ifndef|if|elif|else|endif)\b\s*(?P<rest>.*)$")
# `#if defined (CH32V30x_D8C)` から macro だけ取る。
MACRO = re.compile(r"\b(CH32[A-Za-z0-9_]+)\b")
# 説明の頭に番号が繰り返されることがある（"2 Non Maskable Interrupt"）。
LEADING_NUMBER = re.compile(r"^(?P<number>\d+)\s+")


def find_header(family_dir: Path) -> Path | None:
    """EVT の device header。名前の綴りと大小が family ごとに違う。"""
    found = sorted(family_dir.glob("EVT/**/Peripheral/inc/ch32*.h"))
    plain = [p for p in found
             if re.fullmatch(r"ch32[a-z0-9]+\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else (found[0] if found else None)


def condition_of(stack: list[str | None]) -> str:
    """いま開いている `#if` の条件を1つの文字列にする。

    入れ子は実際には出てこないが、出たときに黙って落とさないよう `+` で繋ぐ。
    `#else` は「上のどれでもない」なので macro 名では書けず、`!` を付ける。
    """
    return "+".join(c for c in stack if c)


def read_enum(header: Path, notes: list[str]) -> list[dict]:
    """`IRQn_Type` の中身を、`#if` の条件つきで読む。"""
    text = header.read_text(errors="ignore")
    found = ENUM.search(text)
    if not found:
        notes.append(f"{header.name}: IRQn_Type の列挙が見つからない")
        return []
    rows: list[dict] = []
    stack: list[str | None] = []
    branches: list[list[str]] = []  # `#else` が否定する条件を段ごとに覚える
    kind = "exception"
    for line in found.group("body").splitlines():
        banner = BANNER.search(line)
        if banner:
            kind = ("exception" if banner.group("which").startswith("Processor")
                    else "irq")
            continue
        directive = IF.match(line)
        if directive:
            # `kind`（例外/割り込みの別）とは別物なので名前を分ける。
            opener, rest = directive.group("kind"), directive.group("rest")
            if opener in ("ifdef", "ifndef", "if"):
                macros = MACRO.findall(rest)
                stack.append(macros[0] if macros else None)
                branches.append(list(macros[:1]))
            elif opener in ("elif", "else") and stack:
                macros = MACRO.findall(rest)
                if opener == "elif" and macros:
                    stack[-1] = macros[0]
                    branches[-1].append(macros[0])
                else:
                    seen = branches[-1] if branches else []
                    stack[-1] = "+".join(f"!{m}" for m in seen) or None
            elif opener == "endif":
                if stack:
                    stack.pop()
                    branches.pop()
            continue
        entry = ENTRY.match(line)
        if not entry:
            continue
        number = int(entry.group("number"))
        description = (entry.group("description") or "").strip()
        # 「84 USBHS global Interrupt」のように番号が説明の頭で繰り返される。
        repeated = LEADING_NUMBER.match(description)
        if repeated and int(repeated.group("number")) == number:
            description = description[repeated.end():].strip()
        rows.append({
            "number": number,
            "name": entry.group("name"),
            "kind": kind,
            "description": description,
            "condition": condition_of(stack),
        })
    return rows


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
        header = find_header(args.mirrors / family)
        if header is None:
            notes.append(f"{family}: device header が無い")
            continue
        found = read_enum(header, notes)
        if not found:
            continue
        # 2 つの群は番号で綺麗に分かれているはず。混ざったら横断幕の読み違い。
        exceptions = [r["number"] for r in found if r["kind"] == "exception"]
        irqs = [r["number"] for r in found if r["kind"] == "irq"]
        if exceptions and irqs and max(exceptions) >= min(irqs):
            notes.append(f"{family}: 例外の最大 {max(exceptions)} が割り込みの最小 "
                         f"{min(irqs)} 以上——横断幕の読み方が違う")
        elif irqs:
            notes.append(f"{family}: 周辺割り込みは {min(irqs)} 番から")
        # 同じ番号が条件違いで複数あるのは正常（variant で入れ替わる）。
        # 同じ条件で番号が重なっていたら読み違えているので言う。
        seen: dict[tuple[int, str], str] = {}
        for row in found:
            key = (row["number"], row["condition"])
            if key in seen and seen[key] != row["name"]:
                notes.append(f"{family}: 番号 {row['number']} が "
                             f"{seen[key]} と {row['name']} で重なる"
                             f"（condition={row['condition'] or 'なし'}）")
            seen[key] = row["name"]
            rows.append({**row, "family": family,
                         "confidence": CONFIDENCE,
                         "basis": f"evt({header.name})"})

    rows.sort(key=lambda r: (r["family"], r["number"], r["condition"]))
    dest = args.out / "interrupts.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    seen_families = sorted({r["family"] for r in rows})
    conditional = sum(1 for r in rows if r["condition"])
    print(f"{dest}: {len(rows)} 行  family {len(seen_families)}"
          f"  うち variant 条件つき {conditional}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
