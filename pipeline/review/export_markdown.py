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
import gzip
import hashlib
import html
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
import figure_captions  # noqa: E402
import logical_tables  # noqa: E402
import lost_subscripts  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
DEFAULT_OUT = REPO / ".cache" / "structured-markdown"

LARGE_IMAGE = 40.0   # pt。これ以上の幅と高さを持つ画像は個別の占位を出す

# 各ページ冒頭に置く表の見た目。既定でセル中央寄せ（PDFに寄せる。ユーザー要望）、
# bit図は16列を等幅fixed＋自動折り返し。CSSに`{{`/`{%`が出ないよう1行1規則で書く
# （JekyllのLiquidが壊れる並びをparity検査が禁じている）。
PAGE_STYLE = "\n".join((
    "<style>",
    "table{border-collapse:collapse;margin:.6em 0}",
    "td,th{border:1px solid #bbb;padding:2px 7px;text-align:center;vertical-align:top}",
    "table.bitfield{table-layout:fixed;width:100%}",
    "table.bitfield td,table.bitfield th{word-break:break-word;font-size:.8em;padding:2px}",
    "</style>",
))


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


def load_geometry(bundle: Path, entry: dict) -> dict:
    payload = gzip.decompress((bundle / entry["geometry_file"]).read_bytes())
    if hashlib.sha256(payload).hexdigest() != entry["geometry_sha256"]:
        raise SystemExit(f"{bundle}/{entry['geometry_file']}: hash differs from manifest")
    return json.loads(payload)


def page_lost_subscripts(bundle: Path, entry: dict, page: dict) -> int:
    """このページで`*`に化けた添字glyphの数。`*`が無いページはgeometryを開かない。"""
    if "*" not in page["text"]:
        return 0
    return lost_subscripts.lost_subscript_count(load_geometry(bundle, entry)["chars"])


def bitfield_plan(bundle: Path, entry: dict, page: dict) -> dict[str, tuple[str, list]]:
    """{table_id: (bit番号line_id, bit中心)}。番号行のある表だけgeometryを開く。"""
    pairs = logical_tables.bitfield_pairs(page)
    if not pairs:
        return {}
    chars = load_geometry(bundle, entry)["chars"]
    lines = {l["id"]: l for l in page["lines"]}
    plan: dict[str, tuple[str, list]] = {}
    for table_id, line_id in pairs.items():
        centers = logical_tables.bit_number_centers(chars, lines[line_id])
        if centers:
            plan[table_id] = (line_id, centers)
    return plan


# Wingdings/Symbolフォントの記号がPUA（私用領域）のまま本文に出ている
# （fontで●等に見えるが文字コードは意味不明）。全コーパスで実測した5種を
# 対応する記号へ。原本の見た目に合わせる＝「差ゼロ」に近づく。
PUA_REPLACEMENTS = {
    "\uf06c": "●",   # Wingdings 0x6C: bullet (8824)
    "\uf06e": "■",   # Wingdings 0x6E: black square
    "\uf0b7": "•",   # Symbol 0xB7: bullet
    "\uf0b4": "×",   # Symbol 0xB4: multiply
    "\uf0b1": "±",   # Symbol 0xB1: plus-minus
}


def pua_normalize(text: str) -> str:
    for pua, real in PUA_REPLACEMENTS.items():
        if pua in text:
            text = text.replace(pua, real)
    return text


_JOIN_PUNCT = ":;.。；：,，、"


