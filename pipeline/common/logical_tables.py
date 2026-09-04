"""L1: ページを跨ぐ表の物理断片を1つの論理表に結合する（D18の中間層）。

人向けMarkdown（pipeline/review）はページ単位のままだと表が改ページで割れる。
この moduleが断片の連鎖（chain）を決め、結合済みのセル（rowspan/colspan込み・
グローバルな行/列番号）を返す。抽出器（pipeline/extract）も同じ結合部品を使う。

**連鎖の判定は変換器の`continues_from_previous`に依存しない**。あのflagは
「前のcaption付き表のidを、captionの無い表が引き継ぐ」だけの素朴な規則で、
caption無しの表どうしを繋げないし（H417 DSの比較表p3+p4を結ばない——D17実測）、
逆に何ページも前のcaptionを引き継いで無関係な表を同一視する。ここでは構造で決める:

- 次ページの**最初の**表で、captionが無い
- その表より上に本文が無い（header/footerだけ）
- 前ページの最後の表より下に本文が無い
- **縦位置が連続**している（前の表はページ下部で終わり、次の表はページ上部から
  始まる）——これが無いと、RMで背中合わせに並ぶ同型の無caption表
  （register field表）を誤結合する
- **列構造が互換**——列数（セルのx辺の数）が同じ。辺の数が違うときは
  x座標の和集合が高々2辺しか増えないこと（header-only断片は空列が消えて
  辺が減る——V203 4-6-1で実測）

列の対応付けは2段構え（extract_low_powerで実証したものの共通化）:
列数が同じ断片は**位置**で（続きページで列幅が引き直されxが数ptずれる——
V20x/30x表4-9で実測）、違うときだけ**x座標の和集合**（許容2pt）で対応付ける。
"""

from __future__ import annotations

import re

TOLERANCE = 2.0        # pt。x辺の同一視
BOTTOM_BAND = 0.75     # 前ページの表がこれより下で終わっていること（ページ高比）
TOP_BAND = 0.25        # 続き断片がこれより上で始まっていること（ページ高比）


def fragment_edges(table: dict) -> list[float]:
    return sorted({round(v, 2) for cell in table["cells"]
                   for v in (cell["bbox"][0], cell["bbox"][2])})


def _union_edges(edge_lists: list[list[float]]) -> list[float]:
    merged: list[float] = []
    for edges in edge_lists:
        for x in edges:
            if not any(abs(x - edge) <= TOLERANCE for edge in merged):
                merged.append(x)
    return sorted(merged)


def compatible(a: list[float], b: list[float]) -> bool:
    if len(a) == len(b):
        return True
    return len(_union_edges([a, b])) <= max(len(a), len(b)) + 2


def merge_cells(fragments: list[tuple[int, dict]]) -> dict:
    """断片列 → 結合済み論理表。セルはグローバルな行/列番号を持つ。"""
    per = [(page, table, fragment_edges(table)) for page, table in fragments]

    if len({len(edges) for _, _, edges in per}) == 1:
        index_maps = [{edge: i for i, edge in enumerate(edges)} for _, _, edges in per]

        def column(fragment: int, x: float) -> int:
            return index_maps[fragment][x]
        width = len(per[0][2]) - 1
    else:
        merged_edges = _union_edges([edges for _, _, edges in per])

        def column(fragment: int, x: float) -> int:
            return min(range(len(merged_edges)),
                       key=lambda i: abs(merged_edges[i] - x))
        width = len(merged_edges) - 1

    cells: list[dict] = []
    row_pages: list[int] = []
    offset = 0
    for fragment, (page, table, _) in enumerate(per):
        for cell in table["cells"]:
            x0, _, x1, _ = cell["bbox"]
            c0 = column(fragment, round(x0, 2))
            c1 = column(fragment, round(x1, 2))
            cells.append({
                "row_start": offset + cell["row_start"],
                "row_end": offset + cell["row_end"],
                "column_start": c0,
                "column_end": max(c1, c0 + 1),
                "text": cell["text"],
                # 元のページ座標と出自ページ。`bbox`という名前にしない——結合セルにbboxが
                # 無いことをapply_bitfield等が「figure/bit図でない」印として使っている。
                # strip_straddling_dupesだけがページ別geometryで境界重複を判定するのに使う。
                "src_bbox": cell["bbox"],
                "page": page,
            })
        row_pages.extend([page] * table["row_count"])
        offset += table["row_count"]

    first = fragments[0][1]
    return {
        "id": first["id"],
        "logical_id": first["logical_id"],
        "caption": first.get("caption"),
        "width": width,
        "row_count": offset,
        "cells": cells,
        "row_pages": row_pages,
        "issues": [issue for _, table in fragments for issue in table["issues"]],
        "parts": [(page, table["id"]) for page, table in fragments],
    }


def fold_boundary_spills(merged: dict) -> int:
    """ページ境界でセルの中身が割れた「宙ぶらりん行」を直前セルへ畳む。

    レジスタのbitfield説明などが長いと、PDFはページの切れ目でそのセルを
    物理的に割る——結合表では「1列だけ非空・他は全部空の行」になる
    （X035RM 3-1のMCO[2:0]説明の続き`Other: No clock output.`が実例）。
    その非空セルを、直前の行の同じ列のセルへ改行連結し、継続セルは空にする。

    **ページ境界（`row_pages`が変わる行）だけ**を対象にする——同一ページ内の
    「1列だけ非空の行」は比較表の縦並び等の正当な独立セルで、畳むと壊れる
    （全コーパス実測: 境界限定1,937件は全て本物、境界を外すと9,527件になり
    製品比較表を誤結合）。**人向け出力専用**——exporterとparity検査だけが呼び、
    切替済みの抽出器（凍結CSV）は呼ばない。冪等（`_folded`で二重適用を防ぐ）。
    """
    if merged.get("_folded"):
        return 0
    merged["_folded"] = True
    row_pages = merged.get("row_pages")
    if not row_pages:
        return 0
    simple: dict[tuple[int, int], dict] = {}
    by_row: dict[int, list[dict]] = {}
    for cell in merged["cells"]:
        single = (cell["row_end"] - cell["row_start"] == 1
                  and cell["column_end"] - cell["column_start"] == 1)
        if single:
            simple[(cell["row_start"], cell["column_start"])] = cell
        if cell["text"].strip():
            by_row.setdefault(cell["row_start"], []).append((cell, single))
    removed: list[dict] = []
    for row in sorted(by_row):
        if row == 0 or row >= len(row_pages) or row_pages[row] == row_pages[row - 1]:
            continue
        occupied = by_row[row]
        if len(occupied) != 1:
            continue
        cell, single = occupied[0]
        if not single:
            continue
        prev = simple.get((row - 1, cell["column_start"]))
        if prev is None or not prev["text"].strip():
            continue
        prev["text"] = prev["text"] + "\n" + cell["text"]
        removed.append(cell)   # 継続セルはグリッドから消す（空行を残さない）
    for cell in removed:
        merged["cells"].remove(cell)
    # 継続セルを消した行番号（他の列の空セルだけが残る＝描画時に落とす行）。
    merged["_folded_rows"] = sorted(c["row_start"] for c in removed)
    return len(removed)


