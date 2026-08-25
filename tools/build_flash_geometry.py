#!/usr/bin/env python3
"""flashの消去単位・書き込み粒度 → tables/flash_geometry.csv

**低レベル flash API の前提**（consumer の依頼 R-26-1）。`products.csv` は容量
しか持たず、消去単位と書き込み粒度は family ごとに違います——標準ページ消去は
1K/2K/4K、快速ページは 64B/128B/256B、word 書き込みが**無い** family もある
（CH32X035 等）。consumer 側で手書きすると family の数だけ誤記リスクになります。

**出所は2つあり、突き合わせます。**

    EVT driver     ch32*_flash.c の関数の @brief（`page size 4KB` / `1page = 256Byte`）
                   と、FLASH_ProgramWord / FLASH_ProgramHalfWord の**有無**
    RM             闪存章の本文（`闪存可以按标准页（1K字节）擦除` /
                   `快速编程按页（128字节）进行编程` / `快速擦除按块（32K字节）`）

両方が一致すれば confirmed、片方だけなら reference、食い違えば conflict で
両論を basis に残します。**実際に食い違いが1件ある**——CH32V103 の driver は
`ProgramPage_Fast ... 1page = 256Byte` と書くが、RM は `快速编程按页（128字节）`
で、同じ driver の消去側も 128B、`ROM_ERASE` の引数条件も `StartAddr%128 == 0`。
EVT のコメントの写し間違いと判断し、値は 128 を採って conflict にします。

列の意味:

    page_erase_bytes     標準ページ消去の単位
    fast_erase_bytes     快速ページ消去の単位（V407/X315/H417 は per-page の
                         快速消去を持たず、ブロック消去のみ）
    fast_program_bytes   快速ページ書き込みの単位
    block_erase_bytes    快速ブロック消去の単位
    program_word         FLASH_ProgramWord / ProgramHalfWord が driver にあるか
                         （1 = word/halfword 単位の直接書き込みができる。
                         空 = 快速ページ経由のみ）
    zero_wait_note       flash_bytes（零等待領域）と総容量の関係の注意。
                         option byte で領域が動く family は memory_configs.csv、
                         総容量は product_attributes の code_flash_bytes を指す

CH32H417 は **flash モードで幾何が変わります**——`FLASH_CFGR0` bit28 が立つ
（dual flash mode）とページ 8K・ブロック 64K、寝ていると 4K/32K。driver の
`FLASH_ErasePage` がアドレスマスクを切り替えているのがそれで、`note` に書きます。

実行:
    uv run tools/build_flash_geometry.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import glob
import re
import sys
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "page_erase_bytes", "fast_erase_bytes", "fast_program_bytes",
           "block_erase_bytes", "program_word", "zero_wait_note", "note",
           "#", "confidence", "basis"]

# --- EVT driver 側 -----------------------------------------------------------
# @brief から次のタグまでを丸ごと。CH32H417 の EraseBlock_Fast は寸法を
# @brief の**次の行**に書く（Dual なら 64KB / single なら 32KB）。
FN_DOC = re.compile(r"@fn\s+(?P<name>FLASH_\w+).*?@brief\s+(?P<brief>.*?)"
                    r"(?=@param|@return|\*/)", re.DOTALL)
FN_DEF = re.compile(r"(?:FLASH_Status|void)\s+(FLASH_\w+)\s*\(")
# `page size 4KB` / `(2KB)` / `(1KB)` / `1page = 256Byte` / `1Block = 32KByte`
KB = re.compile(r"(\d+)\s*KB")
BYTES = re.compile(r"=\s*(\d+)\s*Byte", re.IGNORECASE)

# --- RM 側 --------------------------------------------------------------------
RM_STANDARD = re.compile(r"标准页[（(](\d+)\s*K?B?字?节?[)）]|按标准页[（(](\d+)\s*K")
RM_FAST_PROGRAM = re.compile(r"快速编程按页[（(](\d+)\s*字节[)）]")
RM_FAST_ERASE = re.compile(r"快速擦除[也]?按页[（(](\d+)\s*字节[)）]")
RM_BLOCK = re.compile(r"快速擦除按块[（(](\d+)\s*K字节[)）]")
# 闪存章はどの RM でも前半〜中盤にある。全ページ舐めると重い。
RM_NEEDLE = ("快速编程", "标准页", "快速擦除")


def read_driver(family_dir: Path) -> tuple[dict, str] | None:
    """driver の @brief から幾何を読む。(値の辞書, ファイル名)。"""
    paths = sorted(family_dir.glob("EVT/**/Peripheral/src/ch32*_flash.c"))
    if not paths:
        return None
    text = paths[0].read_text(errors="ignore")
    briefs = {m.group("name"): m.group("brief") for m in FN_DOC.finditer(text)}
    functions = {m.group(1) for m in FN_DEF.finditer(text)}

    def size(name: str, unit: str) -> int | None:
        brief = briefs.get(name, "")
        hits = (KB if unit == "K" else BYTES).findall(brief)
        if not hits:
            return None
        # モードで寸法が変わるもの（CH32H417 の `4KB or 8KB`・block 32KB/64KB）は
        # **小さいほう＝single flash mode** を列に置き、dual は note で言う。
        return min(int(h) for h in hits) * (1024 if unit == "K" else 1)

    found = {
        "page_erase_bytes": size("FLASH_ErasePage", "K"),
        "fast_erase_bytes": size("FLASH_ErasePage_Fast", "B"),
        "fast_program_bytes": size("FLASH_ProgramPage_Fast", "B"),
        "program_word": ("FLASH_ProgramWord" in functions
                         or "FLASH_ProgramHalfWord" in functions),
    }
    block = None
    for name in functions:
        m = re.match(r"FLASH_EraseBlock_(\d+)K_Fast", name)
        if m:
            block = int(m.group(1)) * 1024
    if block is None and any(f.startswith("FLASH_EraseBlock") for f in functions):
        # CH32H417 は @fn が `FLASH_EraseBlock_32K_Fast`、実関数が
        # `FLASH_EraseBlock_Fast` と**コメント側の名前がずれている**ので、
        # EraseBlock で始まるどの brief からでも寸法を拾う。
        for name, brief in briefs.items():
            if name.startswith("FLASH_EraseBlock"):
                hits = KB.findall(brief)
                if hits:
                    block = min(int(h) for h in hits) * 1024
                    break
    found["block_erase_bytes"] = block
    return found, paths[0].name


def read_manual(family_dir: Path) -> tuple[dict, str] | None:
    """RM の闪存章の本文から幾何を読む。(値の辞書, ファイル名)。"""
    paths = sorted(family_dir.glob("datasheet_zh/*RM.PDF"))
    if not paths:
        return None
    found: dict = {}
    with pdfplumber.open(paths[0]) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            page.close()
            if not any(n in text for n in RM_NEEDLE):
                continue
            m = RM_STANDARD.search(text)
            if m and "page_erase_bytes" not in found:
                found["page_erase_bytes"] = int(m.group(1) or m.group(2)) * 1024
            m = RM_FAST_PROGRAM.search(text)
            if m and "fast_program_bytes" not in found:
                found["fast_program_bytes"] = int(m.group(1))
            m = RM_FAST_ERASE.search(text)
            if m and "fast_erase_bytes" not in found:
                found["fast_erase_bytes"] = int(m.group(1))
            m = RM_BLOCK.search(text)
            if m and "block_erase_bytes" not in found:
                found["block_erase_bytes"] = int(m.group(1)) * 1024
    return found, paths[0].name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    with (args.out / "families.csv").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    with (args.out / "products.csv").open(newline="", encoding="utf-8") as f:
        family_of = {r["part_number"]: r["family"] for r in csv.DictReader(f)}
    # 零等待の注意はデータから導く。option byte で領域が動く family と、
    # 比較表が総容量（code_flash_bytes）を別に数える family。
    movable = set()
    with (args.out / "memory_configs.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            movable.add(family_of.get(row["part_number"], ""))
    stated_total = set()
    with (args.out / "product_attributes.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["attribute"].startswith("code_flash"):
                stated_total.add(family_of.get(row["part_number"], ""))

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        family_dir = args.mirrors / family
        driver = read_driver(family_dir)
        manual = read_manual(family_dir)
        if driver is None and manual is None:
            notes.append(f"{family}: flash driver も RM も読めない")
            continue
        evt, driver_name = driver or ({}, "")
        rm, manual_name = manual or ({}, "")

        confidence = "reference"
        basis: list[str] = []
        if driver:
            basis.append(f"evt({driver_name})")
        if manual:
            basis.append(f"rm({manual_name})")
        row = {"family": family, "program_word": "1" if evt.get("program_word") else ""}
        conflicts: list[str] = []
        for column in ("page_erase_bytes", "fast_erase_bytes",
                       "fast_program_bytes", "block_erase_bytes"):
            a, b = evt.get(column), rm.get(column)
            if a is not None and b is not None:
                if a == b:
                    confidence = "confirmed" if confidence != "conflict" else confidence
                    row[column] = a
                else:
                    # CH32V103 の fast_program がこれ（EVT コメント 256 / RM 128）。
                    # RM と、同じ driver の消去側・アドレス条件（%128）が揃うので
                    # RM を採る。
                    confidence = "conflict"
                    row[column] = b
                    conflicts.append(f"!evt-comment:{column}(={a})")
            else:
                row[column] = a if a is not None else (b if b is not None else "")
        zero = []
        # H41x は零等待実行を「Code FLASH を RAM_CODE へロードして走らせる」方式で
        # 行う。基準リンカがそう書いている（`zero_wait flah ,and loaded into
        # RAM_CODE for running`）。RAM_CODE 領域を持つ family だけの話。
        reference_ld = sorted(family_dir.glob("EVT/EXAM/SRC/Ld/**/*.ld"))
        if any("RAM_CODE" in ld.read_text(errors="ignore") for ld in reference_ld):
            zero.append("zero-wait execution loads Code FLASH into RAM_CODE "
                        "(Link.ld); flash_bytes is the non-zero-wait Code FLASH total")
        if family in movable:
            zero.append("zero-wait region is set by option byte (memory_configs.csv)")
        if family in stated_total:
            zero.append("products.flash_bytes is the zero-wait region; total is "
                        "product_attributes code_flash_bytes")
        row["zero_wait_note"] = "; ".join(zero)
        # データ列は英語（中文の原文だけが _zh 列に残る規約。check_tables が見る）。
        row["note"] = ("dual flash mode (FLASH_CFGR0 bit28): page 8K, block 64K"
                       if family == "CH32H417" else "")
        row["confidence"] = confidence
        row["basis"] = "+".join(basis + conflicts)
        rows.append(row)

    rows.sort(key=lambda r: r["family"])
    dest = args.out / "flash_geometry.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    from collections import Counter
    print(f"{dest}: {len(rows)} 行  {dict(Counter(r['confidence'] for r in rows))}",
          file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
