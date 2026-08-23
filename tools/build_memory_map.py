#!/usr/bin/env python3
"""アドレス空間の地図 → tables/memory_map.csv

**出所は datasheet の 1.2 章ではなく EVT の device header。** ヘッダーは
`*_BASE` 定数として同じ地図を持っていて、しかもコンパイルされる側の定義そのもの
なので図を読むより確かで安い。相対の連鎖（`EXTEN_BASE = HBPERIPH_BASE + 0x3800`）
の解決は `extract_addresses.bases()` が既に持っている。

3 種類が同じ名前空間に混ざっているので `kind` で分ける:

    memory      FLASH・SRAM・OB（用户选择字）
    bus         PERIPH_BASE / APB1PERIPH_BASE / AHBPERIPH_BASE — 束ねる側
    peripheral  TIM2_BASE・GPIOA_BASE … 個々の周辺

**FLASH の番地は2つある。** ヘッダーの `FLASH_BASE` は CH32V307 で 0x08000000、
EVT の linker script は `ORIGIN = 0x00000000` を使う。どちらも実在の窓口で、
linker script を書く側が要るのは後者なので、両方を別の行として持つ
（`kind = link-origin`）。どちらか一方だけを載せると片方の用途が壊れる。

**variant で消える番地がある。** CH32V20x の `OSC_BASE` は `_D8`/`_D8W` だけ
（`_D6` には無い）。`#if` の条件を `condition` 列に持ち、どの型番がその macro を
立てるかは `evt_variants.csv` が持つ——`clock_configs.condition` と同じ辿り方。

実行:
    uv run tools/build_memory_map.py [--mirrors <dir>] [--out tables]
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

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "region", "base_address", "kind", "condition",
           "#", "confidence", "basis"]
# EVT だけが言う。reference manual のメモリマップ図が second reading になる。
CONFIDENCE = "reference"

BASE_DEFINE = re.compile(r"^#\s*define\s+(?P<name>\w+_BASE)\b")
IF = re.compile(r"^#\s*(?P<opener>ifdef|ifndef|if|elif|else|endif)\b(?P<rest>.*)$")
# include guard（`__CH32V30x_H`）と variant macro（`CH32V20x_D8`）を取り違えない。
# 後者は必ず `_` の後ろに版を表す語が来て、guard は先頭が `__`。
VARIANT = re.compile(r"(?<!_)\bCH32[A-Za-z0-9]*_(?:D\d[A-Za-z0-9]*|[A-Z]{2,}[A-Za-z0-9]*)\b")
# 束ねる側の名前。個々の周辺と区別する。
BUS = re.compile(r"^(?:A?HB|APB\d|)PERIPH$|^PERIPH$")
# `FLASH_R` は FLASH の**制御レジスタ**（0x40022000）で、記憶域ではない。
MEMORY = {"FLASH", "SRAM", "OB"}

LD_ORIGIN = re.compile(
    r"^\s*(?P<what>FLASH|RAM)\s*\([rwx]+\)\s*:\s*ORIGIN\s*=\s*(?P<origin>0x[0-9A-Fa-f]+)")
COMMENT = re.compile(r"/\*.*?\*/", re.S)


def find_header(family_dir: Path) -> Path | None:
    found = sorted(family_dir.glob("EVT/**/Peripheral/inc/ch32*.h"))
    plain = [p for p in found
             if re.fullmatch(r"ch32[a-z0-9]+\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else (found[0] if found else None)


def conditions(header: Path) -> dict[str, str]:
    """{`*_BASE` の名前: それを囲む variant 条件}。無条件のものは入れない。"""
    stack: list[list[str]] = []
    out: dict[str, str] = {}
    for line in header.read_text(errors="ignore").splitlines():
        text = line.strip()
        directive = IF.match(text)
        if directive:
            opener, rest = directive.group("opener"), directive.group("rest")
            if opener in ("ifdef", "ifndef", "if"):
                stack.append(VARIANT.findall(rest))
            elif opener in ("elif", "else") and stack:
                stack[-1] = VARIANT.findall(rest)
            elif opener == "endif" and stack:
                stack.pop()
            continue
        define = BASE_DEFINE.match(text)
        if define:
            open_now = [m for level in stack for m in level]
            if open_now:
                out[define.group("name")] = "|".join(dict.fromkeys(open_now))
    return out


def kind_of(region: str) -> str:
    if region in MEMORY:
        return "memory"
    if BUS.match(region):
        return "bus"
    return "peripheral"


def read_link_origins(family_dir: Path) -> dict[str, int]:
    """{FLASH|RAM: 領域の先頭番地}。

    IAP の例題は bootloader のぶんだけ後ろにずらした ORIGIN を書くので、
    **一番多い値**を領域の先頭と読む（ずらした側は少数派）。
    """
    counted: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for path in sorted(family_dir.glob("EVT/**/*.ld")):
        for line in COMMENT.sub("", path.read_text(errors="ignore")).splitlines():
            found = LD_ORIGIN.match(line)
            if found:
                counted[found.group("what")][int(found.group("origin"), 16)] += 1
    return {what: tally.most_common(1)[0][0] for what, tally in counted.items()}


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
        lines = header.read_text(errors="ignore").splitlines()
        resolved = extract_addresses.bases(lines)
        guarded = conditions(header)
        found = {name: value for name, value in resolved.items()
                 if name.endswith("_BASE")}
        if not found:
            notes.append(f"{family}: {header.name} に *_BASE が無い")
            continue
        for name, value in sorted(found.items(), key=lambda kv: (kv[1], kv[0])):
            region = name[: -len("_BASE")]
            rows.append({
                "family": family,
                "region": region,
                "base_address": f"{value:#010x}",
                "kind": kind_of(region),
                "condition": guarded.get(name, ""),
                "confidence": CONFIDENCE,
                "basis": f"evt({header.name})",
            })
        origins = read_link_origins(args.mirrors / family)
        for what, origin in sorted(origins.items()):
            rows.append({
                "family": family,
                "region": what,
                "base_address": f"{origin:#010x}",
                # linker script が実際に使う先頭。ヘッダーの FLASH_BASE とは
                # 別の窓口を指すことがある（CH32V307 は 0x08000000 と 0x00000000）。
                "kind": "link-origin",
                "condition": "",
                "confidence": CONFIDENCE,
                "basis": "evt(Link.ld)",
            })
        if not origins:
            notes.append(f"{family}: linker script から ORIGIN が読めない")

    rows.sort(key=lambda r: (r["family"], r["kind"], r["base_address"], r["region"]))
    dest = args.out / "memory_map.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    seen = sorted({r["family"] for r in rows})
    tally = collections.Counter(r["kind"] for r in rows)
    print(f"{dest}: {len(rows)} 行  family {len(seen)}  {dict(tally)}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
