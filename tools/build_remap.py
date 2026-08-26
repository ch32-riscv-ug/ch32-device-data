#!/usr/bin/env python3
"""Normalise the AFIO route selectors into remap_fields.csv / remap_routes.csv.

pin_functions.csv says a signal reaches a pad on route "remap-2"; these two
tables say what that means in hardware:

    remap_fields.csv  one row per (series, selector): the register field that
                      chooses the route -- bits, valid values, reset value
    remap_routes.csv  one row per (series, selector, value, signal, pad):
                      which value routes which signal to which pad

Two columns need reading carefully.

``bits`` names a register per bit, ``PCFR1:2;PCFR2:19;PCFR2:20``, least
significant first. Most selectors sit inside one register, but CH32L103,
CH32M103 and the CH32V20x/V30x families put the upper bits of several selectors
in PCFR2, and a consumer that writes only PCFR1 selects a different route
without any error. ``register`` summarises the same fact as ``PCFR1|PCFR2``.

``peripheral`` and ``role`` are the normalised reading of ``signal``, which is
kept exactly as its document spells it. The documents write the same role four
ways -- USART1_TX, UART_TX, TX1, UTX -- so tools/signal_vocabulary.py reads them
into one pair and leaves the pair empty where no rule applies, rather than
guessing.

Derived from candidates/, where tools/build_candidate.py joined the EVT header
bit definitions, the reference manual's register tables and remap grid, and the
datasheet pin table. The join checked itself while building, but the per-fact
agreements are not recorded in the files, so every row here is confidence
"reference" with the source chain named; promoting them to confirmed by
re-verifying EVT against RM per selector is the known next step.

Usage:
    uv run tools/build_remap.py [--out tables] [--candidates candidates]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import signal_vocabulary  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
CANDIDATES = paths.CANDIDATES

SERIES = re.compile(r"^(CH32[A-Z]\d{3})")

FIELD_COLUMNS = ["series", "selector", "controller", "register", "field",
                 "bits", "valid_values", "reset_value",
                 "#", "confidence", "basis"]
# `peripheral`/`role`（語彙で揃えた読み）は索引 `index/routes.csv` が付ける
# （tools/build_index.py）。ここは資料の綴り（signal・pad）だけ。
ROUTE_COLUMNS = ["series", "selector", "value", "signal", "pad",
                 "#", "confidence", "basis"]

FIELD_BASIS = "candidates(evt-header+rm-register-table+rm-remap-grid:en)"
# The EVT header does not define this field at all, so nothing cross-checks the
# manual's reading of it and the SDK offers no macro to write it. CH32V20x's
# USART4..USART8 are the only fields in any family that come this way.
MANUAL_BASIS = "candidates(rm-register-table+rm-remap-grid:en)"
ROUTE_BASIS = "candidates(datasheet-pin-table+rm-remap-grid:en)"
# The default route is read off the pin table's own default column, not the
# remap grid, which usually starts at value 1.
DEFAULT_BASIS = "candidates(datasheet-pin-table-default:en)"


def bits_of(selector: dict) -> str:
    """The field's bits as register:bit, least significant first."""
    return ";".join(f"{b['register']}:{b['bit']}" for b in selector.get("bits") or ())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    ap.add_argument("--candidates", type=Path, default=CANDIDATES)
    args = ap.parse_args()

    fields: dict = {}
    disagreements: list[str] = []
    routes: set = set()
    for path in sorted(args.candidates.glob("ch32*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        part = data.get("part_number", path.stem.upper())
        m = SERIES.match(part)
        if not m:
            continue
        series = m.group(1)
        for sel in data.get("route_selectors") or []:
            key = (series, sel.get("id", ""))
            entry = {
                "series": series,
                "selector": sel.get("id", ""),
                "controller": sel.get("controller", ""),
                "register": sel.get("register", ""),
                "field": sel.get("field", ""),
                "bits": bits_of(sel),
                "valid_values": ";".join(str(v) for v in sel.get("valid_values") or []),
                "reset_value": "" if sel.get("reset_value") is None
                               else str(sel["reset_value"]),
                "_from_manual": bool(sel.get("_from_manual")),
            }
            known = fields.get(key)
            if known is None:
                fields[key] = entry
            elif known != entry:
                # The same silicon described twice must not differ; surface it.
                # A package that bonds out fewer pads attests fewer values, so
                # the widest reading wins and only the rest is a disagreement.
                merged = dict(known)
                merged["valid_values"] = ";".join(
                    str(v) for v in sorted(
                        {int(v) for v in known["valid_values"].split(";") if v}
                        | {int(v) for v in entry["valid_values"].split(";") if v}
                    )
                )
                if {k: v for k, v in merged.items() if k != "valid_values"} == {
                    k: v for k, v in entry.items() if k != "valid_values"
                }:
                    fields[key] = merged
                else:
                    disagreements.append(
                        f"{series} {key[1]}: {part} の記述が他SKUと異なる"
                    )
        for pin in data.get("pins") or []:
            pad = pin.get("pad", "")
            for fn in pin.get("functions") or []:
                selection = fn.get("selection")
                if not selection:
                    continue
                for value in selection.get("values") or []:
                    routes.add((series, selection.get("selector", ""),
                                value, fn.get("signal", ""), pad))

    field_rows = sorted(fields.values(),
                        key=lambda r: (r["series"], r["selector"]))
    manual_only = [r for r in field_rows if r["_from_manual"]]
    for row in field_rows:
        row["confidence"] = "reference"
        row["basis"] = MANUAL_BASIS if row.pop("_from_manual") else FIELD_BASIS
    route_rows = []
    for (s, sel, value, signal, pad) in sorted(routes):
        route_rows.append(
            {"series": s, "selector": sel, "value": value, "signal": signal,
             "pad": pad,
             "confidence": "reference",
             "basis": DEFAULT_BASIS if value == 0 else ROUTE_BASIS}
        )

    if manual_only:
        print(f"  headerに定義が無くRMだけから作った selector: {len(manual_only)}",
              file=sys.stderr)
        for r in manual_only:
            print(f"    {r['series']} {r['selector']:24} {r['bits']}", file=sys.stderr)

    if args.out:

        args.out.mkdir(parents=True, exist_ok=True)
    for name, rows, columns in (("remap_fields.csv", field_rows, FIELD_COLUMNS),
                                ("remap_routes.csv", route_rows, ROUTE_COLUMNS)):
        dest = paths.table(name.removesuffix(".csv"), args.out)
        with dest.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            writer.writerows({**row, "#": "#"} for row in rows)
        print(f"{dest}: {len(rows)} 行", file=sys.stderr)
    defaults = sum(1 for r in route_rows if r["value"] == 0)
    print(f"  うち既定経路(value=0): {defaults} 行", file=sys.stderr)
    split = [r for r in field_rows if "|" in r["register"]]
    print(f"  registerをまたぐ分割field: {len(split)} selector", file=sys.stderr)
    for r in split:
        print(f"    - {r['series']} {r['selector']} {r['bits']}", file=sys.stderr)
    orphans = {(r["series"], r["selector"]) for r in route_rows} \
        - {(r["series"], r["selector"]) for r in field_rows}
    for series, sel in sorted(orphans):
        print(f"  - routeのみでfield定義がない: {series} {sel}", file=sys.stderr)
    for d in dict.fromkeys(disagreements):
        print(f"  - {d}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
