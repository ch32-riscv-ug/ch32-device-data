#!/usr/bin/env python3
"""Extract the per-SKU product comparison table from a datasheet.

This is the table that enumerates every orderable model with its memory, pin count
and peripheral counts. It is the source for the SKU universe itself, and for the
identity, memory, package and peripheral parts of a record.

Two layouts occur. CH32V003 and CH32V006 give one row per model:

    Model         | Flash memory | SRAM | Pin No. | ... | Package Form
    CH32V003F4P6  | 16K          | 2K   | 20      | ... | TSSOP20

CH32M030 and CH32L103 transpose it, one column per model:

    Model/Resource |      | C8U3 | C8T7 | ...
    Pin Number     |      | 48   | 48   | ...

Values are kept under the document's own labels rather than mapped onto schema
fields, so nothing is lost before the shape of the record is settled.

Usage:
    uv run tools/extract_products.py <datasheet.pdf> [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

MODEL = re.compile(r"^CH32[A-Z0-9]{4,}$")
FAMILY = re.compile(r"^CH32[A-Z]\d{3}$")
# A model suffix as the transposed layout writes it. The shape varies widely --
# C8T6, K8U7 and F6P1 alternate letters and digits, VET6 and RDU6 do not, and
# CH32V303 is listed simply as CB, RB, RC. Anything short and uppercase qualifies,
# which is only safe because a family name must head the column group.
SUFFIX = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")
# The narrower shape, which is unambiguous enough to stand without a family row.
PLAIN_SUFFIX = re.compile(r"^[A-Z]{1,2}\d[A-Z]\d?[A-Z]?\d?$")
MAX_PAGES = 16


def flatten(cell: str | None) -> str:
    return (cell or "").replace("\n", "").strip()


def fill_across(row: list[str]) -> list[str]:
    """Carry a value rightwards over the blank cells it spans."""
    out, last = [], ""
    for cell in row:
        last = cell or last
        out.append(last)
    return out


def read_row_layout(rows: list[list[str]]) -> list[dict] | None:
    """One row per model, labels merged from the header rows above."""
    first = next((i for i, r in enumerate(rows) if r and MODEL.match(r[0])), None)
    if first is None or sum(1 for r in rows[first:] if r and MODEL.match(r[0])) < 2:
        return None
    width = max(len(r) for r in rows)
    labels = [
        " ".join(rows[j][c] for j in range(first) if c < len(rows[j]) and rows[j][c]).strip()
        or f"col{c}"
        for c in range(width)
    ]
    products: list[dict] = []
    carried: list[str] = [""] * width
    for row in rows[first:]:
        if not row or not MODEL.match(row[0]):
            continue
        padded = list(row) + [""] * (width - len(row))
        # A blank cell repeats the model above it, which is how merged cells read.
        values = [cell or carried[i] for i, cell in enumerate(padded)]
        carried = values
        products.append(
            {"part_number": values[0], "attributes": dict(zip(labels[1:], values[1:]))}
        )
    return products


def read_column_layout(rows: list[list[str]], default_family: str) -> list[dict] | None:
    """One column per model, attributes down the rows."""
    def sku_cells(row: list[str], pattern: re.Pattern) -> int:
        # A bare family name spans a group of columns; it names the group, not a model.
        return sum(
            1
            for n in (flatten(c) for c in row[1:])
            if pattern.match(n) or (MODEL.match(n) and not FAMILY.match(n))
        )

    def family_row(upto: int) -> list[str] | None:
        for row in rows[:upto]:
            if sum(1 for c in row if FAMILY.match(flatten(c))) >= 1:
                filled = fill_across([flatten(c) for c in row])
                return [f if FAMILY.match(f) else default_family for f in filled]
        return None

    header = None
    for i, row in enumerate(rows[:3]):
        # The loose shape is only trustworthy when a family name heads the group.
        loose_ok = family_row(i) is not None and sku_cells(row, SUFFIX) >= 2
        if loose_ok or sku_cells(row, PLAIN_SUFFIX) >= 2:
            header = i
            break
    if header is None:
        return None

    families = (family_row(header) or []) + [default_family] * len(rows[header])

    columns: dict[int, str] = {}
    for col, name in enumerate(rows[header]):
        name = flatten(name)
        if MODEL.match(name):
            columns[col] = name
        elif SUFFIX.match(name):
            columns[col] = families[col] + name if col < len(families) else name
    if len(columns) < 2:
        return None

    products = {col: {"part_number": pn, "attributes": {}} for col, pn in columns.items()}
    for row in rows[header + 1:]:
        label = flatten(row[0]) if row else ""
        if not label:
            continue
        for col, product in products.items():
            if col < len(row):
                value = flatten(row[col])
                if value:
                    product["attributes"][label] = value
    return list(products.values())


def extract(pdf_path: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    products: list[dict] = []
    seen: set[str] = set()
    with pdfplumber.open(pdf_path) as pdf:
        title = ""
        for line in pdf.pages[0].extract_text_lines() or []:
            m = re.match(r"^(CH32[A-Z0-9]+)\s", line["text"].strip())
            if m:
                title = m.group(1)
                break
        if not title:
            notes.append("先頭ページから family 名を読めず、転置表の型番を補完できません")
        for pno, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
            for table in page.find_tables():
                rows = [[flatten(c) for c in r] for r in table.extract()]
                if not rows or len(rows[0]) < 4:
                    continue
                found = read_row_layout(rows) or read_column_layout(rows, title)
                if not found:
                    continue
                layout = "row" if read_row_layout(rows) else "column"
                for product in found:
                    key = product["part_number"]
                    if key in seen:
                        # Continuation page: merge the further attributes in.
                        for existing in products:
                            if existing["part_number"] == key:
                                existing["attributes"].update(product["attributes"])
                        continue
                    seen.add(key)
                    product["_source"] = {"page": pno, "layout": layout}
                    products.append(product)
    return products, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    products, notes = extract(args.pdf)
    print(f"入力: {args.pdf}", file=sys.stderr)
    print(f"SKU: {len(products)} 件", file=sys.stderr)
    for p in products:
        attrs = p["attributes"]
        head = list(attrs.items())[:4]
        summary = " ".join(f"{k}={v}" for k, v in head)
        print(f"    {p['part_number']:<16} {summary[:74]}", file=sys.stderr)
    if notes:
        for n in notes:
            print(f"  - {n}", file=sys.stderr)
    if args.emit:
        json.dump(products, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
