#!/usr/bin/env python3
"""main flashの消去/書き込み**手順** → evidence/flash_program_method.csv

**粒度ではなく順序**（consumer の依頼 R-32 / ch32rv 0004）。`flash_geometry.csv` は
消去単位と書き込み粒度を持ちますが、**その bit をどの順に叩くか**が無いため、consumer は
family ごとに実機で当てるしかありませんでした。実害も出ています——CH32X035 を PgStart 方式で
実装したら program が無反応（消去は全 family 共通なので「消えているのに書けない」）。

**出所は2つあり、突き合わせます。**

    RM      闪存章の**番号付き手順**。`4）设置FLASH_CTLR寄存器的FTPG位…` のように、
            順番に制御 bit を名指す。zh を一次にする（R-31 で英訳が5通りに揺れ、
            32bit 値を `byte` と誤訳する版があると分かったため）
    EVT     `ch32*_flash.c` の `FLASH_ProgramPage_Fast` / `FLASH_ErasePage_Fast` が
            実際に立てる bit の順

分類は2系統です。

    Buffered   FTPG → BUFRST → （4B書込 + BUFLOAD）× n → FLASH_ADDR → STRT
    PgStart    FTPG → （4B書込）× n → PG_STRT

**`register_fields.csv` の綴りを併記します**（`ctlr_bit_names`）——RM は `FTPG`/`BUFRST`、
EVT header は `PAGE_PG`/`BUF_RST` と**同じ bit を違う名前で呼ぶ**ので、consumer が
`register_fields` と join する手掛かりが要ります。

**RM に無いが必須の手順は `undocumented_note`**。CH32V103 は driver が各 erase/program の
後に `*(uint32_t*)0x40022034 = *(uint32_t*)((addr & ~3) ^ 0x1000)` を書きます。RM に記述は
無く、consumer の実測では**これが無いと erase も program も無反応**でした。

実行:
    uv run tools/build_flash_program_method.py [--mirrors <dir>] [--out evidence]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "program_method", "program_buffer_load_bits", "program_commit",
           "erase_method", "ctlr_bit_names", "undocumented_note", "#", "confidence", "basis"]

# --- RM 側 --------------------------------------------------------------------
# 闪存章の節見出し。手順はこの見出しの下に番号付きで並ぶ。
SECTION = re.compile(r"(快速页?编程|标准页?编程|快速页?擦除|标准页?擦除|快速块擦除)")
# 手順の行が名指す制御 bit（`R32_FLASH_CTLR` と `FLASH_CTLR` の両方の書き方がある）。
STEP_BIT = re.compile(r"(FTPG|PAGE_PG|BUFRST|BUF_RST|BUFLOAD|BUF_LOAD|PG_?STRT|STRT|FTER|PAGE_ER"
                      r"|BER32|BER64|PAGE_BER32|PAGE_BER64|BLOCK_ER)")
STEP_ADDR = re.compile(r"FLASH_ADDR")
# 番号付きの手順行だけを見る（`4）设置…`）。説明文が bit 名を含んでも拾わないため。
STEP_LINE = re.compile(r"^\s*\d{1,2}\s*[）)]")
RM_NEEDLE = ("快速页编程", "快速编程", "快速页擦除", "快速擦除")

# --- EVT 側 -------------------------------------------------------------------
# CH32H417 は per-page の快速消去を持たず、関数名も `FLASH_EraseBlock_Fast`。
FN_BODY = re.compile(r"void\s+(FLASH_(?:ProgramPage_Fast|ErasePage_Fast|EraseBlock_Fast))"
                     r"\s*\([^)]*\)\s*\{", re.MULTILINE)
# `FLASH->CTLR |= CR_PAGE_PG;` / `CR_STRT_Set` / `CR_PG_STRT`。末尾の `_Set` は付く版と
# 付かない版がある。
EVT_BIT = re.compile(r"CTLR\s*\|=\s*CR_(\w+?)(?:_Set)?\s*;")
# **buffer経由かどうかは関数の有無で決まる**——`ProgramPage_Fast`は起動だけを行い、
# 4バイト書込と`BUFLOAD`は`FLASH_BufLoad`という別関数に分かれている（CH32V003ほか）。
EVT_BUFFER = re.compile(r"void\s+FLASH_Buf(?:Load|Reset)\b")
# buffer に一度に積む幅。`FLASH_BufLoad` の `Data` 引数の本数で決まり、family で
# **32/64/128 bit の3通り**ある（V003ほか Data0 の1本＝32、M030 は Data0/Data1＝64、
# V103 は Data0..Data3＝128）。幅を満たさない書込は黙って壊れる——consumer(ch32rv)は
# V103 で word 単位に積んで内容が壊れ、標準 half-word へ退避している。RM は幅を
# 手順として書かないので、**driver のシグネチャが一次**。
EVT_BUFLOAD_SIG = re.compile(r"void\s+FLASH_BufLoad\s*\(([^)]*)\)")
EVT_BUFLOAD_DATA = re.compile(r"\buint32_t\s+Data\d+\b")
# RM に無い副作用（CH32V103）。FLASH base + 0x34 への読み書き。
MAGIC = re.compile(r"\*\s*\(\s*__IO\s+uint32_t\s*\*\s*\)\s*(0x4002203[0-9A-Fa-f])\s*="
                   r"[^;]*?\^\s*(0x[0-9A-Fa-f]+)")


def rm_steps(family_dir: Path, language: str = "zh") -> tuple[dict, str] | None:
    """RMの闪存章から、節ごとの手順のbit列を読む。({節: [bit...]}, ファイル名)。"""
    found = sorted(family_dir.glob(f"datasheet_{language}/*RM.PDF"))
    if not found:
        return None
    steps: dict[str, list[str]] = {}
    section = None
    with pdfplumber.open(found[0]) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            page.close()
            if section is None and not any(n in text for n in RM_NEEDLE):
                continue
            for line in text.splitlines():
                stripped = line.strip()
                head = SECTION.search(stripped)
                # 見出しは短い行。手順行（`4）…`）の中の語は見出しにしない。
                if head and len(stripped) < 40 and not STEP_LINE.match(stripped):
                    section = head.group(1)
                    steps.setdefault(section, [])
                    continue
                if section is None or not STEP_LINE.match(stripped):
                    continue
                sequence = steps.setdefault(section, [])
                for m in STEP_BIT.finditer(stripped):
                    bit = m.group(1).replace("PGSTRT", "PG_STRT")
                    if not sequence or sequence[-1] != bit:
                        sequence.append(bit)
                if STEP_ADDR.search(stripped) and (not sequence or sequence[-1] != "FLASH_ADDR"):
                    sequence.append("FLASH_ADDR")
    return ({k: v for k, v in steps.items() if v}, found[0].name)


def buf_load_bits(family_dir: Path) -> int:
    """`FLASH_BufLoad`が一度に積む幅（bit）。buffer経由でなければ0。

    ヘッダの宣言と`.c`の定義の両方を見る（片方しか無いmirrorがある）。`Data`引数
    1本＝32bit。**この幅を満たさない単位で積むと内容が壊れる**ので、consumerには
    手順そのものと同じくらい効く（依頼0004のフィードバック）。"""
    for pattern in ("EVT/**/Peripheral/inc/ch32*_flash.h",
                    "EVT/**/Peripheral/src/ch32*_flash.c"):
        for path in sorted(family_dir.glob(pattern)):
            match = EVT_BUFLOAD_SIG.search(path.read_text(errors="ignore"))
            if match:
                return 32 * len(EVT_BUFLOAD_DATA.findall(match.group(1)))
    return 0


def evt_steps(family_dir: Path) -> tuple[dict, str, bool] | None:
    """driverの手順。({関数名: [立てるbit...], "_buffer": [...]}, ファイル名, RMに無い副作用)。"""
    found = sorted(family_dir.glob("EVT/**/Peripheral/src/ch32*_flash.c"))
    if not found:
        return None
    text = found[0].read_text(errors="ignore")
    bodies: dict[str, list[str]] = {}
    for m in FN_BODY.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        body = text[m.end():i]
        sequence: list[str] = []
        for hit in EVT_BIT.finditer(body):
            bit = hit.group(1).upper()
            if not sequence or sequence[-1] != bit:
                sequence.append(bit)
        bodies[m.group(1)] = sequence
    if EVT_BUFFER.search(text):
        # buffer関数がある＝`BUFRST`/`BUFLOAD`を使う系統。`ProgramPage_Fast`本体には
        # 出てこないので、関数の有無をそのまま手順の印にする。
        bodies["_buffer"] = ["BUFRST", "BUFLOAD"]
    return bodies, found[0].name, MAGIC.search(text)


def classify(sequence: list[str], bits: int = 32) -> tuple[str, str]:
    """手順のbit列 → (program_method, program_commit)。R-30の`write_unit`と同じ語彙。

    `bits`はbufferに一度に積む幅（`buf_load_bits`）。全familyを`32-bit`と書いていたが、
    M030は64bit・V103は128bitで、そのまま実装すると壊れる（依頼0004のフィードバック）。"""
    buffered = any(b.startswith(("BUFRST", "BUF_RST", "BUFLOAD", "BUF_LOAD")) for b in sequence)
    enable = next((b for b in sequence if b in ("FTPG", "PAGE_PG")), "FTPG")
    if buffered:
        names = [b for b in sequence if b.startswith(("BUFRST", "BUF_RST"))]
        load = [b for b in sequence if b.startswith(("BUFLOAD", "BUF_LOAD"))]
        method = (f"fast page, {bits or 32}-bit buffer writes ({enable} + "
                  f"{names[0] if names else 'BUFRST'}/{load[0] if load else 'BUFLOAD'}, then STRT)")
        return method, "STRT (bit6)"
    if "PG_STRT" in sequence:
        return f"fast page, direct writes ({enable}, then PG_STRT)", "PG_STRT (bit21)"
    if sequence:
        return f"fast page ({enable}, then STRT)", "STRT (bit6)"
    return "", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()

    with paths.table("families").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    # consumer が register_fields と join するための綴り。
    ctlr_names: dict[str, list[str]] = {}
    with paths.table("register_fields").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if "FLASH_CTLR" not in row["register"]:
                continue
            if row["field"] in ("FTPG", "PAGE_PG", "BUFRST", "BUF_RST", "BUFLOAD",
                                "BUF_LOAD", "PG_STRT", "STRT", "FTER", "PAGE_ER",
                                "BER32", "BER64", "PAGE_BER32", "PAGE_BER64"):
                ctlr_names.setdefault(row["family"], []).append(row["field"])

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        family_dir = args.mirrors / family
        manual = rm_steps(family_dir)
        language = "zh"
        if manual and not manual[0]:
            manual = None
        if manual is None:
            manual = rm_steps(family_dir, "en")
            language = "en"
            if manual and not manual[0]:
                manual = None
        driver = evt_steps(family_dir)
        if manual is None and driver is None:
            notes.append(f"{family}: RM も flash driver も読めない")
            continue
        sections, manual_name = manual or ({}, "")
        evt, driver_name, magic = driver or ({}, "", False)

        # **快速**の節を優先する（標準の節が先に来る文書があり、`标准擦除`の手順＝
        # `FLASH_ADDR`+`STRT`を拾って快速の`FTER`を取り逃していた）。
        def pick(word: str) -> list[str]:
            fast = [v for k, v in sections.items() if word in k and "快速" in k and v]
            other = [v for k, v in sections.items() if word in k and v]
            return (fast or other or [[]])[0]

        program = pick("编程")
        erase = pick("擦除")
        bits = buf_load_bits(family_dir)
        method, commit = classify(program, bits)
        evt_program = list(evt.get("_buffer", [])) + evt.get("FLASH_ProgramPage_Fast", [])
        evt_method, evt_commit = classify(evt_program, bits)

        confidence = "reference"
        basis: list[str] = []
        if manual:
            basis.append(f"rm{'-en' if language == 'en' else ''}({manual_name})")
        if driver:
            basis.append(f"evt({driver_name})")
        if bits:
            # 幅はRMの手順には出ない。driverのシグネチャだけが根拠だとわかるようにする。
            basis.append(f"evt-bufload({bits}bit)")
        if method and evt_method:
            if method.split("(")[0] == evt_method.split("(")[0]:
                confidence = "confirmed"
            else:
                # H417 の RM は起動側も `FTPG` と書く（手順4で立てた有効化bitと同じ）が、
                # driver は `CR_PG_STRT`・`register_fields` は `PG_STRT` bit21 を持ち、
                # 同じ direct writes 系の V407/X315 も PG_STRT。**RM側の誤記と判断して
                # driver の読みを採用値にし、RM の読みを `!` で残す**——「どちらが正しいか
                # 判断したら、その値を列に置く」（V103 の fast_program_bytes で RM を
                # 採ったのと同じ扱い）。confidence は conflict のままなので、
                # fail-closed で読む consumer の挙動は変わらない。
                confidence = "conflict"
                basis.append(f"!rm:program_method({method})")
                method, commit = evt_method, evt_commit
        elif not method:
            method, commit = evt_method, evt_commit

        ERASE_ENABLE = ("FTER", "PAGE_ER", "BER32", "BER64", "PAGE_BER32", "PAGE_BER64", "BER")
        erase_method = ""
        if erase:
            enable = next((b for b in erase if b in ERASE_ENABLE), "")
            if enable:
                # per-page の快速消去を持たない family（V407/X315/H417）は**ブロック消去だけ**
                # で、そこが名指すのは `BER32`。`flash_geometry.fast_erase_bytes` が空なのと
                # 同じ事実なので、そう分かる書き方にする。
                block = enable.endswith(("BER32", "BER64"))
                erase_method = f"{enable} + STRT" if "STRT" in erase else enable
                if block:
                    erase_method += " (block only; no per-page fast erase)"
        if not erase_method or "STRT" not in erase_method:
            # RM の手順が STRT を書き落としている版がある（CH32xRM の V103）。driver の
            # `FLASH_ErasePage_Fast` が実際に立てる bit で補い、basis にそう書く。
            evt_erase = (evt.get("FLASH_ErasePage_Fast")
                         or evt.get("FLASH_EraseBlock_Fast") or [])
            enable = next((b for b in evt_erase if b in ERASE_ENABLE), "")
            if enable and "STRT" in evt_erase:
                erase_method = f"{enable} + STRT"
                if "FLASH_ErasePage_Fast" not in evt:
                    erase_method += " (block only; no per-page fast erase)"
                basis.append("evt-erase")
        note = ""
        if magic:
            # CH32V103 と CH32M030 だけが持つ。XOR する値が family で違う（V103 は 0x1000、
            # M030 は 0x100）ので原文の値をそのまま書く。consumer の実測では V103 は
            # **これが無いと erase も program も無反応**だった。
            note = (f"the driver writes {magic.group(1)} after every erase and program "
                    f"(`= *(uint32_t*)((addr & ~3) ^ {magic.group(2)})`); the RM does not "
                    "mention it, and ch32rv reports that CH32V103 needs it for erase and "
                    "program to have any effect")
        rows.append({
            "family": family,
            "program_method": method,
            "program_buffer_load_bits": str(bits) if bits and "buffer writes" in method else "",
            "program_commit": commit,
            "erase_method": erase_method,
            "ctlr_bit_names": ";".join(sorted(set(ctlr_names.get(family, [])))),
            "undocumented_note": note,
            "confidence": confidence,
            "basis": "+".join(basis),
        })

    rows.sort(key=lambda r: r["family"])
    dest = paths.table("flash_program_method", args.out)
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
