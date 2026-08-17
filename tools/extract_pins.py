#!/usr/bin/env python3
"""Extract package pin / alternate-function candidates from a datasheet pin table.

The vendor pin table is the only source for package bond-out and pad routing; the
EVT tree does not carry it. PDF table recovery is layout-dependent, so this tool
emits *candidates* for human review and, when given a record, reports how far the
candidates agree with it. It never writes device records.

Usage:
    uv run tools/extract_pins.py <datasheet.pdf> --package TSSOP20 \
        [--compare devices/<id>.json] [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

# "Table 2-1 Pin definitions" leads with one pin-number column per package, then
# pad, type, reset function, default alternate and remapping. The number of package
# columns is family-specific (CH32V003 has 4, CH32X035 has 7), so it is detected
# from the header rather than assumed.
PACKAGE_PREFIXES = ("SOP", "QFN", "LQFP", "TSSOP", "QSOP", "TQFP")

PAD = re.compile(r"^P[A-H]\d{1,2}$")
POWER_PADS = {"VSS", "VDD", "VDDA", "VSSA", "VBAT", "VREF+", "VREF-"}
FOOTNOTE = re.compile(r"\(\d+\)")
ROUTED = re.compile(r"^(?P<signal>.+?)_(?P<value>\d+)$")

# Pin type letters in the datasheet's "Pin type" column.
KIND_BY_TYPE = {"P": "power", "I/O": "gpio", "I/O/A": "gpio", "I/O/FT": "gpio"}


def normalise_pad(cell: str) -> str:
    """Strip footnote markers and the line wrap the pad column picks up.

    CH32X035 prints PA7(7), PC16(4)(9) and wraps VDD as "V\\nDD".
    """
    return FOOTNOTE.sub("", cell).replace("\n", "").replace(" ", "")


def read_package_header(cells: list[str]) -> list[str] | None:
    """Package names are printed rotated, so the text layer holds them reversed."""
    names = []
    for cell in cells:
        name = cell[::-1]
        if not cell or not name.startswith(PACKAGE_PREFIXES):
            break
        names.append(name)
    return names if len(names) >= 2 else None


def stop_position(page, stop_label: str) -> float | None:
    """Y coordinate where the next table's caption starts, if it is on this page."""
    try:
        hits = page.search(re.escape(stop_label))
    except Exception:  # pragma: no cover - older pdfplumber without search()
        return 0.0 if stop_label in (page.extract_text() or "") else None
    return min((h["top"] for h in hits), default=None)


def find_pin_tables(pdf, table_label: str, stop_label: str) -> tuple[list[list], list[str], int]:
    """Collect data rows of the pin-definition table across the pages it spans.

    The table routinely continues onto the page that also carries the next table's
    caption, so the cut is made at the caption's y position rather than at the page
    boundary. Continuation pages repeat the header but are otherwise identical, and
    a table whose column count differs belongs to a different product.
    """
    rows: list[list] = []
    packages: list[str] = []
    width = 0
    started = False
    for page in pdf.pages:
        text = page.extract_text() or ""
        if table_label in text:
            started = True
        elif not started:
            continue
        cut = stop_position(page, stop_label) if started else None
        for table in page.find_tables():
            if cut is not None and table.bbox[1] >= cut:
                continue
            extracted = table.extract()
            if width and extracted and len(extracted[0]) != width:
                continue
            for row in extracted:
                cells = [(c or "").strip() for c in row]
                if not packages:
                    found = read_package_header(cells)
                    if found:
                        packages, width = found, len(cells)
                        continue
                if packages:
                    pad_col = len(packages)
                    if pad_col >= len(cells):
                        continue
                    pad = normalise_pad(cells[pad_col])
                    if PAD.match(pad) or pad in POWER_PADS:
                        cells[pad_col] = pad
                        rows.append(cells)
        if cut is not None:
            break
    return rows, packages, len(packages)


def unwrap(cell: str) -> str:
    """Join a wrapped table cell, restoring the separator the line break swallowed.

    A wrap can fall between two signals, where the "/" is implied, or inside one
    signal, where it is not. CH32X035 splits T2C1N_6 as "T2C1N_" / "6", C1P0 as
    "C1P" / "0" and the footnote of A3(3) as "A3(" / "3)". No signal name begins
    with a digit, so a continuation is recognisable: a trailing "_" or "(" on the
    previous line, or a leading digit or ")" on the next one.
    """
    parts = [p.strip() for p in cell.split("\n") if p.strip()]
    out = ""
    for part in parts:
        joined = (
            out.endswith(("/", "_", "("))
            or part.startswith(("/", ")"))
            or part[0].isdigit()
        )
        if out and not joined:
            out += "/"
        out += part
    return out


def signals(cell: str) -> list[str]:
    """Split a cell into signal tokens. '-' is the table's empty marker, not a signal."""
    return [s for s in unwrap(FOOTNOTE.sub("", cell)).split("/") if s and s != "-"]


