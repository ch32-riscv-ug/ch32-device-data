#!/usr/bin/env python3
"""レジスタマップを EVT device header から機械的に集める → tables/register_*.csv

consumer の R-20（レジスタマップ）の **機械的に集められる部分だけ**（2026-08-25）。
出所は 12 family すべてを覆う唯一の機械可読ソース、EVT の device header
（`ch32*.h`）。reference manual（zh）のレジスタ表で bit 位置を突き合わせる。

    register_blocks.csv    D-1  block（USART1）→ 型（USART）と base address
    registers.csv          D-3  型 × register → 構造体内の offset・幅・配列数
    register_fields.csv    D-4  register × bit define → bit 位置・mask・種類（field / 値）
    index/register_layouts.csv   D-5  型 × layout key（構造体と define 名の集合のハッシュ）

**header の作りで読み方が決まる。**

1. register は構造体のメンバー。`__IO uint32_t STATR;`。reserved は配列
   （`uint32_t RESERVED0[2];`）、幅は 8/16/32/64、**入れ子の union**（CH32H417 の
   TIM は 16bit 版と 32bit 版を union で重ねる）、**構造体型のメンバー**
   （`__IO USBSS_EP_TX_TypeDef EP_TX[7];`）がある。offset は位置で決まる
2. bit define は **banner コメント**が register を言う。define 名は言わない
   （`RCC_USART1EN` は APB2PCENR を含まない）:

       /*****  Bit definition for RCC_APB2PCENR register  *****/
       #define RCC_USART1EN   ((uint32_t)0x00004000) /* USART1 clock enable */

   banner の名前を register の識別子に使う（RM のレジスタ表と同じ綴り）。構造体の
   メンバーへの対応は付くものだけ付ける——`DMA_CNTR7` は `DMA_Channel_TypeDef.CNTR`
   のように **instance 番号が banner にだけ付く**ものがあり、名前から決まらない
   ものは offset を空で出す（消さない）
3. **値の列挙**は field の部分集合。`RCC_PLLMULL_3` は `RCC_PLLMULL` の中の値。
   同じ banner の中で、名前が親＋`_…` で mask が親に含まれるものを `kind=value` にする

**RM との突き合わせ**は2段。(1) レジスタ表: (register, field) の綴りが一致するもの
（`GPIOx_CFGLR` の `x`・`IDRy` の `y` は数字を落として比べる）で bit 位置が同じなら
confirmed、違えば conflict（両論を basis に）、RM に無ければ reference。RM の access と
reset を列で持つ。(2) **各章冒頭の絶対アドレス表**（`R32_PWR_CTLR | 0x40007000 | … |
復位値`）: EVT の base+offset と比べ、一致した block/register を confirmed に、違えば
conflict。RM の register 復位値もここから採る（`rm_reset`）。
**RM の読みは遅い**（family 1本 15秒〜数分）ので `--rm-cache` に JSON で置く。

実行:
    uv run tools/build_registers.py [--mirrors <dir>] [--out tables] [--rm-cache <dir>] [--family F]
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_addresses  # noqa: E402
import extract_registers  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
MIRRORS = Path("/home/mt/dev_wch")

BLOCK_COLUMNS = ["family", "block", "type", "layout", "base_address", "#", "confidence", "basis"]
REGISTER_COLUMNS = ["family", "type", "register", "offset", "width_bits", "count",
                    "rm_register", "rm_reset", "rm_address_check", "#", "confidence", "basis"]
FIELD_COLUMNS = ["family", "register", "type", "member", "field", "define", "kind", "of_field",
                 "bits", "mask", "value", "description", "rm_access", "rm_reset",
                 "#", "confidence", "basis"]
LAYOUT_COLUMNS = ["family", "type", "layout", "registers", "fields", "size_bytes",
                  "#", "confidence", "basis"]

BANNER = re.compile(r"Bit definition for\s+(?P<register>\w+)\s+register", re.IGNORECASE)
# `((uint32_t)0x0001)` / `(0x0001)` / `0x0001` / `(0x1U)`。ほかの形（`(1 << 3)`・別名）は採らない。
DEFINE = re.compile(r"^\s*#define\s+(?P<name>\w+)\s+"
                    r"(?:\(\s*\(\s*u?int(?:8|16|32|64)_t\s*\)\s*)?\(?\s*"
                    r"(?P<mask>0[xX][0-9A-Fa-f]+)[uUlL]*\s*\)?\s*\)?"
                    r"\s*(?:/\*+\s*(?P<comment>.*?)\s*\*+/)?\s*$")
POINTER = re.compile(r"^\s*#define\s+(?P<block>\w+)\s+\(\(\s*(?P<type>\w+)_TypeDef\s*\*\s*\)\s*(?P<base>\w+)\s*\)")
MEMBER = re.compile(r"^(?:__I?O?\s+|volatile\s+|const\s+)*"
                    r"(?P<type>u?int(?P<width>8|16|32|64)_t|(?P<struct>\w+)_TypeDef)\s+"
                    r"(?P<name>\w+)(?:\s*\[\s*(?P<count>\d+)\s*\])?\s*;")
# `typedef struct` / `typedef struct {` / `typedef struct __attribute__((packed))`（USBHSH 等）
TYPEDEF_START = re.compile(r"^\s*typedef\s+struct\b(?:\s+__attribute__\s*\(\(\w+\)\))?\s*\{?\s*$")
TYPEDEF_END = re.compile(r"^\s*\}\s*(?P<name>\w+)_TypeDef\s*;")
TRAILING_DIGITS = re.compile(r"(\D+?)(\d+)$")


def find_header(family_dir: Path) -> Path | None:
    found = sorted(family_dir.glob("EVT/**/Peripheral/inc/ch32*.h"))
    plain = [p for p in found if re.fullmatch(r"ch32[a-z0-9]+\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else (found[0] if found else None)


# ---------------------------------------------------------------- 構造体

class Struct:
    def __init__(self, name: str):
        self.name = name
        self.members: list[dict] = []   # {name, offset, width_bits, count, type}
        self.size = 0


def read_structs(text: str) -> dict[str, Struct]:
    """`typedef struct {…} X_TypeDef;` を全部。入れ子の union / struct と構造体型メンバーを解く。

    union の中では全メンバーが union の先頭 offset から始まり、union の大きさは最大の
    メンバー。union 内の匿名 struct は順に並ぶ。構造体型メンバーの大きさは先に読んだ
    構造体から取る（header は使う前に定義している）。
    """
    structs: dict[str, Struct] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not TYPEDEF_START.match(lines[i]):
            i += 1
            continue
        # 本体を `} NAME_TypeDef;` まで集める
        body: list[str] = []
        j = i + 1
        end = None
        while j < len(lines):
            m = TYPEDEF_END.match(lines[j])
            if m:
                end = m.group("name")
                break
            body.append(lines[j])
            j += 1
        if end is None:
            i = j
            continue
        st = Struct(end)
        st.size = _parse_body(body, 0, st, structs)
        structs[end] = st
        i = j + 1
    return structs


def _parse_body(body: list[str], offset: int, st: Struct, structs: dict[str, Struct]) -> int:
    """body の行を offset から並べ、終端 offset を返す。union/struct の入れ子は再帰。"""
    k = 0
    while k < len(body):
        line = body[k].strip()
        if not line or line.startswith("//") or line.startswith("/*"):
            k += 1
            continue
        if re.match(r"^(union|struct)\s*\{?\s*$", line) or re.match(r"^(union|struct)\s*\{", line):
            kind = line.split()[0]
            # 対応する閉じ括弧を探す
            depth = 0
            inner: list[str] = []
            k2 = k
            opened = "{" in line
            while k2 < len(body):
                seg = body[k2]
                if k2 != k:
                    inner.append(seg)
                depth += seg.count("{") - seg.count("}")
                if k2 == k and not opened:
                    pass
                if (opened or k2 > k) and depth <= 0 and "}" in seg:
                    break
                k2 += 1
            # inner の最後の行は `};`（または `} name;`）——除く
            if inner and re.match(r"^\s*\}\s*\w*\s*;?\s*$", inner[-1]):
                inner = inner[:-1]
            # 先頭の `{` だけの行を除く
            if inner and inner[0].strip() == "{":
                inner = inner[1:]
            if kind == "union":
                ends = []
                for alt in _split_union(inner):
                    sub = Struct(st.name)
                    ends.append(_parse_body(alt, offset, sub, structs))
                    st.members.extend(sub.members)
                offset = max(ends) if ends else offset
            else:
                offset = _parse_body(inner, offset, st, structs)
            k = k2 + 1
            continue
        m = MEMBER.match(line)
        if m:
            count = int(m.group("count") or 1)
            if m.group("struct"):
                inner_struct = structs.get(m.group("struct"))
                width = (inner_struct.size if inner_struct else 4) * 8
            else:
                width = int(m.group("width"))
            st.members.append({"name": m.group("name"), "offset": offset,
                               "width_bits": width, "count": count,
                               "type": m.group("type")})
            offset += width // 8 * count
        k += 1
    return offset


def _split_union(inner: list[str]) -> list[list[str]]:
    """union の本体を選択肢（メンバー1つ、または匿名 struct 1つ）ごとに分ける。"""
    alts: list[list[str]] = []
    k = 0
    while k < len(inner):
        line = inner[k].strip()
        if not line or line.startswith("//"):
            k += 1
            continue
        if line.startswith("struct"):
            depth = 0
            block: list[str] = [inner[k]]
            k2 = k
            while k2 < len(inner):
                depth += inner[k2].count("{") - inner[k2].count("}")
                if k2 > k:
                    block.append(inner[k2])
                if depth <= 0 and "}" in inner[k2] and k2 > k:
                    break
                k2 += 1
            alts.append(block)
            k = k2 + 1
            continue
        alts.append([inner[k]])
        k += 1
    return alts


def flat_members(st: Struct, structs: dict[str, Struct]) -> list[dict]:
    """構造体型のメンバー（CAN の `sTxMailBox[3]`、USBSS の `EP_TX[7]`）を展開して
    `sTxMailBox[0].TXMIR` のように親からの offset で並べる。"""
    out: list[dict] = []
    for m in st.members:
        inner = structs.get(m["type"][:-len("_TypeDef")]) if m["type"].endswith("_TypeDef") else None
        if inner is None:
            out.append(m)
            continue
        for idx in range(m["count"]):
            prefix = f"{m['name']}[{idx}]." if m["count"] > 1 else f"{m['name']}."
            for sub in flat_members(inner, structs):
                out.append({**sub, "name": prefix + sub["name"],
                            "offset": m["offset"] + idx * inner.size + sub["offset"]})
    return out


# ---------------------------------------------------------------- bit define

def read_banners(text: str) -> list[tuple[str, list[dict]]]:
    """[(banner register, [define])]。banner に属さない define は採らない。"""
    out: list[tuple[str, list[dict]]] = []
    current: list[dict] | None = None
    for line in text.splitlines():
        b = BANNER.search(line)
        if b:
            current = []
            out.append((b.group("register"), current))
            continue
        if current is None:
            continue
        # banner の節は次の banner か、構造体/他の節見出しまで。`typedef` が出たら閉じる。
        if line.lstrip().startswith("typedef"):
            current = None
            continue
        d = DEFINE.match(line)
        if d:
            current.append({"name": d.group("name"), "mask": int(d.group("mask"), 16),
                            "comment": (d.group("comment") or "").strip()})
    return out


def bit_span(mask: int) -> tuple[int, int] | None:
    if mask == 0:
        return None
    lo = (mask & -mask).bit_length() - 1
    hi = mask.bit_length() - 1
    return (lo, hi) if mask == ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1) else None


def field_name(define: str, register: str, type_name: str) -> str:
    for prefix in (register + "_", type_name + "_"):
        if define.startswith(prefix) and len(define) > len(prefix):
            return define[len(prefix):]
    return define


FIRST_DIGITS = re.compile(r"\d+")


def resolve_member(register: str, structs: dict[str, Struct]) -> tuple[str, dict | None, str]:
    """banner の register 名 → (型, メンバー, 註)。

    型は banner の先頭語（`RCC_APB2PCENR` → `RCC`）。メンバーは、その型で始まる
    構造体（`DMA` → `DMA_TypeDef` と `DMA_Channel_TypeDef`）の中から、
    (a) 名前そのまま、(b) 末尾の数字を落とした名前、(c) 配列名＋番号、
    (d) 入れ子構造体の配列（CAN の `CAN_TXMI0R` → `sTxMailBox[0].TXMIR`、
    `CAN_F3R2` → `sFilterRegister[3].FR2`。最初の数字列が添字）、
    (e) 名前の前方一致が1つだけ（`DMA_CFG4` → `CFGR`）、の順に探す。
    """
    type_name, _, rest = register.partition("_")
    if not rest:
        return type_name, None, "banner に register 名が無い"
    candidates = [s for s in structs.values()
                  if s.name == type_name or s.name.startswith(type_name + "_")]
    if not candidates:
        return type_name, None, f"{type_name}_TypeDef が無い"
    ordered = sorted(candidates, key=lambda s: (s.name != type_name, len(s.name)))
    for st in ordered:
        names = {m["name"]: m for m in st.members}
        if rest in names:
            return type_name, {**names[rest], "struct": st.name, "index": ""}, ""
    # (d) 入れ子構造体の配列。平坦化した名前 `sTxMailBox[0].TXMIR` と、banner の
    # 最初の数字列を添字として抜いた残り `TXMIR` を突き合わせる。
    first = FIRST_DIGITS.search(rest)
    if first:
        leaf = rest[:first.start()] + rest[first.end():]
        idx = int(first.group())
        for st in ordered:
            for m in flat_members(st, structs):
                if "." not in m["name"]:
                    continue
                head, _, tail = m["name"].rpartition(".")
                if tail == leaf and head.endswith(f"[{idx}]"):
                    return type_name, {**m, "struct": st.name, "index": ""}, ""
    m = TRAILING_DIGITS.match(rest)
    if m:
        stem, digits = m.groups()
        for st in sorted(candidates, key=lambda s: (s.name != type_name, len(s.name))):
            names = {mm["name"]: mm for mm in st.members}
            if stem in names and names[stem]["count"] > 1:
                return type_name, {**names[stem], "struct": st.name, "index": digits}, ""
            if stem in names:
                return type_name, {**names[stem], "struct": st.name, "index": digits}, \
                    "banner は instance 番号付き（構造体は instance ごと）"
    # (e) 前方一致が1つだけ（`DMA_CFG4` → `DMA_Channel.CFGR`、`RTC_PSCH` → `PSCRH` は不可）
    if m:
        stem, digits = m.groups()
        hits = [(st, mm) for st in ordered for mm in st.members
                if mm["name"].startswith(stem) and "." not in mm["name"]
                and not mm["name"].upper().startswith("RESERVED")]
        if len(hits) == 1:
            st, mm = hits[0]
            return type_name, {**mm, "struct": st.name, "index": digits}, \
                "banner は instance 番号付き（構造体は instance ごと）"
    # 最後の手: 型を問わず、その名前のメンバーを持つ構造体が1つだけならそれ
    # （FLASH の option byte は `OB_TypeDef` に居る——banner は `FLASH_RDPR`）。
    owners = [st for st in structs.values() if rest in {m["name"] for m in st.members}]
    if len(owners) == 1:
        st = owners[0]
        member = next(m for m in st.members if m["name"] == rest)
        return type_name, {**member, "struct": st.name, "index": ""}, ""
    return type_name, None, "構造体に同名のメンバーが無い"


# ---------------------------------------------------------------- RM

def rm_key(name: str) -> str:
    """`GPIOx_CFGLR` と `GPIO_CFGLR`、`TIM1_CTLR1` と `TIM_CTLR1` を同じ鍵に。"""
    head, _, rest = name.upper().partition("_")
    head = re.sub(r"\d+$|X$", "", head)
    return f"{head}_{rest}"


def field_key(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def rm_fields(family_dir: Path, cache: Path | None) -> tuple[dict, str]:
    manuals = sorted(family_dir.glob("datasheet_zh/*RM.PDF")) or \
        sorted(family_dir.glob("datasheet_en/*RM.PDF"))
    if not manuals:
        return {}, ""
    cached = cache / f"{family_dir.name}.json" if cache else None
    if cached and cached.exists():
        fields = json.loads(cached.read_text(encoding="utf-8"))
    else:
        fields, _ = extract_registers.extract(manuals[0], None)
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    out: dict = {}
    for f in fields:
        # 幅の広い「field」は見出しの走り過ぎ（DMA の NDT 等が別 register に付く）の
        # 疑いがあるが、ここでは名前一致だけで採るので害は小さい。
        out.setdefault((rm_key(f["register"]), field_key(f["field"])), f)
    registers = {rm_key(f["register"]): f["register"] for f in fields}
    out["__registers__"] = registers
    return out, manuals[0].name


# ---------------------------------------------------------------- RM の絶対アドレス表

# RM zh 版の各章冒頭にある表: `R32_PWR_CTLR | 0x40007000 | 电源控制寄存器 | 0x00000000`。
# register の絶対アドレスと復位値を言う。D-1（base）と D-3（offset）の**独立した裏取り**。
ADDR_NAME = re.compile(r"^R(?:8|16|32)_(?P<name>\w+)$")
HEX32 = re.compile(r"^0x[0-9A-Fa-f]{8}$")


def rm_addresses(family_dir: Path, cache: Path | None) -> tuple[list[dict], str]:
    """[{name, address, reset}] を RM の表から。ページ単位に読んで閉じる（メモリ）。"""
    manuals = sorted(family_dir.glob("datasheet_zh/*RM.PDF")) or \
        sorted(family_dir.glob("datasheet_en/*RM.PDF"))
    if not manuals:
        return [], ""
    cached = cache / f"{family_dir.name}.addr.json" if cache else None
    if cached and cached.exists():
        return json.loads(cached.read_text(encoding="utf-8")), manuals[0].name
    import pdfplumber  # noqa: PLC0415
    rows: list[dict] = []
    with pdfplumber.open(manuals[0]) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "R32_" in text or "R16_" in text or "R8_" in text:
                for table in page.find_tables():
                    for row in table.extract():
                        cells = [(c or "").replace("\n", "").replace(" ", "").strip() for c in row]
                        for i, cell in enumerate(cells[:-1]):
                            m = ADDR_NAME.match(cell)
                            if m and HEX32.match(cells[i + 1]):
                                rows.append({"name": m.group("name"),
                                             "address": int(cells[i + 1], 16),
                                             "reset": cells[i + 3] if len(cells) > i + 3 else ""})
                                break
            page.close()
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows, manuals[0].name


def locate(reg: str, offsets: dict[str, dict], block: str, block_name: str) -> list[tuple[str, int]]:
    """RM の register 名に当たり得る header のメンバー [(メンバー名, block 内 offset)]。

    (a) 同名、(b) block 名付き（`EXTEN_TypeDef.EXTEN_CTR`、union の32bit側
    `USBPD_TypeDef.USBPD_STATUS`——8bit の `STATUS` と**両方**返す。RM の
    `R32_USBPD_STATUS` は32bit側なので、どちらかが番地と合えばよい）、(c) 配列＋番号
    （`AFIO_EXTICR1` → `EXTICR[0]`）、(d) instance 番号が block 側にある
    （`DMA_CFGR3` → `DMA1_Channel3.CFGR`）、(e) 入れ子構造体の配列
    （`CAN1_F0R1` → `sFilterRegister[0].FR1`、`TXMI0R` → `sTxMailBox[0].TXMIR`）。
    """
    found: list[tuple[str, int]] = []
    if reg in offsets:
        found.append((reg, offsets[reg]["offset"]))
    if f"{block_name}_{reg}" in offsets:
        found.append((f"{block_name}_{reg}", offsets[f"{block_name}_{reg}"]["offset"]))
    if found:
        return found
    m = TRAILING_DIGITS.match(reg)
    if m:
        stem, digits = m.groups()
        if stem in offsets:
            member = offsets[stem]
            if member["count"] > 1 and 1 <= int(digits) <= member["count"]:
                return [(stem, member["offset"] + (int(digits) - 1) * member["width_bits"] // 8)]
            if block.endswith(digits):
                return [(stem, member["offset"])]
    first = FIRST_DIGITS.search(reg)
    if first:
        leaf = reg[:first.start()] + reg[first.end():]
        idx = int(first.group())
        for name, member in offsets.items():
            head, _, tail = name.rpartition(".")
            if tail == leaf and head.endswith(f"[{idx}]"):
                return [(name, member["offset"])]
    return []


def check_addresses(rows: list[dict], blocks: dict[str, tuple[str, int]],
                    registers: dict[str, dict[str, dict]]) -> tuple[dict, dict, set]:
    """RM の行を (block, register) に解いて EVT の base+offset と比べる。

    返り値: ({(type, register): {"ok": n, "bad": [addr], "reset": set}},
             {block: ok 件数}, 解けなかった名前の集合)。
    `R32_GPIOx_CFGLR` の x は任意の instance——どれかの instance の番地と合えば ok。
    名前の `_` の切り方は block 名が blocks に居る位置で決める（`EXTEN_CTR` は
    block `EXTEN` + register `CTR`）。
    """
    per_register: dict = collections.defaultdict(lambda: {"ok": 0, "bad": [], "reset": set()})
    per_block: dict = collections.Counter()
    unresolved: set[str] = set()
    for r in rows:
        parts = r["name"].split("_")
        hit = False
        for k in range(1, len(parts)):
            block_name, reg = "_".join(parts[:k]), "_".join(parts[k:])
            if block_name in blocks:
                names = [block_name]
            elif "x" in block_name:
                pattern = re.compile("^" + re.escape(block_name).replace("x", "[A-Za-z0-9]+") + "$")
                names = [b for b in blocks if pattern.match(b)]
            else:
                # RM は instance を書かないことがある（`R32_ADC_CTLR1` で header は `ADC1`）。
                # 型が一致する block、または block 名＋数字の block を候補に。
                names = [b for b, (t, _) in blocks.items()
                         if t == block_name or re.fullmatch(re.escape(block_name) + r"\d+", b)]
            if not names:
                continue
            # `R32_DMA_CFGR3` は header の `DMA1_Channel3.CFGR`——register 名の末尾の
            # 数字が instance を選ぶ。block 名で始まる block も候補に入れる。
            names = list(dict.fromkeys(names + [b for b in blocks if b.startswith(block_name)]))
            matched = False
            for b in names:
                type_name, base = blocks[b]
                located = locate(reg, registers.get(type_name, {}), b, block_name)
                if not located:
                    continue
                hit = True
                key = (type_name, located[0][0])
                for use, offset in located:
                    if base + offset == r["address"]:
                        per_register[(type_name, use)]["ok"] += 1
                        per_block[b] += 1
                        if r["reset"]:
                            per_register[(type_name, use)]["reset"].add(r["reset"])
                        matched = True
                        break
                if matched:
                    break
            if hit and not matched:
                per_register[key]["bad"].append(r["address"])
            if hit:
                break
        if not hit:
            unresolved.add(r["name"])
    return per_register, per_block, unresolved


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    ap.add_argument("--rm-cache", type=Path, default=None)
    ap.add_argument("--family", action="append", default=None)
    ap.add_argument("--no-rm", action="store_true", help="RM を読まない（速い。全行 reference）")
    args = ap.parse_args()

    with paths.table("families").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    if args.family:
        families = [x for x in families if x in set(args.family)]

    blocks_out: list[dict] = []
    regs_out: list[dict] = []
    fields_out: list[dict] = []
    layouts_out: list[dict] = []
    notes: list[str] = []

    for family in families:
        family_dir = args.mirrors / family
        header = find_header(family_dir)
        if header is None:
            notes.append(f"{family}: device header が無い")
            continue
        text = header.read_text(errors="ignore")
        lines = text.splitlines()
        structs = read_structs(text)
        bases = extract_addresses.bases(lines)
        banners = read_banners(text)
        manual, manual_name = ({}, "") if args.no_rm else rm_fields(family_dir, args.rm_cache)
        rm_registers = manual.get("__registers__", {})
        evt = f"evt({header.name})"

        # define 名の集合を型ごとに（layout key の材料）
        defines_of_type: dict[str, set[str]] = collections.defaultdict(set)
        for register, defs in banners:
            type_name = register.partition("_")[0]
            defines_of_type[type_name].update(d["name"] for d in defs)

        # layout key
        layout_of: dict[str, str] = {}
        for st in structs.values():
            type_name = st.name
            material = "|".join(f"{m['name']}@{m['offset']}:{m['width_bits']}x{m['count']}"
                                for m in st.members)
            material += "||" + ",".join(sorted(defines_of_type.get(type_name, ())))
            layout_of[type_name] = hashlib.sha1(material.encode()).hexdigest()[:8]
            layouts_out.append({
                "family": family, "type": type_name, "layout": layout_of[type_name],
                "registers": sum(1 for m in st.members if not m["name"].upper().startswith("RESERVED")),
                "fields": len(defines_of_type.get(type_name, ())),
                "size_bytes": st.size, "confidence": "reference", "basis": evt,
            })

        # blocks
        blocks_here: dict[str, tuple[str, int]] = {}
        for line in lines:
            p = POINTER.match(line)
            if not p:
                continue
            base = bases.get(p.group("base"))
            if base is None:
                notes.append(f"{family}: {p.group('block')} の base {p.group('base')} を解けない")
                continue
            blocks_here[p.group("block")] = (p.group("type"), base)

        # registers（構造体のメンバー。reserved は出さない）
        regs_here: dict[str, dict[str, dict]] = collections.defaultdict(dict)
        members_here: dict[str, list[dict]] = {}
        for st in structs.values():
            members_here[st.name] = [m for m in flat_members(st, structs)
                                     if "RESERVED" not in m["name"].upper()]
            for m in members_here[st.name]:
                regs_here[st.name][m["name"]] = m

        # RM の絶対アドレス表で base+offset を裏取り
        per_register: dict = {}
        per_block: dict = {}
        addr_name = ""
        if not args.no_rm:
            addr_rows, addr_name = rm_addresses(family_dir, args.rm_cache)
            per_register, per_block, unresolved_addr = check_addresses(addr_rows, blocks_here, regs_here)
            checked = sum(v["ok"] for v in per_register.values())
            bad = sum(len(v["bad"]) for v in per_register.values())
            notes.append(f"{family}: RM のアドレス表 {len(addr_rows)} 行 → 一致 {checked}・"
                         f"不一致 {bad}・解けない名前 {len(unresolved_addr)}"
                         + (f"（例: {', '.join(sorted(unresolved_addr)[:6])}）" if unresolved_addr else ""))

        for block, (type_name, base) in blocks_here.items():
            ok = per_block.get(block, 0)
            blocks_out.append({
                "family": family, "block": block, "type": type_name,
                "layout": layout_of.get(type_name, ""),
                "base_address": f"{base:#010x}",
                "confidence": "confirmed" if ok else "reference",
                "basis": evt + (f"+rm-address({addr_name})" if ok else ""),
            })

        for type_name, members in members_here.items():
            for m in members:
                rm_name = rm_registers.get(rm_key(f"{type_name}_{m['name']}"), "")
                found = per_register.get((type_name, m["name"]))
                confidence, basis, check_text, reset = "reference", [evt], "", ""
                if rm_name:
                    confidence = "confirmed"
                    basis.append(f"rm({manual_name})")
                if found and found["ok"]:
                    confidence = "confirmed"
                    check_text = f"ok:{found['ok']}"
                    basis.append(f"rm-address({addr_name})")
                    reset = ";".join(sorted(found["reset"]))
                if found and found["bad"]:
                    confidence = "conflict"
                    check_text = (check_text + ";" if check_text else "") + f"mismatch:{len(found['bad'])}"
                    basis.append(f"!rm-address({addr_name})(={found['bad'][0]:#010x})")
                regs_out.append({
                    "family": family, "type": type_name, "register": m["name"],
                    "offset": f"{m['offset']:#05x}", "width_bits": m["width_bits"],
                    "count": m["count"], "rm_register": rm_name, "rm_reset": reset,
                    "rm_address_check": check_text,
                    "confidence": confidence, "basis": "+".join(basis),
                })

        # fields
        unresolved = collections.Counter()
        for register, defs in banners:
            type_name, member, why = resolve_member(register, structs)
            if member is None:
                unresolved[why] += 1
            by_name = {d["name"]: d for d in defs}
            for d in defs:
                name, mask = d["name"], d["mask"]
                span = bit_span(mask)
                kind, of_field, value = "field", "", ""
                # 値の列挙: 親（名前が接頭辞・mask が包含・自分より広い）があるか
                parent = None
                stem = name
                while "_" in stem:
                    stem = stem.rsplit("_", 1)[0]
                    cand = by_name.get(stem)
                    if cand and cand["mask"] != mask and cand["mask"] & mask == mask:
                        parent = cand
                        break
                if parent:
                    kind, of_field = "value", field_name(parent["name"], register, type_name)
                    pspan = bit_span(parent["mask"])
                    if pspan:
                        value = str(mask >> pspan[0])
                elif mask == 0:
                    # mask 0 は field ではあり得ない。親が名前で見つからない値の列挙
                    # （`RCC_MCO_NOCLOCK` の親が `RCC_CFGR0_MCO` と綴られる等）。
                    kind, value = "value", "0"
                fname = field_name(name, register, type_name)
                bits = "" if span is None else (f"{span[0]}" if span[0] == span[1]
                                                else f"{span[1]}:{span[0]}")
                confidence, basis = "reference", [evt]
                rm_access = rm_reset = ""
                said = manual.get((rm_key(register), field_key(fname))) if kind == "field" else None
                if said:
                    rm_access = said.get("access") or ""
                    rm_reset = "" if said.get("reset_value") is None else str(said["reset_value"])
                    lo, width = said["bit_offset"], said["bit_width"]
                    if span and (lo, lo + width - 1) == span:
                        confidence = "confirmed"
                        basis.append(f"rm({manual_name})")
                    elif span:
                        confidence = "conflict"
                        basis.append(f"!rm({manual_name})(={lo + width - 1}:{lo})")
                fields_out.append({
                    "family": family, "register": register, "type": type_name,
                    "member": (f"{member['struct']}.{member['name']}"
                               + (f"[{int(member['index']) - 1}]" if member["index"] and member["count"] > 1 else "")
                               if member else ""),
                    # `field` は読むための名前（型・register の接頭辞を落とした）、
                    # `define` は EVT header の綴りそのまま——証拠へ戻る鍵。
                    "field": fname, "define": name, "kind": kind, "of_field": of_field,
                    "bits": bits, "mask": f"{mask:#x}", "value": value,
                    "description": d["comment"], "rm_access": rm_access, "rm_reset": rm_reset,
                    "confidence": confidence, "basis": "+".join(basis),
                })
        for why, n in unresolved.items():
            notes.append(f"{family}: banner {n} 件を構造体のメンバーに結べない——{why}")
        missing = sorted({register for register, _ in banners
                          if resolve_member(register, structs)[1] is None})
        if missing:
            notes.append(f"{family}: 結べない banner: {', '.join(missing[:12])}"
                         + (" …" if len(missing) > 12 else ""))

    # 出力
    def write(dest: Path, columns: list[str], rows: list[dict], key) -> None:
        rows.sort(key=key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.family:
            # 部分実行は既存の他 family の行を保つ
            try:
                with dest.open(newline="", encoding="utf-8") as f:
                    keep = [r for r in csv.DictReader(f) if r["family"] not in set(args.family)]
            except FileNotFoundError:
                keep = []
            rows = sorted(keep + rows, key=key)
        with dest.open("w", encoding="utf-8", newline="") as out:
            w = csv.DictWriter(out, fieldnames=columns)
            w.writeheader()
            w.writerows({**{c: r.get(c, "") for c in columns}, "#": "#"} for r in rows)
        tally = collections.Counter(r["confidence"] for r in rows)
        print(f"{dest}: {len(rows)} 行  {dict(tally)}", file=sys.stderr)

    write(paths.table("register_blocks", args.out), BLOCK_COLUMNS, blocks_out,
          lambda r: (r["family"], int(r["base_address"], 16), r["block"]))
    write(paths.table("registers", args.out), REGISTER_COLUMNS, regs_out,
          lambda r: (r["family"], r["type"], int(r["offset"], 16), r["register"]))
    write(paths.table("register_fields", args.out), FIELD_COLUMNS, fields_out,
          lambda r: (r["family"], r["register"], int(r["mask"], 16), r["field"]))
    write(paths.index("register_layouts", args.out), LAYOUT_COLUMNS, layouts_out,
          lambda r: (r["family"], r["type"]))
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
