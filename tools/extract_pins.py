#!/usr/bin/env python3
"""Extract package pin / alternate-function candidates from a datasheet pin table.

The vendor pin table is the only source for package bond-out and pad routing; the
EVT tree does not carry it. PDF table recovery is layout-dependent, so this tool
emits *candidates* for human review and, when given a record, reports how far the
candidates agree with it. It never writes device records.

Usage:
    uv run tools/extract_pins.py <datasheet.pdf> --package TSSOP20 \
        [--compare devices/<id>.json] [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

# The pin table leads with one pin-number column per orderable variant, then pad,
# type, reset function, default alternate and remapping. Neither the number of
# variant columns nor the position of the rest is stable across families: CH32V003
# heads four columns with package names, CH32X035 seven, while CH32V006 and
# CH32V407 head theirs with part numbers and CH32V407 inserts an extra "I/O
# structure" column. Both are therefore read from the header labels.
PACKAGE_PREFIXES = ("SOP", "QFN", "LQFP", "TSSOP", "QSOP", "TQFP")
PART_NUMBER = re.compile(r"^(CH32)?[A-Z]{0,2}\d{3}[A-Z0-9]{2,}$")

# Header label -> the column it marks, matched against the merged header text with
# punctuation and case removed.
# The Chinese edition is the original and the English one a translation, so the
# tables are laid out identically and only the labels differ. Both spellings are
# matched so a document can be read in whichever language it is published in --
# CH32V407's reference manual exists only in Chinese.
# The function columns come in up to three: the reset-state main function
# ("Main function (after reset)" / "主功能（复位后）"), the default alternate
# function, and the remap list. CH32V003 prints all three; CH32X315 prints main
# plus one AF list that zh heads "引脚功能" and en "Default alternate function";
# CH32H417 heads its single AF column "Pin function(2)" / "引脚功能(2)". Keys are
# claimed in dict order with each column taken at most once, so the main column
# never swallows the default slot.
COLUMN_LABELS = {
    "pad": ("pinname", "引脚名称"),
    "type": ("pintype", "引脚类型"),
    "main": ("主功能", "mainfunction"),
    "default": ("defaultalternate", "defaultalter", "pinfunction",
                "默认复用功能", "引脚功能"),
    "remap": ("remapping", "重映射功能"),
}
REQUIRED_COLUMNS = ("pad", "type")  # plus at least one of default/remap

PAD = re.compile(r"^P[A-H]\d{1,2}$")
POWER_PADS = {"VSS", "VDD", "VDDA", "VSSA", "VBAT", "VREF+", "VREF-"}

# Supply and special pads are named per family (CH32M030 alone adds VS0-3, VB0-3,
# VHV, VDD8, VDD33, ISP1), so rows are recognised by their pin-type cell instead of
# by a list of pad names. Types read like P, A, O, I/O, I/O/A, I/O/FT.
PIN_TYPE = re.compile(r"^[A-Z]{1,3}(?:/[A-Z]{1,3}){0,3}$")
PAD_TOKEN = re.compile(r"^[A-Z][A-Z0-9_+-]{0,7}$")
# **GPIO の名前に役割を継ぎ足した pad 名**。datasheet は `PA0-WKUP` のように
# その pad の特別な役割を pad 名の一部として書く。8文字までの `PAD_TOKEN` では
# `PC13-TAMPER-RTC`・`PC14-OSC32_IN`・`PC15-OSC32_OUT` が長すぎて外れ、
# **9 冊の datasheet でこの 3 pad が丸ごと落ちていた**（103 型番のうち 99 が
# PC13 を持たない状態だった）。長さで測るのをやめて形で見る——GPIO の名前で
# 始まり `-` で役割が続く、という形は signal 名には無い。
PAD_COMPOUND = re.compile(r"^P[A-H]\d{1,2}-[A-Z0-9][A-Z0-9_+-]*$")
# **括弧は半角とは限らない。** 中文版は全角で（7）と打つ。半角だけを剥がすと
# SDIO_D0（7）や PD0（4）が signal 名としてそのまま表に出る（46種・364行あった）。
FOOTNOTE = re.compile(r"[（(]\d+[)）]")

# Two unrelated ways of naming the route the signal arrives on. Families with an
# AFIO remap register suffix the selector value (TIM1_CH1_2); CH32H41x instead
# multiplexes per pin and names the alternate-function number (TIM8_CH1(AF0)).
ROUTED = re.compile(r"^(?P<signal>.+?)_(?P<value>\d+)$")
ALTERNATE = re.compile(r"^(?P<signal>.+?)[（(](?:AF|af)(?P<value>\d+)[)）]$")

def kind_for(pin_type: str) -> str | None:
    """Map the datasheet's pin-type letters onto the schema's pin kinds.

    The table types every supply pin as P, so ground is not distinguishable here
    and stays a human refinement.
    """
    if "I/O" in pin_type:
        return "gpio"
    # CH32M030 types its output-only medium-voltage pins "O"; they are still GPIO.
    return {"P": "power", "A": "analog", "O": "gpio"}.get(pin_type)


def normalise_pad(cell: str) -> str:
    """Strip the line wrap the pad column picks up, then its footnote markers.

    CH32X035 prints PA7(7), PC16(4)(9) and wraps VDD as "V\\nDD". The wrap can also
    fall inside the marker, as CH32M030 does with "PA13(7\\n)", so whitespace has to
    go first for the marker to be recognisable at all.
    """
    return FOOTNOTE.sub("", cell.replace("\n", "").replace(" ", ""))


# 番号のセルの頭にある数。脚注を剥がした残り。
LEADING = re.compile(r"^(\d+)")


def normalise_number(cell: str) -> str:
    """lead 番号のセルを int にできる形にする。

    脚注は番号にも付き、改行がその中に落ちる——`31(\n6)`・`59(1\n2)`・`60\n(12)`。
    改行の向こう側がページをまたいで落ちると閉じ括弧すら残らない（`60(1`）ので、
    括弧を剥がすだけでは足りず、**頭の数だけを採る**。数で始まらないセルは
    そのまま返す——`EP`（露出パッド）は番号ではない本物の値で、45行ある。
    """
    flat = normalise_pad(cell)
    found = LEADING.match(flat)
    return found.group(1) if found else flat


def is_variant(name: str) -> bool:
    return name.startswith(PACKAGE_PREFIXES) or bool(PART_NUMBER.match(name))


def read_variant(cell: str) -> str | None:
    """Read one variant heading.

    Multi-column headings are printed rotated, so the text layer holds them
    reversed; a table with a single variant column has room to print it upright
    (CH32V203 Table 3-1-4). Both readings are therefore tried.
    """
    text = FOOTNOTE.sub("", cell.replace("\n", "")).strip()
    for candidate in (text[::-1].strip(), text):
        if candidate and is_variant(candidate):
            return candidate
    return None


def read_package_header(cells: list[str], count: int) -> list[str] | None:
    """Name the first `count` columns, leaving a placeholder where the text is lost.

    CH32V208 leaves one heading blank in the text layer and CH32V317 splits
    LQFP100 across two cells, so a heading row is accepted when some -- not
    necessarily all -- of its cells resolve.
    """
    names, resolved = [], 0
    for col in range(count):
        found = read_variant(cells[col]) if col < len(cells) else None
        names.append(found or f"col{col}")
        resolved += found is not None
    return names if resolved else None


def normalise_label(text: str) -> str:
    """Strip punctuation and case, keeping CJK so Chinese labels survive."""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", text.lower())


def read_layout(rows: list[list[str]]) -> tuple[dict[str, int], list[str]] | None:
    """Locate the pad/type/default/remap columns and the variant headings.

    Header labels wrap over several rows, so the rows above the first pad row are
    merged per column before matching. The variant row is the header row whose
    filled cells all sit left of the pad column.
    """
    first_data = next(
        (
            i
            for i, row in enumerate(rows)
            if any(PAD.match(normalise_pad(c)) or normalise_pad(c) in POWER_PADS for c in row)
        ),
        None,
    )
    if not first_data:
        return None
    width = max(len(r) for r in rows[:first_data])
    merged = [
        normalise_label("".join(row[col] for row in rows[:first_data] if col < len(row)))
        for col in range(width)
    ]
    layout: dict[str, int] = {}
    taken: set[int] = set()
    for key, keywords in COLUMN_LABELS.items():
        for keyword in keywords:
            col = next((c for c, text in enumerate(merged)
                        if c not in taken and keyword in text), None)
            if col is not None:
                layout[key] = col
                taken.add(col)
                break
    if any(key not in layout for key in REQUIRED_COLUMNS)             or not ({"default", "remap"} & layout.keys()):
        return None
    best: tuple[int, list[str]] | None = None
    for row in rows[:first_data]:
        found = read_package_header(row, layout["pad"])
        if not found:
            continue
        resolved = sum(1 for n in found if not n.startswith("col"))
        if best is None or resolved > best[0]:
            best = (resolved, found)
    return (layout, best[1]) if best else None


# "Table 2-1 Pin definitions" / "表2-1 引脚定义"
CAPTION = re.compile(r"^((?:Table\s+|表)[\d]+(?:-[\d]+)*)\s*(\S.*)$")
PIN_TABLE_TITLE = ("pin definition", "引脚定义")


def captions(pdf) -> list[tuple[str, str, int]]:
    """Every table caption, as (label, title, page index)."""
    out = []
    for pno, page in enumerate(pdf.pages):
        for line in page.extract_text_lines() or []:
            m = CAPTION.match(line["text"].strip())
            if m:
                out.append((m.group(1), m.group(2), pno))
        # This preliminary pass visits the whole document.  Keeping every page's
        # parsed layout alive until find_pin_tables() starts made a 148-page
        # datasheet consume about 800 MiB just to collect its captions.  The
        # captions above are plain strings now, so none of the page cache is
        # needed by the caller.
        # close() also clears get_textmap's per-page lru_cache; flush_cache()
        # alone leaves that large text map reachable.
        page.close()
    return out


def choose_table(pdf) -> tuple[str, str]:
    """Pick the first pin-definition table and the caption that ends it.

    Families number these differently -- Table 2-1, Table 2-1-1, Table 3-1-1 -- so
    the caption is found by its wording rather than by a fixed label.
    """
    found = captions(pdf)
    for i, (label, title, _) in enumerate(found):
        if any(k in title.lower() for k in PIN_TABLE_TITLE):
            return label, next_caption(found, i)
    raise SystemExit("pin definition の表見出しが見つかりませんでした")


def next_caption(found: list[tuple[str, str, int]], index: int) -> str:
    """The label that ends the table at `index`.

    A caption repeated on continuation pages is the same table, not the next one
    (CH32V103 Table 2-2), so identical labels are skipped.
    """
    label = found[index][0]
    for following, _, _ in found[index + 1:]:
        if following != label:
            return following
    return "\x00"


def caption_position(page, label: str) -> float | None:
    """Y coordinate of a table caption, if it is on this page.

    The label must end where it ends: "Table 3-1" is not an occurrence of
    "Table 3-1-1", which numbers a different table.
    """
    for line in page.extract_text_lines() or []:
        if re.match(re.escape(label) + r"(?![-\d])", line["text"].strip()):
            return line["top"]
    return None


# A repeated column heading also has no pad and no pin type. It is prose --
# "Main function (after reset)", "Default alternate function" -- and no signal
# name holds three lowercase letters in a row or any CJK, so that tells them
# apart. Without this, CH32H417 gained signals called "function" and "reset)".
PROSE = re.compile(r"[a-z]{3,}")


def continues(cells: list[str], pad_col: int, type_col: int,
              signal_cols: list[int]) -> bool:
    """Is this the tail of the row above, carried over a page break?

    Nothing identifies it but its shape: **no pad and no pin type, yet signal
    text and no prose**. A row with neither is a rule or a spacer and carries
    nothing; a row with prose is the heading printed again on the new page.

    lead 番号を全部の封装欄に持つ行は続きではない（`variant_row` を参照）。
    ここへ来るのは番号を持たないか、番号の**尻尾**しか持たない行——CH32V407 の
    PB7 は `60(12)` が切れて `2)` だけが次ページに残る。
    """
    if cells[pad_col] or cells[type_col]:
        return False
    carried = [cells[i] for i in signal_cols if i < len(cells) and cells[i]]
    return bool(carried) and not any(PROSE.search(c) or CJK.search(c) for c in carried)


# 封装欄が書ける値。番号（脚注が付くことがある）か、「この封装には無い」の `-`。
# **数で始まるだけでは足りない**——縦書きの見出しが繰り返されると
# `6TER764V23HC`（`CH32V407RET6` の逆順）のような文字列が同じ欄に入る。
LEAD_CELL = re.compile(r"-|\d+(?:\s*[（(][\d,、\s]*[)）]?)?")


def variant_row(cells: list[str], previous: list[str], pad_col: int) -> bool:
    """pad 欄が空でも lead 番号を持つ、**同じ pad の別の封装の行**か。

    CH32X035 の PC3 は封装によって既定の多重化機能が違うので、pad 欄を縦に
    結合して2行に組まれる:

        11 -  4 -  -  -  -  PC3  I/O/A  PC3  C1N0/C2N1/C3N1/A13
        -  -  -  8  -  4  -  （pad欄は空）    RST/C1N0/C2N1/C3N1/A13

    番号の欄は互いに補い合っていて、どちらの行も自分の封装を持っています。
    ページ境界で切れた尻尾（CH32V407 の PB7 は `60(12)` の `2)` だけが次ページに
    残る）と見分けが要る——**自分の行なら全部の封装の欄に何か書いてある**
    （番号か「この封装には無い」の `-`）。尻尾は書けなかった欄が空のまま残る。

    それだけでは足りません。**pad 欄が縦に結合されているなら、封装は2行に
    分かれている**はず——同じ封装の欄を両方の行が埋めているなら、pad 欄が空なのは
    結合ではなく**その行の pad 名を読み落とした**ということです。CH32L103 の
    PC13/PC14/PC15 がそれで、番号は 2/3/4 と続くのに pad 欄が取れておらず、
    継ぐと直前の VBAT が 3 つに増えていました。
    """
    lead = [cells[i].strip() for i in range(pad_col) if i < len(cells)]
    if not lead or not all(LEAD_CELL.fullmatch(c) for c in lead):
        return False
    above = [previous[i].strip() if i < len(previous) else "" for i in range(pad_col)]
    return not any(a not in ("", "-") and b not in ("", "-")
                   for a, b in zip(lead, above))


# 行の帯（y範囲）を比べるときの許容差（pt）。同じ表の罫線なので動かないが、
# PDF の丸めぶんだけ見る。
ROW_TOLERANCE = 1.0


def fill_merged(table, extracted: list[list[str]]) -> list[list[str]]:
    """縦に結合されたセルを、その矩形が覆っている行にも配る。

    **datasheet は「2つの pad が同じ足に出ている」ことを、lead 番号のセルを縦に
    結合して2行に掛けることで書きます。**

        17 17 27 21 32  PA11(8)        ← G8R6 は 27
        18 16 28 22 33  PA12(7)(8)     ┐ この 28 のセルが
        19 17    23 34  PA13(7)(8)(9)  ┘ 2行に掛かっている

    `table.extract()` は結合セルの値を**テキストが描かれた側の行にだけ**返し、
    もう片方を空にします。空欄を「この封装には無い」（資料は `-` と書く）と
    同じに扱っていたので、**CH32M103 の PA13/PA14 が丸ごと落ち、SWDIO/SWCLK を
    1つも持たない series になっていました**（worklist の F-24）。

    どちらの行にテキストが載るかは版面次第で、上とも下とも限りません
    ——CH32L103 の PA13 は上の PA12 に、CH32M103 の PA13 は下の PA12 に載ります。
    **「上から継ぐ」ではなく、矩形が覆っている行を持ち主**とします。

    埋めた結果は資料の注記と突き合わせて検算できます。CH32L103 の注記 7 は
    「PA12 and PA13 pins are short-connected」と書いていて、結合セルが結ぶ相手と
    一致します。CH32L103F8U6 に至っては表が `17` を2度書いていて、結合を使わずに
    同じことを言っています。
    """
    bands: list[tuple[float, float] | None] = []
    for row in table.rows:
        boxes = [c for c in row.cells if c]
        # 行そのものの帯は**いちばん低いセル**が決める。結合されたセルは
        # 2行ぶんの高さを持つので、それに合わせると帯が広がってしまう。
        bands.append((max(b[1] for b in boxes), min(b[3] for b in boxes))
                     if boxes else None)
    for i, row in enumerate(table.rows):
        band = bands[i]
        if band is None or i >= len(extracted):
            continue
        for j, cell in enumerate(row.cells):
            if cell is not None or j >= len(extracted[i]) or extracted[i][j]:
                continue
            # 結合は連続した行にしか起きないので、近いほうから外へ探す。
            for k in _outwards(i, len(table.rows)):
                box = table.rows[k].cells[j] if j < len(table.rows[k].cells) else None
                if box is None:
                    continue
                if box[1] <= band[0] + ROW_TOLERANCE and box[3] >= band[1] - ROW_TOLERANCE:
                    if k < len(extracted) and j < len(extracted[k]):
                        extracted[i][j] = extracted[k][j]
                break
    return extracted


def _outwards(start: int, total: int):
    """start に近い順に添字を返す（結合セルの持ち主は隣接する行にいる）。"""
    for step in range(1, total):
        for index in (start - step, start + step):
            if 0 <= index < total:
                yield index


def find_pin_tables(
    pdf, table_label: str, stop_label: str
) -> tuple[list[list], list[str], dict[str, int]]:
    """Collect data rows of the pin-definition table across the pages it spans.

    Consecutive pin tables share pages: a page can carry the tail of the previous
    table, this table's caption and the next table's caption. Both ends are therefore
    cut at caption y positions rather than at page boundaries. Continuation tables may
    drop the header entirely (CH32V003) or repeat it (CH32V006), so the layout found
    first is carried forward and a table whose column count differs is treated as
    belonging to another product.
    """
    rows: list[list] = []
    variants: list[str] = []
    layout: dict[str, int] = {}
    width = 0
    started = False
    for page in pdf.pages:
        begin = caption_position(page, table_label)
        if begin is not None:
            started = True
        elif not started:
            continue
        cut = caption_position(page, stop_label)
        for table in page.find_tables():
            if begin is not None and table.bbox[3] <= begin:
                continue
            if cut is not None and table.bbox[1] >= cut:
                continue
            extracted = fill_merged(
                table, [[(c or "").strip() for c in row] for row in table.extract()])
            if not extracted:
                continue
            if width and len(extracted[0]) != width:
                continue
            if not layout:
                found = read_layout(extracted)
                if not found:
                    continue
                layout, variants = found
                width = len(extracted[0])
            pad_col, type_col = layout["pad"], layout["type"]
            signal_cols = [c for c in (layout.get("main"), layout.get("default"),
                                       layout.get("remap")) if c is not None]
            for cells in extracted:
                if max(pad_col, type_col) >= len(cells):
                    continue
                pad = normalise_pad(cells[pad_col])
                pin_type = normalise_pad(cells[type_col])
                if PAD.match(pad) or PAD_COMPOUND.match(pad) or (
                        PAD_TOKEN.match(pad) and PIN_TYPE.match(pin_type)):
                    cells[pad_col] = pad
                    rows.append(cells)
                elif rows and variant_row(cells, rows[-1], pad_col):
                    # 同じ pad の別の封装の行。結合された pad/型の欄を上から継ぐ。
                    cells[pad_col] = rows[-1][pad_col]
                    if not cells[type_col]:
                        cells[type_col] = rows[-1][type_col]
                    rows.append(cells)
                elif continues(cells, pad_col, type_col, signal_cols) and rows:
                    # A row split by a page break: the pad and type cells are on
                    # the page above and only the wide signal columns carry over.
                    # CH32V407 breaks PB7 mid-name, leaving "TIM4_CH2/I2C_S" on
                    # one page and "DA/USBHS2_DP/FSMC_NADV" on the next -- dropped
                    # as pad-less, that lost I2C_SDA and three remap functions.
                    #
                    # **Only the signal columns are carried over.** A stray digit
                    # left in a pin-number column would otherwise be glued onto
                    # the number above and invent a pin.
                    for i in signal_cols:
                        if i < len(cells) and i < len(rows[-1]) and cells[i]:
                            rows[-1][i] = f"{rows[-1][i]}\n{cells[i]}".strip()
        # 読み終えたページの解析キャッシュは捨てる。同じ pdf を表ごとに
        # 何度も走査するので、貯め込むと datasheet 1本でも重くなる。
        page.close()
        if cut is not None:
            break
    return rows, variants, layout


# A subscript sits on its own line, so the letter it hangs off is left alone:
# CH32H417 writes VDD33 as "V" / "DD33" and "Main VDDK" as "Main V" / "DDK".
# No signal in any of the pin tables is a single letter, so a lone trailing
# capital is always the head of one of these.
#
# **語の切れ目は空白だけではない。** 中文版は同じ欄を `主V` と書き、漢字と
# ラテン文字の間に空白を置かない——`\s` だけを見ていたので中文版だけ
# `主V`／`DD33` に割れ、`DD33`・`DDIO`・`DDK`・`IO18` が signal として残っていた。
# 漢字からラテン文字への変わり目も語の始まりとして数える。
SUBSCRIPT = re.compile(r"(?:^|\s|[\u3040-\u30ff\u4e00-\u9fff])[A-Z]$")
# 改行が区切りの版で「上の行の続き」になれる形。1〜2文字か、それに経路の
# 添字が付いたもの（"V_1"）。この版の signal 名はどれも長いので取り違えない。
STUB = re.compile(r"^[A-Z0-9]{1,2}(?:_\d+)?$")

# The peripheral prefix a signal name opens with: the part before the first "_",
# with the instance number dropped. The instance has to go, because a table that
# spells out I2S2_CK between two "/" may only ever print I2S3_SD after a line
# break -- the peripheral is vouched for, the instance is not.
PREFIX = re.compile(r"^([A-Z][A-Z0-9]*?)(\d*)_")


def stem(part: str) -> str | None:
    found = PREFIX.match(part)
    # One letter is not a peripheral name. Without this, CH32V407's LTDC_R2,
    # wrapped as "LTD" / "C_R2", would look like a signal named C_R2.
    return found.group(1) if found and len(found.group(1)) > 1 else None


def opens_signal(part: str, known: frozenset[str]) -> bool:
    """Does this line start a new signal rather than continue the one above?

    Only a peripheral the table itself names counts. Taking any `X_` would split
    CH32H417's "SD" / "RAM_D20(AF12)", because "RAM_" looks like a prefix and is
    not one -- no cell in that table, or any other, opens a signal with it.
    """
    found = stem(part)
    return found is not None and found in known


def vocabulary(cells: list[str]) -> tuple[frozenset[str], frozenset[str]]:
    """Collect what the table spells out where the boundary is certain.

    A segment between two "/" that holds no line break is one signal, whole, so
    both the peripheral it opens with and the name itself are real ones. Segments
    that do hold a break are exactly the ones being disambiguated and cannot
    vouch for themselves.

    The peripherals settle line breaks (see unwrap()); the whole names settle
    runs that no line break separated at all (see resplit()).
    """
    stems: set[str] = set()
    names: set[str] = set()
    for cell in cells:
        for segment in (cell or "").split("/"):
            if "\n" in segment:
                continue
            raw = segment.strip()
            found = stem(raw)
            if found:
                stems.add(found)
            # A whole name is matched against, not merely read for its opening,
            # so it is filtered the way signals() filters what it emits.
            name = FOOTNOTE.sub("", raw)
            if name and " " not in name and not CJK.search(name):
                names.add(name)
    return frozenset(stems), frozenset(names)


def spells(part: str, names: frozenset[str]) -> bool:
    """Is this a whole signal the table spells out, route suffix and all?

    The suffix is still attached at this point -- routes are read off the name
    later -- so CH32V407's LED0 arrives as "LED0_1" and would not match the LED0
    the table prints elsewhere. Two letters or fewer is not enough to go on.
    """
    if len(part) >= 3 and part in names:
        return True
    routed = ROUTED.match(part)
    return bool(routed and len(routed.group("signal")) >= 3
                and routed.group("signal") in names)


def resplit(name: str, known: frozenset[str], names: frozenset[str]) -> list[str]:
    """Cut a name that two signals ran together inside, with no break to show it.

    CH32V407 prints PD14's remap column as

        TIM4_CH3_1/ | USART10_RTS_2US | ART10_RTS_3LED0 | _1/ | FSMC_D0_1

    where the break does fall inside a name -- "USART10_RTS_2US" / "ART10..." --
    so joining it is right, and the join is still three signals long, because the
    datasheet left the "/" out between them. No layout evidence survives that;
    what settles it is the vocabulary the rest of the datasheet spells out.

    A cut is taken only where the left side is already a whole name -- it has a
    "_" and the character before the cut belongs to it -- and the right side
    either opens with a peripheral the table names or is itself a name the table
    spells out. Requiring the left side to be whole is what keeps CH32H417's
    HSADC_IN0, CH32V205's QSPI_SCK and CH32L103's LPTIM_CH1 in one piece: "HS",
    "Q" and "LP" are not names, so ADC_IN0, SPI_SCK and TIM1_CH1 do not start
    signals there.
    """
    out: list[str] = []
    rest = name
    while True:
        cut = next((i for i in range(1, len(rest))
                    if rest[i - 1].isalnum() and "_" in rest[:i]
                    and (opens_signal(rest[i:], known) or spells(rest[i:], names))), 0)
        if not cut:
            break
        out.append(rest[:cut])
        rest = rest[cut:]
    return out + [rest]



def unwrap(cell: str, known: frozenset[str] = frozenset()) -> str:
    """Join a wrapped table cell, restoring the separator the line break swallowed.

    A line break falls either inside one signal or between two, and **which one
    is the datasheet's convention, not a property of the break**. Two conventions
    are in use, and a cell says which it follows:

    Most families separate signals with "/", so a break with no "/" beside it is
    inside a name. The renderer wraps wherever the column runs out, which is not
    where tokens end: CH32H417 splits SDRAM_D20(AF12) as "SD" / "RAM_D20(AF12)",
    CH32V407 splits LTDC_R2 as "LTD" / "C_R2" and USART6_TX as "USAR" / "T6_TX".
    Even here a break can fall between two signals -- "TIM11_CH3(AF13)" /
    "QSPI1_SIO0(AF10)" -- and a closed AF number is what says so.

    CH32V20x and CH32V30x use no "/" at all: the line break *is* the separator.
    There a break is inside a name only when the next line is a stub of one, as
    in "ETH_MII_PPS_OU" / "T" -- and a stub can carry the route suffix with it,
    as in "ETH_MII_RX_D" / "V_1" (see STUB).

    A slashed cell can still drop the "/" at a break, and then nothing on the
    line says which convention that break follows. CH32V407 writes PB5 as

        USART5_CK/ | I2C_SMBA/SPI3_ | MOSI | I2S3_SD/LTDC_V | SYNC

    where "SPI3_"/"MOSI" is inside a name and "MOSI"/"I2S3_SD" is between two,
    with nothing to tell them apart. What tells them apart is the rest of the
    table: `known` holds every peripheral prefix the table spells out where a
    "/" makes the boundary certain, so a line starting "I2S3_" is starting a
    signal, while "RAM_D20(AF12)" -- the tail of CH32H417's SDRAM_D20 -- is not,
    because no cell anywhere writes a signal beginning "RAM_".

    Reading the whole cell first is what makes the conventions separable.
    Deciding per break, as this did before, gets one convention right and the
    other wrong: the previous default inserted a separator everywhere and
    produced ~850 rows where a power pin's name arrived as "V" and "DD33".
    """
    parts = [p.strip() for p in cell.split("\n") if p.strip()]
    slashed = "/" in cell
    out = ""
    for part in parts:
        if out:
            previous = out.split("/")[-1]
            inside = (
                out.endswith(("/", "_", "(", "（"))
                or out.count("(") + out.count("（") > out.count(")") + out.count("）")
                or part.startswith(("/", ")", "）", "_"))
                or part[0].isdigit()
                or SUBSCRIPT.search(previous)
                # This cell separates with "/", so a bare break is not one --
                # unless the previous line finished a signal off with its AF
                # number, which nothing continues, or the next line opens with a
                # peripheral prefix the table uses elsewhere.
                or (slashed
                    and not (previous.endswith((")", "）")) and part[0].isupper())
                    and not opens_signal(part, known))
                # This cell separates with the break itself, so only a stub of a
                # name continues the line above. A stub can carry the route
                # suffix with it: CH32V30x wraps ETH_MII_RX_DV_1 as
                # "ETH_MII_RX_D" / "V_1", and reading that as two signals
                # invents both an ETH_MII_RX_D and a signal called V.
                or (not slashed and STUB.match(part) is not None)
            )
            if not inside:
                out += "/"
        out += part
    return out


CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def signals(cell: str, known: frozenset[str] = frozenset(),
            names: frozenset[str] = frozenset()) -> list[str]:
    """Split a cell into signal tokens. '-' is the table's empty marker, not a
    signal, and no signal name contains CJK -- such tokens are fragments of the
    Chinese edition's prose bleeding into the cell, so they are dropped.

    Nor does one contain a space. The power pins' description column reads "Main
    VDD33", which is prose about the pin rather than a name for it; the pin's own
    column says VDD33 next to it. A stray leading space is a different thing and
    is trimmed.
    """
    # Twice, because a footnote can be split across the break it marks: CH32X035
    # wraps the "(3)" of A3(3) as "A3(" / "3)", which no pass over the raw cell
    # can see.
    joined = FOOTNOTE.sub("", unwrap(FOOTNOTE.sub("", cell), known))
    return [part
            for s in (t.strip() for t in joined.split("/"))
            if s and s != "-" and " " not in s and not CJK.search(s)
            for part in resplit(s, known, names)]


def build(
    pdf_path: Path, package: str, table_label: str, stop_label: str
) -> tuple[list[dict], list[str], list[str]]:
    notes: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        if not table_label:
            table_label, stop_label = choose_table(pdf)
            notes.append(f"表を自動選択: {table_label}（{stop_label} まで）")
        rows, packages, layout = find_pin_tables(pdf, table_label, stop_label)
    if not packages:
        raise SystemExit(f"{table_label} の列見出しを認識できませんでした")
    if package not in packages:
        raise SystemExit(f"{package} は表にありません。候補: {', '.join(packages)}")
    pins, more = pins_for(rows, packages, layout, package)
    return pins, notes + more, packages


def table_cells(rows: list[list[str]], layout: dict[str, int]) -> list[str]:
    """The signal-bearing cells of a pin table, in reading order."""
    return [cells[col] for cells in rows
            for col in (layout.get("main"), layout.get("default"), layout.get("remap"))
            if col is not None and col < len(cells)]


def table_vocabulary(rows: list[list[str]],
                     layout: dict[str, int]) -> tuple[frozenset[str], frozenset[str]]:
    """(周辺機器名, whole name) の語彙。

    Two passes, because most names never appear between two "/" -- the columns
    are narrow and nearly every cell wraps. The first pass settles the line
    breaks from the peripherals alone and so already reads whole the names a run
    has to be cut into; the second pass cuts with them.
    """
    cells_read = table_cells(rows, layout)
    known, plain = vocabulary(cells_read)
    return known, plain.union(*(frozenset(signals(cell, known)) for cell in cells_read))


def datasheet_names(tables) -> frozenset[str]:
    """Every whole name the datasheet's pin tables spell out, in one set."""
    return frozenset().union(*(table_vocabulary(rows, layout)[1]
                               for rows, layout in tables)) if tables else frozenset()


