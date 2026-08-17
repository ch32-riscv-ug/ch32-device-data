#!/usr/bin/env python3
"""Extract register field definitions from a reference manual.

The EVT header gives a selector's bit positions but never its reset value, and it
cannot say which encodings are legal. The manual states both in the per-register
field table that follows each register heading:

    6.3.2.1 Remap Register 1 (AFIO_PCFR1)
    Bit      | Name          | Access | Description | Reset value
    [26:24]  | SWCFG[2:0]    | RW     | ...         | 0
    15       | ADC_ETRGIN_RM | RW     | ...         | 0

This reads those tables into field definitions for review. It emits candidates only
and never writes device records.

Usage:
    uv run tools/extract_registers.py <manual.pdf> [--register AFIO_PCFR1]
        [--compare devices/<id>.json] [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

# "6.3.2.1 Remap Register 1 (AFIO_PCFR1)" -- the register name is parenthesised.
HEADING = re.compile(r"^\d+(?:\.\d+)+\s+.*\(([A-Z][A-Z0-9_]*)\)\s*$")
BIT_RANGE = re.compile(r"^\[(\d+):(\d+)\]$")
BIT_SINGLE = re.compile(r"^(\d+)$")
FIELD_NAME = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)(?:\[\d+:\d+\])?$")
RESET = re.compile(r"^(0x[0-9A-Fa-f]+|\d+)$")

# Routing written into the description instead of a grid: CH32X035 states
# "001: Mapping (SCL/PA13, SDA/PA14)" and CH32M030 "000: Default mapping
# (CH1/PC0, CH2/PC1)". A group may list several signals on one pad, as in
# "CH1/ETR/PA5", where the last token is the pad.
DESCRIBED_ROUTE = re.compile(r"(?P<value>[01xX]{1,4})\s*:\s*[^()]{0,40}?\(([^()]*)\)")
PAD_TOKEN = re.compile(r"^P[A-H]\d{1,2}$")

HEADER_CELLS = ("bit", "name", "access")
RESET_CELL = "resetvalue"


def flatten(cell: str | None) -> str:
    return (cell or "").replace("\n", " ").strip()


def squash(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def field_header(row: list[str]) -> dict[str, int] | None:
    """Column indexes of a "Bit / Name / Access / ... / Reset value" header row."""
    squashed = [squash(c) for c in row]
    layout = {}
    for key in HEADER_CELLS:
        if key not in squashed:
            return None
        layout[key] = squashed.index(key)
    if RESET_CELL not in squashed:
        return None
    layout["reset"] = squashed.index(RESET_CELL)
    if "description" in squashed:
        layout["description"] = squashed.index("description")
    return layout


def parse_bits(cell: str) -> tuple[int, int] | None:
    m = BIT_RANGE.match(cell)
    if m:
        high, low = int(m.group(1)), int(m.group(2))
        return (low, high - low + 1) if high >= low else None
    m = BIT_SINGLE.match(cell)
    return (int(m.group(1)), 1) if m else None


def extract(pdf_path: Path, want: str | None) -> tuple[list[dict], list[str]]:
    fields: list[dict] = []
    notes: list[str] = []
    register: str | None = None
    layout: dict[str, int] | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Headings and tables are interleaved, so read them in vertical order.
            items = [("h", line["top"], line["text"].strip()) for line in page.extract_text_lines() or []]
            items += [("t", table.bbox[1], table) for table in page.find_tables()]
            for kind, _, payload in sorted(items, key=lambda x: x[1]):
                if kind == "h":
                    m = HEADING.match(payload)
                    if m:
                        register, layout = m.group(1), None
                    continue
                if register is None or (want and register != want):
                    continue
                rows = [[flatten(c) for c in row] for row in payload.extract()]
                if not rows:
                    continue
                found = field_header(rows[0])
                if found:
                    layout, rows = found, rows[1:]
                elif layout is None:
                    continue
                for row in rows:
                    if max(layout[k] for k in ("bit", "name", "access", "reset")) >= len(row):
                        continue
                    bits = parse_bits(row[layout["bit"]])
                    # A field name never contains a space; CH32V003 wraps
                    # ADC_ETRGREG_RM as "ADC_ETRGREG_R" + "M".
                    name = FIELD_NAME.match(row[layout["name"]].replace(" ", ""))
                    if not bits or not name or name.group(1).lower() == "reserved":
                        continue
                    reset = RESET.match(row[layout["reset"]])
                    if not reset:
                        notes.append(
                            f"{register}.{name.group(1)}: reset値を読めず ({row[layout['reset']]!r})"
                        )
                    fields.append(
                        {
                            "register": register,
                            "field": name.group(1),
                            "bit_offset": bits[0],
                            "bit_width": bits[1],
                            "reset_value": int(reset.group(1), 0) if reset else None,
                            "access": row[layout["access"]],
                            "description": (
                                row[layout["description"]]
                                if layout.get("description", len(row)) < len(row)
                                else ""
                            ),
                            "page": page.page_number,
                        }
                    )
    return fields, notes


def routes_in(field: dict) -> list[dict]:
    """Routes stated inside a field's description, as (value, signal, pad).

    Signal names there are written relative to the peripheral -- "CH1" under
    TIM3_RM, "SCL" under I2C1_RM -- so the field's own name supplies the prefix.
    """
    peripheral = re.sub(r"_(?:RM|REMAP)$", "", field["field"])
    out: list[dict] = []
    for m in DESCRIBED_ROUTE.finditer(field["description"]):
        pattern = m.group("value")
        values = [pattern] if "x" not in pattern.lower() else None
        bits = [
            int("".join(b), 2)
            for b in _expand_bits(pattern)
        ]
        for group in m.group(2).split(","):
            parts = [p.strip() for p in group.split("/") if p.strip()]
            if len(parts) < 2 or not PAD_TOKEN.match(parts[-1]):
                continue
            pad = parts[-1]
            for name in parts[:-1]:
                signal = name if name.startswith(peripheral) else f"{peripheral}_{name}"
                for value in bits:
                    out.append(
                        {
                            "field": field["field"],
                            "value": value,
                            "signal": signal,
                            "pad": pad,
                            "page": field["page"],
                            "_from_description": True,
                        }
                    )
    return out


def _expand_bits(pattern: str) -> list[list[str]]:
    rows = [[]]
    for bit in pattern:
        rows = (
            [r + [b] for r in rows for b in ("0", "1")]
            if bit in "xX"
            else [r + [bit] for r in rows]
        )
    return rows


def score(fields: list[dict], record: Path) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from extract_remap import canonical_field

    rec = json.loads(record.read_text(encoding="utf-8"))
    by_field = {}
    for f in fields:
        by_field.setdefault(canonical_field(f["field"]), f)

    selectors = rec.get("route_selectors", [])
    print(f"\n照合: {record.name}  record selector {len(selectors)}", file=sys.stderr)
    print("-" * 74, file=sys.stderr)
    hit = bits_ok = reset_ok = 0
    for sel in selectors:
        found = by_field.get(canonical_field(sel["field"]))
        if not found:
            print(f"  RMに無し    {sel['id']}", file=sys.stderr)
            continue
        hit += 1
        want_bits = (
            list(range(sel["bit_offset"], sel["bit_offset"] + sel["bit_width"]))
            if "bit_offset" in sel
            else sel.get("bit_positions", [])
        )
        got_bits = list(range(found["bit_offset"], found["bit_offset"] + found["bit_width"]))
        same_bits = want_bits == got_bits
        same_reset = found["reset_value"] == sel["reset_value"]
        bits_ok += same_bits
        reset_ok += same_reset
        marks = f"bit{'○' if same_bits else '×'} reset{'○' if same_reset else '×'}"
        detail = "" if same_bits else f"  RM={got_bits} record={want_bits}"
        print(f"  {marks}  {sel['id']:24} {found['register']}.{found['field']}{detail}", file=sys.stderr)
    print(
        f"\n  RMに存在 {hit}/{len(selectors)}   bit一致 {bits_ok}/{hit}   reset一致 {reset_ok}/{hit}",
        file=sys.stderr,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--register", help="この register のみ読む（例: AFIO_PCFR1）")
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--routes", action="store_true", help="説明文に書かれた経路を出す")
    args = ap.parse_args()

    fields, notes = extract(args.pdf, args.register)
    registers = sorted({f["register"] for f in fields})
    print(f"入力: {args.pdf}", file=sys.stderr)
    print(f"field定義: {len(fields)} 件 / register {len(registers)} 種", file=sys.stderr)
    if args.register or len(registers) <= 12:
        for reg in registers:
            count = sum(1 for f in fields if f["register"] == reg)
            print(f"    {reg:<22} {count} field", file=sys.stderr)
    if notes:
        print(f"\n要確認 {len(notes)} 件:", file=sys.stderr)
        for note in list(dict.fromkeys(notes))[:10]:
            print(f"  - {note}", file=sys.stderr)

    described = [r for f in fields for r in routes_in(f)]
    if described:
        print(f"説明文から読めた経路: {len(described)} 件", file=sys.stderr)
    if args.routes:
        json.dump(described, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    if args.compare:
        score(fields, args.compare)
    if args.emit:
        json.dump(fields, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