def strip_boundary_dupes(table: dict) -> int:
    """セル境界に載ったグリフをpdfplumberが左右両セルへ二重取りしたぶんを落とす。

    `[31:12] R`（右隣`Reserved`の先頭`R`が末尾に重複）・`RO R`・`s Description`
    （左隣`Access`の末尾`s`が先頭に重複）・`。 0`（左隣説明文の末尾句点が
    reset値へ重複）等。行内で列順に見て、`空白＋1文字`の**末尾**がその文字＝右隣
    セルの先頭非空白文字、または`1文字＋空白`の**先頭**がその文字＝左隣セルの末尾
    非空白文字なら、その1文字を落とす。**短いセル（本文≤14字）に限る**——長い
    説明文が偶然隣と一致して末尾語を失うのを防ぐ。geometry実測: 末尾は誤検出0/60、
    先頭の誤検出は既に文字交錯で崩れた図セルのみ（無害）。exporter・parity検査だけが
    呼ぶ**人向け専用**。凍結CSVの抽出器は呼ばない（canonicalはEVTヘッダ基準で無関係）。
    冪等（`_deduped`）。
    """
    if table.get("_deduped"):
        return 0
    table["_deduped"] = True
    by_row: dict[int, list[dict]] = {}
    for cell in table["cells"]:
        if (cell.get("text") or "").strip():
            by_row.setdefault(cell["row_start"], []).append(cell)
    removed = 0
    for cells in by_row.values():
        cells.sort(key=lambda c: c["column_start"])
        for index, cell in enumerate(cells):
            text = cell.get("text") or ""
            if (len(text) >= 3 and text[-2] == " " and text[-1].strip()
                    and index + 1 < len(cells)):
                right = (cells[index + 1].get("text") or "").lstrip()
                body = text[:-2]
                if right[:1] == text[-1] and 0 < len(body) <= 14 and body.strip():
                    cell["text"] = text = body
                    removed += 1
            if len(text) >= 3 and text[1] == " " and text[0].strip() and index > 0:
                left = (cells[index - 1].get("text") or "").rstrip()
                body = text[2:]
                if left[-1:] == text[0] and 0 < len(body) <= 14 and body.strip():
                    cell["text"] = body
                    removed += 1
    return removed


def _edge_newline_separated(text: str, n: int, tail: bool) -> bool:
    """末尾/先頭のn個の非空白文字が、残りと**改行**で隔てられているか（空白や地続きは
    別視覚行でない＝あふれた実文字なので除去しない）。"""
    if tail:
        i, dropped = len(text), 0
        while i > 0 and dropped < n:
            i -= 1
            if text[i] not in " \n":
                dropped += 1
        return i > 0 and text[i - 1] == "\n"
    i, dropped = 0, 0
    while i < len(text) and dropped < n:
        if text[i] not in " \n":
            dropped += 1
        i += 1
    return i < len(text) and text[i] == "\n"


def _drop_edge_chars(text: str, n: int, tail: bool) -> str:
    """textの末尾（tail=True）または先頭からn個の非空白文字を、間の空白/改行ごと落とす。"""
    if tail:
        i, dropped = len(text), 0
        while i > 0 and dropped < n:
            i -= 1
            if text[i] not in " \n":
                dropped += 1
        while i > 0 and text[i - 1] in " \n":
            i -= 1
        return text[:i]
    i, dropped = 0, 0
    while i < len(text) and dropped < n:
        if text[i] not in " \n":
            dropped += 1
        i += 1
    while i < len(text) and text[i] in " \n":
        i += 1
    return text[i:]


def unbalanced_parens(text: str) -> bool:
    """開き括弧が閉じ括弧より多いか（半角/全角）。折り返しで切れた表題・セルの印。"""
    return (text.count("(") + text.count("（")) > (text.count(")") + text.count("）"))


def caption_full(page: dict, table: dict) -> tuple[str, list[str]]:
    """表題が折り返して括弧が閉じていないとき、後続のparagraph行を括弧が閉じるまで繋いだ
    全文と、繋いだ続き行のidを返す。bundleの`caption.text`は1行目だけ（`…SRAM (RISC-V5F`＋
    次行`+ RISC-V3F)`。H417DS0.en p99。全corpusで11表題）。exporter（`<caption>`と本文skip）と
    extract_low_power（条件prefix）が同じ全文を使う。"""
    caption = table.get("caption")
    if not caption:
        return "", []
    text = caption["text"].strip()
    lines = {line["id"]: line for line in page["lines"]}
    order = [item["id"] for item in page["reading_order"] if item["type"] == "line"]
    if caption.get("line_id") not in order:
        return text, []
    index = order.index(caption["line_id"]) + 1
    used: list[str] = []
    # 括弧が閉じていない、または接続詞/前置詞で終わる（`…runs from internal Flash or`＋
    # `SRAM (…)`。V003DS0 表3-x）間は折り返し。暴走防止で最大3行。
    while (unbalanced_parens(text) or _dangling(text)) and index < len(order) and len(used) < 3:
        nxt = lines[order[index]]
        if nxt.get("role") not in ("paragraph", "list-item"):
            break
        if _looks_like_caption(nxt["text"]):
            # 原本の表題に`（（`の重複があると括弧は永久に閉じない（V407RM.zh p106 `表10-4 串行外设
            # 接口（（SPI1/2/3）模块`）。次の表の表題まで飲み込まないよう、表題らしい行で止める。
            break
        cont = nxt["text"].strip()
        # CJKの行折り返しは印字に空白が無い（H417RM.zh p795 `…数据值），`＋`基于某些IOSR值…`。
        # PDF突合サブエージェントの指摘）。両側がCJK/全角約物なら区切りを入れない。
        sep = "" if (_cjk(text[-1:]) and _cjk(cont[:1])) else " "
        text = text + sep + cont
        used.append(nxt["id"])
        index += 1
    return text, used


_DANGLING = {"or", "and", "with", "without", "of", "from", "in", "to", "for", "by", "at",
             "on", "the", "a", "an", "+", "&", "/", "vs", "via", "under", "between"}


def _cjk(ch: str) -> bool:
    """CJK統合漢字・全角約物（`，（）`等）・CJK句読点か。"""
    return bool(ch) and ("一" <= ch <= "鿿" or "＀" <= ch <= "￯" or "　" <= ch <= "〿")


def _looks_like_caption(text: str) -> bool:
    """`Table 3-7 …`／`表10-5 …`／`图2-1 …`／`Figure 4 …`で始まる行か（表題の続き行ではなく別の表題）。"""
    text = text.strip()
    for marker in ("Table", "Figure", "表", "图"):
        if text.startswith(marker):
            rest = text[len(marker):].lstrip()
            return rest[:1].isdigit()
    return False


def _dangling(text: str) -> bool:
    """表題が文の途中で切れているか——英語は末尾の語が接続詞/前置詞/冠詞、CJKは末尾が
    読点・連結語（`，`・`、`・`与`・`或`・`和`・`及`・`及び`）。"""
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped[-1] in "，、与或和及＋/":
        return True
    last = stripped.split()[-1].strip("()（）[]「」,;:").lower()
    return last in _DANGLING


