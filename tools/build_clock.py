#!/usr/bin/env python3
"""Normalise the EVT clock configurations into clock_configs.csv / clock_prescalers.csv.

    clock_configs.csv     one row per (series, configuration, #if branch): which
                          oscillator, what each clock domain runs at, the bus
                          prescalers, the PLL settings, the flash latency, and
                          anything written outside RCC
    clock_prescalers.csv  one row per (series, prescaler field, divider): the
                          value that selects that divider
    clock_sources.csv     one row per (series, consumer, option): what USB, the
                          RTC, the ADC, I2S and the rest can be clocked from,
                          and the register field that selects it
    clock_symbols.csv     one row per (family, symbol) named in clock_configs'
                          `pll` or `outside_rcc`: the number it stands for, the
                          register it is written to, and that register's address

Read from EVT's system_ch32*.c, which ships one function per configuration the
vendor supports. Three things about that source shape are load-bearing.

**The copies are not identical.** EVT ships this file once per example -- 390
times for CH32H417 -- in several distinct versions. `evt_copies` says how many
copies state a configuration: 162/168 is the mainstream one, 4/168 is
example-specific. Nothing is dropped, so a consumer can decide.

**A configuration can depend on a compile-time switch.** CH32V307's 144 MHz
setting writes RCC_PLLMULL18 under `#ifdef CH32V30x_D8` and RCC_PLLMULL18_EXTEN
otherwise, so one function is two facts. Each branch is its own row and the
`condition` column says which.

**Not every name states a frequency.** "SetSysClockToHSE" runs the system
straight off the crystal, whose frequency is a board property, not the chip's.
Those rows have an empty `domains` rather than a guess.

**A symbol name does not give away its value.** CH32V307 defines
RCC_PLLMULL18 as 0x003C0000 and RCC_PLLMULL18_EXTEN as 0, so the same "x18"
encodes two ways, and EXTEN_PLL_HSI_PRE says nothing about being bit 4 of a
register at 0x40023800. clock_symbols.csv carries the number and the address so
the `pll` and `outside_rcc` cells can be turned into register writes.

Usage:
    uv run tools/build_clock.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import extract_clock_tree  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

# Keyed by family, not series. A clock tree is a property of the silicon, and
# one EVT clone describes one silicon; families.csv already carries which series
# each covers. Keying by series would copy CH32V20x's 19 configurations onto both
# CH32V203 and CH32V208 and, worse, let a series that two family directories both
# mention pick up the wrong tree.
CONFIG_COLUMNS = ["family", "config", "source", "condition", "domains",
                  "hpre", "ppre1", "ppre2", "pll", "flash_latency", "outside_rcc",
                  "#", "confidence", "basis", "evt_copies"]
PRESCALER_COLUMNS = ["family", "field", "divider", "value",
                     "#", "confidence", "basis"]
SOURCE_COLUMNS = ["family", "consumer", "option", "value", "register", "shift",
                  "condition", "#", "confidence", "basis"]
SYMBOL_COLUMNS = ["family", "symbol", "register", "address", "value",
                  "#", "confidence", "basis"]

BASIS = "evt(system_ch32*.c)"
PRESCALER_BASIS = "evt(device-header)"
SOURCE_BASIS = "evt(rcc-header+rcc-driver)"
SYMBOL_BASIS = "evt(device-header+system_ch32*.c)"
# One source only, so nothing here is confirmed by agreement between documents.
# The reference manual states the same fields and is the obvious second reading.
CONFIDENCE = "reference"

CONDITIONED = re.compile(r"^(?P<symbol>\S+) \[(?P<condition>.*)\]$")


def known_families(tables: Path) -> set[str]:
    """The family names families.csv carries, which are the EVT clone names."""
    path = tables / "families.csv"
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {r["family"] for r in csv.DictReader(f)}


def split_by_condition(pll: list[str]) -> dict[str, list[str]]:
    """PLL symbols grouped by the #if branch they sit in, "" for unconditional."""
    grouped: dict[str, list[str]] = collections.defaultdict(list)
    for entry in pll:
        m = CONDITIONED.match(entry)
        if m:
            grouped[m.group("condition")].append(m.group("symbol"))
        else:
            grouped[""].append(entry)
    return grouped or {"": []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    observed, notes = extract_clock_tree.extract_all(args.mirrors)
    families = known_families(args.out)

    config_rows: list[dict] = []
    prescaler_rows: list[dict] = []
    source_rows: list[dict] = []
    symbol_rows: list[dict] = []
    unmapped: list[str] = []
    for family, data in sorted(observed.items()):
        if families and family not in families:
            unmapped.append(family)
            continue
        for field, table in sorted(data["prescaler_encodings"].items()):
            for divider, value in sorted(table.items(), key=lambda kv: kv[1]):
                prescaler_rows.append({
                    "family": family, "field": field,
                    "divider": divider.replace("DIV", ""), "value": value,
                    "confidence": CONFIDENCE, "basis": PRESCALER_BASIS,
                })
        for entry in data.get("symbols", []):
            symbol_rows.append({
                "family": family, "symbol": entry["symbol"],
                "register": entry["register"], "address": entry["address"],
                "value": entry["value"],
                "confidence": CONFIDENCE, "basis": SYMBOL_BASIS,
            })
        for consumer, options in sorted(data.get("peripheral_sources", {}).items()):
            for option in options:
                source_rows.append({
                    "family": family, "consumer": consumer,
                    "option": option["option"], "value": option["value"],
                    "register": option["register"], "shift": option["shift"],
                    "condition": option["condition"],
                    "confidence": CONFIDENCE, "basis": SOURCE_BASIS,
                })
        for name, entry in sorted(data["configs"].items()):
            domains = ";".join(f"{k}={v}" for k, v in entry["domains"].items())
            for condition, symbols in sorted(split_by_condition(entry["pll"]).items()):
                config_rows.append({
                    "family": family,
                    "config": name,
                    "source": entry["source"] or "",
                    "condition": condition,
                    "domains": domains,
                    "hpre": entry["prescalers"].get("HPRE", "").replace("DIV", ""),
                    "ppre1": entry["prescalers"].get("PPRE1", "").replace("DIV", ""),
                    "ppre2": entry["prescalers"].get("PPRE2", "").replace("DIV", ""),
                    "pll": ";".join(symbols),
                    "flash_latency": ("" if entry["flash_latency"] is None
                                      else str(entry["flash_latency"])),
                    "outside_rcc": ";".join(entry["outside_rcc"]),
                    "confidence": CONFIDENCE, "basis": BASIS,
                    "evt_copies": entry["copies"],
                })
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows, columns in (
        ("clock_configs.csv", config_rows, CONFIG_COLUMNS),
        ("clock_prescalers.csv", prescaler_rows, PRESCALER_COLUMNS),
        ("clock_sources.csv", source_rows, SOURCE_COLUMNS),
        ("clock_symbols.csv", symbol_rows, SYMBOL_COLUMNS),
    ):
        rows.sort(key=lambda r: tuple(str(r.get(c, "")) for c in columns[:4]))
        with (args.out / name).open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            writer.writerows({**row, "#": "#"} for row in rows)
        print(f"{args.out}/{name}: {len(rows)} 行", file=sys.stderr)

    staged = [r for r in config_rows if r["domains"].count("=") > 1]
    print(f"  クロックドメインが2段以上: {len(staged)} 行", file=sys.stderr)
    outside = collections.Counter(r["outside_rcc"] for r in config_rows if r["outside_rcc"])
    for what, n in outside.most_common():
        print(f"  RCC外のレジスタ: {what} ({n} 行)", file=sys.stderr)
    same_value = collections.Counter(
        (r["family"], r["consumer"], r["value"]) for r in source_rows)
    aliased = [k for k, n in same_value.items() if n > 1]
    if aliased:
        print(f"  同じ値が別のsourceを指す（分岐で意味が変わる）: {len(aliased)} 件",
              file=sys.stderr)
        for family, consumer, value in aliased:
            options = [f"{r['option']}[{r['condition'] or '既定'}]" for r in source_rows
                       if (r["family"], r["consumer"], r["value"]) == (family, consumer, value)]
            print(f"    {family} {consumer} {value:#x} = {' / '.join(options)}",
                  file=sys.stderr)
    named = {(r["family"], s)
             for r in config_rows
             for cell in (r["pll"], r["outside_rcc"])
             for entry in cell.split(";") if entry
             for s in [entry.split(" ")[-1]]}
    have = {(r["family"], r["symbol"]) for r in symbol_rows}
    missing = sorted(named - have)
    print(f"  clock_configs が名前で呼ぶ記号 {len(named)} / 値の解けたもの {len(have & named)}",
          file=sys.stderr)
    for family, symbol in missing:
        print(f"    - {family} {symbol}: device header に #define が無い", file=sys.stderr)
    no_address = [r for r in symbol_rows if not r["address"]]
    if no_address:
        print(f"  レジスタのアドレスが解けない記号: {len(no_address)}", file=sys.stderr)
        for r in no_address:
            print(f"    - {r['family']} {r['symbol']} ({r['register']})", file=sys.stderr)
    no_latency = sorted({r["family"] for r in config_rows} -
                        {r["family"] for r in config_rows if r["flash_latency"]})
    print(f"  flash latencyを一度も書かない family: {' '.join(no_latency)}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    for family in unmapped:
        print(f"  - {family}: families.csv に無いので載せない", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
