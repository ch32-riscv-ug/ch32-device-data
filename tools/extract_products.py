#!/usr/bin/env python3
"""Extract the per-SKU product comparison table from a datasheet.

This is the table that enumerates every orderable model with its memory, pin count
and peripheral counts. It is the source for the SKU universe itself, and for the
identity, memory, package and peripheral parts of a record.

Two layouts occur. CH32V003 and CH32V006 give one row per model:

    Model         | Flash memory | SRAM | Pin No. | ... | Package Form
    CH32V003F4P6  | 16K          | 2K   | 20      | ... | TSSOP20

CH32M030 and CH32L103 transpose it, one column per model:

    Model/Resource |      | C8U3 | C8T7 | ...
    Pin Number     |      | 48   | 48   | ...

Values are kept under the document's own labels rather than mapped onto schema
fields, so nothing is lost before the shape of the record is settled.

Usage:
    uv run tools/extract_products.py <datasheet.pdf> [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

MODEL = re.compile(r"^CH32[A-Z0-9]{4,}$")
FAMILY = re.compile(r"^CH32[A-Z]\d{3}$")
# A model suffix as the transposed layout writes it. The shape varies widely --
# C8T6, K8U7 and F6P1 alternate letters and digits, VET6 and RDU6 do not, and
# CH32V303 is listed simply as CB, RB, RC. CH32V203 writes F8x6 and C8x6, the
# lower-case x standing for either package letter, so one column covers both
# F8P6 and F8U6. Anything short and upper-case (plus that x) qualifies, which is
# only safe because a family name must head the column group.
SUFFIX = re.compile(r"^[A-Z][A-Z0-9x]{1,5}$")
# The narrower shape, which is unambiguous enough to stand without a family row.
PLAIN_SUFFIX = re.compile(r"^[A-Z]{1,2}\d[A-Zx]\d?[A-Z]?\d?$")
MAX_PAGES = 16


# 零等待領域が**列ではなく脚注の散文**にある family がある。CH32X305/X315 の
# 比較表は `Code FLASH（字节） 480K(1)` の1列しか持たず、その `(1)` が指す注が
#
#     注：1.480KB闪存包含192KB的零等待程序运行区域和288KB非零等待区域。
#     Note: 1. The 480KB flash memory contains 192KB of zero-wait program
#           execution area and 288KB of non-zero-wait area.
#
# と書く。EVT の Link.ld はどれも `FLASH 192K` を link していて、480K を
# `flash_bytes` に採ると linker script が 2.5 倍に見積もる（worklist の F-14）。
# 脚注番号と値の対応を作らなくても、**文が総量と零等待量の両方を書いている**ので
# 総量が一致することで結び付けられる。
ZERO_WAIT = {
    "zh": re.compile(r"(?P<total>\d+)\s*KB?\s*闪存包含\s*(?P<zero>\d+)\s*KB?\s*的?零等待"),
    "en": re.compile(r"(?P<total>\d+)\s*KB\s+flash\s+memory\s+contains\s+"
                     r"(?P<zero>\d+)\s*KB\s+of\s+zero[-\s]?wait", re.IGNORECASE),
}
# 注入するラベル。既存の `Code FLASH（字节）` より具体的な綴りなので
# build_tables の「同じフィールドに寄る列は具体的な方を promote」に乗る。
ZERO_WAIT_LABEL = {"zh": "零等待Code FLASH（字节）", "en": "Zero-wait Code FLASH (bytes)"}


def read_zero_wait(pdf, lang: str) -> tuple[int, str] | None:
    """(page_no, "192K") — 脚注が言う零等待領域。無ければ None。

    折り返しで文が2行に割れるので、隣接2行の窓で読む。
    """
    pattern = ZERO_WAIT[lang]
    for page in pdf.pages[:MAX_PAGES]:
        lines = (page.extract_text() or "").splitlines()
        for i, _ in enumerate(lines):
            found = pattern.search(" ".join(lines[i:i + 2]))
            if found:
                result = page.page_number, f"{found.group('zero')}K"
                page.close()
                return result
        page.close()
    return None


# 比較表の下に並ぶ脚注。`3.CH32V303RCT7芯片支持的工作温度范围为：-40℃～105℃。`
# 全角ピリオドもある。番号だけ拾えばよく、本文の型番は PART_NUMBER で見る。
FOOTNOTE_LINE = re.compile(r"^\s*(?P<number>\d{1,2})\s*[.．、]\s*(?P<text>\S.*)$")
# 値に付く脚注の印。`-40℃～85℃（3）`
FOOTNOTE_MARK = re.compile(r"[（(](\d{1,2})[)）]")


def read_footnotes(page) -> dict[str, str]:
    """{脚注番号: 本文}。表の下に並ぶ注記。"""
    out: dict[str, str] = {}
    for line in (page.extract_text() or "").splitlines():
        found = FOOTNOTE_LINE.match(line.strip())
        if found:
            out.setdefault(found.group("number"), found.group("text"))
    return out


def unrotate(page, table, rows: list[list[str]]) -> list[list[str]]:
    """縦書きのセルを読み直す。

    比較表の見出し列は狭いので、長い題は **90度回して**組まれる
    （CH32V203 の `Communication interface`）。`table.extract()` はその文字を
    逆順に返すので、そのままだと `ecafretninoitacinummoC` が属性名になる。
    文字は `upright: False` で確実に見分けられ、しかも `page.chars` を文書順に
    読めば正しい向きで出る（空白も戻る）ので、そのセルだけ読み直す。

    回った文字が 1 つも無いページでは何もしない——ほとんどのページがそうで、
    セルごとに文字を走査する費用を払わずに済む。
    """
    turned = [c for c in page.chars if not c.get("upright", True)]
    if not turned:
        return rows
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            if not text or i >= len(table.rows) or j >= len(table.rows[i].cells):
                continue
            box = table.rows[i].cells[j]
            if not box:
                continue
            x0, top, x1, bottom = box
            inside = [c for c in turned
                      if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                      and top <= (c["top"] + c["bottom"]) / 2 <= bottom]
            if inside:
                rows[i][j] = flatten("".join(c["text"] for c in inside))
    return rows


def flatten(cell: str | None) -> str:
    return (cell or "").replace("\n", "").strip()


# 行を分ける縦の隙間。上付きの脚注番号（`Built-in Rd(1)` の `(1)`）は
# 2〜3pt 持ち上がるだけなので、これより小さい差は同じ行とみなす。
LINE_GAP = 4.0
# 行末がこれなら折り返しは語の途中。空白が残っていても切れ目ではない。
CONNECTORS = "-+/(_&"


def spaced(previous: str, piece: str) -> bool:
    """折り返しの前後を空白で継ぐか。

    行末に空白が残っていれば語の切れ目。ただし**漢字どうしの境目には入れない**
    ——中文は語を空白で区切らないので、`通用，`と`引脚兼容`の間の空白は
    版面の詰めであって語の切れ目ではない。
    """
    if previous == previous.rstrip():
        return False
    head, tail = previous.rstrip()[-1:], piece.strip()[:1]
    # 語を繋ぐ記号で終わっているなら、そこは語の切れ目ではない。
    # `General-`＋`purpose`・`MAC+`＋`10/100M PHY` は詰めて継ぐのが資料の綴り。
    if head in CONNECTORS:
        return False
    return head.isascii() or tail.isascii()


def dewrap(page, table, raw: list[list]) -> list[list[str]]:
    """セル内の折り返しを継ぐ。**空白が落ちたのか元から無いのかは版面が知っている。**

    `table.extract()` は行末の空白を落として改行だけを残すので、そこから先は
    文字列を見ても決まらない——`Low-power`＋`timer` は空白で折り返した所、
    `General-purp`＋`ose` は語の途中。改行を空文字で繋いでいたため
    `Communicationinterfaces`・`MAC+10/100MPHY`・`Low-powertimer` のように
    語が癒着していた（worklist の F-22）。

    **文字の層には行末の空白が残っている。** 折り返しが空白の位置で起きたなら
    その行の最後の文字は空白そのもので、語の途中で折れたなら空白は無い。
    推測ではなく資料が書いたとおりに継げる。

    行の切り分けだけ注意が要る。上付きの脚注番号は `top` が 2〜3pt ずれるので、
    厳密に揃えて分けると `Built-in Rd(1)` が3行に割れる。隙間で分ける。
    """
    wrapped = [(i, j) for i, row in enumerate(raw)
               for j, cell in enumerate(row) if cell and "\n" in cell]
    rows = [[flatten(c) for c in r] for r in raw]
    if not wrapped:
        return rows
    chars = page.chars
    for i, j in wrapped:
        if i >= len(table.rows) or j >= len(table.rows[i].cells):
            continue
        box = table.rows[i].cells[j]
        if not box:
            continue
        x0, top, x1, bottom = box
        inside = [c for c in chars
                  if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                  and top <= (c["top"] + c["bottom"]) / 2 <= bottom]
        if not inside:
            continue
        lines: list[list] = []
        for char in sorted(inside, key=lambda c: (c["top"], c["x0"])):
            if lines and char["top"] - lines[-1][0]["top"] <= LINE_GAP:
                lines[-1].append(char)
            else:
                lines.append([char])
        pieces = ["".join(c["text"] for c in sorted(line, key=lambda c: c["x0"]))
                  for line in lines]
        pieces = [p for p in pieces if p.strip()]
        if len(pieces) < 2:
            continue
        # 行末の空白が「ここは語の切れ目」と言っている。**継いだ後では消えて
        # しまう**ので、継ぐ前の行そのものを見る。
        text = pieces[0].strip()
        for previous, piece in zip(pieces, pieces[1:]):
            text += (" " if spaced(previous, piece) else "") + piece.strip()
        rows[i][j] = text.strip()
    return rows


# 継続ページの列を前の表に結び付けるときの許容差（pt）。同じ表の続きなら
# 罫線そのものなので 1pt も動かないが、PDF の丸めぶんだけ見る。
COLUMN_TOLERANCE = 3.0


def column_spans(table) -> list[tuple[float, float] | None]:
    """列ごとの x 範囲。結合セルは広いので、その列で**最も狭い**セルを採る。"""
    width = max(len(row.cells) for row in table.rows)
    spans: list[tuple[float, float] | None] = []
    for col in range(width):
        boxes = [row.cells[col] for row in table.rows
                 if col < len(row.cells) and row.cells[col]]
        spans.append(min(((b[0], b[2]) for b in boxes), key=lambda s: s[1] - s[0])
                     if boxes else None)
    return spans


def continued_columns(spans, carry: dict) -> dict[int, str] | None:
    """見出しの無い継続ページで、列と型番の対応を前の表から引き継ぐ。

    **列番号では合わない。** CH32L103 の英語版は継続ページで見出し列が2段に
    割れ、9列の表が10列になる。罫線の x 範囲は同じ表の続きである限り動かない
    ので、そちらで結ぶ。全部の列が1つずつに当たらなければ**別の表**とみなす
    ——たまたま隣り合っただけの表を比較表の続きとして読むほうが害が大きい。
    """
    previous = carry.get("columns")
    if not previous or not spans:
        return None
    found: dict[int, str] = {}
    for (x0, x1), part in previous:
        hits = [j for j, span in enumerate(spans)
                if span and abs(span[0] - x0) <= COLUMN_TOLERANCE
                and abs(span[1] - x1) <= COLUMN_TOLERANCE]
        if len(hits) != 1 or hits[0] in found:
            return None
        found[hits[0]] = part
    # 見出し列が1つも残らない表は比較表ではない。
    return found if len(found) == len(previous) and min(found) >= 1 else None


def join_wrap(head: str, tail: str) -> str:
    """ページ境界で切れた文字列を継ぐ。

    折り返しの起きた場所が空白かどうかは版面が決めるので復元できないが、
    **欧文は空白でしか折り返せない**（CH32H417 の `USBHS (USB` ＋ `2.0)`）。
    漢字は任意の位置で折り返すので詰めて継ぐ。
    """
    if not head:
        return tail
    if head[-1].isascii() and tail[:1].isascii():
        return f"{head} {tail}"
    return head + tail


def identifier(cell: str | None) -> str:
    """型番・family 名として読むときの綴り。**空白は落とす。**

    `dewrap` は折り返しを資料の書いたとおりに継ぐので、版面の都合で
    `CH32V103`＋`C6T6` の間に空白が残っていれば `CH32V103 C6T6` になる。
    ラベルや値としてはそれが正しいが、**型番に空白は入らない**ので、
    識別子として突き合わせるときだけ詰める。
    """
    return re.sub(r"\s+", "", flatten(cell))


def fill_across(row: list[str]) -> list[str]:
    """Carry a value rightwards over the blank cells it spans."""
    out, last = [], ""
    for cell in row:
        last = cell or last
        out.append(last)
    return out


def read_row_layout(rows: list[list[str]]) -> list[dict] | None:
    """One row per model, labels merged from the header rows above."""
    first = next((i for i, r in enumerate(rows)
                  if r and MODEL.match(identifier(r[0]))), None)
    if first is None or sum(1 for r in rows[first:]
                            if r and MODEL.match(identifier(r[0]))) < 2:
        return None
    width = max(len(r) for r in rows)
    # 見出しは縦に何段か重なる。**最後の段が見出しそのもので、その上は群の名前。**
    # 繋いだ文字列だけを持つと `Communication interface CAN` の
    # `Communication interface` を後から剥がせない（worklist の F-20）。
    stacks = [[rows[j][c] for j in range(first) if c < len(rows[j]) and rows[j][c]]
              for c in range(width)]
    labels = [" ".join(stack).strip() or f"col{c}" for c, stack in enumerate(stacks)]
    groups = [" ".join(stack[:-1]).strip() for stack in stacks]
    products: list[dict] = []
    carried: list[str] = [""] * width
    for row in rows[first:]:
        if not row or not MODEL.match(identifier(row[0])):
            continue
        padded = list(row) + [""] * (width - len(row))
        # A blank cell repeats the model above it, which is how merged cells read.
        values = [cell or carried[i] for i, cell in enumerate(padded)]
        carried = values
        products.append(
            {"part_number": identifier(values[0]),
             "attributes": dict(zip(labels[1:], values[1:])),
             "_groups": dict(zip(labels[1:], groups[1:]))}
        )
    return products


def excepted(value: str, part: str, footnotes: dict[str, str]) -> bool:
    """この値に付く脚注が、この型番を名指しで別扱いしているか。

    比較表は同じ値が続く列を結合し、そこから外れる型番を脚注で断る。値を
    そのまま横へ及ぼすと、名指しされた型番だけ嘘になる（CH32V303RCT7 は
    表の -40〜85℃ ではなく脚注の -40〜105℃）。

    **注文型番が揃ってからでないと判定できない。** 比較表の列見出しは
    `CH32V303RC` のような略記で、RCT6 と RCT7 の両方を兼ねる。脚注が名指しする
    のは RCT7 だけなので、略記のまま突き合わせると RCT6 まで落ちる。呼ぶのは
    略記を展開したあと（`build_tables` の alias 展開の後）。
    """
    if not part:
        return False
    return any(part in footnotes.get(number, "").replace(" ", "")
               for number in FOOTNOTE_MARK.findall(value))


def read_column_layout(rows: list[list[str]], default_family: str,
                       footnotes: dict[str, str] | None = None,
                       spans: list | None = None,
                       carry: dict | None = None) -> list[dict] | None:
    """One column per model, attributes down the rows.

    `carry` は**同じ比較表の前のページ**から持ち越す状態。ページを跨いだ表を
    `pdfplumber` は別々の表として返すので、これが無いと継続ページは
    (a) 見出し行が無ければ列と型番の対応が付かず丸ごと落ち、
    (b) 折り返しの尻尾が親を失い、
    (c) 行グループの見出しが引き継がれない（F-19）。
    """
    def sku_cells(row: list[str], pattern: re.Pattern) -> int:
        # A bare family name spans a group of columns; it names the group, not a model.
        return sum(
            1
            for n in (identifier(c) for c in row[1:])
            if pattern.match(n) or (MODEL.match(n) and not FAMILY.match(n))
        )

    def family_row(upto: int) -> list[str] | None:
        for row in rows[:upto]:
            if sum(1 for c in row if FAMILY.match(identifier(c))) >= 1:
                filled = fill_across([identifier(c) for c in row])
                return [f if FAMILY.match(f) else default_family for f in filled]
        return None

    carry = {} if carry is None else carry
    header = None
    for i, row in enumerate(rows[:3]):
        # The loose shape is only trustworthy when a family name heads the group.
        loose_ok = family_row(i) is not None and sku_cells(row, SUFFIX) >= 2
        if loose_ok or sku_cells(row, PLAIN_SUFFIX) >= 2:
            header = i
            break

    if header is None:
        # 見出しを繰り返さない継続ページ。列は罫線の x 範囲で引き継ぐ。
        columns = continued_columns(spans, carry)
        if not columns:
            return None
        start = 0
    else:
        families = (family_row(header) or []) + [default_family] * len(rows[header])
        columns = {}
        for col, name in enumerate(rows[header]):
            name = identifier(name)
            if MODEL.match(name):
                columns[col] = name
            elif SUFFIX.match(name):
                columns[col] = families[col] + name if col < len(families) else name
        if len(columns) < 2:
            return None
        start = header + 1

    products = {col: {"part_number": pn, "attributes": {}} for col, pn in columns.items()}
    # **見出しは1列とは限らない。** 型番の列より左にある列は全部見出しで、
    # CH32H417 の比較表はそこを2段に使う:
    #
    #     SRAM   内核1高速ITCM     128KB
    #            内核1高速DTCM     256KB   ← row[0] が空。行グループの子
    #            共享代码和数据区   512KB
    #
    # row[0] だけを見て空なら捨てていたので、**グループの最初の子しか残らず**
    # SRAM が 896KB のうち 128KB になっていた（worklist の F-15）。
    depth = min(columns)
    carried = [""] * depth
    # **同じ比較表の続きなら、見出しの段は前のページから続いている。**
    # 型番の並びが前の表と同じであることを条件にする（見出しを繰り返す
    # 継続ページはここを通る——CH32H417 の英語版がそれで、繰り返すのは
    # 型番の行だけ、行グループの `PDUSB` は繰り返さない）。
    continuation = list(columns.values()) == carry.get("parts")
    last_label = ""
    if continuation:
        for level, text in enumerate(carry.get("labels") or []):
            if level < depth:
                carried[level] = text
        last_label = carry.get("last_label", "")

    for row in rows[start:]:
        if not row:
            continue
        cells = [flatten(row[level]) if level < len(row) else ""
                 for level in range(depth)]
        values = [flatten(row[col]) if col < len(row) else ""
                  for col in sorted(products)]
        # **値を1つも持たない行は属性行ではない。** 転置レイアウトでは属性は
        # 必ずどれかの型番の欄に値を持つ。値が空で見出しだけある行は、
        # ページ境界で切れたセルの尻尾（F-19b）——CH32H417 の
        # `USBHS (USB` に続く `2.0)` がこれで、前のラベルに継ぐのが正しい。
        if any(cells) and not any(values):
            if not last_label:
                continue
            for level, cell in enumerate(cells):
                if cell:
                    carried[level] = join_wrap(carried[level], cell)
            joined = " ".join(part for part in carried if part).strip()
            if joined != last_label:
                carry.setdefault("renames", []).append((last_label, joined))
                last_label = joined
            continue
        for level, cell in enumerate(cells):
            if cell:
                carried[level] = cell
                # 上の段が変わったら下の段は無効。そうしないと見出しが1段だけの
                # 行（GPIO端口数）に、前のグループの子見出しが付いて回る。
                for lower in range(level + 1, depth):
                    carried[lower] = ""
        stack = [part for part in carried if part]
        label = " ".join(stack).strip()
        if not label:
            continue
        # 最後の段が見出しそのもの。その上は群の名前で、剥がせるように分けて持つ。
        group = " ".join(stack[:-1]).strip()
        last_label = label
        # **値の空欄は「左と同じ」。** 比較表は同じ値が続く列を横に結合するので、
        # 空いたセルは隣の型番と同じことを言っている。CH32V30x の Ethernet 行は
        #
        #     Ethernet | - | | | | | | | | 1G MAC+10M PHY | | |
        #                V303CB ────────→   V307RC ─────────────→
        #
        # で、`-`（無い）が V303/V305 の 8 型番に、`1G MAC+10M PHY` が V307 の
        # 3 型番に及ぶ。埋めないと **値を持つ 1 型番にしか属性が付かない**——
        # CH32V307RCT6 は Ethernet を持ち VCT6 は持たない、という形になっていた。
        #
        # 「空欄＝無い」ではない。**無いことは `-` と書かれる**ので取り違えない。
        # この読み方は独立した出所で検算できる——同じ表の封装形式の行は
        # V303RC が空欄で、左から埋めると LQFP64M になり、注文型番表から作った
        # `products.csv` の CH32V303RCT6 = LQFP64M と一致する。
        spread = ""
        for col, value in zip(sorted(products), values):
            if value:
                spread = value
            if not spread:
                continue
            products[col]["attributes"][label] = spread
            products[col].setdefault("_groups", {})[label] = group
            if not value:
                # **自分の欄が空で、左から流れてきた値**という印。脚注の例外は
                # これにだけ効かせる——その型番の欄に書いてある値なら、脚注が
                # 名指ししていても資料がそう書いたということなので落とせない。
                products[col].setdefault("_filled", set()).add(label)

    # 次の表が続きだったときに渡す状態。
    carry["parts"] = list(columns.values())
    carry["labels"] = list(carried)
    carry["last_label"] = last_label
    if spans:
        carry["columns"] = [(spans[col], part) for col, part in sorted(columns.items())
                            if col < len(spans) and spans[col]]
    return list(products.values())


def extract(pdf_path: Path) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    products: list[dict] = []
    seen: set[str] = set()
    with pdfplumber.open(pdf_path) as pdf:
        title = ""
        for line in pdf.pages[0].extract_text_lines() or []:
            # The English cover reads "CH32M030 Datasheet", the Chinese one
            # "CH32M030数据手册" with no space, so the name is not delimited.
            m = re.match(r"^(CH32[A-Z][0-9A-Z]{2,5}?)(?=[\s\u4e00-\u9fff]|$)", line["text"].strip())
            if m:
                title = m.group(1)
                break
        if not title:
            notes.append("先頭ページから family 名を読めず、転置表の型番を補完できません")
        # 比較表はページを跨ぐ。`pdfplumber` はページごとに別の表として返すので、
        # 前の表の状態をここで持ち回る（F-19）。**隣り合うページの間だけ**——
        # 間に別の内容が挟まったらもう続きではない。
        carry: dict = {}
        for pno, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
            if carry and pno > carry.get("page", 0) + 1:
                carry = {}
            for table in page.find_tables():
                rows = unrotate(page, table, dewrap(page, table, table.extract()))
                if not rows or len(rows[0]) < 4:
                    continue
                notes_here = read_footnotes(page)
                found = read_row_layout(rows)
                layout = "row"
                if not found:
                    layout = "column"
                    found = read_column_layout(rows, title, notes_here,
                                               column_spans(table), carry)
                    if found:
                        carry["page"] = pno
                for product in found or ():
                    # 脚注は値の横流しの例外を決めるが、判定は注文型番が
                    # 揃ってからでないとできない（excepted の説明）。持ち回す。
                    product["_footnotes"] = dict(notes_here)
                if not found:
                    continue
                # ページ境界で切れたラベルは、前のページに書いたものを直す。
                for old_label, new_label in carry.pop("renames", []):
                    for target in products + found:
                        for key in ("attributes", "_groups"):
                            holder = target.get(key)
                            if holder and old_label in holder:
                                holder[new_label] = holder.pop(old_label)
                        filled = target.get("_filled")
                        if filled and old_label in filled:
                            filled.discard(old_label)
                            filled.add(new_label)
                for product in found:
                    key = product["part_number"]
                    if key in seen:
                        # Continuation page: merge the further attributes in.
                        # **脚注も足す。** 比較表は複数ページに渡り、注記は
                        # 最後のページの下にある。最初のページのぶんだけ持って
                        # いると、`（3）` が指す注が手元に無いことになる。
                        for existing in products:
                            if existing["part_number"] == key:
                                existing["attributes"].update(product["attributes"])
                                existing.setdefault("_groups", {}).update(
                                    product.get("_groups") or {})
                                existing.setdefault("_footnotes", {}).update(
                                    product.get("_footnotes") or {})
                                existing.setdefault("_filled", set()).update(
                                    product.get("_filled") or set())
                        continue
                    seen.add(key)
                    product["_source"] = {"page": pno, "layout": layout}
                    products.append(product)
            page.close()
        lang = "zh" if "datasheet_zh" in str(pdf_path) else "en"
        split = read_zero_wait(pdf, lang)
    if split:
        page_no, value = split
        notes.append(f"零等待領域は脚注にある（p.{page_no}）: {value}")
        for product in products:
            product["attributes"][ZERO_WAIT_LABEL[lang]] = value
    return products, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    products, notes = extract(args.pdf)
    print(f"入力: {args.pdf}", file=sys.stderr)
    print(f"SKU: {len(products)} 件", file=sys.stderr)
    for p in products:
        attrs = p["attributes"]
        head = list(attrs.items())[:4]
        summary = " ".join(f"{k}={v}" for k, v in head)
        print(f"    {p['part_number']:<16} {summary[:74]}", file=sys.stderr)
    if notes:
        for n in notes:
            print(f"  - {n}", file=sys.stderr)
    if args.emit:
        json.dump(products, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
