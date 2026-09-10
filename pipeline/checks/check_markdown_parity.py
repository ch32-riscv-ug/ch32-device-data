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
4. 添字が`*`になっているglyph（**原本の版面が`*`を刷っている**。
   `pipeline/common/lost_subscripts`）を持つページの冒頭に、その旨の警告があること

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
               entries: dict[int, dict] | None = None,
               figure_regions: list | tuple = (),
               next_page: dict | None = None,
               doc_vocab: dict[str, int] | None = None) -> list[str]:
    bad = []
    # previewはGitHub Pages（Jekyll）で配る。Liquidが特別扱いする並びが原本の
    # 本文（コード例の入れ子初期化など）から流れ込むとPagesのビルドごと落ちる
    # ので、出た時点でここで捕まえる（本体repo側は check_docs.py が見る）。
    for sequence in ("{" + "{", "{" + "%"):
        if sequence in text:
            bad.append(f"p{page['number']}: Liquid-breaking sequence {sequence!r} "
                       "in the markdown -- Pages build would fail")
    position = 0
    # exporterと同じ「そのページの正しいフィールド名」（記述表のName列）。
    description_names = logical_tables.description_names(page, chains, next_page)
    fragment_ids = logical_tables.fragment_tables(page)
    # exporterが繋ぐ「境界で割れた視覚行」——右半分は先頭の重複文字を除いた残りが、左半分の
    # 直後に出る。順序照合なので右半分の全文（重複文字込み）を探すと1文字ぶん前で外れる。
    vocab = export_markdown.page_vocabulary(page)
    doc_vocab = doc_vocab if doc_vocab is not None else {}
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

    # exporterと同じ読み順（拾い直した図ラベルを含む`reading_stream`）を歩く。
    for item in logical_tables.reading_stream(page, figure_regions):
        if item["type"] == "table":
            info = chains[item["id"]]
            if not info["start"]:
                # 続き断片は開始ページで結合済み。ここには可視のポインタが要る。
                expect(CONTINUED, f"table {item['id']} continuation pointer")
                continue
            if item["id"] in fragment_ids:
                continue   # exporterと同じく、重なりセルの残骸だけの1列表は描かない
            record = info["merged"] or tables[item["id"]]
            logical_tables.drop_phantom_fragment_rows(record)
            if info["merged"]:
                # exporterと同じ畳み込みを見る（境界で割れたセルは前セルへ連結
                # 済み・継続セルは空）。continuationセルは`_folded`で空になり
                # expect("")がスキップ、前セルには連結後textが入る。
                # **重複グリフの除去を先に**——刷り直された見出しを落とすと、その見出しから
                # 隣のデータセルへ降りた文字（`I/O电平`の`平`が`平\nFT`）の出所が消えてしまい、
                # `平FT`という値になっていた（V203DS0.zh p27。全面見直しの検証で発見）。
                # 幽霊列（断片の境界の和集合が生む余分な1列）を先に消す。
                logical_tables.snap_ghost_columns(record)
                # 続きの断片に欠けた最外列（レジスタ名・`Bit`・`Reset value`）を、先頭断片の
                # 列境界とそのページのgeometryで埋める（`R32_USART3_GPR`が名無しだった）。
                logical_tables.recover_chain_columns(record, chars_for)
                # 斜めに割れた角セル/折り返し見出しの二重出力を先に落とす——行の列数が
                # 揃わないと以降の畳み込みも列を数え違える。
                logical_tables.strip_duplicated_span_lines(record)
                logical_tables.strip_boundary_dupes(record, chars_for)
                if (logical_tables.has_edge_newline(record)
                        or logical_tables.has_short_edge(record)):
                    logical_tables.strip_straddling_dupes(record, chars_for)
                logical_tables.drop_repeated_headers(record)
                # 境界行のreset列に降りた行端グリフを先に消す——空になれば続き行として畳める。
                logical_tables.clean_reset_column(record)
                logical_tables.fold_boundary_spills(record)
                # ページ境界で切れた縦の結合セルを続きの行まで伸ばす（列ずれを直す）。
                logical_tables.extend_boundary_spans(record)
                # 空になった境界行を消す（余分なrowspanと空`<tr>`を出さない）。
                logical_tables.drop_empty_boundary_rows(record)
            if item["id"] in bitfields:
                # bit番号をヘッダへ、縦割れ名を連結——exporterと同じ表を見る。
                line_id, centers = bitfields[item["id"]]
                logical_tables.apply_bitfield(record, lines[line_id], centers)
                logical_tables.fix_doubled_names(record, description_names)
            elif item["id"] in cross:
                # 前ページの番号行で組み直した箱（ページ跨ぎ分割）。
                logical_tables.apply_bitfield(record, None, cross[item["id"]])
                logical_tables.fix_doubled_names(record, description_names)
            else:
                # 通常表: exporterと同じ変換（ヘッダ折り返しの畳み込み・境界二重取り除去）を見る。
                logical_tables.strip_duplicated_span_lines(record)
                logical_tables.fold_header_wrap(record)
                logical_tables.strip_boundary_dupes(record, chars_for)
                if logical_tables.has_edge_newline(record) or logical_tables.has_short_edge(record):
                    logical_tables.strip_straddling_dupes(record, chars_for)
                logical_tables.clean_reset_column(record)
                if logical_tables.has_subscript_shape(record):
                    logical_tables.reattach_cell_subscripts(record, chars_for)
            listy = logical_tables.is_list_table(record)
            # exporterはグリッドを行→列の順に描く。bundleのセル列はrowspanセルが先に並ぶことが
            # あり（繰り返し見出し行の`Pin name`が`H417WEU6`より前）、そのまま照合すると
            # 「順序が違う」と誤検出した（H417DS0.en p34で1,037件）。
            for cell in sorted(record["cells"], key=lambda c: (c["row_start"], c["column_start"])):
                # exporterと同じ表示（折り返し結合・改行は<br>・一覧表は項目改行）で検査する
                expect(export_markdown.cell_html(cell["text"],
                                                 list_cell=listy and cell["row_start"] > 0,
                                                 vocab=vocab, doc_vocab=doc_vocab),
                       f"table {item['id']} cell")
        elif item["type"] == "line":
            if item["id"] in synth:
                # 罫線の無いbit図: 番号行の位置で合成テーブルを見る。
                for cell in synth[item["id"]]["cells"]:
                    expect(export_markdown.cell_html(cell["text"], vocab=vocab,
                                                     doc_vocab=doc_vocab),
                           f"bitfield {item['id']} cell")
                continue
            if item["id"] in consumed_lines:
                if item["id"] in plan.get("caption_cont", set()):
                    # 折り返した表題の続き行（`+ RISC-V3F)`）は本文から消えるが、`<caption>`の
                    # 中に全文として出ていなければならない。順序は問わず**存在だけ**見る——
                    # skipにしただけでは「表題も1行目・本文からも消えた」を検出できなかった
                    # （H417DS0.en p99、ページ跨ぎ結合表で全文が落ちていた）。converter 1.8.0で
                    # 全文は`caption.text`そのものになったが、検査はそのまま残す。
                    body = html.escape(lines[item["id"]]["text"].strip())
                    if body and text.find(body) < 0:
                        bad.append(f"p{page['number']} caption continuation {item['id']}: "
                                   f"missing from <caption>: {body[:60]!r}")
                continue   # bit番号行/フィールド行は表へ畳んだ
            line = lines[item["id"]]
            if line["bbox"][3] - line["bbox"][1] < 0.5:
                continue   # 高さ0の退化行（重複見出しのghost）——exporterと同じくskip。
            # 文字の正規化と下付き復元はconverterが済ませている（1.8.0）。
            body = line["text"]
            if line.get("role") == "list-item":
                # exporterと同じく行頭bulletを落とす（`- `の二重を消す）。
                body = export_markdown.strip_leading_bullet(body)
            if line.get("merged_into"):
                continue   # 割れた視覚行の右半分（converterが左半分へ繋いである）
            expect(export_markdown.escape_body(body), f"{line.get('role')} {item['id']}")
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
    doc_vocab = export_markdown.document_vocabulary(pages)
    plans = export_markdown.document_bitfields(bundle, manifest, pages)
    # exporterと同じ図領域（描画済みassetのbbox）。拾い直す行は図の中だけなので、
    # parityも同じ領域を見ないと「本文から消えた」と誤検出する。
    regions: dict[int, list] = {}
    assets_file = markdown / "assets.json"
    if assets_file.exists():
        payload = json.loads(assets_file.read_text(encoding="utf-8"))
        items = payload.get("assets", payload) if isinstance(payload, dict) else payload
        for asset in (items.values() if isinstance(items, dict) else items):
            regions.setdefault(asset["page"], []).append(asset["bbox"])
    bad: list[str] = []
    for index, (entry, page) in enumerate(zip(manifest["pages"], pages)):
        md = markdown / "pages" / f"{page['number']:04d}.md"
        if not md.exists():
            bad.append(f"p{page['number']}: markdown page missing")
            continue
        text = md.read_text(encoding="utf-8")
        bad.extend(check_page(page, text, chains, markdown / "pages",
                              plans[page["number"]], bundle, entry_of,
                              regions.get(page["number"], []),
                              pages[index + 1] if index + 1 < len(pages) else None,
                              doc_vocab))
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
