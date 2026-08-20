#!/usr/bin/env python3
"""Extract alternate-function remapping routes from a reference manual.

A datasheet pin table only lists the routes bonded out on that package, and never
the default (value 0) route or the values a selector rejects. The reference manual
states the whole silicon as a grid -- one row per signal, one column per selector
value -- which makes it both a completion source and a cross-check for the
datasheet:

    Alternate function | TIM1_RM=000 Default | TIM1_RM=001 Partial | ...
    TIM1_ETR           | PC1                 | PC1                 | ...

This reads that grid into (field, value, signal, pad) routes for review, and when
given a record reports where the two disagree. It emits candidates only and never
writes device records.

Usage:
    uv run tools/extract_remap.py <manual.pdf> [--compare devices/<id>.json] [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))

import signal_vocabulary  # noqa: E402

# A remap column is headed by the selector field and the value it takes, wrapped
# over several lines: "TIM1_R\nM=000\nDefault\nmapping". A digit may be "x" where
# the manual does not care about that bit (CH32H417 writes SDMMC_RM=1x).
COLUMN_HEADER = re.compile(r"(?P<field>[A-Z0-9]+(?:_[A-Z0-9]+)*_RM)=(?P<value>[01xX]+)")
PAD = re.compile(r"^P[A-H]\d{1,2}$")
PAD_IN_PROSE = re.compile(r"\bP[A-H]\d{1,2}\b")
SIGNAL = re.compile(r"^[A-Z][A-Z0-9_]*$")
MIN_COLUMNS = 3


def flatten(cell: str | None) -> str:
    return (cell or "").replace("\n", "").strip()


def expand(pattern: str) -> list[int]:
    """Every value a bit pattern selects, expanding each "x" to 0 and 1."""
    values = [0]
    for bit in pattern:
        if bit in "xX":
            values = [v << 1 | b for v in values for b in (0, 1)]
        else:
            values = [v << 1 | int(bit) for v in values]
    return sorted(values)


def read_header(row: list[str]) -> list[tuple[str, list[int]]] | None:
    """Parse a header row into (field, values) per column, or None if it is not one."""
    columns: list[tuple[str, list[int]]] = []
    for cell in row[1:]:
        m = COLUMN_HEADER.search(flatten(cell))
        if not m:
            return None
        columns.append((m.group("field"), expand(m.group("value"))))
    return columns if len(columns) >= 2 else None


def pads_in(cell: str) -> tuple[list[str], bool]:
    """Pads a cell names, and whether they had to be dug out of prose.

    A cell may hold two pads for one value (CH32M030 writes "PC3/PB9"), or a
    sentence instead of a pad, as CH32M030 Table 6-15 does for the ADC trigger.
    """
    text = flatten(cell)
    if not text or text == "-":
        return [], False
    parts = [p.strip() for p in text.split("/")]
    if all(PAD.match(p) for p in parts):
        return parts, False
    return PAD_IN_PROSE.findall(text), True


def extract(pdf_path: Path) -> tuple[list[dict], list[str]]:
    routes: list[dict] = []
    notes: list[str] = []
    pending: list[tuple[str, list[int]]] | None = None
    pending_page = -2

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.find_tables():
                rows = [[flatten(c) for c in row] for row in table.extract()]
                if not rows or len(rows[0]) < MIN_COLUMNS:
                    continue
                header = read_header(rows[0])
                if header:
                    pending, pending_page = header, page.page_number
                    body = rows[1:]
                elif pending and len(rows[0]) == len(pending) + 1 and page.page_number - pending_page <= 1:
                    # A grid split across pages repeats no header on the later part.
                    body = rows
                else:
                    continue
                pending_page = page.page_number
                for row in body:
                    signal_cell = row[0]
                    if not signal_cell:
                        continue  # stray header fragment inside the grid
                    names = [s.strip() for s in signal_cell.split("/")]
                    prose_signal = not all(SIGNAL.match(s) for s in names)
                    if prose_signal:
                        # CH32M030 Table 6-15 writes the ADC trigger row as a sentence
                        # rather than a signal name. Keep it, flagged, so the reviewer
                        # sees what the manual claims.
                        names = [signal_cell]
                        notes.append(f"signal名が文章の行: {signal_cell!r}")
                    for col, (field, values) in enumerate(pending, start=1):
                        if col >= len(row):
                            continue
                        pads, from_prose = pads_in(row[col])
                        if from_prose and pads:
                            notes.append(
                                f"{field}={values} {signal_cell}: 文章から pad を推定 ({row[col]!r})"
                            )
                        for signal in names:
                            for pad in pads:
                                for value in values:
                                    routes.append(
                                        {
                                            "field": field,
                                            "value": value,
                                            "signal": signal,
                                            "pad": pad,
                                            "page": page.page_number,
                                            **({"_pad_from_prose": True} if from_prose else {}),
                                            **(
                                                {"_signal_from_prose": True}
                                                if prose_signal
                                                else {}
                                            ),
                                        }
                                    )
    return routes, notes


# Naming lives in one module, because the manual, the datasheet and the EVT header
# each spell the same route differently and a second copy of the rules would drift.
canonical_field = signal_vocabulary.canonical_field
canonical_signal = signal_vocabulary.comparable


def score(routes: list[dict], record: Path) -> None:
    rec = json.loads(record.read_text(encoding="utf-8"))
    field_of = {s["id"]: s["field"] for s in rec.get("route_selectors", [])}

    want: set[tuple[str, int, str, str]] = set()
    for pin in rec.get("pins", []):
        for fn in pin.get("functions", []):
            selection = fn.get("selection")
            if not selection:
                continue
            field = field_of.get(selection["selector"])
            if field is None:
                continue
            for value in selection["values"]:
                want.add(
                    (canonical_field(field), value, canonical_signal(fn["signal"]), pin["pad"])
                )

    def key(r):
        return (canonical_field(r["field"]), r["value"], canonical_signal(r["signal"]), r["pad"])

    prose = {key(r) for r in routes if r.get("_signal_from_prose")}
    got = {key(r) for r in routes if not r.get("_signal_from_prose")}
    on_package = {pin["pad"] for pin in rec.get("pins", [])}
    fields = {f for f, _, _, _ in want}
    got_in_scope = {r for r in got if r[0] in fields}

    print(f"\n照合: {record.name}", file=sys.stderr)
    print("-" * 74, file=sys.stderr)
    print(f"  record の selector 経路: {len(want)}", file=sys.stderr)
    print(f"  RM から抽出（同じfieldのみ）: {len(got_in_scope)}", file=sys.stderr)
    print(f"  一致: {len(want & got_in_scope)}/{len(want)}", file=sys.stderr)

    rm_only = sorted(got_in_scope - want)
    defaults = [r for r in rm_only if r[1] == 0]
    if defaults:
        print(
            f"  うち value=0 の default 経路: {len(defaults)}"
            "（recordは default に selector 値を持たない）",
            file=sys.stderr,
        )
    if prose:
        print(f"\n  RMが文章で書いている経路 ({len(prose)}件):", file=sys.stderr)
        for field, value, signal, pad in sorted(prose):
            print(f"    {canonical_field(field)}={value} -> {pad}   ({signal[:44]})", file=sys.stderr)

    for label, rows in (
        ("record のみ", sorted(want - got_in_scope)),
        ("RM のみ（default を除く）", [r for r in rm_only if r[1] != 0]),
    ):
        if not rows:
            continue
        print(f"\n  {label} ({len(rows)}件):", file=sys.stderr)
        for field, value, signal, pad in rows[:25]:
            # The manual describes the silicon; a record describes one package.
            off = "" if not on_package or pad in on_package else "  <- このpackageにない"
            print(f"    {field}={value:<3} {signal:<16} {pad}{off}", file=sys.stderr)
        if len(rows) > 25:
            print(f"    ... 他 {len(rows) - 25} 件", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--compare", type=Path, help="既存 device record と照合する")
    ap.add_argument("--emit", action="store_true", help="候補JSONを標準出力へ")
    args = ap.parse_args()

    routes, notes = extract(args.pdf)
    fields = sorted({r["field"] for r in routes})
    print(f"入力: {args.pdf}", file=sys.stderr)
    print(f"remap経路: {len(routes)} 件 / selector field {len(fields)} 種", file=sys.stderr)
    for field in fields:
        values = sorted({r["value"] for r in routes if r["field"] == field})
        signals = len({r["signal"] for r in routes if r["field"] == field})
        print(f"    {field:<18} 値{values} signal{signals}種", file=sys.stderr)
    if notes:
        print(f"\n要確認 {len(notes)} 件:", file=sys.stderr)
        for note in dict.fromkeys(notes):
            print(f"  - {note}", file=sys.stderr)

    if args.compare:
        score(routes, args.compare)
    if args.emit:
        json.dump(routes, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
