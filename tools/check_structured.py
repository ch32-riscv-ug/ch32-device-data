#!/usr/bin/env python3
"""Validate structured documents and, for two editions, their table universe."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import jsonschema

import convert_structured


def load(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(convert_structured.SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    return document


def table_key(number: str) -> str:
    # A known class of source typo changes only the chapter prefix (e.g. the
    # same table printed as 3-2 and 4-2).  Keep the printed number in JSON but
    # compare the within-chapter identity here.
    return number.split("-", 1)[-1]


def table_numbers(document: dict) -> list[str]:
    return [table_key(table["caption"]["source_number"])
            for table in document["tables"] if table["caption"]]


def validate_geometry(document: dict) -> list[str]:
    errors = []
    pages = {page["number"]: page for page in document["pages"]}
    for table in document["tables"]:
        if table["page"] not in pages:
            errors.append(f'{table["id"]}: page {table["page"]} is absent')
            continue
        occupied = {}
        for cell in table["cells"]:
            if cell["row_end"] > table["row_count"]:
                errors.append(f'{cell["id"]}: row_end exceeds table grid')
            if cell["column_end"] > table["column_count"]:
                errors.append(f'{cell["id"]}: column_end exceeds table grid')
            for row in range(cell["row_start"], cell["row_end"]):
                for column in range(cell["column_start"], cell["column_end"]):
                    if (row, column) in occupied:
                        errors.append(
                            f'{cell["id"]}: overlaps {occupied[(row, column)]} at {row},{column}')
                    occupied[(row, column)] = cell["id"]
    return errors


def compare(left: dict, right: dict) -> list[str]:
    errors = []
    if left["source"]["document"] != right["source"]["document"]:
        errors.append("editions name different source documents")
    if left["source"]["language"] == right["source"]["language"]:
        errors.append("both inputs have the same language")
    sequences = {document["source"]["language"]: table_numbers(document)
                 for document in (left, right)}
    for lang, numbers in sequences.items():
        duplicates = sorted(number for number, count in Counter(numbers).items() if count > 1)
        if duplicates:
            errors.append(f'{lang}: duplicate printed table numbers: {", ".join(duplicates)}')
    if len(sequences) == 2 and len(set(map(tuple, sequences.values()))) != 1:
        langs = sorted(sequences)
        a, b = sequences[langs[0]], sequences[langs[1]]
        first = next((index for index, pair in enumerate(zip(a, b), 1)
                      if pair[0] != pair[1]), min(len(a), len(b)) + 1)
        errors.append(
            f'table sequence differs first at position {first}: '
            f'{langs[0]}={a[first - 1:first]}, {langs[1]}={b[first - 1:first]} '
            f'(counts {len(a)} vs {len(b)})')
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("structured", type=Path, nargs="+")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    if len(args.structured) > 2:
        parser.error("provide one document, or a zh/en pair")
    documents = [load(path) for path in args.structured]
    errors = []
    for path, document in zip(args.structured, documents):
        errors.extend(f"{path}: {error}" for error in validate_geometry(document))
        if args.require_approved and document["review"]["status"] != "approved":
            errors.append(f"{path}: document has not been approved")
        print(f'{path}: {len(document["pages"])} pages, {len(document["tables"])} fragments')
    if len(documents) == 2:
        errors.extend(compare(*documents))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print("structured document check: OK")


if __name__ == "__main__":
    main()
