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


def text_grid(merged: dict) -> tuple[list[list[str | None]], list[int]]:
    """結合済み論理表 → 文字の格子（抽出器向け。spanの先頭位置に文字を置く）。"""
    rows: list[list[str | None]] = [[None] * merged["width"]
                                    for _ in range(merged["row_count"])]
    for cell in merged["cells"]:
        rows[cell["row_start"]][cell["column_start"]] = cell["text"]
    return rows, merged["row_pages"]


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