def pins_for(
    rows: list[list[str]], packages: list[str], layout: dict[str, int], package: str,
    names: frozenset[str] | None = None
) -> tuple[list[dict], list[str]]:
    """Slice the shared table rows down to one variant's pins."""
    notes: list[str] = []
    index = packages.index(package)
    pad_col, type_col = layout["pad"], layout["type"]
    main_col = layout.get("main")
    default_col, remap_col = layout.get("default"), layout.get("remap")
    if default_col is None:
        notes.append("この表には default alternate function 列がなく、remap列のみ採取した")
    if remap_col is None:
        notes.append("この表には remap 列がなく、default/主功能列のみ採取した")
    last_col = max(c for c in (pad_col, type_col, main_col, default_col, remap_col)
                   if c is not None)
    # The whole table's vocabulary, gathered before any cell is read, so that a
    # cell whose line breaks lost their "/" can be settled by what the other
    # cells spell out. See unwrap() and resplit().
    known, mine = table_vocabulary(rows, layout)
    # A datasheet prints its pins twice -- once per package in the numbering
    # table, once per pad in the description table -- and the columns are not
    # equally narrow, so a name that only ever wraps in one of them is spelled
    # out whole in the other. CH32V407's LED0 and CH32V003's T2CH1ETR are only
    # readable that way. Callers that hold every table of one datasheet pass
    # them all in; alone, a table still has its own.
    names = mine | (names or frozenset())

    pins: list[dict] = []
    for cells in rows:
        if last_col >= len(cells):
            notes.append(f"列数不足の行を無視: {cells[:pad_col + 2]}")
            continue
        number = normalise_number(cells[index])
        if number == "-":
            # `-` は「この封装にこの pad は無い」と資料が書いたもの。
            continue
        if number == "":
            # **空欄は「無い」ではない**（資料は無いことを `-` と書く）。同じ足に
            # 出ている pad は番号のセルを縦に結合して書かれ、それは `fill_merged`
            # が埋める。ここまで空で残るのは結合でもない空欄で、資料が `-` を
            # 書き忘れたのか別の意味があるのかこの表からは決まらない
            # ——8行あり、CH32V20x の PA8（TSSOP20/QFN28）のように、同じ表の
            # 隣の行が `-` を書いているものもある。落とすが、黙って落とさない。
            notes.append(f"{cells[pad_col]}: lead番号が空欄。結合セルでもないので"
                         "この封装にあるのかどうか決まらず、落とした")
            continue
        pad = cells[pad_col]
        pin_type = normalise_pad(cells[type_col])
        kind = kind_for(pin_type)
        if kind is None:
            kind = "other"
            notes.append(f"{pad}: pin type {pin_type!r} を分類できず other とした")
        functions = []
        if main_col is not None:
            # The reset-state main function: usually the pad itself, but NRST
            # and the oscillator pads state their special role here.
            for token in signals(cells[main_col], known, names):
                functions.append({"signal": token, "route": "main"})
        if default_col is not None:
            for token in signals(cells[default_col], known, names):
                # CH32H41x puts its alternate-function numbers in this column too.
                af = ALTERNATE.match(token)
                functions.append(
                    {
                        "signal": af.group("signal"),
                        "route": f"af-{af.group('value')}",
                        "_alternate_function": int(af.group("value")),
                    }
                    if af
                    else {"signal": token, "route": "default"}
                )
        for token in signals(cells[remap_col], known, names) if remap_col is not None else ():
            af = ALTERNATE.match(token)
            if af:
                functions.append(
                    {
                        "signal": af.group("signal"),
                        "route": f"af-{af.group('value')}",
                        "_alternate_function": int(af.group("value")),
                    }
                )
                continue
            m = ROUTED.match(token)
            if m:
                functions.append(
                    {
                        "signal": m.group("signal"),
                        "route": f"remap-{m.group('value')}",
                        "_selector_value": int(m.group("value")),
                    }
                )
            else:
                functions.append({"signal": token, "route": None, "_needs_review": True})
                notes.append(
                    f"{pad}: remap列の {token!r} に経路番号がない。"
                    "どのselectorが選ぶかRMで要確認"
                )
        try:
            number_value: int | str = int(number)
        except ValueError:
            number_value = number
        if number_value == 0:
            # WCH numbers the exposed thermal pad 0; the schema spells it EP.
            number_value = "EP"
            notes.append(f"{pad}: pin番号0をexposed pad (EP) として扱った")
        pins.append(
            {
                "number": number_value,
                "pad": pad,
                "kind": kind,
                "_pin_type": pin_type,
                "functions": functions,
            }
        )

    pins.sort(key=lambda p: (isinstance(p["number"], str), p["number"]))
    return pins, notes


