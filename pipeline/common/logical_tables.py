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

import functools
import re
from collections import Counter

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


def _snap(edges: list[float], x: float) -> int:
    return min(range(len(edges)), key=lambda i: abs(edges[i] - x))


def _ghost_free_edges(per: list[tuple], merged_edges: list[float]) -> list[float] | None:
    """**断片より列が増えた**結合表で、幽霊列を消せる基準の境界を返す（無ければNone）。

    列境界は断片の**和集合**（`_union_edges`）なので、片方のページの余分な境界が論理表
    全体へ伝播する。`compatible`が+2列まで許すため、5列の表が6列になり**どのセルも
    占めていない列**が1本挟まる——`CH32M030RM.en` p46では見出しが7つの列枠に対し本文が
    1,1,2,1,2と並び、`Name`が2〜3列目・`RO`が3〜4列目と**ラベルと値が1つずれて**いた
    （再突合の指摘。`CH32xRM.zh` p179は`R32_USART3_GPR`が空セルになっていた）。

    **境界の最も多い断片を基準に寄せ直す**が、次を両方満たすときだけ——満たさないなら
    和集合のまま（安全側）:

    - どの断片のどのセルも**colspanが変わらない**（消えるのは占有されていない列だけ）
    - 同じ行で2つのセルが同じ列に**衝突しない**

    全corpus実測: 断片より列が増えた結合表は47件（+81列）で衝突は**0件**。うち
    colspanが保たれるのが**14件**で、そこだけ寄せる。幅が変わる33件（`CH32X315DS0.en`
    p22の70セル等）は断片の境界が大きく食い違うので触らない。
    """
    reference = max((edges for _, _, edges in per), key=len)
    if len(merged_edges) <= len(reference):
        return None
    for _, table, _ in per:
        seen: set[tuple[int, int]] = set()
        for cell in table["cells"]:
            start = _snap(reference, round(cell["bbox"][0], 2))
            end = max(_snap(reference, round(cell["bbox"][2], 2)), start + 1)
            if end - start != cell["column_end"] - cell["column_start"]:
                return None
            if (cell["row_start"], start) in seen:
                return None
            seen.add((cell["row_start"], start))
    return reference


def merge_cells(fragments: list[tuple[int, dict]]) -> dict:
    """断片列 → 結合済み論理表。セルはグローバルな行/列番号を持つ。"""
    per = [(page, table, fragment_edges(table)) for page, table in fragments]

    reference_edges: list[float] | None = None
    if len({len(edges) for _, _, edges in per}) == 1:
        index_maps = [{edge: i for i, edge in enumerate(edges)} for _, _, edges in per]

        def column(fragment: int, x: float) -> int:
            return index_maps[fragment][x]
        width = len(per[0][2]) - 1
    else:
        merged_edges = _union_edges([edges for _, _, edges in per])
        # 幽霊列を消せる基準の境界を**記録するだけ**（適用は人向け経路）。
        reference_edges = _ghost_free_edges(per, merged_edges)

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
                # converterが下付きを戻す前の綴り（あれば）。版面の割り方＝下付きの
                # 境界を要る抽出器が`text_grid(..., "text_split")`で引く。
                **({"text_split": cell["text_split"]} if "text_split" in cell else {}),
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
        # 人向け経路だけが使う（`snap_ghost_columns`）。canonicalの列番号は動かさない。
        **({"_reference_edges": reference_edges} if reference_edges else {}),
    }


def drop_repeated_headers(merged: dict) -> int:
    """ページ跨ぎの結合表で、**続き断片の先頭に印字し直された列見出し**を落とす。

    datasheetのpin定義表は各ページの先頭に同じ見出し（`Pin No.`/`Pin name`/…、2〜6行に
    折り返す）を刷り直す。結合表ではそれが本文行として途中に何度も現れていた（L103DS0・
    V006DS0・V203DS0で各ページぶん。全面見直しの指摘）。断片の開始行から k 行（k≤8）の文字を
    連結したものが、表の先頭 k 行の連結と一致するときだけ、その k 行を落として行番号を詰める。
    exporterとparityが同じ順で呼ぶ。冪等。
    """
    if merged.get("_headers_dropped"):
        return 0
    merged["_headers_dropped"] = True
    row_pages = merged.get("row_pages")
    if not row_pages:
        return 0
    by_row: dict[int, list[tuple[int, str]]] = {}
    for cell in merged["cells"]:
        text = "".join((cell.get("text") or "").split())
        if text:
            by_row.setdefault(cell["row_start"], []).append((cell["column_start"], text))

    def signature(start: int, k: int) -> tuple:
        # 列ごとに文字を連結してから並べる——刷り直しの見出しは同じ語でも行の割れ方が違う
        # （`主功能（复位后）`が1行のページと`主功能`/`（复位`/`后）`の3行のページ）。
        cols: dict[int, str] = {}
        for r in range(start, start + k):
            for col, text in sorted(by_row.get(r, [])):
                cols[col] = cols.get(col, "") + text
        return tuple(sorted(cols.items()))

    header_height = max([c["row_end"] for c in merged["cells"] if c["row_start"] == 0] or [1])
    heads = {signature(0, h) for h in range(1, max(header_height, 1) + 1)}
    heads.discard(())
    starts = [i for i in range(1, len(row_pages)) if row_pages[i] != row_pages[i - 1]]
    drop: set[int] = set()
    for s in starts:
        for k in range(8, 0, -1):
            if s + k > len(row_pages) or any(r in drop for r in range(s, s + k)):
                continue
            if signature(s, k) in heads:
                drop.update(range(s, s + k))
                break
    if not drop:
        return 0
    keep = [r for r in range(len(row_pages)) if r not in drop]
    remap = {old: new for new, old in enumerate(keep)}
    cells = []
    for cell in merged["cells"]:
        rows = [r for r in range(cell["row_start"], cell["row_end"]) if r not in drop]
        if not rows:
            continue
        cell["row_start"], cell["row_end"] = remap[rows[0]], remap[rows[-1]] + 1
        cells.append(cell)
    merged["cells"] = cells
    merged["row_pages"] = [row_pages[r] for r in keep]
    merged["row_count"] = len(keep)
    return len(drop)


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
        # **1行ぶんの高さ**であればcolspanは許す（1.10.2）。畳み先は「同じ列範囲」で
        # 決めるので、列がずれる余地は無い——`USBHS (USB`＋`2.0)`はどちらもcolspan=2で、
        # 1行1列だけを許す旧条件では弾かれ、幽霊行が残っていた（H417DS0.en p3/p4）。
        single = cell["row_end"] - cell["row_start"] == 1
        if single:
            simple[(cell["row_start"], cell["column_start"])] = cell
        if cell["text"].strip():
            by_row.setdefault(cell["row_start"], []).append((cell, single))
    removed: list[dict] = []
    for row in sorted(by_row):
        if row == 0 or row >= len(row_pages) or row_pages[row] == row_pages[row - 1]:
            continue
        occupied = by_row[row]
        if len(occupied) == 1:
            cell, single = occupied[0]
            if not single:
                continue
            prev = simple.get((row - 1, cell["column_start"]))
            if prev is None or not prev["text"].strip():
                continue
            if prev["column_end"] != cell["column_end"]:
                continue   # 列範囲が違うなら畳み先が一意でない
            prev["text"] = prev["text"] + "\n" + cell["text"]
            removed.append(cell)   # 継続セルはグリッドから消す（空行を残さない）
            continue
        # **複数セルの畳み込みは撤退**（2026-09-06）。`默认复用功能`と`重映射功能`が同時に
        # 次ページへ溢れた行を1行に畳む一般化を入れたが、**畳んだ行が他の列をrowspanで
        # 覆っていた場合に列がずれる**回帰を生んだ（L103DS0.zh p23/p24でPB5の値が引脚编号の
        # 列に出た。全面見直しの検証3巡目）。得られたのは全corpus22行に対し、崩れは
        # pin表の実データなので割に合わない。中身が1つの行だけを畳む元の規則に戻す。
    for cell in removed:
        merged["cells"].remove(cell)
    # 継続セルを消した行番号（他の列の空セルだけが残る＝描画時に落とす行）。
    merged["_folded_rows"] = sorted(c["row_start"] for c in removed)
    return len(removed)


def extend_boundary_spans(merged: dict) -> int:
    """**ページ境界で切れた縦の結合セルを1つに戻す**（1.10.2）。戻した数を返す。

    背の高い結合セル（`VIL`が標準I/OとFT I/Oの両ブロックを覆う等）は、pdfplumberに
    ページの切れ目で切られる。前ページ側は下端で止まったセル、次ページ側は**中身の無い
    セル**になる（続きの箱に上枠が無い）。結合表ではその2つが別のセルとして並び、
    しかも続き側は`fold_boundary_spills`が畳んだ行から始まるため**描画時に丸ごと落ちて
    列が1つ足りなくなる**——`CH32H417DS0.en` p104の表3-19では「FT I/O pin, input low level
    voltage」の3行が7列ではなく6列になり、条件がSymbol欄に、値がCondition/Min欄に出て
    **Unit欄が消えていた**（2026-09-07の検証ラウンドがhigh 3件として指摘）。

    条件は狭い——(1)ページ境界の行から始まり、(2)**中身が空**で、(3)**直上のセルと
    列範囲が完全に一致**し、(4)直上のセルが境界でちょうど終わっていて中身が空でない。
    この形はpdfplumberが箱を切ったときの署名。空セルを上へ吸収するので、描画される
    文字は変わらない（元から空）——変わるのは**行の列数が揃うこと**だけ。
    """
    if merged.get("_spans_extended"):
        return 0
    merged["_spans_extended"] = True
    row_pages = merged.get("row_pages")
    if not row_pages:
        return 0
    boundaries = {r for r in range(1, min(merged["row_count"], len(row_pages)))
                  if row_pages[r] != row_pages[r - 1]}
    if not boundaries:
        return 0
    ends: dict[tuple[int, int, int], dict] = {}
    for cell in merged["cells"]:
        ends[(cell["row_end"], cell["column_start"], cell["column_end"])] = cell
    # **その行が自分の中身を持つなら触らない**（2026-09-08）。「境界の空セル＋直上が
    # 境界でちょうど終わる」形は、箱が切られた場合と**次ページの行が正当にその列だけ
    # 空**な場合で見分けが付かない。中身のある行へ吸わせると、直上の値がその行に
    # 被さって**値の捏造**になる——`CH32M030DS2.zh` p3/p4で`17|25|ISP1`の行が上の
    # `PA8`の`ADC_IN7/MCO/…`と`SPI_MOSI_3`を持つ形になった（再突合が指摘）。
    # 全corpus実測: 発火11,015件のうち1,185件が中身のある行＝捏造、9,830件が
    # `fold_boundary_spills`で空になった行＝安全。取りこぼす側（結合を戻さず空セルの
    # まま）は列数が合ったままなので無害で、誤りの向きが非対称。
    own_content = {cell["row_start"] for cell in merged["cells"]
                   if (cell.get("text") or "").strip()}
    absorbed = []
    for cell in merged["cells"]:
        if cell["row_start"] not in boundaries or (cell["text"] or "").strip():
            continue
        if cell["row_start"] in own_content:
            continue
        above = ends.get((cell["row_start"], cell["column_start"], cell["column_end"]))
        if above is None or not (above["text"] or "").strip():
            continue
        above["row_end"] = cell["row_end"]
        absorbed.append(cell)
    for cell in absorbed:
        merged["cells"].remove(cell)
    return len(absorbed)