def build(
    pdf_path: Path, package: str, table_label: str, stop_label: str
) -> tuple[list[dict], list[str], list[str]]:
    notes: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        rows, packages, pad_col = find_pin_tables(pdf, table_label, stop_label)
    if not packages:
        raise SystemExit(f"{table_label} のパッケージ列見出しを認識できませんでした")
    if package not in packages:
        raise SystemExit(f"{package} は表にありません。候補: {', '.join(packages)}")
    index = packages.index(package)
    type_col, default_col, remap_col = pad_col + 1, pad_col + 3, pad_col + 4

    pins: list[dict] = []
    for cells in rows:
        if remap_col >= len(cells):
            notes.append(f"列数不足の行を無視: {cells[:pad_col + 2]}")
            continue
        number = cells[index]
        if number in {"-", ""}:
            continue
        pad = cells[pad_col]
        kind = KIND_BY_TYPE.get(cells[type_col], "other")
        if kind == "other" and cells[type_col]:
            notes.append(f"{pad}: pin type {cells[type_col]!r} を分類できず other とした")
        functions = []
        for signal in signals(cells[default_col]):
            functions.append({"signal": signal, "route": "default"})
        for token in signals(cells[remap_col]):
            m = ROUTED.match(token)
            if m:
                functions.append(
                    {
                        "signal": m.group("signal"),
                        "route": f"remap-{m.group('value')}",
                        "_selector_value": int(m.group("value")),
                    }
                )
            else:
                functions.append({"signal": token, "route": None, "_needs_review": True})
                notes.append(
                    f"{pad}: remap列の {token!r} に経路番号がない。"
                    "どのselectorが選ぶかRMで要確認"
                )
        try:
            number_value: int | str = int(number)
        except ValueError:
            number_value = number
        pins.append({"number": number_value, "pad": pad, "kind": kind, "functions": functions})

    pins.sort(key=lambda p: (isinstance(p["number"], str), p["number"]))
    return pins, notes, packages


def score(pins: list[dict], record: Path) -> None:
    rec = json.loads(record.read_text(encoding="utf-8"))
    truth = rec.get("pins", [])
    print(f"\n照合: {record.name}  record {len(truth)} pin / 抽出 {len(pins)} pin")
    print("-" * 74)

    got_pads = {(p["number"], p["pad"]) for p in pins}
    want_pads = {(p["number"], p["pad"]) for p in truth}
    print(f"  pin番号とpadの対応:  一致 {len(got_pads & want_pads)}/{len(want_pads)}")
    for miss in sorted(want_pads - got_pads, key=lambda x: str(x[0])):
        print(f"    record にあり抽出になし: {miss}")
    for extra in sorted(got_pads - want_pads, key=lambda x: str(x[0])):
        print(f"    抽出にあり record になし: {extra}")

    def pairs(source):
        return {(p["pad"], f["signal"]) for p in source for f in p["functions"]}

    got, want = pairs(pins), pairs(truth)
    n_got = sum(len(p["functions"]) for p in pins)
    n_want = sum(len(p["functions"]) for p in truth)
    print(f"\n  pin function 数: record {n_want} / 抽出 {n_got}")
    print(f"  (pad, signal) 一致: {len(got & want)}/{len(want)}")
    only_record = sorted(want - got)
    only_extract = sorted(got - want)
    if only_record:
        print(f"\n  record のみ ({len(only_record)}件):")
        for pad, sig in only_record:
            print(f"    {pad:5} {sig}")
    if only_extract:
        print(f"\n  抽出のみ ({len(only_extract)}件):")
        for pad, sig in only_extract:
            print(f"    {pad:5} {sig}")

    def routes(source):
        """(pad, signal) -> the selector values that reach it, 'default' included.

        A record collapses several selector values that pick the same route into one
        function (CH32X035 remap-5-to-7); the extractor emits one per value. Compare
        the value sets so the two representations are judged equivalent.
        """
        out: dict[tuple[str, str], set] = {}
        for pin in source:
            for f in pin["functions"]:
                key = (pin["pad"], f["signal"])
                if "_selector_value" in f:
                    out.setdefault(key, set()).add(f["_selector_value"])
                elif f.get("selection"):
                    out.setdefault(key, set()).update(f["selection"]["values"])
                else:
                    out.setdefault(key, set()).add("default")
        return out

    got_r, want_r = routes(pins), routes(truth)
    shared = got_r.keys() & want_r.keys()
    same = {k for k in shared if got_r[k] == want_r[k]}
    print(f"\n  (pad, signal) ごとの selector 値集合 一致: {len(same)}/{len(want_r)}")
    differing = sorted(shared - same)
    if differing:
        print(f"\n  signalは一致するが selector 値が異なる ({len(differing)}件):")
        for key in differing:
            print(f"    {key[0]:6} {key[1]:10} 抽出={sorted(got_r[key], key=str)} record={sorted(want_r[key], key=str)}")

    review = sum(1 for p in pins for f in p["functions"] if f.get("_needs_review"))
    print(f"\n  経路番号がなく人手確認が要る function: {review}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--package", required=True, help="例: TSSOP20")
    ap.add_argument("--table", default="Table 2-1", help="pin定義表の見出し")
    ap.add_argument("--stop", default="Table 2-2", help="読み取りを止める次表の見出し")
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    pins, notes, packages = build(args.pdf, args.package, args.table, args.stop)
    print(f"入力: {args.pdf}")
    print(f"表にあるパッケージ: {', '.join(packages)}")
    print(f"{args.package} の抽出 pin: {len(pins)} / function: {sum(len(p['functions']) for p in pins)}")
    if notes:
        print(f"\n要確認 {len(notes)} 件:")
        for n in notes:
            print(f"  - {n}")
    if args.compare:
        score(pins, args.compare)
    if args.emit:
        json.dump(pins, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
