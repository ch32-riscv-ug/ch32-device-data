#!/usr/bin/env python3
"""周辺クロックの enable bit → tables/clock_enables.csv

**family × peripheral → どの RCC レジスタの何 bit か**（consumer の依頼 R-26 参考）。
consumer 側は `CH32_RCC_APB1_TIM4` のような define を family ごとに手書きしていて、
family を足すたびに手作業になっていた。`clock_symbols.csv` に `RCC_AFIOEN` だけが
ある形式を、全 peripheral ぶん揃える。

**出所は EVT の `ch32*_rcc.h`**。`RCC_<bus>PeriphClockCmd()` に渡す定数が
peripheral ごとの bit で、bus の名前がレジスタを言う:

    RCC_AHBPeriph_USBPD  ((uint32_t)0x00020000)   → RCC->AHBPCENR bit17
    RCC_HBPeriph_USBPD   ((uint32_t)0x00020000)   → RCC->HBPCENR  bit17（L103/V205）
    RCC_HB1Periph_TIM2   …                        → RCC->HB1PCENR（X315/H417）

bus の呼び名は family で違う（AHB/APB1/APB2 と HB/PB1/PB2 と HB/HB1/HB2）。
`RCC_<bus>PeriphClockCmd` が `RCC-><bus>PCENR` へ書くことは 8 family の rcc.c で
確かめた（対応は名前どおりで例外なし）。レジスタのオフセットは device header の
`RCC_TypeDef` から、base は `RCC_BASE` から取る。

**RM のレジスタ表と突き合わせる。** `RCC_HBPCENR` の `USBPDEN` のように RM は
`<peripheral>EN` と綴るので、bit 位置が一致すれば confirmed、無ければ reference、
食い違えば conflict。GPIO だけ綴りが違い（EVT `GPIOA`、RM `IOPAEN`）、それは
別名として引く。

実行:
    uv run tools/build_clock_enables.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_addresses  # noqa: E402
import extract_registers  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "peripheral", "bus", "register", "offset", "address", "bit",
           "mask", "macro", "#", "confidence", "basis"]

PERIPH = re.compile(r"^\s*#define\s+(?P<macro>RCC_(?P<bus>[A-Z0-9]+)Periph_(?P<name>\w+))\s+"
                    r"\(\s*\(\s*u?int\d+_t\s*\)\s*(?P<mask>0[xX][0-9A-Fa-f]+)\s*\)", re.M)
STRUCT = re.compile(r"typedef\s+struct\s*\{(?P<body>[^{}]*?)\}\s*RCC_TypeDef\s*;", re.S)
MEMBER = re.compile(r"(?:__I?O?\s+|volatile\s+|const\s+)*"
                    r"u?int(?P<width>8|16|32|64)_t\s+(?P<name>\w+)"
                    r"(?:\s*\[\s*(?P<count>\d+)\s*\])?\s*;")
# RM 側の field 名。EVT の GPIOA は RM では IOPA。
RM_ALIAS = {"GPIO": "IOP"}


def find_header(family_dir: Path, pattern: str) -> Path | None:
    found = sorted(family_dir.glob(f"EVT/**/Peripheral/inc/{pattern}"))
    plain = [p for p in found if re.fullmatch(r"ch32[a-z0-9]+(_rcc)?\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else (found[0] if found else None)


def rcc_offsets(text: str) -> dict[str, int]:
    found = STRUCT.search(text)
    if not found:
        return {}
    offsets: dict[str, int] = {}
    offset = 0
    for line in found.group("body").splitlines():
        m = MEMBER.search(line)
        if not m:
            continue
        offsets[m.group("name")] = offset
        offset += int(m.group("width")) // 8 * int(m.group("count") or 1)
    return offsets


def rm_fields(family_dir: Path) -> tuple[dict, str]:
    """{(register, field): bit} — RCC の *PCENR だけ。"""
    paths = sorted(family_dir.glob("datasheet_zh/*RM.PDF"))
    if not paths:
        return {}, ""
    fields, _ = extract_registers.extract(paths[0], None)
    out: dict = {}
    for f in fields:
        if f["register"].startswith("RCC_") and f["register"].endswith("PCENR"):
            out.setdefault((f["register"], f["field"]), f["bit_offset"])
    return out, paths[0].name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()

    with paths.table("families").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        family_dir = args.mirrors / family
        rcc_h = find_header(family_dir, "ch32*_rcc.h")
        dev_h = find_header(family_dir, "ch32*.h")
        if rcc_h is None or dev_h is None:
            notes.append(f"{family}: rcc.h か device header が無い")
            continue
        dev_text = dev_h.read_text(errors="ignore")
        offsets = rcc_offsets(dev_text)
        base = extract_addresses.bases(dev_text.splitlines()).get("RCC_BASE")
        manual, manual_name = rm_fields(family_dir)
        for m in PERIPH.finditer(rcc_h.read_text(errors="ignore")):
            name, bus, mask = m.group("name"), m.group("bus"), int(m.group("mask"), 16)
            if name.upper() == "ALL" or mask == 0:
                continue
            register = f"{bus}PCENR"
            if register not in offsets:
                notes.append(f"{family}: {m.group('macro')} の bus {bus} に当たる "
                             f"{register} が RCC_TypeDef に無い")
                continue
            lo = (mask & -mask).bit_length() - 1
            hi = mask.bit_length() - 1
            bit = f"{lo}" if lo == hi else f"{hi}:{lo}"
            confidence, basis = "reference", [f"evt({rcc_h.name}+{dev_h.name})"]
            stem = name
            for evt_name, rm_name in RM_ALIAS.items():
                if stem.startswith(evt_name):
                    stem = rm_name + stem[len(evt_name):]
            said = manual.get((f"RCC_{register}", f"{stem}EN"))
            if said is not None and lo == hi:
                if said == lo:
                    confidence = "confirmed"
                    basis.append(f"rm({manual_name})")
                else:
                    confidence = "conflict"
                    basis.append(f"!rm({manual_name})(=bit{said})")
            rows.append({
                "family": family,
                "peripheral": name,
                "bus": bus,
                "register": register,
                "offset": f"{offsets[register]:#04x}",
                "address": f"{base + offsets[register]:#010x}" if base is not None else "",
                "bit": bit,
                "mask": f"{mask:#x}",
                "macro": m.group("macro"),
                "confidence": confidence,
                "basis": "+".join(basis),
            })

    rows.sort(key=lambda r: (r["family"], r["register"], int(r["mask"], 16)))
    dest = paths.table("clock_enables", args.out)
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{dest}: {len(rows)} 行  family {len({r['family'] for r in rows})}  {dict(tally)}",
          file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    for r in [r for r in rows if r["confidence"] == "conflict"][:12]:
        print(f"  ! {r['family']} {r['register']}.{r['peripheral']} evt=bit{r['bit']} {r['basis']}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
