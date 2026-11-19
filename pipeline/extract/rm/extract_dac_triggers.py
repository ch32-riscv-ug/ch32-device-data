#!/usr/bin/env python3
"""DAC の外部トリガ（TSEL1 / TSEL2 の各値が何を選ぶか）→ index/dac_triggers.csv

DAC は `DAC_CTLR` の `TENx`（トリガを使う）を 1 にしたとき、`TSELx`（3 bit）で変換を始める事象を
選ぶ（ch1 は `[5:3]`、ch2 は `[21:19]`）。値ごとに何が選ばれるか（タイマの TRGO・EXTI の線・
ソフトウェア）を書くのは EVT の DAC ヘッダと RM の field の説明。consumer（ch32rv のコア）は DAC の
DMA 波形・三角波・ノイズ・2 ch の同時更新に使う（2026-11-19 の依頼）。

**出所は2つ。**

    EVT の DAC ヘッダ   `#define DAC_Trigger_T6_TRGO ((uint32_t)0x00000004)`
                        mask は ch1 の位置で、`TEN1`（bit 2）を含む。値は mask を `TSEL1` の位置
                        （`register_fields` の bits）で割る。`DAC_Trigger_None`（=0、TEN を 0 に
                        する）は TSEL の値ではないので行を持たない
    RM の field の説明  `000：TIM6 TRGO事件； 001：TIM8 TRGO事件； … 111：软件触发；`（zh・en）

列は `adc_triggers` と同じ（consumer が同じ読み方で読めるように）。`group` は `dac`、`remap_field`・
`remap_value` は空（DAC のトリガを remap で切り替える bit は無い）。EVT の定義は ch1 の位置だけを
書き、ch2 は SPL が 16 bit ずらして使う（`DAC_Init`）——`TSEL2` の行も同じ定義を `define` に書く。
EVT と RM（zh・en のどちらか）が同じ事象を言えば confirmed、RM が別の事象を言えば conflict、RM が
読めなければ reference。

**対象は DAC を持つ family。** EVT が DAC ヘッダを持つ family（H417・V307・V407。datasheet の
capabilities も DAC を言う）。V103 の RM（CH32xRM）と device ヘッダは DAC の register を書くが、
datasheet は DAC を持たないと言い（capabilities に無い）、EVT に DAC のドライバも無いので対象に
しない。

実行:
    uv run pipeline/extract/rm/extract_dac_triggers.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MIRRORS = REPO.parent
sys.path.insert(0, str(REPO / "pipeline" / "common"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))
sys.path.insert(0, str(REPO / "pipeline" / "extract" / "rm"))

import paths  # noqa: E402
import register_fields as rm_fields  # noqa: E402
from extract_adc_triggers import header_fields, manuals  # noqa: E402

# adc_triggers と同じ列（check_tables はリテラルの並びを読む）。
COLUMNS = ["family", "group", "register", "field", "bits", "value", "trigger", "kind",
           "remap_field", "remap_value", "define", "confidence", "basis"]

FIELDS = ("TSEL1", "TSEL2")
DEFINE = re.compile(r"^\s*#define\s+(?P<name>DAC_Trigger_\w+)\s+"
                    r"\(\s*\(\s*uint32_t\s*\)\s*(?P<mask>0[xX][0-9A-Fa-f]+)\s*\)")


def header_token(suffix: str) -> str:
    """`T6_TRGO` → TIM6_TRGO、`Ext_IT9` → EXTI9、`Software` → SWTRIG。

    >>> [header_token(s) for s in ("T6_TRGO", "T8_TRGO", "Ext_IT9", "Software")]
    ['TIM6_TRGO', 'TIM8_TRGO', 'EXTI9', 'SWTRIG']
    """
    m = re.fullmatch(r"T(?:IM)?(\d+)_TRGO", suffix)
    if m:
        return f"TIM{m.group(1)}_TRGO"
    m = re.fullmatch(r"Ext_IT(\d+)", suffix)
    if m:
        return f"EXTI{m.group(1)}"
    if suffix == "Software":
        return "SWTRIG"
    return suffix


def rm_token(text: str) -> str:
    """RM の説明の1項目 → 事象。読めなければ空。

    >>> [rm_token(t) for t in ("TIM6 TRGO事件", "TRGO event of TIM3", "TIM8 TRGO event",
    ...                        "外部中断线9", "External interrupt line 9", "软件触发", "Software trigger", "保留")]
    ['TIM6_TRGO', 'TIM3_TRGO', 'TIM8_TRGO', 'EXTI9', 'EXTI9', 'SWTRIG', 'SWTRIG', '']
    """
    m = (re.search(r"TIM\s*(\d+)\s*(?:的)?\s*TRGO", text, re.IGNORECASE)
         or re.search(r"TRGO\s+event\s+of\s+(?:the\s+)?TIM\s*(\d+)", text, re.IGNORECASE))
    if m:
        return f"TIM{m.group(1)}_TRGO"
    m = re.search(r"(?:外部中断线|EXTI\s*(?:线|line)?|external\s+interrupt\s+line)\s*(\d+)", text, re.IGNORECASE)
    if m:
        return f"EXTI{m.group(1)}"
    if re.search(r"软件触发|software\s+trigger", text, re.IGNORECASE):
        return "SWTRIG"
    return ""


def rm_values(description: str) -> dict[int, str]:
    """`000：TIM6 TRGO事件； 001：… 111：软件触发；` → {0: TIM6_TRGO, …}。

    区切りの `；` を欠く版がある（`010：TIM7 TRGO事件 011：TIM5 TRGO事件`）ので、次の値の符号
    までを1つの値の説明にする。

    >>> rm_values("000：TIM6 TRGO事件； 010：TIM7 TRGO事件 011：TIM5 TRGO事件 111：软件触发； 其他：保留。")
    {0: 'TIM6_TRGO', 2: 'TIM7_TRGO', 3: 'TIM5_TRGO', 7: 'SWTRIG'}
    """
    marks = list(re.finditer(r"(?<![0-9A-Za-z])([01]{3})\s*[：:]", description))
    found: dict[int, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(description)
        token = rm_token(re.split(r"其他|其它|Others?\b", description[m.end():end])[0])
        if token:
            found.setdefault(int(m.group(1), 2), token)
    return found


def kind_of(token: str) -> str:
    return "timer" if token.startswith("TIM") else "exti" if token.startswith("EXTI") else "software"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先のディレクトリ（試験用）")
    args = ap.parse_args()

    rms = manuals()
    fields_of = header_fields()
    rows = []
    for header in sorted(MIRRORS.glob("CH32*/EVT/EXAM/SRC/Peripheral/inc/*_dac.h")):
        family = header.parents[5].name
        fields = fields_of.get(family, {})
        manual = rms.get(family)
        described: dict[tuple[str, str], tuple[dict[int, str], int | None]] = {}
        for lang in ("zh", "en"):
            if not manual:
                break
            try:
                found, _ = rm_fields.extract(f"{manual}.{lang}", None)
            except SystemExit:
                continue
            for f in found:
                if f["field"] in FIELDS and f["register"].endswith("DAC_CTLR"):
                    described.setdefault((f["field"], lang), (rm_values(f["description"] or ""), f.get("page")))
        defines: dict[int, list[str]] = collections.defaultdict(list)
        offset1, width1 = fields.get("DAC_CTLR.TSEL1", (None, None))
        if offset1 is None:
            print(f"{family}: DAC_CTLR.TSEL1 の位置が分からない", file=sys.stderr)
            continue
        for line in header.read_text(encoding="utf-8", errors="replace").splitlines():
            m = DEFINE.match(line)
            if not m or m.group("name") == "DAC_Trigger_None":
                continue
            mask = int(m.group("mask"), 16)
            # TEN1（bit 2）以外に TSEL1 の外の bit を持つ定義は読まない。
            if mask & ~((((1 << width1) - 1) << offset1) | (1 << 2)):
                print(f"{family}: {m.group('name')} は TSEL1 の外の bit を持つので読まない", file=sys.stderr)
                continue
            defines[(mask >> offset1) & ((1 << width1) - 1)].append(m.group("name"))
        for field in FIELDS:
            offset, width = fields.get(f"DAC_CTLR.{field}", (None, None))
            if offset is None:
                print(f"{family}: DAC_CTLR.{field} の位置が分からない", file=sys.stderr)
                continue
            bits = f"{offset + width - 1}:{offset}"
            for value, names in sorted(defines.items()):
                token = header_token(names[0][len("DAC_Trigger_"):])
                said = {lang: (v[value], page) for (f, lang), (v, page) in described.items()
                        if f == field and value in v}
                basis = f"evt({header.name})"
                agree = [lang for lang in ("zh", "en") if lang in said and said[lang][0] == token]
                for lang in agree:
                    basis += f"+rm:{manual}.PDF:{lang}(p.{said[lang][1]})"
                differ = [lang for lang in ("zh", "en") if lang in said and said[lang][0] != token]
                for lang in differ:
                    basis += f"+!rm:{manual}.PDF:{lang}(p.{said[lang][1]})(trigger={said[lang][0]})"
                rows.append({
                    "family": family, "group": "dac", "register": "DAC_CTLR", "field": field,
                    "bits": bits, "value": value, "trigger": token, "kind": kind_of(token),
                    "remap_field": "", "remap_value": "", "define": ";".join(names),
                    "confidence": "conflict" if differ else "confirmed" if agree else "reference",
                    "basis": basis,
                })
    dest = paths.table("dac_triggers", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    shown = dest.relative_to(REPO) if dest.is_relative_to(REPO) else dest
    print(f"{shown}: {len(rows)} 行", dict(collections.Counter(r["confidence"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
