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

# The pin table leads with one pin-number column per orderable variant, then pad,
# type, reset function, default alternate and remapping. Neither the number of
# variant columns nor the position of the rest is stable across families: CH32V003
# heads four columns with package names, CH32X035 seven, while CH32V006 and
# CH32V407 head theirs with part numbers and CH32V407 inserts an extra "I/O
# structure" column. Both are therefore read from the header labels.
PACKAGE_PREFIXES = ("SOP", "QFN", "LQFP", "TSSOP", "QSOP", "TQFP")
PART_NUMBER = re.compile(r"^(CH32)?[A-Z]{0,2}\d{3}[A-Z0-9]{2,}$")

# Header label -> the column it marks, matched against the merged header text with
# punctuation and case removed.
COLUMN_LABELS = {
    "pad": ("pinname",),
    "type": ("pintype",),
    # CH32H417 heads the default-route column "Pin function(2)" instead, and the
    # CH32H415 table omits it entirely, so this one column is optional.
    "default": ("defaultalternate", "defaultalter", "pinfunction"),
    "remap": ("remapping",),
}
REQUIRED_COLUMNS = ("pad", "type", "remap")

PAD = re.compile(r"^P[A-H]\d{1,2}$")
POWER_PADS = {"VSS", "VDD", "VDDA", "VSSA", "VBAT", "VREF+", "VREF-"}

# Supply and special pads are named per family (CH32M030 alone adds VS0-3, VB0-3,
# VHV, VDD8, VDD33, ISP1), so rows are recognised by their pin-type cell instead of
# by a list of pad names. Types read like P, A, O, I/O, I/O/A, I/O/FT.
PIN_TYPE = re.compile(r"^[A-Z]{1,3}(?:/[A-Z]{1,3}){0,3}$")
PAD_TOKEN = re.compile(r"^[A-Z][A-Z0-9_+-]{0,7}$")
FOOTNOTE = re.compile(r"\(\d+\)")

# Two unrelated ways of naming the route the signal arrives on. Families with an
# AFIO remap register suffix the selector value (TIM1_CH1_2); CH32H41x instead
# multiplexes per pin and names the alternate-function number (TIM8_CH1(AF0)).
ROUTED = re.compile(r"^(?P<signal>.+?)_(?P<value>\d+)$")
ALTERNATE = re.compile(r"^(?P<signal>.+?)\((?:AF|af)(?P<value>\d+)\)$")

def kind_for(pin_type: str) -> str | None:
    """Map the datasheet's pin-type letters onto the schema's pin kinds.

    The table types every supply pin as P, so ground is not distinguishable here
    and stays a human refinement.
    """
    if "I/O" in pin_type:
        return "gpio"
    # CH32M030 types its output-only medium-voltage pins "O"; they are still GPIO.
    return {"P": "power", "A": "analog", "O": "gpio"}.get(pin_type)


def normalise_pad(cell: str) -> str:
    """Strip the line wrap the pad column picks up, then its footnote markers.

    CH32X035 prints PA7(7), PC16(4)(9) and wraps VDD as "V\\nDD". The wrap can also
    fall inside the marker, as CH32M030 does with "PA13(7\\n)", so whitespace has to
    go first for the marker to be recognisable at all.
    """
    return FOOTNOTE.sub("", cell.replace("\n", "").replace(" ", ""))


def is_variant(name: str) -> bool:
    return name.startswith(PACKAGE_PREFIXES) or bool(PART_NUMBER.match(name))


def read_variant(cell: str) -> str | None:
    """Read one variant heading.

    Multi-column headings are printed rotated, so the text layer holds them
    reversed; a table with a single variant column has room to print it upright
    (CH32V203 Table 3-1-4). Both readings are therefore tried.
    """
    text = FOOTNOTE.sub("", cell.replace("\n", "")).strip()
    for candidate in (text[::-1].strip(), text):
        if candidate and is_variant(candidate):
            return candidate
    return None


