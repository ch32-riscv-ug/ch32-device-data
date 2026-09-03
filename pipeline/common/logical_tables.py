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


def strip_straddling_dupes(table: dict, chars: list[dict]) -> int:
    """図セルの端で**グリフ中心がセル外**にある1-2文字を落とす（境界を跨いで隣セルへ
    二重取りされたグリフ）。

    `ReservedR`（`R`のグリフ中心が右隣の列に在る）や`Reserved\\nT`（`T`の中心が左隣に
    在る）のように、末尾の重複文字が**テキスト隣接セルの境界文字と一致しない**——別の
    行/列から跨いだ——ケースはstrip_boundary_dupesでは捕まらない。ここでは各セルに
    実際に載っているグリフ（中心がbbox内）を綴り直し、textがそれより端に1-2文字だけ
    多いぶんを重複とみて落とす。空白/改行の有無に依らずgeometryで判定するので安全。
    レジスタbit図のセルにだけ効かせる（exporter・parity検査が同じ生セルへ適用＝整合）。
    canonical抽出器は呼ばない（凍結CSVはEVTヘッダ基準で無関係）。冪等。
    """
    if table.get("_straddle_stripped"):
        return 0
    table["_straddle_stripped"] = True
    removed = 0
    for cell in table["cells"]:
        text = cell.get("text") or ""
        if "bbox" not in cell or not text.strip():
            continue
        x0, y0, x1, y1 = cell["bbox"]
        own = "".join(
            g["text"] for g in sorted(
                (g for g in chars if (g.get("text") or "").strip()
                 and y0 - 0.5 <= (g["bbox"][1] + g["bbox"][3]) / 2 <= y1 + 0.5
                 and x0 - 0.5 <= (g["bbox"][0] + g["bbox"][2]) / 2 <= x1 + 0.5),
                key=lambda g: (round(g["bbox"][1]), g["bbox"][0])))
        core = text.replace("\n", "").replace(" ", "")
        extra = len(core) - len(own)
        if len(own) < 2 or not 0 < extra <= 2:
            continue
        # **改行で別視覚行に分離された端文字だけ**落とす。狭い列で名前がセル幅を
        # 超えてあふれると実文字の中心もセル外に落ちる（`SWIE`+`R 22`＝SWIER22の
        # `R`、`USART`の先頭`U`）——これは同じ視覚行なので触らない。真の二重取りは
        # 隣の**行**からグリフが降って来る（`Reserve\nd\nR`の`R`）ので改行で分かれる。
        if core.startswith(own) and _edge_newline_separated(text, extra, tail=True):
            cell["text"] = _drop_edge_chars(text, extra, tail=True)
            removed += 1
        elif core.endswith(own) and _edge_newline_separated(text, extra, tail=False):
            cell["text"] = _drop_edge_chars(text, extra, tail=False)
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
