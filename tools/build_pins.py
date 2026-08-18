#!/usr/bin/env python3
"""Normalise the pin-definition tables into product-level pins.csv / pin_functions.csv.

The bottom of the hierarchy families -> series -> products -> pins. Rows are
keyed by part_number, so they join products.csv (and through it series and
families) relationally -- the datasheet and table a row came from are kept only
as provenance, to the right of the "#" separator.

    pins.csv           part_number, pin, pad: which pad sits on which lead
    pin_functions.csv  part_number, pad, signal, route: what the pad carries

A datasheet states each pinout once for a scope of products it names in the
caption ("CH32V103x8x6", "CH32V006 ... 除CH32V006F4U6以外", "TSSOP20(F8)"), so
one table's rows fan out to every product it covers. The resolution mirrors
what tools/build_all.py does for candidates: the product's column is found by
part number, then by package, and captions arbitrate when one package appears
in several tables.

Each language edition is read on its own and the readings compared; matching
absorbs the editions' drift in table numbering, column spelling and shared
columns. A fact both editions state is confirmed, one edition alone is
reference, and the same lead carrying different pads is a conflict.

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
REPO = Path(__file__).resolve().parent.parent

# The "#" column separates data from metadata; see tables/README.ja.md.
PIN_COLUMNS = ["part_number", "pin", "pad", "kind",
               "#", "confidence", "basis", "table", "datasheet"]
FUNCTION_COLUMNS = ["part_number", "pad", "signal", "route",
                    "#", "confidence", "basis", "table", "datasheet"]

SERIES_TOKEN = re.compile(r"CH32[A-Z0-9x]+")
FOOTNOTE = re.compile(r"[（(]\d+[)）]")
# "TSSOP20(F8)" -- the pin-class letter and capacity digit that pick the SKU group.
GROUP_TOKEN = re.compile(r"[（(]([A-Z]\d)[)）]")


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

    Returns (columns, functions, titles):
        columns:   {(tkey, canon variant): {"table", "variant", "pins": {(pin, pad): kind}}}
        functions: {(tkey, pad): {(signal, route)}}
        titles:    {tkey: (printed table number, caption title)}
    tkey names the table by the series in its caption (with an ordinal, one
    series can have several pin tables) so the editions pair despite numbering.
    """
    columns: dict = {}
    functions: dict = collections.defaultdict(set)
    titles: dict = {}
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
            m = re.search(r"CH32[A-Z0-9]+", title)
            token = m.group(0) if m else table_number(label)
            tkey = (token, ordinal[token])
            ordinal[token] += 1
            titles[tkey] = (table_number(label), title)
            for variant in variants:
                if not variant or variant == "-":
                    continue
                try:
                    pins, _ = extract_pins.pins_for(rows, variants, layout, variant)
                except Exception:  # noqa: BLE001
                    continue
                # A heading may stack the packages that share one numbering
                # column ("LQFP48/QFN48X7"); the other edition may give each its
                # own column, so it is registered once per package it names.
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
    return columns, dict(functions), titles


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


