#!/usr/bin/env python3
"""Normalise the pin-definition tables into pins.csv and pin_functions.csv.

The bottom of the hierarchy families -> series -> products -> pins. Two tables,
because the fact split is physical vs logical:

    pins.csv           which pad sits on which lead, per package column
    pin_functions.csv  which signals a pad carries, per pin-definition table

A pad's functions are stated once per table row and shared by every package
column of that table, so they are not repeated per package.

Each language edition is read on its own and the readings compared. Matching is
not literal, because the editions drift in form while stating the same fact:
the table numbering differs (CH32X315's zh 表2-1-1 is en Table 2-1), so tables
pair by the series named in the caption; column headings differ in spelling
(QFN48×7 / QFN48X7, QFN28(6) / QFN28, LQFP64M / LQFP64), so columns pair by a
normalised name, and a last unpaired column on each side pairs by elimination.

A (pin, pad) both editions state is confirmed, one edition alone is reference,
and the same lead carrying different pads is a conflict for a person to settle.

Usage:
    uv run tools/build_pins.py --out tables [--family CH32V003]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pdfplumber  # noqa: E402

import build_all  # noqa: E402
import extract_pins  # noqa: E402

MIRRORS = Path("/home/mt/dev_wch")

# The empty "#" column separates data from metadata; see tables/README.ja.md.
PIN_COLUMNS = ["family", "datasheet", "table", "package", "pin", "pad", "kind",
               "#", "confidence", "basis"]
FUNCTION_COLUMNS = ["family", "datasheet", "table", "pad", "signal", "route",
                    "#", "confidence", "basis"]

SERIES_TOKEN = re.compile(r"CH32[A-Z0-9]+")
FOOTNOTE = re.compile(r"[（(]\d+[)）]")


def pin_key(value) -> tuple:
    """Leads sort numerically; non-numeric pins (the exposed pad) sort after."""
    try:
        return (0, int(value), "")
    except (TypeError, ValueError):
        return (1, 0, str(value))


def table_number(label: str) -> str:
    return re.sub(r"[^0-9-]", "", label)


def canon_variant(name: str) -> str:
    """One spelling for one column: QFN48×7 and QFN48X7, QFN28(6) and QFN28."""
    return FOOTNOTE.sub("", name.replace("×", "X")).strip().upper()


def read_edition(path: Path) -> tuple[dict, dict, dict]:
    """One edition's pin tables.

    Returns (columns, functions, table_names):
        columns:     {(tkey, canon variant): {"table", "variant", "pins": {(pin, pad): kind}}}
        functions:   {(tkey, pad): {(signal, route)}}
        table_names: {tkey: printed table number}
    tkey names the table by the series in its caption (with an ordinal, one
    series can have several pin tables) so the editions pair despite numbering.
    """
    columns: dict = {}
    functions: dict = collections.defaultdict(set)
    table_names: dict = {}
    overrides = build_all.curated_columns().get(path.name, {})
    ordinal: collections.Counter = collections.Counter()
    with pdfplumber.open(path) as pdf:
        caps = extract_pins.captions(pdf)
        seen: set[str] = set()
        for i, (label, title, _) in enumerate(caps):
            if not any(t in title.lower() for t in extract_pins.PIN_TABLE_TITLE) \
                    or label in seen:
                continue
            seen.add(label)
            stop = extract_pins.next_caption(caps, i)
            rows, variants, layout = extract_pins.find_pin_tables(pdf, label, stop)
            fixed = overrides.get(label, {}).get("columns")
            if fixed:
                # The curated list is authoritative; the parser only found where
                # the columns are, not always what they are called.
                variants = fixed + variants[len(fixed):]
            m = SERIES_TOKEN.search(title)
            token = m.group(0) if m else table_number(label)
            tkey = (token, ordinal[token])
            ordinal[token] += 1
            table_names[tkey] = table_number(label)
            for variant in variants:
                if not variant or variant == "-":
                    continue
                try:
                    pins, _ = extract_pins.pins_for(rows, variants, layout, variant)
                except Exception:  # noqa: BLE001
                    continue
                # A heading may stack the packages that share one numbering
                # column, as CH32V203's en edition does with "LQFP48/QFN48X7";
                # the other edition may give each its own column, so the shared
                # column is registered once per package it names.
                for component in (v.strip() for v in variant.split("/")):
                    if not component:
                        continue
                    cell = columns.setdefault((tkey, canon_variant(component)),
                                              {"table": table_number(label),
                                               "variant": component, "pins": {}})
                    for p in pins:
                        cell["pins"][(p["number"], p["pad"])] = \
                            p.get("kind") or p.get("_pin_type", "")
                for p in pins:
                    for f in p.get("functions", []):
                        functions[(tkey, p["pad"])].add(
                            (f.get("signal") or "", f.get("route") or ""))
    return columns, dict(functions), table_names


def pair_leftovers(zh: dict, en: dict) -> dict[tuple, tuple]:
    """A single unpaired column on each side of one table names the same package.

    CH32V208's zh heading says LQFP64M where the en image says LQFP64; with every
    other column already paired, the two leftovers can only be each other.
    """
    remap: dict[tuple, tuple] = {}
    by_table_zh = collections.defaultdict(list)
    by_table_en = collections.defaultdict(list)
    for tkey, cvar in zh.keys() - en.keys():
        by_table_zh[tkey].append(cvar)
    for tkey, cvar in en.keys() - zh.keys():
        by_table_en[tkey].append(cvar)
    for tkey in by_table_zh.keys() & by_table_en.keys():
        if len(by_table_zh[tkey]) == 1 and len(by_table_en[tkey]) == 1:
            remap[(tkey, by_table_en[tkey][0])] = (tkey, by_table_zh[tkey][0])
    return remap


def merge_pins(zh: dict, en: dict, family: str, datasheet: str) -> list[dict]:
    for old, new in pair_leftovers(zh, en).items():
        en[new] = en.pop(old)
        en[new]["renamed_from"] = en[new]["variant"]
    out = []
    for key in sorted(set(zh) | set(en)):
        zh_cell = zh.get(key, {})
        en_cell = en.get(key, {})
        zh_pins = zh_cell.get("pins", {})
        en_pins = en_cell.get("pins", {})
        renamed = en_cell.get("renamed_from")
        # The same lead carrying different pads in the two editions is the one
        # genuine contradiction this table can hold.
        zh_by_pin = collections.defaultdict(set)
        en_by_pin = collections.defaultdict(set)
        for (pin, pad) in zh_pins:
            zh_by_pin[pin].add(pad)
        for (pin, pad) in en_pins:
            en_by_pin[pin].add(pad)
        for (pin, pad) in sorted(set(zh_pins) | set(en_pins),
                                 key=lambda k: (pin_key(k[0]), k[1])):
            in_zh, in_en = (pin, pad) in zh_pins, (pin, pad) in en_pins
            en_tag = f"pin-table:en({renamed})" if renamed else "pin-table:en"
            if in_zh and in_en:
                confidence, basis = "confirmed", f"pin-table:zh+{en_tag}"
            elif in_zh and pin in en_by_pin and not (en_by_pin[pin] & zh_by_pin[pin]):
                other = ",".join(sorted(en_by_pin[pin]))
                confidence, basis = "conflict", f"pin-table:zh+!pin-table:en(={other})"
            elif in_en and pin in zh_by_pin and not (zh_by_pin[pin] & en_by_pin[pin]):
                continue  # already reported from the zh side
            elif in_zh:
                confidence, basis = "reference", "pin-table:zh"
            else:
                confidence, basis = "reference", en_tag
            out.append({
                "family": family, "datasheet": datasheet,
                "table": zh_cell.get("table") or en_cell.get("table"),
                "package": zh_cell.get("variant") or en_cell.get("variant"),
                "pin": pin, "pad": pad,
                "kind": zh_pins.get((pin, pad)) or en_pins.get((pin, pad), ""),
                "confidence": confidence, "basis": basis,
            })
    return out


def merge_functions(zh: dict, en: dict, zh_names: dict, en_names: dict,
                    family: str, datasheet: str) -> list[dict]:
    out = []
    for tkey, pad in sorted(set(zh) | set(en)):
        zh_set = zh.get((tkey, pad), set())
        en_set = en.get((tkey, pad), set())
        for signal, route in sorted(zh_set | en_set):
            in_zh, in_en = (signal, route) in zh_set, (signal, route) in en_set
            confidence = "confirmed" if in_zh and in_en else "reference"
            basis = "+".join(s for s, hit in
                             (("pin-table:zh", in_zh), ("pin-table:en", in_en)) if hit)
            out.append({
                "family": family, "datasheet": datasheet,
                "table": zh_names.get(tkey) or en_names.get(tkey, ""),
                "pad": pad, "signal": signal, "route": route,
                "confidence": confidence, "basis": basis,
            })
    return out


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        # The "#" separator carries "#" in every row; see tables/README.ja.md.
        writer.writerows({**row, "#": "#"} for row in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("tables"))
    ap.add_argument("--family")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    pin_rows: list[dict] = []
    fn_rows: list[dict] = []
    for family in sorted(MIRRORS.glob("CH32*")):
        if args.family and family.name != args.family:
            continue
        names = {p.name for sub in ("datasheet_en", "datasheet_zh")
                 for p in (family / sub).glob("*DS0.PDF")}
        for name in sorted(names):
            editions = {}
            for lang in ("zh", "en"):
                path = family / f"datasheet_{lang}" / name
                try:
                    editions[lang] = read_edition(path) if path.exists() \
                        else ({}, {}, {})
                except Exception as exc:  # noqa: BLE001
                    print(f"{family.name}/{name} {lang}: 読めません {exc}",
                          file=sys.stderr)
                    editions[lang] = ({}, {}, {})
            pin_rows += merge_pins(editions["zh"][0], editions["en"][0],
                                   family.name, name)
            fn_rows += merge_functions(editions["zh"][1], editions["en"][1],
                                       editions["zh"][2], editions["en"][2],
                                       family.name, name)
            print(f"{family.name}/{name}: pins {len(pin_rows)} / functions {len(fn_rows)} 累計",
                  file=sys.stderr)

    pin_rows.sort(key=lambda r: (r["family"], r["datasheet"], r["table"],
                                 r["package"], pin_key(r["pin"]), r["pad"]))
    fn_rows.sort(key=lambda r: (r["family"], r["datasheet"], r["table"],
                                r["pad"], r["signal"], r["route"]))
    write_csv(args.out / "pins.csv", pin_rows, PIN_COLUMNS)
    write_csv(args.out / "pin_functions.csv", fn_rows, FUNCTION_COLUMNS)
    for name, rows in (("pins.csv", pin_rows), ("pin_functions.csv", fn_rows)):
        counts = collections.Counter(r["confidence"] for r in rows)
        print(f"{args.out}/{name}: {len(rows)} 行 {dict(counts)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
