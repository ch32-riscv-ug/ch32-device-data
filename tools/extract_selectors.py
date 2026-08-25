#!/usr/bin/env python3
"""Derive route-selector candidates from EVT vendor register bit defines.

The vendor device header (``ch32*.h``) states remap register fields as compiled
constants, so their bit positions are load-bearing and reliable. Everything else a
route selector needs -- legal values, reset value, and whether the field routes a
package pin at all -- is not in the header and must come from the reference manual
and human review.

A field is not always one register's worth of bits. CH32L103, CH32M103 and the
CH32V20x/V30x families ran out of room in PCFR1 and put the upper bits of several
selectors in PCFR2, which the header states as a second define:

    AFIO_PCFR1_USART1_RM     PCFR1 bit 2         the low bit
    AFIO_PCFR2_USART1_RM_H   PCFR2 bits 19,20    the high bits of the same field

Writing only the PCFR1 bit selects route 0 or 1 and silently ignores anything
higher, so a selector is emitted with its bits qualified by register, ordered
least-significant first, and both halves joined into one field.

This tool therefore emits *candidates* for review. It never writes device records.

Usage:
    uv run tools/extract_selectors.py <header.h> [--compare <record>.json] [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import signal_vocabulary  # noqa: E402

DEFINE = re.compile(
    r"^#define\s+(?P<name>[A-Z0-9_]+)\s+\(\(uint32_t\)(?P<mask>0x[0-9A-Fa-f]+)\)"
    r"\s*(?:/\*(?P<comment>.*?)\*/)?\s*$"
)

# Register symbol prefix -> (controller id, register name) as used by the schema.
# Order matters: a field split across registers takes its bits in this order, which
# is the order the vendor's own GPIO_PinRemapConfig() composes the value in.
REGISTERS = {
    "AFIO_PCFR1_": ("afio", "PCFR1"),
    "AFIO_PCFR2_": ("afio", "PCFR2"),
    "EXTEN_": ("extend", "CTR"),
}

# Register-level plumbing rather than a field.
NOT_A_FIELD = {"BASE"}

# Within one register the vendor splits a field using a suffixed symbol.
HIGH_BIT_SUFFIX = "_HIGH_BIT_REMAP"

# Across registers it does the same two ways, both seen in shipped headers:
#   CH32L103   AFIO_PCFR2_USART1_RM_H     the _H suffix names the upper half
#   CH32V30x   AFIO_PCFR2_USART1_REMAP    the same field name in the other register
# Either way the PCFR2 define joins the PCFR1 field of the same name. A PCFR2 field
# with no PCFR1 counterpart -- CH32V30x USART4..USART8, CH32L103 LPTIM -- is a
# selector in its own right.
HIGH_HALF_SUFFIX = "_H"

# A routing field is never this wide. Wider masks are unlock keys (EXTEN_KEY_R is
# 0xFFFFFFFF), DAC values, or whole-register masks.
MAX_FIELD_BITS = 8


def bits_of(mask: int) -> list[int]:
    return [i for i in range(32) if mask >> i & 1]


def parse_header(path: Path) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {prefix: [] for prefix in REGISTERS}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = DEFINE.match(line.strip())
        if not m:
            continue
        name = m.group("name")
        for prefix in REGISTERS:
            if not name.startswith(prefix):
                continue
            short = name[len(prefix):]
            if short not in NOT_A_FIELD:
                found[prefix].append(
                    {
                        "symbol": name,
                        "short": short,
                        "mask": int(m.group("mask"), 16),
                        "comment": (m.group("comment") or "").strip(),
                    }
                )
            break
    return found


def classify(entries: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    """Split defines into field masks and their subordinate symbols.

    A define is a field when no other define is a proper name prefix of it.
    Subordinates attach to the longest *field* prefix rather than the longest name
    prefix, so AFIO_PCFR1_TIM1_REMAP_PARTIALREMAP_1 lands under TIM1_REMAP even
    though TIM1_REMAP_PARTIALREMAP is itself a defined symbol.
    """
    names = {e["short"] for e in entries}
    fields = [
        e
        for e in entries
        if not any(e["short"].startswith(n + "_") for n in names - {e["short"]})
    ]
    field_names = {f["short"] for f in fields}
    subordinate: dict[str, list[dict]] = {}
    for e in entries:
        if e["short"] in field_names:
            continue
        parents = [n for n in field_names if e["short"].startswith(n + "_")]
        if parents:
            subordinate.setdefault(max(parents, key=len), []).append(e)
    return fields, subordinate


def merge_high_bits(fields: list[dict]) -> tuple[list[dict], list[str]]:
    """Join a _HIGH_BIT_REMAP define into its field, within one register."""
    by_short = {f["short"]: f for f in fields}
    merged: list[str] = []
    drop: set[str] = set()
    for f in fields:
        if not f["short"].endswith(HIGH_BIT_SUFFIX):
            continue
        target = by_short.get(f["short"][: -len(HIGH_BIT_SUFFIX)] + "_REMAP")
        if target is None:
            continue
        target["mask"] |= f["mask"]
        drop.add(f["short"])
        merged.append(f"{f['symbol']} -> {target['symbol']}")
    return [f for f in fields if f["short"] not in drop], merged


class Selector:
    """One route selector, whose bits may span more than one register.

    ``parts`` holds the per-register halves in REGISTERS order, which is the order
    the value's bits run from least to most significant.
    """

    def __init__(self, controller: str, register: str, field: dict, subs: list[dict]):
        self.controller = controller
        self.field = field["short"]
        self.symbol = field["symbol"]
        self.parts: list[dict] = []
        self.add(register, field, subs)

    def add(self, register: str, field: dict, subs: list[dict]) -> None:
        self.parts.append(
            {"register": register, "mask": field["mask"],
             "symbol": field["symbol"], "subs": subs}
        )

    @property
    def registers(self) -> list[str]:
        return [p["register"] for p in self.parts]

    @property
    def split(self) -> bool:
        return len(self.parts) > 1

    def bits(self) -> list[tuple[str, int]]:
        """The field's bits, least-significant first, each tagged by register."""
        return [(p["register"], b) for p in self.parts for b in bits_of(p["mask"])]

    def value_of(self, register: str, mask: int) -> int:
        """Read a subordinate's mask as a field value."""
        return sum(
            1 << i
            for i, (reg, bit) in enumerate(self.bits())
            if reg == register and mask >> bit & 1
        )

    def is_bit_index(self, register: str, sub: dict) -> bool:
        """Whether a subordinate names a bit of the field rather than a value.

        The vendor writes both, and they look alike: AFIO_PCFR1_TIM1_REMAP_1 is
        the field's bit 1 (mask 0x10000) while ..._REMAP_PARTIALREMAP_1 is the
        value 1 (mask 0x8000). Reading a bit index as a value invents encodings --
        a 3-bit field would always claim 1, 2 and 4 -- and CH32L103's USART3_RM
        shows that is wrong: its legal values are 0, 2 and 3, never 1.

        The tell is that the name's trailing number is the index of the one bit
        the mask sets.
        """
        m = re.fullmatch(r".*_(\d+)", sub["short"])
        mask = sub["mask"]
        if not m or not mask or mask & (mask - 1):
            return False
        index = int(m.group(1))
        bits = self.bits()
        return index < len(bits) and bits[index] == (register, mask.bit_length() - 1)

    def valid_values(self) -> tuple[list[int] | None, str]:
        """The values the header names, or None where it names none.

        Only the subordinates that name a value count; see is_bit_index(). What
        is left is what the vendor spelled out -- NOREMAP, PARTIALREMAP2,
        FULLREMAP -- which is an honest enumeration including its gaps: CH32V30x
        TIM1 defines 0, 1 and 3, and 2 really is reserved.

        Where the vendor listed only bit helpers this returns None rather than a
        guess, because a field's width says nothing about which encodings the
        silicon accepts. The manual is then the only source.
        """
        width = len(self.bits())
        if self.split:
            # Each half enumerates only its own bits, so no combination of them
            # spells a value that crosses the register boundary. Nothing here is
            # trustworthy; the manual's remap grid is the only source.
            return None, "分割fieldのため従属定義から値を決められない"
        named = [(p["register"], sub) for p in self.parts for sub in p["subs"]
                 if not self.is_bit_index(p["register"], sub)]
        if not named:
            return None, "値を名指しする従属定義なし（bit index補助のみ）"
        raw = {(register, sub["mask"]) for register, sub in named}
        if any(mask & ~p["mask"] for p in self.parts for (reg, mask) in raw
               if reg == p["register"]):
            return None, "従属定義の値がfieldマスク外"
        vals = sorted({self.value_of(reg, mask) for reg, mask in raw})
        return vals, f"従属{len(named)}件から{len(vals)}値/全{1 << width}値"


