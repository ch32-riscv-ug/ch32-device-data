#!/usr/bin/env python3
"""Combine the extractors into one candidate record fragment.

No single document holds a complete route selector. The EVT device header states
the bit positions, the manual's register table the reset value, the manual's
remap grid which pad each value reaches, the datasheet which of those pads the
package bonds out, and EVT's own GPIO_PinRemapConfig() -- compiled for the host
and run -- which encodings are real routes at all. This joins them and reports
where they disagree.

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
import extract_remap_fields  # noqa: E402
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
    header: Path, manuals: Path | list[Path] | None, gpio: Path | None = None
) -> tuple[list[dict], list[dict], list[dict], dict[str, set[int]], list[str]]:
    """Parse everything that is the same for every package of one silicon.

    Reading a reference manual is the slow part, so a bulk run does this once per
    family and reuses it for each of its SKUs.

    `manuals` is every edition of the manual, oldest first. Both editions are
    read and their routes unioned, because neither is complete: the English
    CH32X035 manual truncates TIM1_RM's route list after value 0 where the
    Chinese one reaches 2, and the Chinese edition has 895 register fields to the
    English one's 876. Where they state the same scalar differently the later
    edition wins, which is the Chinese one -- it is the newer of the two.

    Passing none of them is allowed. Refusing to build without a manual once left
    CH32V407/V467 with no selectors at all even though their EVT header defines
    every field and their datasheet pin table names every route. What is lost is
    the reset value and the grid's reading of which values are legal, and those
    stay unstated rather than guessed.
    """
    notes: list[str] = []

    selectors, sel_notes = extract_selectors.build(header)
    notes += [f"[header] {n}" for n in sel_notes]

    # The gpio header names one constant per real route and the gpio source
    # decodes it, so running that decoder is the only mechanical source for
    # *which encodings exist*. The device header enumerates bits, and often
    # only bit-index helpers for values; the manual's grid writes don't-care
    # digits. This needs a host compiler, and families that ship no
    # GPIO_Remap constant simply contribute nothing.
    evt_values: dict[str, set[int]] = {}
    if gpio is not None:
        observed, evt_notes = extract_remap_fields.extract_family(gpio)
        notes += [f"[evt] {n}" for n in evt_notes]
        for name, field in observed.items():
            if field.get("values"):
                evt_values.setdefault(canonical_field(name), set()).update(
                    field["values"].values()
                )

    editions = ([manuals] if isinstance(manuals, Path)
                else [m for m in (manuals or []) if m is not None])
    if not editions:
        notes.append("[register] reference manual が無いので reset値と remap格子は未取得")
        return selectors, [], [], evt_values, notes

    reg_fields: list[dict] = []
    routes: list[dict] = []
    for manual in editions:
        edition = manual.parent.name.rpartition("_")[2] or manual.parent.name
        fields, reg_notes = extract_registers.extract(manual, None)
        for f in fields:
            f["_edition"] = edition
        reg_fields += fields
        notes += [f"[register:{edition}] {n}" for n in reg_notes[:5]]

        grid, remap_notes = extract_remap.extract(manual)
        notes += [f"[remap:{edition}] {n}" for n in dict.fromkeys(remap_notes)]

        # Not every family tabulates its routes. CH32X035 states them only inside
        # the register field descriptions, so those are folded into the same pool.
        described = [r for f in fields for r in extract_registers.routes_in(f)]
        # Where the routes came from, because the two are not equally reliable.
        # The grid is a table; a description is prose read with a regex, and a
        # register-field table whose rows run on sweeps up pads that belong to
        # the next field. CH32V00x's ADC_ETRGREG_RM comes out of its description
        # with 35 pads at value 1 where its grid says one (PC2).
        for r in grid:
            r.setdefault("_source", "grid")
        for r in described:
            r.setdefault("_source", "description")
        notes.append(
            f"[register:{edition}] field {len(fields)} 件 / 格子経路 {len(grid)} 件 / "
            f"説明文経路 {len(described)} 件"
        )
        routes += grid + described
    return selectors, reg_fields, routes, evt_values, notes


def build(header: Path, manuals: Path | list[Path] | None, datasheet: Path,
          package: str, gpio: Path | None = None) -> tuple[dict, list[str]]:
    selectors, reg_fields, routes, evt_values, notes = read_silicon(header, manuals, gpio)
    pins, pin_notes, _ = extract_pins.build(datasheet, package, "", "")
    notes += [f"[pins] {n}" for n in pin_notes[:5]]
    return join(selectors, reg_fields, routes, pins, evt_values, notes)


def join(
    selectors: list[dict],
    reg_fields: list[dict],
    routes: list[dict],
    pins: list[dict],
    evt_values: dict[str, set[int]],
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
            known = reset_of.get(key)
            if known is not None and known != f["reset_value"]:
                notes.append(
                    f"[register] {key}: reset値が版で異なる {known} -> "
                    f"{f['reset_value']} ({f.get('_edition', '?')} を採用)"
                )
            reset_of[key] = f["reset_value"]
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
    #
    # Kept twice, because a run-on register description can put a pad under a
    # field that the grid does not, and that turns a pad the grid identifies
    # into an ambiguous one. The grid is consulted first and the union only when
    # it says nothing -- which is the whole of CH32X035, whose manual has no
    # grid at all.
    by_pad_value: dict[tuple[str, int], set[tuple[str, str]]] = collections.defaultdict(set)
    grid_pad_value: dict[tuple[str, int], set[tuple[str, str]]] = collections.defaultdict(set)
    for r in routes:
        key = canonical_field(r["field"])
        values_of[key].add(r["value"])
        field_of_route.setdefault((canonical_signal(r["signal"]), r["value"], r["pad"]), key)
        by_pad_value[(r["pad"], r["value"])].add((key, r["signal"]))
        if r.get("_source") == "grid":
            grid_pad_value[(r["pad"], r["value"])].add((key, r["signal"]))

    by_canonical = {canonical_field(s["field"]): s for s in selectors}

    routed = [
        (pin, fn)
        for pin in pins
        for fn in pin["functions"]
        if fn.get("_selector_value") is not None
    ]

    def owns(key: str, head: str) -> bool:
        """Whether selector `key` is the one a signal from peripheral `head` uses."""
        return key == head or key.split("_")[0] == head

    def other_instance(key: str, head: str) -> bool:
        """Whether the two are the same peripheral with a different instance number."""
        a, b = (signal_vocabulary.INSTANCE.match(key),
                signal_vocabulary.INSTANCE.match(head))
        return bool(a and b and a.group(1) == b.group(1)
                    and a.group(2) != b.group(2))

    def contradicted(key: str, head: str) -> bool:
        """Whether `key` cannot own this signal, judged by the names alone.

        Two ways to refute an answer. The peripheral the signal names has a
        selector of its own, so a different one cannot be it: CH32V407's
        TIM4_CH1 came back as TIM3's route -- the manual puts TIM4's grid on the
        page after TIM3's, and it read as one table -- and TIM4 has a selector.
        Or the two differ only in the instance number, which refutes it even
        where the signal's own selector is missing: CH32V203's pin table lists
        USART4 pins but its EVT header exposes no PCFR2 field at all, and
        USART1's selector is still not the one that routes USART4.

        Everything else is a gap rather than a contradiction, and stays
        unrefuted. CH32V303's DVP_D5 came back as ETH's route the same way as
        the TIM4 case, but the header exposes no DVP field, so there is no
        selector to prefer. And a peripheral that shares another's field must
        stay unrefuted or it loses its routes: CH32V30x's I2S3_WS really is
        routed by SPI3_REMAP, and nothing on that silicon is named I2S3.
        """
        if owns(key, head):
            return False
        return (any(owns(k, head) for k in by_canonical)
                or other_instance(key, head))

    PAD_EVIDENCE = {"grid": grid_pad_value, "any": by_pad_value}

    def resolve(pin, fn, value, pad_evidence=("grid", "any")) -> tuple[str | None, str]:
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

        `pad_evidence` says which readings of the pad may be used. The default
        route gets the grid only. The pin table's "default" column cannot be
        crossed with a pad, because at reset every peripheral sharing the pad
        sits at value 0 -- but the manual's own value-0 column is a statement
        about one field, and the name filter below keeps the other peripherals
        out of it, so the two objections do not apply to it.
        """
        signal = canonical_signal(fn["signal"])
        pair = signal_vocabulary.split(fn["signal"])
        head = pair[0] if pair else signal.partition("_")[0]
        key = field_of_route.get((signal, value, pin["pad"]))
        # The manual names this exact route. It may route a field the header does
        # not expose as a selector, hence the membership test.
        if key in by_canonical and not (pair and contradicted(key, head)):
            return key, "signal"
        # The signal names its peripheral and that peripheral has a selector.
        if pair and pair[0] in by_canonical:
            return pair[0], "peripheral"
        # Align on the pad and the value. This identifies a route without reading
        # the name, so it cannot say whose route it is -- which means it may not
        # answer against the name either. CH32V002's ADC_IETR shares PA2 with
        # TIM1's complementary channel, and the pad alone made it TIM1's; keeping
        # only the candidates the name allows leaves the ADC field it belongs to.
        def by_pad() -> tuple[str, str] | None:
            # The pad may only answer with a selector the name allows, not merely
            # one it fails to refute. CH32V30x's I2S3 has no selector of its own
            # -- SPI3_REMAP routes it -- so nothing about I2S3 is refutable, and
            # refutation alone let PC7 at value 0 answer TIM8, whose channel 2
            # shares the pad. Requiring agreement leaves it undecided instead,
            # which is what the manual leaves it as.
            for source in pad_evidence:
                candidates = {
                    k
                    for k, _ in PAD_EVIDENCE[source].get((pin["pad"], value), set())
                    if k in by_canonical and (not pair or owns(k, head))
                }
                if len(candidates) == 1:
                    return candidates.pop(), ("pad+value" if source == "any"
                                              else "pad+value(grid)")
            return None

        def by_prefix() -> tuple[str, str] | None:
            # A peripheral whose selector is named for a part of it: ADC_ETR
            # under ADC1_ETRGINJ, ISINK1 under ISINK1_ADJ.
            matches = [k for k in by_canonical if k.split("_")[0] == head]
            if len(matches) == 1:
                return matches[0], "prefix"
            # More than one, and the signal says which: CH32H417 has
            # UHSIF_CLK_RM and UHSIF_PORT_RM, and UHSIF_PORT33 is port 33 of
            # the second.
            numbered = [k for k in matches
                        if re.fullmatch(re.escape(k) + r"\d*", signal)]
            return (numbered[0], "prefix") if len(numbered) == 1 else None

        # Which of the two goes first depends on whether the name can police the
        # pad. With a readable name the pad is checked against it and beats the
        # prefix, which is what decides between CH32V00x's two ADC trigger
        # fields. Without one the pad answers unchecked and may name the wrong
        # owner, so a structural match on the selector's own name is better:
        # CH32M030's ISINK1 shares PA6 with TIM2 and belongs to ISINK1_ADJ.
        order = (by_pad, by_prefix) if pair else (by_prefix, by_pad)
        for step in order:
            found = step()
            if found:
                return found
        return None, ""

    used: set[str] = set()
    attested: dict[str, set[int]] = collections.defaultdict(set)
    for pin, fn in routed:
        key, how = resolve(pin, fn, fn["_selector_value"])
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
    # The same resolution, with only the manual's own value-0 column allowed as
    # pad evidence. A pad whose default function belongs to no selector at all is
    # the common case -- ADC inputs, power, oscillators -- and not something to
    # report.
    for pin in pins:
        for fn in pin["functions"]:
            if fn.get("route") != "default" or fn.get("selection"):
                continue
            key, how = resolve(pin, fn, 0, pad_evidence=("grid",))
            if key is None:
                continue
            if how != "signal":
                fn["_selector_resolved_by"] = how
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
            if rm == sorted(bit for _, bit in bits):
                # The same bits under a different register name is one register
                # spelled two ways, not a field split across two. The Chinese
                # CH32V103 manual writes AFIO_PCFR where the header writes
                # AFIO_PCFR1, and taking it at face value invented a second
                # register and doubled every one of that family's fields.
                notes.append(
                    f"[join] {selector_id(controller, s['field'])}: "
                    f"RMが同じbitを {register} という名前で書いている"
                    f"（headerは {order[0]}）。同じregisterとして扱う"
                )
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
        evt = set(evt_values.get(key, ()))
        # Only where the header actually enumerated values. Its fallback is every
        # value the field can hold, which would swallow the other sources.
        header_says = (
            set(s["valid_values"])
            if s.get("_valid_values_enumerated") and not completed
            else set()
        )
        found = grid | pins_say | header_says | evt
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
                ("RM remap格子", grid), ("datasheet pin表", pins_say),
                ("ヘッダ", header_says), ("EVTデコーダ", evt),
            )
            if source
        ) or "既定値のみ"
        if evt - (grid | pins_say | header_says):
            out["_values_only_from_evt"] = sorted(evt - (grid | pins_say | header_says))
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
    ap.add_argument("--manual", type=Path, action="append",
                    help="reference manual。両言語版を古い順に繰り返し指定できる")
    ap.add_argument("--gpio", type=Path,
                    help="EVT の <fam>_gpio.c。経路の列挙値をベンダのデコーダから観測する")
    ap.add_argument("--datasheet", type=Path, required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    candidate, notes = build(args.header, args.manual, args.datasheet, args.package,
                             args.gpio)
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
