#!/usr/bin/env python3
"""OPA/CMP の選択 field の値 → 端子・内部の接続 → index/opa_cmp_selects.csv

OPA と CMP は、正端・負端・出力・PGA のバイアスなどの経路を field の値で選ぶ。値ごとにどの端子か
は RM の field の説明だけが書く（`MODE1 … 1：输出信号通过PA7输出； 0：输出信号通过PB1输出`）。
datasheet のピン表の番号（`OPA_OUT1`/`OPA_OUT2`）は値と一致しない family がある（V407 の MODE1 は
0 が PB1、1 が PA7。H41x の OPA2/OPA3 も同じ）。consumer（ch32rv のコア）は RM から手で書いていた
（2026-11-19 の依頼）。

1行は family × register × field × 値。`target` は端子（`PB1`）か内部の接続を英語の記号で:
`OPAn_OUT`（OPA の出力）・`DAC_OUT`・`PGA`（負端を使わない PGA の内部帰還）・`OFF`（閉じる）・
`GND`・`VREF`。説明が端子を2つ書く値（差動の PGA で `OPA1_CHN1（PA5）` を使う）は `;` で並べる。
読めない値は行を持たない。zh・en 版が同じ target を言えば confirmed、違えば conflict（zh を採る）、
片方だけなら reference。対象は OPA/CMP の register の field のうち、少なくとも1つの値が端子を書く
もの。

実行:
    uv run pipeline/extract/rm/extract_opa_cmp_selects.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))
sys.path.insert(0, str(REPO / "pipeline" / "extract" / "rm"))

import bundle_pages  # noqa: E402
import paths  # noqa: E402
import register_fields as rm_fields  # noqa: E402

COLUMNS = ["family", "register", "field", "bits", "value", "target", "confidence", "basis"]
REGISTER = re.compile(r"^(?:R32_)?(?:OPA|CMP)", re.IGNORECASE)
PAD = re.compile(r"(?<![A-Z0-9])P[A-F]\d{1,2}(?!\d)")


def target_of(text: str) -> str:
    """値の説明 → target。読めなければ空。

    >>> [target_of(t) for t in ("输出信号通过PA7输出", "正端接OPA2输出", "负端接DAC输出", "正端关闭",
    ...                         "PGA模式，无负端输入通道，内部增益 为4", "OPA1_CHN1（PA5）",
    ...                         "Output signal through PB1", "output of OPA2", "closed", "输出端关闭")]
    ['PA7', 'OPA2_OUT', 'DAC_OUT', 'OFF', 'PGA', 'PA5', 'PB1', 'OPA2_OUT', 'OFF', 'OFF']
    """
    pads = list(dict.fromkeys(PAD.findall(text)))
    if pads:
        return ";".join(pads)
    m = re.search(r"OPA\s*(\d)\s*(?:的)?(?:输出|output)|output\s+of\s+OPA\s*(\d)", text, re.IGNORECASE)
    if m:
        return f"OPA{m.group(1) or m.group(2)}_OUT"
    if re.search(r"DAC", text):
        return "DAC_OUT"
    if re.search(r"PGA", text):
        return "PGA"
    if re.search(r"关闭|断开|均不选择|高阻|\boff\b|\bclosed?\b|disconnect|none selected|high.impedance", text, re.IGNORECASE):
        return "OFF"
    if re.search(r"接地|\bGND\b|ground", text, re.IGNORECASE):
        return "GND"
    if re.search(r"VREF|参考电压", text, re.IGNORECASE):
        return "VREF"
    return ""


def values(description: str, width: int) -> dict[int, str]:
    """`00：…； 01：…； 1x：…` → {値: target}。`x` は両方に開く。

    区切りの `；` が無い版がある（L103 zh の NSEL1 は `0000：PB11 0001：PA6 …` と並べるだけ）ので、
    **次の値の符号までを1つの値の説明**にする。field の幅と違う桁数で書く版もある（H417 en の
    1 bit の MODE2 を `00: …; 01: …`）——幅で読めなければ桁数を問わず読む。

    >>> values("0000：PB11 0001：PA6 0110：PB10，PGA模式 1111：均不选择 其他：保留", 4)
    {0: 'PB11', 1: 'PA6', 6: 'PB10', 15: 'OFF'}
    >>> values("00: Output signal via PB1; 01: Output signal via PE7;", 1)
    {0: 'PB1', 1: 'PE7'}
    """
    def scan(pattern: str) -> dict[int, str]:
        marks = list(re.finditer(pattern, description))
        found: dict[int, str] = {}
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(description)
            text = re.split(r"其他|其它|Others?\b", description[m.end():end])[0]
            target = target_of(text)
            if not target:
                continue
            options = [""]
            for ch in m.group(1).lower():
                options = [o + c for o in options for c in ("01" if ch == "x" else ch)]
            for o in options:
                found.setdefault(int(o, 2), target)
        return found
    return (scan(rf"(?<![0-9A-Za-z])([01xX]{{{width}}})\s*[：:]")
            or scan(r"(?<![0-9A-Za-z])([01xX]{1,4})\s*[：:]"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先のディレクトリ（試験用）")
    args = ap.parse_args()

    with paths.table("families").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    rows = []
    for family in families:
        editions = {}
        for lang, (bundle, document) in bundle_pages.rm_bundles(family).items():
            fields = {}
            for f in rm_fields.extract(bundle.name, None)[0]:
                if not REGISTER.match(f["register"]):
                    continue
                register = re.sub(r"^R32_", "", f["register"], flags=re.IGNORECASE)
                got = values(f["description"] or "", f["bit_width"])
                if got and any(PAD.search(t) for t in got.values()):
                    fields.setdefault((register, f["field"]),
                                      (f["bit_offset"], f["bit_width"], got, f.get("page")))
            editions[lang] = (document, fields)
        keys = sorted({k for _, fields in editions.values() for k in fields})
        for register, field in keys:
            said = {lang: fields[(register, field)] for lang, (_, fields) in editions.items()
                    if (register, field) in fields}
            kept_lang = "zh" if "zh" in said else "en"
            offset, width, kept_values, _ = said[kept_lang]
            bits = f"{offset}" if width == 1 else f"{offset + width - 1}:{offset}"
            for value in sorted({v for s in said.values() for v in s[2]}):
                claims = {lang: s[2][value] for lang, s in said.items() if value in s[2]}
                kept = claims.get(kept_lang) or next(iter(claims.values()))
                document = {lang: editions[lang][0] for lang in claims}
                basis = "+".join(f"rm:{document[lang]}:{lang}" for lang, t in claims.items() if t == kept)
                basis += "".join(f"+!rm:{document[lang]}:{lang}(target={t})"
                                 for lang, t in claims.items() if t != kept)
                rows.append({"family": family, "register": register, "field": field, "bits": bits,
                             "value": value, "target": kept,
                             "confidence": ("conflict" if "+!" in basis
                                            else "confirmed" if len(claims) == 2 else "reference"),
                             "basis": basis})
    dest = paths.table("opa_cmp_selects", args.out)
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
