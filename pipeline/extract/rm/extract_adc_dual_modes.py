#!/usr/bin/env python3
"""ADC のデュアルモード（DUALMOD の各値が何を選ぶか）→ index/adc_dual_modes.csv

ADC1 と ADC2 を組にして同時・交互に変換するモードは `ADC_CTLR1` の `DUALMOD[3:0]`（`[19:16]`）
で選ぶ（ADC2 では保留の bit）。値ごとの意味を書くのは EVT の ADC ヘッダ（`ADC_Mode_*`）と RM の
field の説明（`0000：独立模式 0001：同步规则+同步注入模式 …`）。consumer（ch32rv のコア）は ADC の
デュアルモードに使う（2026-11-19 の依頼）。

1行は family × 値。`mode` は値の意味を英語の記号で、RM の説明の並びのまま `+` でつなぐ:
`independent`・`regular_simultaneous`・`injected_simultaneous`・`fast_interleaved`・
`slow_interleaved`・`alternate_trigger`（`0001` は `regular_simultaneous+injected_simultaneous`）。

**対象は DUALMOD の field を持つ family**（`register_fields` の EVT の device ヘッダ由来の行。H417・
V103・V20x・V307・V407・X315）。L103・V205 などの ADC ヘッダも `ADC_Mode_*` を10個並べるが、
device ヘッダに DUALMOD が無い（ADC が1つ）ので行を持たない——ヘッダの定義だけでは作らない。

EVT の定義と RM（zh・en のどちらか）が同じ意味を言えば confirmed、RM が別の意味を言えば conflict、
RM がその値を書かなければ reference。RM の説明はページをまたぐことが多い（H417 は 0100 まで
が前のページ）ので、`register_fields.extract` が続きの断片をつないだ説明を読む。

実行:
    uv run pipeline/extract/rm/extract_adc_dual_modes.py [--out <dir>]
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

COLUMNS = ["family", "register", "field", "bits", "value", "mode", "define", "confidence", "basis"]
DEFINE = re.compile(r"^\s*#define\s+(?P<name>ADC_Mode_\w+)\s+"
                    r"\(\s*\(\s*uint32_t\s*\)\s*(?P<mask>0[xX][0-9A-Fa-f]+)\s*\)")

# EVT の名前の部品 → 記号。
HEADER_PARTS = {"Independent": "independent", "RegSimult": "regular_simultaneous",
                "InjecSimult": "injected_simultaneous", "FastInterl": "fast_interleaved",
                "SlowInterl": "slow_interleaved", "AlterTrig": "alternate_trigger"}


def header_mode(suffix: str) -> str:
    """`RegInjecSimult` → regular_simultaneous+injected_simultaneous、`InjecSimult_FastInterl` → …

    >>> [header_mode(s) for s in ("Independent", "RegInjecSimult", "RegSimult_AlterTrig",
    ...                           "InjecSimult_FastInterl", "SlowInterl", "AlterTrig")]
    ['independent', 'regular_simultaneous+injected_simultaneous', 'regular_simultaneous+alternate_trigger', 'injected_simultaneous+fast_interleaved', 'slow_interleaved', 'alternate_trigger']
    """
    if suffix == "RegInjecSimult":
        return "regular_simultaneous+injected_simultaneous"
    return "+".join(HEADER_PARTS.get(p, p) for p in suffix.split("_"))


def rm_part(text: str) -> str:
    """RM の説明の1つの部品 → 記号。読めなければ空。

    >>> [rm_part(t) for t in ("独立模式", "同步规则", "混合的同步规则", "注入同步模式", "快速交替模式",
    ...                       "快速交叉模式", "慢速交替模式", "交替触发模式", "Independent mode",
    ...                       "Synchronous regulars", "Synchronization rules", "Rule synchronization mode",
    ...                       "synchronous injection mode", "rapid alternating mode", "Fast crossover mode",
    ...                       "Slow alternating mode", "Alternate trigger mode", "Alternating trigger mode")]
    ['independent', 'regular_simultaneous', 'regular_simultaneous', 'injected_simultaneous', 'fast_interleaved', 'fast_interleaved', 'slow_interleaved', 'alternate_trigger', 'independent', 'regular_simultaneous', 'regular_simultaneous', 'regular_simultaneous', 'injected_simultaneous', 'fast_interleaved', 'fast_interleaved', 'slow_interleaved', 'alternate_trigger', 'alternate_trigger']
    """
    t = text.lower()
    if "独立" in t or "independent" in t:
        return "independent"
    if "触发" in t or "trigger" in t:
        return "alternate_trigger"
    if re.search(r"快速|fast|rapid", t):
        return "fast_interleaved"
    if re.search(r"慢速|slow", t):
        return "slow_interleaved"
    if re.search(r"规则|regular|rule", t):
        return "regular_simultaneous"
    if re.search(r"注入|inject", t):
        return "injected_simultaneous"
    return ""


def rm_values(description: str) -> dict[int, str]:
    """`0000：独立模式 0001：同步规则+同步注入模式 …` → {0: independent, 1: …}。

    区切りの `；` を欠く版がある（CH32FV2x_V3xRM zh）ので、次の値の符号までを1つの値の説明にする。

    >>> rm_values("0000：独立模式 0001：同步规则+同步注入模式 1001：交替触发模式 注：ADC2中这些位为保留位")
    {0: 'independent', 1: 'regular_simultaneous+injected_simultaneous', 9: 'alternate_trigger'}
    """
    marks = list(re.finditer(r"(?<![0-9A-Za-z])([01]{4})\s*[：:]", description))
    found: dict[int, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(description)
        text = re.split(r"注[：:]|Note\s*:|[。.]\s*$|；|;", description[m.end():end])[0]
        parts = [rm_part(p) for p in re.split(r"[+＋]", text)]
        if parts and all(parts):
            found.setdefault(int(m.group(1), 2), "+".join(parts))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先のディレクトリ（試験用）")
    args = ap.parse_args()

    rms = manuals()
    fields_of = header_fields()
    rows = []
    for header in sorted(MIRRORS.glob("CH32*/EVT/EXAM/SRC/Peripheral/inc/*_adc.h")):
        family = header.parents[5].name
        offset, width = fields_of.get(family, {}).get("ADC_CTLR1.DUALMOD", (None, None))
        if offset is None:
            continue
        manual = rms.get(family)
        described: dict[str, tuple[dict[int, str], int | None]] = {}
        for lang in ("zh", "en"):
            if not manual:
                break
            try:
                found, _ = rm_fields.extract(f"{manual}.{lang}", None)
            except SystemExit:
                continue
            for f in found:
                if f["field"] == "DUALMOD" and f["register"].endswith("CTLR1"):
                    described.setdefault(lang, (rm_values(f["description"] or ""), f.get("page")))
        defines: dict[int, list[str]] = collections.defaultdict(list)
        for line in header.read_text(encoding="utf-8", errors="replace").splitlines():
            m = DEFINE.match(line)
            if not m:
                continue
            mask = int(m.group("mask"), 16)
            if mask & ~(((1 << width) - 1) << offset):
                print(f"{family}: {m.group('name')} は DUALMOD の外の bit を持つので読まない", file=sys.stderr)
                continue
            defines[mask >> offset].append(m.group("name"))
        bits = f"{offset + width - 1}:{offset}"
        for value, names in sorted(defines.items()):
            mode = header_mode(names[0][len("ADC_Mode_"):])
            said = {lang: (v[value], page) for lang, (v, page) in described.items() if value in v}
            basis = f"evt({header.name})"
            agree = [lang for lang in ("zh", "en") if lang in said and said[lang][0] == mode]
            differ = [lang for lang in ("zh", "en") if lang in said and said[lang][0] != mode]
            for lang in agree:
                basis += f"+rm:{manual}.PDF:{lang}(p.{said[lang][1]})"
            for lang in differ:
                basis += f"+!rm:{manual}.PDF:{lang}(p.{said[lang][1]})(mode={said[lang][0]})"
            rows.append({"family": family, "register": "ADC_CTLR1", "field": "DUALMOD", "bits": bits,
                         "value": value, "mode": mode, "define": ";".join(names),
                         "confidence": "conflict" if differ else "confirmed" if agree else "reference",
                         "basis": basis})
    dest = paths.table("adc_dual_modes", args.out)
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