def cell_html(text: str) -> str:
    """セルの中身。物理行の切れ目（`\\n`）を、**折り返しか意図的な改行か**で
    出し分ける（前者は繋ぎ、後者は`<br>`）。完全な区別は原理的に不可能だが、
    行末・行頭の文字種で実用的に分けられる（狭いregisterセルで`USART1RST`が
    `USAR`/`T1`/`RST`に折り返される一方、MCO説明の`control:`/`100:…`は項目改行）:

    - 前行が句読点（`:;.,`等）で終わる → 意図的な改行（`<br>`）
    - 英字（小文字が絡む＝英単語）の折り返し → 空白で繋ぐ（`source is`+`greater`）
    - 識別子（大文字・数字）の折り返し → そのまま繋ぐ（`USAR`+`T1`=`USART1`）
    - それ以外は保守的に`<br>`
    """
    text = pua_normalize(text)
    parts = text.split("\n")
    if len(parts) == 1:
        return html.escape(text)
    result = html.escape(parts[0])
    for prev, cur in zip(parts, parts[1:]):
        pe = prev.rstrip()
        if not pe or not cur:
            sep = "<br>"
        elif pe[-1] in _JOIN_PUNCT:
            sep = "<br>"
        elif (pe[-1].isalpha() and pe[-1].islower()) or (cur[0].isalpha() and cur[0].islower()):
            sep = " "
        elif pe[-1].isalnum() and cur[0].isalnum():
            sep = ""
        else:
            sep = "<br>"
        result += sep + html.escape(cur)
    return result


def table_html(table: dict, url: str | None, number: int) -> str:
    columns = table.get("width") or table["column_count"]
    row_count = table["row_count"]
    grid: list[list[str | None]] = [[None for _ in range(columns)]
                                    for _ in range(row_count)]
    covered = [False] * row_count   # 上の行からrowspanで覆われている行
    for cell in table["cells"]:
        attrs = []
        if cell["row_end"] - cell["row_start"] > 1:
            attrs.append(f'rowspan="{cell["row_end"] - cell["row_start"]}"')
        if cell["column_end"] - cell["column_start"] > 1:
            attrs.append(f'colspan="{cell["column_end"] - cell["column_start"]}"')
        inner = cell_html(cell["text"])
        if cell.get("italic"):
            inner = f"<em>{inner}</em>"
        if cell.get("bold"):
            inner = f"<strong>{inner}</strong>"
        # セルは既定で中央寄せ（PDFに寄せる。ユーザー要望）だが、長い/複数行の
        # 説明セルは中央寄せだと逆に読みにくくPDFとも違うので左寄せに戻す。
        cell_text = cell["text"] or ""
        if len(cell_text) > 40 or "\n" in cell_text:
            attrs.append('style="text-align:left"')
        # 表の1行目はヘッダ（<th>。ブラウザが太字＋中央寄せ）。原本の見出し行
        # （Bit/Name/Access…）がそのまま見出しになる。ヘッダの無い表（ビット図）
        # でも実害は小さい。continuation断片はrow_start>0なので<td>のまま。
        tag = "th" if cell["row_start"] == 0 else "td"
        grid[cell["row_start"]][cell["column_start"]] = (
            f"<{tag}" + ("".join(" " + a for a in attrs)) + ">"
            + inner + f"</{tag}>")
        for r in range(cell["row_start"] + 1, cell["row_end"]):
            covered[r] = True
    # fold_boundary_spillsが継続セルを消した行は、他の列の空セルだけが残る。
    # rowspanに覆われていなければ落とす（跨ぐrowspanがあれば高さがずれるので
    # 残す。安全側）。元から空の行には触れない——消したと分かっている行だけ。
    folded_rows = set(table.get("_folded_rows", ()))
    rows = ["<tr>" + "".join(cell or "" for cell in row) + "</tr>"
            for r, row in enumerate(grid)
            if covered[r] or r not in folded_rows]
    # captionを持つ表だけが`<caption>`を出す。caption行の無い表（レジスタの
    # ビット図・説明表）は、原本でも表番号が振られていない——continuation継承で
    # 前ページの表番号（logical_id）を借りて名乗ると、無関係な`table-3-1@1`が
    # 6つ並ぶ（ユーザー指摘）。内部IDは追跡用にコメントへ残す。
    caption = table["caption"]["text"] if table["caption"] else None
    cap_html = f"<caption>{html.escape(caption)}</caption>" if caption else ""
    span = table.get("parts")
    parts = []
    if table["issues"]:
        where = (f"the PDF, pp.{span[0][0]}-{span[-1][0]}" if span
                 else f"the PDF, p.{number}")
        parts.append(f"> ⚠ Table extraction recorded {len(table['issues'])} issue(s) "
                     f"(overlapping merged cells); verify against "
                     f"{page_link(url, number, where)}.\n")
    lid = table["logical_id"]
    origin = (f"<!-- {table['id']} ({lid}) pages {span[0][0]}-{span[-1][0]} -->" if span
              else f"<!-- {table['id']} ({lid}) -->")
    # レジスタのbit図は16列を等幅にして、狭い1-bit列で名前が自動折り返しになるよう
    # table-layout:fixed（class="bitfield"）＋等幅colgroupを付ける。
    if table.get("_bitfield"):
        colgroup = ("<colgroup>"
                    + f'<col style="width:{100 / columns:.4f}%">' * columns
                    + "</colgroup>")
        open_tag = '<table class="bitfield">'
    else:
        colgroup = ""
        open_tag = "<table>"
    parts.append(f"{origin}\n{open_tag}{cap_html}{colgroup}{''.join(rows)}</table>")
    return "\n".join(parts)