def drop_empty_boundary_rows(merged: dict) -> int:
    """**ページ境界に残った「セルが1つも無い行」をグリッドから消す**。消した数を返す。

    `fold_boundary_spills`が継続セルを畳み、`extend_boundary_spans`が残りの空セルを
    上へ吸い上げると、その行には**セルが1つも残らない**。exporterはそれを空の`<tr>`
    として出し、しかも跨いでいる結合セルのrowspanが1つ余分になる——`CH32H417DS0.en`
    p104の表3-19では`VIL`がPDFの6行ぶんに対し7、`Standard I/O …`が3に対し4になり、
    値の欄を横に割る空の帯が出ていた（同 p3のPDUSBはrowspan=5対PDF4行、
    `CH32L103DS0.zh` p21・`CH32L103RM.en` p13も同形。再突合が指摘）。

    落とすのは**境界行かつセルが0個**のものだけ——文字を持つセルは1つも無いので
    出力の文字は変わらず、変わるのはrowspanと行数だけ。同一ページ内のセル0行
    （結合の段で空いた穴。全corpus8件）は原因が別なので触らない。冪等。

    行番号の詰め直しは間違えやすいので例で固定する。跨いでいるセルは下端が詰まり、
    下にある行は繰り上がる:

    >>> def c(r0, r1, text=""):
    ...     return {"row_start": r0, "row_end": r1, "column_start": 0,
    ...             "column_end": 1, "text": text}
    >>> t = {"id": "t", "row_count": 4, "row_pages": [1, 1, 2, 2],
    ...      "cells": [c(0, 1, "a"), c(1, 3, "span"), c(3, 4, "d")],
    ...      "_folded_rows": [2]}
    >>> drop_empty_boundary_rows(t), t["row_count"], t["row_pages"]
    (1, 3, [1, 1, 2])
    >>> [(x["row_start"], x["row_end"], x["text"]) for x in t["cells"]]
    [(0, 1, 'a'), (1, 2, 'span'), (2, 3, 'd')]

    **自分の中身を持つ境界行は消さない**（`extend_boundary_spans`が実データ行へ
    吸い上げるのを止めたのと同じ理由。これを消すと値が1行ぶん繰り上がる）:

    >>> t = {"id": "t", "row_count": 3, "row_pages": [1, 2, 2],
    ...      "cells": [c(0, 1, "a"), c(1, 2, "real"), c(2, 3, "b")]}
    >>> drop_empty_boundary_rows(t), t["row_count"]
    (0, 3)

    消える行から始まって**下へ続く**空セルは、次の行から始まるセルへ読み替える:

    >>> t = {"id": "t", "row_count": 4, "row_pages": [1, 2, 2, 2],
    ...      "cells": [c(0, 1, "a"), c(1, 2), c(1, 4), c(2, 3, "c")],
    ...      "_folded_rows": [1]}
    >>> drop_empty_boundary_rows(t), t["row_count"]
    (1, 3)
    >>> sorted((x["row_start"], x["row_end"], x["text"]) for x in t["cells"])
    [(0, 1, 'a'), (1, 2, 'c'), (1, 3, '')]
    """
    if merged.get("_rows_dropped"):
        return 0
    merged["_rows_dropped"] = True
    row_pages = merged.get("row_pages")
    if not row_pages:
        return 0
    count = merged.get("row_count", 0)
    have = {cell["row_start"] for cell in merged["cells"]}
    texted = {cell["row_start"] for cell in merged["cells"]
              if (cell.get("text") or "").strip()}
    folded = set(merged.get("_folded_rows", ()))
    gone = {row for row in range(1, min(count, len(row_pages)))
            if row not in texted and row_pages[row] != row_pages[row - 1]
            and (row not in have or row in folded)}
    if not gone:
        return 0
    _remove_rows(merged, gone)
    return len(gone)


def _remove_rows(table: dict, gone: set[int]) -> None:
    """指定した行をグリッドから消す（跨ぐセルの下端を詰め、以降の行を繰り上げる）。

    消える行に**空セルが残っている**ことがある——`extend_boundary_spans`は直上が空の列
    （`Typ.`のように全行空）を吸い上げないので、1つだけ残って行が消えなかった
    （`CH32H417DS0.en` p104の空帯が残った理由）。下へ続く空セルは**次の行から始まる
    セル**に読み替え、その行だけの空セルは落とす。文字は無いので失われない。
    """
    if not gone:
        return
    count = table.get("row_count", 0)
    # 消える行が2つ続く場合もあるので、どのセルも消える行から始まらなくなるまで繰り返す。
    while any(cell["row_start"] in gone for cell in table["cells"]):
        for cell in list(table["cells"]):
            if cell["row_start"] not in gone:
                continue
            if cell["row_end"] - cell["row_start"] > 1:
                cell["row_start"] += 1
            else:
                table["cells"].remove(cell)
    for cell in table["cells"]:
        # 跨いでいる途中の行が消えるぶんだけ下端を詰め、下にある行はまとめて繰り上げる。
        cell["row_end"] -= sum(1 for row in gone
                               if cell["row_start"] < row < cell["row_end"])
        shift = sum(1 for row in gone if row < cell["row_start"])
        cell["row_start"] -= shift
        cell["row_end"] -= shift
    table["row_count"] = count - len(gone)
    row_pages = table.get("row_pages")
    if row_pages:
        table["row_pages"] = [page for row, page in enumerate(row_pages) if row not in gone]
    if table.get("_folded_rows"):
        table["_folded_rows"] = sorted(
            row - sum(1 for dead in gone if dead < row)
            for row in table["_folded_rows"] if row not in gone)


def snap_ghost_columns(merged: dict) -> int:
    """**幽霊列を消す**（`merge_cells`が記録した基準の境界へ寄せる）。消えた列数を返す。

    列境界は断片の**和集合**（`_union_edges`）なので、片方のページの余分な境界が論理表
    全体へ伝播する。`compatible`が+2列まで許すため、5列の表が6列になり隣のセルの
    colspanが伸びて**ラベルと値が1つずれる**——`CH32M030RM.en` p46では見出しが7つの列枠に
    対し本文が1,1,2,1,2と並び、`Name`が2〜3列目・`RO`が3〜4列目に出ていた
    （`CH32xRM.zh` p179は`R32_USART3_GPR`の行が空セルになっていた。再突合の指摘）。

    寄せられるかの判定は`merge_cells`が済ませている（`_reference_edges`。境界の最も
    多い断片で、どの断片のどのセルもcolspanが変わらず衝突もしないときだけ記録される）。
    ここでは各セルの`src_bbox`をその境界へ寄せ直す。

    **人向け出力専用**（exporterとparity検査だけが呼ぶ）——`merge_cells`の列番号を
    動かすと正規CSVに効く。`merge_cells`側で寄せた版を試したところ
    `evidence/operating_conditions.csv`にX315の偽行（`typ=enabled`）が1行増え、
    zhの異論がStop mode行から奪われた（`check_baseline`が捕捉。2026-09-08に撤退して
    この形に組み替えた）。canonicalは和集合の列番号のまま、人向けだけ寄せる。

    全corpus実測: 断片より列が増えた結合表47件のうち、寄せても壊れないのが**14件**。
    幅が変わる33件（`CH32X315DS0.en` p22の70セル等）は断片の境界が大きく食い違うので
    `merge_cells`が記録しない。冪等（`_ghost_snapped`）。
    """
    if merged.get("_ghost_snapped"):
        return 0
    merged["_ghost_snapped"] = True
    reference = merged.get("_reference_edges")
    if not reference:
        return 0
    before = merged.get("width") or merged.get("column_count") or 0
    for cell in merged["cells"]:
        box = cell.get("src_bbox") or cell.get("bbox")
        if not box:
            return 0   # 座標が無いセルがあるなら触らない（bit図の合成など）
        start = _snap(reference, round(box[0], 2))
        cell["column_start"] = start
        cell["column_end"] = max(_snap(reference, round(box[2], 2)), start + 1)
    merged["width"] = len(reference) - 1
    if "column_count" in merged:
        merged["column_count"] = merged["width"]
    merged["cells"].sort(key=lambda c: (c["row_start"], c["column_start"]))
    return before - merged["width"]


