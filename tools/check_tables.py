#!/usr/bin/env python3
"""Check that every reference between the normalised tables actually joins.

The tables are meant to be used relationally -- products join series, pins join
products, everything that names a document joins documents.csv -- so a value
that fails to join is a defect, whether a typo, a normalisation gap, or a row
that never got generated. Prints each violation and exits non-zero on any.

Usage:
    uv run tools/check_tables.py [--tables tables]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def load(tables: Path, name: str) -> list[dict]:
    with (tables / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", type=Path, default=Path("tables"))
    args = ap.parse_args()
    t = {name: load(args.tables, name)
         for name in ("families", "series", "products", "packages",
                      "cores", "documents", "pins", "pin_functions")}

    families = {r["family"] for r in t["families"]}
    series = {r["series"] for r in t["series"]}
    products = {r["part_number"] for r in t["products"]}
    packages = {r["package"] for r in t["packages"]}
    cores = {r["core"] for r in t["cores"]}
    documents = {r["document"] for r in t["documents"]}
    pin_pads = {(r["part_number"], r["pad"]) for r in t["pins"]}

    bad: list[str] = []

    def check(table: str, row_key: str, value: str, target: set, target_name: str,
              split: str | None = None) -> None:
        values = [v.strip() for v in value.split(split)] if split else [value]
        for v in values:
            if v and v not in target:
                bad.append(f"{table}: {row_key} の {v!r} が {target_name} にない")

    for r in t["series"]:
        check("series", r["series"], r["family"], families, "families")
        check("series", r["series"], r["datasheets"], documents, "documents", ";")
        check("series", r["series"], r["core"], cores, "cores", " + ")
    for r in t["products"]:
        check("products", r["part_number"], r["family"], families, "families")
        check("products", r["part_number"], r["series"], series, "series")
        check("products", r["part_number"], r["package"], packages, "packages")
        check("products", r["part_number"], r["datasheet"], documents, "documents")
    for r in t["packages"]:
        check("packages", r["package"], r["families"], families, "families", ";")
    for r in t["families"]:
        for column in ("datasheets", "reference_manuals", "evt"):
            check("families", r["family"], r[column], documents, "documents", ";")
        for token in r["cores"].split(";"):
            check("families", r["family"], token, cores, "cores", " + ")
    for r in t["cores"]:
        check("cores", r["core"], r["manual"], documents, "documents")
    for name in ("pins", "pin_functions"):
        for r in t[name]:
            check(name, r["part_number"], r["part_number"], products, "products")
            check(name, r["part_number"], r["datasheet"], documents, "documents")
    for r in t["pin_functions"]:
        if (r["part_number"], r["pad"]) not in pin_pads:
            bad.append(f"pin_functions: {r['part_number']} の pad {r['pad']!r} が pins にない")

    counts = {name: len(rows) for name, rows in t.items()}
    print("行数:", counts, file=sys.stderr)
    if bad:
        seen: list[str] = []
        for b in bad:
            if b not in seen:
                seen.append(b)
        print(f"結合できない参照 {len(seen)} 種:", file=sys.stderr)
        for b in seen[:40]:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print("全テーブルの参照が結合可能です", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
