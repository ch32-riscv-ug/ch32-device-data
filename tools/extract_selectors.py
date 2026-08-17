#!/usr/bin/env python3
"""Derive route-selector candidates from EVT vendor register bit defines.

The vendor device header (``ch32*.h``) states remap register fields as compiled
constants, so their bit positions are load-bearing and reliable. Everything else a
route selector needs -- legal values, reset value, and whether the field routes a
package pin at all -- is not in the header and must come from the reference manual
and human review.

This tool therefore emits *candidates* for review. It never writes device records.

Usage:
    uv run tools/extract_selectors.py <header.h> [--compare devices/<id>.json] [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFINE = re.compile(
    r"^#define\s+(?P<name>[A-Z0-9_]+)\s+\(\(uint32_t\)(?P<mask>0x[0-9A-Fa-f]+)\)"
    r"\s*(?:/\*(?P<comment>.*?)\*/)?\s*$"
)

# Register symbol prefix -> (controller id, register name) as used by the schema.
REGISTERS = {
    "AFIO_PCFR1_": ("afio", "PCFR1"),
    "EXTEN_": ("extend", "CTR"),
}

# Register-level plumbing rather than a field.
NOT_A_FIELD = {"BASE"}

# The vendor splits one logical field across two physical bits using a separate
# symbol. That the two belong together is stated nowhere; this rule is a human guess.
HIGH_BIT_SUFFIX = "_HIGH_BIT_REMAP"

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


def value_candidates(field: dict, subs: list[dict]) -> tuple[list[int] | None, str]:
    """Collect candidate field values from subordinate symbols.

    The header gives no way to tell an enumerated legal value from a bit-index
    helper: AFIO_PCFR1_TIM1_REMAP_1 (bit index) and ..._PARTIALREMAP_1 (a real
    value) are both 0x80. Treating every subordinate as a value therefore
    under-reports where the vendor listed only single-bit helpers, and cannot
    express reserved encodings at all. Always confirm against the manual.
    """
    width = len(bits_of(field["mask"]))
    if not subs:
        return None, "従属定義なし"
    raw = {s["mask"] for s in subs}
    if any(v & ~field["mask"] for v in raw):
        return None, "従属定義の値がfieldマスク外"
    positions = bits_of(field["mask"])
    vals = sorted({sum(((v >> p) & 1) << i for i, p in enumerate(positions)) for v in raw})
    helpers = sum(1 for s in subs if re.fullmatch(r".*_\d+", s["short"]))
    caveat = f"（うち{helpers}件はbit index補助の可能性）" if helpers else ""
    return vals, f"従属{len(subs)}件から{len(vals)}値/全{1 << width}値{caveat}"


def build(path: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    candidates: list[dict] = []
    parsed = parse_header(path)
    for prefix, (controller, register) in REGISTERS.items():
        entries = parsed[prefix]
        if not entries:
            continue
        fields, subordinate = classify(entries)
        fields, merged = merge_high_bits(fields)
        notes.extend(f"HIGH_BIT併合（人手規則・ヘッダに根拠なし）: {line}" for line in merged)
        for f in fields:
            bits = bits_of(f["mask"])
            if not bits:
                notes.append(f"マスク0のため除外: {f['symbol']}")
                continue
            if len(bits) > MAX_FIELD_BITS:
                notes.append(
                    f"{len(bits)}bit幅のため除外: {f['symbol']}（route selectorではない）"
                )
                continue
            sel: dict = {
                "_symbol": f["symbol"],
                "controller": controller,
                "register": register,
                "field": f["short"],
            }
            if bits == list(range(bits[0], bits[0] + len(bits))):
                sel["bit_offset"] = bits[0]
                sel["bit_width"] = len(bits)
            else:
                sel["bit_positions"] = bits
                notes.append(
                    f"非連続field: {f['symbol']} bits={bits}"
                    "（値のLSB順が昇順bit順と一致する前提。RMで要確認）"
                )
            vals, how = value_candidates(f, subordinate.get(f["short"], []))
            sel["valid_values"] = vals if vals is not None else list(range(1 << len(bits)))
            sel["_valid_values_source"] = how if vals is not None else "幅からの推定"
            sel["_reset_value"] = None
            candidates.append(sel)
    return candidates, notes


def selector_bits(sel: dict) -> tuple:
    bits = sel.get("bit_positions")
    if bits is None:
        bits = list(range(sel["bit_offset"], sel["bit_offset"] + sel["bit_width"]))
    return (sel["controller"], sel["register"], tuple(bits))


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
            print(f"  取得できず  {t['id']:26} bits={list(k[2])}")
            continue
        hit += 1
        diffs = []
        if c["field"] != t["field"]:
            diffs.append(f"field名 header={c['field']} / record={t['field']}")
        if sorted(c["valid_values"]) != sorted(t["valid_values"]):
            diffs.append(
                f"valid_values header={c['valid_values']} / record={t['valid_values']}"
            )
        print(f"  {'一致    ' if not diffs else '差分あり'}  {t['id']:26} bits={list(k[2])}")
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
            print(f"    {c['_symbol']:40} bits={list(selector_bits(c)[2])}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("header", type=Path, help="EVT の ch32*.h")
    ap.add_argument("--compare", type=Path, help="既存 device record と照合する")
    ap.add_argument("--emit", action="store_true", help="候補JSONを標準出力へ")
    args = ap.parse_args()

    candidates, notes = build(args.header)
    print(f"入力: {args.header}")
    print(f"route-selector 候補: {len(candidates)} 件")
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
