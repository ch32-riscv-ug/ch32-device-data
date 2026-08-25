#!/usr/bin/env python3
"""USBPD を動かすための配管（RCC の enable bit と PHY 設定 bit）→ tables/usbpd_plumbing.csv

**CH32X035 以外の series へ PD を広げる前提**（consumer の依頼 R-26-4）。block の
base は `memory_map.csv`、CC pad は `pin_roles.csv` が持っている。足りないのは

    RCC の enable bit      `clock_enables.csv` の USBPD 行（family で bus が違う）
    PHY の設定 bit         X035 は AFIO_CTLR の USBPD_PHY_V33(bit8) / USBPD_IN_HVT(bit9)。
                           これが他 family ではどこにあるか

**PHY 設定 bit の置き場所が family で違い、それが表の要る理由です。**

    CH32X035        AFIO->CTLR    USBPD_PHY_V33 / USBPD_IN_HVT / UDP_PUE …
    CH32L103/V205   AFIO->CR      USBPD_IN_HVT
    CH32H417        AFIO->PCFR1   USBPD_CC_HVT
    CH32M030        EXTEN->EXTEN_CTLR0   USBPD0_CC_REF / CC_HVT / LVE_T（PD が2つ）
    CH32X315        header に PHY 設定の define が無い（RCC の enable だけ載せる）

出所は EVT の device header。define の名前がレジスタを名乗る（`AFIO_CTLR_…`）か、
名乗らないものは直前の banner コメント（`Bit definition for EXTEN_CTLR0 register`）
が言う。bit 位置は RM のレジスタ表と突き合わせ、一致で confirmed。

実行:
    uv run tools/build_usbpd_plumbing.py [--mirrors <dir>] [--out tables]
    （`clock_enables.csv` を先に作っておく）
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_addresses  # noqa: E402
import extract_registers  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "peripheral", "rcc_register", "rcc_bit", "rcc_address",
           "phy_block", "phy_register", "phy_field", "phy_bits", "phy_mask", "phy_address",
           "#", "confidence", "basis"]

DEFINE = re.compile(r"^\s*#define\s+(?P<name>(?:AFIO|EXTEN)_\w*(?:USBPD|UDP|UDM|PD_PHY)\w*)\s+"
                    r"\(\s*\(\s*u?int\d+_t\s*\)\s*(?P<mask>0[xX][0-9A-Fa-f]+)\s*\)", re.M)
BANNER = re.compile(r"Bit definition for\s+(?P<register>\w+)\s+register", re.IGNORECASE)
STRUCT = re.compile(r"typedef\s+struct\s*\{(?P<body>[^{}]*?)\}\s*(?P<name>AFIO|EXTEN)_TypeDef\s*;", re.S)
MEMBER = re.compile(r"(?:__I?O?\s+|volatile\s+|const\s+)*"
                    r"u?int(?P<width>8|16|32|64)_t\s+(?P<name>\w+)"
                    r"(?:\s*\[\s*(?P<count>\d+)\s*\])?\s*;")
ENUM_VALUE = re.compile(r"^(?P<parent>.+)_\d+$")


def find_header(family_dir: Path) -> Path | None:
    found = sorted(family_dir.glob("EVT/**/Peripheral/inc/ch32*.h"))
    plain = [p for p in found if re.fullmatch(r"ch32[a-z0-9]+\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else (found[0] if found else None)


def read_structs(text: str) -> dict[str, dict[str, int]]:
    """{block: {member: offset}}。

    **入れ子の union を持つ構造体がある。** CH32M030 の `EXTEN_TypeDef` は途中に
    `union { struct {…}; … };` を挟むので、`{…}` を1段だけ見る正規表現では丸ごと
    落ちる（USBPD の PHY 設定 bit が `EXTEN_CTLR0` にあるのに「define が無い」と
    出ていた）。`} NAME_TypeDef;` から手前の `typedef struct` まで戻って本体を取り、
    **union 以降のメンバーはオフセットが一意でないので採らない**。
    """
    out: dict[str, dict[str, int]] = {}
    for end in re.finditer(r"\}\s*(?P<name>AFIO|EXTEN)_TypeDef\s*;", text):
        start = text.rfind("typedef struct", 0, end.start())
        if start < 0:
            continue
        body = text[start:end.start()]
        body = body.split("union", 1)[0]
        offsets: dict[str, int] = {}
        offset = 0
        for line in body.splitlines():
            member = MEMBER.search(line)
            if not member:
                continue
            offsets[member.group("name")] = offset
            offset += int(member.group("width")) // 8 * int(member.group("count") or 1)
        out[end.group("name")] = offsets
    return out


def bit_span(mask: int) -> tuple[int, int] | None:
    if mask == 0:
        return None
    lo = (mask & -mask).bit_length() - 1
    hi = mask.bit_length() - 1
    return (lo, hi) if mask == ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1) else None


def phy_defines(text: str, structs: dict) -> list[tuple[str, str, str, int]]:
    """[(block, register, field, mask)]。register は名前か直前の banner から。"""
    out = []
    names = {m.group("name"): int(m.group("mask"), 16) for m in DEFINE.finditer(text)}
    banner_at: list[tuple[int, str]] = [(m.start(), m.group("register")) for m in BANNER.finditer(text)]
    for m in DEFINE.finditer(text):
        name, mask = m.group("name"), int(m.group("mask"), 16)
        parent = ENUM_VALUE.match(name)
        if parent and parent.group("parent") in names \
                and names[parent.group("parent")] & mask == mask \
                and names[parent.group("parent")] != mask:
            continue  # 値の列挙
        block = name.split("_")[0]
        members = structs.get(block, {})
        rest = name[len(block) + 1:]
        register = field = None
        for member in sorted(members, key=len, reverse=True):
            if rest.startswith(member + "_"):
                register, field = member, rest[len(member) + 1:]
                break
        if register is None:
            # 名前がレジスタを名乗らない（CH32M030 の EXTEN_USBPD0_CC_REF）。
            # 直前の banner が言う。
            before = [r for at, r in banner_at if at < m.start()]
            if before and before[-1] in members:
                register, field = before[-1], rest
        if register is None:
            continue
        out.append((block, register, field, mask))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    with (args.out / "families.csv").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    enables: dict[str, list[dict]] = collections.defaultdict(list)
    with (args.out / "clock_enables.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if re.fullmatch(r"USBPD\d*", r["peripheral"]):
                enables[r["family"]].append(r)

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        header = find_header(args.mirrors / family)
        if header is None or family not in enables:
            continue  # PD を持たない family（clock enable に USBPD が無い）
        text = header.read_text(errors="ignore")
        structs = read_structs(text)
        bases = extract_addresses.bases(text.splitlines())
        phy = phy_defines(text, structs)
        manual: dict = {}
        manual_name = ""
        if phy:
            paths = sorted((args.mirrors / family / "datasheet_zh").glob("*RM.PDF"))
            if paths:
                fields, _ = extract_registers.extract(paths[0], None)
                manual = {(f["register"], f["field"]): (f["bit_offset"], f["bit_width"])
                          for f in fields if f["register"].startswith(("AFIO_", "EXTEN_"))}
                manual_name = paths[0].name
        for en in enables[family]:
            rcc = {"family": family, "peripheral": en["peripheral"],
                   "rcc_register": en["register"], "rcc_bit": en["bit"],
                   "rcc_address": en["address"]}
            if not phy:
                notes.append(f"{family}: PHY 設定の define が header に無い（RCC の enable だけ）")
                rows.append({**rcc, "phy_block": "", "phy_register": "", "phy_field": "",
                             "phy_bits": "", "phy_mask": "", "phy_address": "",
                             "confidence": en["confidence"], "basis": en["basis"]})
                continue
            for block, register, field, mask in phy:
                # PD が2つある family（M030）は field 名に番号が付く。番号が合う側だけ。
                mine = re.search(r"USBPD(\d)", field)
                want = re.search(r"USBPD(\d)", en["peripheral"])
                if mine and want and mine.group(1) != want.group(1):
                    continue
                span = bit_span(mask)
                bits = ("" if span is None else f"{span[0]}" if span[0] == span[1]
                        else f"{span[1]}:{span[0]}")
                confidence, basis = "reference", [f"evt({header.name})"]
                said = next((manual[(r, field)] for r in (f"{block}_{register}", register)
                             if (r, field) in manual), None)
                if said and span:
                    lo, width = said
                    if (lo, lo + width - 1) == span:
                        confidence = "confirmed"
                        basis.append(f"rm({manual_name})")
                    else:
                        confidence = "conflict"
                        basis.append(f"!rm({manual_name})(={lo + width - 1}:{lo})")
                base = bases.get(f"{block}_BASE")
                offset = structs[block][register]
                rows.append({**rcc, "phy_block": block, "phy_register": register,
                             "phy_field": field, "phy_bits": bits, "phy_mask": f"{mask:#x}",
                             "phy_address": f"{base + offset:#010x}" if base is not None else "",
                             "confidence": confidence, "basis": "+".join(basis)})

    dest = args.out / "usbpd_plumbing.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{dest}: {len(rows)} 行  family {len({r['family'] for r in rows})}  {dict(tally)}",
          file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