def render_page(page: dict, url: str | None, chains: dict[str, dict],
                assets: dict[str, dict], page_count: int,
                lost_glyphs: int = 0,
                bitfields: dict[str, tuple[str, list]] | None = None) -> str:
    tables = {item["id"]: item for item in page["tables"]}
    lines = {item["id"]: item for item in page["lines"]}
    images = {item["id"]: item for item in page["images"]}
    number = page["number"]
    # レジスタのbit図: 「31 30 … 16」の番号行を次表のヘッダへ畳む。番号行は
    # 表に吸収されるので本文からは消す（parity検査も同じ集合を消す）。
    bitfields = bitfields or {}
    consumed_lines = {line_id for line_id, _ in bitfields.values()}
    # このページで画像として描画済みの図領域。中にある行・表は、画像が既に
    # 見せているので**可視出力から畳んでコメントに落とす**（図中ラベルが
    # 本文として図の下に重複して出ていた——preview初公開でユーザーが発見）。
    figure_regions = [a["bbox"] for a in assets.values() if a["page"] == number]
    # captionを持たない独立asset（回転文字入りのgraphicsクラスタ＝封装図・
    # 引脚配置図）。領域に最初に入った時点で画像を先に出す——折りたたみの
    # 「figure above」が成立するように。
    standalone = {key: a for key, a in assets.items()
                  if a["page"] == number and "-cluster-" in key}
    emitted: set[str] = set()

    def in_figure(bbox: list[float]) -> bool:
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3]
                   for b in figure_regions)

    def emit_standalone(bbox: list[float], sink: list[str]) -> None:
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        for key, a in standalone.items():
            if key in emitted:
                continue
            b = a["bbox"]
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                emitted.add(key)
                sink.extend(("", f"![figure p.{number}](../{a['file']}) "
                             f"<!-- {key} uncaptioned graphics, rendered from "
                             f"the PDF; verify at {url or 'the PDF'}#page={number} -->",
                             ""))
    # 前後ページのリンク。GitHub Pagesにはファイル一覧が無いので、これが
    # 唯一の移動手段になる（github.comのファイルビューでは左のリストでも動ける）。
    nav = ([f"[← p.{number - 1}]({number - 1:04d}.md)"] if number > 1 else [])
    nav.append("[index](../README.md)")
    nav.append(page_link(url, number, f"PDF p.{number}"))
    if number < page_count:
        nav.append(f"[p.{number + 1} →]({number + 1:04d}.md)")
    output = [f"<!-- source-page: {number} -->", PAGE_STYLE,
              f"<sub>{' · '.join(nav)}</sub>", ""]
    cids = page["text"].count("(cid:")
    if cids:
        output += [f"> ⚠ {cids} glyph(s) on this page could not be decoded to text "
                   f"(they appear as `(cid:N)`); read "
                   f"{page_link(url, number, f'the PDF, p.{number}')}.", ""]
    if lost_glyphs:
        output += [f"> ⚠ {lost_glyphs} subscript glyph(s) on this page appear as `*` "
                   "because the PDF's text layer maps them to `*` (broken ToUnicode); "
                   "the printed page shows the real subscripts -- read "
                   f"{page_link(url, number, f'the PDF, p.{number}')}.", ""]
    # 描画済みの図領域の**中**にある行・表・画像は、図の下へそのまま流すと
    # 「同じ内容が画像と文字で二重に出る」（preview初公開でユーザーが発見）。
    # 消すのではなく（検索・コピーに役立つ——ユーザー要望）、**「図から
    # パースした文字」と分かる折りたたみにまとめて**図の直後に置く。
    figure_text: list[str] = []

    def flush_figure_text() -> None:
        if figure_text:
            output.extend(("", "<details><summary>🖼 Text parsed from the "
                           "figure above</summary>", ""))
            output.extend(figure_text)
            output.extend(("", "</details>", ""))
            figure_text.clear()

    for item in page["reading_order"]:
        inside = in_figure(item["bbox"])
        if not inside:
            flush_figure_text()
        else:
            emit_standalone(item["bbox"], output)
        if item["type"] == "table":
            info = chains[item["id"]]
            if not info["start"]:
                pointer = (f"> ⬆ **Table continued** — rendered in full at "
                           f"[page {info['start_page']}]"
                           f"({info['start_page']:04d}.md). <!-- {item['id']} -->")
                (figure_text if inside else output).extend(("", pointer, ""))
                continue
            record = info["merged"] or tables[item["id"]]
            if info["merged"]:
                logical_tables.fold_boundary_spills(record)
            if item["id"] in bitfields:
                line_id, centers = bitfields[item["id"]]
                logical_tables.apply_bitfield(record, lines[line_id], centers)
            (figure_text if inside else output).extend(
                ("", table_html(record, url, number), ""))
            continue
        if item["type"] == "image":
            image = images[item["id"]]
            asset = assets.get(image["id"])
            x0, top, x1, bottom = image["bbox"]
            if asset:
                output.extend(("", f"![image p.{number}](../{asset['file']}) "
                               f"<!-- {image['id']} rendered from the PDF -->", ""))
            elif inside:
                # 描画済みの図領域の中の画像。図の埋め込みが既に見せている。
                figure_text.append(f"<!-- image: {image['id']} inside the figure -->")
            elif x1 - x0 >= LARGE_IMAGE and bottom - top >= LARGE_IMAGE:
                output.extend(("", f"> 🖼 **Image not reproduced** "
                               f"({x1 - x0:.0f}×{bottom - top:.0f} pt) — see "
                               f"{page_link(url, number, f'the PDF, p.{number}')}."
                               f" <!-- {image['id']} -->", ""))
            else:
                output.append(f"<!-- image: {image['id']} bbox={image['bbox']} -->")
            continue
        if item["id"] in consumed_lines:
            continue   # bit番号行は次表のヘッダへ畳んだ（bitfield）
        line = lines[item["id"]]
        role = line.get("role", "paragraph")
        text = html.escape(pua_normalize(line["text"]))
        # 本文・箇条書きの強調（原本のfontから。見出しは`#`で既に強調済み）。
        if role in ("paragraph", "list-item"):
            if line.get("italic"):
                text = f"<em>{text}</em>"
            if line.get("bold"):
                text = f"<strong>{text}</strong>"
        if role in ("header", "footer"):
            # 図領域がページ下端に届くとfooterが領域内に入る。順序を保つため
            # コメントも同じ入れ物へ。
            (figure_text if inside else output).append(f"<!-- {role}: {text} -->")
            continue
        caption = figure_captions.caption_match(line["text"])
        if inside and not caption:
            # 図中のラベル。役割（heading等）は図の外の文脈なので飾らない。
            figure_text.append(text + "  ")
            continue
        if caption:
            asset = assets.get(line["id"])
            if asset:
                # asset rendererが図領域を描画済み。captionの下に埋め込む。
                output.extend(("", text + "  ",
                               f"![{html.escape(caption.group(0))}]"
                               f"(../{asset['file']}) "
                               f"<!-- rendered from the PDF; verify at "
                               f"{url or 'the PDF'}#page={number} -->", ""))
            else:
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
    flush_figure_text()
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
    assets: dict[str, dict] = {}
    assets_path = out / "assets.json"
    if assets_path.exists():
        record = json.loads(assets_path.read_text(encoding="utf-8"))
        if record["source_sha256"] == source["sha256"]:
            assets = record["assets"]
        else:
            print(f"{assets_path}: stale (different original); ignoring -- "
                  "re-run pipeline/review/render_assets.py", file=sys.stderr)
    links = []
    for entry, page in zip(manifest["pages"], pages):
        name = f"{page['number']:04d}.md"
        (pages_dir / name).write_text(
            render_page(page, url, chains, assets, len(pages),
                        page_lost_subscripts(bundle, entry, page),
                        bitfield_plan(bundle, entry, page)),
            encoding="utf-8")
        links.append(f"- [page {page['number']}](pages/{name})")
    (out / "README.md").write_text(
        f"# {source['document']} ({source['language']})\n\n"
        f"- type: `{source['document_type']}`\n"
        f"- source SHA-256: `{source['sha256']}`\n"
        + (f"- original: <{url}>\n" if url else "")
        + "\nHeaders and footers are folded into HTML comments. Figures are rendered\n"
        "from the PDF where the asset renderer found their region; a caption whose\n"
        "figure could not be located carries a visible notice instead, and every\n"
        "page links back to the PDF. A table that spans pages is rendered in full\n"
        "on the page where it starts; the following pages carry a visible pointer.\n"
        "Where the PDF's own text layer maps subscript glyphs to `*` (broken\n"
        "ToUnicode), the page starts with a notice -- the printed page shows the\n"
        "real subscripts.\n\n"
        + "\n".join(links) + "\n", encoding="utf-8")
    return out


