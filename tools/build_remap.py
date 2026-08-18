#!/usr/bin/env python3
"""Normalise the AFIO route selectors into remap_fields.csv / remap_routes.csv.

pin_functions.csv says a signal reaches a pad on route "remap-2"; these two
tables say what that means in hardware:

    remap_fields.csv  one row per (series, selector): the register field that
                      chooses the route -- bits, valid values, reset value
    remap_routes.csv  one row per (series, selector, value, signal, pad):
                      which value routes which signal to which pad

Derived from candidates/, where tools/build_candidate.py joined the EVT header
bit definitions, the reference manual's register tables and remap grid, and the
datasheet pin table. The join checked itself while building, but the per-fact
agreements are not recorded in the files, so every row here is confidence
"reference" with the source chain named; promoting them to confirmed by
re-verifying EVT against RM per selector is the known next step.

Usage:
    uv run tools/build_remap.py [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANDIDATES = REPO / "candidates"

SERIES = re.compile(r"^(CH32[A-Z]\d{3})")

FIELD_COLUMNS = ["series", "selector", "controller", "register", "field",
                 "bits", "valid_values", "reset_value",
                 "#", "confidence", "basis"]
ROUTE_COLUMNS = ["series", "selector", "value", "signal", "pad",
                 "#", "confidence", "basis"]

FIELD_BASIS = "candidates(evt-header+rm-register-table+rm-remap-grid:en)"
ROUTE_BASIS = "candidates(datasheet-pin-table+rm-remap-grid:en)"


def bits_of(selector: dict) -> str:
    """The field's bit positions, LSB first: '17', '4;5', or '1;22'."""
    positions = selector.get("bit_positions")
    if positions:
        return ";".join(str(b) for b in positions)
    offset = selector.get("bit_offset")
    width = selector.get("bit_width", 1)
    if offset is None:
        return ""
    return ";".join(str(offset + i) for i in range(width))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    fields: dict = {}
    disagreements: list[str] = []
    routes: set = set()
    for path in sorted(CANDIDATES.glob("ch32*.json")):
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
            }
            known = fields.get(key)
            if known is None:
                fields[key] = entry
            elif known != entry:
                # The same silicon described twice must not differ; surface it.
                disagreements.append(f"{series} {key[1]}: {part} の記述が他SKUと異なる")
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
    for row in field_rows:
        row["confidence"] = "reference"
        row["basis"] = FIELD_BASIS
    route_rows = [
        {"series": s, "selector": sel, "value": value, "signal": signal,
         "pad": pad, "confidence": "reference", "basis": ROUTE_BASIS}
        for (s, sel, value, signal, pad) in sorted(routes)
    ]

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows, columns in (("remap_fields.csv", field_rows, FIELD_COLUMNS),
                                ("remap_routes.csv", route_rows, ROUTE_COLUMNS)):
        with (args.out / name).open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            writer.writerows({**row, "#": "#"} for row in rows)
        print(f"{args.out}/{name}: {len(rows)} 行", file=sys.stderr)
    orphans = {(r["series"], r["selector"]) for r in route_rows} \
        - {(r["series"], r["selector"]) for r in field_rows}
    for series, sel in sorted(orphans):
        print(f"  - routeのみでfield定義がない: {series} {sel}", file=sys.stderr)
    for d in dict.fromkeys(disagreements):
        print(f"  - {d}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