def build(path: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    parsed = parse_header(path)

    # Read each register on its own first: a PCFR1 subordinate never prefixes a
    # PCFR2 field, so the name-prefix rule only makes sense within one register.
    per_register: list[tuple[str, str, list[dict], dict[str, list[dict]]]] = []
    for prefix, (controller, register) in REGISTERS.items():
        entries = parsed[prefix]
        if not entries:
            continue
        fields, subordinate = classify(entries)
        fields, merged = merge_high_bits(fields)
        notes.extend(f"HIGH_BIT併合（人手規則・ヘッダに根拠なし）: {line}" for line in merged)
        per_register.append((controller, register, fields, subordinate))

    selectors: dict[tuple[str, str], Selector] = {}
    for controller, register, fields, subordinate in per_register:
        for f in fields:
            key = (controller, signal_vocabulary.canonical_field(f["short"]))
            known = selectors.get(key)
            subs = subordinate.get(f["short"], [])
            if known is None:
                selectors[key] = Selector(controller, register, f, subs)
                continue
            if register in known.registers:
                # Two names collapsing onto one key inside one register would make
                # the join arbitrary; keep them apart under their own name and say
                # so, rather than merging bits that may belong to different fields.
                notes.append(
                    f"同一registerで名前が衝突: {f['symbol']} と {known.symbol}"
                )
                spare = (controller, f"{key[1]}:{f['short']}")
                selectors[spare] = Selector(controller, register, f, subs)
                continue
            known.add(register, f, subs)
            notes.append(
                f"分割field併合（{'_H接尾辞' if f['short'].endswith(HIGH_HALF_SUFFIX) else '同名'}）: "
                f"{f['symbol']} -> {known.symbol}"
            )

    candidates: list[dict] = []
    for sel in selectors.values():
        bits = sel.bits()
        if not bits:
            notes.append(f"マスク0のため除外: {sel.symbol}")
            continue
        if len(bits) > MAX_FIELD_BITS:
            notes.append(
                f"{len(bits)}bit幅のため除外: {sel.symbol}（route selectorではない）"
            )
            continue
        out: dict = {
            "_symbol": sel.symbol,
            "controller": sel.controller,
            "register": "|".join(sel.registers),
            "field": sel.field,
            "bits": [{"register": reg, "bit": bit} for reg, bit in bits],
        }
        within = [bit for _, bit in bits]
        contiguous = within == list(range(within[0], within[0] + len(within)))
        if not sel.split and not contiguous:
            notes.append(
                f"非連続field: {sel.symbol} bits={within}"
                "（値のLSB順が昇順bit順と一致する前提。RMで要確認）"
            )
        vals, how = sel.valid_values()
        # Whether these values are something the header states or merely every
        # value the field is wide enough to hold. A consumer of this candidate has
        # to know the difference: the guess is an upper bound, not evidence.
        out["_valid_values_enumerated"] = vals is not None
        out["valid_values"] = vals if vals is not None else list(range(1 << len(bits)))
        out["_valid_values_source"] = how if vals is not None else "幅からの推定"
        out["_reset_value"] = None
        if sel.split:
            out["_split_registers"] = sel.registers
        candidates.append(out)
    return candidates, notes


def selector_bits(sel: dict) -> tuple:
    """A comparison key: the controller and the field's register-qualified bits."""
    return (sel["controller"], tuple((b["register"], b["bit"]) for b in sel["bits"]))


def show_bits(key: tuple) -> str:
    return ",".join(f"{reg}:{bit}" for reg, bit in key[1])


def score(candidates: list[dict], record: Path) -> None:
    rec = json.loads(record.read_text(encoding="utf-8"))
    truth = rec.get("route_selectors", [])
    by_bits = {selector_bits(c): c for c in candidates}
    truth_by_bits = {selector_bits(t): t for t in truth}

    print(f"\n照合: {record.name}  record {len(truth)} selector / 抽出 {len(candidates)} 件")
    print("-" * 74)
    hit = 0
    for k, t in truth_by_bits.items():
        c = by_bits.get(k)
        if c is None:
            print(f"  取得できず  {t['id']:26} bits={show_bits(k)}")
            continue
        hit += 1
        diffs = []
        if c["field"] != t["field"]:
            diffs.append(f"field名 header={c['field']} / record={t['field']}")
        if sorted(c["valid_values"]) != sorted(t["valid_values"]):
            diffs.append(
                f"valid_values header={c['valid_values']} / record={t['valid_values']}"
            )
        print(f"  {'一致    ' if not diffs else '差分あり'}  {t['id']:26} bits={show_bits(k)}")
        for d in diffs:
            print(f"{'':14}└ {d}")

    extra = [c for k, c in by_bits.items() if k not in truth_by_bits]
    print(
        f"\n  bit位置一致 {hit}/{len(truth)}   取得できず {len(truth) - hit}"
        f"   record外の余剰 {len(extra)}"
    )
    if extra:
        print("\n  record に無い抽出結果（採否は人が判断する）:")
        for c in sorted(extra, key=selector_bits):
            print(f"    {c['_symbol']:40} bits={show_bits(selector_bits(c))}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("header", type=Path, help="EVT の ch32*.h")
    ap.add_argument("--compare", type=Path, help="既存 device record と照合する")
    ap.add_argument("--emit", action="store_true", help="候補JSONを標準出力へ")
    args = ap.parse_args()

    candidates, notes = build(args.header)
    print(f"入力: {args.header}")
    print(f"route-selector 候補: {len(candidates)} 件")
    split = [c for c in candidates if c.get("_split_registers")]
    if split:
        print(f"うち register をまたぐ分割 field: {len(split)} 件")
        for c in split:
            bits = ",".join(f"{b['register']}:{b['bit']}" for b in c["bits"])
            print(f"  {c['field']:20} {bits}")
    if notes:
        print("\n人手の判断が入った箇所 / 要確認:")
        for n in notes:
            print(f"  - {n}")
    guessed = sum(1 for c in candidates if c["_valid_values_source"] == "幅からの推定")
    print(f"\nreset_value をヘッダから取得できず: {len(candidates)}/{len(candidates)} 件")
    print(f"valid_values が幅からの推定: {guessed}/{len(candidates)} 件")

    if args.compare:
        score(candidates, args.compare)
    if args.emit:
        json.dump(candidates, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
