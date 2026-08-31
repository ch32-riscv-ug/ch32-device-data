#!/usr/bin/env python3
"""Render one or two structured datasheet excerpts as review HTML."""

from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path

import jsonschema

import convert_structured


STYLE = """
:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
body { margin: 1.5rem; max-width: 1800px; }
h1, h2 { line-height: 1.2; }
.meta, .small { color: #666; font-size: .88rem; }
.summary { border-collapse: collapse; margin: 1rem 0 2rem; }
.summary th, .summary td { border: 1px solid #aaa; padding: .35rem .6rem; }
.ok { color: #087830; font-weight: 700; }
.missing { color: #b3261e; font-weight: 700; }
.pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.edition { min-width: 0; border: 1px solid #aaa; border-radius: .4rem; padding: .75rem; overflow: auto; }
.fragment { margin: .75rem 0 1.5rem; }
.caption { font-weight: 650; margin-bottom: .35rem; }
table.source { border-collapse: collapse; width: 100%; font-size: .86rem; }
table.source td { border: 1px solid #888; padding: .25rem .35rem; vertical-align: top; white-space: pre-wrap; }
table.source td:empty { min-width: 1.5rem; height: 1.1rem; }
details { margin: .5rem 0; }
pre { white-space: pre-wrap; font-size: .8rem; }
@media (max-width: 1000px) { .pair { grid-template-columns: 1fr; } }
@media (prefers-color-scheme: dark) { .meta, .small { color: #bbb; } }
"""


def load(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(convert_structured.SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    return document


def number_for(table: dict) -> str:
    if table["caption"]:
        return table["caption"]["source_number"]
    logical = table["logical_id"]
    return logical.removeprefix("table-").rsplit("@", 1)[0] if logical.startswith("table-") else logical


def group_tables(document: dict) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for table in document["tables"]:
        grouped[table["logical_id"]].append(table)
    return dict(grouped)


def render_grid(table: dict) -> str:
    starts = {(cell["row_start"], cell["column_start"]): cell
              for cell in table["cells"]}
    covered = set()
    for cell in table["cells"]:
        for row in range(cell["row_start"], cell["row_end"]):
            for col in range(cell["column_start"], cell["column_end"]):
                if (row, col) != (cell["row_start"], cell["column_start"]):
                    covered.add((row, col))
    rows = []
    for row in range(table["row_count"]):
        cells = []
        for col in range(table["column_count"]):
            if (row, col) in covered:
                continue
            cell = starts.get((row, col))
            if cell is None:
                cells.append("<td class=missing-cell></td>")
                continue
            rowspan = cell["row_end"] - cell["row_start"]
            colspan = cell["column_end"] - cell["column_start"]
            attrs = [f'rowspan="{rowspan}"' if rowspan > 1 else "",
                     f'colspan="{colspan}"' if colspan > 1 else "",
                     f'title="{html.escape(cell["id"])}; bbox={cell["bbox"]}"']
            value = html.escape(cell["text"]).replace("\n", "<br>")
            cells.append(f"<td {' '.join(filter(None, attrs))}>{value}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table class=source>" + "".join(rows) + "</table>"


def render_group(group: list[dict] | None, lang: str) -> str:
    if not group:
        return f'<div class="edition missing">{lang}: no corresponding table</div>'
    fragments = []
    for table in group:
        caption = table["caption"]["text"] if table["caption"] else "continued fragment"
        fragments.append(
            '<div class="fragment">'
            f'<div class="caption">{html.escape(caption)}</div>'
            f'<div class="small">page {table["page"]}; {table["id"]}; '
            f'{table["row_count"]}×{table["column_count"]}; '
            f'review={table["review"]["status"]}</div>'
            f'{render_grid(table)}</div>')
    return f'<div class="edition"><h3>{lang}</h3>{"".join(fragments)}</div>'


def page_text(document: dict) -> str:
    blocks = []
    for page in document["pages"]:
        text = "\n".join(line["text"] for line in page["lines"])
        blocks.append(f'<details><summary>page {page["number"]} text</summary>'
                      f'<pre>{html.escape(text)}</pre></details>')
    return "".join(blocks)


def render(documents: list[dict]) -> str:
    by_lang = {document["source"]["language"]: document for document in documents}
    grouped = {lang: group_tables(document) for lang, document in by_lang.items()}
    logical_ids = []
    for document in documents:
        for table in document["tables"]:
            if table["logical_id"] not in logical_ids:
                logical_ids.append(table["logical_id"])

    metadata = []
    for lang, document in by_lang.items():
        source = document["source"]
        metadata.append(
            f'<div><strong>{lang}</strong>: {html.escape(source["document"])}; '
            f'pages {source["selected_pages"]}; SHA-256 {source["sha256"][:12]}…; '
            f'review={document["review"]["status"]}</div>')

    summary_rows = []
    for logical_id in logical_ids:
        present = {lang: len(groups.get(logical_id, [])) for lang, groups in grouped.items()}
        comparable = len(by_lang) == 2 and all(present.get(lang) for lang in ("zh", "en"))
        sample = next(grouped[lang][logical_id][0] for lang in grouped if logical_id in grouped[lang])
        summary_rows.append(
            f'<tr><td>{html.escape(number_for(sample))}</td>'
            f'<td>{present.get("zh", 0)}</td><td>{present.get("en", 0)}</td>'
            f'<td class="{"ok" if comparable else "missing"}">'
            f'{"paired" if comparable else "check"}</td></tr>')

    sections = []
    for logical_id in logical_ids:
        sample = next(grouped[lang][logical_id][0] for lang in grouped if logical_id in grouped[lang])
        sections.append(
            f'<section><h2>Table {html.escape(number_for(sample))}</h2><div class=pair>'
            f'{render_group(grouped.get("zh", {}).get(logical_id), "zh")}'
            f'{render_group(grouped.get("en", {}).get(logical_id), "en")}'
            '</div></section>')

    raw_text = "".join(
        f'<section><h2>{lang} page text</h2>{page_text(document)}</section>'
        for lang, document in by_lang.items())
    title = html.escape(documents[0]["source"]["document"])
    return (f'<!doctype html><html lang="en"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title} structured review</title><style>{STYLE}</style><body>'
            f'<h1>{title}: structured conversion review</h1>'
            f'<div class=meta>{"".join(metadata)}</div>'
            '<table class=summary><thead><tr><th>table</th><th>zh fragments</th>'
            '<th>en fragments</th><th>pairing</th></tr></thead><tbody>'
            f'{"".join(summary_rows)}</tbody></table>{"".join(sections)}{raw_text}</body></html>')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("structured", type=Path, nargs="+", help="one file, or zh and en files")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    documents = [load(path) for path in args.structured]
    languages = [document["source"]["language"] for document in documents]
    if len(set(languages)) != len(languages):
        parser.error("each input must have a different language")
    if len(documents) > 2:
        parser.error("at most two inputs are supported")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(documents), encoding="utf-8")
    print(f"{args.out}: {len(documents)} editions")


if __name__ == "__main__":
    main()
