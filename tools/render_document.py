#!/usr/bin/env python3
"""Render a structured PDF bundle as navigable HTML for human review."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import paths


STYLE = """
body{font-family:system-ui,sans-serif;margin:0;color:#18212b;background:#f4f6f8}
header{position:sticky;top:0;background:#172b4d;color:white;padding:.7rem 1rem;z-index:2}
main{max-width:1100px;margin:1rem auto;background:white;padding:1.2rem;box-shadow:0 1px 5px #bbb}
.meta{color:#52606d}.line{white-space:pre-wrap}.table-wrap{overflow:auto;margin:1rem 0}
table{border-collapse:collapse;font-size:.86rem}td,th{border:1px solid #9aa5b1;padding:.25rem .4rem;vertical-align:top}
.warn{background:#fff4d6;padding:.5rem}.nav{display:flex;justify-content:space-between;margin:1rem 0}
code{font-size:.8rem}details{margin:.8rem 0}
"""


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value) -> str:
    return html.escape(str(value))


def table_html(table: dict) -> str:
    caption = table["caption"]["text"] if table["caption"] else table["logical_id"]
    rows = []
    for row in table["extracted_rows"]:
        rows.append("<tr>" + "".join(
            f"<td>{esc(cell) if cell is not None else ''}</td>" for cell in row) + "</tr>")
    warning = (f'<div class="warn">{esc("; ".join(table["issues"]))}</div>'
               if table["issues"] else "")
    return (f'<section id="{esc(table["id"])}"><h3>{esc(caption)}</h3>{warning}'
            f'<div class="table-wrap"><table>{"".join(rows)}</table></div>'
            f'<details><summary>物理セル構造</summary><pre>{esc(json.dumps(table["cells"], ensure_ascii=False, indent=2))}</pre></details></section>')


def render_page(bundle: Path, out: Path, manifest: dict, page_index: int,
                source: Path | None) -> None:
    entry = manifest["pages"][page_index]
    page = load(bundle / entry["file"])
    number = page["number"]
    previous = f"{manifest['pages'][page_index - 1]['number']:04d}.html" if page_index else "../index.html"
    following = (f"{manifest['pages'][page_index + 1]['number']:04d}.html"
                 if page_index + 1 < len(manifest["pages"]) else "../index.html")
    source_link = (f'<a href="{esc(source.resolve().as_uri())}#page={number}">原本PDFの同じページ</a>'
                   if source else "原本PDF未指定")
    tables = "".join(table_html(table) for table in page["tables"])
    rendered_lines = []
    for line in page["lines"]:
        tag = f'h{line.get("level", 2)}' if line.get("role") == "heading" else "div"
        css = f'line {line.get("role", "paragraph")}'
        rendered_lines.append(
            f'<{tag} class="{css}" id="{esc(line["id"])}">{esc(line["text"])}</{tag}>')
    lines = "\n".join(rendered_lines)
    counts = {"images": len(page["images"]), "precision_geometry": "separate .json.gz"}
    body = f"""<!doctype html><meta charset="utf-8"><title>{esc(manifest['source']['document'])} p.{number}</title>
<style>{STYLE}</style><header>{esc(manifest['source']['document'])} — page {number}</header><main>
<nav class="nav"><a href="{previous}">← 前</a>{source_link}<a href="{following}">次 →</a></nav>
<p class="meta">{page['width']} × {page['height']} pt / drawing {esc(counts)}</p>
<h2>読み順テキスト</h2>{lines}<h2>検出表 ({len(page['tables'])})</h2>{tables}
<details><summary>生テキスト</summary><pre>{esc(page['text'])}</pre></details>
<nav class="nav"><a href="{previous}">← 前</a><a href="{following}">次 →</a></nav></main>"""
    (out / "pages" / f"{number:04d}.html").write_text(body, encoding="utf-8")


def render(bundle: Path, out: Path, source: Path | None) -> Path:
    manifest = load(bundle / "manifest.json")
    review = load(bundle / "review.json")
    (out / "pages").mkdir(parents=True, exist_ok=True)
    links = "".join(f'<li><a href="pages/{e["number"]:04d}.html">page {e["number"]}</a></li>'
                    for e in manifest["pages"])
    index = f"""<!doctype html><meta charset="utf-8"><title>{esc(manifest['source']['document'])}</title>
<style>{STYLE}</style><header>{esc(manifest['source']['document'])}</header><main>
<h1>構造化変換レビュー</h1><p class="meta">type={esc(manifest['source']['document_type'])} / language={esc(manifest['source']['language'])} / pages={len(manifest['pages'])} / review={esc(review['status'])}</p>
<p><code>source sha256: {esc(manifest['source']['sha256'])}</code></p><ol>{links}</ol></main>"""
    target = out / "index.html"
    target.write_text(index, encoding="utf-8")
    for index_ in range(len(manifest["pages"])):
        render_page(bundle, out, manifest, index_, source)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or paths.CACHE / "structured-review" / args.bundle.name
    print(render(args.bundle, out, args.source))


if __name__ == "__main__":
    main()