def viewer_html(docs: list[dict]) -> str:
    """目視確認用の左右同期ビュアー（previewリポジトリのGitHub Pages専用）。

    左に原本PDF（ブラウザ内蔵viewer・`#page=N`で頭出し）、右にこの出力の
    同じページ（Jekyllが`pages/NNNN.md`→`.html`に描画したもの）。ページ移動は
    両側へ同時に効く（ボタン・数字入力・←→キー）。状態はURLのhashに残るので、
    気になったページをそのまま共有できる。PDF側はページ移動のたびに**iframe
    要素ごと作り直す**——fragmentだけの変更では内蔵viewerが動かず、かつ
    `about:blank`を挟む二段セットはナビゲーションが競合してページの偶奇で
    交互に失敗した（ユーザー報告）。要素の差し替えなら必ず新規ナビゲーションに
    なる。PDF本体はブラウザがcacheする。
    """
    payload = json.dumps(
        [{"name": d["name"], "pages": d["pages"], "pdf": d["pdf"]} for d in docs],
        ensure_ascii=False)
    return """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDF × rendering — side-by-side viewer</title>
<style>
  body { margin: 0; font: 14px system-ui, sans-serif; }
  header { display: flex; gap: .5em; align-items: center; padding: 6px 8px;
           background: #222; color: #eee; flex-wrap: wrap; }
  header select, header input, header button { font: inherit; }
  #page { width: 5em; }
  main { display: flex; height: calc(100vh - 44px); }
  main > * { border: 0; flex: 1 1 50%; height: 100%; }
  #pdfpane { display: flex; }
  #pdfpane iframe { border: 0; flex: 1 1 100%; height: 100%; }
  a { color: #9cf; }
</style>
<header>
  <select id="doc"></select>
  <button id="prev" title="PageUp / ←">◀</button>
  <input id="page" type="number" min="1" value="1">
  <span>/ <span id="total">?</span></span>
  <button id="next" title="PageDown / →">▶</button>
  <label><input type="checkbox" id="swap"> swap</label>
  <a id="mdlink" href="#" target="_blank">open page</a>
  <a href="./">index</a>
</header>
<main id="panes">
  <div id="pdfpane" title="original PDF"></div>
  <iframe id="md" title="structured rendering"></iframe>
</main>
<script>
const DOCS = __DOCS__;
const sel = document.getElementById("doc");
const pageBox = document.getElementById("page");
const total = document.getElementById("total");
const pdfpane = document.getElementById("pdfpane");
const md = document.getElementById("md");
const mdlink = document.getElementById("mdlink");
for (const d of DOCS) {
  const o = document.createElement("option");
  o.value = d.name; o.textContent = d.name + " (" + d.pages + "p)";
  sel.appendChild(o);
}
function state() {
  const d = DOCS[sel.selectedIndex];
  const p = Math.min(Math.max(1, pageBox.valueAsNumber || 1), d.pages);
  return { d, p };
}
function update(pushHash = true) {
  const { d, p } = state();
  pageBox.value = p; pageBox.max = d.pages; total.textContent = d.pages;
  const mdUrl = d.name + "/pages/" + String(p).padStart(4, "0") + ".html";
  md.src = mdUrl; mdlink.href = mdUrl;
  // 内蔵PDF viewerはfragmentだけの変更では動かず、about:blankトグルは
  // ナビゲーションが競合してページの偶奇で交互に失敗する。iframe要素を
  // 毎回作り直せば必ず新規ナビゲーションになる。
  const frame = document.createElement("iframe");
  frame.title = "original PDF";
  frame.src = d.pdf + "#page=" + p;
  pdfpane.replaceChildren(frame);
  if (pushHash)
    history.replaceState(null, "", "#doc=" + encodeURIComponent(d.name) + "&p=" + p);
}
function move(delta) {
  pageBox.value = (pageBox.valueAsNumber || 1) + delta;
  update();
}
sel.addEventListener("change", () => { pageBox.value = 1; update(); });
pageBox.addEventListener("change", () => update());
document.getElementById("prev").addEventListener("click", () => move(-1));
document.getElementById("next").addEventListener("click", () => move(1));
document.getElementById("swap").addEventListener("change", (e) => {
  document.getElementById("panes").style.flexDirection =
    e.target.checked ? "row-reverse" : "row";
});
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.key === "ArrowLeft" || e.key === "PageUp") { move(-1); e.preventDefault(); }
  if (e.key === "ArrowRight" || e.key === "PageDown") { move(1); e.preventDefault(); }
});
const hash = new URLSearchParams(location.hash.slice(1));
const wanted = hash.get("doc");
if (wanted) {
  const at = DOCS.findIndex((d) => d.name === wanted);
  if (at >= 0) { sel.selectedIndex = at; pageBox.value = +(hash.get("p") || 1); }
}
update(false);
</script>
""".replace("__DOCS__", payload)


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
        done = []
        viewer_docs = []
        for job in convert_all.targets():
            export(BUNDLES / job["name"], args.out, urls)
            manifest = json.loads((BUNDLES / job["name"] / "manifest.json")
                                  .read_text(encoding="utf-8"))
            done.append((job["document_type"], job["name"],
                         manifest["source"]["page_count"]))
            source = manifest["source"]
            viewer_docs.append({
                "name": job["name"],
                "pages": manifest["source"]["page_count"],
                "pdf": urls.get((source["document"], source["language"]), ""),
            })
        # previewリポジトリ（GitHub Pages）のトップになるindex。
        kinds = ("datasheet", "reference-manual", "core-manual",
                 "package-drawing", "other")
        lines = ["# CH32 structured documents (preview)", "",
                 "Regenerable rendering of the WCH PDFs -- see",
                 "[ch32-device-data](https://github.com/ch32-riscv-ug/ch32-device-data)",
                 "`pipeline/review/`. Headers/footers are folded into comments,",
                 "page-spanning tables are joined, figures are rendered from the PDF,",
                 "and every known gap is marked in place.", "",
                 "**[Side-by-side viewer](viewer.html)** -- the original PDF and this",
                 "rendering on the same page, with synchronized page navigation",
                 "(GitHub Pages only).", ""]
        for kind in kinds:
            docs = sorted(name for k, name, _ in done if k == kind)
            if not docs:
                continue
            lines += [f"## {kind}", ""]
            lines += [f"- [{name}]({name}/) "
                      f"({next(p for k, n, p in done if n == name)} pages)"
                      for name in docs]
            lines.append("")
        (args.out / "README.md").write_text("\n".join(lines), encoding="utf-8")
        (args.out / "viewer.html").write_text(
            viewer_html(viewer_docs), encoding="utf-8")
        print(f"{len(done)} documents -> {args.out}", file=sys.stderr)
        return 0
    if not args.bundle:
        ap.error("give a bundle path or --all")
    print(export(args.bundle, args.out, urls))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
