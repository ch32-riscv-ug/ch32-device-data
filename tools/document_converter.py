#!/usr/bin/env python3
"""Convert an entire PDF document to a generic structured-document bundle.

The default scope is every page.  ``--pages`` exists only for converter
development and regression probes; production extraction must use an all-pages
bundle.  The generated raw pages are replaceable.  ``review.json`` is a sidecar
and is created only when absent, so reconversion never erases human decisions.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import statistics
from importlib.metadata import version
from pathlib import Path

import jsonschema
import pdfplumber

import convert_structured as v01
import paths


VERSION = "0.2"
DEFAULT_OUT = paths.CACHE / "structured-documents"
MANIFEST_SCHEMA = paths.REPO / "schemas" / "structured-document-manifest.schema.json"
PAGE_SCHEMA = paths.REPO / "schemas" / "structured-document-page.schema.json"
GEOMETRY_SCHEMA = paths.REPO / "schemas" / "structured-document-geometry.schema.json"
REVIEW_SCHEMA = paths.REPO / "schemas" / "structured-document-review.schema.json"


def dump_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


_VALIDATORS: dict[Path, jsonschema.Draft202012Validator] = {}


def validate(value: dict, schema_path: Path) -> None:
    validator = _VALIDATORS.get(schema_path)
    if validator is None:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        _VALIDATORS[schema_path] = validator
    validator.validate(value)


def validate_geometry(value: dict) -> None:
    """Fast validation for the very large per-character precision layer.

    Draft-2020 validation dispatches once per property of every glyph and made
    a large RM take over an hour.  The converter owns this record, so validate
    its envelope here; the independent checker walks every ID and bbox.
    """
    if set(value) != {"schema_version", "source_sha256", "number", "chars", "drawings"}:
        raise ValueError("precision geometry has unexpected or missing keys")
    if value["schema_version"] != VERSION or len(value["source_sha256"]) != 64:
        raise ValueError("precision geometry has invalid identity")
    if not isinstance(value["number"], int) or value["number"] < 1:
        raise ValueError("precision geometry has invalid page number")
    if not isinstance(value["chars"], list) or not isinstance(value["drawings"], list):
        raise ValueError("precision geometry arrays are invalid")


def text_items(page, kind: str) -> list[dict]:
    source = (page.extract_text_lines(return_chars=False) if kind == "line"
              else page.extract_words())
    out = []
    for index, item in enumerate(source or [], 1):
        out.append({
            "id": f"p{page.page_number}-{kind}-{index:05d}",
            "text": item["text"],
            "bbox": v01.rounded_box((item["x0"], item["top"],
                                      item["x1"], item["bottom"])),
        })
    return out


def chars(page) -> list[dict]:
    out = []
    for index, item in enumerate(page.chars, 1):
        out.append({
            "id": f"p{page.page_number}-char-{index:06d}",
            "text": item.get("text", ""),
            "bbox": v01.rounded_box((item["x0"], item["top"],
                                      item["x1"], item["bottom"])),
            "font": str(item.get("fontname") or ""),
            "size": round(float(item.get("size") or 0), 3),
            "upright": bool(item.get("upright", True)),
        })
    return out


HEADING_NUMBER = re.compile(r"^(?P<number>\d+(?:\.\d+)+)\s+\S")
CHAPTER_HEADING = re.compile(r"^(?:第\s*\d+\s*章|Chapter\s+\d+)", re.I)
LIST_ITEM = re.compile(r"^(?:[•●▪◆◇*-]|\(\d+\)|[a-z]\))\s*")


def classify_lines(lines: list[dict], page_chars: list[dict], height: float) -> None:
    sizes = [item["size"] for item in page_chars
             if item["text"].strip() and item["size"] > 0]
    body_size = statistics.median(sizes) if sizes else 0
    for line in lines:
        x0, top, x1, bottom = line["bbox"]
        members = [item for item in page_chars
                   if item["bbox"][2] >= x0 and item["bbox"][0] <= x1
                   and item["bbox"][3] >= top and item["bbox"][1] <= bottom]
        line_sizes = [item["size"] for item in members if item["text"].strip()]
        line["font_size"] = round(statistics.median(line_sizes), 3) if line_sizes else 0
        named = [item for item in members if item["text"].strip()]
        line["bold"] = bool(named) and sum(
            "bold" in item["font"].lower() for item in named) >= len(named) / 2
        text = line["text"].strip()
        numbered = HEADING_NUMBER.match(text)
        if CHAPTER_HEADING.match(text) or numbered or (
                len(text) <= 120 and body_size and line["font_size"] >= body_size * 1.25):
            line["role"] = "heading"
            line["level"] = (min(6, numbered.group("number").count(".") + 1)
                             if numbered else 1)
        elif top < height * 0.06:
            line["role"] = "header"
        elif bottom > height * 0.94:
            line["role"] = "footer"
        elif LIST_ITEM.match(text):
            line["role"] = "list-item"
        else:
            line["role"] = "paragraph"


def drawings(page) -> list[dict]:
    out = []
    for kind in ("line", "rect", "curve", "image"):
        for index, item in enumerate(getattr(page, f"{kind}s"), 1):
            record = {
                "id": f"p{page.page_number}-draw-{kind}-{index:05d}",
                "type": kind,
                "bbox": v01.rounded_box((item["x0"], item["top"],
                                          item["x1"], item["bottom"])),
            }
            if kind == "image":
                if item.get("name"):
                    record["name"] = str(item["name"])
                size = item.get("srcsize")
                if size and len(size) == 2:
                    record["source_size"] = [int(size[0]), int(size[1])]
            out.append(record)
    return out


def overlap_issues(cells: list[dict]) -> list[str]:
    occupied = {}
    overlaps = []
    for cell in cells:
        for row in range(cell["row_start"], cell["row_end"]):
            for column in range(cell["column_start"], cell["column_end"]):
                previous = occupied.get((row, column))
                if previous:
                    overlaps.append(f"{cell['id']} overlaps {previous} at {row},{column}")
                occupied[(row, column)] = cell["id"]
    return overlaps


def page_record(page, lang: str, source_sha256: str,
                previous_logical_id: str | None,
                previous_page: int | None,
                number_occurrences: dict[str, int]) -> tuple[dict, dict, str | None]:
    page_chars = chars(page)
    lines = text_items(page, "line")
    classify_lines(lines, page_chars, float(page.height))
    words = text_items(page, "word")
    page_drawings = drawings(page)
    captions = v01.captions(lines, lang)
    detected = sorted(page.find_tables(), key=lambda item: (item.bbox[1], item.bbox[0]))
    tables = []
    previous_bottom = 0.0
    for table_index, table in enumerate(detected, 1):
        candidates = [item for item in captions
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
            consecutive = previous_page is not None and page.page_number == previous_page + 1
            logical_id = (previous_logical_id if consecutive and previous_logical_id
                          else f"unlabelled-p{page.page_number}-{table_index}")
            caption_record = None
            continues = bool(consecutive and previous_logical_id)
        table_id = f"p{page.page_number}-table-{table_index:03d}"
        cells, row_count, column_count = v01.physical_cells(page, table, table_id)
        tables.append({
            "id": table_id,
            "logical_id": logical_id,
            "bbox": v01.rounded_box(table.bbox),
            "caption": caption_record,
            "continues_from_previous": continues,
            "row_count": row_count,
            "column_count": column_count,
            # Preserve pdfplumber's flattened view as well as physical cells.
            # They answer different questions for merged register/electrical
            # tables, and retaining both makes migration lossless.
            "extracted_rows": table.extract(),
            "row_cells": [[v01.rounded_box(cell) if cell is not None else None
                           for cell in row.cells] for row in table.rows],
            "cells": cells,
            "issues": overlap_issues(cells),
        })
        previous_bottom = table.bbox[3]

    def outside_tables(line: dict) -> bool:
        x0, top, x1, bottom = line["bbox"]
        center_x, center_y = (x0 + x1) / 2, (top + bottom) / 2
        return not any(table["bbox"][0] <= center_x <= table["bbox"][2]
                       and table["bbox"][1] <= center_y <= table["bbox"][3]
                       for table in tables)

    order = ([{"id": line["id"], "type": "line", "bbox": line["bbox"]}
              for line in lines if outside_tables(line)]
             + [{"id": table["id"], "type": "table", "bbox": table["bbox"]}
                for table in tables]
             + [{"id": item["id"], "type": "image", "bbox": item["bbox"]}
                for item in page_drawings if item["type"] == "image"])
    order.sort(key=lambda item: (item["bbox"][1], item["bbox"][0], item["type"]))
    record = {
        "schema_version": VERSION,
        "source_sha256": source_sha256,
        "number": page.page_number,
        "width": round(float(page.width), 3),
        "height": round(float(page.height), 3),
        "rotation": int(getattr(page, "rotation", 0) or 0),
        "text": page.extract_text() or "",
        "lines": lines,
        "words": words,
        "images": [item for item in page_drawings if item["type"] == "image"],
        "tables": tables,
        "reading_order": order,
    }
    geometry = {
        "schema_version": VERSION,
        "source_sha256": source_sha256,
        "number": page.page_number,
        "chars": page_chars,
        "drawings": page_drawings,
    }
    return record, geometry, previous_logical_id


def convert(pdf_path: Path, lang: str, document_type: str, out: Path,
            pages_arg: str | None) -> Path:
    source_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    bundle = out / f"{pdf_path.stem}.{lang}"
    review_path = bundle / "review.json"
    if review_path.exists():
        old_review = json.loads(review_path.read_text(encoding="utf-8"))
        validate(old_review, REVIEW_SCHEMA)
        if old_review["source_sha256"] != source_sha256:
            raise ValueError(
                f"{review_path}: belongs to a different source; move or review it before reconversion")
    page_dir = bundle / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir = bundle / "geometry"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    page_entries = []
    number_occurrences: dict[str, int] = {}
    previous_logical_id = None
    previous_page = None
    with pdfplumber.open(pdf_path) as pdf:
        selected = (v01.parse_pages(pages_arg, len(pdf.pages)) if pages_arg
                    else list(range(1, len(pdf.pages) + 1)))
        for page_number in selected:
            page = pdf.pages[page_number - 1]
            record, geometry, previous_logical_id = page_record(
                page, lang, source_sha256, previous_logical_id,
                previous_page, number_occurrences)
            validate(record, PAGE_SCHEMA)
            validate_geometry(geometry)
            payload = dump_bytes(record)
            geometry_payload = gzip.compress(dump_bytes(geometry), compresslevel=9, mtime=0)
            relative = Path("pages") / f"{page_number:04d}.json"
            geometry_relative = Path("geometry") / f"{page_number:04d}.json.gz"
            (bundle / relative).write_bytes(payload)
            (bundle / geometry_relative).write_bytes(geometry_payload)
            page_entries.append({
                "number": page_number,
                "file": relative.as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "geometry_file": geometry_relative.as_posix(),
                "geometry_sha256": hashlib.sha256(geometry_payload).hexdigest(),
                "width": record["width"],
                "height": record["height"],
            })
            previous_page = page_number
            page.flush_cache()
        page_count = len(pdf.pages)

    manifest = {
        "schema_version": VERSION,
        "source": {
            "document": pdf_path.name,
            "document_type": document_type,
            "language": lang,
            "sha256": source_sha256,
            "page_count": page_count,
        },
        "conversion": {
            "engine": "pdfplumber",
            "engine_version": version("pdfplumber"),
            "coordinates": "PDF points, origin at top-left",
            "scope": "excerpt" if pages_arg else "all-pages",
            "table_settings": {},
        },
        "pages": page_entries,
    }
    validate(manifest, MANIFEST_SCHEMA)
    (bundle / "manifest.json").write_bytes(dump_bytes(manifest))

    if not review_path.exists():
        review = {
            "schema_version": VERSION,
            "source_sha256": source_sha256,
            "status": "unreviewed",
            "decisions": {},
        }
        validate(review, REVIEW_SCHEMA)
        review_path.write_bytes(dump_bytes(review))
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--lang", choices=("zh", "en"), required=True)
    parser.add_argument(
        "--document-type",
        choices=("datasheet", "reference-manual", "core-manual",
                 "package-drawing", "other", "unknown"),
        default="unknown")
    parser.add_argument("--pages", help="development only; default converts every page")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    bundle = convert(args.pdf, args.lang, args.document_type, args.out, args.pages)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    print(f"{bundle}: {len(manifest['pages'])}/{manifest['source']['page_count']} pages "
          f"({manifest['conversion']['scope']})")


if __name__ == "__main__":
    main()
