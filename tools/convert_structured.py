#!/usr/bin/env python3
"""Convert a datasheet excerpt to a reviewable, extraction-neutral JSON form.

This is deliberately *not* an operating-conditions extractor.  It records the
PDF text lines, physical table cells, merged-cell spans and source coordinates
before any symbol or value interpretation.  A later extractor must consume an
approved file in this format instead of reading the PDF directly.

Examples:

    uv run tools/convert_structured.py \
        /home/mt/dev_wch/CH32V003/datasheet_en/CH32V003DS0.PDF --lang en \
        --pages 18-22

    uv run tools/convert_structured.py ... --lang zh --electrical-chapter
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

import jsonschema
import pdfplumber

import paths


SCHEMA_VERSION = "0.1"
SCHEMA = paths.REPO / "schemas" / "structured-document.schema.json"
DEFAULT_OUT = paths.CACHE / "structured"

CHAPTER_START = {
    "en": re.compile(r"Chapter\s+\d+\s+Electrical\s+Characteristics", re.I),
    "zh": re.compile(r"第\s*\d+\s*章\s*电\s*气\s*特\s*性"),
}
CHAPTER_END = {
    "en": re.compile(
        r"Chapter\s+\d+\s+Package(?:\s+and\s+Ordering)?\s+Information", re.I),
    "zh": re.compile(r"第\s*\d+\s*章\s*封\s*装(?:\s*及\s*订\s*货\s*信\s*息)?"),
}
TABLE_NUMBER = {
    "en": re.compile(r"Table\s+(\d+(?:-\d+)+)", re.I),
    "zh": re.compile(r"表\s*(\d+(?:-\d+)+)"),
}


def rounded_box(box) -> list[float]:
    return [round(float(value), 3) for value in box]


def parse_pages(text: str, page_count: int) -> list[int]:
    """Parse ``1,3-5`` using one-based PDF page numbers.

    >>> parse_pages("3,5-7", 10)
    [3, 5, 6, 7]
    >>> parse_pages("0", 10)
    Traceback (most recent call last):
    ...
    ValueError: page 0 is outside 1..10
    """
    selected: set[int] = set()
    for part in text.split(","):
        bounds = part.strip().split("-", 1)
        try:
            start = int(bounds[0])
            end = int(bounds[-1])
        except ValueError as exc:
            raise ValueError(f"invalid page range {part!r}") from exc
        if start > end:
            raise ValueError(f"page range starts after it ends: {part!r}")
        for page in range(start, end + 1):
            if not 1 <= page <= page_count:
                raise ValueError(f"page {page} is outside 1..{page_count}")
            selected.add(page)
    return sorted(selected)


def electrical_chapter_pages(pdf, lang: str) -> list[int]:
    selected = []
    in_chapter = False
    for page in pdf.pages:
        text = page.extract_text() or ""
        if not in_chapter:
            if not CHAPTER_START[lang].search(text):
                page.flush_cache()
                continue
            in_chapter = True
        elif CHAPTER_END[lang].search(text):
            page.flush_cache()
            break
        selected.append(page.page_number)
        page.flush_cache()
    if not selected:
        raise ValueError(f"electrical characteristics chapter not found ({lang})")
    return selected


def line_records(page) -> list[dict]:
    records = []
    for index, line in enumerate(page.extract_text_lines(return_chars=False), 1):
        records.append({
            "id": f"p{page.page_number}-line-{index:04d}",
            "text": line["text"],
            "bbox": rounded_box((line["x0"], line["top"], line["x1"], line["bottom"])),
        })
    return records


def cell_text(page, bbox) -> str:
    # `Table.extract()` flattens merged cells into a rectangular matrix.  Crop
    # each physical rectangle instead so the text remains attached to the cell
    # that owns its rowspan/colspan.
    return (page.crop(bbox).extract_text(x_tolerance=3, y_tolerance=3) or "").strip()


def physical_cells(page, table, table_id: str) -> tuple[list[dict], int, int]:
    # Every physical cell edge participates in the logical grid.  A large cell
    # crossing several adjacent intervals is therefore an explicit span.
    xs = sorted({round(value, 6) for cell in table.cells for value in (cell[0], cell[2])})
    ys = sorted({round(value, 6) for cell in table.cells for value in (cell[1], cell[3])})
    x_index = {value: index for index, value in enumerate(xs)}
    y_index = {value: index for index, value in enumerate(ys)}
    cells = []
    for index, bbox in enumerate(sorted(table.cells, key=lambda box: (box[1], box[0])), 1):
        x0, top, x1, bottom = (round(value, 6) for value in bbox)
        cells.append({
            "id": f"{table_id}-cell-{index:04d}",
            "row_start": y_index[top],
            "row_end": y_index[bottom],
            "column_start": x_index[x0],
            "column_end": x_index[x1],
            "bbox": rounded_box(bbox),
            "text": cell_text(page, bbox),
        })
    return cells, len(ys) - 1, len(xs) - 1


def captions(lines: list[dict], lang: str) -> list[dict]:
    found = []
    for line in lines:
        match = TABLE_NUMBER[lang].search(line["text"])
        if match:
            found.append({
                "line_id": line["id"],
                "source_number": match.group(1),
                "text": line["text"],
                "top": line["bbox"][1],
            })
    return found


def convert(pdf_path: Path, lang: str, requested_pages: str | None,
            whole_chapter: bool) -> dict:
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    with pdfplumber.open(pdf_path) as pdf:
        if whole_chapter:
            selected = electrical_chapter_pages(pdf, lang)
        else:
            selected = parse_pages(requested_pages or "1", len(pdf.pages))

        output_pages = []
        output_tables = []
        number_occurrences: dict[str, int] = {}
        previous_logical_id: str | None = None
        for page_number in selected:
            page = pdf.pages[page_number - 1]
            lines = line_records(page)
            page_captions = captions(lines, lang)
            tables = sorted(page.find_tables(), key=lambda item: (item.bbox[1], item.bbox[0]))
            previous_bottom = 0.0
            for table_index, table in enumerate(tables, 1):
                # A caption belongs to the first physical table below it.  A
                # table above the first new caption is a continuation from the
                # preceding page (or an intentionally partial excerpt).
                candidates = [item for item in page_captions
                              if previous_bottom <= item["top"] < table.bbox[1]]
                caption = candidates[-1] if candidates else None
                if caption:
                    number = caption["source_number"]
                    occurrence = number_occurrences.get(number, 0) + 1
                    number_occurrences[number] = occurrence
                    logical_id = f"table-{number}@{occurrence}"
                    previous_logical_id = logical_id
                    caption_record = {key: caption[key]
                                      for key in ("line_id", "source_number", "text")}
                    continues = False
                else:
                    logical_id = previous_logical_id or f"unlabelled-p{page_number}-{table_index}"
                    caption_record = None
                    continues = previous_logical_id is not None
                table_id = f"p{page_number}-table-{table_index:02d}"
                cells, row_count, column_count = physical_cells(page, table, table_id)
                output_tables.append({
                    "id": table_id,
                    "logical_id": logical_id,
                    "page": page_number,
                    "bbox": rounded_box(table.bbox),
                    "caption": caption_record,
                    "continues_from_previous": continues,
                    "row_count": row_count,
                    "column_count": column_count,
                    "cells": cells,
                    "review": {"status": "unreviewed"},
                })
                previous_bottom = table.bbox[3]
            output_pages.append({
                "number": page_number,
                "width": round(float(page.width), 3),
                "height": round(float(page.height), 3),
                "lines": lines,
            })
            page.flush_cache()

        document = {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "document": pdf_path.name,
                "language": lang,
                "sha256": digest,
                "page_count": len(pdf.pages),
                "selected_pages": selected,
            },
            "conversion": {
                "engine": "pdfplumber",
                "engine_version": version("pdfplumber"),
                "coordinates": "PDF points, origin at top-left",
                "table_settings": {},
            },
            "review": {"status": "unreviewed"},
            "pages": output_pages,
            "tables": output_tables,
        }
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--lang", choices=("zh", "en"), required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--pages", help="one-based pages, e.g. 18-22 or 18,20-22")
    selection.add_argument("--electrical-chapter", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    document = convert(args.pdf, args.lang, args.pages, args.electrical_chapter)
    args.out.mkdir(parents=True, exist_ok=True)
    destination = args.out / f"{args.pdf.stem}.{args.lang}.structured.json"
    destination.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    labelled = sum(table["caption"] is not None for table in document["tables"])
    continuations = sum(table["continues_from_previous"] for table in document["tables"])
    print(f"{destination}: {len(document['pages'])} pages, "
          f"{len(document['tables'])} table fragments "
          f"({labelled} labelled, {continuations} continuations)")


if __name__ == "__main__":
    main()
