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
import re
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
                      "cores", "documents", "pins", "pin_functions",
                      "product_attributes", "remap_fields", "remap_routes",
                      "errata", "operating_conditions", "evt_examples")}

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
    for r in t["errata"]:
        check("errata", r["id"], r["series"], series, "series", ";")
    for r in t["evt_examples"]:
        check("evt_examples", r["example"], r["family"], families, "families")
    for r in t["operating_conditions"]:
        check("operating_conditions", r["symbol"], r["series"], series,
              "series", ";")
        check("operating_conditions", r["symbol"], r["datasheet"], documents,
              "documents")
    for name in ("pins", "pin_functions"):
        for r in t[name]:
            check(name, r["part_number"], r["part_number"], products, "products")
            check(name, r["part_number"], r["datasheet"], documents, "documents")
    for r in t["pin_functions"]:
        if (r["part_number"], r["pad"]) not in pin_pads:
            bad.append(f"pin_functions: {r['part_number']} の pad {r['pad']!r} が pins にない")
    for r in t["product_attributes"]:
        check("product_attributes", r["attribute"], r["part_number"], products, "products")
    # The two remap tables have to agree with each other as well as join, because
    # the ways they can disagree are the ways a consumer writes the wrong register
    # and gets a different route with no error at all.
    remap_fields = {(r["series"], r["selector"]) for r in t["remap_fields"]}
    field_by_key: dict[tuple[str, str], dict] = {}
    for r in t["remap_fields"]:
        check("remap_fields", r["selector"], r["series"], series, "series")
        where = f"{r['series']} {r['selector']}"
        field_by_key[(r["series"], r["selector"])] = r

        bits = [b for b in r["bits"].split(";") if b]
        if not bits:
            bad.append(f"remap_fields: {where} に bits がない")
            continue
        if any(not re.fullmatch(r"[A-Z][A-Z0-9]*:(?:[0-9]|[12][0-9]|3[01])", b) for b in bits):
            bad.append(f"remap_fields: {where} の bits が register:bit 形式でない: {r['bits']}")
            continue
        if len(set(bits)) != len(bits):
            bad.append(f"remap_fields: {where} の bits に重複がある: {r['bits']}")
        named = list(dict.fromkeys(b.split(":")[0] for b in bits))
        if r["register"] != "|".join(named):
            bad.append(
                f"remap_fields: {where} の register {r['register']!r} が bits の register と一致しない"
            )

        values = [int(v) for v in r["valid_values"].split(";") if v != ""]
        if not values:
            bad.append(f"remap_fields: {where} に valid_values がない")
            continue
        # A value wider than the field cannot be written. Where this fired it was
        # never a bad value: it was a field whose upper bits live in a second
        # register that the row failed to name.
        limit = 1 << len(bits)
        outside = [v for v in values if v >= limit]
        if outside:
            bad.append(
                f"remap_fields: {where} の valid_values {outside} が bits {len(bits)}bit に収まらない"
            )
        if r["reset_value"] and int(r["reset_value"]) not in values:
            bad.append(f"remap_fields: {where} の reset_value が valid_values にない")

    for r in t["remap_routes"]:
        where = f"{r['series']} {r['selector']} 値{r['value']}"
        field = field_by_key.get((r["series"], r["selector"]))
        if field is None:
            bad.append(f"remap_routes: ({r['series']}, {r['selector']}) が remap_fields にない")
            continue
        values = {int(v) for v in field["valid_values"].split(";") if v != ""}
        if int(r["value"]) not in values:
            bad.append(f"remap_routes: {where} が remap_fields の valid_values にない")
        # An empty pair means the vocabulary has no rule for that spelling, which
        # is a recorded gap. One half filled is a bug in the rule.
        if bool(r.get("peripheral")) != bool(r.get("role")):
            bad.append(f"remap_routes: {where} の peripheral と role が片方だけ埋まっている")

    # Data columns carry no CJK: Chinese readings are evidence (kept in the
    # *_basis and label_zh columns), never the displayed value. A leak here
    # means the translation dictionary in curated/translations.json is missing
    # an entry, or an extractor let prose fragments through.
    cjk = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
    for name, rows in t.items():
        if not rows:
            continue
        columns = []
        for column in rows[0]:
            if column == "#":
                break
            if column != "label_zh":
                columns.append(column)
        for r in rows:
            for column in columns:
                value = r.get(column, "")
                if value and cjk.search(value):
                    bad.append(f"{name}: {column} にCJKが残っている: {value[:40]!r}")

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
