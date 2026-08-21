#!/usr/bin/env python3
"""Normalise the EVT clock configurations into clock_configs.csv / clock_prescalers.csv.

    clock_configs.csv     one row per (series, configuration, #if branch): which
                          oscillator, what each clock domain runs at, the bus
                          prescalers, the PLL settings, the flash latency, and
                          anything written outside RCC
    clock_prescalers.csv  one row per (series, prescaler field, divider): the
                          value that selects that divider

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

CONFIG_COLUMNS = ["series", "config", "source", "condition", "domains",
                  "hpre", "ppre1", "ppre2", "pll", "flash_latency", "outside_rcc",
                  "#", "confidence", "basis", "evt_copies"]
PRESCALER_COLUMNS = ["series", "field", "divider", "value",
                     "#", "confidence", "basis"]

BASIS = "evt(system_ch32*.c)"
PRESCALER_BASIS = "evt(device-header)"
# One source only, so nothing here is confirmed by agreement between documents.
# The reference manual states the same fields and is the obvious second reading.
CONFIDENCE = "reference"

CONDITIONED = re.compile(r"^(?P<symbol>\S+) \[(?P<condition>.*)\]$")


def family_series(candidates: Path) -> dict[str, list[str]]:
    """Which series each EVT family's silicon covers, from candidates/ provenance."""
    out: dict[str, set[str]] = collections.defaultdict(set)
    for path in sorted(candidates.glob("ch32*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        header = (data.get("_provenance") or {}).get("header")
        m = re.match(r"^(CH32[A-Z]\d{2}[0-9A-Za-z])", data.get("part_number", ""))
        if header and m:
            out[header.split("/")[0]].add(m.group(1))
    return {family: sorted(series) for family, series in out.items()}


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
    ap.add_argument("--candidates", type=Path, default=REPO / "candidates")
    args = ap.parse_args()

    observed, notes = extract_clock_tree.extract_all(args.mirrors)
    covers = family_series(args.candidates)

    config_rows: list[dict] = []
    prescaler_rows: list[dict] = []
    unmapped: list[str] = []
    for family, data in sorted(observed.items()):
        series_list = covers.get(family)
        if not series_list:
            unmapped.append(family)
            continue
        for series in series_list:
            for field, table in sorted(data["prescaler_encodings"].items()):
                for divider, value in sorted(table.items(), key=lambda kv: kv[1]):
                    prescaler_rows.append({
                        "series": series, "field": field,
                        "divider": divider.replace("DIV", ""), "value": value,
                        "confidence": CONFIDENCE, "basis": PRESCALER_BASIS,
                    })
            for name, entry in sorted(data["configs"].items()):
                domains = ";".join(f"{k}={v}" for k, v in entry["domains"].items())
                for condition, symbols in sorted(split_by_condition(entry["pll"]).items()):
                    config_rows.append({
                        "series": series,
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
    no_latency = sorted({r["series"] for r in config_rows} -
                        {r["series"] for r in config_rows if r["flash_latency"]})
    print(f"  flash latencyを一度も書かない series: {' '.join(no_latency)}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    for family in unmapped:
        print(f"  - {family}: candidates/ に無いので series へ対応付けられない",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
