#!/usr/bin/env python3
"""Normalise the AFIO route selectors into remap_fields.csv / remap_routes.csv.

pin_functions.csv says a signal reaches a pad on route "remap-2"; these two
tables say what that means in hardware:

    remap_fields.csv  one row per (series, selector): the register field that
                      chooses the route -- bits, valid values, reset value
    remap_routes.csv  one row per (series, selector, value, signal, pad):
                      which value routes which signal to which pad

Two columns need reading carefully.

``bits`` names a register per bit, ``PCFR1:2;PCFR2:19;PCFR2:20``, least
significant first. Most selectors sit inside one register, but CH32L103,
CH32M103 and the CH32V20x/V30x families put the upper bits of several selectors
in PCFR2, and a consumer that writes only PCFR1 selects a different route
without any error. ``register`` summarises the same fact as ``PCFR1|PCFR2``.

``peripheral`` and ``role`` are the normalised reading of ``signal``, which is
kept exactly as its document spells it. The documents write the same role four
ways -- USART1_TX, UART_TX, TX1, UTX -- so tools/signal_vocabulary.py reads them
into one pair and leaves the pair empty where no rule applies, rather than
guessing.

Derived from candidates/, where tools/build_candidate.py joined the EVT header
bit definitions, the reference manual's register tables and remap grid, and the
datasheet pin table. The join checked itself while building, but the per-fact
agreements are not recorded in the files, so every row here is confidence
"reference" with the source chain named; promoting them to confirmed by
re-verifying EVT against RM per selector is the known next step.

Usage:
    uv run tools/build_remap.py [--out tables] [--candidates candidates]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import signal_vocabulary  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
CANDIDATES = paths.CANDIDATES

SERIES = re.compile(r"^(CH32[A-Z]\d{3})")

FIELD_COLUMNS = ["series", "selector", "controller", "register", "field",
                 "bits", "valid_values", "reset_value",
                 "#", "confidence", "basis"]
# `peripheral`/`role`（語彙で揃えた読み）は索引 `index/routes.csv` が付ける
# （tools/build_index.py）。ここは資料の綴り（signal・pad）だけ。
ROUTE_COLUMNS = ["series", "selector", "value", "signal", "pad",
                 "#", "confidence", "basis"]

FIELD_BASIS = "candidates(evt-header+rm-register-table+rm-remap-grid:en)"
# The EVT header does not define this field at all, so nothing cross-checks the
# manual's reading of it and the SDK offers no macro to write it. CH32V20x's
# USART4..USART8 are the only fields in any family that come this way.
MANUAL_BASIS = "candidates(rm-register-table+rm-remap-grid:en)"
# **経路の basis は候補が記録した出所から組む**（`build_candidate.route_sources`）。
# 値が既定値かどうかで決め打っていたので、remap 格子の表を1つも持たない family
# （`CH32X035RM`・`CH32V205RM`・`CH32X315RM` は zh/en とも0経路）でも `rm-remap-grid` を
# 名乗っていた——CH32X035 の234行のうち186行がそれだった（F-66。2026-09-15）。
# 出所が記録されていない古い候補は、既定値かどうかの従来の読みに落とす。
def route_basis(sources, disputed: int | None = None, editions=()) -> str:
    """`basis` の綴り。格子が別の値だと言っているならそれも書く（F-73）。

    食い違いの書き方は他の表と同じ DSL——`!<出所>(<列>=<値>)` で「その出所は何と
    言うか」を持つ。`index/conflicts.csv` はこれを読んで `alternative` 列に写す。

    **末尾の版の印は、その経路を述べた application manual の版**。長らく `:en` の
    決め打ちで、**中文版しか言っていない経路も `en` を名乗っていた**（F-75。実測:
    説明文由来は zh のみ 503・en のみ 465、格子由来は en のみ 29）。manual が
    どちらも述べていなければ印は付かない（pin 表は版を持たない）。

    >>> route_basis(["datasheet-pin-table", "rm-field-description"], editions=["en", "zh"])
    'candidates(datasheet-pin-table+rm-field-description:en+zh)'
    >>> route_basis(["datasheet-pin-table-default"])
    'candidates(datasheet-pin-table-default)'
    >>> route_basis(["datasheet-pin-table"], disputed=0)
    'candidates(datasheet-pin-table)+!rm-remap-grid(value=0)'
    """
    tag = f":{'+'.join(sorted(editions))}" if editions else ""
    out = f"candidates({'+'.join(sources)}{tag})"
    return out if disputed is None else f"{out}+!rm-remap-grid(value={disputed})"


# **2つの資料が言っていれば `confirmed`。** この表の出所は「datasheet の pin 表」と
# 「application manual」（格子と説明文の2通りの述べ方）で、食い違いが起きるのは
# **資料のあいだ**（F-73 がまさにそれ）。同じ manual の zh/en が経路について食い違う
# ことは全corpusで一度も無いので、版の一致を確度に数えても本物の食い違いを見つける
# 力にならない——だから「2つの資料が一致」を confirmed の意味に採る（2026-09-16、
# ユーザー判断）。片方しか言っていなければ `reference` のまま。
DATASHEET_SOURCES = frozenset({"datasheet-pin-table", "datasheet-pin-table-default"})
MANUAL_SOURCES = frozenset({"rm-remap-grid", "rm-field-description"})


def route_confidence(sources) -> str:
    """出所の顔ぶれから確度を決める。

    >>> route_confidence(["datasheet-pin-table", "rm-remap-grid"])
    'confirmed'
    >>> route_confidence(["datasheet-pin-table-default"])
    'reference'
    """
    said = set(sources)
    return "confirmed" if (said & DATASHEET_SOURCES) and (said & MANUAL_SOURCES) else "reference"


LEGACY_ROUTE_BASIS = ["datasheet-pin-table", "rm-remap-grid"]
LEGACY_DEFAULT_BASIS = ["datasheet-pin-table-default"]


def bits_of(selector: dict) -> str:
    """The field's bits as register:bit, least significant first."""
    return ";".join(f"{b['register']}:{b['bit']}" for b in selector.get("bits") or ())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    ap.add_argument("--candidates", type=Path, default=CANDIDATES)
    args = ap.parse_args()

    fields: dict = {}
    disagreements: list[str] = []
    routes: dict = {}
    disputed: dict = {}   # 経路の鍵 → 格子が言う別の値（F-73）
    editions: dict = {}   # 経路の鍵 → それを述べた manual の版（F-75）
    from_grid: set = set()   # 値を格子から採った経路（pin 表はその値を言っていない）
    for path in sorted(args.candidates.glob("ch32*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        part = data.get("part_number", path.stem.upper())
        m = SERIES.match(part)
        if not m:
            continue
        series = m.group(1)
        for sel in data.get("route_selectors") or []:
            key = (series, sel.get("id", ""))
            entry = {
                "series": series,
                "selector": sel.get("id", ""),
                "controller": sel.get("controller", ""),
                "register": sel.get("register", ""),
                "field": sel.get("field", ""),
                "bits": bits_of(sel),
                "valid_values": ";".join(str(v) for v in sel.get("valid_values") or []),
                "reset_value": "" if sel.get("reset_value") is None
                               else str(sel["reset_value"]),
                "_from_manual": bool(sel.get("_from_manual")),
                "_sources": tuple(sel.get("sources") or ()),
            }
            known = fields.get(key)
            if known is None:
                fields[key] = entry
            elif known != entry:
                # The same silicon described twice must not differ; surface it.
                # A package that bonds out fewer pads attests fewer values, so
                # the widest reading wins and only the rest is a disagreement.
                merged = dict(known)
                merged["valid_values"] = ";".join(
                    str(v) for v in sorted(
                        {int(v) for v in known["valid_values"].split(";") if v}
                        | {int(v) for v in entry["valid_values"].split(";") if v}
                    )
                )
                merged["_sources"] = tuple(sorted(set(known["_sources"])
                                                  | set(entry["_sources"])))
                skip = ("valid_values", "_sources")
                if {k: v for k, v in merged.items() if k not in skip} == {
                    k: v for k, v in entry.items() if k not in skip
                }:
                    fields[key] = merged
                else:
                    disagreements.append(
                        f"{series} {key[1]}: {part} の記述が他SKUと異なる"
                    )
        for pin in data.get("pins") or []:
            pad = pin.get("pad", "")
            for fn in pin.get("functions") or []:
                selection = fn.get("selection")
                if not selection:
                    continue
                for value in selection.get("values") or []:
                    key = (series, selection.get("selector", ""),
                           value, fn.get("signal", ""), pad)
                    said = selection.get("sources") or (
                        LEGACY_DEFAULT_BASIS if value == 0 else LEGACY_ROUTE_BASIS)
                    routes.setdefault(key, set()).update(said)
                    if isinstance(said, dict):
                        for who in said.values():
                            editions.setdefault(key, set()).update(who)
                    # 格子が別の値だと言っている経路（F-73）。**SKU ごとに集まる**ので
                    # 1つでも異論があれば残す（同じ series の別 package で pad が
                    # 出ていないだけのことがある、という `said` と同じ理由）。
                    if selection.get("disputed_by_grid") is not None:
                        disputed[key] = selection["disputed_by_grid"]
                    if selection.get("value_from_grid"):
                        from_grid.add(key)

    field_rows = sorted(fields.values(),
                        key=lambda r: (r["series"], r["selector"]))
    manual_only = [r for r in field_rows if r["_from_manual"]]
    # `basis` に出す順は経路と同じ並びにする。
    ORDER = ["evt-header", "rm-register-table", "rm-remap-grid",
             "rm-field-description", "datasheet-pin-table"]
    for row in field_rows:
        row["confidence"] = "reference"
        said = row.pop("_sources", None)
        row.pop("_from_manual", None)
        # 出所は候補が記録したものから組む。記録の無い古い候補だけ従来の決め打ちに落とす。
        row["basis"] = (route_basis([n for n in ORDER if n in said])
                        if said else MANUAL_BASIS)
    route_rows = []
    for key in sorted(routes):
        (s, sel, value, signal, pad) = key
        # 出所は SKU ごとに集まる。**1つの SKU でも格子が言っていれば言っている**
        # ——同じ series の別 package で pad が出ていないだけのことがある。
        order = ["datasheet-pin-table-default", "datasheet-pin-table",
                 "rm-remap-grid", "rm-field-description"]
        said = [name for name in order if name in routes[key]]
        # **格子が異を唱えた経路は `conflict`。** 他の証拠表と同じ作法で、片方に寄せず
        # 両論を残す（値は pin 表を保ち、格子の言い分を `basis` に書く。F-73）。
        against = disputed.get(key)
        route_rows.append(
            {"series": s, "selector": sel, "value": value, "signal": signal,
             "pad": pad,
             "confidence": ("conflict" if against is not None
                            else "reference" if key in from_grid
                            else route_confidence(said)),
             "basis": route_basis(said, against, editions.get(key, ()))}
        )

    if manual_only:
        print(f"  headerに定義が無くRMだけから作った selector: {len(manual_only)}",
              file=sys.stderr)
        for r in manual_only:
            print(f"    {r['series']} {r['selector']:24} {r['bits']}", file=sys.stderr)

    if args.out:

        args.out.mkdir(parents=True, exist_ok=True)
    for name, rows, columns in (("remap_fields.csv", field_rows, FIELD_COLUMNS),
                                ("remap_routes.csv", route_rows, ROUTE_COLUMNS)):
        dest = paths.table(name.removesuffix(".csv"), args.out)
        with dest.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            writer.writerows({**row, "#": "#"} for row in rows)
        print(f"{dest}: {len(rows)} 行", file=sys.stderr)
    defaults = sum(1 for r in route_rows if r["value"] == 0)
    print(f"  うち既定経路(value=0): {defaults} 行", file=sys.stderr)
    split = [r for r in field_rows if "|" in r["register"]]
    print(f"  registerをまたぐ分割field: {len(split)} selector", file=sys.stderr)
    for r in split:
        print(f"    - {r['series']} {r['selector']} {r['bits']}", file=sys.stderr)
    orphans = {(r["series"], r["selector"]) for r in route_rows} \
        - {(r["series"], r["selector"]) for r in field_rows}
    for series, sel in sorted(orphans):
        print(f"  - routeのみでfield定義がない: {series} {sel}", file=sys.stderr)
    for d in dict.fromkeys(disagreements):
        print(f"  - {d}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