def read_package_header(cells: list[str], count: int) -> list[str] | None:
    """Name the first `count` columns, leaving a placeholder where the text is lost.

    CH32V208 leaves one heading blank in the text layer and CH32V317 splits
    LQFP100 across two cells, so a heading row is accepted when some -- not
    necessarily all -- of its cells resolve.
    """
    names, resolved = [], 0
    for col in range(count):
        found = read_variant(cells[col]) if col < len(cells) else None
        names.append(found or f"col{col}")
        resolved += found is not None
    return names if resolved else None


def normalise_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def read_layout(rows: list[list[str]]) -> tuple[dict[str, int], list[str]] | None:
    """Locate the pad/type/default/remap columns and the variant headings.

    Header labels wrap over several rows, so the rows above the first pad row are
    merged per column before matching. The variant row is the header row whose
    filled cells all sit left of the pad column.
    """
    first_data = next(
        (
            i
            for i, row in enumerate(rows)
            if any(PAD.match(normalise_pad(c)) or normalise_pad(c) in POWER_PADS for c in row)
        ),
        None,
    )
    if not first_data:
        return None
    width = max(len(r) for r in rows[:first_data])
    merged = [
        normalise_label("".join(row[col] for row in rows[:first_data] if col < len(row)))
        for col in range(width)
    ]
    layout: dict[str, int] = {}
    for key, keywords in COLUMN_LABELS.items():
        for col, text in enumerate(merged):
            if any(k in text for k in keywords):
                layout[key] = col
                break
    if any(key not in layout for key in REQUIRED_COLUMNS):
        return None
    best: tuple[int, list[str]] | None = None
    for row in rows[:first_data]:
        found = read_package_header(row, layout["pad"])
        if not found:
            continue
        resolved = sum(1 for n in found if not n.startswith("col"))
        if best is None or resolved > best[0]:
            best = (resolved, found)
    return (layout, best[1]) if best else None


CAPTION = re.compile(r"^(Table\s+[\d]+(?:-[\d]+)*)\s+(\S.*)$")


def captions(pdf) -> list[tuple[str, str, int]]:
    """Every table caption, as (label, title, page index)."""
    out = []
    for pno, page in enumerate(pdf.pages):
        for line in page.extract_text_lines() or []:
            m = CAPTION.match(line["text"].strip())
            if m:
                out.append((m.group(1), m.group(2), pno))
    return out


def choose_table(pdf) -> tuple[str, str]:
    """Pick the first pin-definition table and the caption that ends it.

    Families number these differently -- Table 2-1, Table 2-1-1, Table 3-1-1 -- so
    the caption is found by its wording rather than by a fixed label.
    """
    found = captions(pdf)
    for i, (label, title, _) in enumerate(found):
        if "pin definition" in title.lower():
            return label, next_caption(found, i)
    raise SystemExit("pin definition の表見出しが見つかりませんでした")


def next_caption(found: list[tuple[str, str, int]], index: int) -> str:
    """The label that ends the table at `index`.

    A caption repeated on continuation pages is the same table, not the next one
    (CH32V103 Table 2-2), so identical labels are skipped.
    """
    label = found[index][0]
    for following, _, _ in found[index + 1:]:
        if following != label:
            return following
    return "\x00"


def caption_position(page, label: str) -> float | None:
    """Y coordinate of a table caption, if it is on this page.

    The label must end where it ends: "Table 3-1" is not an occurrence of
    "Table 3-1-1", which numbers a different table.
    """
    for line in page.extract_text_lines() or []:
        if re.match(re.escape(label) + r"(?![-\d])", line["text"].strip()):
            return line["top"]
    return None


