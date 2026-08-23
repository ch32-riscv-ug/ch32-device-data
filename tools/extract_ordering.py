#!/usr/bin/env python3
"""Extract the package and ordering information table from a datasheet.

This table is the authoritative mapping from an order model to its package, and it
is the only place that states body size, pin pitch and packing type:

    Package Form | Body Size | Pin Pitch | Package Description | Order Model
    QFN48X7_A    | 7*7mm     | 0.5mm     | Quad Flat No-lead   | CH32M030C8U3
    QFN48        | 5*5mm     | 0.35mm    | Quad Flat No-lead   | CH32M030C8U7

Column order and spelling vary -- CH32V103 leads with the order model and adds a
packing type, CH32V208 prints "Bidy Size" -- so columns are found by their labels.

Usage:
    uv run tools/extract_ordering.py <datasheet.pdf> [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

MODEL = re.compile(r"CH32[A-Z0-9]{4,}")
MAX_PAGES_FROM_END = 60

# Label keyword -> field. Order matters: the more specific label is tried first so
# that CH32X035, which heads its description column "Package Form" as well, does
# not lose the real package column.
# The Chinese edition is the original; both spellings are matched so a document can
# be read in whichever language it is published in.
COLUMNS = (
    ("model", ("ordermodel", "订购型号", "订货型号")),
    ("packing", ("packingtype", "包装方式")),
    ("body_size", ("bodysize", "bidysize", "塑体尺寸", "封装尺寸", "本体尺寸")),
    ("pin_pitch", ("pinpitch", "引脚节距", "引脚间距")),
    ("description", ("packagedescription", "封装说明")),
    ("package", ("packageform", "封装形式", "封装")),
)


def flatten(cell: str | None) -> str:
    return (cell or "").replace("\n", " ").strip()


def squash(text: str) -> str:
    """Strip punctuation and case, keeping CJK so Chinese labels survive."""
    return re.sub(r"[^a-z\u4e00-\u9fff]", "", text.lower())


def read_layout(row: list[str]) -> dict[str, int] | None:
    labels = [squash(c) for c in row]
    taken: set[int] = set()
    layout: dict[str, int] = {}
    for field, keywords in COLUMNS:
        for col, text in enumerate(labels):
            if col in taken or not text:
                continue
            if any(k in text for k in keywords):
                layout[field] = col
                taken.add(col)
                break
    if "model" not in layout or "package" not in layout:
        return None
    return layout


def extract(pdf_path: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    entries: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        # The table sits near the back of the document.
        start = max(0, len(pdf.pages) - MAX_PAGES_FROM_END)
        layout: dict[str, int] | None = None
        for page in pdf.pages[start:]:
            for table in page.find_tables():
                rows = [[flatten(c) for c in r] for r in table.extract()]
                if not rows:
                    continue
                found = read_layout(rows[0])
                if found:
                    layout, body = found, rows[1:]
                elif layout and len(rows[0]) > max(layout.values()):
                    body = rows  # continuation without a repeated header
                else:
                    continue
                carried: dict[str, str] = {}
                for row in body:
                    if max(layout.values()) >= len(row):
                        continue
                    values = {f: row[c] for f, c in layout.items()}
                    # A package spanning several models leaves the shared cells blank.
                    for field, value in values.items():
                        if value:
                            carried[field] = value
                        else:
                            values[field] = carried.get(field, "")
                    for model in MODEL.findall(values["model"]):
                        entries.append(
                            {
                                "part_number": model,
                                **{k: v for k, v in values.items() if k != "model"},
                                "page": page.page_number,
                            }
                        )
            page.close()
    if not entries:
        notes.append("ordering情報の表を認識できませんでした")
    return entries, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    entries, notes = extract(args.pdf)
    print(f"入力: {args.pdf}", file=sys.stderr)
    print(f"order model: {len(entries)} 件", file=sys.stderr)
    for e in entries:
        print(
            f"    {e['part_number']:<16} {e.get('package', ''):<12}"
            f" {e.get('body_size', ''):<10} {e.get('pin_pitch', ''):<10}"
            f" {e.get('packing', '')}",
            file=sys.stderr,
        )
    for n in notes:
        print(f"  - {n}", file=sys.stderr)
    if args.emit:
        json.dump(entries, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
