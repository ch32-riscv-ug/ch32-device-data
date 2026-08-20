#!/usr/bin/env python3
"""Combine the four extractors into one candidate record fragment.

No single document holds a complete route selector. The EVT header states the bit
positions, the manual's register table the reset value, the manual's remap grid the
legal values and which pad each value reaches, and the datasheet which of those
pads the package bonds out. This joins them and reports where they disagree.

Selectors are kept only when a pin actually references them, which removes the bulk
of the register fields that are not pin routes at all.

Usage:
    uv run tools/build_candidate.py --header <evt>/ch32xxx.h --manual <rm>.pdf \
        --datasheet <ds>.pdf --package LQFP48 [--compare devices/<id>.json] [--emit]

It prints a candidate fragment for review and never writes device records.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import extract_pins  # noqa: E402
import extract_registers  # noqa: E402
import extract_remap  # noqa: E402
import extract_selectors  # noqa: E402
import signal_vocabulary  # noqa: E402
from extract_remap import canonical_field, canonical_signal  # noqa: E402


# The datasheet writes one signal where a timer shares a pad between a channel and
# its external trigger. Records so far split these; the tool keeps the datasheet's
# spelling and flags it rather than deciding silently.
COMBINED_SIGNAL = re.compile(r"^(?P<base>[A-Z0-9]+)_(?P<parts>CH\d+N?_ETR)$")


def selector_id(controller: str, field: str) -> str:
    """Spell the id the way existing records do: afio-tim1-remap."""
    return f"{controller}-{field.lower().replace('_', '-')}"


def bits_of(selector: dict) -> list[tuple[str, int]]:
    """A selector's bits as (register, bit), least-significant first."""
    return [(b["register"], b["bit"]) for b in selector["bits"]]


def show_bits(bits: list[tuple[str, int]]) -> str:
    return ";".join(f"{register}:{bit}" for register, bit in bits)


