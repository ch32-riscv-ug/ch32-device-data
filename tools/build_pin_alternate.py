#!/usr/bin/env python3
"""AF番号をどこに書くか → tables/pin_alternate.csv

**CH32V205・CH32X315・CH32H417はAFIO remapを持たない。** 経路の選び方が別で、
ピンごとに4bitのAF番号を書く。`pin_functions.csv`はその番号を`route = af-N`として
持っているのに（4412行）、**Nの書き込み先をどの表も言っていなかった**のがこの表を
足した理由（F-12。F-10「V205とX315のRMから経路が0件」の続き）。

    remap を持つ 9 family    AFIO->PCFR1 の周辺機器ごとのフィールドに経路番号
    AF を持つ 3 family       AFIO->GPIOx_AFLR / AFHR のピンごとの4bitにAF番号

consumer側の症状は「CH32V205のPWMが全滅する」。`remap-N`しか見ていないと
`af-N`の行が読み飛ばされる。

規則はEVTの`GPIO_PinAFConfig()`がそのまま書いている:

    if(GPIO_PinSource >= 0x08) tmp = GPIO_PinSource - 0x08; else tmp = GPIO_PinSource;
    AFIO->GPIOA_AFHR &= ~(0xF << (tmp << 2));      /* pin 8-15 は AFHR */
    AFIO->GPIOA_AFLR &= ~(0xF << (tmp << 2));      /* pin 0-7 は AFLR */

**この形を読んで確かめる**（幅0xF・シフト`<< 2`・境界`0x08`）ので、4bitずつという
のは決め打ちではない。番地は`extract_addresses`が構造体のメンバーオフセットから
解く——**familyごとに違う**。CH32H417のAFIOは`PCFR1`の直後にAF registerが並ぶので
`GPIOA_AFLR`が`0x40010004`、CH32V205とCH32X315は`ECR`/`EXTICR`/`CR`が前にあるので
`0x40010020`から始まる。同じ番地が family によって別の register を指す
（CH32H417の`GPIOD_AFHR`とCH32V205の`GPIOA_AFLR`がどちらも`0x40010020`）。

bit定義はEVT headerに1つも無い（`AFIO_GPIOA_AFLR_*`のような定数は存在しない）ので、
列挙値はここではなく`pin_functions.csv`の`af-N`側にある。

実行:
    uv run tools/build_pin_alternate.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_addresses  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "pad", "port", "pin", "block", "register", "address",
           "bits", "width_bits", "#", "confidence", "basis"]
# EVT だけが言う。reference manual の GPIO 章が second reading になる。
CONFIDENCE = "reference"

# AFIO->GPIOA_AFLR / GPIOA_AFHR。LR が pin 0-7、HR が pin 8-15。
AF_REGISTER = re.compile(r"^GPIO(?P<port>[A-H])_AF(?P<half>[LH])R$")
# GPIO_PinAFConfig() が書いている規則。マスク・シフト・上下の境界を読む。
#     AFIO->GPIOA_AFHR &= ~(0xF << (tmp << 2));
RULE = re.compile(r"GPIO[A-H]_AF[LH]R\s*&=\s*~\(\s*(?P<mask>0x[0-9A-Fa-f]+)\s*<<\s*"
                  r"\(\s*\w+\s*<<\s*(?P<shift>\d+)\s*\)")
#     if(GPIO_PinSource >= 0x08)
SPLIT = re.compile(r"GPIO_PinSource\s*>=\s*(?P<at>0x[0-9A-Fa-f]+|\d+)")


def read_rule(source: Path) -> tuple[int, int, int] | None:
    """(フィールドの幅bit, ピンあたりの刻みbit, 上下の境界) を driver から読む。

    ポート分だけ同じ形が並ぶので、**全部が同じことを言っている**ことを確かめて
    から採る。1つでも違えばポートによって幅が違うという意味になり、そのときは
    決め打ちで書けないので何も出さない。
    """
    text = source.read_text(errors="ignore")
    rules = {(m.group("mask"), m.group("shift")) for m in RULE.finditer(text)}
    splits = {int(m.group("at"), 0) for m in SPLIT.finditer(text)}
    if len(rules) != 1 or len(splits) != 1:
        return None
    mask, shift = rules.pop()
    return bin(int(mask, 16)).count("1"), 1 << int(shift), splits.pop()


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
        headers = [p for p in sorted((args.mirrors / family).glob("EVT/**/inc/ch32*.h"))
                   if re.fullmatch(r"ch32[a-zA-Z0-9]+\.h", p.name)]
        if not headers:
            notes.append(f"{family}: device header が無い")
            continue
        resolved = extract_addresses.addresses(headers[0])
        found = {register: at for (block, register), at in resolved.items()
                 if block == "AFIO" and AF_REGISTER.match(register)}
        if not found:
            continue
        drivers = sorted((args.mirrors / family).glob("EVT/**/src/*_gpio.c"))
        rule = next((r for r in (read_rule(p) for p in drivers) if r), None)
        if rule is None:
            notes.append(f"{family}: GPIO_PinAFConfig から幅と刻みが読めない")
            continue
        width, stride, boundary = rule
        if stride != width:
            notes.append(f"{family}: フィールド幅 {width}bit と刻み {stride}bit が違う")
        basis = f"evt({headers[0].name}+{drivers[0].name})"
        for register, at in sorted(found.items(), key=lambda kv: kv[1]):
            match = AF_REGISTER.match(register)
            port, half = match.group("port"), match.group("half")
            first = 0 if half == "L" else boundary
            count = boundary if half == "L" else (32 // stride)
            for index in range(count):
                pin = first + index
                lo = index * stride
                rows.append({
                    "family": family,
                    "pad": f"P{port}{pin}",
                    "port": port,
                    "pin": pin,
                    "block": "AFIO",
                    "register": register,
                    "address": f"{at:#010x}",
                    "bits": ";".join(f"{register}:{lo + b}" for b in range(width)),
                    "width_bits": width,
                    "confidence": CONFIDENCE,
                    "basis": basis,
                })

    dest = args.out / "pin_alternate.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    seen = sorted({r["family"] for r in rows})
    print(f"{dest}: {len(rows)} 行  family {len(seen)} ({', '.join(seen)})",
          file=sys.stderr)
    for note in notes:
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