def spell_glyphs(glyphs: list[dict]) -> str:
    """グリフ列を読み順（行→x）で綴る。**語の間の空白を隙間から復元する**。

    表の外から取り込む列（converterの`recover_outer_column`・`fill_grid_holes`、人向け
    経路の`recover_chain_columns`）は、pdfplumberのセル抽出を通らないので区切りが入らず
    `Resetvalue`・`Filterregister0`になっていた。converter 1.10.0で`convert.py`に書き、
    人向け経路も同じ綴りを使うためここへ移した（converterは名前を残して委譲。出力は同一）。

    - **視覚行の切れ目は`\\n`**にする。狭い列では見出しも値も折り返され、`Reset`/`value`
      は空白で繋ぐべきで`0xFFF`/`F`は繋いではいけない——この判定は既に
      `cell_html`（行末・行頭の文字種で折り返しか意図的な改行かを分ける）が持っている
      ので、そちらへ渡す。改行を入れずに繋いでいたので`Resetvalue`になっていた。
    - **同じ視覚行の語間の空白**は隙間から復元する。隙間が**グリフ幅の中央値の0.35倍**を
      超え、かつ両側がASCIIなら空白（CJKは字間が広く、識別子`R32_ESIG_FLACAP`のような
      連続は隙間が空かない）。全corpus実測: 空白が入るのは35セルで全部`Reset value`型の
      見出し。閾値0.25〜0.50で結果が同じ＝隙間が明確に分かれているので真ん中を採る。
      値のセル（`0xFFFF`・`[31:0]`）は1つも変わらない。

    >>> spell_glyphs([{"text": "R", "bbox": [0, 0, 5, 10]}, {"text": "e", "bbox": [5, 0, 10, 10]},
    ...               {"text": "v", "bbox": [14, 0, 19, 10]}, {"text": "0", "bbox": [0, 12, 5, 22]}])
    'Re v\\n0'
    """
    ordered = sorted(glyphs, key=lambda g: (round(g["bbox"][1], 1), g["bbox"][0]))
    if not ordered:
        return ""
    widths = sorted(g["bbox"][2] - g["bbox"][0] for g in ordered)
    median = widths[len(widths) // 2]
    out: list[str] = []
    for index, glyph in enumerate(ordered):
        if index:
            previous = ordered[index - 1]
            both_ascii = previous["text"].isascii() and glyph["text"].isascii()
            if abs(glyph["bbox"][1] - previous["bbox"][1]) >= 1.0:
                out.append("\n")
            elif (both_ascii
                    and glyph["bbox"][0] - previous["bbox"][2] > median * 0.35):
                out.append(" ")
        out.append(glyph["text"])
    return "".join(out)


def recover_chain_columns(merged: dict, chars_for) -> int:
    """**継続断片に欠けた最外列**を、結合表の列境界とページのgeometryから埋める。
    足したセル数を返す。

    ページ跨ぎの結合表で、続きのページの断片だけ最外列（レジスタ名・`Bit`・`Reset value`）
    の罫線が拾われず列数が1つ少ないと、その列の値が**Markdownのどこにも出ない**——
    `CH32xRM.zh` p179-180の`R32_USART3_GPR`（再突合の指摘。行が`| 0x40004818 | UASRT3保护
    时间和预分频 | | 0x00000000 |`と名無しになっていた）。converterの`recover_outer_column`
    は**その断片1つだけ**を見て「1列ぶんの幅・全行帯に中身」を要求するので、断片が1行の
    ときや外側グリフの幅が判断できないときは触れない。結合表なら先頭断片が持つ列の
    **x範囲**が分かるので、入れ先が一意に決まる。

    手順（断片ごと）: 単独列セルの`src_bbox`から列0と列(width-1)のx範囲を取り、断片の
    行帯（自セルの`src_bbox`のy境界）ごとにその範囲の中心を持つグリフを`spell_glyphs`で
    綴る。次を全部満たすときだけ足す:

    - 結合表が3列以上で、断片の列数が結合表より少ない
    - **すべての行帯に中身がある**（1つでも空なら列ではない）
    - 既にセルがある座標には足さない（rowspanの続き・converterが埋めた列はそのまま）

    全corpus実測（converter 1.14.0）: 候補190断片のうち、1,225セルはconverterが既に同じ
    文字で埋めていて、88セルは行/列をまたぐ既存セルの部分読み（触らない）。足すのは
    **18表33セル**で、全件目視: レジスタ名12（`R32_CRC_CTLR`・`R32_GPIOC_SPEED`・
    `R32_FLASH_BOOT_MODEKEYR`…）、bit範囲2、reset値4、見出し4（`Bit`・`Reset value`・
    `复位值`）、記述子名3（`TDes5-7`）、ページ末で見出し行の外2列が落ちた`RB_UEPn`/
    `Description: The address…`（`CH32M030RM.en` p226）。

    **人向け出力専用**（exporterとparity検査が同じ順で呼ぶ）。canonicalの列番号や
    `extracted_rows`は動かさない。`snap_ghost_columns`の**後**に呼ぶ（列番号が確定して
    から穴を見る）。冪等（`_chain_recovered`）。

    >>> merged = {"width": 3, "row_pages": [1, 2], "parts": [(1, "a"), (2, "b")], "cells": [
    ...     {"row_start": 0, "row_end": 1, "column_start": 0, "column_end": 1, "text": "Name",
    ...      "src_bbox": [10, 0, 50, 10], "page": 1},
    ...     {"row_start": 0, "row_end": 1, "column_start": 1, "column_end": 2, "text": "Addr",
    ...      "src_bbox": [50, 0, 90, 10], "page": 1},
    ...     {"row_start": 0, "row_end": 1, "column_start": 2, "column_end": 3, "text": "Reset",
    ...      "src_bbox": [90, 0, 130, 10], "page": 1},
    ...     {"row_start": 1, "row_end": 2, "column_start": 1, "column_end": 2, "text": "0x40",
    ...      "src_bbox": [50, 0, 90, 10], "page": 2},
    ...     {"row_start": 1, "row_end": 2, "column_start": 2, "column_end": 3, "text": "0",
    ...      "src_bbox": [90, 0, 130, 10], "page": 2}]}
    >>> glyphs = {2: [{"text": ch, "bbox": [12 + 4 * i, 1, 15 + 4 * i, 9]}
    ...               for i, ch in enumerate("R32_X")]}
    >>> recover_chain_columns(merged, lambda page: glyphs.get(page, []))
    1
    >>> [c["text"] for c in merged["cells"] if c["row_start"] == 1]
    ['R32_X', '0x40', '0']
    >>> recover_chain_columns(merged, lambda page: glyphs.get(page, []))   # 冪等
    0
    """
    if merged.get("_chain_recovered") or not merged.get("parts"):
        return 0
    merged["_chain_recovered"] = True
    width = merged.get("width") or merged.get("column_count") or 0
    cells = merged["cells"]
    if width < 3 or any(not c.get("src_bbox") for c in cells):
        return 0
    spans: dict[int, list[float]] = {}     # 列 → 単独列セルのx範囲（全断片の和）
    for cell in cells:
        if cell["column_end"] - cell["column_start"] == 1:
            box = cell["src_bbox"]
            span = spans.setdefault(cell["column_start"], [box[0], box[2]])
            span[0], span[1] = min(span[0], box[0]), max(span[1], box[2])
    covered = {(r, k) for c in cells for r in range(c["row_start"], c["row_end"])
               for k in range(c["column_start"], c["column_end"])}
    row_pages = merged.get("row_pages") or []
    added = 0
    for page, _table_id in merged["parts"]:
        rows = [r for r, p in enumerate(row_pages) if p == page]
        own = [c for c in cells if c.get("page") == page and not c.get("_chain_recovered")]
        if not rows or not own:
            continue
        ys = sorted({round(c["src_bbox"][1], 2) for c in own}
                    | {round(c["src_bbox"][3], 2) for c in own})
        xs = {round(c["src_bbox"][0], 2) for c in own} | {round(c["src_bbox"][2], 2) for c in own}
        if len(ys) != len(rows) + 1 or len(xs) - 1 >= width:
            continue
        glyphs: list[dict] | None = None
        for column in (0, width - 1):
            if column not in spans or all((r, column) in covered for r in rows):
                continue
            cx0, cx1 = spans[column]
            if glyphs is None:
                glyphs = [g for g in chars_for(page) if (g.get("text") or "").strip()]
            found: list[str] = []
            for index in range(len(rows)):
                y0, y1 = ys[index], ys[index + 1]
                inside = [g for g in glyphs
                          if cx0 + 0.5 <= (g["bbox"][0] + g["bbox"][2]) / 2 <= cx1 - 0.5
                          and y0 + 0.5 <= (g["bbox"][1] + g["bbox"][3]) / 2 <= y1 - 0.5]
                found.append(spell_glyphs(inside) if inside else "")
            if not all(found):
                continue
            for index, text in enumerate(found):
                row = rows[index]
                if (row, column) in covered:
                    continue
                cells.append({
                    "row_start": row, "row_end": row + 1,
                    "column_start": column, "column_end": column + 1,
                    "text": text, "src_bbox": [cx0, ys[index], cx1, ys[index + 1]],
                    "page": page, "_chain_recovered": True,
                })
                covered.add((row, column))
                added += 1
    if added:
        cells.sort(key=lambda c: (c["row_start"], c["column_start"]))
    return added


def strip_duplicated_span_lines(table: dict) -> int:
    """**縦の結合セルの1行分が、覆っている行にもう一度出ているぶん**を落とす。

    斜めに割れた角セル（`Product model`／`Resource differences`）や折り返した見出し
    （`Reset`／`value`）を、pdfplumberは**結合セルとして1つ**出したうえで**下の行に
    もう1つ**出すことがある。結合表ではその行が列数を超え、**以降のセルが右へずれる**
    ——`CH32H417DS0.en` p3では行が10列（表は8列）になり、`QEU6`〜`REU6`が`128`〜`60`の
    2つ右に出て、どの型番が何ピンか読み違える形になっていた（再突合の指摘）。
    比較表の先頭（`CH32L103DS0.en` p2・`CH32V205DS0.en` p3・同zh）も同じ形。

    落とすのは次を全部満たすセルだけ:

    - その行の占める列数が**表の列数を超えている**（超えていないなら独立したセル）
    - 覆っている結合セルと**列範囲が重なる**（同じ箱の二重出力に限る）
    - 結合セルの本文が**2行以内**で、そのセルの本文が**その1行と完全一致**する

    「2行以内」が要——長い説明セルは**次の行の文字まで飲み込む**ことがあり、そのとき
    小さいセルの方が本物なので消すとデータが失われる（`QingKeV4_Processor_Manual` p37の
    `Floating-point unit status FS FS Meaning 00 OFF …`が9行ぶんを飲み、`FS Meaning`・
    `Initial`・`Clean`・`Dirty`が独立セルで在る）。全corpus実測: 列数超え＋重なり＋
    部分一致は206件、うち**完全一致かつ上が2行以内は74件・26文書**で、これは全部本物の
    二重出力（`Product model`／`Reset value`／`TIM2_RM=10`＋`Partial mapping`／
    `PLLCLK/8`／`td(CLKL_AV)`／`ITR1`＋`（TS=001）`）。**3行以上は40件**あり、そこに
    上の危険な型が入る。

    消しても**文字は失われない**——同じ綴りが結合セルに残っている。変わるのは行の列数が
    揃って以降のセルが本来の列に戻ることだけ。`strip_boundary_dupes`と同じ「二重取りの
    除去」なので同じ層に置き、**人向け出力専用**（exporterとparity検査だけが呼ぶ）。
    冪等（`_span_dupes_stripped`）。
    """
    if table.get("_span_dupes_stripped"):
        return 0
    table["_span_dupes_stripped"] = True
    columns = table.get("width") or table.get("column_count") or 0
    if not columns:
        return 0

    def norm(text: str | None) -> str:
        return " ".join((text or "").split())

    dead: set[int] = set()
    dead_rows: set[int] = set()

    def row_width(row: int) -> int:
        return sum(cell["column_end"] - cell["column_start"] for cell in table["cells"]
                   if cell["row_start"] <= row < cell["row_end"] and id(cell) not in dead)

    for span in [c for c in table["cells"]
                 if c["row_end"] - c["row_start"] > 1 and norm(c.get("text"))]:
        lines = [norm(part) for part in (span.get("text") or "").split("\n") if norm(part)]
        if not lines or len(lines) > 2:
            continue
        for row in range(span["row_start"] + 1, span["row_end"]):
            for cell in table["cells"]:
                if row_width(row) <= columns:
                    break
                if (cell is span or cell["row_start"] != row or id(cell) in dead
                        or not (cell["column_start"] < span["column_end"]
                                and span["column_start"] < cell["column_end"])):
                    continue
                if norm(cell.get("text")) in lines:
                    dead.add(id(cell))
                    dead_rows.add(row)
    if not dead:
        return 0
    table["cells"] = [cell for cell in table["cells"] if id(cell) not in dead]
    # 二重出力だけで出来ていた行は、消したあとセルが1つも残らない——空の`<tr>`として
    # 出て、覆っている結合セルのrowspanも1つ余分になる（remap表のヘッダは版面では
    # 1行で、2行目は折り返しの続きだった）。その行はグリッドから詰める。
    have = {cell["row_start"] for cell in table["cells"]}
    _remove_rows(table, {row for row in dead_rows if row not in have})
    return len(dead)


def strip_boundary_dupes(table: dict, chars=None) -> int:
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

    `chars`（ページのグリフ列か`page番号→グリフ列`の関数）を渡すと、下の「英字1文字のセル」の
    規則を**幾何で裏取り**する——その文字の字形が自セルに面積の半分以上入っていれば、隣からの
    はみ出しではなく自分の値なので消さない。文字だけの判定は、pin表の`HVCP | P`（type列の
    `P`＝電源）やフレーム図の`DATA | A`（ACK）を「`HVCP`の末尾がはみ出した」と誤認して**94セルの
    値を消していた**（全corpus実測。全件が左の語から8〜31pt離れた独立の値。2026-09-09の再突合が
    M030DS2.zh p3で指摘）。狙いの`Standard I/O port`→`t`は字形が境界に接して自セルに半分も
    入らないので、裏取りしても落ちる。
    """
    if table.get("_deduped"):
        return 0
    table["_deduped"] = True

    def own_glyph(cell: dict, ch: str) -> bool:
        """chの字形がこのセルに面積の半分以上入っているか（charsが無ければ判定できない＝偽）。"""
        if chars is None:
            return False
        box = cell.get("bbox") or cell.get("src_bbox")
        if not box:
            return False
        page_chars = chars(cell.get("page")) if callable(chars) else chars
        return any(g.get("text") == ch and _overlap_frac(g["bbox"], box) >= 0.5 for g in page_chars)
    by_row: dict[int, list[dict]] = {}
    for cell in table["cells"]:
        if (cell.get("text") or "").strip():
            by_row.setdefault(cell["row_start"], []).append(cell)
    # 単位の列（`V`・`A`・`s`が1文字で正しく入る）は、隣と同じ文字でも消さない——`VHV+9`の
    # 隣の単位`V`を「はみ出した重複」と見て**空にしていた**（M030DS2.zh p7。全面見直しの検証）。
    unit_columns = {c["column_start"] for c in table["cells"] if c["row_start"] == 0
                    and (c.get("text") or "").replace("\n", " ").strip().lower()
                    in ("unit", "units", "单位", "單位")}
    removed = 0
    for cells in by_row.values():
        cells.sort(key=lambda c: c["column_start"])
        for index, cell in enumerate(cells):
            text = cell.get("text") or ""
            # セル全体が英字1文字で、左隣の長い文（4字以上）がその文字で終わる——隣の末尾グリフ
            # が空セルへ跨いだもの（`Standard I/O port`→Min列に`t`。V208DS0.en p35・V003DS0.en
            # p23。全面見直しの指摘。CSVならMin=`t`になる）。数字は値なので触らない。
            if (len(text.strip()) == 1 and text.strip().isalpha() and index > 0
                    and cell["column_start"] not in unit_columns):
                left = (cells[index - 1].get("text") or "").rstrip()
                if len(left) >= 4 and left[-1] == text.strip() and not own_glyph(cell, text.strip()):
                    cell["text"] = ""
                    removed += 1
                    continue
            # 数字は落とさない——`HSRXEN = 1`の`1`が右隣`12`の先頭と一致して消え、`Page 0`の`0`が
            # `0x0800…`と一致して消えた（全面見直しの指摘。値の欠落はCSVにも効く）。数字の二重取りは
            # geometryで裏取りする`strip_straddling_dupes`に任せる。演算子で終わる本体（`HSRXEN =`）
            # や演算子で始まる本体（`= 6V`）が残る除去も、右辺/左辺を奪っているので行わない。
            if (len(text) >= 3 and text[-2] == " " and text[-1].strip() and not text[-1].isdigit()
                    and index + 1 < len(cells)):
                right = (cells[index + 1].get("text") or "").lstrip()
                body = text[:-2]
                if (right[:1] == text[-1] and 0 < len(body) <= 14 and body.strip()
                        and body.rstrip()[-1:] not in "=<>≤≥+-*/~"):
                    cell["text"] = text = body
                    removed += 1
            if (len(text) >= 3 and text[1] == " " and text[0].strip() and not text[0].isdigit()
                    and index > 0):
                left = (cells[index - 1].get("text") or "").rstrip()
                body = text[2:]
                if (left[-1:] == text[0] and 0 < len(body) <= 14 and body.strip()
                        and body.lstrip()[:1] not in "=<>≤≥+-*/~"):
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
    全文と、繋いだ続き行のidを返す（`…SRAM (RISC-V5F`＋次行`+ RISC-V3F)`。H417DS0.en p99。
    全corpus27表題）。

    **呼ぶのはconverterだけ**（1.8.0）。それまではbundleの`caption.text`が1行目のままで、
    exporterと`extract_low_power`が各々これを呼んで繋ぎ直していた——同じ修復を2箇所で
    掛けていた。いまは`caption.text`が全文、`caption.continuation_line_ids`が繋いだ行の
    idで、読み手はそれを読むだけでよい。"""
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


_LIST_HEADERS = ("pin name", "pin no", "pin type", "remap", "alternate", "default function",
                 "引脚名称", "引脚名", "引脚编号", "引脚类型", "重映射", "复用", "默认功能")


def is_list_table(table: dict) -> bool:
    """pin定義表・remap表か（ヘッダ行の語で判定）。これらのセルは**1行に1機能**を並べる
    一覧なので、物理行の切れ目は折り返しでなく項目の区切り（`MCO`/`TIM1_CH1`/`USART1_CK`）。
    レジスタ表の識別子折り返し（`USAR`+`T1`）と同じ規則で地続きに繋ぐと`MCOTIM1_CH1USART1_CK`
    になっていた（全面見直しがL103DS0/M030DS0で約100セルを指摘）。結果は`_list_table`に記憶。
    """
    if "_list_table" in table:
        return table["_list_table"]
    header = " ".join((c.get("text") or "").replace("\n", " ")
                      for c in table["cells"] if c["row_start"] == 0).lower()
    table["_list_table"] = any(word in header for word in _LIST_HEADERS)
    return table["_list_table"]


_RESET_HEADERS = ("reset value", "reset", "复位值", "复位", "初始值", "默认值", "default")
_RESET_VALUE = re.compile(r"0x[0-9A-Fa-f]+|[01xX]+b?|[0-9A-Fa-f]{2,}|-|—|–|N/A|无|无效")
# Access列（`RW`/`RO`/`WO`/`RC_W0`…）も語彙が決まっている。説明列の行端が降りて`L<br>RO 10`・
# `E10<br>RW N m T h`になっていた（V205RM.en p37・M030RM.en p113。全面見直しの指摘）。
_ACCESS_HEADERS = ("access", "访问", "读写", "读/写", "属性", "类型", "type", "r/w")
# `w1`/`r0`/`r1`/`w0` はQingKeプロセッサマニュアルの書き方（`30 resumereq W1 …`）。
# 語彙に無いと下の1〜2字規則が**黙って消す**ので、実測で出る綴りは入れておく。
_ACCESS_VALUE = re.compile(r"(?i)r|w|rw|ro|wo|rc|rs|rw1|rc_w0|rc_w1|rc_w|rw0|w1c|w0c|w1s"
                           r"|r/w|rw/ro|ro/rw|rwo|w1|r0|r1|w0|-|—")


def clean_reset_column(table: dict) -> int:
    """記述表の**reset値の列**に降ってきた、説明列の行末グリフを落とす。

    説明文が右寄せ気味に組まれると各行の最後の1文字がreset列へ跨ぎ、`0`が`e 0 e`・
    `e w . 0 t`・`n m k k 0 n y`になる（L103RM.en p49・H417RM.en p672・M030RM.zh p110。
    全面見直しの指摘。CSVのreset値にも効く）。geometryの重複判定（`strip_straddling_dupes`）
    はLatin文字を`tsu`の`t`と区別できず触らないが、**reset値の列**と分かっていれば話は別——
    正当な値は`0`/`1`/`x`/`0x…`/`00b`/`-`の1トークンだけで、空白で切れた1文字の英字が並ぶ
    ことはない。ヘッダが`Reset value`/`复位值`の列で、**値トークンがちょうど1つ・他が全部
    1文字**のセルだけを値トークンに置き換える。地続きの`0M`や2文字以上の異物は触らない。
    """
    if table.get("_reset_cleaned"):
        return 0
    table["_reset_cleaned"] = True
    kinds: dict[int, re.Pattern] = {}
    for c in table["cells"]:
        if c["row_start"] != 0:
            continue
        head = (c.get("text") or "").replace("\n", " ").strip().lower()
        if head in _RESET_HEADERS:
            kinds[c["column_start"]] = _RESET_VALUE
        elif head in _ACCESS_HEADERS:
            kinds[c["column_start"]] = _ACCESS_VALUE
    if not kinds:
        return 0
    fixed = 0
    for cell in table["cells"]:
        pattern = kinds.get(cell["column_start"])
        if cell["row_start"] == 0 or pattern is None:
            continue
        text = (cell.get("text") or "").strip()
        if (pattern is _RESET_VALUE and text
                and text not in ("无", "无效", "-", "—", "–", "…", "...", "．．．")
                and not any(ch.isascii() and ch.isalnum() for ch in text)):
            # 英数字を1つも含まないreset値（`该只模E）`の`）`・`不当切`）は説明列の行端が降りたもの。
            cell["text"] = ""
            fixed += 1
            continue
        tokens = text.split()
        if len(tokens) == 1 and len(text) <= 2 and not pattern.fullmatch(text):
            # 値の形をしていない1〜2字の単独トークン（`t`・`y`・`e`＝説明列の行末の英字）。
            # **落とすのは小文字のLatinだけ。** 白名簿（`_ACCESS_VALUE`）に無いものを
            # 一律に消すと、**語彙の漏れがそのまま黙った削除になる**——QingKeの`W1`/`R0`が
            # それで消え、`访问`列が空の行が全corpus 509セル・30文書あった（2026-09-06の
            # 検証ラウンドが検出）。落としたい残骸は説明列の行末に立つ語の一部なので
            # 小文字で、access/reset値は大文字か数字（`RW`・`W1`・`R0`・`0`・`1x`）。
            # これで失敗の向きが「消しすぎ」から「残しすぎ」に変わる。
            # さらに**1文字だけ**に絞る（1.9.3）。2文字の小文字は実在する値でありうる
            # ——SDコマンドの`类型`列の`ac`（`adtc`と対）が消え、表32-4/5/6の14行中8行が
            # 値を失っていた（CH32H417RM.zh p602。2026-09-07の検証ラウンド）。狙っている
            # 残骸は説明列の行末に立つ**1文字**（`t`・`y`・`e`）なので、そこだけを落とす。
            if len(text) == 1 and text.isascii() and text.islower():
                cell["text"] = ""
                fixed += 1
            continue
        if len(tokens) < 2:
            continue
        values = [tok for tok in tokens if pattern.fullmatch(tok)]
        strays = [tok for tok in tokens if not pattern.fullmatch(tok)]
        if pattern is _RESET_VALUE:
            # `0xFFFFFFF`＋改行＋`F`は折り返した16進1桁——異物ではなく続き（V407RM.en p551
            # MACA3LR。全面見直しの指摘。落とすと32bit値が28bitになる）。値の後に16進1桁だけが
            # 続くなら繋ぐ。
            if (len(values) == 1 and strays and tokens[0] == values[0]
                    and values[0].lower().startswith("0x")
                    and all(re.fullmatch(r"[0-9A-Fa-f]", s) for s in strays)):
                cell["text"] = values[0] + "".join(strays)
                fixed += 1
                continue
            # 数字の値の隣の孤立した`x`は説明文の`channel x`の末尾（V407RM.en p155 `x 0`）。
            digit_values = [v for v in values if v[0].isdigit()]
            if len(digit_values) == 1 and all(v in ("x", "X") for v in values if v not in digit_values):
                strays += [v for v in values if v not in digit_values]
                values = digit_values
        # reset列は1文字の異物だけ、Access列は3文字以下の英数字の異物まで（`E10`・`10`）。
        limit = 1 if pattern is _RESET_VALUE else 3
        if (len(values) == 1 and strays
                and all(len(tok) <= limit and tok.isalnum() or len(tok) == 1 for tok in strays)):
            cell["text"] = values[0]
            fixed += 1
    return fixed


# 括弧付きの指数（`(G+2)`・`（N-1）`）。**中に英字か演算子がある**ものだけ——数字だけの
# `(1)`/`（2）`は脚注番号なので指数にしない。
_PAREN_EXPONENT = re.compile(r"[（(](?=[^）)]*(?:[A-Za-z]|[+\-*/×]))[A-Za-z0-9+\-*/×^ ]+[）)]")
_LONE_LETTER = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z](?=[ \n]|$)")
# 上付きが潰れた冪（`232`＝2^32・`220`＝2^20）の疑い。geometryで上付きと確かめてから直す。
_POWER_OF_TWO = re.compile(r"(?<![0-9.])2(?:16|20|24|32|64)(?![0-9])")


