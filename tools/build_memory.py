#!/usr/bin/env python3
"""FLASH/SRAM の分割が可変な part の組合せ表 → tables/memory_configs.csv

一部の part は **FLASH と SRAM の境界が用户选择字（option byte）で動く**。
`products.csv` の `flash_bytes`/`sram_bytes` は datasheet の比較表が載せる1組を
言うだけなので、「192K+128K に振り直せる」ことも「振り直したら linker script が
変わる」こともそこからは読めない。この表がその組合せを持つ（R-24追補3 の E-3）。

    CH32V307VCT6  datasheet CODE-256KB + RAM-64KB
                  ほかに 192K+128K / 224K+96K / 288K+32K / 128K+192K が選べる
    CH32V407VET6  datasheet CODE-512KB + RAM-200KB、ほかに 576K+136K

**「出荷時の組」と言えるものは無い。** RM 32.4.6 は `RAM_CODE_MOD` の復位値を
`x` と書き、「USER と RDPRT はシステムリセット後に用户选择字領域から読み込む」と
注記する。決めるのは option byte で、RM はその出荷値を書かない。EVT も決めない
——例題ごとに違う組を link している（符号表に載る組だけ数えて）:

    CH32V20x   128K+64K ×14  144K+48K ×1
    CH32V307   256K+64K ×17  192K+128K ×8  288K+32K ×2
    CH32V407   576K+136K ×7  512K+200K ×1

そこで列は「既定」と名乗らず、出所を名前にする——`datasheet_value` は
**datasheet の比較表が載せる組**（`products.csv` の `sram_bytes` に当たる行）で、
それ以上の意味は無い。consumer は決め打つのではなく、自分の linker script に
合わせて option byte を書く必要がある。

**zh と en で FLASH_OBR のフィールド幅が食い違う。** 中文版は
`RAM_CODE_MOD[2:0]` を `[9:7]`、English 版は `SRAM_CODE_MODE` を `[9:8]` と書く。
組合せが 5 通りある以上 3bit 要るので中文版が正しく、EVT header の
`FLASH_OBR_RAM_CODE_MOD ((uint16_t)0x0300)` は English 版と同じ 2bit の誤り
（`110`=128K+192K と `111`=288K+32K が区別できない）。CH32V407 も同型で、
`ch32v4x7.h` は bit9 と書くが reference manual は bit8 と書く。どちらも
`confidence: conflict` にし、`basis` に両方を残す。

書き込み先は FLASH_OBR ではなく **用户选择字の USER バイト**で、FLASH_OBR は
リセット時にそこから読み込まれた値を見せるだけ（RM 32.4.6 の注）。列は両方持つ。

    option_byte_bits  0x1FFFF800 の USER バイトの中のビット位置（書く側）
    obr_bits          FLASH_OBR の中のビット位置（読む側）

出所は3つで、それぞれ別のことを言う:

    reference manual   符号（どの値がどの組合せか）・適用 part・条件
    EVT の Link.ld     組合せの一覧（符号は無い）。RM との照合に使う
    EVT の header      FLASH_OBR のマスクと OB_RAM_CODE_MOD の値

実行:
    uv run tools/build_memory.py [--mirrors <dir>] [--out tables]
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

COLUMNS = ["part_number", "value", "code_bytes", "sram_bytes",
           "datasheet_value", "option_byte_bits", "obr_bits",
           "condition", "#", "confidence", "basis"]

# "00x：CODE-192KB + RAM-128KB" / "1：CODE-576KB + RAM-136KB"。CH32V407 は
# 1bit なので値が1文字になる。区切りは全角コロンで、English 版も全角のまま。
# 行頭とは限らない。CH32V407 の RM はフィールド名の折り返しを同じ行に混ぜて
# "RAM_CODE_M 1：CODE-576KB + RAM-136KB" と出す。
COMBINATION = re.compile(
    r"(?:^|(?<=\s))(?P<value>[01x]{1,3})\s*[：:]\s*CODE\s*[-‐–]\s*(?P<code>\d+)\s*KB"
    r"\s*\+\s*RAM\s*[-‐–]\s*(?P<sram>\d+)\s*KB")
# EVT の Link.ld のコメント: "FLASH-192K + RAM-128K"
LD_COMBINATION = re.compile(r"FLASH\s*-\s*(?P<code>\d+)K\s*\+\s*RAM\s*-\s*(?P<sram>\d+)K")
# Link.ld が実際に link する側。他の組はコメントアウトされて同じ MEMORY ブロックに
# 並んでいるので、/* */ を落としてから読む。CH32V407 は "0x20000000+1024" と
# "136K-1K" のように式で書くので、先頭の数だけ取る。
LD_ACTIVE = re.compile(
    r"^\s*(?P<what>FLASH|RAM)\s*\([rwx]+\)\s*:\s*ORIGIN\s*=[^,]+,\s*"
    r"LENGTH\s*=\s*(?P<size>\d+)\s*K", re.M)
COMMENT = re.compile(r"/\*.*?\*/", re.S)
# 適用先。part の頭（CH32V303RC）か variant macro（CH32V20x_D8W）で書かれる。
# variant macro は CH32V20x_D8W のように小文字の x を含むので、大文字だけの
# 文字クラスでは CH32V20 までしか取れず、CH32V203 全部に当たってしまう。
APPLIES = re.compile(r"CH32[A-Z]\d{2}[A-Za-z0-9]*(?:_[A-Za-z0-9]+)?")
# "（2）110b仅适用于批号倒数第六位不为0的产品。"
# "(2) The 110b applies only to products where the penultimate sixth digit ..."
CONDITION = re.compile(
    r"(?P<value>[01]{2,3})b?\s*(?:仅适用于|applies only to|only applies to)\s*(?P<text>.+)")
# 用户选择字の節に出る書き込み側の位置。"USER [7:5]"。
USER_BITS = re.compile(r"USER\s*\[(?P<hi>\d+):(?P<lo>\d+)\]")
# 適用先を絞っていると宣言する言葉。これが無い組はその manual が扱う全 part に
# 効く、というのが読み方で、CH32V407 の RM は実際に何も絞っていない。
NARROWS = ("适用于", "Applied for", "applies only to", "applied for")
# ページの柱と footer。"CH32V407应用手册 https://wch.cn" が毎ページ入るので、
# 適用先を探す前に落とさないと柱の型番を適用先と読んでしまう。
RUNNING = re.compile(r"应用手册|Reference Manual|wch\.cn|wch-ic\.com|^V\d+\.\d+\s+\d+$")

# EVT header の定義。
# USER バイトが FLASH_OBR の中で始まる位置。`FLASH_OBR_USER` は CH32V407 では
# 0x021C（bit 2,3,4,9）で連続していない——header が知っているビットの論理和に
# なっているだけ——ので使えない。IWDGSW が USER の bit0 だと用户选择字の表が
# 書いているので、`FLASH_OBR_WDG_SW` の位置がそのまま USER の起点になる。
OBR_WDG = re.compile(r"#define\s+FLASH_OBR_WDG_SW\s+\(\(u?int\d+_t\)\s*(0x[0-9A-Fa-f]+)")
OBR_FIELD = re.compile(r"#define\s+FLASH_OBR_S?RAM_CODE_MODE?\s+\(\(u?int\d+_t\)\s*(0x[0-9A-Fa-f]+)")
OB_VALUE = re.compile(r"#define\s+OB_RAM_CODE_MOD\d\s+\(\(u?int\d+_t\)\s*(0x[0-9A-Fa-f]+)")


def bit_span(mask: int) -> tuple[int, int] | None:
    """連続した1の並びなら (hi, lo)。飛んでいたら None。"""
    if not mask:
        return None
    lo = (mask & -mask).bit_length() - 1
    hi = mask.bit_length() - 1
    return (hi, lo) if mask >> lo == (1 << (hi - lo + 1)) - 1 else None


def read_manual(path: Path) -> list[dict]:
    """reference manual から組合せの組を読む。

    同じ表が2回出る（FLASH_OBR の節と用户选择字の節）。**続きの行が組に属するか
    は行の見た目では決まらない**ので、組合せ行が途切れてから次の組合せ行が来た
    ところで組を切る。間の行が適用先と条件を書いている。
    """
    groups: list[dict] = []
    current: dict | None = None
    tail: list[str] = []
    user_bits: tuple[int, int] | None = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "CODE-" not in text and "CODE -" not in text and "USER" not in text:
                continue
            for line in text.splitlines():
                line = line.strip()
                if RUNNING.search(line):
                    continue
                found = USER_BITS.search(line)
                if found and user_bits is None:
                    user_bits = (int(found.group("hi")), int(found.group("lo")))
                match = COMBINATION.search(line)
                if match:
                    # 組の切れ目は「適用先を書き終えたところ」。組合せ行の間に
                    # 別の行が挟まるのは PDF が同じセルを分けて出しているだけで、
                    # 切れ目ではない（en 版は 110 と 111 の間にフィールド名の
                    # 折り返しが入る）。
                    if current is not None and any(
                            marker in text for text in tail
                            for marker in NARROWS):
                        current["tail"] = tail
                        groups.append(current)
                        current, tail = None, []
                    if current is None:
                        current = {"page": page.page_number, "values": {}}
                    current["values"][match.group("value")] = (
                        int(match.group("code")) * 1024, int(match.group("sram")) * 1024)
                elif current is not None:
                    tail.append(line)
    if current is not None:
        current["tail"] = tail
        groups.append(current)
    for group in groups:
        text = " ".join(group.pop("tail", []))
        group["applies"] = sorted(set(APPLIES.findall(text)))
        conditions: dict[str, str] = {}
        for found in CONDITION.finditer(text):
            conditions[found.group("value")] = found.group("text").strip()
        group["conditions"] = conditions
        group["user_bits"] = user_bits
        group["narrowed"] = any(marker in text for marker in NARROWS)
    return groups


def read_header(header: Path) -> dict:
    """EVT header の FLASH_OBR まわり。RM との突き合わせに使う。"""
    text = header.read_text(errors="ignore")
    out: dict = {}
    found = OBR_WDG.search(text)
    if found:
        out["user_shift"] = int(found.group(1), 16).bit_length() - 1
    found = OBR_FIELD.search(text)
    if found:
        out["field_mask"] = int(found.group(1), 16)
    return out


def read_flash_header(paths: list[Path]) -> int | None:
    """OB_RAM_CODE_MOD0/1 の差分が、USER バイトの中で動くビット。

    CH32V407 の reference manual は用户选择字の節でビットを裸の "6" と書くので
    `USER [7:5]` の形では拾えない。EVT が両方の値を定数で持っているので、その
    排他的論理和が動くビットを言う。
    """
    values: set[int] = set()
    for path in paths:
        for found in OB_VALUE.finditer(path.read_text(errors="ignore")):
            values.add(int(found.group(1), 16))
    if len(values) < 2:
        return None
    differing = 0
    for value in values:
        differing |= value ^ min(values)
    return differing


def read_linker(family_dir: Path) -> set[tuple[int, int]]:
    """EVT の Link.ld のコメントが挙げる組合せ。RM の裏取りに使う。"""
    found: set[tuple[int, int]] = set()
    for path in family_dir.glob("EVT/**/*.ld"):
        for match in LD_COMBINATION.finditer(path.read_text(errors="ignore")):
            found.add((int(match.group("code")) * 1024, int(match.group("sram")) * 1024))
    return found


def read_linker_active(family_dir: Path) -> dict[tuple[int, int], int]:
    """EVT の各例題の Link.ld が実際に link している組と、その本数。

    「EVT の既定」と呼べる1組は**無い**。例題ごとに違う組を link していて、
    しかも大半は符号表に無い組（IAP が FLASH を切り分けた残り、BLE がスタックの
    ぶんを空けた残り）なので、符号表と突き合わせられるものだけ数える。

        CH32V20x   128K+64K ×14  144K+48K ×1
        CH32V307   256K+64K ×17  192K+128K ×8  288K+32K ×2
        CH32V407   576K+136K ×7  512K+200K ×1

    つまり consumer は「既定がこれ」と決め打つのではなく、**自分の linker script に
    合わせて option byte を書く**のが正しい。この関数の出力は notes に出すだけで、
    表の列にはしない（1組に決められないものを1列にすると嘘になる）。
    """
    found: dict[tuple[int, int], int] = {}
    for path in sorted(family_dir.glob("EVT/**/*.ld")):
        sizes = {m.group("what"): int(m.group("size")) * 1024
                 for m in LD_ACTIVE.finditer(COMMENT.sub("", path.read_text(errors="ignore")))}
        if "FLASH" in sizes and "RAM" in sizes:
            key = (sizes["FLASH"], sizes["RAM"])
            found[key] = found.get(key, 0) + 1
    return found


def expand(applies: list[str], parts: list[dict], variants: dict[str, list[str]],
           notes: list[str]) -> list[str]:
    """適用先の書き方を part_number の一覧にする。

    RM は part の頭（CH32V303RC）でも variant macro（CH32V20x_D8W）でも書く。
    CH32F は同じ silicon の ARM 版で、この repository の catalogue には無い。
    """
    out: set[str] = set()
    for name in applies:
        if name.startswith("CH32F"):
            continue
        if name in variants:
            out.update(variants[name])
            continue
        matched = [p["part_number"] for p in parts if p["part_number"].startswith(name)]
        if matched:
            out.update(matched)
        else:
            notes.append(f"適用先 {name} に当たる part が catalogue に無い")
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()

    def table(name: str) -> list[dict]:
        return paths.load(name.removesuffix(".csv"))

    families = table("families.csv")
    parts = table("products.csv")
    variants: dict[str, list[str]] = {}
    for row in table("evt_variants.csv"):
        variants.setdefault(row["macro"], []).append(row["part_number"])

    notes: list[str] = []
    # 走査するのは「EVT header が RAM_CODE_MOD を定義している family の RM」だけ。
    # CH32V20x の header には無いが、その parts は CH32V307 と同じ RM に載る。
    headers: dict[str, dict] = {}
    manuals: dict[str, list[str]] = {}
    for family in families:
        name = family["family"]
        found = sorted((args.mirrors / name).glob("EVT/**/inc/ch32*.h"))
        base = [p for p in found if re.fullmatch(r"ch32[a-zA-Z0-9]+\.h", p.name)]
        if not base:
            continue
        info = read_header(base[0])
        if "field_mask" not in info:
            continue
        info["ob_mask"] = read_flash_header([p for p in found if p.name.endswith("_flash.h")])
        headers[name] = info
        for document in family["reference_manuals"].split(";"):
            if document:
                manuals.setdefault(document, []).append(name)

    # Link.ld の組合せはどの family のものでも裏取りになる。CH32V20x の parts は
    # CH32V307 と同じ RM に載るが、組合せを書いた Link.ld は CH32V20x の側にある。
    ld: set[tuple[int, int]] = set()
    active: dict[str, dict[tuple[int, int], int]] = {}
    for owner in families:
        ld |= read_linker(args.mirrors / owner["family"])
        used = read_linker_active(args.mirrors / owner["family"])
        if used:
            active[owner["family"]] = used
    by_part = {p["part_number"]: p for p in parts}

    rows: list[dict] = []
    for document, owners in sorted(manuals.items()):
        family = owners[0]
        readings: dict[str, list[dict]] = {}
        for lang in ("zh", "en"):
            path = args.mirrors / family / f"datasheet_{lang}" / document
            if path.exists():
                readings[lang] = read_manual(path)
        if not readings:
            notes.append(f"{document}: 読める版が無い")
            continue
        # 同じ組が2つの節に出る（FLASH_OBR の節と用户选择字の節）。**畳む鍵は
        # 値の集合ではなく適用先**で、節によって版によって符号行が1つ欠けること
        # があり、値で畳むと同じ組が二重に出る。適用先は両方の節で同じ。
        merged: dict[frozenset, dict] = {}
        for lang, groups in readings.items():
            for group in groups:
                key = frozenset(group["applies"])
                entry = merged.setdefault(key, {"values": {}, "applies": set(),
                                                "conditions": {}, "langs": set(),
                                                "user_bits": None, "page": {},
                                                "narrowed": False})
                entry["narrowed"] |= group["narrowed"]
                for value, pair in group["values"].items():
                    seen = entry["values"].setdefault(value, pair)
                    if seen != pair:
                        notes.append(f"{document}: 符号 {value} の組合せが節によって違う "
                                     f"({seen} と {pair})")
                entry["applies"].update(group["applies"])
                entry["conditions"].update(group["conditions"])
                entry["langs"].add(lang)
                entry["page"].setdefault(lang, group["page"])
                entry["user_bits"] = entry["user_bits"] or group["user_bits"]

        info = headers.get(family, {})
        field_span = bit_span(info.get("field_mask", 0))
        user_shift = info.get("user_shift")
        ob_span = bit_span(info.get("ob_mask") or 0)

        for key, entry in merged.items():
            combinations = set(entry["values"].values())
            missing = combinations - ld
            if ld and missing:
                notes.append(f"{family}: Link.ld が挙げない組合せが RM にある: "
                             + ", ".join(f"{c // 1024}K+{s // 1024}K" for c, s in sorted(missing)))
            # 必要なビット幅。`1xx` は下2桁が何でもよいという意味なので、
            # 桁数ではなく **x でない一番下の桁まで** を数える。CH32V20x の
            # 00x/01x/1xx は 2bit で足り、CH32V30x の 110/111 は 3bit 要る。
            width = max(len(v.rstrip("x")) for v in entry["values"])
            # 書く側。RM が USER [hi:lo] と書いていればそれ、CH32V407 のように
            # 裸のビット番号で書いていたら EVT の OB_RAM_CODE_MOD の差分で補う。
            option = entry["user_bits"] or ob_span
            option_bits = f"[{option[0]}:{option[1]}]" if option else ""
            # 読む側。FLASH_OBR の中で USER バイトが占める位置ぶんだけずれる。
            obr_bits = ""
            if option and user_shift is not None:
                obr_bits = (f"[{option[0] + user_shift}:"
                            f"{option[1] + user_shift}]")
            confidence = "confirmed" if len(entry["langs"]) > 1 else "reference"
            basis = [f"rm({document}:{lang}(p.{page}))"
                     for lang, page in sorted(entry["page"].items())]
            if field_span:
                stated = field_span[0] - field_span[1] + 1
                if stated != width:
                    confidence = "conflict"
                    notes.append(
                        f"{family}: EVT header の FLASH_OBR フィールドは "
                        f"[{field_span[0]}:{field_span[1]}]（{stated}bit）だが、"
                        f"RM の符号は {width}bit 要る（{width}bit 無いと "
                        + " と ".join(sorted(v for v in entry["values"] if "x" not in v))
                        + " が区別できない）")
                elif obr_bits and obr_bits != f"[{field_span[0]}:{field_span[1]}]":
                    confidence = "conflict"
                    notes.append(
                        f"{family}: EVT header の FLASH_OBR フィールドは "
                        f"[{field_span[0]}:{field_span[1]}] だが、RM は {obr_bits} と書く")
                basis.append(f"evt({family})")
            if ld:
                basis.append("evt(Link.ld)")

            # 適用先を絞る文が無ければ、その manual が扱う family 全体に効く。
            # CH32V407 の RM はフィールドの説明に適用先を書かないが、それは
            # 「限定が無い」という意味で、読めなかったという意味ではない。
            if entry["narrowed"]:
                targets = expand(sorted(entry["applies"]), parts, variants, notes)
            else:
                covered = set(owners)
                targets = sorted(p["part_number"] for p in parts
                                 if p["family"] in covered)
            if not targets:
                notes.append(f"{family}: 適用先を決められない組がある "
                             f"({', '.join(sorted(entry['applies'])) or '記載なし'})")
                continue
            for part in targets:
                product = by_part[part]
                default_ram = int(product["sram_bytes"] or 0)
                for value, (code, sram) in sorted(entry["values"].items()):
                    rows.append({
                        "part_number": part,
                        "value": value,
                        "code_bytes": code,
                        "sram_bytes": sram,
                        "datasheet_value": "1" if sram and sram == default_ram else "",
                        "option_byte_bits": option_bits,
                        "obr_bits": obr_bits,
                        "condition": entry["conditions"].get(value, ""),
                        "confidence": confidence,
                        "basis": "+".join(basis),
                    })

    for part in {r["part_number"] for r in rows}:
        mine = [r for r in rows if r["part_number"] == part]
        if not any(r["datasheet_value"] for r in mine):
            notes.append(f"{part}: products.csv の sram_bytes に当たる組合せが無い")
    # 「EVT の既定」は無い、を数で残す。符号表に載る組だけ数える。
    for family, used in sorted(active.items()):
        valid = {(r["code_bytes"], r["sram_bytes"]) for r in rows
                 if by_part[r["part_number"]]["family"] == family}
        counted = sorted(((k, n) for k, n in used.items() if k in valid),
                         key=lambda kv: -kv[1])
        if counted:
            notes.append(f"{family}: EVT の Link.ld が link している組 "
                         + "  ".join(f"{c // 1024}K+{s // 1024}K ×{n}"
                                     for (c, s), n in counted))

    rows.sort(key=lambda r: (r["part_number"], r["value"]))
    dest = paths.table("memory_configs", args.out)
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    print(f"{dest}: {len(rows)} 行  "
          f"part {len({r['part_number'] for r in rows})}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