def merge_cells(zh: dict, en: dict) -> dict:
    """Cross-edition judgement per (tkey, cvar): {(pin, pad): (kind, conf, basis)}."""
    for old, new in pair_leftovers(zh, en).items():
        en[new] = en.pop(old)
        en[new]["renamed_from"] = en[new]["variant"]
    merged: dict = {}
    for key in sorted(set(zh) | set(en)):
        zh_cell, en_cell = zh.get(key, {}), en.get(key, {})
        zh_pins, en_pins = zh_cell.get("pins", {}), en_cell.get("pins", {})
        renamed = en_cell.get("renamed_from")
        en_tag = f"pin-table:en({renamed})" if renamed else "pin-table:en"
        zh_by_pin = collections.defaultdict(set)
        en_by_pin = collections.defaultdict(set)
        for (pin, pad) in zh_pins:
            zh_by_pin[pin].add(pad)
        for (pin, pad) in en_pins:
            en_by_pin[pin].add(pad)
        cell = {"table": zh_cell.get("table") or en_cell.get("table"),
                "variant": zh_cell.get("variant") or en_cell.get("variant"),
                "pins": {}}
        for (pin, pad) in set(zh_pins) | set(en_pins):
            in_zh, in_en = (pin, pad) in zh_pins, (pin, pad) in en_pins
            if in_zh and in_en:
                conf, basis = "confirmed", f"pin-table:zh+{en_tag}"
            elif in_zh and pin in en_by_pin and not (en_by_pin[pin] & zh_by_pin[pin]):
                other = ",".join(sorted(en_by_pin[pin]))
                conf, basis = "conflict", f"pin-table:zh+!pin-table:en(={other})"
            elif in_en and pin in zh_by_pin and not (zh_by_pin[pin] & en_by_pin[pin]):
                continue  # the zh side of this contradiction carries the row
            elif in_zh:
                conf, basis = "reference", "pin-table:zh"
            else:
                conf, basis = "reference", en_tag
            kind = zh_pins.get((pin, pad)) or en_pins.get((pin, pad), "")
            cell["pins"][(pin, pad)] = (kind, conf, basis)
        merged[key] = cell
    return merged


def merge_function_sets(zh: dict, en: dict) -> dict:
    """Cross-edition judgement per (tkey, pad): {(signal, route): (conf, basis)}."""
    merged: dict = {}
    for key in set(zh) | set(en):
        zh_set, en_set = zh.get(key, set()), en.get(key, set())
        entry = {}
        for fn in zh_set | en_set:
            in_zh, in_en = fn in zh_set, fn in en_set
            conf = "confirmed" if in_zh and in_en else "reference"
            basis = "+".join(s for s, hit in
                             (("pin-table:zh", in_zh), ("pin-table:en", in_en)) if hit)
            entry[fn] = (conf, basis)
        merged[key] = entry
    return merged


def scope_allows(part: str, titles: list[str]) -> bool | None:
    """Does a table's caption scope cover this part number?

    Returns True (named or matched), False (excluded or another group named),
    None (the caption states no scope this part can be judged by).
    """
    verdict: bool | None = None
    for title in titles:
        if not title:
            continue
        excluded = re.search(r"除(.*?)以外", title) or re.search(r"except([^)）]*)", title, re.I)
        if excluded and part in excluded.group(1).replace(" ", ""):
            return False
        if part in title.replace(" ", ""):
            return True
        tokens = []
        for m in re.finditer(r"(CH32[A-Z])([A-Z0-9x]+)((?:/\d{3})+)?", title):
            tokens.append(m.group(1) + m.group(2))
            # "CH32V303/305/307" abbreviates the later series to their digits.
            for digits in re.findall(r"\d{3}", m.group(3) or ""):
                tokens.append(m.group(1) + digits)
        for token in tokens:
            if excluded and token in excluded.group(1).replace(" ", ""):
                continue
            if "x" in token:
                # CH32V103x8x6: the lower-case x stands for any character.
                if re.fullmatch(token.replace("x", "[A-Z0-9]") + "[A-Z0-9]*", part):
                    return True
                verdict = False
            elif part.startswith(token):
                return True
            else:
                # The caption names some other group, which speaks against this
                # table unless a later token claims the part after all.
                verdict = False
        groups = GROUP_TOKEN.findall(title)
        if groups:
            # "TSSOP20(F8)/QSOP28(G8)": the pin-class+capacity pair names the group.
            if part[8:10] in groups:
                return True
            verdict = False
    return verdict


def resolve(part: str, package: str, cells: dict, titles: dict) -> tuple | None:
    """The (tkey, cvar) column that defines this product's pins.

    The same ladder build_all.choose_column climbs: a column named after the part
    itself wins; otherwise the package name finds the column and the captions
    arbitrate when several tables print that package.
    """
    bare = part[4:] if part.startswith("CH32") else part
    for key, cell in cells.items():
        v = cell["variant"].upper()
        if v == part or part.endswith(v) or part.rstrip("0123456789").endswith(v) \
                or (len(bare) >= 5 and bare in v):
            return key
    want = canon_variant(package) if package else None
    matches = [k for k in cells if want and k[1] == want]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        allowed = [k for k in matches if scope_allows(part, titles.get(k[0], []))]
        if len(allowed) == 1:
            return allowed[0]
        undecided = [k for k in matches
                     if scope_allows(part, titles.get(k[0], [])) is None]
        if len(undecided) == 1:
            return undecided[0]
    return None