# 潰れた**括弧付き指数**（`2(G+2)`＝`2^(G+2)`）。数字の直後に括弧が地続きで、中に英字か
# 演算子がある形。脚注の`2(1)`と分けるのは中身（数字だけなら脚注）。geometryを開く前の
# 前判定に要る——`_LONE_LETTER`も`_POWER_OF_TWO`も当たらず、QingKe V3/V4/V5の
# NAPOT行6箇所が判定に入っていなかった（2026-09-07の検証ラウンドが検出）。
_FLAT_PAREN_EXPONENT = re.compile(
    r"(?<![A-Za-z0-9])\d[（(](?=[^）)]{0,12}(?:[A-Za-z]|[+\-*/×]))[^）)]{1,12}[）)]")


def has_subscript_shape(table: dict) -> bool:
    """下付き/上付きが基底から離れた疑いのあるセル（`V *2-1.5DD5`・`f = 2.4MHz S`・
    `V ,V\nS0 S1`・`2(G+2)`）があるか——基底が**1文字だけで空白/改行/末尾の前に立つ**か、
    潰れた冪、または数字に地続きの括弧付き式。geometryを開く前の安価な前判定。"""
    for c in table["cells"]:
        text = c.get("text") or ""
        if (_LONE_LETTER.search(text) or _POWER_OF_TWO.search(text)
                or _FLAT_PAREN_EXPONENT.search(text)):
            return True
    return False


def _rebuilt_from_glyphs(text: str, glyphs: list[dict], dominant: float) -> str | None:
    """**セル文字列をgeometryの読み順から組み直す**（1.10.1）。直せないならNone。

    脚注の上付きと下付きが同じ基底に付くシンボルで、pdfplumberは脚注を基底の行に、
    下付きを次の行に置く——`V_DD12A(1)`が`'V (1)\nDD12A'`に、`t_SU(LSI)(1)`が
    `'t (1)\nSU(LSI)'`になる。**文字は全部あって順序だけが違う**ので、挿し込みでは
    直せない（`reattach_cell_subscripts`の歯止めが正しく拒否する）。全corpus419セル、
    うち338が24字以内（2026-09-07の検証ラウンドが「下付きの離脱」として指摘した型）。

    行（上端で束ねる）→x の順に並べ直すだけなので、**挿入位置の曖昧さが原理的に無い**
    ——`每2^20个`を`每2个…121pp^20m`に壊した回帰は「既存の文字列に挿し込む」ことが
    原因だった。組み直しにはその失敗モードがない。

    **短いセルに限る**。グリフは空白を持たないので、長い説明セルを組み直すと
    `Thedatabusisdriven`のように語間が失われる。24字以内（実測で81%がここに入る）で、
    文字集合が完全に一致し、結果が現状と違うときだけ返す。
    """
    flat = "".join(text.split())
    if len(flat) > 24:
        return None
    rows: list[list[dict]] = []
    for glyph in sorted(glyphs, key=lambda g: (g["bbox"][1], g["bbox"][0])):
        if rows and glyph["bbox"][1] - rows[-1][-1]["bbox"][1] > 0.5 * dominant:
            rows.append([])
        elif not rows:
            rows.append([])
        rows[-1].append(glyph)
    rebuilt = "\n".join("".join(g["text"] for g in sorted(row, key=lambda g: g["bbox"][0]))
                         for row in rows)
    if not rebuilt.strip() or rebuilt == text:
        return None
    if Counter("".join(rebuilt.split())) != Counter(flat):
        return None
    return rebuilt