def read_silicon(
    header: Path, manual: Path | None
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Parse everything that is the same for every package of one silicon.

    Reading a reference manual is the slow part, so a bulk run does this once per
    family and reuses it for each of its SKUs.

    The manual is optional. CH32V407 and CH32V467 have no mirrored manual, and
    refusing to build without one left them with no selectors at all even though
    their EVT header defines every field and their datasheet pin table names every
    route. What is lost without a manual is the reset value and the grid's reading
    of which values are legal, so those stay unstated rather than guessed.
    """
    notes: list[str] = []

    selectors, sel_notes = extract_selectors.build(header)
    notes += [f"[header] {n}" for n in sel_notes]

    if manual is None:
        notes.append("[register] reference manual が無いので reset値と remap格子は未取得")
        return selectors, [], [], notes

    reg_fields, reg_notes = extract_registers.extract(manual, None)
    notes += [f"[register] {n}" for n in reg_notes[:5]]

    routes, remap_notes = extract_remap.extract(manual)
    notes += [f"[remap] {n}" for n in dict.fromkeys(remap_notes)]

    # Not every family tabulates its routes. CH32X035 states them only inside the
    # register field descriptions, so those are folded into the same pool.
    described = [r for f in reg_fields for r in extract_registers.routes_in(f)]
    if described:
        notes.append(f"[register] 説明文から読めた経路 {len(described)} 件を併用")
    return selectors, reg_fields, routes + described, notes


def build(header: Path, manual: Path | None, datasheet: Path, package: str) -> tuple[dict, list[str]]:
    selectors, reg_fields, routes, notes = read_silicon(header, manual)
    pins, pin_notes, _ = extract_pins.build(datasheet, package, "", "")
    notes += [f"[pins] {n}" for n in pin_notes[:5]]
    return join(selectors, reg_fields, routes, pins, notes)


def join(
    selectors: list[dict],
    reg_fields: list[dict],
    routes: list[dict],
    pins: list[dict],
    notes: list[str],
) -> tuple[dict, list[str]]:

    # Manual-side lookups, keyed the way the documents disagree least. Bits are
    # kept per register, because a field split across PCFR1 and PCFR2 appears in
    # the manual as one entry per register, under names that differ only in how
    # they mark the upper half (USART1_RM in PCFR1, USART1_RM1 in PCFR2).
    reset_of: dict[str, int] = {}
    reg_bits: dict[tuple[str, str, str], set[int]] = collections.defaultdict(set)
    for f in reg_fields:
        key = canonical_field(f["field"])
        controller, _, register = f["register"].rpartition("_")
        if f["reset_value"] is not None:
            reset_of.setdefault(key, f["reset_value"])
        # One field can take two rows in the same register's table, where the
        # manual gives its upper bits their own name: CH32V003 lists USART1_RM at
        # bit 2 and USART1_RM1 at bit 21. Both rows describe one field.
        reg_bits[(controller.lower(), register, key)].update(
            range(f["bit_offset"], f["bit_offset"] + f["bit_width"])
        )

    values_of: dict[str, set[int]] = collections.defaultdict(set)
    field_of_route: dict[tuple[str, int, str], str] = {}
    # Which selectors reach a pad at a given value. This is the last resort in
    # resolve(): it works without the signal name, but a shared pad means it
    # cannot say which peripheral's route it found.
    by_pad_value: dict[tuple[str, int], set[tuple[str, str]]] = collections.defaultdict(set)
    for r in routes:
        key = canonical_field(r["field"])
        values_of[key].add(r["value"])
        field_of_route.setdefault((canonical_signal(r["signal"]), r["value"], r["pad"]), key)
        by_pad_value[(r["pad"], r["value"])].add((key, r["signal"]))

    by_canonical = {canonical_field(s["field"]): s for s in selectors}

    routed = [
        (pin, fn)
        for pin in pins
        for fn in pin["functions"]
        if fn.get("_selector_value") is not None
    ]

    def resolve(pin, fn) -> tuple[str | None, str]:
        """Which selector field drives this function, and how that was decided.

        The pin table writes "T1C1_3" to mean "this pad carries TIM1's channel 1
        when TIM1's own remap field holds 3", so the signal names the peripheral
        and the peripheral names the selector. The pad does not: one pad carries
        several peripherals, and matching on it picks whichever of them the
        manual happened to describe at that value. CH32X035 shows the cost --
        the manual's TIM1_RM description is cut off in the PDF after value 1, and
        matching on the pad sent every TIM1 route at value 3 to the I2C1, SPI1
        and USART2 selectors, whose descriptions do mention PC0..PC7.

        So name evidence comes first and the pad is the fallback, not the other
        way round. Every step reads the name through the shared vocabulary rather
        than matching it literally: the pin table writes TX1 where the manual
        writes USART1_TX.
        """
        value = fn["_selector_value"]
        signal = canonical_signal(fn["signal"])
        key = field_of_route.get((signal, value, pin["pad"]))
        # The manual names this exact route. It may route a field the header does
        # not expose as a selector, hence the membership test.
        if key in by_canonical:
            return key, "signal"
        # The signal names its peripheral and that peripheral has a selector.
        pair = signal_vocabulary.split(fn["signal"])
        if pair and pair[0] in by_canonical:
            return pair[0], "peripheral"
        # Nothing usable in the name: align on the pad and the value, which
        # identifies a route without the name but cannot tell whose route it is.
        candidates = {
            k
            for k, _ in by_pad_value.get((pin["pad"], value), set())
            if k in by_canonical
        }
        if len(candidates) == 1:
            return candidates.pop(), "pad+value"
        # A peripheral whose selector is named for a part of it: ADC_ETR under
        # ADC1_ETRGIN.
        head = signal.partition("_")[0]
        matches = [k for k in by_canonical if k.split("_")[0] == head]
        return (matches[0], "prefix") if len(matches) == 1 else (None, "")

    used: set[str] = set()
    attested: dict[str, set[int]] = collections.defaultdict(set)
    for pin, fn in routed:
        key, how = resolve(pin, fn)
        if key is None:
            fn["_unresolved_selector"] = True
            notes.append(
                f"[join] {pin['pad']} {fn['signal']} 値{fn['_selector_value']}: "
                "selectorを決められず"
            )
            continue
        if COMBINED_SIGNAL.match(fn["signal"]):
            fn["_combined_signal"] = True
            notes.append(
                f"[join] {fn['signal']}: datasheetが1 signalで書く合成名。"
                "分割保持するかは人手判断"
            )
        selector = by_canonical[key]
        fn["selection"] = {
            "selector": selector_id(selector["controller"], selector["field"]),
            "values": [fn["_selector_value"]],
        }
        if how != "signal":
            fn["_selector_resolved_by"] = how
        used.add(key)
        attested[key].add(fn["_selector_value"])

    # The default route is a selector value like any other -- value 0 -- but no
    # document writes it that way: the pin table has a "default" column and the
    # remap grid usually starts at 1. Naming it here keeps every route of a
    # selector in one place, so a consumer does not have to join the remap tables
    # against the pin table to learn where a peripheral starts out.
    #
    # Only two of resolve()'s three answers are safe at value 0. Matching the
    # grid's own value-0 column is exact, and reading the peripheral out of the
    # signal name is what "default" means. Matching on pad+value is not: at reset
    # every peripheral sharing a pad is at value 0, so the pad picks no winner.
    for pin in pins:
        for fn in pin["functions"]:
            if fn.get("route") != "default" or fn.get("selection"):
                continue
            signal = canonical_signal(fn["signal"])
            key = field_of_route.get((signal, 0, pin["pad"]))
            if key not in by_canonical:
                pair = signal_vocabulary.split(fn["signal"])
                head = signal.partition("_")[0]
                matches = [k for k in by_canonical if k.split("_")[0] == head]
                if pair and pair[0] in by_canonical:
                    key = pair[0]
                elif len(matches) == 1:
                    key = matches[0]
                else:
                    # A pad whose default function belongs to no selector at all
                    # is the common case -- ADC inputs, power, oscillators -- and
                    # not something to report.
                    continue
            selector = by_canonical[key]
            fn["selection"] = {
                "selector": selector_id(selector["controller"], selector["field"]),
                "values": [0],
            }
            used.add(key)
            attested[key].add(0)

    # Keep only the selectors a pin refers to, completed from the manual.
    kept = []
    for key in sorted(used):
        s = by_canonical[key]
        bits = bits_of(s)
        controller = s["controller"]

        # The header and the manual each describe the whole field, so a register
        # only one of them names is a gap in the other rather than a conflict, and
        # the two are unioned. CH32V20x is the case that matters: its header
        # defines no AFIO_PCFR2 field at all, so USART1's upper bit and the whole
        # of USART4..USART8 can only come from the manual. Where both name the
        # same register and disagree, that is a conflict and gets said out loud.
        #
        # `order` is the registers the header named, in the order it named them,
        # which is the order the value's bits run in; a register the manual adds
        # goes after those.
        order = list(dict.fromkeys(register for register, _ in bits))
        completed = False
        for (rm_controller, register, field), found in sorted(reg_bits.items()):
            rm = sorted(found)
            if rm_controller != controller or field != key:
                continue
            if register in order:
                mine = [b for r, b in bits if r == register]
                if mine != rm:
                    notes.append(
                        f"[join] {selector_id(controller, s['field'])}: "
                        f"{register} の bit位置が資料間で不一致 header={mine} RM={rm}"
                    )
                continue
            if len(bits) + len(rm) > extract_selectors.MAX_FIELD_BITS:
                # Not a route selector; the register heading ran on and picked up
                # a wide field from the next register's table.
                continue
            bits += [(register, b) for b in rm]
            order.append(register)
            completed = True
            notes.append(
                f"[join] {selector_id(controller, s['field'])}: "
                f"{register}:{rm} をRMから補完（ヘッダに定義なし）"
            )
        bits.sort(key=lambda rb: (order.index(rb[0]), rb[1]))

        out = {
            "id": selector_id(controller, s["field"]),
            "controller": controller,
            "register": "|".join(order),
            "field": s["field"],
            "bits": [{"register": register, "bit": bit} for register, bit in bits],
        }
        # Three sources, none complete on its own. The manual's remap grid names
        # the columns, but writes a don't-care digit where a column stands for
        # more than one encoding, so it over-reports. The datasheet's pin table
        # attests only the values that route a bonded-out pad, so it under-reports
        # but is never wrong. The header enumerates values only where the vendor
        # spelled them out as separate defines. Taking the union keeps every value
        # a document actually states, and in particular keeps remap_routes.value a
        # subset of valid_values, which check_tables.py enforces.
        grid = set(values_of.get(key, []))
        pins_say = set(attested.get(key, ()))
        # Only where the header actually enumerated values. Its fallback is every
        # value the field can hold, which would swallow the other two sources.
        header_says = (
            set(s["valid_values"])
            if s.get("_valid_values_enumerated") and not completed
            else set()
        )
        found = grid | pins_say | header_says
        limit = 1 << len(bits)
        over = sorted(v for v in found if v >= limit)
        if over:
            notes.append(
                f"[join] {out['id']}: field幅{len(bits)}bitに収まらない値 {over} を除外"
            )
            found -= set(over)
        out["valid_values"] = sorted(found | {0}) or [0]
        out["_valid_values_source"] = "+".join(
            name
            for name, source in (
                ("RM remap格子", grid), ("datasheet pin表", pins_say), ("ヘッダ", header_says)
            )
            if source
        ) or "既定値のみ"
        if grid and pins_say - grid:
            out["_values_not_in_grid"] = sorted(pins_say - grid)
        if key in reset_of:
            out["reset_value"] = reset_of[key]
        else:
            out["_reset_value_missing"] = True
            notes.append(f"[join] {out['id']}: reset値がRMに見つからず")
        if len(out["register"].split("|")) > 1:
            out["_split_registers"] = out["register"].split("|")
        kept.append(out)

    return {"route_selectors": kept, "pins": pins}, notes


def score(candidate: dict, record: Path) -> None:
    rec = json.loads(record.read_text(encoding="utf-8"))
    out = sys.stderr

    want_sel = {canonical_field(s["field"]): s for s in rec.get("route_selectors", [])}
    got_sel = {canonical_field(s["field"]): s for s in candidate["route_selectors"]}
    print(f"\n照合: {record.name}", file=out)
    print("-" * 74, file=out)
    print(
        f"  route_selectors: record {len(want_sel)} / 候補 {len(got_sel)} / "
        f"共通 {len(want_sel.keys() & got_sel.keys())}",
        file=out,
    )
    exact = 0
    for key in sorted(want_sel.keys() & got_sel.keys()):
        w, g = want_sel[key], got_sel[key]
        same = (
            bits_of(w) == bits_of(g)
            and sorted(w["valid_values"]) == sorted(g["valid_values"])
            and w["reset_value"] == g.get("reset_value")
        )
        exact += same
        if not same:
            print(
                f"    差分 {g['id']:24} bit{show_bits(bits_of(g))}/{show_bits(bits_of(w))} "
                f"val{g['valid_values']}/{w['valid_values']} "
                f"reset{g.get('reset_value')}/{w['reset_value']}",
                file=out,
            )
    print(f"  bit・valid_values・reset がすべて一致: {exact}/{len(want_sel)}", file=out)
    for key in sorted(want_sel.keys() - got_sel.keys()):
        print(f"    候補に無い selector: {want_sel[key]['id']}", file=out)

    def triples(pins):
        return {
            (p["pad"], canonical_signal(f["signal"]), v)
            for p in pins
            for f in p["functions"]
            for v in (f.get("selection") or {}).get("values", [])
        }

    want, got = triples(rec.get("pins", [])), triples(candidate["pins"])
    print(f"\n  selection 付き経路: record {len(want)} / 候補 {len(got)}", file=out)
    print(f"  一致: {len(want & got)}/{len(want)}", file=out)
    unresolved = sum(
        1 for p in candidate["pins"] for f in p["functions"] if f.get("_unresolved_selector")
    )
    byhow = collections.Counter(
        f.get("_selector_resolved_by", "signal")
        for p in candidate["pins"]
        for f in p["functions"]
        if f.get("selection")
    )
    print(f"  selector未解決 {unresolved} / 解決内訳 {dict(byhow)}", file=out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--header", type=Path, required=True)
    ap.add_argument("--manual", type=Path, help="無い family は省略できる")
    ap.add_argument("--datasheet", type=Path, required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    candidate, notes = build(args.header, args.manual, args.datasheet, args.package)
    out = sys.stderr
    print(
        f"候補: route_selectors {len(candidate['route_selectors'])} / "
        f"pins {len(candidate['pins'])} / "
        f"function {sum(len(p['functions']) for p in candidate['pins'])}",
        file=out,
    )
    if notes:
        unique = list(dict.fromkeys(notes))
        print(f"\n要確認 {len(unique)} 件:", file=out)
        for note in unique[:20]:
            print(f"  - {note}", file=out)
        if len(unique) > 20:
            print(f"  ... 他 {len(unique) - 20} 件", file=out)

    if args.compare:
        score(candidate, args.compare)
    if args.emit:
        json.dump(candidate, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
