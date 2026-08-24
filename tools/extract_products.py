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


def fill_across(row: list[str]) -> list[str]:
    """Carry a value rightwards over the blank cells it spans."""
    out, last = [], ""
    for cell in row:
        last = cell or last
        out.append(last)
    return out


def read_row_layout(rows: list[list[str]]) -> list[dict] | None:
    """One row per model, labels merged from the header rows above."""
    first = next((i for i, r in enumerate(rows) if r and MODEL.match(r[0])), None)
    if first is None or sum(1 for r in rows[first:] if r and MODEL.match(r[0])) < 2:
        return None
    width = max(len(r) for r in rows)
    labels = [
        " ".join(rows[j][c] for j in range(first) if c < len(rows[j]) and rows[j][c]).strip()
        or f"col{c}"
        for c in range(width)
    ]
    products: list[dict] = []
    carried: list[str] = [""] * width
    for row in rows[first:]:
        if not row or not MODEL.match(row[0]):
            continue
        padded = list(row) + [""] * (width - len(row))
        # A blank cell repeats the model above it, which is how merged cells read.
        values = [cell or carried[i] for i, cell in enumerate(padded)]
        carried = values
        products.append(
            {"part_number": values[0], "attributes": dict(zip(labels[1:], values[1:]))}
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
                       footnotes: dict[str, str] | None = None) -> list[dict] | None:
    """One column per model, attributes down the rows."""
    def sku_cells(row: list[str], pattern: re.Pattern) -> int:
        # A bare family name spans a group of columns; it names the group, not a model.
        return sum(
            1
            for n in (flatten(c) for c in row[1:])
            if pattern.match(n) or (MODEL.match(n) and not FAMILY.match(n))
        )

    def family_row(upto: int) -> list[str] | None:
        for row in rows[:upto]:
            if sum(1 for c in row if FAMILY.match(flatten(c))) >= 1:
                filled = fill_across([flatten(c) for c in row])
                return [f if FAMILY.match(f) else default_family for f in filled]
        return None

    header = None
    for i, row in enumerate(rows[:3]):
        # The loose shape is only trustworthy when a family name heads the group.
        loose_ok = family_row(i) is not None and sku_cells(row, SUFFIX) >= 2
        if loose_ok or sku_cells(row, PLAIN_SUFFIX) >= 2:
            header = i
            break
    if header is None:
        return None

    families = (family_row(header) or []) + [default_family] * len(rows[header])

    columns: dict[int, str] = {}
    for col, name in enumerate(rows[header]):
        name = flatten(name)
        if MODEL.match(name):
            columns[col] = name
        elif SUFFIX.match(name):
            columns[col] = families[col] + name if col < len(families) else name
    if len(columns) < 2:
        return None

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
    for row in rows[header + 1:]:
        if not row:
            continue
        for level in range(depth):
            cell = flatten(row[level]) if level < len(row) else ""
            if cell:
                carried[level] = cell
                # 上の段が変わったら下の段は無効。そうしないと見出しが1段だけの
                # 行（GPIO端口数）に、前のグループの子見出しが付いて回る。
                for lower in range(level + 1, depth):
                    carried[lower] = ""
        label = " ".join(part for part in carried if part).strip()
        if not label:
            continue
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
        carry = ""
        for col in sorted(products):
            value = flatten(row[col]) if col < len(row) else ""
            if value:
                carry = value
            if not carry:
                continue
            products[col]["attributes"][label] = carry
            if not value:
                # **自分の欄が空で、左から流れてきた値**という印。脚注の例外は
                # これにだけ効かせる——その型番の欄に書いてある値なら、脚注が
                # 名指ししていても資料がそう書いたということなので落とせない。
                products[col].setdefault("_filled", set()).add(label)
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
        for pno, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
            for table in page.find_tables():
                rows = unrotate(page, table,
                                [[flatten(c) for c in r] for r in table.extract()])
                if not rows or len(rows[0]) < 4:
                    continue
                notes_here = read_footnotes(page)
                found = (read_row_layout(rows)
                         or read_column_layout(rows, title, notes_here))
                for product in found or ():
                    # 脚注は値の横流しの例外を決めるが、判定は注文型番が
                    # 揃ってからでないとできない（excepted の説明）。持ち回す。
                    product["_footnotes"] = dict(notes_here)
                if not found:
                    continue
                layout = "row" if read_row_layout(rows) else "column"
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