def print_err(*args):
    print(*args, file=sys.stderr)


def score(pins: list[dict], record: Path) -> None:
    rec = json.loads(record.read_text(encoding="utf-8"))
    truth = rec.get("pins", [])
    print_err(f"\n照合: {record.name}  record {len(truth)} pin / 抽出 {len(pins)} pin")
    print_err("-" * 74)

    got_pads = {(p["number"], p["pad"]) for p in pins}
    want_pads = {(p["number"], p["pad"]) for p in truth}
    print_err(f"  pin番号とpadの対応:  一致 {len(got_pads & want_pads)}/{len(want_pads)}")
    for miss in sorted(want_pads - got_pads, key=lambda x: str(x[0])):
        print_err(f"    record にあり抽出になし: {miss}")
    for extra in sorted(got_pads - want_pads, key=lambda x: str(x[0])):
        print_err(f"    抽出にあり record になし: {extra}")

    def pairs(source):
        return {(p["pad"], f["signal"]) for p in source for f in p["functions"]}

    got, want = pairs(pins), pairs(truth)
    n_got = sum(len(p["functions"]) for p in pins)
    n_want = sum(len(p["functions"]) for p in truth)
    print_err(f"\n  pin function 数: record {n_want} / 抽出 {n_got}")
    print_err(f"  (pad, signal) 一致: {len(got & want)}/{len(want)}")
    only_record = sorted(want - got)
    only_extract = sorted(got - want)
    if only_record:
        print_err(f"\n  record のみ ({len(only_record)}件):")
        for pad, sig in only_record:
            print_err(f"    {pad:5} {sig}")
    if only_extract:
        print_err(f"\n  抽出のみ ({len(only_extract)}件):")
        for pad, sig in only_extract:
            print_err(f"    {pad:5} {sig}")

    def routes(source):
        """(pad, signal) -> the selector values that reach it, 'default' included.

        A record collapses several selector values that pick the same route into one
        function (CH32X035 remap-5-to-7); the extractor emits one per value. Compare
        the value sets so the two representations are judged equivalent.
        """
        out: dict[tuple[str, str], set] = {}
        for pin in source:
            for f in pin["functions"]:
                key = (pin["pad"], f["signal"])
                if "_selector_value" in f:
                    out.setdefault(key, set()).add(f["_selector_value"])
                elif f.get("selection"):
                    out.setdefault(key, set()).update(f["selection"]["values"])
                else:
                    out.setdefault(key, set()).add("default")
        return out

    got_r, want_r = routes(pins), routes(truth)
    shared = got_r.keys() & want_r.keys()
    same = {k for k in shared if got_r[k] == want_r[k]}
    print_err(f"\n  (pad, signal) ごとの selector 値集合 一致: {len(same)}/{len(want_r)}")
    differing = sorted(shared - same)
    if differing:
        print_err(f"\n  signalは一致するが selector 値が異なる ({len(differing)}件):")
        for key in differing:
            print_err(f"    {key[0]:6} {key[1]:10} 抽出={sorted(got_r[key], key=str)} record={sorted(want_r[key], key=str)}")

    review = sum(1 for p in pins for f in p["functions"] if f.get("_needs_review"))
    print_err(f"\n  経路番号がなく人手確認が要る function: {review}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--package", help="列見出し。パッケージ名か型番（例: TSSOP20, V006K8U7）")
    ap.add_argument("--table", default="", help="pin定義表の見出し。既定は自動選択")
    ap.add_argument("--stop", default="", help="読み取りを止める次表の見出し")
    ap.add_argument("--list", action="store_true", help="表見出しと列の一覧だけ表示する")
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    if args.list:
        with pdfplumber.open(args.pdf) as pdf:
            for label, title, pno in captions(pdf):
                if any(k in title.lower() for k in PIN_TABLE_TITLE):
                    print_err(f"  {label:<14} p{pno + 1:<4} {title}")
        return 0
    if not args.package:
        ap.error("--package か --list が要ります")

    pins, notes, packages = build(args.pdf, args.package, args.table, args.stop)
    print_err(f"入力: {args.pdf}")
    print_err(f"表にある列: {', '.join(packages)}")
    print_err(f"{args.package} の抽出 pin: {len(pins)} / function: {sum(len(p['functions']) for p in pins)}")
    if notes:
        print_err(f"\n要確認 {len(notes)} 件:")
        for n in notes:
            print_err(f"  - {n}")
    if args.compare:
        score(pins, args.compare)
    if args.emit:
        json.dump(pins, sys.stdout, indent=2, ensure_ascii=False)
        print_err()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
