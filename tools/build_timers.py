#!/usr/bin/env python3
"""タイマ1つずつの素性 → tables/timers.csv

**「このタイマのカウンタは何ビットか」が機械可読でありませんでした。** 比較表は
`Timer General-purpose TIM4 (32-bit)` のような**文**を series 粒度で持つだけで、
綴りも `ADTM` / `GPTM` / `高级定时器` と family ごとに揺れます。consumer 側は
32bit のタイマ一覧を手書きするしかなく、そこが間違うと `tone()` のような周期の
計算が静かにずれます。

**RM の register 見出しが対象タイマを名指ししています。**

    14.4.10 高级定时器的计数器（TIMx_CNT）（x=1/8/9/10）
            [15:0] CNT[15:0] RW 定时器的计数器的实时值。 0
    15.4.11 通用定时器的计数器（TIMx_CNT）（x=5）
            [31:0] CNT[31:0] RW 定时器的计数器的实时值。 0
    注：32位的TIM5_CNT仅适用于型号为CH32V20x_D8、CH32V20x_D8W系列的产品，
        其他系列芯片的TIM5_CNT为16位。

見出しが**種類**（高级/通用/基本）と**どのタイマか**（x=…）を、直後の field 表が
**幅**を言います。注が付くものは variant によって幅が変わるので、`condition` に
EVT の variant macro を置きます（`interrupts.csv` と同じ持ち方）。

チャネル数と相補出力の有無は pin 側から数えます——`pin_roles.csv` の
`(TIMn, CHm)` と `(TIMn, CHmN)`。**pinout 単位の下限**であって silicon の上限では
ないので、`channels` は「pin に出ている最大のチャネル番号」です。

実行:
    uv run tools/build_timers.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "timer", "kind", "counter_width_bits", "channels",
           "complementary", "update_vector", "condition",
           "#", "confidence", "basis"]

# `15.4.10 通用定时器的计数器（TIMx_CNT）（x=2/3/4）` と、単体の
# `14.4.9 定时器的计数器（TIM1_CNT）`。前者は対象を x= で並べ、後者は名前が名乗る。
HEAD_GROUP = re.compile(
    r"^\d+(?:\.\d+)+\s*(?P<kind>\S*?定时器).*?TIMx_CNT\s*[)）]?\s*[（(]\s*x\s*=\s*"
    r"(?P<list>[\d/,\s]+)[)）]")
HEAD_ONE = re.compile(
    r"^\d+(?:\.\d+)+\s*(?P<kind>\S*?定时器).*?TIM(?P<n>\d+)_CNT\s*[)）]")
# 直後の field 表の CNT 行。`[31:0] CNT[31:0]` / `[15:0] CNT[15:0]`。
WIDTH = re.compile(r"\[(?P<hi>\d+):0\]\s*CNT")
# 幅が variant で変わるという注。`32位的TIM5_CNT仅适用于型号为…系列的产品`
VARIES = re.compile(r"(?P<bits>\d+)位的TIM(?P<n>\d+)_CNT")
MACRO = re.compile(r"CH32[A-Za-z0-9_]+")
# 見出しの種類。資料の言い方をそのまま英語の呼び名へ。
KINDS = {"高级定时器": "advanced", "通用定时器": "general-purpose",
         "基本定时器": "basic", "低功耗定时器": "low-power"}
# 見出しから幅の行までの距離。表は見出しのすぐ下にある。
LOOKAHEAD = 25


def read_timers(path: Path) -> tuple[list[dict], list[str]]:
    """RM から (timer, kind, width, condition の素材) を読む。"""
    found: dict[int, dict] = {}
    notes: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            for i, line in enumerate(lines):
                text = line.strip()
                group = HEAD_GROUP.match(text)
                single = None if group else HEAD_ONE.match(text)
                if not group and not single:
                    continue
                width = None
                for step, after in enumerate(lines[i:i + LOOKAHEAD]):
                    # **次の見出しを跨がない。** 同じページに2つ並ぶことがあり
                    # （CH32H417 の 15.4.10 は 16bit、15.4.11 は 32bit）、跨ぐと
                    # 隣の幅を静かに拾う。
                    if step and (HEAD_GROUP.match(after.strip())
                                 or HEAD_ONE.match(after.strip())):
                        break
                    hit = WIDTH.search(after)
                    if hit:
                        width = int(hit.group("hi")) + 1
                        break
                if width is None:
                    notes.append(f"{text[:40]}: 見出しはあるが CNT の幅が読めない")
                    continue
                kind = KINDS.get((group or single).group("kind"), "")
                numbers = ([int(n) for n in re.findall(r"\d+", group.group("list"))]
                           if group else [int(single.group("n"))])
                for n in numbers:
                    # **同じタイマが2度出たら広いほうを採らない。** 章が分かれて
                    # いる以上どちらも本文で、どちらが効くかは注が決める。
                    if n in found and found[n]["counter_width_bits"] != width:
                        notes.append(f"TIM{n}: 幅が2通り出た "
                                     f"({found[n]['counter_width_bits']} と {width})")
                    found.setdefault(n, {"timer": f"TIM{n}", "kind": kind,
                                         "counter_width_bits": width,
                                         "page": page.page_number})
            # variant で幅が変わる注。
            for line in lines:
                varies = VARIES.search(line)
                if varies:
                    n = int(varies.group("n"))
                    if n in found:
                        found[n]["_varies"] = (int(varies.group("bits")),
                                               MACRO.findall(line))
            page.close()
    return [found[n] for n in sorted(found)], notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    def load(name: str) -> list[dict]:
        with (args.out / f"{name}.csv").open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    families = [r["family"] for r in load("families")]
    variants = {(r["family"], r["macro"]) for r in load("evt_variants")
                if "macro" in r}
    # **更新割り込みは `TIMn_UP`。** 高級タイマはベクタが4本に割れていて
    # （`TIMn_BRK` / `TIMn_UP` / `TIMn_TRG_COM` / `TIMn_CC`）、表の並び順で
    # 最初に当たるのは `BRK` なので、名前で選ばないと**中断入力のベクタを
    # 更新割り込みとして渡してしまいます**。ベクタが1本のタイマは `TIMn`。
    by_timer: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for row in load("interrupts"):
        hit = re.match(r"^(TIM\d+)(?:_|$)", row["name"])
        if hit:
            by_timer[(row["family"], hit.group(1))].add(row["name"])
    irq_of: dict[tuple[str, str], str] = {}
    for key, found in by_timer.items():
        exact = f"{key[1]}_UP"
        irq_of[key] = (exact if exact in found else
                       key[1] if key[1] in found else
                       sorted(found)[0] if found else "")
    channels: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for row in load("pin_roles"):
        if row["peripheral"].startswith("TIM") and row["role"].startswith("CH"):
            channels[(row["family"], row["peripheral"])].add(row["role"])

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        manual = next((p for p in sorted((args.mirrors / family / "datasheet_zh").glob("*RM.PDF"))), None)
        if manual is None:
            notes.append(f"{family}: reference manual が無い")
            continue
        found, said = read_timers(manual)
        notes += [f"{family}: {n}" for n in said]
        if not found:
            notes.append(f"{family}: タイマの計数器の見出しを1つも読めない")
        for timer in found:
            seen = channels.get((family, timer["timer"]), set())
            plain = {c for c in seen if not c.endswith("N")}
            varies = timer.get("_varies")
            # **注が名指しする variant をこの family が持たないなら、その幅は
            # ここには適用されない。** CH32V20x と CH32V30x は RM を共有していて、
            # 注は「32位の TIM5_CNT は CH32V20x_D8/D8W にだけ、他は16位」と書く。
            # CH32V307 の側で 32bit と言い切ると嘘になるので conflict にする。
            applies = [m for m in (varies[1] if varies else []) if (family, m) in variants]
            if varies and not applies:
                notes.append(f"{family} {timer['timer']}: RMの注が名指しする variant を"
                             f"この family は持たない（{varies[1]}）。幅は"
                             f"{timer['counter_width_bits']}bitと読めるが適用外の可能性")
            rows.append({
                "family": family,
                "timer": timer["timer"],
                "kind": timer["kind"],
                "counter_width_bits": timer["counter_width_bits"],
                # **pin に出ている最大のチャネル番号**で、silicon の上限ではない。
                "channels": max((int(re.sub(r"\D", "", c) or 0) for c in plain),
                                default=""),
                "complementary": "1" if any(c.endswith("N") for c in seen) else "",
                "update_vector": irq_of.get((family, timer["timer"]), ""),
                # 幅が variant で変わるなら、その variant を条件に置く。
                "condition": ";".join(applies),
                "confidence": ("varies-by-package" if applies else
                               "conflict" if varies else "reference"),
                "basis": f"rm({manual.name}:p{timer['page']})",
            })

    dest = args.out / "timers.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    wide = sum(1 for r in rows if r["counter_width_bits"] == 32)
    print(f"{dest}: {len(rows)} 行  family {len({r['family'] for r in rows})}"
          f"  32bit {wide}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
