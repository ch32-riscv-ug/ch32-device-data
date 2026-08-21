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

sys.path.insert(0, str(Path(__file__).parent))

import signal_vocabulary  # noqa: E402


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
                      "errata", "operating_conditions", "evt_examples",
                      "clock_configs", "clock_prescalers", "clock_sources",
                      "clock_symbols", "evt_variants")}

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

    # A route must sit on the selector its own peripheral owns. The ways it can
    # end up elsewhere are silent: a manual's grid split across two pages reads
    # as one table and puts TIM4's routes under TIM3_RM, and matching a route on
    # (pad, value) picks whichever peripheral sharing the pad the manual happened
    # to describe. Both produce a row a consumer would write the wrong register
    # for. Only refutable cases are reported -- either the peripheral has a
    # selector of its own in this series, or it differs from the selector's
    # peripheral in the instance number alone -- which is what leaves the
    # genuinely shared fields alone: CH32V407's I2S3_WS really is routed by
    # SPI3_REMAP, and nothing on that silicon is named I2S3.
    owners: dict[str, set[str]] = {}
    for r in t["remap_fields"]:
        key = signal_vocabulary.canonical_field(r["field"])
        owners.setdefault(r["series"], set()).add(key.split("_")[0])
    def same_name_other_instance(a: str, b: str) -> bool:
        # The same rule build_candidate refutes an answer with, read from the
        # one module that owns how a peripheral name is spelled.
        ma, mb = (signal_vocabulary.INSTANCE.match(a),
                  signal_vocabulary.INSTANCE.match(b))
        return bool(ma and mb and ma.group(1) == mb.group(1)
                    and ma.group(2) != mb.group(2))

    for r in t["remap_routes"]:
        peripheral = r.get("peripheral")
        field = field_by_key.get((r["series"], r["selector"]))
        if not peripheral or field is None:
            continue
        key = signal_vocabulary.canonical_field(field["field"])
        if key == peripheral or key.split("_")[0] == peripheral:
            continue
        if (peripheral in owners.get(r["series"], set())
                or same_name_other_instance(key, peripheral)):
            bad.append(f"remap_routes: {r['series']} {r['selector']} 値{r['value']} の "
                       f"{r['signal']} ({r['pad']}) は {peripheral} の信号なので "
                       f"{key} の selector には載らない")

    # The clock tables come from EVT's system_ch32*.c, one row per configuration
    # and #if branch. What can be checked without EVT is that they join, that a
    # divider a configuration selects is one the family actually encodes, and
    # that the frequencies parse.
    prescalers = {(r["family"], r["field"], r["divider"]) for r in t["clock_prescalers"]}
    for r in t["clock_prescalers"]:
        check("clock_prescalers", r["field"], r["family"], families, "families")
        if not r["divider"].isdigit() or int(r["divider"]) < 1:
            bad.append(f"clock_prescalers: {r['family']} {r['field']} の divider "
                       f"{r['divider']!r} が分周比でない")
    for r in t["clock_sources"]:
        check("clock_sources", r["consumer"], r["family"], families, "families")
        if not r["value"].isdigit() or not r["shift"].isdigit():
            bad.append(f"clock_sources: {r['family']} {r['consumer']} の value/shift が数でない")
    for r in t["clock_configs"]:
        where = f"{r['family']} {r['config']}"
        check("clock_configs", r["config"], r["family"], families, "families")
        for column, field in (("hpre", "HPRE"), ("ppre1", "PPRE1"), ("ppre2", "PPRE2")):
            divider = r[column]
            if divider and (r["family"], field, divider) not in prescalers:
                bad.append(f"clock_configs: {where} の {column}={divider} が "
                           f"clock_prescalers に無い")
        for domain in (d for d in r["domains"].split(";") if d):
            name, _, hz = domain.partition("=")
            if not name or not hz.isdigit():
                bad.append(f"clock_configs: {where} の domains {domain!r} が "
                           "名前=Hz の形でない")
        if r["flash_latency"] and not r["flash_latency"].isdigit():
            bad.append(f"clock_configs: {where} の flash_latency が数でない")
        # A flash clock divider, not a wait count. Keeping it out of
        # flash_latency is the whole point, so it has to look like a divider.
        div = r["flash_sck_div"]
        if div and not (div.isdigit() and int(div) >= 1
                        and int(div) & (int(div) - 1) == 0):
            bad.append(f"clock_configs: {where} の flash_sck_div {div!r} が"
                       "2のべき乗の分周比でない")
        if div and r["flash_latency"]:
            bad.append(f"clock_configs: {where} が flash_latency と flash_sck_div の"
                       "両方を持つ（単位が違うので同時には書けない）")

    # A `pll` or `outside_rcc` cell names symbols. Without clock_symbols the
    # name is all there is, and the name does not give the number away:
    # CH32V307's RCC_PLLMULL18 is 0x003C0000 and RCC_PLLMULL18_EXTEN is 0.
    address = re.compile(r"^0x[0-9a-f]{8}$")
    symbols = {(r["family"], r["symbol"]) for r in t["clock_symbols"]}
    # A prescaler symbol is in two tables, keyed differently: clock_prescalers
    # enumerates the header's whole divider table, clock_symbols records what a
    # configuration wrote. Where they overlap they have to say the same number,
    # which is a real cross-check because the two are built from different reads.
    prescaler_value = {(r["family"], r["field"], r["divider"]): r["value"]
                       for r in t["clock_prescalers"]}
    prescaler_symbol = re.compile(r"^RCC_(?P<field>[A-Za-z0-9]+?)_[Dd]iv(?P<divider>\d+)$")
    for r in t["clock_symbols"]:
        check("clock_symbols", r["symbol"], r["family"], families, "families")
        if r["role"] not in ("value", "mask", "poll"):
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の role "
                       f"{r['role']!r} が value/mask/poll でない")
        if not r["value"].isdigit():
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の value が数でない")
        if r["address"] and not address.match(r["address"]):
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の address "
                       f"{r['address']!r} が 0x のあと8桁でない")
        if "->" not in r["register"]:
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の register "
                       f"{r['register']!r} が BLOCK->REGISTER の形でない")
        m = prescaler_symbol.match(r["symbol"])
        if m:
            key = (r["family"], m.group("field").upper(), m.group("divider"))
            other = prescaler_value.get(key)
            if other is not None and other != r["value"]:
                bad.append(f"clock_symbols: {r['family']} {r['symbol']} の value "
                           f"{r['value']} が clock_prescalers の {other} と違う")
    for r in t["clock_configs"]:
        for cell in (r["pll"], r["outside_rcc"]):
            for entry in (e for e in cell.split(";") if e):
                symbol = entry.split(" ")[-1]
                if (r["family"], symbol) not in symbols:
                    bad.append(f"clock_configs: {r['family']} {r['config']} が呼ぶ "
                               f"{symbol} が clock_symbols にない")

    # A `condition` naming a compile-time variant macro is unresolvable for a
    # part unless evt_variants says which parts set it.
    macros = {(r["family"], r["macro"]) for r in t["evt_variants"]}
    for r in t["evt_variants"]:
        check("evt_variants", r["macro"], r["family"], families, "families")
        check("evt_variants", r["macro"], r["part_number"], products, "products")
    named = re.compile(r"\bCH32[A-Za-z0-9_]+\b")
    for table in ("clock_configs", "clock_sources"):
        for r in t[table]:
            for macro in named.findall(r["condition"]):
                if (r["family"], macro) not in macros:
                    bad.append(f"{table}: {r['family']} の condition が呼ぶ "
                               f"{macro} が evt_variants にない")

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
