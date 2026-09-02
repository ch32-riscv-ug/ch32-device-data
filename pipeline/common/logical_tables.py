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

    1ずつ厳密に降順・長さ8/16/32・全て0..31——bit図に固有の並びで、本文中の
    数字列と衝突しない。
    """
    tokens = text.split()
    if len(tokens) not in (8, 16, 32) or not all(t.isdigit() for t in tokens):
        return None
    nums = [int(t) for t in tokens]
    if any(a - b != 1 for a, b in zip(nums, nums[1:])):
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
    if len(nums) not in (8, 16, 32) or any(a - b != 1 for a, b in zip(nums, nums[1:])):
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

    def bit_span(cell: dict) -> tuple[int, int] | None:
        cx0, cx1 = cell["bbox"][0], cell["bbox"][2]
        idx = [i for i, x in enumerate(xs) if cx0 - 1 <= x <= cx1 + 1]
        if idx:
            return idx[0], idx[-1] + 1
        # どの中心も含まないほど狭い/ずれたセルは、中点に最も近い1列へ寄せる
        mid = (cx0 + cx1) / 2
        near = min(range(width), key=lambda i: abs(xs[i] - mid))
        return near, near + 1

    fields = [c for c in table["cells"] if (c.get("text") or "").strip()]
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
    # 同じ列span（狭い列）で縦に割れた名前を上のセルへ連結（`Reser`+`ved`＝Reserved）。
    groups: dict[tuple[int, int], list[dict]] = {}
    for cell in cells:
        if cell["row_start"] >= 1:
            groups.setdefault((cell["column_start"], cell["column_end"]), []).append(cell)
    drop: list[dict] = []
    for group in groups.values():
        if len(group) == 1:
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
    # 描画順（行→列）に並べる。parityはセルのリスト順に読み進めるので、ヘッダ行を
    # 先頭に置かないと番号が「順序外」に見える。
    cells.sort(key=lambda c: (c["row_start"], c["column_start"]))
    table["cells"] = cells
    table["column_count"] = width
    table["row_count"] = len(starts)
    table["_bitfield"] = True


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
    chains: list[list[tuple[int, dict]]] = []
    open_chain: list[tuple[int, dict]] | None = None
    previous_page: dict | None = None

    for page in pages:
        tables = sorted(page["tables"], key=lambda t: (t["bbox"][1], t["bbox"][0]))
        for index, table in enumerate(tables):
            if (index == 0 and open_chain is not None and previous_page is not None
                    and page["number"] == previous_page["number"] + 1
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
