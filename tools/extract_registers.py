#!/usr/bin/env python3
"""Extract register field definitions from a reference manual.

The EVT header gives a selector's bit positions but never its reset value, and it
cannot say which encodings are legal. The manual states both in the per-register
field table that follows each register heading:

    6.3.2.1 Remap Register 1 (AFIO_PCFR1)
    Bit      | Name          | Access | Description | Reset value
    [26:24]  | SWCFG[2:0]    | RW     | ...         | 0
    15       | ADC_ETRGIN_RM | RW     | ...         | 0

This reads those tables into field definitions for review. It emits candidates only
and never writes device records.

Usage:
    uv run tools/extract_registers.py <manual.pdf> [--register AFIO_PCFR1]
        [--compare <record>.json] [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

# "6.3.2.1 Remap Register 1 (AFIO_PCFR1)" -- the register name is parenthesised.
# The Chinese edition writes the same heading with full-width brackets,
# "8.3.2.1 重映射寄存器1（AFIO_PCFR1）", and is generally the newer of the two.
SECTION = re.compile(r"^\d+(?:\.\d+)+\s+\S")
# The name is not always the end of the line, and not always upper case. A whole
# family of registers is written once with the index left as a lower-case
# placeholder, and the range it stands for is appended in a second bracket:
#
#     11.3.3 DMAy 通道 x 配置寄存器（DMAy_CFGRx）（x=1/2/3/4/5/6/7/8，y=1/2）
#     10.3.1.1 GPIO 配置寄存器低位（GPIOx_CFGLR）（x=A/B/C/D/E）
#
# Anchoring at the end and demanding upper case missed every one of these -- 161
# headings in CH32FV2x_V3xRM and 271 in CH32H417RM. The qualifier cannot be
# mistaken for a name because "x=1/2" does not match the name pattern at all.
REGISTER_IN_HEADING = re.compile(r"[(\uff08]([A-Z][A-Za-z0-9_]*)[)\uff09]")
BIT_RANGE = re.compile(r"^\[(\d+):(\d+)\]$")
BIT_SINGLE = re.compile(r"^(\d+)$")
FIELD_NAME = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)(?:\[\d+:\d+\])?$")
# 復位値の書き方は3通り。`0x0`（16進）・`0`（10進）・**`00b`/`000b`（2進、b付き）**。
# 2進を認めていなかったので、多bit field の復位値が 45 行で空欄になっていた
# （CH32V30x の PCFR2 の USART6〜8、CH32H417 の PCFR1 全部——worklist の F-34）。
RESET = re.compile(r"^(?:(?P<hex>0x[0-9A-Fa-f]+)|(?P<bin>[01]+)b|(?P<dec>\d+))$")


def parse_reset(found: "re.Match[str]") -> int:
    if found.group("hex"):
        return int(found.group("hex"), 16)
    if found.group("bin"):
        return int(found.group("bin"), 2)
    return int(found.group("dec"))

# Routing written into the description instead of a grid: CH32X035 states
# "001: Mapping (SCL/PA13, SDA/PA14)" and CH32M030 "000: Default mapping
# (CH1/PC0, CH2/PC1)". A group may list several signals on one pad, as in
# "CH1/ETR/PA5", where the last token is the pad.
DESCRIBED_ROUTE = re.compile(r"(?P<value>[01xX]{1,4})\s*:\s*[^()]{0,40}?\(([^()]*)\)")
# The manuals are not consistent about case inside a field description:
# CH32X035 writes "010: mapping (rx/pc17, cts/pb15, tx/pc16, ...)" in lower
# case for one row of USART4_RM and upper case for the rest. Dropping the
# lower-case rows loses whole routes, and USART4 value 2 is the one whose
# TX and RX sit on the same pads as value 5 but the other way round.
PAD_TOKEN = re.compile(r"^P[A-Ha-h]\d{1,2}$")

# A field table's header row, in either edition. The Chinese one is
# "位 名称 访问 描述 复位值"; squash() strips it to nothing, so the two
# vocabularies are matched separately.
HEADER_CELLS = ("bit", "name", "access")
RESET_CELL = "resetvalue"
HEADER_CELLS_ZH = {"bit": "位", "name": "名称", "access": "访问"}
RESET_CELL_ZH = "复位值"
DESCRIPTION_ZH = "描述"


def flatten(cell: str | None) -> str:
    return (cell or "").replace("\n", " ").strip()


def squash(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def field_header(row: list[str]) -> dict[str, int] | None:
    """Column indexes of a "Bit / Name / Access / ... / Reset value" header row."""
    squashed = [squash(c) for c in row]
    layout = {}
    for key in HEADER_CELLS:
        if key in squashed:
            layout[key] = squashed.index(key)
    if len(layout) == len(HEADER_CELLS) and RESET_CELL in squashed:
        layout["reset"] = squashed.index(RESET_CELL)
        if "description" in squashed:
            layout["description"] = squashed.index("description")
        return layout

    # The Chinese edition, whose cells squash() cannot see.
    stripped = [(c or "").strip() for c in row]
    layout = {}
    for key, cell in HEADER_CELLS_ZH.items():
        if cell not in stripped:
            return None
        layout[key] = stripped.index(cell)
    if RESET_CELL_ZH not in stripped:
        return None
    layout["reset"] = stripped.index(RESET_CELL_ZH)
    if DESCRIPTION_ZH in stripped:
        layout["description"] = stripped.index(DESCRIPTION_ZH)
    return layout


def parse_bits(cell: str) -> tuple[int, int] | None:
    m = BIT_RANGE.match(cell)
    if m:
        high, low = int(m.group(1)), int(m.group(2))
        return (low, high - low + 1) if high >= low else None
    m = BIT_SINGLE.match(cell)
    return (int(m.group(1)), 1) if m else None


def extract(pdf_path: Path, want: str | None) -> tuple[list[dict], list[str]]:
    fields: list[dict] = []
    notes: list[str] = []
    register: str | None = None
    layout: dict[str, int] | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Headings and tables are interleaved, so read them in vertical order.
            items = [("h", line["top"], line["text"].strip()) for line in page.extract_text_lines() or []]
            items += [("t", table.bbox[1], table) for table in page.find_tables()]
            for kind, _, payload in sorted(items, key=lambda x: x[1]):
                if kind == "h":
                    # **A heading always replaces the register, even when no name
                    # can be read from it.** Keeping the previous one is what
                    # made CH32H417's whole DMA chapter -- 41 trigger-multiplexer
                    # rows and the DMAy_CFGRx fields -- come out as AFIO_EXTICR2
                    # fields named TIM1_CH1..TIM9_CH3, which then looked exactly
                    # like real remap selectors. Dropping the tables is the
                    # honest outcome: absence beats a plausible wrong owner.
                    if SECTION.match(payload):
                        found = REGISTER_IN_HEADING.search(payload)
                        register = found.group(1) if found else None
                        layout = None
                    continue
                if register is None or (want and register != want):
                    continue
                rows = [[flatten(c) for c in row] for row in payload.extract()]
                if not rows:
                    continue
                found = field_header(rows[0])
                if found:
                    layout, rows = found, rows[1:]
                elif layout is None:
                    continue
                for row in rows:
                    if max(layout[k] for k in ("bit", "name", "access", "reset")) >= len(row):
                        continue
                    bits = parse_bits(row[layout["bit"]])
                    # A field name never contains a space; CH32V003 wraps
                    # ADC_ETRGREG_RM as "ADC_ETRGREG_R" + "M".
                    name = FIELD_NAME.match(row[layout["name"]].replace(" ", ""))
                    if not bits or not name or name.group(1).lower() == "reserved":
                        continue
                    reset = RESET.match(row[layout["reset"]].replace(" ", "").strip())
                    if not reset:
                        notes.append(
                            f"{register}.{name.group(1)}: reset値を読めず ({row[layout['reset']]!r})"
                        )
                    fields.append(
                        {
                            "register": register,
                            "field": name.group(1),
                            "bit_offset": bits[0],
                            "bit_width": bits[1],
                            "reset_value": parse_reset(reset) if reset else None,
                            "access": row[layout["access"]],
                            "description": (
                                row[layout["description"]]
                                if layout.get("description", len(row)) < len(row)
                                else ""
                            ),
                            "page": page.page_number,
                        }
                    )
            # flush_cache() だけでは extract_text_lines() が作った
            # get_textmap のlru_cacheが残る。close() はページを再利用不能に
            # する処理ではなく、両方のキャッシュを捨てる。
            page.close()
    return fields, notes


# The Chinese edition writes the same route lists with full-width punctuation:
# "010：映射（RX/PC17，CTS/PB15，TX/PC16）". Folding these onto ASCII lets one
# regex read both editions -- and the Chinese one is worth reading, because it
# is uniform where the English one is not: CH32X035's USART4_RM has one row in
# lower case in English and none in Chinese.
FULLWIDTH = str.maketrans({"：": ":", "（": "(", "）": ")", "，": ",",
                           "／": "/", "、": ",", "　": " "})


def routes_in(field: dict) -> list[dict]:
    """Routes stated inside a field's description, as (value, signal, pad).

    Signal names there are written relative to the peripheral -- "CH1" under
    TIM3_RM, "SCL" under I2C1_RM -- so the field's own name supplies the prefix.
    """
    peripheral = re.sub(r"_(?:RM|REMAP)$", "", field["field"])
    out: list[dict] = []
    upper = (field["description"].translate(FULLWIDTH).upper()
             if field.get("description") else "")
    for m in DESCRIBED_ROUTE.finditer(upper):
        pattern = m.group("value")
        values = [pattern] if "x" not in pattern.lower() else None
        bits = [
            int("".join(b), 2)
            for b in _expand_bits(pattern)
        ]
        for group in m.group(2).split(","):
            parts = [p.strip() for p in group.split("/") if p.strip()]
            if len(parts) < 2 or not PAD_TOKEN.match(parts[-1]):
                continue
            pad = parts[-1].upper()
            for name in parts[:-1]:
                signal = name if name.startswith(peripheral) else f"{peripheral}_{name}"
                for value in bits:
                    out.append(
                        {
                            "field": field["field"],
                            "value": value,
                            "signal": signal,
                            "pad": pad,
                            "page": field["page"],
                            "_from_description": True,
                        }
                    )
    return out


# 説明文が列挙する値。`00：默认映射…；01：重映射…；1x：重映射…` / `0：…；1：…`。
ENUMERATED = re.compile(r"(?:^|[\s;.])(?P<value>[01xX]{1,4})[:：]")


def values_in(field: dict) -> set[int]:
    """説明文が列挙している field の値（`x` は両方に展開）。

    remap 格子に無い値でも説明文が定義していることがある——CH32V30x の
    `TIM5CH4_RM` は格子を持たず、説明文が `1：重映射，…映射至LSI内部时钟` と
    書く。pad に出ない経路なので `routes_in` は拾えず、valid_values が 0 だけに
    なっていた（worklist の F-35）。
    """
    text = (field.get("description") or "").translate(FULLWIDTH)
    out: set[int] = set()
    for m in ENUMERATED.finditer(text):
        for bits in _expand_bits(m.group("value").lower()):
            out.add(int("".join(bits), 2))
    return out


def _expand_bits(pattern: str) -> list[list[str]]:
    rows = [[]]
    for bit in pattern:
        rows = (
            [r + [b] for r in rows for b in ("0", "1")]
            if bit in "xX"
            else [r + [bit] for r in rows]
        )
    return rows


def score(fields: list[dict], record: Path) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from extract_remap import canonical_field

    rec = json.loads(record.read_text(encoding="utf-8"))
    by_field = {}
    for f in fields:
        by_field.setdefault(canonical_field(f["field"]), f)

    selectors = rec.get("route_selectors", [])
    print(f"\n照合: {record.name}  record selector {len(selectors)}", file=sys.stderr)
    print("-" * 74, file=sys.stderr)
    hit = bits_ok = reset_ok = 0
    for sel in selectors:
        found = by_field.get(canonical_field(sel["field"]))
        if not found:
            print(f"  RMに無し    {sel['id']}", file=sys.stderr)
            continue
        hit += 1
        # The manual states one register at a time, so compare only the half of a
        # split field that lives in the register this entry describes.
        register = found["register"].rpartition("_")[2]
        want_bits = [b["bit"] for b in sel.get("bits", []) if b["register"] == register]
        got_bits = list(range(found["bit_offset"], found["bit_offset"] + found["bit_width"]))
        same_bits = want_bits == got_bits
        same_reset = found["reset_value"] == sel["reset_value"]
        bits_ok += same_bits
        reset_ok += same_reset
        marks = f"bit{'○' if same_bits else '×'} reset{'○' if same_reset else '×'}"
        detail = "" if same_bits else f"  RM={got_bits} record={want_bits}"
        print(f"  {marks}  {sel['id']:24} {found['register']}.{found['field']}{detail}", file=sys.stderr)
    print(
        f"\n  RMに存在 {hit}/{len(selectors)}   bit一致 {bits_ok}/{hit}   reset一致 {reset_ok}/{hit}",
        file=sys.stderr,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--register", help="この register のみ読む（例: AFIO_PCFR1）")
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--routes", action="store_true", help="説明文に書かれた経路を出す")
    args = ap.parse_args()

    fields, notes = extract(args.pdf, args.register)
    registers = sorted({f["register"] for f in fields})
    print(f"入力: {args.pdf}", file=sys.stderr)
    print(f"field定義: {len(fields)} 件 / register {len(registers)} 種", file=sys.stderr)
    if args.register or len(registers) <= 12:
        for reg in registers:
            count = sum(1 for f in fields if f["register"] == reg)
            print(f"    {reg:<22} {count} field", file=sys.stderr)
    if notes:
        print(f"\n要確認 {len(notes)} 件:", file=sys.stderr)
        for note in list(dict.fromkeys(notes))[:10]:
            print(f"  - {note}", file=sys.stderr)

    described = [r for f in fields for r in routes_in(f)]
    if described:
        print(f"説明文から読めた経路: {len(described)} 件", file=sys.stderr)
    if args.routes:
        json.dump(described, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    if args.compare:
        score(fields, args.compare)
    if args.emit:
        json.dump(fields, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