def reattach_cell_subscripts(table: dict, chars) -> int:
    """表セルの中で基底から離れた**下付き**を、geometryで元の位置へ戻す。

    pdfplumberはセル内の下付き（小さいフォント・低い基線）を別の視覚行として拾い、
    `VDD5*2-1.5`を`V *2-1.5DD5`、`fS < 200KHz`を`f < 200KHz S`、`VS0,VS1`を`V ,V\nS0 S1`にする
    （datasheetの電気特性表に集中。全面見直しがM030DS2/L103DS0/V003DS0で50セル超を指摘。
    値・条件の意味が変わるのでCSVにも効く）。converterの`merge_subscript_lines`は行しか見ない。

    セルのグリフを大きさで**基底**と**下付き**（サイズ≤0.8×中央値、かつ基底より下）に分け、
    下付きの連なりを、そのすぐ左にある基底グリフの直後へ挿し直す。textは組み直さず、
    下付きの綴りを消して基底の後へ挿すだけ——挿す前後で**空白以外の文字列が一致**しなければ
    何もしない（安全側）。下付きと次の文字の隙間が狭ければ間の空白も落とす（`VS0,VS1`）。
    charsはグリフ列か`page番号→グリフ列`の関数（結合表）。exporterとparityが同じ順で呼ぶ。冪等。
    """
    if table.get("_subscripts_reattached"):
        return 0
    table["_subscripts_reattached"] = True
    fixed = 0
    for cell in table["cells"]:
        text = cell.get("text") or ""
        box = cell.get("bbox") or cell.get("src_bbox")
        if not box or not (_LONE_LETTER.search(text) or _POWER_OF_TWO.search(text)
                           or _FLAT_PAREN_EXPONENT.search(text)):
            continue
        page_chars = chars(cell.get("page")) if callable(chars) else chars
        glyphs = [g for g in page_chars if (g.get("text") or "").strip()
                  and box[0] <= (g["bbox"][0] + g["bbox"][2]) / 2 <= box[2]
                  and box[1] <= (g["bbox"][1] + g["bbox"][3]) / 2 <= box[3]]
        if len(glyphs) < 2:
            continue
        # 基底の大きさ＝最大のグリフ。中央値だと`C /C`+`L1 L2`（基底3・下付き4）や`232`（基底1・
        # 上付き2）で下付きの方が多数になり、下付きを基底と取り違えて何もしなかった。
        dominant = max(g["size"] for g in glyphs)
        small = [g for g in glyphs if g["size"] <= 0.8 * dominant]
        normal = [g for g in glyphs if g["size"] > 0.8 * dominant]
        if not small or not normal:
            continue
        def _fallback() -> bool:
            """挿し込みが諦めたら、geometryから組み直せるか試す。"""
            rebuilt = _rebuilt_from_glyphs(text, glyphs, dominant)
            if rebuilt is None:
                return False
            cell["text"] = rebuilt
            return True

        if (not _LONE_LETTER.search(text)
                and not _FLAT_PAREN_EXPONENT.search(text)
                and not any(ch.isdigit() for g in small for ch in g["text"])):
            continue
        # 読み順（視覚行→x）。基底の並びはtextの空白以外の並びと一致するはず。
        def order(gs):
            gs = sorted(gs, key=lambda g: (g["bbox"][1], g["bbox"][0]))
            rows, cur = [], []
            for g in gs:
                if cur and g["bbox"][1] - cur[-1]["bbox"][1] > 0.5 * dominant:
                    rows.append(cur); cur = []
                cur.append(g)
            if cur:
                rows.append(cur)
            return [g for row in rows for g in sorted(row, key=lambda g: g["bbox"][0])]
        normal = order(normal)
        # 下付きの連なり: 同じ基線帯でxが連続するもの
        # まず基線帯（top）で行に分け、行の中を x 順に並べて隙間で連なりに切る。x だけで
        # 並べると別の行の下付きが交互に混ざり（`HCLK`と`SYS`。V004DS0.en p21）、top の丸めで
        # 並べると`CLK`が`K`/`CL`に割れて`tKCL`になった（H417DS0.en p133）。
        bands: list[list[dict]] = []
        for g in sorted(small, key=lambda g: g["bbox"][1]):
            if bands and abs(g["bbox"][1] - bands[-1][-1]["bbox"][1]) < 0.5 * g["size"]:
                bands[-1].append(g)
            else:
                bands.append([g])
        runs: list[list[dict]] = []
        for band in bands:
            for g in sorted(band, key=lambda g: g["bbox"][0]):
                # 下限は-0.35——太字系のフォントは下付きの字形箱が**互いに重なる**（`PCLK`のP/Cが
                # 幅の22%重なる。L103RM.zh p239）。-0.2で割れると`P`・`C`・`L`・`K`の単字除去が本文の
                # `SCK`を食い、セル全体の復元が失敗していた。全corpus実測: 緩めて変わるのは9セルで
                # 全部正しい復元（`FPCLK`・`FHCLK`・`VIO18`・`VBC_SRC`）。
                if (runs and runs[-1][0] in band
                        and -0.35 * g["size"] <= g["bbox"][0] - runs[-1][-1]["bbox"][2] < 0.35 * g["size"]):
                    runs[-1].append(g)
                else:
                    runs.append([g])
        plan = []   # (基底index, 挿す綴り, 直後の空白を落とすか, textから消す綴り, 連なりのx0)
        for run in runs:
            sub = raw = "".join(g["text"] for g in run)
            x0, top, bottom = run[0]["bbox"][0], run[0]["bbox"][1], run[0]["bbox"][3]
            # 基底: 小さいグリフの左に接し（1.5文字幅以内）、下付きなら基底より下に沈み、
            # 上付きなら基底より上に浮いている。上付きの数字は`^`を付けて書く——`2^32`が
            # `232`に潰れ、タイマの最大カウントが読めなかった（V208DS0.en p38・H417RM.zh p117。
            # 全面見直しの指摘）。脚注の`(1)`のような括弧付きは`^`無しで基底の直後へ戻す。
            # 基底は**同じ視覚行**にいること（箱が縦に重なる）。長い説明セルでは、別の行の
            # 同じxにいるグリフが基底に選ばれ、`每2^20个…121ppm`が`每2个…121pp^20m`になった。
            def on_line(g):
                return g["bbox"][1] < bottom and g["bbox"][3] > top
            bases = [(i, g) for i, g in enumerate(normal)
                     if -0.3 * g["size"] <= x0 - g["bbox"][2] <= 1.5 * g["size"] and on_line(g)
                     and top >= g["bbox"][1] + 0.15 * g["size"]
                     and bottom <= g["bbox"][3] + 0.6 * g["size"]]
            if not bases:
                supers = [(i, g) for i, g in enumerate(normal)
                          if -0.3 * g["size"] <= x0 - g["bbox"][2] <= 1.5 * g["size"] and on_line(g)
                          and bottom <= g["bbox"][3] - 0.25 * g["size"]
                          and top < g["bbox"][1] + 0.1 * g["size"]]
                if not supers:
                    # 下付きが**セルの中で次の行へ折り返した**（`t`+`MAX_COUN`/`T`。H417DS0.en
                    # p112）。左に基底がいない小グリフの連なりは、直前の連なりの続きとして繋ぐ。
                    if plan and top > plan[-1][5]:
                        i, prev_sub, tight, prev_raw, x_prev, _ = plan[-1]
                        plan[-1] = (i, prev_sub + sub, tight, prev_raw + raw, x_prev, top)
                        continue
                    break
                bases = supers
                # `^`を付けるのは**指数**だけ——基底が数字か、単独で立つ1文字（`2`・`x`）の
                # とき。`Cortex`+`TM`や`ARM○`+`R`は商標や登録記号で指数ではないので、
                # `Cortex^TM`にしない（全corpus792行の試算で1件見つかった）。
                index0, base0 = min(supers, key=lambda ig: x0 - ig[1]["bbox"][2])
                token = base0["text"]
                standalone = index0 == 0 or not normal[index0 - 1]["text"].isalnum()
                if sub.isalnum() and token.isalnum() and (token.isdigit() or standalone):
                    sub = "^" + sub
                elif token.isdigit() and _PAREN_EXPONENT.fullmatch(sub):
                    # 括弧の中に**式**が入った指数（`2^(G+2)`＝NAPOTの領域幅）。潰すと
                    # 掛け算に読めて値が変わる（QingKe V3/V4/V5 の zh/en 6箇所。
                    # 2026-09-07の検証ラウンドが検出）。脚注の`(1)`/`（2）`と分けるのは
                    # **中身**——数字だけなら脚注、英字か演算子を含むなら指数。
                    sub = "^" + sub
            i, base = min(bases, key=lambda ig: x0 - ig[1]["bbox"][2])
            nxt = normal[i + 1] if i + 1 < len(normal) else None
            # 基底と次の文字の隙間が**下付きの幅でほぼ説明できる**なら印字上の空白は無い
            # （`VS0,`）。下付きの幅を引いても1pt超の余りがあれば本物の空白（`fS = 2.4MHz`）。
            width = run[-1]["bbox"][2] - run[0]["bbox"][0]
            tight = (nxt is not None
                     and abs(nxt["bbox"][1] - base["bbox"][1]) < 0.5 * dominant
                     and (nxt["bbox"][0] - base["bbox"][2]) - width < 1.2)
            plan.append((i, sub, tight, raw, x0, top))
        if not plan or len(plan) > len(runs):
            fixed += 1 if _fallback() else 0
            continue
        # textから下付き/上付きの綴りを（トークン優先で）消す
        stripped = text
        ok = True
        for _, _, _, raw, _, _ in plan:
            # 下付き自体が改行で割れていることがある（`t`+`MAX_COUN`+`T`。H417DS0.en p112）。
            # 空白・改行をまたいで照合する。
            loose = r"\s*".join(re.escape(ch) for ch in raw)
            m = (re.search(r"(?<![A-Za-z0-9])(" + loose + r")(?![A-Za-z0-9])", stripped)
                 or re.search("(" + loose + ")", stripped))
            if not m:
                ok = False
                break
            stripped = stripped[:m.start()] + stripped[m.end():]
        if not ok:
            fixed += 1 if _fallback() else 0
            continue
        if "".join(stripped.split()) != "".join(g["text"] for g in normal):
            # 挿し込みでは直せない（セル文字列の順序自体が壊れている）。geometryから
            # 組み直せるなら組み直す——行→xに並べ直すだけなので挿入位置の曖昧さが無い。
            fixed += 1 if _fallback() else 0
            continue
        # k番目の基底の直後へ挿す（後ろから）
        out = stripped
        # 同じ基底に複数の連なりが付く（`V`＋下付き`BAT`＋上付き脚注`(2)`）ときは、右のものから
        # 挿して最終的に x 順に並ぶようにする（`V（2）BAT`にならない）。
        for i, sub, tight, _, _, _ in sorted(plan, key=lambda x: (-x[0], -x[4])):
            count, at = -1, None
            for idx, ch in enumerate(out):
                if not ch.isspace():
                    count += 1
                    if count == i:
                        at = idx + 1
                        break
            if at is None:
                ok = False
                break
            tail = out[at:]
            if tight and tail[:1] == " ":
                tail = tail[1:]
            out = out[:at] + sub + tail
        if not ok:
            continue
        out = "\n".join(line.rstrip() for line in out.split("\n") if line.strip())
        flat_out = "".join(out.split()).replace("^", "")
        # **挿した位置がグリフの読み順と一致すること**だけを条件にする。文字集合の一致で
        # 妥協すると、長い説明セルで基底の索引がずれても通ってしまい、`每2^20个…121ppm`が
        # `每2个…121pp^20m`になった（CH32xRM.zh p32。全面見直しの指摘。私が入れた回帰）。
        # `^`の直後は必ず英数字か**開き括弧**（`ARM○^`のような裸の`^`を作らない）。括弧を
        # 許すのは`2^(G+2)`のような式の指数のため——ここで弾いていたので、NAPOTの領域幅が
        # `2(G+2)`のまま出ていた（QingKe V3/V4/V5のzh/en 6箇所。2026-09-07の検証ラウンド）。
        if re.search(r"\^(?![A-Za-z0-9（(])", out):
            continue
        if out != text and flat_out == "".join(g["text"] for g in order(glyphs)):
            cell["text"] = out
            fixed += 1
    return fixed


# 見出しの続きではありえない中身: 数字・bit範囲・16進・アクセス値・`-`。
_DATA_LIKE = re.compile(r"\[?\d+(?::\d+)?\]?|0x[0-9A-Fa-f]+|[-—–]|(?i:rw|ro|wo|rc_w0|rc_w1|rw1|w1c)|[01xX]+b?")


def _fold_spanning_header(table: dict) -> int:
    """見出しの一部が折り返して**見出しブロックの下の行**に落ちた形を、ヘッダへ畳む。

    datasheetのpin表は見出しがrowspanで2〜4行の高さを持ち、`Pin`/`name`・`Main`/`function`/
    `(after`/`reset)`のように折り返した片が下の行に別セルとして落ちる。DMA転送表も
    `Source`/`bit width`のように割れる（V407RM.en p145）。

    **見出しの続きの行は、折り返した列にしかセルが無い**——これが本文データとの違い。
    `Reset value`だけがrowspan 2の記述表では、下の行に`31`/`RAMLV`/`RW`/`0`と**全列**に
    データが入るので当たらない。この判定だけで足り、片の中身の字種は見ない（`Number`の
    ような大文字始まりの正当な続きを弾いてしまうため）。

    **計画してから一括で適用する**——途中で条件に外れたときに見出しだけ書き換わって片が
    残る、という壊れ方をしたことがある（全面見直しの検証3巡目でV407RM.en p145/p124が
    `Source bit width`と`bit width`の二重になった）。
    """
    if table.get("_bitfield"):
        return 0
    header = [c for c in table["cells"] if c["row_start"] == 0]
    if len(header) < 2:
        return 0
    height = max(c["row_end"] for c in header)
    if height < 2:
        return 0
    # 折り返した列＝見出しが下端まで届いていない列。
    wrapped = [h for h in header if h["row_end"] < height]
    # **畳むのは1列幅の見出しだけ**。複数列にまたがる見出しの下の行は、列を数え上げる
    # 副見出し（`Pin number`の下の`QSOP28`/`QFN32`…）であって折り返しではない。
    foldable = [h for h in wrapped if h["column_end"] - h["column_start"] == 1]
    if not foldable or len(foldable) > len(header) / 2:
        return 0
    spans = [(h["column_start"], h["column_end"]) for h in wrapped]

    def in_wrapped(cell: dict) -> bool:
        return any(a <= cell["column_start"] < b for a, b in spans)

    block = [c for c in table["cells"]
             if 1 <= c["row_start"] < height and (c.get("text") or "").strip()]
    if not block or not all(in_wrapped(c) for c in block):
        return 0
    plan: list[tuple[dict, str, list[dict]]] = []
    for head in foldable:
        pieces = [c for c in block
                  if head["column_start"] <= c["column_start"] < head["column_end"]
                  and c["row_start"] >= head["row_end"] and c["row_end"] <= height]
        texts = [" ".join((c.get("text") or "").split()) for c in pieces]
        if any(len(x) > 16 or _DATA_LIKE.fullmatch(x) for x in texts if x):
            return 0
        if not any(texts):
            continue
        parts = [(head.get("text") or "").replace("\n", " ").strip()] + [x for x in texts if x]
        joined = parts[0]
        for piece in parts[1:]:
            # CJK同士は空白を入れない（`引脚`+`类型(1)`＝`引脚类型(1)`）。
            sep = "" if (_has_cjk(joined[-1:]) and (_has_cjk(piece[:1]) or piece[:1] in "（(")) else " "
            joined += sep + piece
        plan.append((head, joined, pieces))
    if not plan:
        return 0
    folded: list[dict] = []
    for head, joined, pieces in plan:
        head["text"] = joined
        head["row_end"] = height
        folded.extend(pieces)
    ids = {id(c) for c in folded}
    table["cells"] = [c for c in table["cells"] if id(c) not in ids]
    # 見出しブロック内で、もうどのセルも始まらない行を詰める
    occupied = {c["row_start"] for c in table["cells"]}
    empty = [r for r in range(1, height) if r not in occupied]
    if empty:
        keep = [r for r in range(table["row_count"]) if r not in empty]
        remap = {old: new for new, old in enumerate(keep)}
        for c in table["cells"]:
            rows = [r for r in range(c["row_start"], c["row_end"]) if r not in empty]
            c["row_start"], c["row_end"] = remap[rows[0]], remap[rows[-1]] + 1
        table["row_count"] = len(keep)
        if table.get("_folded_rows"):
            table["_folded_rows"] = sorted(remap[r] for r in table["_folded_rows"] if r in remap)
        if table.get("row_pages"):
            table["row_pages"] = [table["row_pages"][r] for r in keep]
    return len(folded)


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
    folded = _fold_spanning_header(table)
    if folded:
        return folded
    row1 = [c for c in table["cells"] if c["row_start"] == 1 and (c.get("text") or "").strip()]
    if len(row1) != 1:
        return 0
    tail = row1[0]
    word = tail["text"].strip()
    if tail["row_end"] - tail["row_start"] != 1 or "\n" in word or len(word) > 16:
        return 0
    # 見出しが**既に折り返しの両行を持っている**のに、2行目の断片が別セルとして残ることがある
    # （`Reset\nvalue`のヘッダ＋row1に`value`。CH32xRM.en p72/p201）。その列を覆う見出しが
    # その語で終わっていれば、断片は重複なので行ごと落とす。
    covering = next((c for c in table["cells"]
                     if c["row_start"] == 0
                     and c["column_start"] <= tail["column_start"] < c["column_end"]
                     and (c.get("text") or "").strip()), None)
    if covering is not None and covering["text"].replace("\n", " ").strip().lower().endswith(word.lower()):
        table["cells"] = [c for c in table["cells"] if c["row_start"] != 1]
        for c in table["cells"]:
            if c["row_start"] > 1:
                c["row_start"] -= 1
            if c["row_end"] > 1:
                c["row_end"] -= 1
        table["row_count"] -= 1
        if table.get("_folded_rows"):
            table["_folded_rows"] = sorted(r - 1 if r > 1 else r
                                           for r in table["_folded_rows"] if r != 1)
        if table.get("row_pages") and len(table["row_pages"]) > 1:
            del table["row_pages"][1]
        return 1
    # ここから先は「見出しへ**足す**」経路——小文字1語（`value`）に限る。大文字始まりを足すと
    # データ行を見出しへ吸い込む。
    if not (word.isalpha() and word.islower() and len(word) <= 8):
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


