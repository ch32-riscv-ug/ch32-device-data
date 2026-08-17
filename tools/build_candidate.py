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
from extract_remap import canonical_field, canonical_signal  # noqa: E402


# The datasheet writes one signal where a timer shares a pad between a channel and
# its external trigger. Records so far split these; the tool keeps the datasheet's
# spelling and flags it rather than deciding silently.
COMBINED_SIGNAL = re.compile(r"^(?P<base>[A-Z0-9]+)_(?P<parts>CH\d+N?_ETR)$")


def selector_id(controller: str, field: str) -> str:
    """Spell the id the way existing records do: afio-tim1-remap."""
    return f"{controller}-{field.lower().replace('_', '-')}"


def bits_of(selector: dict) -> list[int]:
    if "bit_positions" in selector:
        return list(selector["bit_positions"])
    return list(range(selector["bit_offset"], selector["bit_offset"] + selector["bit_width"]))


def read_silicon(header: Path, manual: Path) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Parse everything that is the same for every package of one silicon.

    Reading a reference manual is the slow part, so a bulk run does this once per
    family and reuses it for each of its SKUs.
    """
    notes: list[str] = []

    selectors, sel_notes = extract_selectors.build(header)
    notes += [f"[header] {n}" for n in sel_notes]

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


def build(header: Path, manual: Path, datasheet: Path, package: str) -> tuple[dict, list[str]]:
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

    # Manual-side lookups, keyed the way the documents disagree least.
    reset_of: dict[str, int] = {}
    reg_bits: dict[str, list[int]] = {}
    for f in reg_fields:
        key = canonical_field(f["field"])
        if f["reset_value"] is not None:
            reset_of.setdefault(key, f["reset_value"])
        reg_bits.setdefault(key, list(range(f["bit_offset"], f["bit_offset"] + f["bit_width"])))

    values_of: dict[str, set[int]] = collections.defaultdict(set)
    field_of_route: dict[tuple[str, int, str], str] = {}
    # A pad reached at a given selector value identifies the route without relying on
    # the signal name, which lets the two vocabularies be aligned. CH32V003 names the
    # same route TIM1_CH1 in the manual and T1CH1 in the datasheet.
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

    def resolve(pin, fn, alias: dict[str, str]) -> tuple[str | None, str]:
        """Which selector field drives this function, and how that was decided."""
        value = fn["_selector_value"]
        name = alias.get(fn["signal"], fn["signal"])
        signal = canonical_signal(name)
        key = field_of_route.get((signal, value, pin["pad"]))
        # The manual may route a field the header does not expose as a selector.
        if key in by_canonical:
            return key, "alias" if name != fn["signal"] else "signal"
        # The documents may name the same route differently. Align on the pad and
        # value instead, which identifies the route without using the name at all.
        candidates = {
            (k, rm_name)
            for k, rm_name in by_pad_value.get((pin["pad"], value), set())
            if k in by_canonical
        }
        if len(candidates) == 1:
            return candidates.pop()[0], "pad+value"
        # Families without a remap grid: fall back to the peripheral prefix.
        head = signal.partition("_")[0]
        matches = [k for k in by_canonical if k.split("_")[0] == head]
        return (matches[0], "prefix") if len(matches) == 1 else (None, "")

    # First pass: learn how the two documents spell the same route, but only from
    # pads whose value reaches exactly one route. Where several routes share a pad at
    # the same value the pairing is guesswork, so nothing is learned from it.
    proposals: dict[str, set[str]] = collections.defaultdict(set)
    ambiguous = 0
    for pin, fn in routed:
        value = fn["_selector_value"]
        if field_of_route.get((canonical_signal(fn["signal"]), value, pin["pad"])):
            continue
        found = {
            rm_name
            for k, rm_name in by_pad_value.get((pin["pad"], value), set())
            if k in by_canonical
        }
        if len(found) == 1:
            rm_name = found.pop()
            if canonical_signal(rm_name) != canonical_signal(fn["signal"]):
                proposals[fn["signal"]].add(rm_name)
        elif found:
            ambiguous += 1
    if ambiguous:
        notes.append(
            f"[join] pad+値が複数経路を指し対応付けられなかった function: {ambiguous}"
        )
    alias = {ds: next(iter(rm)) for ds, rm in proposals.items() if len(rm) == 1}
    for ds, rm in sorted(proposals.items()):
        if len(rm) > 1:
            notes.append(f"[join] signal名 {ds} の対応先が一意でない: {sorted(rm)}")

    # Second pass: resolve with the learned aliases in hand.
    used: set[str] = set()
    for pin, fn in routed:
        key, how = resolve(pin, fn, alias)
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
    aliases = {ds: sorted(rm) for ds, rm in proposals.items()}

    # Keep only the selectors a pin refers to, completed from the manual.
    kept = []
    for key in sorted(used):
        s = by_canonical[key]
        out = {
            "id": selector_id(s["controller"], s["field"]),
            "controller": s["controller"],
            "register": s["register"],
            "field": s["field"],
        }
        out.update(
            {"bit_positions": s["bit_positions"]}
            if "bit_positions" in s
            else {"bit_offset": s["bit_offset"], "bit_width": s["bit_width"]}
        )
        manual_values = sorted(values_of.get(key, []))
        out["valid_values"] = manual_values or s["valid_values"]
        out["_valid_values_source"] = "RM remap格子" if manual_values else "ヘッダ幅からの推定"
        if key in reset_of:
            out["reset_value"] = reset_of[key]
        else:
            out["_reset_value_missing"] = True
            notes.append(f"[join] {out['id']}: reset値がRMに見つからず")
        if key in reg_bits and reg_bits[key] != bits_of(s):
            out["_bit_disagreement"] = {"header": bits_of(s), "manual": reg_bits[key]}
            notes.append(
                f"[join] {out['id']}: bit位置が資料間で不一致 "
                f"header={bits_of(s)} RM={reg_bits[key]}"
            )
        kept.append(out)

    if aliases:
        notes.append(
            f"[join] datasheetとRMでsignal名が異なる経路を {len(aliases)} 件 pad+値で対応付けた"
        )
    return (
        {
            "route_selectors": kept,
            "pins": pins,
            "_signal_aliases": dict(sorted(aliases.items())),
        },
        notes,
    )


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
                f"    差分 {g['id']:24} bit{bits_of(g)}/{bits_of(w)} "
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
    alias = candidate.get("_signal_aliases") or {}
    if alias:
        print(f"\n  pad+値から導出したsignal名対応 ({len(alias)}件):", file=out)
        for ds, rm in list(alias.items())[:14]:
            print(f"    datasheet {ds:12} = RM {', '.join(rm)}", file=out)
        if len(alias) > 14:
            print(f"    ... 他 {len(alias) - 14} 件", file=out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--header", type=Path, required=True)
    ap.add_argument("--manual", type=Path, required=True)
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
