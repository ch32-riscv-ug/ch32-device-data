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
import re
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

# 各ページ冒頭に置く表の見た目。**全テーブルを同じ横幅に**（width:100%＋max-width上限。
# ユーザー要望——レジスタごとに幅が変わるのを揃える）、既定でセル中央寄せ（PDFに寄せる）、
# bit図は16列を等幅fixed＋自動折り返し。CSSに`{{`/`{%`が出ないよう1行1規則で書く
# （JekyllのLiquidが壊れる並びをparity検査が禁じている）。
# GitHub Pagesのテーマが`.markdown-body table{display:block;width:100%;overflow:auto}`
# （詳細度0,1,1）で素の`table`規則に勝ち、tableをblock化する。blockのtableは中身が内容幅に
# 縮むので、内容の広い表だけ100%に見えた。`display:table`＋`width`を`!important`で取り戻す。
PAGE_STYLE = "\n".join((
    "<style>",
    "table{border-collapse:collapse;margin:.6em 0;"
    "display:table!important;width:100%!important;max-width:960px!important}",
    "td,th{border:1px solid #bbb;padding:2px 7px;text-align:center;vertical-align:top}",
    "table.bitfield{table-layout:fixed}",
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


def bitfield_plan(bundle: Path, entry: dict, page: dict) -> dict:
    """レジスタbit図の描画計画。番号行のあるページだけgeometryを開く。

    返すもの:
      tables {table_id: (番号line_id, bit中心)}   直下に図テーブルがある版
      synth  {番号line_id: 描画用テーブル}          罫線が無く単一フィールドの版
      skip   set(line_id)                          本文から消す行（番号行・吸収した
                                                    フィールド行）。synthの番号行は
                                                    描画trigger（skipには入れない）
    """
    # 表のcaption行は`<caption>`として描かれる。同じ行がreading_orderにも残ると本文
    # 段落として二重に出る（「Table 4-1 …」が表の上と表内captionで2回。ユーザー指摘）。
    # caption行を本文から消す——parityも同じskipを読むので整合する。
    caption_skip: set[str] = set()
    caption_cont: set[str] = set()   # 続き行のid。parityは「本文から消えたが<caption>に在る」ことを別途見る
    for t in page["tables"]:
        if t.get("caption") and t["caption"].get("line_id"):
            caption_skip.add(t["caption"]["line_id"])
            # 折り返した表題の2行目（`+ RISC-V3F)`）も`<caption>`へ入れて本文から消す。
            full, used = logical_tables.caption_full(page, t)
            if used:
                t["_caption_full"] = full
                caption_skip.update(used)
                caption_cont.update(used)
    pairs = logical_tables.bitfield_pairs(page)
    singletons = logical_tables.bitfield_singletons(page)
    if not pairs and not singletons:
        return {"tables": {}, "synth": {}, "skip": set(caption_skip),
                "cross": {}, "cross_note": set(), "caption_cont": caption_cont}
    chars = load_geometry(bundle, entry)["chars"]
    lines = {l["id"]: l for l in page["lines"]}
    tables_by_id = {t["id"]: t for t in page["tables"]}
    tables: dict[str, tuple[str, list]] = {}
    skip: set[str] = set(caption_skip)
    for table_id, line_id in pairs.items():
        centers = logical_tables.bit_number_centers(chars, lines[line_id])
        if centers:
            tables[table_id] = (line_id, centers)
            skip.add(line_id)
            # 図セルの端で隣列へ二重取りされたグリフ（`ReservedR`等）をgeometryで落とす。
            logical_tables.strip_straddling_dupes(tables_by_id[table_id], chars)
    synth: dict[str, dict] = {}
    for number_id, field_id in singletons.items():
        centers = logical_tables.bit_number_centers(chars, lines[number_id])
        if centers:
            synth[number_id] = logical_tables.build_bitfield_singleton(
                lines[number_id], lines[field_id], centers)
            skip.add(field_id)
    return {"tables": tables, "synth": synth, "skip": skip, "caption_cont": caption_cont,
            "cross": {}, "cross_note": set()}


def document_bitfields(bundle: Path, manifest: dict, pages: list[dict]) -> dict[int, dict]:
    """ページごとのbit図計画に、ページ跨ぎの分割（番号行がページ末尾・箱が次ページ
    先頭）を足す。番号行のx中心は同一レジスタなので、ページを跨いでも箱のx配置に合う。

    箱ページ側の計画に`cross {box_id: 中心}`、番号行ページ側に`cross_note {line_id}`
    （消費して「次ページへ」の印を出す行）を積む。exporterとparityが同じ計画を使う。
    """
    plans = {page["number"]: bitfield_plan(bundle, entry, page)
             for entry, page in zip(manifest["pages"], pages)}
    entry_of = {page["number"]: entry
                for entry, page in zip(manifest["pages"], pages)}
    for prev, page in zip(pages, pages[1:]):
        if prev["number"] + 1 != page["number"]:
            continue
        plan_prev, plan_here = plans[prev["number"]], plans[page["number"]]
        hp = float(prev.get("height") or 792)
        hh = float(page.get("height") or 792)
        num_lines = sorted(
            (l for l in prev["lines"]
             if logical_tables.bit_numbers(l["text"]) and l["id"] not in plan_prev["skip"]
             and l["bbox"][3] > hp * 0.80),
            key=lambda l: l["bbox"][1])
        if not num_lines:
            continue
        used = set(plan_here["tables"]) | set(plan_here["cross"])
        top_boxes = sorted(
            (t for t in page["tables"]
             if t["bbox"][1] < hh * 0.20 and logical_tables._diagram_like(t)
             and t["id"] not in used),
            key=lambda t: t["bbox"][1])
        chars_prev = None
        for line, box in zip(num_lines, top_boxes):
            lx0, _, lx1, _ = line["bbox"]
            bx0, _, bx1, _ = box["bbox"]
            if min(lx1, bx1) - max(lx0, bx0) <= 0.6 * (lx1 - lx0):
                continue   # 同じレジスタなら横幅が重なる（別物への誤接続を防ぐ）
            if chars_prev is None:
                chars_prev = load_geometry(bundle, entry_of[prev["number"]])["chars"]
            centers = logical_tables.bit_number_centers(chars_prev, line)
            if not centers:
                continue
            plan_here["cross"][box["id"]] = centers
            plan_prev["skip"].add(line["id"])
            plan_prev["cross_note"].add(line["id"])
    return plans


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


def _undouble(part: str) -> str:
    """図ラベル等で全グリフが2回ずつ拾われた行（`OOSSCC__IINN`→`OSC_IN`、`CCPPOOLL==00`→
    `CPOL=0`）を畳む。PDFが太字風に同じ文字を重ね描きし、pdfplumberが両方を拾ったもの。
    条件: 空白なし・6文字以上・偶数長・全ての隣接ペアが同じ・**hex桁以外の文字を含む**
    （`0000FF`のような正当な16進値は偶然ペアになるので除外）。全corpus実測143件。"""
    s = part.strip()
    if (len(s) < 6 or len(s) % 2 or " " in s
            or any(s[i] != s[i + 1] for i in range(0, len(s), 2))
            or len(set(s)) < 2
            or all(ch in "0123456789abcdefABCDEF" for ch in s)):
        return part
    return part.replace(s, s[::2])


def pua_normalize(text: str) -> str:
    for pua, real in PUA_REPLACEMENTS.items():
        if pua in text:
            text = text.replace(pua, real)
    if "\n" in text:
        return "\n".join(_undouble(p) for p in text.split("\n"))
    return _undouble(text)


# convert.pyの見出し判定と同じ——番号見出し（`20.1 …`）・章見出し（`第N章`/`Chapter N`）は
# 本物なので降格しない。フォントサイズだけで見出しになった行の連続runを段落へ戻すのに使う。
_HEADING_NUMBER = re.compile(r"^(?:\d+(?:\.\d+)+)\s+\S")
_CHAPTER_HEADING = re.compile(r"^(?:第\s*\d+\s*章|Chapter\s+\d+)", re.I)
# 傍注の書き出し——これで始まる大フォント行は見出しでなく段落（`注：…`が5つのH1に化けた）。
_NOTE_MARKER = re.compile(r"^(?:注意|注|说明|說明|備考|备注|Note|NOTE|Notes)\s*[:：]")


def demoted_heading_lines(page: dict) -> set[str]:
    """フォントサイズ由来のheadingが3つ以上連続するrunのline idを返す。

    Overview本文・`注：…`傍注・mode説明などが**本文中央値の1.25倍**のフォントで組まれると、
    converterが各物理行をlevel-1見出しに化けさせる（H417RM.en p357の`(SerDes)`、L103RM.zhの
    注が5つのH1に。全corpus 359 run/272ページ）。本物の見出しは1-2行で連続しない一方、
    番号/章見出しは正当に連続しうるので**番号・章見出しは除外**。exporterだけがこれを段落へ
    戻す（parityは`#`接頭辞を見ず本文textだけ照合するので、heading↔paragraphの切替に非依存）。
    """
    lines = {l["id"]: l for l in page["lines"]}
    demote: set[str] = set()
    run: list[str] = []

    def flush() -> None:
        # 3行以上のrunは段落ブロック。短いrunでも注記マーカー（`注：`/`Note:`等）で
        # 始まる行を含むなら傍注が見出しに化けたもの——長さに依らず段落へ戻す（`(SerDes)`の
        # ような題の折り返しはマーカーが無いので据え置き）。
        has_note = any(_NOTE_MARKER.match(lines[i]["text"].strip()) for i in run)
        if len(run) >= 3 or has_note:
            demote.update(run)
        run.clear()

    for item in page["reading_order"]:
        line = lines.get(item["id"]) if item["type"] == "line" else None
        text = (line or {}).get("text", "").strip()
        if (line and line.get("role") == "heading" and text
                and not _HEADING_NUMBER.match(text) and not _CHAPTER_HEADING.match(text)):
            run.append(item["id"])
            # 見出し（番号・章以外）が50字超なら、それだけで段落——本物の節見出しは
            # 短い。実測: >50字の非caption見出し645件は全て文/傍注（実在の長い見出しは無し）。
            # 図caption（`Figure N-M …`）はcaption_matchが先に描くのでここで拾っても無害。
            # CJKの文末/節句読点（。，；：、）で終わる行も段落——節見出しはこれで終わらない
            # （ページ跨ぎの文末断片`除BTF位。`や本文`…実現交互。`。実測536件は全て段落）。
            if len(text) > 50 or text[-1] in "。，；：、":
                demote.add(item["id"])
        else:
            flush()
    flush()
    return demote


def title_continuations(page: dict) -> tuple[dict[str, str], set[str]]:
    """章見出しの折り返し2行目を1行目へ繋ぐ計画。`{章見出しline_id: 続きのtext}`と、
    本文から消す続き行のidを返す。

    `Chapter 20 Serial-parallel Interconversion Controller and Transceiver`＋`(SerDes)`のように
    ページ幅いっぱいの章題が折り返すと、2行目も同フォントで短いのでconverterが独立の
    level-1見出しにする（`# (SerDes)`）。条件を**章見出し（第N章/Chapter N）の直後・同フォント
    サイズ・40字以下・番号/章見出しでも図表captionでもない・文末句読点で終わらない**に絞る
    （全corpus実測: 該当5件は全て題の折り返し。番号見出し直後の`图22-3 …`caption等28件中23件は
    この条件で除外される）。parityは1行目のtext→2行目のtextを順に探すので、繋いだ1行に
    両方が並べば通る。
    """
    lines = {l["id"]: l for l in page["lines"]}
    order = [lines[it["id"]] for it in page["reading_order"]
             if it["type"] == "line" and it["id"] in lines]
    merge: dict[str, str] = {}
    skip: set[str] = set()
    for a, b in zip(order, order[1:]):
        ta, tb = a["text"].strip(), b["text"].strip()
        if not (a.get("role") == "heading" and b.get("role") == "heading"):
            continue
        if not _CHAPTER_HEADING.match(ta):
            continue
        if _HEADING_NUMBER.match(tb) or _CHAPTER_HEADING.match(tb):
            continue
        if not tb or len(tb) > 40 or tb[-1] in "。.；;":
            continue
        if figure_captions.caption_match(tb):
            continue
        if abs((a.get("font_size") or 0) - (b.get("font_size") or 0)) > 0.6:
            continue
        merge[a["id"]] = tb
        skip.add(b["id"])
    return merge, skip


_BULLETS = "-–—•●○▪·*‣◦"


def strip_leading_bullet(text: str) -> str:
    """箇条書き行の行頭bullet（`bullet + 空白`）を落とす。exporterが`- `を足すので
    残すと`- - Dual…`と二重になる。**bulletの直後が空白のときだけ**落とす——`-0.5`や
    `-40℃`のようなマイナス符号（空白が続かない）を誤って剥がして値を壊さないため。
    exporterとparity検査が同じ関数で処理して整合させる。"""
    s = text.lstrip()
    if len(s) >= 2 and s[0] in _BULLETS and s[1] in " \t":
        return s[2:].lstrip()
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
        elif pe[-1].isalnum() and cur[0].isalnum() and " " not in cur.strip():
            # 識別子の折り返し（`USAR`+`T1`=`USART1`）だけ地続きに繋ぐ。継続断片は
            # 空白を含まない1トークン。curが複数語（`10: Calibration voltage…`等の
            # enum項目行）なら折り返しでなく項目改行なので`<br>`（`AVDD10`連結を防ぐ）。
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
    # スロット単位の被覆（colspan/rowspanが覆っている格子）。被覆されておらず中身も無い
    # スロットは`<td></td>`で埋めないと、後続セルが左へ詰まって列がずれる——ページ跨ぎ
    # 断片で先頭列だけpdfplumberが取り漏らした行（FV2x p63 CRC一覧の`0x40023004`が
    # 名称列に見える）。全corpusで幅に届かない行を持つ結合表650件。
    slot_covered = [[False] * columns for _ in range(row_count)]
    for cell in table["cells"]:
        for r in range(cell["row_start"], min(cell["row_end"], row_count)):
            for c in range(cell["column_start"], min(cell["column_end"], columns)):
                if (r, c) != (cell["row_start"], cell["column_start"]):
                    slot_covered[r][c] = True
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

    def row_html(r: int, row: list[str | None]) -> str:
        # 中身のあるセルが1つも無い行は従来どおり空`<tr>`（見えない）のまま——被覆されて
        # いない空スロットへ`<td></td>`を出すのは、**何かが入っている行**だけ（列ずれ防止）。
        if not any(row):
            return "<tr></tr>"
        tag = "th" if r == 0 else "td"
        return "<tr>" + "".join(
            cell if cell else ("" if slot_covered[r][c] else f"<{tag}></{tag}>")
            for c, cell in enumerate(row)) + "</tr>"

    rows = [row_html(r, row) for r, row in enumerate(grid)
            if covered[r] or r not in folded_rows]
    # captionを持つ表だけが`<caption>`を出す。caption行の無い表（レジスタの
    # ビット図・説明表）は、原本でも表番号が振られていない——continuation継承で
    # 前ページの表番号（logical_id）を借りて名乗ると、無関係な`table-3-1@1`が
    # 6つ並ぶ（ユーザー指摘）。内部IDは追跡用にコメントへ残す。
    caption = (table.get("_caption_full") or table["caption"]["text"]) if table["caption"] else None
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
                lost_glyphs: int = 0, plan: dict | None = None,
                bundle: Path | None = None,
                entries: dict[int, dict] | None = None) -> str:
    tables = {item["id"]: item for item in page["tables"]}
    lines = {item["id"]: item for item in page["lines"]}
    images = {item["id"]: item for item in page["images"]}
    number = page["number"]
    # 大フォントの段落ブロック（Overview・注記・mode説明）が複数の見出しに化けた行を段落へ戻す。
    demote_headings = demoted_heading_lines(page)
    # 章題の折り返し2行目（`# (SerDes)`）は1行目の見出しへ繋ぐ。
    title_merge, title_skip = title_continuations(page)
    # geometryは要るときだけ開く（表の端に降ってきた重複グリフ除去に使う）。ページ跨ぎの
    # 結合表はセルごとに出自ページが違うので、ページ番号で引ける関数として渡す。
    _geo: dict[int, list[dict]] = {}

    def chars_for(page_number: int | None = None) -> list[dict]:
        pg = number if page_number is None else page_number
        if pg not in _geo:
            _geo[pg] = (load_geometry(bundle, entries[pg])["chars"]
                        if bundle is not None and entries and pg in entries else [])
        return _geo[pg]
    # レジスタのbit図: 番号行を図テーブルのヘッダへ畳む（tables）か、罫線が無い版は
    # 番号行の位置で合成テーブルを描く（synth）。畳んだ行は本文から消す（skip）。
    plan = plan or {"tables": {}, "synth": {}, "skip": set()}
    bitfields = plan["tables"]
    synth = plan["synth"]
    consumed_lines = plan["skip"]
    cross = plan.get("cross", {})            # {box_id: 中心} 前ページの番号行で組み直す箱
    cross_note = plan.get("cross_note", set())  # 次ページの箱へ番号を送った番号行
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
            if info["merged"] and tables[item["id"]].get("_caption_full"):
                # 折り返し表題の全文はbitfield_planがページ表に付ける。ページ跨ぎの結合表は
                # 別dictなので載せ替える——無いと続き行がskipされたうえ表題も1行目だけになり、
                # `+ RISC-V3F)`が本文からも表題からも消える（H417DS0.en p99。parityは検出できない）。
                record["_caption_full"] = tables[item["id"]]["_caption_full"]
            if (not record.get("caption")
                    and not any((c.get("text") or "").strip() for c in record["cells"])):
                # 全セル空の偽table（図box由来。全corpus 1,115件）——空の枠は出さない。
                # 空セルのcell_htmlは""でparityのexpectはno-opなので整合は保たれる。
                # bitfield/crossでもfieldが空ならapply_bitfieldは早期returnで内容を足さない
                # （番号ヘッダも付かない）ので、空gridの`|||…|||`を出さずに済む。
                continue
            if info["merged"]:
                logical_tables.fold_boundary_spills(record)
            if item["id"] in bitfields:
                line_id, centers = bitfields[item["id"]]
                logical_tables.apply_bitfield(record, lines[line_id], centers)
            elif item["id"] in cross:
                # 前ページ末尾の番号行で組み直す箱（bit図のページ跨ぎ分割）。
                logical_tables.apply_bitfield(record, None, cross[item["id"]])
            else:
                # 通常表: `Reset`/`value`に割れたヘッダを戻し、境界グリフの二重取り（`[31:12] R`等）を落とす。
                logical_tables.fold_header_wrap(record)
                logical_tables.strip_boundary_dupes(record)
                # 端に降ってきた別行のCJK/句読点グリフ（reset値の`0\n。`・`0000b\n时`）を
                # geometryで確認して落とす。Latin英数字は`tsu`/`td`の実文字と区別できないので
                # 触らない（latin_ok=False）。候補セルがあるページだけgeometryを開く。
                if logical_tables.has_edge_newline(record) or logical_tables.has_short_edge(record):
                    logical_tables.strip_straddling_dupes(record, chars_for)
            if inside:
                # 図領域内のtableは、図のbox/ラベルを罫線ありtableと誤抽出したもの
                # （全corpus 3,758件）。枠付きboxが図テキストへ割り込むので、セルの中身を
                # プレーンテキストで出す（`<details>🖼 Text parsed…`の趣旨に沿う）。transformは
                # 上で適用済みなので、parityは同じ変換後セルをこの順で読んで整合する。
                flat = "  ".join(cell_html(c["text"]) for c in record["cells"]
                                 if (c.get("text") or "").strip())
                if flat:
                    figure_text.append(flat + "  ")
            else:
                output.extend(("", table_html(record, url, number), ""))
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
        if item["id"] in synth:
            # 罫線の無いbit図: 番号行の位置で合成テーブルを描く。
            (figure_text if inside else output).extend(
                ("", table_html(synth[item["id"]], url, number), ""))
            continue
        if item["id"] in cross_note:
            # 番号は次ページの箱のヘッダへ送った。ここには可視のポインタを置く。
            (figure_text if inside else output).extend(
                ("", f"> ⬇ **Bit numbers for the register diagram at the top of "
                 f"[page {number + 1}]({number + 1:04d}.md)**. <!-- {item['id']} -->", ""))
            continue
        if item["id"] in consumed_lines:
            continue   # bit番号行/フィールド行は表へ畳んだ（bitfield）
        line = lines[item["id"]]
        if line["bbox"][3] - line["bbox"][1] < 0.5:
            continue   # 高さ0の退化行——2列見出し検出が生む重複見出しのghost（`# Feature`
                       # が2回。全corpusで28件全てこのパターン）。parityも同じくskip。
        if item["id"] in title_skip:
            continue   # 章題の折り返し2行目は直前の章見出しへ繋いだ
        role = line.get("role", "paragraph")
        raw = pua_normalize(line["text"])
        if role == "list-item":
            # 原本の行頭bullet（`- `等）を落とす——exporterが`- `を足すので二重になる
            # （`- - Dual…`。ユーザー指摘）。parityも同じ関数で落として整合させる。
            raw = strip_leading_bullet(raw)
        text = html.escape(raw)
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
        if role == "heading" and item["id"] not in demote_headings:
            if item["id"] in title_merge:
                text += " " + html.escape(pua_normalize(title_merge[item["id"]]))
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
    entry_of = {page["number"]: entry for entry, page in zip(manifest["pages"], pages)}
    chains = logical_tables.document_chains(pages)
    plans = document_bitfields(bundle, manifest, pages)
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
                        plans[page["number"]], bundle, entry_of),
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