def find_pin_tables(
    pdf, table_label: str, stop_label: str
) -> tuple[list[list], list[str], dict[str, int]]:
    """Collect data rows of the pin-definition table across the pages it spans.

    Consecutive pin tables share pages: a page can carry the tail of the previous
    table, this table's caption and the next table's caption. Both ends are therefore
    cut at caption y positions rather than at page boundaries. Continuation tables may
    drop the header entirely (CH32V003) or repeat it (CH32V006), so the layout found
    first is carried forward and a table whose column count differs is treated as
    belonging to another product.
    """
    rows: list[list] = []
    variants: list[str] = []
    layout: dict[str, int] = {}
    width = 0
    started = False
    for page in pdf.pages:
        begin = caption_position(page, table_label)
        if begin is not None:
            started = True
        elif not started:
            continue
        cut = caption_position(page, stop_label)
        for table in page.find_tables():
            if begin is not None and table.bbox[3] <= begin:
                continue
            if cut is not None and table.bbox[1] >= cut:
                continue
            extracted = [[(c or "").strip() for c in row] for row in table.extract()]
            if not extracted:
                continue
            if width and len(extracted[0]) != width:
                continue
            if not layout:
                found = read_layout(extracted)
                if not found:
                    continue
                layout, variants = found
                width = len(extracted[0])
            pad_col, type_col = layout["pad"], layout["type"]
            for cells in extracted:
                if max(pad_col, type_col) >= len(cells):
                    continue
                pad = normalise_pad(cells[pad_col])
                pin_type = normalise_pad(cells[type_col])
                if PAD.match(pad) or (PAD_TOKEN.match(pad) and PIN_TYPE.match(pin_type)):
                    cells[pad_col] = pad
                    rows.append(cells)
        if cut is not None:
            break
    return rows, variants, layout


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
            or part.startswith(("/", ")", "_"))
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
        if not table_label:
            table_label, stop_label = choose_table(pdf)
            notes.append(f"表を自動選択: {table_label}（{stop_label} まで）")
        rows, packages, layout = find_pin_tables(pdf, table_label, stop_label)
    if not packages:
        raise SystemExit(f"{table_label} の列見出しを認識できませんでした")
    if package not in packages:
        raise SystemExit(f"{package} は表にありません。候補: {', '.join(packages)}")
    pins, more = pins_for(rows, packages, layout, package)
    return pins, notes + more, packages


def pins_for(
    rows: list[list[str]], packages: list[str], layout: dict[str, int], package: str
) -> tuple[list[dict], list[str]]:
    """Slice the shared table rows down to one variant's pins."""
    notes: list[str] = []
    index = packages.index(package)
    pad_col, type_col = layout["pad"], layout["type"]
    default_col, remap_col = layout.get("default"), layout["remap"]
    if default_col is None:
        notes.append("この表には default alternate function 列がなく、remap列のみ採取した")

    pins: list[dict] = []
    for cells in rows:
        if remap_col >= len(cells):
            notes.append(f"列数不足の行を無視: {cells[:pad_col + 2]}")
            continue
        number = cells[index]
        if number in {"-", ""}:
            continue
        pad = cells[pad_col]
        pin_type = normalise_pad(cells[type_col])
        kind = kind_for(pin_type)
        if kind is None:
            kind = "other"
            notes.append(f"{pad}: pin type {pin_type!r} を分類できず other とした")
        functions = []
        if default_col is not None:
            for token in signals(cells[default_col]):
                # CH32H41x puts its alternate-function numbers in this column too.
                af = ALTERNATE.match(token)
                functions.append(
                    {
                        "signal": af.group("signal"),
                        "route": f"af-{af.group('value')}",
                        "_alternate_function": int(af.group("value")),
                    }
                    if af
                    else {"signal": token, "route": "default"}
                )
        for token in signals(cells[remap_col]):
            af = ALTERNATE.match(token)
            if af:
                functions.append(
                    {
                        "signal": af.group("signal"),
                        "route": f"af-{af.group('value')}",
                        "_alternate_function": int(af.group("value")),
                    }
                )
                continue
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
        if number_value == 0:
            # WCH numbers the exposed thermal pad 0; the schema spells it EP.
            number_value = "EP"
            notes.append(f"{pad}: pin番号0をexposed pad (EP) として扱った")
        pins.append(
            {
                "number": number_value,
                "pad": pad,
                "kind": kind,
                "_pin_type": pin_type,
                "functions": functions,
            }
        )

    pins.sort(key=lambda p: (isinstance(p["number"], str), p["number"]))
    return pins, notes


