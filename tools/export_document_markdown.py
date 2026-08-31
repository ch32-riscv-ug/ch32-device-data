#!/usr/bin/env python3
"""Export the readable layer of a structured document bundle as Markdown."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import paths


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table_html(table: dict) -> str:
    # HTML inside Markdown preserves merged cells; pipe tables cannot.
    grid = [[None for _ in range(table["column_count"])]
            for _ in range(table["row_count"])]
    for cell in table["cells"]:
        attrs = []
        if cell["row_end"] - cell["row_start"] > 1:
            attrs.append(f'rowspan="{cell["row_end"] - cell["row_start"]}"')
        if cell["column_end"] - cell["column_start"] > 1:
            attrs.append(f'colspan="{cell["column_end"] - cell["column_start"]}"')
        grid[cell["row_start"]][cell["column_start"]] = (
            "<td " + " ".join(attrs) + ">" + html.escape(cell["text"]) + "</td>")
    rows = ["<tr>" + "".join(cell or "" for cell in row) + "</tr>" for row in grid]
    caption = table["caption"]["text"] if table["caption"] else table["logical_id"]
    return f"<!-- {table['id']} -->\n<table><caption>{html.escape(caption)}</caption>{''.join(rows)}</table>"


def render_page(page: dict) -> str:
    tables = {item["id"]: item for item in page["tables"]}
    lines = {item["id"]: item for item in page["lines"]}
    output = [f"<!-- source-page: {page['number']} -->"]
    for item in page["reading_order"]:
        if item["type"] == "table":
            output.extend(("", table_html(tables[item["id"]]), ""))
            continue
        if item["type"] != "line":
            output.append(f"\n<!-- image: {item['id']} bbox={item['bbox']} -->\n")
            continue
        line = lines[item["id"]]
        role = line.get("role", "paragraph")
        text = line["text"]
        if role == "heading":
            output.extend(("", "#" * line.get("level", 2) + " " + text, ""))
        elif role == "list-item":
            output.append("- " + text)
        elif role in ("header", "footer"):
            output.append(f"<!-- {role}: {text} -->")
        else:
            output.append(text + "  ")
    return "\n".join(output).rstrip() + "\n"


def export(bundle: Path, out: Path) -> Path:
    manifest = load(bundle / "manifest.json")
    pages = out / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    page_links = []
    for entry in manifest["pages"]:
        page = load(bundle / entry["file"])
        name = f"{entry['number']:04d}.md"
        (pages / name).write_text(render_page(page), encoding="utf-8")
        page_links.append(f"- [page {entry['number']}](pages/{name})")
    index = out / "README.md"
    index.write_text(
        f"# {manifest['source']['document']}\n\n"
        f"- type: `{manifest['source']['document_type']}`\n"
        f"- language: `{manifest['source']['language']}`\n"
        f"- source SHA-256: `{manifest['source']['sha256']}`\n\n"
        + "\n".join(page_links) + "\n", encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or paths.CACHE / "structured-markdown" / args.bundle.name
    print(export(args.bundle, out))


if __name__ == "__main__":
    main()