def fold_header_wrap(table: dict) -> int:
    """`Reset value`のような狭いヘッダが2行に折り返し、2行目（`value`）がpdfplumberで
    **独立したデータ行**になったものを、ヘッダセルへ戻して行を消す（全corpus 104ページで
    `<tr><td>value</td></tr>`。register意味監査サブエージェントが発見、2026-09-03）。

    条件: row 1 に中身のあるセルが**ちょうど1つ**、その中身が短い小文字1語（`value`等）、
    同じ列の row 0 が短いヘッダ（`Reset`）。両方を空白で繋いでヘッダに、row 1 を詰める。
    parityは`Reset`→`value`の順に探すので、繋いだ`Reset value`で通る。冪等。
    """
    if table.get("_header_folded") or table.get("row_count", 0) < 2:
        return 0
    table["_header_folded"] = True
    row1 = [c for c in table["cells"] if c["row_start"] == 1 and (c.get("text") or "").strip()]
    if len(row1) != 1:
        return 0
    tail = row1[0]
    word = tail["text"].strip()
    if not (word.isalpha() and word.islower() and len(word) <= 8
            and tail["row_end"] - tail["row_start"] == 1):
        return 0
    head = next((c for c in table["cells"]
                 if c["row_start"] == 0 and c["column_start"] == tail["column_start"]
                 and c["row_end"] == 1 and (c.get("text") or "").strip()), None)
    if head is None or len(head["text"].strip()) > 12 or "\n" in head["text"]:
        return 0
    head["text"] = head["text"].strip() + " " + word
    # row 1 を消して以降の行を1つ繰り上げる（row 1 に他の空セルがあれば一緒に消える）
    table["cells"] = [c for c in table["cells"] if c["row_start"] != 1]
    for c in table["cells"]:
        if c["row_start"] > 1:
            c["row_start"] -= 1
        if c["row_end"] > 1:
            c["row_end"] -= 1
    table["row_count"] -= 1
    # 行番号を持つ付帯情報も一緒に繰り上げる。`_folded_rows`（fold_boundary_spillsが消した
    # 継続行——table_htmlがその行を落とす）を繰り上げ忘れると**1つ下の実データ行を捨てる**
    # （V003RM.en p17でPLLON行が消えた。parityはセル列を読むので検出できずmissingになる）。
    if table.get("_folded_rows"):
        table["_folded_rows"] = sorted(r - 1 if r > 1 else r
                                       for r in table["_folded_rows"] if r != 1)
    if table.get("row_pages") and len(table["row_pages"]) > 1:
        del table["row_pages"][1]
    return 1


_NAME_HEADERS = ("Name", "名称", "名字", "Field", "位域名")


def description_names(page: dict, chains: dict[str, dict] | None = None) -> set[str]:
    """このページの記述表の`Name`列（`名称`/`Field`/`位域名`）に並ぶ、**正しいフィールド名**。

    レジスタのページは「bit図」＋「bitごとの説明表」の対で書かれるので、説明表の名称列が
    そのページの正解表になる。bit図の組み直しの検算に使う（`fix_doubled_names`）。

    `chains`（`document_chains`の結果）を渡すと、**ページ跨ぎの結合表**からも集める——
    説明表が前ページから続いていると、このページの断片にはヘッダ行が無く名称列を
    見つけられない（FV2x_V3xRM.en p622の`TIM1_STOP`等12件がそれで直せなかった）。
    証拠は「このページに出ている表（とその続き）」に限る——文書全体から集めると
    `PB11`の正解として別章の`PB1`を拾ってしまう。
    """
    names: set[str] = set()
    tables = [((chains or {}).get(t["id"], {}).get("merged") or t)
              for t in page["tables"]]
    for table in tables:
        by_row: dict[int, list[dict]] = {}
        for cell in table["cells"]:
            by_row.setdefault(cell["row_start"], []).append(cell)
        header = by_row.get(0) or []
        columns = [c["column_start"] for c in header
                   if (c.get("text") or "").strip() in _NAME_HEADERS]
        if not columns:
            continue
        for row, cells in by_row.items():
            if row == 0:
                continue
            for cell in cells:
                if cell["column_start"] in columns:
                    text = (cell.get("text") or "").strip()
                    if text:
                        names.add(text)
    return names


