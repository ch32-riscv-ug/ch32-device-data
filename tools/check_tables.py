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
                      "clock_symbols", "clock_init", "evt_variants", "systick",
                      "memory_configs", "pin_alternate", "interrupts",
                      "memory_map", "features", "sources")}

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

    # SystemInit's steps. The order is the fact here, so it has to be a dense
    # run per (family, function) -- a gap means a line the reader dropped.
    init_steps: dict[tuple[str, str], list[int]] = {}
    for r in t["clock_init"]:
        check("clock_init", r["function"], r["family"], families, "families")
        if r["action"] not in ("set", "clear", "write", "poll", "trim"):
            bad.append(f"clock_init: {r['family']} {r['function']} の action "
                       f"{r['action']!r} が set/clear/write/poll/trim でない")
        if not r["value"].isdigit() or not r["step"].isdigit():
            bad.append(f"clock_init: {r['family']} {r['function']} の value/step が数でない")
            continue
        if r["register"] and "->" not in r["register"]:
            bad.append(f"clock_init: {r['family']} {r['function']} の register "
                       f"{r['register']!r} が BLOCK->REGISTER の形でない")
        if r["address"] and not address.match(r["address"]):
            bad.append(f"clock_init: {r['family']} {r['function']} の address "
                       f"{r['address']!r} が 0x のあと8桁でない")
        # Only a trim reads from somewhere; a register step's address is the
        # register itself and naming a source as well would be two answers.
        if bool(r["source"]) and r["action"] != "trim":
            bad.append(f"clock_init: {r['family']} {r['function']} の "
                       f"{r['action']} が source を持っている")
        init_steps.setdefault((r["family"], r["function"]), []).append(int(r["step"]))
        # A poll condition or a trim source that names a symbol is a reference
        # to clock_symbols, and a reference to a row that does not exist leaves
        # the consumer to guess the bit. CH32X315's RCC_HSIRDY was exactly that.
        for symbol in re.findall(r"\b(?:RCC|FLASH|EXTEN)_[A-Za-z0-9_]+", r["condition"]):
            if (r["family"], symbol) not in symbols:
                bad.append(f"clock_init: {r['family']} {r['function']} の condition が呼ぶ "
                           f"{symbol} が clock_symbols にない")
    for (family, function), steps in init_steps.items():
        if sorted(steps) != list(range(min(steps), min(steps) + len(steps))):
            bad.append(f"clock_init: {family} {function} の step が連番でない: "
                       f"{sorted(steps)}")

    # SysTick's layout. The one thing a consumer must not get wrong is where the
    # compare register is, so the offsets have to be a consistent non-overlapping
    # map and the write granularity has to divide the width.
    seen_offsets: dict[tuple[str, str], set[int]] = {}
    for r in t["systick"]:
        check("systick", r["register"], r["family"], families, "families")
        where = f"{r['family']} {r['block']} {r['register']}"
        try:
            at, width, writable = (int(r["offset"], 16), int(r["width_bits"]),
                                   int(r["write_bits"]))
        except ValueError:
            bad.append(f"systick: {where} の offset/width_bits/write_bits が数でない")
            continue
        if width % writable:
            bad.append(f"systick: {where} の write_bits {writable} が "
                       f"width_bits {width} を割り切らない")
        if r["address"] and not address.match(r["address"]):
            bad.append(f"systick: {where} の address {r['address']!r} が "
                       "0x のあと8桁でない")
        if r["address"] and int(r["address"], 16) % 4:
            bad.append(f"systick: {where} の address が4byte境界にない")
        occupied = seen_offsets.setdefault((r["family"], r["block"]), set())
        span = set(range(at, at + width // 8))
        if span & occupied:
            bad.append(f"systick: {where} の offset {at:#x} が同じ block の"
                       "他の register と重なる")
        occupied |= span

    # AF番号の書き込み先。**af-N の行があるのに書き込み先が無いと、経路の情報が
    # そこで行き止まりになる**（F-10/F-12 がまさにそれだった）ので、pin_functions
    # の af-N と (family, pad) で結合できることを見る。pad は "PA0-WKUP" のように
    # 役割つきで書かれることがあるので、頭の P?? だけで突き合わせる。
    pad_head = re.compile(r"^(P[A-H]\d{1,2})")
    alternate = {(r["family"], r["pad"]) for r in t["pin_alternate"]}
    family_of = {r["part_number"]: r["family"] for r in t["products"]}
    seen_bits: dict[tuple[str, str], set[int]] = {}
    for r in t["pin_alternate"]:
        check("pin_alternate", r["pad"], r["family"], families, "families")
        where = f"{r['family']} {r['pad']}"
        if not pad_head.fullmatch(r["pad"]):
            bad.append(f"pin_alternate: {where} の pad が P<port><pin> でない")
        bits = [b for b in r["bits"].split(";") if b]
        if len(bits) != int(r["width_bits"]):
            bad.append(f"pin_alternate: {where} の bits が {len(bits)} 個で "
                       f"width_bits {r['width_bits']} と合わない")
        indices = set()
        for bit in bits:
            register, _, index = bit.partition(":")
            if register != r["register"] or not index.isdigit() or int(index) > 31:
                bad.append(f"pin_alternate: {where} の bits {bit!r} が "
                           f"{r['register']} の 0-31 でない")
            else:
                indices.add(int(index))
        occupied = seen_bits.setdefault((r["family"], r["register"]), set())
        if indices & occupied:
            bad.append(f"pin_alternate: {where} の bit が同じ register の"
                       "他の pad と重なる")
        occupied |= indices
        if not address.match(r["address"]) or int(r["address"], 16) % 4:
            bad.append(f"pin_alternate: {where} の address が 0x8桁の4byte境界でない")
    for r in t["pin_functions"]:
        if not r["route"].startswith("af-"):
            continue
        head = pad_head.match(r["pad"])
        family = family_of.get(r["part_number"])
        if head and family and (family, head.group(1)) not in alternate:
            bad.append(f"pin_functions: {r['part_number']} {r['pad']} の "
                       f"{r['route']} を書く先が pin_alternate にない")

    # FLASH/SRAM の可変な分割。**間違えると linker script が黙って壊れる**ので、
    # ここで見るのは (1) 出荷時の1組が products.csv と一致すること、(2) 符号が
    # 互いに排他であること、(3) フィールド幅が符号を表せること。
    sram_of = {r["part_number"]: r["sram_bytes"] for r in t["products"]}
    flash_of = {r["part_number"]: r["flash_bytes"] for r in t["products"]}
    by_part: dict[str, list[dict]] = {}
    for r in t["memory_configs"]:
        check("memory_configs", r["part_number"], r["part_number"], products, "products")
        by_part.setdefault(r["part_number"], []).append(r)
        if not re.fullmatch(r"[01x]+", r["value"]):
            bad.append(f"memory_configs: {r['part_number']} の value "
                       f"{r['value']!r} が 0/1/x でない")
        for column in ("code_bytes", "sram_bytes"):
            if not r[column].isdigit() or int(r[column]) <= 0:
                bad.append(f"memory_configs: {r['part_number']} の {column} が正の数でない")
    span = re.compile(r"^\[(\d+):(\d+)\]$")
    for part, rows in sorted(by_part.items()):
        # 「既定」と呼べる1組は資料が決めていない（build_memory.py の説明）。
        # 列が言うのは「datasheet の比較表が載せる組」だけで、それは1つ。
        quoted = [r for r in rows if r["datasheet_value"]]
        if len(quoted) != 1:
            bad.append(f"memory_configs: {part} の datasheet_value が "
                       f"{len(quoted)} 行ある（比較表が載せる組は1つ）")
        if len(quoted) == 1:
            if quoted[0]["sram_bytes"] != sram_of.get(part):
                bad.append(f"memory_configs: {part} の datasheet_value の sram_bytes "
                           f"{quoted[0]['sram_bytes']} が products.csv の "
                           f"{sram_of.get(part)} と違う")
            elif quoted[0]["code_bytes"] != flash_of.get(part):
                # ここが合わないのは products.csv が零等待領域ではなく総容量を
                # 取っているとき（worklist の F-14）。linker script が壊れる。
                bad.append(f"memory_configs: {part} の datasheet_value の code_bytes "
                           f"{quoted[0]['code_bytes']} が products.csv の "
                           f"flash_bytes {flash_of.get(part)} と違う")
        # 2つの符号が同じビット並びに当たってはいけない。x は don't care なので
        # 桁ごとに「どちらかが x」なら重なる。
        values = [r["value"] for r in rows]
        for i, one in enumerate(values):
            for other in values[i + 1:]:
                if all(a == b or "x" in (a, b) for a, b in zip(one, other)):
                    bad.append(f"memory_configs: {part} の符号 {one} と {other} が"
                               "同じ値に当たる")
        needed = max(len(v.rstrip("x")) for v in values)
        for column in ("option_byte_bits", "obr_bits"):
            cell = rows[0][column]
            if not cell:
                continue
            found = span.match(cell)
            if not found:
                bad.append(f"memory_configs: {part} の {column} {cell!r} が [hi:lo] でない")
                continue
            hi, lo = int(found.group(1)), int(found.group(2))
            if hi - lo + 1 < needed:
                bad.append(f"memory_configs: {part} の {column} {cell} は "
                           f"{hi - lo + 1}bit だが符号は {needed}bit 要る")

    # 読んだ原典の版。全 family が揃っていないと、生成物の差分の原因を
    # 「入力が変わった」と「再生成を忘れた」に切り分けられない。
    recorded = {r["family"] for r in t["sources"]}
    for family in families - recorded:
        bad.append(f"sources: {family} の版が記録されていない"
                   "——差分の原因を切り分けられなくなる")
    for r in t["sources"]:
        check("sources", r["family"], r["family"], families, "families")
        if not re.fullmatch(r"[0-9a-f]{40}", r["commit"]):
            bad.append(f"sources: {r['family']} の commit "
                       f"{r['commit']!r} が 40 桁の hash でない")
        if r["dirty"]:
            bad.append(f"sources: {r['family']} の mirror に未コミットの変更が"
                       "あった——commit は読んだ中身を説明しない")

    # アドレス空間の地図。番地は 0x 付きの 32bit、同じ (family, kind, region) は1行。
    span = re.compile(r"^0x[0-9a-f]{8}$")
    seen_region: set[tuple[str, str, str, str]] = set()
    for r in t["memory_map"]:
        check("memory_map", r["region"], r["family"], families, "families")
        if not span.match(r["base_address"]):
            bad.append(f"memory_map: {r['family']} {r['region']} の base_address "
                       f"{r['base_address']!r} が 0x8桁でない")
        key = (r["family"], r["kind"], r["region"], r["condition"])
        if key in seen_region:
            bad.append(f"memory_map: {r['family']} の {r['kind']}/{r['region']} が重複")
        seen_region.add(key)

    # 機能の一覧は datasheet が覆う series の事実。節番号は1冊の中でだけ一意なので、
    # (series群, section) で重ならないこと。
    seen_feature: set[tuple[str, str]] = set()
    for r in t["features"]:
        check("features", r["section"], r["family"], families, "families")
        check("features", r["section"], r["series"], series, "series", ";")
        check("features", r["section"], r["datasheet"], documents, "documents")
        if not r["feature"] and not r["feature_zh"]:
            bad.append(f"features: {r['series']} {r['section']} が両言語とも空")
        key = (r["series"], r["section"])
        if key in seen_feature:
            bad.append(f"features: {r['series']} の節 {r['section']} が重複")
        seen_feature.add(key)

    # 割り込みは family ごとに1つの列挙で、番号は variant で入れ替わる。
    # 同じ (family, condition) の中では番号が1つの名前しか指さないこと。
    seen_irq: dict[tuple[str, int, str], str] = {}
    for r in t["interrupts"]:
        check("interrupts", r["name"], r["family"], families, "families")
        if r["kind"] not in ("exception", "irq"):
            bad.append(f"interrupts: {r['family']} {r['name']} の kind "
                       f"{r['kind']!r} が exception/irq でない")
        if not r["number"].isdigit():
            bad.append(f"interrupts: {r['family']} {r['name']} の number が数でない")
            continue
        key = (r["family"], int(r["number"]), r["condition"])
        if key in seen_irq and seen_irq[key] != r["name"]:
            bad.append(f"interrupts: {r['family']} の {r['number']} 番が "
                       f"{seen_irq[key]} と {r['name']} で重なる"
                       f"（condition={r['condition'] or 'なし'}）")
        seen_irq[key] = r["name"]
    # 例外の番号は全部、周辺割り込みの番号より小さい。境目の番号は family で
    # 違う（CH32H417 は 32 番から。IPC と HSEM がプロセッサ側の枠にいる）ので、
    # 番号そのものではなく2群が交ざらないことを見る。
    for family in {r["family"] for r in t["interrupts"]}:
        mine = [r for r in t["interrupts"] if r["family"] == family
                and r["number"].isdigit()]
        highest = [int(r["number"]) for r in mine if r["kind"] == "exception"]
        lowest = [int(r["number"]) for r in mine if r["kind"] == "irq"]
        if highest and lowest and max(highest) >= min(lowest):
            bad.append(f"interrupts: {family} の例外 {max(highest)} 番が "
                       f"周辺割り込みの最小 {min(lowest)} 番以上")

    # A `condition` naming a compile-time variant macro is unresolvable for a
    # part unless evt_variants says which parts set it.
    macros = {(r["family"], r["macro"]) for r in t["evt_variants"]}
    for r in t["evt_variants"]:
        check("evt_variants", r["macro"], r["family"], families, "families")
        check("evt_variants", r["macro"], r["part_number"], products, "products")
    named = re.compile(r"\bCH32[A-Za-z0-9_]+\b")
    for table in ("clock_configs", "clock_sources", "interrupts"):
        for r in t[table]:
            for macro in named.findall(r["condition"]):
                if (r["family"], macro) not in macros:
                    bad.append(f"{table}: {r['family']} の condition が呼ぶ "
                               f"{macro} が evt_variants にない")

    # Data columns carry no CJK: Chinese readings are evidence (kept in the
    # *_basis and *_zh columns), never the displayed value. A leak here
    # means the translation dictionary in curated/translations.json is missing
    # an entry, or an extractor let prose fragments through.
    #
    # `_zh` で終わる列は中文の原文を残すためのもの（`label_zh`・`feature_zh`）。
    # 名前で除くので、同じ役目の列が増えても検査を書き足さずに済む。
    cjk = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
    for name, rows in t.items():
        if not rows:
            continue
        columns = []
        for column in rows[0]:
            if column == "#":
                break
            if not column.endswith("_zh"):
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
