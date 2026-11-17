#!/usr/bin/env python3
"""ADC の外部トリガ（EXTSEL / JEXTSEL の各値が何を選ぶか）→ index/adc_triggers.csv

ADC は `ADC_CTLR2` の `EXTSEL`（規則チャネル）と `JEXTSEL`（注入チャネル）で変換を始める
事象を選ぶ。値ごとに何が選ばれるか（タイマのイベント・EXTI の線・外部の端子・ソフトウェア）は
family で違い、M030 は 4 bit（`CTLR2[19:16]`・`[14:11]`）で並びも違う。consumer（ch32rv の
コア）は EVT の `ADC_ExternalTrigConv_*` を読んで手で書いていた（2026-11-17 の依頼）。

**出所は2つ。**

    EVT の ADC ヘッダ   `#define ADC_ExternalTrigConv_T1_CC1 ((uint32_t)0x00000000)`
                        値は mask を field の位置（`register_fields` の `EXTSEL` の bits）で割る
    RM の field の説明  `000：定时器1的CC1事件；001：…；111：SWSTART软件触发。`（zh・en）

両方が同じ事象を言えば confirmed、RM が別の事象を言えば conflict（basis に `!rm(...)`）、
RM の説明が読めなければ reference。RM の説明が表に切れて値を書かない版がある
（CH32FV2x_V3xRM の en 版 EXTSEL は見出しの1行だけ）ので、zh・en のどちらかで照合する。

**1つの値に候補が2つ並ぶことがある**——`Ext_IT11_TIM8_TRGO`（EXTI11 か TIM8 の TRGO）、
`Ext_PD3_PC2`（PD3 か PC2）。どちらになるかは AFIO の remap の bit が決める
（`AFIO_PCFR1.ADC1_ETRGREG_REMAP`。RM: 「0：…与EXTI11相连；1：…与TIM8_TRGO相连」「0：…与PD3相连；
1：…与PC2相连」）。候補の並びは remap の値の順（0 が先）。この family の header がその remap の
bit を持てば、**remap の field と値ごとに1行**にし、`trigger` には1つだけ書く（ADC1 と ADC2 で
別の bit を持つ family は、それぞれの bit で行が分かれる）。bit を持たなければ候補を `;` で並べて
1行にする。

実行:
    uv run pipeline/extract/rm/extract_adc_triggers.py [--out <dir>]
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

COLUMNS = ["family", "group", "register", "field", "bits", "value", "trigger", "kind",
           "remap_field", "remap_value", "define", "confidence", "basis"]

GROUPS = {"regular": ("EXTSEL", "ADC_ExternalTrigConv_", "SWSTART"),
          "injected": ("JEXTSEL", "ADC_ExternalTrigInjecConv_", "JSWSTART")}
DEFINE = re.compile(r"^\s*#define\s+(?P<name>ADC_ExternalTrig(?:Injec)?Conv_\w+)\s+"
                    r"\(\s*\(\s*uint32_t\s*\)\s*(?P<mask>0[xX][0-9A-Fa-f]+)\s*\)")
PAD = re.compile(r"^P[A-F]\d+$")


def header_tokens(suffix: str, software: str) -> list[str]:
    """`T1_CC4_CC5` → [TIM1_CC4, TIM1_CC5]、`Ext_IT11_TIM8_TRGO` → [EXTI11, TIM8_TRGO]。

    >>> header_tokens("T1_CC1", "SWSTART"), header_tokens("Ext_IT11_TIM8_TRGO", "SWSTART")
    (['TIM1_CC1'], ['EXTI11', 'TIM8_TRGO'])
    >>> header_tokens("T1_CC4_CC5", "SWSTART"), header_tokens("Ext_PD3_PC2_OPA", "SWSTART")
    (['TIM1_CC4', 'TIM1_CC5'], ['PD3', 'PC2', 'OPA'])
    >>> header_tokens("None", "JSWSTART"), header_tokens("Ext_IT15_T8_CC4", "JSWSTART")
    (['JSWSTART'], ['EXTI15', 'TIM8_CC4'])
    """
    if suffix == "None":
        return [software]
    out, timer = [], None
    for part in suffix.split("_"):
        m = re.fullmatch(r"T(?:IM)?(\d+)", part)
        if m:
            timer = m.group(1)
            continue
        if re.fullmatch(r"CC\d|TRGO", part) and timer:
            out.append(f"TIM{timer}_{part}")
            continue
        timer = None
        m = re.fullmatch(r"IT(\d+)", part)
        if m:
            out.append(f"EXTI{m.group(1)}")
        elif PAD.match(part) or part in ("TKEY", "OPA"):
            out.append(part)
        elif part != "Ext":
            out.append(part)
    return out


def rm_tokens(text: str) -> list[str]:
    """RM の説明の1項目の事象。zh・en の両方を読む。

    >>> rm_tokens("定时器1的CC4事件/CC5事件"), rm_tokens("EXTI线11/定时器8的TRGO事件")
    (['TIM1_CC4', 'TIM1_CC5'], ['EXTI11', 'TIM8_TRGO'])
    >>> rm_tokens("EXTI line 15/CC4 event of timer8"), rm_tokens("PD3/PC2事件")
    (['TIM8_CC4', 'EXTI15'], ['PD3', 'PC2'])
    >>> rm_tokens("SWSTART软件触发"), rm_tokens("TRGO event of timer 1"), rm_tokens("保留")
    (['SWSTART'], ['TIM1_TRGO'], [])

    en 版はタイマの番号を後ろにまとめて書くことがある（M030: `CC4 event/CC5 event of timer 1`）。

    >>> rm_tokens("CC4 event/CC5 event of timer 1")
    ['TIM1_CC4', 'TIM1_CC5']
    """
    out = []
    # en: `<CC|TRGO> event of timer N`。番号の無いものは後ろ（無ければ前）の番号を採る。
    found = [(m.group(1).upper(), m.group(2)) for m in re.finditer(
        r"\b(CC\d|TRGO) event(?: of (?:the )?timer ?(\d+))?", text, re.IGNORECASE)]
    for i, (event, timer) in enumerate(found):
        timer = timer or next((t for _, t in found[i + 1:] if t), None) or next(
            (t for _, t in reversed(found[:i]) if t), None)
        if timer:
            out.append(f"TIM{timer}_{event}")
    for item in re.split(r"[/／]", text):
        # zh: `定时器N的<CC|TRGO>事件`。番号の無いもの（`定时器1的CC4事件/CC5事件`）は前の番号。
        for m in re.finditer(r"(?:定时器(\d+)的)?(CC\d|TRGO)事件", item):
            timer = m.group(1) or (out[-1].split("_")[0][3:]
                                   if out and out[-1].startswith("TIM") else None)
            if timer:
                out.append(f"TIM{timer}_{m.group(2)}")
        for m in re.finditer(r"EXTI\s*(?:线|line\s*)?(\d+)", item, re.IGNORECASE):
            out.append(f"EXTI{m.group(1)}")
        out += re.findall(r"\bP[A-F]\d+\b|(?<![A-Z])P[A-F]\d+", item)
        m = re.search(r"\b(J?SWSTART)", item)
        if m:
            out.append(m.group(1))
        for word in ("TKEY", "OPA"):
            if word in item.upper():
                out.append(word)
    return list(dict.fromkeys(out))


def rm_values(description: str, width: int) -> dict[int, list[str]]:
    """`000：定时器1的CC1事件；…` → {0: [TIM1_CC1], …}。読めない値は持たない。"""
    found = {}
    for m in re.finditer(rf"(?<![01])([01]{{{width}}})\s*[：:]\s*([^；;。\n]*)", description):
        tokens = rm_tokens(m.group(2))
        if tokens:
            found.setdefault(int(m.group(1), 2), tokens)
    return found


def kind_of(token: str) -> str:
    if token.startswith("TIM"):
        return "timer"
    if token.startswith("EXTI"):
        return "exti"
    if PAD.match(token):
        return "pin"
    if token.endswith("SWSTART"):
        return "software"
    return token.lower()   # tkey / opa


def manuals() -> dict[str, str]:
    """family → RM の名前（目録の reference-manual の行）。"""
    out = {}
    with open(REPO / "catalog" / "documents.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["kind"] == "reference-manual":
                for family in row["repositories"].split(";"):
                    out[family] = row["document"].removesuffix(".PDF")
    return out


def header_fields() -> dict[str, dict[str, tuple[int, int]]]:
    """family → field → (offset, width)。`register_fields` の EVT 由来の行から。"""
    out: dict[str, dict] = collections.defaultdict(dict)
    with open(paths.table("register_fields"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["kind"] != "field":
                continue
            bits = row["bits"]
            hi, _, lo = bits.partition(":")
            lo = lo or hi
            if not (hi.isdigit() and lo.isdigit()):
                continue
            key = f"{row['register']}.{row['field']}"
            out[row["family"]][key] = (int(lo), int(hi) - int(lo) + 1)
    return out


def remap_fields(fields: dict[str, tuple[int, int]], group: str) -> list[str]:
    """この group の外部トリガを remap する AFIO の bit（header の綴り）。"""
    tag = {"regular": ("REG", "IN"), "injected": ("INJ", "IN")}[group]
    found = []
    for key in sorted(fields):
        m = re.fullmatch(r"AFIO_PCFR1\.ADC\d?_ETRG(REG|INJ|IN)_REMAP", key)
        if m and m.group(1) in tag:
            found.append(key)
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
        fields = fields_of.get(family, {})
        manual = rms.get(family)
        described: dict[tuple[str, str], dict[int, list[str]]] = {}
        for lang in ("zh", "en"):
            if not manual:
                break
            try:
                rm, _ = rm_fields.extract(f"{manual}.{lang}", None)
            except SystemExit:
                continue
            for f in rm:
                if f["field"] in ("EXTSEL", "JEXTSEL") and f["register"].endswith("CTLR2"):
                    described[(f["field"], lang)] = rm_values(f["description"], f["bit_width"])
        defines: dict[tuple[str, int], list[str]] = collections.defaultdict(list)
        for line in header.read_text(encoding="utf-8", errors="replace").splitlines():
            m = DEFINE.match(line)
            if not m:
                continue
            for group, (field, prefix, _) in GROUPS.items():
                if m.group("name").startswith(prefix):
                    offset, width = fields.get(f"ADC_CTLR2.{field}", (None, None))
                    if offset is None:
                        print(f"{family}: ADC_CTLR2.{field} の位置が分からない", file=sys.stderr)
                        continue
                    mask = int(m.group("mask"), 16)
                    # field の外に bit を持つ定義は別の選択子のもの（V205 の `TKEY`=0x01000000 は
                    # 値6の中を EXTI15/OPA/TKEY に分ける別の bit）。
                    if mask & ~(((1 << width) - 1) << offset):
                        print(f"{family}: {m.group('name')} は {field} の外の bit を持つので読まない",
                              file=sys.stderr)
                        continue
                    defines[(group, mask >> offset)].append(m.group("name"))
        for (group, value), names in sorted(defines.items()):
            field, prefix, software = GROUPS[group]
            offset, width = fields[f"ADC_CTLR2.{field}"]

            def norm(tokens: list[str]) -> set[str]:
                # en 版は注入の JSWSTART も `SWSTART` と書く（M030）。どちらもソフトウェア。
                return {software if t.endswith("SWSTART") else t for t in tokens}

            said = {lang: v[value] for (f, lang), v in described.items() if f == field and value in v}
            # **同じ値に定義が2つ以上あることがある。** V20x/V30x の header は STM32 の ADC3 用の
            # 名前（`T4_CC3`・`T8_CC2`・`T5_TRGO` …）を同じ値で並べ、V205 は値6を分ける別の選択子の
            # `Ext_IT15_OPA`（=0）を並べる。RM が言う事象と一致する定義があればそれだけを採る。
            if len(names) > 1 and said:
                matching = [n for n in names if any(
                    norm(header_tokens(n[len(prefix):], software)) == norm(t) for t in said.values())]
                if matching and len(matching) < len(names):
                    print(f"{family} {field}={value}: RM と合わない定義を外した "
                          f"{sorted(set(names) - set(matching))}", file=sys.stderr)
                    names = matching
            tokens: list[str] = []
            for name in names:
                tokens += header_tokens(name[len(prefix):], software)
            tokens = list(dict.fromkeys(tokens))
            agree = sorted(lang for lang, t in said.items() if norm(t) == norm(tokens))
            differ = {lang: t for lang, t in said.items() if norm(t) != norm(tokens)}
            basis = f"evt({header.name})"
            if agree:
                basis += f"+rm({manual}:{'+'.join(agree)})"
            for lang, t in sorted(differ.items()):
                basis += f"+!rm({manual}:{lang})(trigger={';'.join(t)})"
            confidence = ("conflict" if differ else "confirmed" if agree else "reference")
            bits = f"{offset + width - 1}:{offset}"
            # 候補が2つ以上で、remap の bit を header が持つなら、bit と値ごとに1行。
            # 外部の事象（`Ext_…`）だけ。M030 の `T1_CC4_CC5` は remap で選ぶものではない。
            external = all(n[len(prefix):].startswith("Ext_") for n in names)
            switch = remap_fields(fields, group) if len(tokens) == 2 and external else []
            choices = ([(f, v, [tokens[v]]) for f in switch for v in (0, 1)]
                       if switch else [("", "", tokens)])
            for remap_field, remap_value, chosen in choices:
                rows.append({
                    "family": family, "group": group, "register": "ADC_CTLR2",
                    "field": field, "bits": bits, "value": value,
                    "trigger": ";".join(chosen),
                    "kind": ";".join(dict.fromkeys(kind_of(t) for t in chosen)),
                    "remap_field": remap_field, "remap_value": remap_value,
                    "define": ";".join(names), "confidence": confidence, "basis": basis,
                })
    rows.sort(key=lambda r: (r["family"], r["group"] != "regular", r["value"],
                             r["remap_field"], str(r["remap_value"])))
    dest = paths.table("adc_triggers", args.out)
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