_RANGE_NAME = re.compile(r"([A-Za-z][A-Za-z_0-9]*)\s*\[\d+:\d+\]")


def description_names(page: dict, chains: dict[str, dict] | None = None,
                      next_page: dict | None = None) -> set[str]:
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
    # bit図がページ末尾に来ると、その記述表は**次ページ**で始まる（FV2x_V3xRM.en p590の
    # R32_SDIO_MASK——`RXFIRFOXEFIIFOEE I`が直せなかった。全面見直しの指摘）。隣のページの
    # 記述表も根拠に足す（同じ章の続きなので`PB1`/`PB11`の取り違えの危険は文書全体より小さい）。
    if next_page is not None:
        tables += [((chains or {}).get(t["id"], {}).get("merged") or t)
                   for t in next_page["tables"]]
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
    # このページのbit図が`PENDSET[31:16]`・`INTEN[63:48]`のように**範囲つきで書いた綴り**も
    # 正解として採る。同じレジスタの上位半分がbaseを見せていることがあり、記述表が次ページに
    # 送られているとそこだけが根拠になる（CH32V003RM.en p43のPFIC_IPSR1——説明表はp44に在り、
    # 図の6セル全部が壊れていたのでpage内に他の手がかりが無かった。PDF↔MD突合の指摘）。
    for table in tables:
        for cell in table["cells"]:
            match = _RANGE_NAME.fullmatch((cell.get("text") or "").strip())
            if match:
                names.add(match.group(1))
    return names