def _undoubled_tail(text: str) -> str | None:
    """末尾が同じブロックの2連なら1つ分を落とした綴り（`HSYNCSCS`→`HSYNCS`）。
    ブロックに英字が要る——`PB11`型の数字末尾は正当な名前なので触らない。"""
    for k in range(1, len(text) // 2 + 1):
        block = text[-k:]
        if text[-2 * k:-k] == block and any(ch.isalpha() for ch in block):
            return text[:-k]
    return None


def fix_doubled_names(table: dict, names: set[str]) -> int:
    """bit図のセルで**末尾のブロックが二重になった名前**を、記述表のName列と照合して直す。

    原因はこちら側——`apply_bitfield`が縦に割れた名前を繋ぐとき、隣のセルに二重取りされた
    末尾断片も足してしまう（bundleのセルは`HSYNCS`と正しい）。結果、bit図と直下の説明表が
    食い違った: `HSYNCSCS`/`VSYNCSCS`/`COLKENLKEN`/`VBRR`/`WWDG_STOPTOP`/`TIM1_STOPP`/
    `Reservederved`/`BURST_ENDRST_END`/`PA1PA2_RMM`（PDF↔MD突合サブエージェントが発見。
    全corpus44セル・6文書）。

    直すのは**説明表が否定し、重複を外すと説明表と一致する**ときだけ——`PB11`・`ODR11`・
    `DMA2_CH11`のような正当な数字末尾（説明表にその綴りが在る）は触らない。冪等。
    """
    if not names or table.get("_undoubled"):
        return 0
    table["_undoubled"] = True
    fixed = 0
    for cell in table["cells"]:
        # 判定は**描画後の形**で行う——`apply_bitfield`の連結は改行を残すことがあり
        # （`HSYNCS\nCS`）、`cell_html`が識別子として地続きに繋いで`HSYNCSCS`になる。
        flat = (cell.get("text") or "").replace("\n", "").strip()
        if len(flat) < 4 or " " in flat or flat in names:
            continue
        short = _undoubled_tail(flat)
        if short and len(short) >= 3 and short in names:
            cell["text"] = short
            fixed += 1
    return fixed


_RECOVER_TOKEN = re.compile(r"[A-Za-z0-9_\[\]:.]{2,}")


def recovered_lines(page: dict) -> list[dict]:
    """変換器が`reading_order`から外した行のうち、**表のセルにも残った行にも中身が無い**もの。

    converterは表の領域に重なる行をreading_orderから外す（表のセルが同じ文字を持つはず、
    という前提）。ところが図（クロックツリー・メモリマップ・プロトコル図）のラベルは
    「図をtableと誤検出した箱」の外側に落ちることがあり、セルにもreading_orderにも無い
    ——exporterもparityもreading_orderだけを歩くので、**黙って消える**（PDF↔MD突合が
    V407RM.en p529の`RDes2`/`RDes3`、p11の`Approx.`/`40mV`、p406の`HB bus`で発見）。

    図は画像として描かれるので人には見えているが、この文書の方針は「図から読めた文字も
    検索・コピーのために残す」なので、拾い直して`<details>`へ入れる。
    **重複を出さないため、語（2文字以上）が1つでも他所に在る行は拾わない**（部分的に
    セルへ入っている行を足すと同じ文字が二度出る）。
    """
    order = {item["id"] for item in page["reading_order"] if item["type"] == "line"}
    covered = " ".join((c.get("text") or "") for t in page["tables"] for c in t["cells"])
    kept = " ".join(l["text"] for l in page["lines"] if l["id"] in order)
    haystack = covered + " " + kept
    out = []
    for line in page["lines"]:
        if line["id"] in order or line.get("role") in ("header", "footer"):
            continue
        tokens = _RECOVER_TOKEN.findall(line["text"])
        if not tokens or any(token in haystack for token in tokens):
            continue
        out.append(line)
    return out


def reading_stream(page: dict) -> list[dict]:
    """`reading_order`に`recovered_lines`を縦位置で差し込んだ読み順。exporterとparityが
    同じ関数を使うので、拾い直した行も同じ位置・同じ順で検査される。"""
    recovered = recovered_lines(page)
    if not recovered:
        return list(page["reading_order"])
    stream = list(page["reading_order"])
    for line in sorted(recovered, key=lambda l: (l["bbox"][1], l["bbox"][0])):
        item = {"type": "line", "id": line["id"], "bbox": line["bbox"]}
        index = next((i for i, existing in enumerate(stream)
                      if existing["bbox"][1] > line["bbox"][1]), len(stream))
        stream.insert(index, item)
    return stream


def drop_phantom_fragment_rows(table: dict) -> int:
    """縦に割れた名前の**断片が別の行としても現れる**ぶんを落とす（重なりセルの副産物）。

    pdfplumberが重なった結合セルを記録したとき、`BU⏎RS⏎T_E⏎ND`（=BURST_END）を持つ縦長セルの
    下に、`RS`・`T_E`・`ND`だけの1セル行が並ぶことがある。縦長セルが既に全文を持っているので、
    その断片行は同じ文字の二重表示（H417RM.en p226/p461/p976/p988ほか、全corpus 64行・26文書）。

    落とすのは**同じ列で、その行を覆う行span2以上のセルの物理行と完全一致する**セルだけ
    ——値がたまたま一致する比較表（`2*DAC`が別列の値として在る等）は触らない。冪等。
    """
    if table.get("_phantom_dropped"):
        return 0
    table["_phantom_dropped"] = True
    cells = table["cells"]
    by_row: dict[int, list[dict]] = {}
    for cell in cells:
        if (cell.get("text") or "").strip():
            by_row.setdefault(cell["row_start"], []).append(cell)
    removed = []
    for row, occupied in by_row.items():
        if row == 0 or len(occupied) != 1:
            continue
        cell = occupied[0]
        text = (cell["text"] or "").strip()
        if not text:
            continue
        for other in cells:
            if other is cell or other["column_start"] != cell["column_start"]:
                continue
            if not (other["row_start"] < row <= other["row_end"]
                    and other["row_end"] - other["row_start"] >= 2):
                continue
            lines = [q.strip() for q in (other.get("text") or "").split("\n") if q.strip()]
            if len(lines) > 1 and text in lines:
                removed.append(cell)
                break
    for cell in removed:
        cells.remove(cell)
    return len(removed)


def _box_overlap(inner: list[float], outer: list[float]) -> float:
    ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return (ix * iy) / area if area > 0 else 0.0


def fragment_tables(page: dict) -> set[str]:
    """**別の表の箱の中にある、断片だけの1列表**のid（描かない）。

    重なった結合セルの残骸が独立した表として抽出される: `<table><tr><th>AL</th></tr>
    <tr><td>LA</td></tr></table>`（V407RM.en p340の`STALLA`の破片）、`USART1_RM1=0(2)`＋
    `Default Mapping`（FV2x_V3xRM.en p138）、`signal`＋`level`。全corpus 559表・41文書。

    条件は厳しく: 1列・2行以下で、**すべてのセルの文字が、面積の6割以上を重ねる別の表の
    セルの物理行と完全一致**すること——中身は必ずその表に出るので、消しても文字は失われない。
    exporterとparityが同じ判定を使う。
    """
    out: set[str] = set()
    for table in page["tables"]:
        if (table.get("column_count") or 0) > 1 or (table.get("row_count") or 0) > 2:
            continue
        texts = [(c.get("text") or "").strip() for c in table["cells"]
                 if (c.get("text") or "").strip()]
        if not texts:
            continue
        for host in page["tables"]:
            if host["id"] == table["id"] or _box_overlap(table["bbox"], host["bbox"]) < 0.6:
                continue
            lines = {q.strip() for c in host["cells"]
                     for q in (c.get("text") or "").split("\n") if q.strip()}
            if all(text in lines for text in texts):
                out.add(table["id"])
                break
    return out


def looks_ruled(table: dict) -> bool:
    """図領域の中にあっても**本物の罫線表**か（行3以上・列2以上・非空セル6以上・
    2行以上が2セル以上埋まっている）。

    図領域は`render_assets`がgraphicsの縦クラスタで決めるが、**罫線表の罫線もgraphics**
    なので、表題が図と名乗っていると表そのものが図領域になる。原本の誤植でそうなる例:
    CH32V407RM.**en** p475 `Figure 26-19 Mode D FSMC_BCR1 bit field`（zh は`表26-19`、
    同じ章の Mode 1/A/B/C は en でも`Table 26-8/26-10/26-13/26-16`）——18行のbit域表が
    画像＋折りたたみの平文になり、表として読めなかった。全corpusで**229表・48文書**が該当
    （図領域内の表5,146のうち。残り4,917は図のboxやラベルで、平文のままが正しい）。
    exporterはこれをHTML表として折りたたみの中に描き、平文へ潰さない。
    """
    rows = table.get("row_count") or 0
    # ページ跨ぎの結合表は`column_count`を持たず`width`を持つ（`merge_cells`）。
    columns = table.get("column_count") or table.get("width") or 0
    if rows < 3 or columns < 2:
        return False
    filled = [c for c in table["cells"] if (c.get("text") or "").strip()]
    if len(filled) < 6:
        return False
    per_row: dict[int, int] = {}
    for cell in filled:
        per_row[cell["row_start"]] = per_row.get(cell["row_start"], 0) + 1
    return sum(1 for n in per_row.values() if n >= 2) >= 2


def has_short_edge(table: dict) -> bool:
    """短いセル（値・reset値など≤12字）に、端の1文字が地続き/空白で付いた候補があるか
    （`0对`・`e 0`・`Reserved L`）。geometryを開く前の安価な前判定。"""
    for cell in table["cells"]:
        text = (cell.get("text") or "").strip()
        if 2 <= len(text) <= 12 and (text[1] == " " or text[-2] == " "
                                      or not text.isascii()):
            return True
    return False


def has_edge_newline(table: dict) -> bool:
    """端に「1文字＋改行」または「改行＋1文字」を持つセルがあるか——strip_straddling_dupesの
    候補。geometry（重い）を開く前の安価な前判定に使う。"""
    for cell in table["cells"]:
        text = cell.get("text") or ""
        if len(text) >= 2 and (text[1] == "\n" or text[-2] == "\n"):
            return True
    return False


def _overlap_frac(glyph_box: list[float], cell_box: list[float]) -> float:
    """グリフ面積のうちセルbboxに入っている割合（0..1）。"""
    gx0, gy0, gx1, gy1 = glyph_box
    cx0, cy0, cx1, cy1 = cell_box
    area = max(0.0, gx1 - gx0) * max(0.0, gy1 - gy0)
    if area <= 0:
        return 0.0
    ix = max(0.0, min(gx1, cx1) - max(gx0, cx0))
    iy = max(0.0, min(gy1, cy1) - max(gy0, cy0))
    return ix * iy / area


def _at_line_edge(text: str, ch: str) -> bool:
    """chがtextのどこかの**行の先頭か末尾**にあるか。境界を跨いだグリフは相手セルでも
    行の端に現れる（`LEVEL`の先頭L・説明文の行末`，`）。行の中程にある同じ文字
    （`15:0]`の`1`が隣の`[15:0]`の中程に在る等）は根拠にしない。"""
    for line in text.split("\n"):
        line = line.strip()
        if line and (line[0] == ch or line[-1] == ch):
            return True
    return False


def _strip_value_edges(table: dict, cell: dict) -> bool:
    """短いASCIIの値セル（reset値`0`/`0x…`/`00b`）の端に付いた非ASCII文字（`，\\n0`・`0对`・
    `00b 次`）を、**隣セルの行端に同じ文字がある**ことを確認して落とす。zhの説明文の行末が
    右の狭いreset列へ跨ぐ症状（全corpus zhで622セル）。全角文字のグリフ箱は広く、面積判定
    では自セル側に半分以上入ることがあるため、ここはテキストで決める。値にCJKは含まれない
    ので値セルに限れば安全。"""
    text = cell.get("text") or ""
    core = text.replace("\n", "").replace(" ", "")
    if not core:
        return False
    lead = 0
    while lead < len(core) and not core[lead].isascii():
        lead += 1
    tail = 0
    while tail < len(core) - lead and not core[-1 - tail].isascii():
        tail += 1
    mid = core[lead:len(core) - tail]
    if not mid and 1 <= len(core) <= 3 and not any(c.isalnum() for c in core):
        # 句読点だけのセル（`。`）——説明文の行末句点が隣の空セルへ単独で降りたもの
        # （V003RM.zh p16の名称空行）。隣の行端に同じ文字があれば空にする。
        for ch in core:
            if not any(_at_line_edge((o.get("text") or "").strip(), ch)
                       for o in table["cells"]
                       if o is not cell and len((o.get("text") or "").strip()) > 1
                       and o.get("page") == cell.get("page")):
                return False
        cell["text"] = ""
        return True
    if not (lead or tail) or not mid or not mid.isascii() or len(mid) > 12 or lead + tail > 3:
        return False
    if not any(c.isalnum() for c in mid):
        return False
    # 値と**地続き**の非ASCIIは単位/助数詞（`8路`・`105℃`・`2组`——datasheetの製品比較表）で
    # 本物。隣から降ってきた文字は別行か空白で切れている（`0\n对`・`，\n0`・`00b 次`）。
    # 同列の兄弟セルが皆`…路`で終わるため「隣の行端に同じ文字」は単位でも満たされてしまう
    # ——分離の有無で決める。
    if lead and _fused_edge(text, lead, tail=False):
        lead = 0
    if tail and _fused_edge(text, tail, tail=True):
        tail = 0
    if not (lead or tail):
        return False
    edges = core[:lead] + (core[len(core) - tail:] if tail else "")
    for ch in edges:
        if not any(_at_line_edge((o.get("text") or "").strip(), ch)
                   for o in table["cells"]
                   if o is not cell and len((o.get("text") or "").strip()) > 1
                   and o.get("page") == cell.get("page")):
            return False
    if tail:
        text = _drop_edge_chars(text, tail, tail=True)
    if lead:
        text = _drop_edge_chars(text, lead, tail=False)
    cell["text"] = text
    return True


def _edge_separated(text: str, ch: str) -> bool:
    """chが行の端にあり、かつ隣の文字と**空白で切れている**か（`1 INTE`の`1`、`Reserved L`の
    `L`、1文字だけの行）。語に融合している（`INTEN1`の`1`・`ddr[1`の`1`）なら偽。"""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[0] == ch and (len(line) == 1 or line[1].isspace()):
            return True
        if line[-1] == ch and (len(line) == 1 or line[-2].isspace()):
            return True
    return False


def _fused_edge(text: str, n: int, tail: bool) -> bool:
    """端のn個の非空白文字が、残りの文字と地続き（空白/改行なし）か。"""
    s = text.rstrip() if tail else text.lstrip()
    if tail:
        i, dropped = len(s), 0
        while i > 0 and dropped < n:
            i -= 1
            if not s[i].isspace():
                dropped += 1
        return i > 0 and not s[i - 1].isspace()
    i, dropped = 0, 0
    while i < len(s) and dropped < n:
        if not s[i].isspace():
            dropped += 1
        i += 1
    return i < len(s) and not s[i].isspace()


def _owned_elsewhere(table: dict, cell: dict, ch: str, chars: list[dict],
                     ours_fused: bool = False) -> bool:
    """文字chの**具体的なグリフ**が「このセルに重なるが面積の半分未満しか入らず、別のセルに
    半分以上入り、その別セルのtextにもchがある」か＝pdfplumberのcropが境界を跨ぐグリフを
    両セルの文字列に入れた真の重複。自セルに半分以上入る端のグリフは自分の文字なので
    対象外（`Reserved`の`R`・`PB14`の`4`）。近くの無関係な同じ文字（隣の`RW`の`R`）は自セルに
    重ならないので数えない。`R 22`の`R`（どのセルにも半分以上入らないあふれ）も偽で守られる。"""
    box = cell.get("bbox") or cell["src_bbox"]
    # pdfplumberのcropは境界に**接している**だけのグリフも拾うので、自セルとの重なりは
    # 0でもよい（`Reserved L`のLはx0がセル右端と一致）。2pt広げた箱に触れていれば候補。
    near = [box[0] - 2.0, box[1] - 2.0, box[2] + 2.0, box[3] + 2.0]
    for glyph in chars:
        if glyph.get("text") != ch:
            continue
        if _overlap_frac(glyph["bbox"], near) <= 0.0:
            continue   # 触れていない
        if _overlap_frac(glyph["bbox"], box) >= 0.5:
            continue   # 自分のもの
        for other in table["cells"]:
            obox = other.get("bbox") or other.get("src_bbox")
            other_text = (other.get("text") or "").strip()
            if (other is cell or not obox or not _at_line_edge(other_text, ch)
                    or other.get("page") != cell.get("page")):   # 座標はページ内でしか比べられない
                continue
            if len(other_text) <= 1:
                # 相手の中身がその1文字だけ＝自セルのテキストがあふれて隣に**人工セル**が
                # できたもの（`PB14`の`4`が幅17ptのセルから隣へ40/60で跨ぎ、隣は`4`だけ）。
                # 意味を持つのは`PB14`側なので、こちらの文字を重複扱いしない。
                continue
            if ours_fused and _edge_separated(other_text, ch):
                # 自セルでは語に融合（`INTEN1`）、相手では空白で切れている（`1 INTE`）——
                # 融合している側が本物で、切れている側がcropの拾いすぎ。幾何が相手寄りでも
                # こちらの文字は残す（狭い列から名前があふれた典型）。
                continue
            if _overlap_frac(glyph["bbox"], obox) >= 0.5:
                return True
    return False


def strip_straddling_dupes(table: dict, chars: list[dict]) -> int:
    """セル境界を跨いだグリフをpdfplumberのcropが**両セル**の文字列に入れた重複を、
    geometryで裏取りして落とす（bit図・通常表・ページ跨ぎ結合表に共通）。

    手順（セルごと）:
    1. 値セルの前処理 `_strip_value_edges`: 短いASCII値（`0`/`0x…`/`00b`）の端に付いた
       非ASCII文字（`，\\n0`・`0对`）は、隣セルの行端に同じ文字があれば落とす（全角文字の
       グリフ箱は広く面積では決まらないため、テキストで決める）。
    2. `own`＝**面積の半分以上がbbox内**にあるグリフの綴り。textの端（または中間の1文字行）
       がownより1-2文字多ければ余剰候補。中心判定ではなく面積で見るのは、狭い列で名前が
       あふれると端の実グリフの中心がわずかに外へ出て `Reserved`→`eserved` と誤るため。
    3. 余剰候補の**具体的なグリフ**が `_owned_elsewhere`——自セルに半分未満しか入らず、
       別セルに半分以上入り、その別セルの**行端**にその文字がある（`LEVEL`の先頭L・説明文の
       行末`，`）、かつ相手が1文字だけの人工セル（`PB14`の`4`）でない——なら落とす。
       `R 22`のR（どのセルにも半分以上入らないあふれ）や`t\\nsu`の`t`は偽になり守られる。

    charsはページのグリフ列か、`page番号→グリフ列`の関数（結合表はセルごとに出自ページが
    違うので後者で渡す。結合セルは`src_bbox`/`page`を持つ）。exporterとparity検査が同じ
    セルへ同じ順で適用するので整合する。canonical抽出器は呼ばない。冪等。
    """
    if table.get("_straddle_stripped"):
        return 0
    table["_straddle_stripped"] = True
    removed = 0
    for cell in table["cells"]:
        text = cell.get("text") or ""
        box = cell.get("bbox") or cell.get("src_bbox")
        if not box or not text.strip():
            continue
        if _strip_value_edges(table, cell):
            removed += 1
            continue
        x0, y0, x1, y1 = box
        # ページ跨ぎの結合表はセルごとに出自ページが違う——charsはpageを引く関数でも渡せる
        page_chars = chars(cell.get("page")) if callable(chars) else chars
        # 自セルの綴り＝**面積の半分以上がbbox内**にあるグリフ（中心判定だと端の実グリフが
        # 中心わずか外で漏れ、`Reserved`→`eserved`のように実文字を「余剰」と誤認した）。
        own = "".join(
            g["text"] for g in sorted(
                (g for g in page_chars if (g.get("text") or "").strip()
                 and _overlap_frac(g["bbox"], box) >= 0.5),
                key=lambda g: (round(g["bbox"][1]), g["bbox"][0])))
        core = text.replace("\n", "").replace(" ", "")
        extra = len(core) - len(own)
        if len(own) < 2 or not 0 < extra <= 2:
            continue
        # **改行で別視覚行に分離された端文字だけ**落とす。狭い列で名前がセル幅を
        # 超えてあふれると実文字の中心もセル外に落ちる（`SWIE`+`R 22`＝SWIER22の
        # `R`、`USART`の先頭`U`）——これは同じ視覚行なので触らない。真の二重取りは
        # 隣の**行**からグリフが降って来る（`Reserve\nd\nR`の`R`）ので改行で分かれる。
        # 端でなく**中間の行**に1文字だけ載っている重複（`BIDI\nC\nOE`——右隣`CRCEN`の`C`が
        # 縦割れ名の行間へ降りた。V003RM.zh p172）: その1文字行を抜いた綴りがownと一致すれば
        # それを落とす。geometryで裏取り済みなので安全。
        parts = text.split("\n")
        middle_done = False
        for index in range(1, len(parts) - 1):
            lone = parts[index].strip()
            if len(lone) != 1 or not _owned_elsewhere(table, cell, lone, page_chars):
                continue
            candidate = "\n".join(parts[:index] + parts[index + 1:])
            if candidate.replace("\n", "").replace(" ", "") == own:
                cell["text"] = candidate
                removed += 1
                middle_done = True
                break
        if middle_done:
            continue
        if core.startswith(own):
            dropped, tail = core[len(own):], True
        elif core.endswith(own):
            dropped, tail = core[:extra], False
        else:
            continue
        # 落とす文字は**全て**「中心が別セル内にあり、そのセルのtextにも在る」グリフでなければ
        # ならない（真の二重取り）。これで区切りの種類（空白/改行/地続き）に依らず、
        # `Reserved L`（LEVELのL）・`e 0`（ヘッダ`Reset value`のe）・`0对`（説明列の对）は消え、
        # `R 22`のR（あふれ・どのセルにも属さない）や`t\nsu(SI)`の`t`は守られる。
        fused = _fused_edge(text, extra, tail)
        if not all(_owned_elsewhere(table, cell, ch, page_chars, ours_fused=fused)
                   for ch in dropped):
            continue
        cell["text"] = _drop_edge_chars(text, extra, tail=tail)
        removed += 1
    return removed


def text_grid(merged: dict) -> tuple[list[list[str | None]], list[int]]:
    """結合済み論理表 → 文字の格子（抽出器向け。spanの先頭位置に文字を置く）。"""
    rows: list[list[str | None]] = [[None] * merged["width"]
                                    for _ in range(merged["row_count"])]
    for cell in merged["cells"]:
        rows[cell["row_start"]][cell["column_start"]] = cell["text"]
    return rows, merged["row_pages"]


# ---- レジスタのbit-field図 -------------------------------------------------
# RMのレジスタは「31 30 … 16」の1行（bit番号）＋直下のフィールド箱で描かれる。抽出は
# 版によって列数がまちまち（空の16列箱の版もあれば、同じフィールドの箱仕切りが消えて
# 8〜9列に潰れ名前がそのまま入る版もある）。列構造に頼らず、**bit番号のx中心を列の
# 真実**として（bitは等幅でない——比例配分は不可）、各フィールドが跨ぐbit数を中心の
# 包含で数え、16等幅へ組み直す。番号はヘッダ行、狭い列で縦に割れた名前は連結、TIMの
# CCMRのような出力名/入力名の2段は残す。**人向け出力専用**（exporterとparity検査
# だけが呼ぶ。凍結CSVの抽出器は触らない）。冪等。

def bit_numbers(text: str) -> list[int] | None:
    """行が「N N-1 … 」のbit番号列ならintの並びを返す（でなければNone）。

    厳密に降順（a>b）・長さ≥8・全て0..31。これで3形をまとめて拾う——16bitの
    `15 14 … 0`、幅が半端な`11 10 … 0`（12bit）、byte境界の`31 24 23 16 15 8 7 0`。
    横並びレジスタが混ざった非降順（`8 7 5 3 0 9 8 7`）や、bit>31（`96 … 65`）は弾く。
    列マップはbit番号のx中心が担うので、間隔が一定でなくても構わない。
    """
    tokens = text.split()
    if len(tokens) < 8 or not all(t.isdigit() for t in tokens):
        return None
    nums = [int(t) for t in tokens]
    if any(a <= b for a, b in zip(nums, nums[1:])):
        return None
    if not all(0 <= n <= 31 for n in nums):
        return None
    return nums


def bit_number_centers(chars: list[dict], number_line: dict) -> list[tuple[str, float]] | None:
    """geometryのcharから、bit番号行の各数字のx中心を得る（[(番号, x)…]）。

    各bit列の中心を与える——列幅がまちまちでも、フィールドの跨ぐbit数を数える基準に
    なる。行の帯（y中心が行bbox内）にあるdigitをx空白で束ね、綴りが本当に降順bit列
    かを検証する（帯に別文字が混ざったら諦めてNone＝この表は変換しない）。
    """
    x0, top, _, bottom = number_line["bbox"]
    x1 = number_line["bbox"][2]

    def cy(char: dict) -> float:
        box = char["bbox"]
        return (box[1] + box[3]) / 2

    band = sorted((c for c in chars
                   if top - 1 <= cy(c) <= bottom + 1 and (c.get("text") or "").strip()
                   and x0 - 2 <= c["bbox"][0] and c["bbox"][2] <= x1 + 2),
                  key=lambda c: c["bbox"][0])
    if not band:
        return None
    groups: list[list[dict]] = [[band[0]]]
    for prev, cur in zip(band, band[1:]):
        if cur["bbox"][0] - prev["bbox"][2] > 2.5:
            groups.append([])
        groups[-1].append(cur)
    out: list[tuple[str, float]] = []
    for group in groups:
        token = "".join(c["text"] for c in group)
        if not token.isdigit():
            return None
        out.append((token, (group[0]["bbox"][0] + group[-1]["bbox"][2]) / 2))
    nums = [int(t) for t, _ in out]
    if len(nums) < 8 or any(a <= b for a, b in zip(nums, nums[1:])):
        return None
    if not all(0 <= n <= 31 for n in nums):
        return None
    return out


def _diagram_like(table: dict) -> bool:
    """bit図らしい表か（背が低く・短いセルだけ）。説明表（Bit/Name/Access…長文）を
    番号行の直下と誤って掴まないためのガード。"""
    x0, top, x1, bottom = table["bbox"]
    if bottom - top > 80:                       # 説明表は背が高い（数百pt）
        return False
    return all(len(c.get("text") or "") <= 40 for c in table["cells"])


def bitfield_pairs(page: dict) -> dict[str, str]:
    """{table_id: bit番号line_id}。番号行の直下（gap≤14pt・x重なり）の最寄り図。"""
    out: dict[str, str] = {}
    numlines = [l for l in page["lines"] if bit_numbers(l["text"])]
    for line in numlines:
        lx0, _, lx1, lbottom = line["bbox"]
        best, best_gap = None, 1e9
        for table in page["tables"]:
            tx0, top, tx1, _ = table["bbox"]
            gap = top - lbottom
            overlap = min(lx1, tx1) - max(lx0, tx0)
            if (0 <= gap <= 14 and gap < best_gap and overlap > 0.6 * (lx1 - lx0)
                    and _diagram_like(table)):
                best, best_gap = table["id"], gap
        if best is not None:
            out[best] = line["id"]
    return out


def apply_bitfield(table: dict, number_line: dict,
                   centers: list[tuple[str, float]]) -> None:
    """フィールドをbit番号のx中心で16等幅へ組み直す（in-place）。

    番号のx中心が「跨ぐbit数」を決める。空の箱は捨て、名前を持つセルだけを中心の
    包含で列に割り当て、番号のヘッダ行を上に足す。同じ列spanで縦に割れた名前は連結、
    どのセルも開始しない空き行は詰める（TIMの出力/入力2段は残る）。
    """
    if table.get("_bitfield"):
        return
    xs = [x for _, x in centers]
    width = len(centers)

    def bit_span(cell: dict) -> tuple[int, int]:
        # 半開区間[cx0, cx1)で中心を拾う——境界に載った中心は右隣のセルだけが取り、
        # 隣接セルが同じ列を二重に主張してグリッドが壊れるのを防ぐ。
        cx0, cx1 = cell["bbox"][0], cell["bbox"][2]
        idx = [i for i, x in enumerate(xs) if cx0 <= x < cx1]
        if idx:
            return idx[0], idx[-1] + 1
        # どの中心も含まないほど狭い/ずれたセルは、中点に最も近い1列へ寄せる
        mid = (cx0 + cx1) / 2
        near = min(range(width), key=lambda i: abs(xs[i] - mid))
        return near, near + 1

    fields = [c for c in table["cells"] if (c.get("text") or "").strip() and "bbox" in c]
    if not fields:
        return
    field_min = min(c["row_start"] for c in fields)
    cells: list[dict] = []
    for cell in fields:
        start, end = bit_span(cell)
        cells.append({**cell, "column_start": start, "column_end": end,
                      "row_start": cell["row_start"] - field_min + 1,
                      "row_end": cell["row_end"] - field_min + 1})
    for i, (num, _) in enumerate(centers):
        cells.append({"id": f"{table['id']}-bit{i}", "row_start": 0, "row_end": 1,
                      "column_start": i, "column_end": i + 1, "text": num,
                      "bbox": table["bbox"], "bold": False, "italic": False})
    # セル境界に載った1文字が隣のセルへ二重取りされる（`INTRSET14`の末尾`E`が右隣の
    # `Reserved`断片に入り`E Rese`／`USART`の`U`が左隣に入り`U\nRese…`）。**縦連結の前・
    # 行ごとに**、断片の先頭が「1文字＋空白/改行」でその文字が同じ行の左隣末尾2字か右隣
    # 先頭2字に重複するなら落とす——連結後だと`E`が識別子の内部に埋もれて捕まえられない。
    by_row: dict[int, list[dict]] = {}
    for cell in cells:
        if cell["row_start"] >= 1:
            by_row.setdefault(cell["row_start"], []).append(cell)
    for row_cells in by_row.values():
        row_cells.sort(key=lambda c: c["column_start"])
        for index, cell in enumerate(row_cells):
            text = cell.get("text") or ""
            if len(text) >= 2 and text[1] in " \n" and text[0].strip():
                left = (row_cells[index - 1]["text"] if index else "").rstrip()[-2:]
                right = (row_cells[index + 1]["text"]
                         if index + 1 < len(row_cells) else "").lstrip()[:2]
                if text[0] in left or text[0] in right:
                    cell["text"] = text[2:]
    # 同じ列span（狭い列）で縦に割れた名前を上のセルへ連結（`Reser`+`ved`＝Reserved）。
    # ただし連結するのは「1行レジスタで狭い列の名前が折り返した」ときだけ——広い
    # フィールドが両行に跨る（rowspan）のがその印。跨るセルが無ければ本当に2段の
    # フィールド行（byte境界PFICの`Reserved`行と`PRIO_*`行）なので連結せず2行で残す。
    has_span = any(c["row_end"] - c["row_start"] > 1
                   for c in cells if c["row_start"] >= 1)
    groups: dict[tuple[int, int], list[dict]] = {}
    for cell in cells:
        if cell["row_start"] >= 1:
            groups.setdefault((cell["column_start"], cell["column_end"]), []).append(cell)
    drop: list[dict] = []
    for group in groups.values():
        if len(group) == 1 or not has_span:
            continue
        group.sort(key=lambda c: c["row_start"])
        head = group[0]
        head["text"] = "".join((c.get("text") or "") for c in group)
        head["row_end"] = max(c["row_end"] for c in group)
        drop.extend(group[1:])
    for cell in drop:
        cells.remove(cell)
    # どのセルも開始しない行（縦割れが消えて空いた行）を詰める。開始行の集合で番号を
    # 振り直す——単純レジスタは1データ行に、TIMの出力名/入力名の2段は2行のまま残り、
    # CC1S[1:0]のような両モード共有名は両行にまたがる。
    starts = sorted({0} | {c["row_start"] for c in cells})
    remap = {orig: i for i, orig in enumerate(starts)}
    for cell in cells:
        cell["row_end"] = sum(1 for s in starts if s < cell["row_end"])
        cell["row_start"] = remap[cell["row_start"]]
    # 折り返し行は空白なしで繋ぐ——bit名は1個の識別子で、cell_htmlの英単語スペース判定が
    # `Rese`+`rved`を`Rese rved`にするのを防ぐ（境界の二重取りは連結前に落とし済み）。
    for cell in cells:
        if cell["row_start"] >= 1:
            cell["text"] = (cell.get("text") or "").replace("\n", "")
    # 描画順（行→列）に並べる。parityはセルのリスト順に読み進めるので、ヘッダ行を
    # 先頭に置かないと番号が「順序外」に見える。
    cells.sort(key=lambda c: (c["row_start"], c["column_start"]))
    # 同じ(row_start,column_start)へ複数セルが落ちることがある——ページ跨ぎで番号中心が
    # 実列数より少ない（27..16の12個に16列を詰める等）と、bit_spanのnearフォールバックが
    # 複数セルを端の1列へ束ねる。table_htmlのgridは`grid[r][c]=…`で後勝ちに上書きし可視は
    # 1つだが、parityはcells全部を読むため衝突セルが「順序外」に化ける。gridと同じく後勝ちで
    # 1つに畳み、描画とparityが必ず同じセル列を見るようにする（衝突の無い通常図には無影響）。
    deduped: dict[tuple[int, int], dict] = {}
    for cell in cells:
        deduped[(cell["row_start"], cell["column_start"])] = cell
    cells = sorted(deduped.values(),
                   key=lambda c: (c["row_start"], c["column_start"]))
    table["cells"] = cells
    table["column_count"] = width
    table["row_count"] = len(starts)
    table["_bitfield"] = True


def bitfield_singletons(page: dict) -> dict[str, str]:
    """{bit番号line_id: フィールドline_id}。直下に図テーブルが無く、帯にフィールド行が
    ちょうど1本だけある番号行（罫線の無い箱——全Reservedや単一フィールドの半分）。

    その1本は半分全体（全bit）を張る（中央寄せの短いテキストで、x範囲では列を張れない
    ——1本しか無いことが「全列」の根拠）。番号行〜次の番号行/表/40ptまでを帯とする。
    """
    paired = set(bitfield_pairs(page).values())
    numlines = [l for l in page["lines"] if bit_numbers(l["text"])]
    tops = sorted([l["bbox"][1] for l in numlines]
                  + [t["bbox"][1] for t in page["tables"]])
    out: dict[str, str] = {}
    for line in numlines:
        if line["id"] in paired:
            continue
        lx0, ltop, lx1, lbottom = line["bbox"]
        nexts = [t for t in tops if t > ltop + 2]
        band_end = min(min(nexts) if nexts else lbottom + 40, lbottom + 40)
        fields = [x for x in page["lines"]
                  if lbottom <= x["bbox"][1] < band_end and x["id"] != line["id"]
                  and x.get("role") in ("paragraph", "list-item")
                  and (x["text"] or "").strip() and not bit_numbers(x["text"])
                  and len(x["text"]) <= 40
                  and min(lx1, x["bbox"][2]) - max(lx0, x["bbox"][0]) > 0]
        if len(fields) == 1:
            out[line["id"]] = fields[0]["id"]
    return out


def build_bitfield_singleton(number_line: dict, field_line: dict,
                             centers: list[tuple[str, float]]) -> dict:
    """番号行＋全幅の単一フィールド行から、描画用のbit図テーブルを組み立てる。"""
    width = len(centers)
    cells = [{"id": f"{number_line['id']}-bit{i}", "row_start": 0, "row_end": 1,
              "column_start": i, "column_end": i + 1, "text": num,
              "bbox": number_line["bbox"], "bold": False, "italic": False}
             for i, (num, _) in enumerate(centers)]
    cells.append({"id": f"{number_line['id']}-field", "row_start": 1, "row_end": 2,
                  "column_start": 0, "column_end": width, "text": field_line["text"],
                  "bbox": field_line["bbox"],
                  "bold": bool(field_line.get("bold")),
                  "italic": bool(field_line.get("italic"))})
    return {"id": f"{number_line['id']}-bitfield", "cells": cells,
            "column_count": width, "row_count": 2, "caption": None, "issues": [],
            "logical_id": f"{number_line['id']}-bitfield", "_bitfield": True}


def _body_lines(page: dict) -> list[dict]:
    return [line for line in page["lines"]
            if line.get("role") not in ("header", "footer")]


def _continues(previous_page: dict, page: dict,
               previous_table: dict, table: dict) -> bool:
    if table.get("caption"):
        return False
    height_prev = previous_page["height"]
    height = page["height"]
    if previous_table["bbox"][3] < height_prev * BOTTOM_BAND:
        return False
    if table["bbox"][1] > height * TOP_BAND:
        return False
    if any(line["bbox"][1] > previous_table["bbox"][3] - 1
           for line in _body_lines(previous_page)):
        return False
    if any(line["bbox"][3] < table["bbox"][1] + 1
           for line in _body_lines(page)):
        return False
    return compatible(fragment_edges(previous_table), fragment_edges(table))


def document_chains(pages: list[dict]) -> dict[str, dict]:
    """全ページの表 → {table_id: {"chain": [(page, table), ...], "start": bool}}。

    連鎖に入らない表は自分だけのchainになる。呼ぶ側はreading_orderで表に
    出会ったとき、start=Trueなら結合表を描き、Falseなら「前のページで描画済み」
    のポインタを置く。
    """
    # bit図（番号行の直下の図）はページ跨ぎで結合しない——1〜3行で自己完結し、
    # 背中合わせに並ぶと誤結合しやすい（結合セルはbboxを持たずbit図の組み直しが
    # 壊れる）。連結の開始側・継続側の両方から外す。
    bitfield_ids: set[str] = set()
    for page in pages:
        bitfield_ids |= set(bitfield_pairs(page).keys())

    chains: list[list[tuple[int, dict]]] = []
    open_chain: list[tuple[int, dict]] | None = None
    previous_page: dict | None = None

    for page in pages:
        tables = sorted(page["tables"], key=lambda t: (t["bbox"][1], t["bbox"][0]))
        for index, table in enumerate(tables):
            if (index == 0 and open_chain is not None and previous_page is not None
                    and page["number"] == previous_page["number"] + 1
                    and table["id"] not in bitfield_ids
                    and open_chain[-1][1]["id"] not in bitfield_ids
                    and _continues(previous_page, page, open_chain[-1][1], table)):
                open_chain.append((page["number"], table))
            else:
                open_chain = [(page["number"], table)]
                chains.append(open_chain)
        if not tables:
            open_chain = None
        previous_page = page

    out: dict[str, dict] = {}
    for chain in chains:
        merged = merge_cells(chain) if len(chain) > 1 else None
        for position, (_, table) in enumerate(chain):
            out[table["id"]] = {
                "chain": chain,
                "start": position == 0,
                "merged": merged,
                "start_page": chain[0][0],
            }
    return out