def load_products(family_filter: str | None) -> dict:
    """products.csv rows grouped by (family, datasheet): [(part, package)]."""
    grouped: dict = collections.defaultdict(list)
    with (REPO / "tables" / "products.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if family_filter and row["family"] != family_filter:
                continue
            grouped[(row["family"], row["datasheet"])].append(
                (row["part_number"], row["package"]))
    return grouped


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        # The separator carries "#" in every row, so the boundary is visible
        # wherever one lands in the file.
        writer.writerows({**row, "#": "#"} for row in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("tables"))
    ap.add_argument("--family")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    products = load_products(args.family)
    pin_rows: list[dict] = []
    fn_rows: list[dict] = []
    unresolved: list[str] = []
    for (family, datasheet) in sorted(products):
        editions = {}
        for lang in ("zh", "en"):
            path = MIRRORS / family / f"datasheet_{lang}" / datasheet
            try:
                editions[lang] = read_edition(path) if path.exists() else ({}, {}, {})
            except Exception as exc:  # noqa: BLE001
                print(f"{family}/{datasheet} {lang}: 読めません {exc}", file=sys.stderr)
                editions[lang] = ({}, {}, {})
        cells = merge_cells(editions["zh"][0], editions["en"][0])
        functions = merge_function_sets(editions["zh"][1], editions["en"][1])
        titles: dict = collections.defaultdict(list)
        for _, _, ed_titles in editions.values():
            for tkey, (_, title) in ed_titles.items():
                titles[tkey].append(title)
        names = {tkey: number for ed in editions.values()
                 for tkey, (number, _) in ed[2].items()}
        for part, package in sorted(products[(family, datasheet)]):
            key = resolve(part, package, cells, titles)
            if key is None:
                unresolved.append(f"{part} ({family}/{datasheet} package={package})")
                continue
            cell = cells[key]
            pads = set()
            for (pin, pad), (kind, conf, basis) in cell["pins"].items():
                pads.add(pad)
                pin_rows.append({
                    "part_number": part, "pin": pin, "pad": pad, "kind": kind,
                    "confidence": conf, "basis": basis,
                    "table": cell["table"], "datasheet": datasheet,
                })
            for pad in pads:
                for (signal, route), (conf, basis) in \
                        functions.get((key[0], pad), {}).items():
                    fn_rows.append({
                        "part_number": part, "pad": pad,
                        "signal": signal, "route": route,
                        "confidence": conf, "basis": basis,
                        "table": names.get(key[0], ""), "datasheet": datasheet,
                    })
        print(f"{family}/{datasheet}: pins {len(pin_rows)} / functions {len(fn_rows)} 累計",
              file=sys.stderr)

    pin_rows.sort(key=lambda r: (r["part_number"], pin_key(r["pin"]), r["pad"]))
    fn_rows.sort(key=lambda r: (r["part_number"], r["pad"], r["signal"], r["route"]))
    write_csv(args.out / "pins.csv", pin_rows, PIN_COLUMNS)
    write_csv(args.out / "pin_functions.csv", fn_rows, FUNCTION_COLUMNS)
    for name, rows in (("pins.csv", pin_rows), ("pin_functions.csv", fn_rows)):
        counts = collections.Counter(r["confidence"] for r in rows)
        print(f"{args.out}/{name}: {len(rows)} 行 {dict(counts)}", file=sys.stderr)
    if unresolved:
        print(f"pin表に対応付けできなかった型番 {len(unresolved)} 件:", file=sys.stderr)
        for u in unresolved:
            print(f"  - {u}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