def _undoubled_tail(text: str) -> str | None:
    """末尾が同じブロックの2連なら1つ分を落とした綴り（`HSYNCSCS`→`HSYNCS`）。
    ブロックに英字が要る——`PB11`型の数字末尾は正当な名前なので触らない。"""
    for k in range(1, len(text) // 2 + 1):
        block = text[-k:]
        if text[-2 * k:-k] == block and any(ch.isalpha() for ch in block):
            return text[:-k]
    return None


def _truncates_index(text: str, name: str) -> bool:
    """`text`から`name`への差し替えが**索引を短くするだけ**か（`ODR11`→`ODR1`）。

    `_only_duplicate_glyphs`は落ちる数字が名前にも在れば通してしまうので、
    `ODR1`が記述表に在る一方で図の`ODR11`が正しい、という形を別に弾く。全corpusでは
    この形の置き換えは0件（2026-09-04に943件を全数検査）だが、`ODR1`と`ODR11`が同じ
    ページのName列に並ぶと踏む穴なので歯止めとして置く。
    """
    return (text.startswith(name) and text != name
            and text[len(name):].strip().isdigit())


def _only_duplicate_glyphs(text: str, name: str, edges: str = "") -> bool:
    """`text`から`name`へ縮めるとき、**落ちる文字が全て`name`自身に在る**か。

    交錯した重複は名前のグリフが二度出る形なので、落ちるのは名前が持つ文字だけになる
    （`PLLRPDLLY`→`PLLRDY`で落ちるのは`P,L,L`）。一方、図の`INTEN12`・`PENDSTA15`・
    `HSICAL[7:0]`は**Name列が索引や範囲を書かないだけで図が正しい**——落ちる`1`/`2`/`[7:0]`は
    名前に無い文字なので、この条件で弾ける（この歯止め無しでは905件が索引や範囲を失った）。
    空白は版面の都合なので例外。

    `edges`は**隣のセルと接する1字**（左隣の末尾・右隣の先頭）のうち**英字だけ**。列の境界を
    跨いだ字形はpdfplumberが両側のセルに入れるので、名前に無い文字でもここから来たなら重複と
    見なせる（`CSS_HSE_DIS`|`SReserSved`の`S`。`Reserved`に大文字`S`は無い）。歯止めが2つ要る:

    - **接する1字だけ**。2字へ広げると`AWDIE`|`EOCI`の`EOCI`が`EOC`へ縮む（本当は`EOCIE`の
      取りこぼしで、縮めるのは誤り）。
    - **数字は借りない**。`EXTI11`|`EXTI10`|`EXTI9`の`EXTI10`が、左隣の末尾`1`を借りて
      `EXTI0`へ縮んだ（実測。索引が変わるので最悪の壊れ方）。
    """
    counts: dict[str, int] = {}
    for ch in name:
        counts[ch] = counts.get(ch, 0) + 1
    for ch in text:
        if ch.isspace():
            continue
        if counts.get(ch):
            counts[ch] -= 1
        elif ch not in name and ch not in edges:
            return False
    return True


def _touching_glyphs(table: dict, cell: dict) -> str:
    """`cell`が隣と接する1字（左隣の末尾＋右隣の先頭）。"""
    edges = ""
    for other in table["cells"]:
        if other is cell or other["row_start"] != cell["row_start"]:
            continue
        text = (other.get("text") or "").replace("\n", "").strip()
        if not text:
            continue
        if other["column_end"] == cell["column_start"]:
            edges += text[-1]
        elif other["column_start"] == cell["column_end"]:
            edges += text[0]
    return edges


def _is_subsequence(name: str, text: str) -> bool:
    """`name`の文字が`text`に順番どおり現れるか（間に余分な文字があってよい）。"""
    it = iter(text)
    return all(ch in it for ch in name)


def _indexed_bases(table: dict, names: set[str]) -> tuple[set[str], dict[int, str]]:
    """索引付きの名前を組むための（base集合, 列→bit番号）。

    `PFIC_IPR1`・`PFIC_IENR1`・`PFIC_IPSR1`のように1bitずつ索引が付くレジスタでは、記述表の
    Name列が`PENDSTA`・`INTEN`と索引を書かないので、記述表だけでは`PENDSTA15`を復元できない
    （PDF↔MD突合が`PENPDESNTDAS1T5`・`INTENIN1T5E N`・`PENDPSEETN1D5SET15`で指摘）。索引は
    **`apply_bitfield`が置いた0行目のbitヘッダ**が持っている。baseの根拠は2つ:

    1. **同じ図の無傷の兄弟セル**が`INTEN12`のように綴りを見せ、その数字がその列のbit番号と
       一致する（2つ以上一致すれば索引の付き方はそれだけで確かめられる。1つだけのときは
       baseが記述表にも在ることを求める＝base＝記述表・索引＝兄弟とヘッダの二重の裏づけ）。
    2. 兄弟が1つも無傷でない図（FV2x_V3xRM.en p106のPFIC_IPR1は6セル全部が壊れていた）では
       **記述表のName列そのもの**をbaseにする。

    どちらの経路でも、実際に差し替わるのは`fix_doubled_names`の歯止め（部分列・落ちる文字は
    名前の中だけ・索引を短くしない・候補がただ1つ）を全て通ったときだけ。
    """
    bit_at = {c["column_start"]: (c.get("text") or "").strip()
              for c in table["cells"] if c["row_start"] == 0}
    confirmed: dict[str, int] = {}
    for cell in table["cells"]:
        if cell["row_start"] < 1 or cell["column_end"] - cell["column_start"] != 1:
            continue
        text = (cell.get("text") or "").replace("\n", "").strip()
        match = re.fullmatch(r"([A-Za-z][A-Za-z_]*)(\d+)", text)
        if not match or bit_at.get(cell["column_start"]) != match.group(2):
            continue
        confirmed[match.group(1)] = confirmed.get(match.group(1), 0) + 1
    bases = {base for base, count in confirmed.items()
             if count >= 2 or (count >= 1 and base in names)}
    bases |= {n for n in names
              if len(n) >= 3 and not n[-1].isdigit()
              and all(ch.isalnum() or ch == "_" for ch in n)}
    # 記述表が族名を`SWIERx`・`MRx`・`FBMx`と書くことがある（`x`はbit索引の代わり）。
    # 末尾の`x`を外した綴りもbaseにする——`SWIER`+bit14＝`SWIER14`（PDF↔MD突合の指摘）。
    bases |= {n[:-1] for n in names
              if len(n) >= 4 and n.endswith("x") and n[-2].isupper()
              and all(ch.isalnum() or ch == "_" for ch in n)}
    return bases, bit_at


def _is_doubled(flat: str, name: str) -> bool:
    """`flat` が `name` を**2つ交錯させたもの**か（長さも文字も過不足なく2倍）。

    候補が2つ以上残ったときの決め手に使う。`CCRCCFCARILCFAIL`（16字）には記述表の
    `CCRCFAIL`（8字）と `CCRCFAILC`（9字）の両方が部分列として入るが、**2つ交錯**の関係が
    成り立つのは長さが丁度2倍の前者だけ。

    >>> _is_doubled("CCRCCFCARILCFAIL", "CCRCFAIL")
    True
    >>> _is_doubled("CCRCCFCARILCFAIL", "CCRCFAILC")
    False
    >>> _is_doubled("SPI1SRPSIT1RST", "SPI1RST"), _is_doubled("ABAB", "AB")
    (True, True)
    """
    if len(flat) != 2 * len(name) or not name:
        return False

    @functools.lru_cache(maxsize=None)
    def walk(pos: int, i: int, j: int) -> bool:
        if pos == len(flat):
            return i == j == len(name)
        c = flat[pos]
        if i < len(name) and name[i] == c and walk(pos + 1, i + 1, j):
            return True
        return j < len(name) and name[j] == c and walk(pos + 1, i, j + 1)

    try:
        return walk(0, 0, 0)
    finally:
        walk.cache_clear()


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
    bases, bit_at = _indexed_bases(table, names)
    # 図の**他の名前セルも共有する頭文字**は、その図のフィールド命名の一部（DMA_INTFCRは
    # 全セルが`C`＝clearで始まる）。en版RM p173の記述表は`TCIFx`と接頭辞なしで書くので、
    # bit1に在る`CTCIF1`が偶然`TCIF`+bit1と一致して`TCIF1`へ縮みかけた（索引はチャネル番号で
    # bit番号ではない）。3セル以上が同じ頭文字なら、**その頭文字を落とすだけの候補**
    # （`n == flat[1:]`）は認めない。
    #
    # 「頭文字が違えば全部拒否」にすると広すぎた——`TUSARTU4RST`（`USART4RST` の交錯）は
    # 同じ行に T で始まる壊れたセルが3つ並ぶために弾かれ、直せていなかった（2026-09-10）。
    # 守りたいのは「先頭1字を落として別の名前にする」形だけなので、そこに絞る。
    heads: dict[str, int] = {}
    for cell in table["cells"]:
        if cell["row_start"] < 1:
            continue
        head = (cell.get("text") or "").replace("\n", "").strip()[:1]
        if head.isalpha():
            heads[head] = heads.get(head, 0) + 1
    fixed = 0
    for cell in table["cells"]:
        # 判定は**描画後の形**で行う——`apply_bitfield`の連結は改行を残すことがあり
        # （`HSYNCS\nCS`）、`cell_html`が識別子として地続きに繋いで`HSYNCSCS`になる。
        flat = (cell.get("text") or "").replace("\n", "").strip()
        if len(flat) < 4 or flat in names:
            continue
        if " " not in flat:
            short = _undoubled_tail(flat)
            if short and len(short) >= 3 and short in names:
                cell["text"] = short
                fixed += 1
                continue
        # 末尾の二重だけでなく、**縦割れの断片が交錯して混ざる**壊れ方もある
        # （`ATACAMTADCMD`＝`ATACMD`、`CTBXBEF`＝`CTXBEF`、`Reser Cved`＝`Reserved`、
        # `DBCDKEBNCKDEN`＝`DBCKEND`。PDF↔MD突合サブエージェントが1文書で107件を検出）。
        # 正しい名前は記述表のName列に在り、**その文字が順番どおり含まれる**という関係が
        # 成り立つ。候補が1つに決まるときだけ差し替える（長さは名前の2倍+2まで——
        # `Reserved bits must be 0`のような説明文を名前へ潰さないための歯止め）。
        # 索引付きの名前は記述表に無いので、base（記述表/無傷の兄弟）＋**そのセル自身の列の
        # bit番号**で組む（`PENDSTA15`）。索引を隣のbitの値と取り違えないよう、候補は列ごと。
        single = cell["column_end"] - cell["column_start"] == 1
        bit = bit_at.get(cell["column_start"], "") if single else ""
        # **そのセル自身が既に「base＋自分の列のbit番号」の形なら正しい**ので触らない。
        # DMA_INTFCRの`CTCIF1`（bit1・記述表は族名`CTCIFx`）を、`TCIFx`由来の`TCIF1`へ
        # 縮めるところだった——落ちる`C`が`TCIF1`にも在るため重複判定を通ってしまう
        # （zh版4文書でPDF↔MD突合の抽出中に発見。中断標志清除レジスタのCは意味を持つ）。
        if bit.isdigit() and any(flat == base + bit for base in bases):
            continue
        pool = names | ({base + bit for base in bases} if bit.isdigit() else set())
        # 索引がbit番号でない図（DMA_INTFRのチャネル番号`TEIF7`が bit27 に在る）では、**描画文字の
        # 中の数字**を索引にした綴りも候補にする（V003RM.en p66 `TEIFTE7I F`。全面見直しの指摘）。
        # 交錯の証拠として、描画文字が候補の1.5倍以上の長さであることを求める（`CTCIF1`→`TCIF1`
        # のような1文字差は通さない）。
        digits = re.findall(r"\d+", flat)
        if digits:
            compact = len(flat.replace(" ", ""))
            pool = pool | {base + d for base in bases for d in digits
                           if compact >= 1.5 * (len(base) + len(d))}
        def survivors(edges: str) -> list[str]:
            return [n for n in pool
                    if len(n) >= 3 and " " not in n and n != flat
                    and len(flat) <= 2 * len(n) + 2
                    and not (n == flat[1:] and heads.get(flat[:1], 0) >= 3)
                    and not _truncates_index(flat, n)
                    and _only_duplicate_glyphs(flat, n, edges)
                    and _is_subsequence(n, flat)]

        candidates = survivors("")
        # 自セルの中だけでは決まらなかったときに限り、**隣と接する1字**を重複の出所として
        # 許す（`_only_duplicate_glyphs`の`edges`）。後詰めにするのが要——先に混ぜると
        # `TXFITFXOFEI`に`TXFIFOE`と`TXFIFOF`の2つが立って**既に直っていたセルが戻った**し、
        # SDIO_ICRの`STBITERRC`が同じページのMASK側の`STBITERRIE`へ化けた（実測）。
        # 併せて、**候補が描画文字の接頭辞になる形**（`ADC2_ETRGINJ_RM`→`ADC2_ETRGINJ_R`）は
        # 認めない——末尾を落とすだけの関係は交錯の形ではなく、この例では記述表のName列が
        # 折り返しで`M`を落としていて図のほうが正しかった。
        if not candidates:
            edges = "".join(ch for ch in _touching_glyphs(table, cell)
                            if ch.isalpha())
            if edges:
                candidates = [n for n in survivors(edges)
                              if not flat.replace(" ", "").startswith(n)]
        # **記述表に実在する綴りを、合成した索引付きより優先する。** 合成候補
        # （`base`＋描画文字の中の数字）は「索引がbit番号でない図」のための後詰めで、
        # 記述表がその名前をそのまま載せているなら合成する必要が無い。優先しないと
        # `SPI1SRPSIT1RST` に `SPI1RST`（記述表）と `SPI1RST1`（`SPI1RST`＋文字中の`1`）の
        # 2つが立って決まらず、**混ざった綴りがそのまま残っていた**（2026-09-10の実測で
        # 16セル・4文書。`TIM9TRISMT9RST`・`CCRCCFCARILCFAIL`・`CMDSCEMNTDCSENTC` ほか）。
        literal = [n for n in candidates if n in names]
        if literal:
            candidates = literal
        if len(candidates) > 1:
            # `RXFIRFOXEFIIFOEE I`には`RXFIFOEIE`と`RXFIFOFIE`の両方が部分列として入る。1つの
            # レジスタに同じ名前は1度しか現れないので、**同じ図の別セルに既に在る綴り**は候補から
            # 外す（FV2x_V3xRM.en p590 R32_SDIO_MASK。全面見直しの指摘）。
            present = {(c.get("text") or "").replace("\n", "").strip()
                       for c in table["cells"] if c is not cell}
            candidates = [n for n in candidates if n not in present]
        if len(candidates) > 1:
            # **丁度2つ交錯している候補**が1つだけならそれ。記述表に `CCRCFAIL` と
            # `CCRCFAILC` のように片方が他方の接頭辞である名前が並ぶと、部分列の判定では
            # どちらも通る——`CCRCCFCARILCFAIL` は16字なので8字の方だけが2倍に合う
            # （2026-09-10。SDIO の状態レジスタで5セル残っていた）。
            doubled = [n for n in candidates if _is_doubled(flat, n)]
            if len(doubled) == 1:
                candidates = doubled
            elif len({len(n) for n in candidates}) == len(candidates):
                # **いちばん長い候補**を採る。描画文字は「正しい名前＋重複したグリフ」なので、
                # 長い名前ほど多くを説明する——`CTIMCETOIMUTECO`（15字）には `CTIMEOUT` と
                # `CTIMEOUTC` の両方が入るが、余りが少ないのは後者で、隣のセルも `DTIMEOUTC`
                # （同じ clear ビットの並び）。長さが同じ候補が混じるときは決め手にならないので
                # 使わない（2026-09-10）。
                candidates = [max(candidates, key=len)]
        if len(candidates) == 1:
            cell["text"] = candidates[0]
            fixed += 1
    return fixed


_RECOVER_TOKEN = re.compile(r"[A-Za-z0-9_\[\]:.]{2,}")


def split_line_merges(page: dict) -> dict[str, tuple[str, str]]:
    """**同じ視覚行が x のある位置で二つに割れ、境目の1文字が両側に入った**行の対を見つけ、
    `{左のline_id: (右のline_id, 右の続き（先頭の重複文字を除く））}` を返す。

    **呼ぶのはconverterだけ**（1.9.0）。それまではexporterとparityが各々これを呼んで
    描画時に繋いでおり、bundleの行は割れたままだった。

    zh版datasheetの本文は全行が x≈241 で `…対外`/`外多组…` のように割れ、1ページに25行も
    「途中で改行して1文字が二重」に見えていた（V002DS0.zh・V006DS0.zh・M030DS2.zh p6。
    全面見直しの指摘）。条件は**同じ高さ（上端差≤1.5pt）・左右が接している（隙間≤3pt）・
    同じフォントサイズ・左の末尾文字＝右の先頭文字**。2段組の独立した列は末尾と先頭が
    一致しないので触らない。読み順で右が先に来る（文の後半が先に出る）ものも同じ対として繋ぐ。
    """
    lines = [l for l in page["lines"] if (l.get("text") or "").strip()
             and l.get("role") not in ("header", "footer")]
    merge: dict[str, str] = {}
    skip: set[str] = set()
    used: set[str] = set()
    pairs: list[tuple[dict, dict]] = []
    for a in lines:
        if a["id"] in used:
            continue
        ax0, ay0, ax1, ay1 = a["bbox"]
        for b in lines:
            if b is a or b["id"] in used:
                continue
            bx0, by0, bx1, by1 = b["bbox"]
            if abs(ay0 - by0) > 1.5 or not -1.0 <= bx0 - ax1 <= 3.0:
                continue
            if abs((a.get("font_size") or 0) - (b.get("font_size") or 0)) > 0.6:
                continue
            ta, tb = a["text"], b["text"]
            if not ta.strip() or not tb.strip() or ta.rstrip()[-1] != tb.lstrip()[0]:
                continue
            # 本文らしさ: 左半分に空白かCJKがあり、識別子や数だけの行（pin図の`11`/`12`・
            # `SERDES_TXP`/`PE4`）ではない
            core = ta.strip()
            if len(core) < 4 or not (" " in core or _has_cjk(core)):
                continue
            pairs.append((a, b))
            used.update((a["id"], b["id"]))
            break
    # 系統的な割れだけ採る——同じ境界x（±2pt）に3対以上並ぶこと。偶然の一致（隣り合う
    # ラベルの末尾と先頭が同じ文字）は1〜2対で止まる。
    for a, b in pairs:
        x = a["bbox"][2]
        if sum(1 for a2, _ in pairs if abs(a2["bbox"][2] - x) <= 2.0) >= 3:
            merge[a["id"]] = (b["id"], b["text"].lstrip()[1:])
            skip.add(b["id"])
    return merge


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u30ff" or "\uff00" <= ch <= "\uffef"
               for ch in text)


