#!/usr/bin/env python3
"""PoC: extract operating-condition rows from structured-document JSON.

The input contains no domain interpretation; this program never opens a PDF.
For the PoC it reuses the existing symbol/value rules from build_operating.py so
we can compare only the effect of inserting the structured-document boundary.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import jsonschema

import build_operating as operating
import convert_structured


COLUMNS = ["symbol", "parameter", "condition", "min", "typ", "max", "unit",
           "page", "table", "fragment"]
LOGICAL_NUMBER = re.compile(r"^table-(?P<number>\d+(?:-\d+)+)@\d+$")


def norm_header(cell: str | None) -> str | None:
    """PoC-local header normalisation; do not modify the production parser."""
    text = operating.FOOTNOTE.sub("", cell or "")
    text = re.sub(r"\s+", "", text).replace(".", "")
    if text.lower().startswith("condition:"):
        text = "condition"
    return operating.HEADER_MAP.get(text.lower() if text.isascii() else text)


def _header_labels(table: list[list[str | None]], header_end: int) -> dict[int, str]:
    labels = {}
    for column in range(max(map(len, table))):
        parts = []
        for row in table[:header_end]:
            cell = row[column] if column < len(row) else None
            text = operating.norm_text(cell)
            if text and norm_header(cell) is None and text not in parts:
                parts.append(text)
        labels[column] = " ".join(parts)
    return labels


def infer_schema(table: list[list[str | None]], previous: dict | None = None) -> dict | None:
    """Map a physical table grid to the domain columns used by the PoC."""
    if not table:
        return None
    width = max(map(len, table))
    padded = [list(row) + [None] * (width - len(row)) for row in table]
    header_at = None
    headers = None
    for index, row in enumerate(padded[:4]):
        candidate = [norm_header(cell) for cell in row]
        if "symbol" in candidate and "parameter" in candidate and "unit" in candidate:
            header_at, headers = index, candidate
            break
    if header_at is None:
        if previous and previous["width"] == width:
            return {**previous, "data_start": 0, "continued": True}
        data_start = next((index for index, row in enumerate(padded[:4])
                           if operating.KEEP.match(operating.norm_symbol(row[0]))), None)
        if data_start is None or width < 5:
            return None
        first = padded[data_start]
        if not operating.norm_text(first[1]) or not operating.norm_value(first[-1]):
            return None
        return {
            "width": width,
            "symbol": 0,
            "parameter": 1,
            "unit": width - 1,
            "conditions": list(range(2, width - 2)),
            "values": {width - 2: "typ"},
            "labels": _header_labels(padded, data_start),
            "data_start": data_start,
            "continued": False,
        }

    positions = {name: index for index, name in enumerate(headers) if name}
    values = {index: name for index, name in enumerate(headers)
              if name in {"min", "typ", "max"}}
    if not values:
        return None
    symbol_column = positions["symbol"]
    data_start = header_at + 1
    while data_start < min(len(padded), header_at + 5):
        symbol = operating.norm_symbol(padded[data_start][symbol_column])
        if symbol and symbol not in operating.HEADER_ROW:
            break
        data_start += 1
    labels = _header_labels(padded[header_at:data_start], data_start - header_at)
    unit_column = positions["unit"]
    for column, kind in list(sorted(values.items())):
        following = min([position for position in list(values) + [unit_column]
                         if position > column], default=unit_column)
        for extra in range(column + 1, following):
            if headers[extra] is None and labels.get(extra):
                values[extra] = kind
    first_value = min(values)
    assigned = {symbol_column, positions["parameter"], unit_column, *values}
    conditions = [index for index in range(positions["parameter"] + 1, first_value)
                  if index not in assigned]
    if "condition" in positions and positions["condition"] not in conditions:
        conditions.insert(0, positions["condition"])
    return {
        "width": width,
        "symbol": symbol_column,
        "parameter": positions["parameter"],
        "unit": unit_column,
        "conditions": sorted(set(conditions)),
        "values": dict(sorted(values.items())),
        "labels": labels,
        "data_start": data_start,
        "continued": False,
    }


def _condition_text(state: dict, schema: dict, value_column: int | None,
                    table_context: str) -> str:
    parts = [table_context] if table_context else []
    for column in schema["conditions"]:
        value = state["conditions"].get(column, "")
        if value:
            label = schema["labels"].get(column, "")
            parts.append(f"{label}={value}" if label else value)
    if value_column is not None:
        label = schema["labels"].get(value_column, "")
        if label:
            parts.append(label)
    return "; ".join(parts)


def parse_table(table: list[list[str | None]], schema: dict, state: dict,
                lang: str, page: int, number: str,
                table_context: str) -> tuple[list[dict], dict]:
    width = schema["width"]
    output = []
    counts = {}
    for kind in schema["values"].values():
        counts[kind] = counts.get(kind, 0) + 1
    split_kinds = {kind for kind, count in counts.items() if count > 1}
    for raw in table[schema["data_start"]:]:
        cells = list(raw) + [None] * (width - len(raw))
        symbol = operating.norm_symbol(cells[schema["symbol"]])
        parameter = operating.norm_text(cells[schema["parameter"]])
        if symbol:
            state = {"symbol": symbol, "parameter": parameter,
                     "unit": state.get("unit", ""), "conditions": {}}
        elif not state.get("symbol"):
            continue
        elif parameter:
            state["parameter"] = parameter
        unit = operating.norm_value(cells[schema["unit"]])
        if unit:
            state["unit"] = unit
        for column in schema["conditions"]:
            value = operating.norm_text(cells[column])
            if value:
                state["conditions"][column] = value
        values = {column: operating.norm_value(cells[column])
                  for column in schema["values"]}
        if not (symbol or parameter or unit or any(values.values())):
            continue
        duplicate = next(iter(split_kinds), None)
        selected = ([column for column, kind in schema["values"].items()
                     if kind == duplicate and values[column]] if duplicate else [None])
        if duplicate and not selected:
            selected = [None]
        for value_column in selected:
            row_values = {"min": "", "typ": "", "max": ""}
            for column, kind in schema["values"].items():
                if kind != duplicate or column == value_column:
                    row_values[kind] = values[column]
            row = {
                "symbol": state["symbol"],
                "parameter": state["parameter"],
                "condition": _condition_text(
                    state, schema, value_column, table_context),
                **row_values,
                "unit": state["unit"],
                "_table": number,
            }
            if operating.keep_row(row, lang, page):
                output.append({**row, "_page": page})
    return output, state


def grid(table: dict) -> list[list[str | None]]:
    """Expand physical cells to a matrix; covered span positions stay None."""
    rows = [[None for _ in range(table["column_count"])]
            for _ in range(table["row_count"])]
    for cell in table["cells"]:
        rows[cell["row_start"]][cell["column_start"]] = cell["text"]
    return rows


def table_number(table: dict) -> str:
    if table["caption"]:
        return table["caption"]["source_number"]
    match = LOGICAL_NUMBER.match(table["logical_id"])
    return match.group("number") if match else ""


def caption_context(table: dict) -> str:
    caption = table["caption"]
    if not caption:
        return ""
    # Branch tables put a whole-table VDD/SRAM condition in the title.  Keep
    # the title tail as source text; deciding whether it is meaningful belongs
    # to the domain parser, not the converter.
    text = caption["text"]
    match = convert_structured.TABLE_NUMBER["en"].search(text)
    if not match:
        match = convert_structured.TABLE_NUMBER["zh"].search(text)
    return text[match.end():].strip() if match else text


def extract(document: dict, allow_unreviewed: bool = False) -> list[dict]:
    if document["review"]["status"] != "approved" and not allow_unreviewed:
        raise ValueError("structured document is not approved; use --allow-unreviewed only for PoC")
    lang = document["source"]["language"]
    schemas: dict[str, dict] = {}
    states: dict[str, dict] = {}
    contexts: dict[str, str] = {}
    rows = []
    for table in document["tables"]:
        logical_id = table["logical_id"]
        raw = grid(table)
        previous = schemas.get(logical_id)
        schema = infer_schema(raw, previous)
        if schema is None:
            continue
        schemas[logical_id] = {key: value for key, value in schema.items()
                               if key not in {"data_start", "continued"}}
        context = caption_context(table)
        if context:
            contexts[logical_id] = context
        found, state = parse_table(
            raw, schema, states.get(logical_id, {}), lang, table["page"],
            table_number(table), contexts.get(logical_id, ""))
        states[logical_id] = state
        for row in found:
            rows.append({
                **{key: row.get(key, "") for key in COLUMNS},
                "page": row["_page"],
                "table": row["_table"],
                "fragment": table["id"],
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("structured", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--allow-unreviewed", action="store_true",
                        help="PoC only: extract before human approval")
    args = parser.parse_args()

    document = json.loads(args.structured.read_text(encoding="utf-8"))
    schema = json.loads(convert_structured.SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    try:
        rows = extract(document, args.allow_unreviewed)
    except ValueError as exc:
        parser.error(str(exc))
    destination = args.out or args.structured.with_suffix(".operating.csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{destination}: {len(rows)} rows")


if __name__ == "__main__":
    main()
