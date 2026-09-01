#!/usr/bin/env python3
"""構造化bundle → 人が読むMarkdown（D18 review工程。ゴールは PDF との差ゼロ）。

PoCの`tools/export_document_markdown.py`を出発点に、本番の要件を足したもの。

- **既知の取りこぼしは隠さず、その場所で見えるように印を出す**（2026-09-01の
  ユーザー要件）。印を出すのは:
  - **図** — 資料自身のcaption行（`Figure N-N`／`图N-N`）を検出し、その直後に
    「図は再現していない」の警告と原本PDFの該当ページへのリンクを置く。
    vector描画の個数では判定しない（普通の文章ページでも数十個あり誤検出する
    ——V003で実測）。captionの無い図はこの印から漏れるので、**各ページ冒頭の
    原本リンク**が最後の砦
  - **大きめの画像**（40×40pt以上）— 個別に占位を置く。小さい画像（点線などの
    3×1px断片）はHTMLコメントに留める
  - **復号できなかったglyph** — 本文に`(cid:N)`が残るページは冒頭で個数を警告
  - **表のissues** — 変換器が記録した結合セルの重なり等を表の直前に警告
- header/footerはHTMLコメント（表示からは消えるが監査には残る）
- 表はrowspan/colspanを保ったHTML table（pipe表は結合セルを表せない）
- 本文はhtml escape（`<`や`&`を含む原文がHTML解釈で消えないように）
- 読む順はbundleの`reading_order`
- pageの中身はmanifestのSHA-256と照合してから使う

出力は`.cache/structured-markdown/<stem>.<lang>/`（再生成できる表示。非コミット）。
PDFとの「差ゼロ」は`pipeline/checks/check_markdown_parity.py`が機械検査する。

実行:
    uv run pipeline/review/export_markdown.py --all
    uv run pipeline/review/export_markdown.py .cache/structured-bundles/CH32V003DS0.en
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
import logical_tables  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
DEFAULT_OUT = REPO / ".cache" / "structured-markdown"

FIGURE_CAPTION = re.compile(r"^(?:Figure|图)\s*\d+(?:-\d+)*", re.IGNORECASE)
LARGE_IMAGE = 40.0   # pt。これ以上の幅と高さを持つ画像は個別の占位を出す


def mirror_urls() -> dict[tuple[str, str], str]:
    """(document, lang) → mirrorのGitHub Pages URL（原本ページへのリンク用）。"""
    out: dict[tuple[str, str], str] = {}
    with (REPO / "catalog" / "documents.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for lang in ("zh", "en"):
                if row.get(f"mirror_url_{lang}"):
                    out[(row["document"], lang)] = row[f"mirror_url_{lang}"]
    return out


def page_link(url: str | None, number: int, label: str) -> str:
    if url:
        return f"[{label}]({url}#page={number})"
    return label


def load_page(bundle: Path, entry: dict) -> dict:
    payload = (bundle / entry["file"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
    return json.loads(payload)


def table_html(table: dict, url: str | None, number: int) -> str:
    columns = table.get("width") or table["column_count"]
    grid: list[list[str | None]] = [[None for _ in range(columns)]
                                    for _ in range(table["row_count"])]
    for cell in table["cells"]:
        attrs = []
        if cell["row_end"] - cell["row_start"] > 1:
            attrs.append(f'rowspan="{cell["row_end"] - cell["row_start"]}"')
        if cell["column_end"] - cell["column_start"] > 1:
            attrs.append(f'colspan="{cell["column_end"] - cell["column_start"]}"')
        grid[cell["row_start"]][cell["column_start"]] = (
            "<td" + ("".join(" " + a for a in attrs)) + ">"
            + html.escape(cell["text"]) + "</td>")
    rows = ["<tr>" + "".join(cell or "" for cell in row) + "</tr>" for row in grid]
    caption = table["caption"]["text"] if table["caption"] else table["logical_id"]
    span = table.get("parts")
    parts = []
    if table["issues"]:
        where = (f"the PDF, pp.{span[0][0]}-{span[-1][0]}" if span
                 else f"the PDF, p.{number}")
        parts.append(f"> ⚠ Table extraction recorded {len(table['issues'])} issue(s) "
                     f"(overlapping merged cells); verify against "
                     f"{page_link(url, number, where)}.\n")
    origin = (f"<!-- {table['id']} pages {span[0][0]}-{span[-1][0]} -->" if span
              else f"<!-- {table['id']} -->")
    parts.append(f"{origin}\n"
                 f"<table><caption>{html.escape(caption)}</caption>{''.join(rows)}</table>")
    return "\n".join(parts)


def render_page(page: dict, url: str | None, chains: dict[str, dict]) -> str:
    tables = {item["id"]: item for item in page["tables"]}
    lines = {item["id"]: item for item in page["lines"]}
    images = {item["id"]: item for item in page["images"]}
    number = page["number"]
    output = [f"<!-- source-page: {number} -->",
              f"<sub>{page_link(url, number, f'PDF p.{number}')}</sub>", ""]
    cids = page["text"].count("(cid:")
    if cids:
        output += [f"> ⚠ {cids} glyph(s) on this page could not be decoded to text "
                   f"(they appear as `(cid:N)`); read "
                   f"{page_link(url, number, f'the PDF, p.{number}')}.", ""]
    for item in page["reading_order"]:
        if item["type"] == "table":
            info = chains[item["id"]]
            if not info["start"]:
                # 表はページを跨ぐが、人向けには開始ページで結合済みの全体を描く。
                # このページの断片の場所には可視のポインタを置く（黙って消さない）。
                output.extend(("", f"> ⬆ **Table continued** — rendered in full at "
                               f"[page {info['start_page']}]"
                               f"({info['start_page']:04d}.md). <!-- {item['id']} -->", ""))
                continue
            record = info["merged"] or tables[item["id"]]
            output.extend(("", table_html(record, url, number), ""))
            continue
        if item["type"] == "image":
            image = images[item["id"]]
            x0, top, x1, bottom = image["bbox"]
            if x1 - x0 >= LARGE_IMAGE and bottom - top >= LARGE_IMAGE:
                output.extend(("", f"> 🖼 **Image not reproduced** "
                               f"({x1 - x0:.0f}×{bottom - top:.0f} pt) — see "
                               f"{page_link(url, number, f'the PDF, p.{number}')}."
                               f" <!-- {image['id']} -->", ""))
            else:
                output.append(f"<!-- image: {image['id']} bbox={image['bbox']} -->")
            continue
        line = lines[item["id"]]
        role = line.get("role", "paragraph")
        text = html.escape(line["text"])
        if role in ("header", "footer"):
            output.append(f"<!-- {role}: {text} -->")
            continue
        if FIGURE_CAPTION.match(line["text"].strip()):
            # 図そのものは再現していない。captionの場所で見えるように言う。
            output.extend(("", text + "  ",
                           f"> ⚠ **The figure itself is not reproduced** — see "
                           f"{page_link(url, number, f'the PDF, p.{number}')}.", ""))
            continue
        if role == "heading":
            output.extend(("", "#" * min(6, line.get("level", 2)) + " " + text, ""))
        elif role == "list-item":
            output.append("- " + text)
        else:
            output.append(text + "  ")
    return "\n".join(output).rstrip() + "\n"


def export(bundle: Path, out_root: Path, urls: dict[tuple[str, str], str]) -> Path:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    source = manifest["source"]
    url = urls.get((source["document"], source["language"]))
    out = out_root / bundle.name
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    pages = [load_page(bundle, entry) for entry in manifest["pages"]]
    chains = logical_tables.document_chains(pages)
    links = []
    for page in pages:
        name = f"{page['number']:04d}.md"
        (pages_dir / name).write_text(render_page(page, url, chains), encoding="utf-8")
        links.append(f"- [page {page['number']}](pages/{name})")
    (out / "README.md").write_text(
        f"# {source['document']} ({source['language']})\n\n"
        f"- type: `{source['document_type']}`\n"
        f"- source SHA-256: `{source['sha256']}`\n"
        + (f"- original: <{url}>\n" if url else "")
        + "\nHeaders and footers are folded into HTML comments. Figures are not\n"
        "reproduced; every figure caption and every page links back to the PDF.\n"
        "A table that spans pages is rendered in full on the page where it starts;\n"
        "the following pages carry a visible pointer instead of a fragment.\n\n"
        + "\n".join(links) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundle", type=Path, nargs="?")
    ap.add_argument("--all", action="store_true", help="catalogの全bundleを書き出す")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="出力先の上書き（試験用）")
    args = ap.parse_args()
    urls = mirror_urls()
    if args.all:
        sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
        import convert_all  # noqa: PLC0415
        done = 0
        for job in convert_all.targets():
            export(BUNDLES / job["name"], args.out, urls)
            done += 1
        print(f"{done} documents -> {args.out}", file=sys.stderr)
        return 0
    if not args.bundle:
        ap.error("give a bundle path or --all")
    print(export(args.bundle, args.out, urls))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
