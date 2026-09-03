#!/usr/bin/env python3
"""人向けMarkdownとbundleの差ゼロ検査（D18のゴールの機械的定義）。

「PDFと差がない」を2段に分けて検査する。bundle自体はPDFとhashで結ばれている
（変換検証）ので、ここは**bundle→Markdownで何も落ちていない・順序が変わって
いない**ことを見る:

1. 本文の行（header/footer以外）と表の全セルの文字が、bundleの読み順どおりに
   Markdownへ現れること（html escapeを考慮して探す）
2. header/footerの行もコメントとして残っていること（表示から消えるが監査に残る）
3. 図のcaption行の直後に「再現していない」の印があること（既知の取りこぼしを
   隠さない、の検査）
4. 添字が`*`に化けたglyph（壊れたToUnicode。`pipeline/common/lost_subscripts`）を
   持つページの冒頭に、その旨の警告があること

実行:
    uv run pipeline/checks/check_markdown_parity.py --all
    uv run pipeline/checks/check_markdown_parity.py <bundle-dir> <markdown-dir>
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
sys.path.insert(0, str(REPO / "pipeline" / "review"))
import export_markdown  # noqa: E402  cell_htmlの表示を検査と揃える
import figure_captions  # noqa: E402
import logical_tables  # noqa: E402
import lost_subscripts  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
MARKDOWN = REPO / ".cache" / "structured-markdown"
NOT_REPRODUCED = "The figure itself is not reproduced"
LOST_SUBSCRIPT = "subscript glyph(s) on this page appear as `*`"
CONTINUED = "**Table continued** — rendered in full at"
EMBEDDED = re.compile(r"\]\((\.\./assets/[^)]+)\)")


def load_page(bundle: Path, entry: dict) -> dict:
    payload = (bundle / entry["file"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
    return json.loads(payload)


def check_page(page: dict, text: str, chains: dict[str, dict],
               pages_dir: Path, plan: dict | None = None,
               bundle: Path | None = None,
               entries: dict[int, dict] | None = None) -> list[str]:
    bad = []
    # previewはGitHub Pages（Jekyll）で配る。Liquidが特別扱いする並びが原本の
    # 本文（コード例の入れ子初期化など）から流れ込むとPagesのビルドごと落ちる
    # ので、出た時点でここで捕まえる（本体repo側は check_docs.py が見る）。
    for sequence in ("{" + "{", "{" + "%"):
        if sequence in text:
            bad.append(f"p{page['number']}: Liquid-breaking sequence {sequence!r} "
                       "in the markdown -- Pages build would fail")
    position = 0
    tables = {item["id"]: item for item in page["tables"]}
    lines = {item["id"]: item for item in page["lines"]}
    # bit図: 番号行は表のヘッダへ畳むか合成テーブルの位置になる——exporterと
    # 同じ計画を使う（tables=表へ畳む・synth=罫線無し合成・skip=本文から消す行）。
    plan = plan or {"tables": {}, "synth": {}, "skip": set()}
    bitfields = plan["tables"]
    synth = plan["synth"]
    consumed_lines = plan["skip"]   # cross_note行もskipに入る（本文からは番号→次ページ印）
    cross = plan.get("cross", {})
    # exporterと同じく、通常表の端に降ってきたCJK/句読点グリフをgeometryで落とす。
    # 候補セルがあるときだけ開く（遅延）。
    _geo: dict[int, list[dict]] = {}

    def chars_for(page_number: int | None = None) -> list[dict]:
        pg = page["number"] if page_number is None else page_number
        if pg not in _geo:
            _geo[pg] = (export_markdown.load_geometry(bundle, entries[pg])["chars"]
                        if bundle is not None and entries and pg in entries else [])
        return _geo[pg]

    def expect(needle: str, what: str) -> None:
        nonlocal position
        if not needle:
            return
        at = text.find(needle, position)
        if at < 0:
            where = "missing" if text.find(needle) < 0 else "out of order"
            bad.append(f"p{page['number']} {what}: {where}: {needle[:60]!r}")
        else:
            position = at + len(needle)

    for item in page["reading_order"]:
        if item["type"] == "table":
            info = chains[item["id"]]
            if not info["start"]:
                # 続き断片は開始ページで結合済み。ここには可視のポインタが要る。
                expect(CONTINUED, f"table {item['id']} continuation pointer")
                continue
            record = info["merged"] or tables[item["id"]]
            if info["merged"]:
                # exporterと同じ畳み込みを見る（境界で割れたセルは前セルへ連結
                # 済み・継続セルは空）。continuationセルは`_folded`で空になり
                # expect("")がスキップ、前セルには連結後textが入る。
                logical_tables.fold_boundary_spills(record)
            if item["id"] in bitfields:
                # bit番号をヘッダへ、縦割れ名を連結——exporterと同じ表を見る。
                line_id, centers = bitfields[item["id"]]
                logical_tables.apply_bitfield(record, lines[line_id], centers)
            elif item["id"] in cross:
                # 前ページの番号行で組み直した箱（ページ跨ぎ分割）。
                logical_tables.apply_bitfield(record, None, cross[item["id"]])
            else:
                # 通常表: exporterと同じ変換（ヘッダ折り返しの畳み込み・境界二重取り除去）を見る。
                logical_tables.fold_header_wrap(record)
                logical_tables.strip_boundary_dupes(record)
                if logical_tables.has_edge_newline(record) or logical_tables.has_short_edge(record):
                    logical_tables.strip_straddling_dupes(record, chars_for)
            for cell in record["cells"]:
                # exporterと同じ表示（折り返し結合・改行は<br>）で検査する
                expect(export_markdown.cell_html(cell["text"]),
                       f"table {item['id']} cell")
        elif item["type"] == "line":
            if item["id"] in synth:
                # 罫線の無いbit図: 番号行の位置で合成テーブルを見る。
                for cell in synth[item["id"]]["cells"]:
                    expect(export_markdown.cell_html(cell["text"]),
                           f"bitfield {item['id']} cell")
                continue
            if item["id"] in consumed_lines:
                if item["id"] in plan.get("caption_cont", set()):
                    # 折り返した表題の続き行（`+ RISC-V3F)`）は本文から消えるが、`<caption>`の
                    # 中に全文として出ていなければならない。順序は問わず**存在だけ**見る——
                    # skipにしただけでは「表題も1行目・本文からも消えた」を検出できなかった
                    # （H417DS0.en p99、ページ跨ぎ結合表で_caption_fullが落ちていた）。
                    body = html.escape(export_markdown.pua_normalize(lines[item["id"]]["text"]).strip())
                    if body and text.find(body) < 0:
                        bad.append(f"p{page['number']} caption continuation {item['id']}: "
                                   f"missing from <caption>: {body[:60]!r}")
                continue   # bit番号行/フィールド行は表へ畳んだ
            line = lines[item["id"]]
            if line["bbox"][3] - line["bbox"][1] < 0.5:
                continue   # 高さ0の退化行（重複見出しのghost）——exporterと同じくskip。
            body = export_markdown.pua_normalize(line["text"])
            if line.get("role") == "list-item":
                # exporterと同じく行頭bulletを落とす（`- `の二重を消す）。
                body = export_markdown.strip_leading_bullet(body)
            expect(html.escape(body), f"{line.get('role')} {item['id']}")
            if (line.get("role") not in ("header", "footer")
                    and figure_captions.caption_match(line["text"])):
                # captionの直後には、描画済みの図（実ファイルがあること）か、
                # 「再現していない」の可視の印のどちらかが要る。
                window = text[position:position + 400]
                embed = EMBEDDED.search(window)
                if embed:
                    if not (pages_dir / embed.group(1)).resolve().exists():
                        bad.append(f"p{page['number']} {item['id']}: embedded asset "
                                   f"missing on disk: {embed.group(1)}")
                elif NOT_REPRODUCED not in window:
                    bad.append(f"p{page['number']} {item['id']}: figure caption with "
                               "neither a rendered image nor a notice")
    return bad


def lost_glyphs(bundle: Path, entry: dict, page: dict) -> int:
    """添字が`*`に化けたglyphの数（`*`が無いページはgeometryを開かない）。"""
    if "*" not in page["text"]:
        return 0
    payload = gzip.decompress((bundle / entry["geometry_file"]).read_bytes())
    if hashlib.sha256(payload).hexdigest() != entry["geometry_sha256"]:
        raise SystemExit(f"{bundle}/{entry['geometry_file']}: hash differs from manifest")
    return lost_subscripts.lost_subscript_count(json.loads(payload)["chars"])


def check_document(bundle: Path, markdown: Path, limit: int = 5) -> int:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    pages = [load_page(bundle, entry) for entry in manifest["pages"]]
    entry_of = {page["number"]: entry for entry, page in zip(manifest["pages"], pages)}
    chains = logical_tables.document_chains(pages)
    plans = export_markdown.document_bitfields(bundle, manifest, pages)
    bad: list[str] = []
    for entry, page in zip(manifest["pages"], pages):
        md = markdown / "pages" / f"{page['number']:04d}.md"
        if not md.exists():
            bad.append(f"p{page['number']}: markdown page missing")
            continue
        text = md.read_text(encoding="utf-8")
        bad.extend(check_page(page, text, chains, markdown / "pages",
                              plans[page["number"]], bundle, entry_of))
        if lost_glyphs(bundle, entry, page) and LOST_SUBSCRIPT not in text:
            bad.append(f"p{page['number']}: lost-subscript glyphs without a "
                       "visible notice")
    if bad:
        print(f"[{bundle.name}] {len(bad)} parity issue(s):", file=sys.stderr)
        for line in bad[:limit]:
            print(f"    {line}", file=sys.stderr)
        if len(bad) > limit:
            print(f"    ... {len(bad) - limit} more", file=sys.stderr)
    return len(bad)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundle", type=Path, nargs="?")
    ap.add_argument("markdown", type=Path, nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
        import convert_all  # noqa: PLC0415
        total = bad_docs = issues = 0
        for job in convert_all.targets():
            total += 1
            n = check_document(BUNDLES / job["name"], MARKDOWN / job["name"])
            if n:
                bad_docs += 1
                issues += n
        print(f"{total} documents checked: "
              f"{total - bad_docs} clean, {bad_docs} with {issues} issue(s)")
        return 1 if issues else 0
    if not (args.bundle and args.markdown):
        ap.error("give bundle and markdown paths, or --all")
    return 1 if check_document(args.bundle, args.markdown, limit=20) else 0


if __name__ == "__main__":
    raise SystemExit(main())