def print_err(*args):
    print(*args, file=sys.stderr)


def score(pins: list[dict], record: Path) -> None:
    rec = json.loads(record.read_text(encoding="utf-8"))
    truth = rec.get("pins", [])
    print_err(f"\n照合: {record.name}  record {len(truth)} pin / 抽出 {len(pins)} pin")
    print_err("-" * 74)

    got_pads = {(p["number"], p["pad"]) for p in pins}
    want_pads = {(p["number"], p["pad"]) for p in truth}
    print_err(f"  pin番号とpadの対応:  一致 {len(got_pads & want_pads)}/{len(want_pads)}")
    for miss in sorted(want_pads - got_pads, key=lambda x: str(x[0])):
        print_err(f"    record にあり抽出になし: {miss}")
    for extra in sorted(got_pads - want_pads, key=lambda x: str(x[0])):
        print_err(f"    抽出にあり record になし: {extra}")

    def pairs(source):
        return {(p["pad"], f["signal"]) for p in source for f in p["functions"]}

    got, want = pairs(pins), pairs(truth)
    n_got = sum(len(p["functions"]) for p in pins)
    n_want = sum(len(p["functions"]) for p in truth)
    print_err(f"\n  pin function 数: record {n_want} / 抽出 {n_got}")
    print_err(f"  (pad, signal) 一致: {len(got & want)}/{len(want)}")
    only_record = sorted(want - got)
    only_extract = sorted(got - want)
    if only_record:
        print_err(f"\n  record のみ ({len(only_record)}件):")
        for pad, sig in only_record:
            print_err(f"    {pad:5} {sig}")
    if only_extract:
        print_err(f"\n  抽出のみ ({len(only_extract)}件):")
        for pad, sig in only_extract:
            print_err(f"    {pad:5} {sig}")

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
    print_err(f"\n  (pad, signal) ごとの selector 値集合 一致: {len(same)}/{len(want_r)}")
    differing = sorted(shared - same)
    if differing:
        print_err(f"\n  signalは一致するが selector 値が異なる ({len(differing)}件):")
        for key in differing:
            print_err(f"    {key[0]:6} {key[1]:10} 抽出={sorted(got_r[key], key=str)} record={sorted(want_r[key], key=str)}")

    review = sum(1 for p in pins for f in p["functions"] if f.get("_needs_review"))
    print_err(f"\n  経路番号がなく人手確認が要る function: {review}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--package", help="列見出し。パッケージ名か型番（例: TSSOP20, V006K8U7）")
    ap.add_argument("--table", default="", help="pin定義表の見出し。既定は自動選択")
    ap.add_argument("--stop", default="", help="読み取りを止める次表の見出し")
    ap.add_argument("--list", action="store_true", help="表見出しと列の一覧だけ表示する")
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    if args.list:
        with pdfplumber.open(args.pdf) as pdf:
            for label, title, pno in captions(pdf):
                if "pin definition" in title.lower():
                    print_err(f"  {label:<14} p{pno + 1:<4} {title}")
        return 0
    if not args.package:
        ap.error("--package か --list が要ります")

    pins, notes, packages = build(args.pdf, args.package, args.table, args.stop)
    print_err(f"入力: {args.pdf}")
    print_err(f"表にある列: {', '.join(packages)}")
    print_err(f"{args.package} の抽出 pin: {len(pins)} / function: {sum(len(p['functions']) for p in pins)}")
    if notes:
        print_err(f"\n要確認 {len(notes)} 件:")
        for n in notes:
            print_err(f"  - {n}")
    if args.compare:
        score(pins, args.compare)
    if args.emit:
        json.dump(pins, sys.stdout, indent=2, ensure_ascii=False)
        print_err()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