def recovered_lines(page: dict, figure_regions: list | tuple = ()) -> list[dict]:
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

    さらに**描画済みの図の領域に入る行だけ**を拾う（`figure_regions`）。図の外で拾った分は
    PDF↔MD突合サブエージェント（zh版RM 6ページ）が「bit図の破片が本文へ重複して出る」と
    判定した——`INTENINTENINTENINTEN`・`A15 A14 A13`（`STA15`等の再切り出し）・`# TDes0`が
    本文の見出しに。図の中なら`<details>🖼 Text parsed from the figure above`の中に入り、
    「図から読めた文字」として意味が通る。判定が一致した実測: 突合がOKと言った2ページは
    全行が図の中、WRONGと言った4ページは図の中0行。
    """
    if not figure_regions:
        return []
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
        box = line["bbox"]
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if not any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in figure_regions):
            continue
        out.append(line)
    return out


def reading_stream(page: dict, figure_regions: list | tuple = ()) -> list[dict]:
    """`reading_order`に`recovered_lines`を縦位置で差し込んだ読み順。exporterとparityが
    同じ関数を使うので、拾い直した行も同じ位置・同じ順で検査される。"""
    recovered = recovered_lines(page, figure_regions)
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
        # 3行の断片スタック（`MA`/`XC`/`H`＝`EXMAXCH`）も同じ残骸——2行までに絞ると
        # 30表が残った（PDF↔MD突合の指摘）。中身が本体表に在ることは下で必ず確かめる。
        if (table.get("column_count") or 0) > 1 or (table.get("row_count") or 0) > 3:
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
    画像＋折りたたみの平文になり、表として読めなかった。全corpusで**106表・37文書**が該当
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
    # 図のラベル格子（タイミング図の`CH0 CH1 CH2 …`・流れ図の枠）は**穴が多く、1行目が
    # 揃わない**。罫線表として描くと空セルばかりの格子になり読めない（zh版RM p175/600/678を
    # PDF↔MD突合が指摘）。埋まり6割以上＋1行目が全部埋まっていることを要求する。
    if len(filled) < 0.6 * rows * columns:
        return False
    per_row: dict[int, int] = {}
    for cell in filled:
        per_row[cell["row_start"]] = per_row.get(cell["row_start"], 0) + 1
    first = [c for c in table["cells"] if c["row_start"] == 0]
    if not first or any(not (c.get("text") or "").strip() for c in first):
        return False
    # 波形図の数字格子（`7 6 5 4 …`が1文字ずつのセル）と、同じ語が2回並ぶ壊れたセル
    # （`List filter List filter`）は表ではない（PDF↔MD突合の指摘。H417RM.en p594/p807）。
    if sum(1 for c in filled if len((c.get("text") or "").strip()) <= 1) >= 0.6 * len(filled):
        return False
    for cell in filled:
        words = (cell.get("text") or "").split()
        half = len(words) // 2
        if half and words[:half] == words[half:half * 2]:
            return False
    # 図の箱の格子は**小さく、枠の隙間が完全な空行になる**（`Laye FI|er IFO|1`＝図中の
    # `Layer 1 FIFO`の箱が縦割れしたもの。H417RM.en p979／zh p824をPDF↔MD突合が指摘）。
    # 5行以下で空行を含むものは表でない——datasheetのpin表は80行の中に空行が混じるが
    # 小さくないので残る（この条件に当たるのは全corpusで2表、いずれも同じ図のen/zh）。
    if rows <= 5 and len({c["row_start"] for c in filled}) < rows:
        return False
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
            if (_overlap_frac(glyph["bbox"], obox) >= 0.5
                    and _glyph_still_in_other(glyph, obox, other_text, chars)):
                return True
    return False


def _glyph_still_in_other(glyph: dict, obox: list[float], text: str, chars: list[dict]) -> bool:
    """相手セルの**その字形**が、相手の綴りにまだ残っているか。

    `_at_line_edge`は文字の一致しか見ないので、**同じ文字が相手の別の場所にある**だけで
    「相手の持ち物」と誤認した——`IACTS | IACTS`（bit図の名前が列幅より広く、左の`S`が
    面積の78%で右セルに掛かる）で、右セルの綴りは末尾に**別の**`S`を持つため、左の`S`が
    落ちて`IACT`（Markdownでは`IACT9`）になっていた（`CH32M030RM.en` p46。再突合の指摘）。
    先に`strip_boundary_dupes`が右セルの先頭`S `を落としているので、この字形は右の綴りの
    どこにも残っていないのに、右からも左からも消えていた。

    字形が相手の綴りから消える経路は`strip_boundary_dupes`の**行端**の除去（と1文字だけの行）
    しか無い。だから判定は字形の**位置**で決まる: 相手の自グリフ（面積の半分以上が相手に入る）
    を同じ視覚行（top±1pt）で並べ、この字形が**行の中程**なら常に残っている（真）、**左端**なら
    相手の綴りに`ch`で始まる行があるか、**右端**なら`ch`で終わる行があるか（1字だけの行はどちらか）。

    2回やり直した（2026-09-09）。(1) 中程を偽にしていた版は、1行に2語の結合セル
    `td(ALE-NWE) th(NWE-ALE)`の語末`)`を「相手のものでない」として隣の`t\\nw(NWE)`の先頭に
    残した（H417DS0.en p128）。(2) 個数（相手に半分以上入る`ch`の字形数 ≤ 綴りの`ch`数）で見た版は、
    相手が**別の迷子**を抱えていると崩れた——`IACTS`の右セルは左からの`S`も抱えるので個数が合わず、
    その右セルの末尾`S`（さらに右の`Reserved`にも掛かる）を「相手のものでない」として
    `S\\nReserved`を作った（M030RM.en p46・V205RM.en p81。走行2の前後比較で捕捉）。

    >>> chars = [{"text": "S", "bbox": [0, 0, 4, 10]}, {"text": "I", "bbox": [6, 0, 8, 10]},
    ...          {"text": "S", "bbox": [8, 0, 12, 10]}]
    >>> _glyph_still_in_other(chars[0], [1, 0, 12, 10], "IS", chars)   # 左端の字形。行頭はI
    False
    >>> _glyph_still_in_other(chars[2], [1, 0, 12, 10], "IS", chars)   # 右端の字形。行末はS
    True
    >>> _glyph_still_in_other(chars[1], [1, 0, 12, 10], "XX", chars)   # 中程は常に残っている
    True
    """
    ch = glyph.get("text")
    line = sorted((g for g in chars if (g.get("text") or "").strip()
                   and _overlap_frac(g["bbox"], obox) >= 0.5
                   and abs(g["bbox"][1] - glyph["bbox"][1]) < 1.0),
                  key=lambda g: g["bbox"][0])
    same = [g is glyph or g["bbox"] == glyph["bbox"] for g in line]
    if not any(same):
        return False
    first, last = same[0], same[-1]
    if not first and not last:
        return True
    lines = [part.strip() for part in text.split("\n") if part.strip()]
    return ((first and any(part[0] == ch for part in lines))
            or (last and any(part[-1] == ch for part in lines)))


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


def text_grid(merged: dict, field: str = "text") -> tuple[list[list[str | None]], list[int]]:
    """結合済み論理表 → 文字の格子（抽出器向け。spanの先頭位置に文字を置く）。

    `field="text_split"`にすると、converterが下付きを戻す**前**の綴り（版面の割り方。
    無いセルは`text`）を置く。改行が下付きの境界を示すので、そこから正規化記号を
    作る抽出器（`operating_rows.norm_symbol`の`I\nDD`→`I_DD`）がこちらを読む。
    """
    rows: list[list[str | None]] = [[None] * merged["width"]
                                    for _ in range(merged["row_count"])]
    for cell in merged["cells"]:
        text = cell.get(field) if field != "text" else cell["text"]
        rows[cell["row_start"]][cell["column_start"]] = (
            cell["text"] if text is None else text)
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

    **変換器が表の外から拾った列は行ラベル**として先頭（右外なら末尾）の列に残す
    （下の`outside`。レジスタ配列の`IPRIOR63`）。

    >>> table = {"id": "t", "bbox": [0, 0, 100, 20], "row_count": 1, "column_count": 3,
    ...          "cells": [
    ...     {"id": "t-label-left", "text": "IPRIOR63", "bbox": [0, 10, 20, 20],
    ...      "row_start": 0, "row_end": 1, "column_start": 0, "column_end": 1},
    ...     {"id": "t-cell-0001", "text": "PRIO_1", "bbox": [20, 10, 60, 20],
    ...      "row_start": 0, "row_end": 1, "column_start": 1, "column_end": 2},
    ...     {"id": "t-cell-0002", "text": "PRIO_0", "bbox": [60, 10, 100, 20],
    ...      "row_start": 0, "row_end": 1, "column_start": 2, "column_end": 3}]}
    >>> apply_bitfield(table, None, [("7", 40.0), ("0", 80.0)])
    >>> table["row_count"], table["column_count"]
    (2, 3)
    >>> [(c["row_start"], c["column_start"], c["text"]) for c in table["cells"]]
    [(0, 1, '7'), (0, 2, '0'), (1, 0, 'IPRIOR63'), (1, 1, 'PRIO_1'), (1, 2, 'PRIO_0')]
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

    def outside(cell: dict) -> str | None:
        """bit中心の**外に丸ごと**あるか（"left"/"right"/None）。"""
        box = cell["bbox"]
        if any(box[0] <= x < box[2] for x in xs):
            return None
        return "left" if box[2] <= min(xs) else ("right" if box[0] > max(xs) else None)

    # **変換器が表の外から拾った列**（`recover_outer_column`の`-outer-`・
    # `recover_sibling_labels`の`-label-`）はbitフィールドではない——レジスタ配列の
    # 行ラベル（`IPRIOR63`・`IALLOC63`・`IPRIOR17`）。bit中心はpdfplumberの格子から
    # 決まるので外から足した列に中心は無く、`bit_span`のnearフォールバックが端のbit列へ
    # 寄せ、最後のdedupで**フィールドに上書きされて消えていた**（`CH32FV2x_V3xRM.zh`
    # p107の`IPRIOR63`はMarkdownのどこにも出ていなかった。再突合の指摘）。
    #
    # 根拠をidにするのは、**それが変換器自身が記録した出自**だから。同じ「中心の外」には
    # pdfplumberの格子のセルも来る——番号行が16列のうち12〜13列ぶんしか無い図
    # （`CH32H417RM.en` p620の`FBM`×4と`15`..`12`、`CH32V407RM.en` p224の`Reserved`）で、
    # これらは本物のフィールドなので触らない。全corpus実測: bit図9,760件のうち中心の外に
    # セルがあるのは**33件**で、`-label-`/`-outer-`が24件（全部レジスタ配列の行ラベル）・
    # `-cell-`が9件（全部本物のフィールド）。
    labels = [c for c in fields
              if ("-label-" in c.get("id", "") or "-outer-" in c.get("id", ""))
              and outside(c)]
    if labels:
        marked = {id(c) for c in labels}
        fields = [c for c in fields if id(c) not in marked]
        if not fields:
            return          # ラベルだけの表は組み直さない（bit図ではない）
    field_min = min(c["row_start"] for c in fields)
    cells: list[dict] = []
    for cell in fields:
        start, end = bit_span(cell)
        cells.append({**cell, "column_start": start, "column_end": end,
                      "row_start": cell["row_start"] - field_min + 1,
                      "row_end": cell["row_end"] - field_min + 1})
    # 行ラベルは仮に列-1（左）/width（右）へ置く。**縦連結の対象にしない**（`IPRIOR17`と
    # `IPRIOR16`が1セルに繋がる。L103RM.zh p70）ので、グループ分けの後に足す。
    label_cells = [{**cell,
                    "column_start": -1 if outside(cell) == "left" else width,
                    "column_end": 0 if outside(cell) == "left" else width + 1,
                    "row_start": max(1, cell["row_start"] - field_min + 1),
                    "row_end": max(2, cell["row_end"] - field_min + 1)}
                   for cell in labels]
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
        # 行の**3セル以上が同じ頭文字**で始まるなら、それは隣からのbleedではなく本物の綴り
        # ——EXTI_SWIEVRの下段は`R15`/`R 14`/`R13`…と16列に同じ`R`が並ぶ。この歯止めが無いと
        # `R 14`の`R`を右隣`R13`の`R`と見て落とし、上段と繋いで`SWIE14`になっていた（PDF↔MD
        # 突合が11セルで指摘。parityは落ちない——bundleの文字が消えても順序は保たれるため）。
        heads: dict[str, int] = {}
        for cell in row_cells:
            text = cell.get("text") or ""
            if text[:1].strip():
                heads[text[0]] = heads.get(text[0], 0) + 1
        for index, cell in enumerate(row_cells):
            text = cell.get("text") or ""
            if len(text) >= 2 and text[1] in " \n" and text[0].strip():
                if heads.get(text[0], 0) >= 3:
                    continue
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
    # 跨るセルが無くても、**全列が1bit幅の2段で上段が同じ綴りの繰り返し**なら折り返した
    # 名前——CANx_FMCFGRの下位（FV2x_V3xRM.en p447）は`FBM`×16の下に`FB15M`…`FB0M`が並び、
    # 跨るセルが無いので2段のフィールド行と見なされ、`FBM`の行と数字の行に割れていた
    # （PDF↔MD突合の指摘）。TIMのCCMR（出力名/入力名の2段）は上段の綴りが列ごとに違う。
    rows_present = sorted({c["row_start"] for c in cells if c["row_start"] >= 1})
    if not has_span and len(rows_present) == 2:
        top = [c for c in cells if c["row_start"] == rows_present[0]]
        bottom = [c for c in cells if c["row_start"] == rows_present[1]]
        top_texts = [(c.get("text") or "").strip() for c in top]
        bottom_texts = [(c.get("text") or "").strip() for c in bottom]
        same_word = len(set(top_texts)) == 1 and top_texts[0].isalpha()
        # 上段が英字だけの短い名（列ごとに違ってよい: DMA_INTFCRの`CTEIF`/`CHTIF`/`CTCIF`/`CGIF`）で
        # 下段が全部数字なら、名前＋索引の折り返し（V407RM.en p155。全面見直しの指摘）。
        alpha_over_digits = (all(x.isalpha() and len(x) <= 8 for x in top_texts)
                             and bottom_texts and all(x.isdigit() for x in bottom_texts))
        if (len(top) >= 8 and (same_word or alpha_over_digits)
                and all(c["column_end"] - c["column_start"] == 1 for c in top)
                and any(ch.isdigit() for x in bottom_texts for ch in x)):
            has_span = True
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
    cells.extend(label_cells)
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
    # 行ラベルを入れたぶん列をずらす（左のラベルは列0、bit列は1..width）。ヘッダ行の列0は
    # セルが無い穴になり、`table_html`が`<th></th>`で埋める（行ラベルに番号は無い）。
    if label_cells:
        if any(c["column_start"] < 0 for c in cells):
            for cell in cells:
                cell["column_start"] += 1
                cell["column_end"] += 1
        width = max(c["column_end"] for c in cells)
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
        # 重なりセルの残骸（本体表に中身が含まれる1列断片）は描かれないので連鎖にも入れない。
        # p145の残骸が「前ページ最後の表」として続き（p146の11行）を引き取り、残骸ごと描かれず
        # **11行が出力から消えていた**（V407RM.en Table 11-1。全面見直しの指摘）。
        phantoms = fragment_tables(page)
        tables = sorted((t for t in page["tables"] if t["id"] not in phantoms),
                        key=lambda t: (t["bbox"][1], t["bbox"][0]))
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
    for page in pages:
        for table in page["tables"]:
            out.setdefault(table["id"], {"chain": [(page["number"], table)], "start": True,
                                         "merged": None, "start_page": page["number"]})
    return out
