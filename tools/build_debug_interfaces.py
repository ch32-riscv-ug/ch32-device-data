#!/usr/bin/env python3
"""datasheetの節見出しから debug 配線の種別を series 単位に → index/debug_interfaces.csv

`evidence/features.csv` は datasheet の機能説明章の**節見出し**を持っていて、
debug 接続の節は wire 数まで名乗るものがあります（`1-wire Serial Debug Interface
(SDI)`・`串行2线调试接口`）。書き込みツール（ch32rv。R-29）は SKU ごとに
「1線 SWIO か、2線 RVSWD か」を fail-closed で知りたいので、この見出しの主張を
series 単位の索引に組み直します。

**新しい事実は足しません。** `debug_if` が入るのは**見出しが wire 数を言う series
だけ**で、言わないもの（`Serial Debug Interface (SDI)` とだけ書く V205/M030/H41x 等）
は空にします——core 名や pad 数からの推測はしません（両対応の series があるため。
実際 V007(+M007) は見出しが 1-wire なのに pin 表は SWDIO+SWCLK の両方を持ちます）。
pad の裏付けは `index/pinout.csv` の正規化 role（SWDIO/SWCLK）から並べて置くだけです。

実行:
    uv run tools/build_debug_interfaces.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

COLUMNS = ["series", "family", "debug_if", "wording", "section",
           "swdio_pads", "swclk_pads", "#", "confidence", "basis"]

# 節見出しが debug 接続のものか（SWPMI「Single-wire Protocol Master Interface」と
# SDIO はここで落ちる: en に debug も zh に 调试 も無い）。
IS_DEBUG = re.compile(r"debug", re.IGNORECASE)
IS_DEBUG_ZH = "调试"

# 見出しの wire 数の語彙。ここに無い「N-wire」が現れたら生成が落ちる。
ONE_WIRE = re.compile(r"1-wire|single-wire|单线", re.IGNORECASE)
TWO_WIRE = re.compile(r"2-wire|2线|两线|二线", re.IGNORECASE)
ANY_WIRE = re.compile(r"wire|[单两二2]\s*线", re.IGNORECASE)

# 見出しが wire 数を言わない series の数（2026-09-01 の資料で 11:
# V005/V006/V205/M030/H415/H416/H417/V407/V467/X305/X315）。増減どちらでも
# 生成が落ちるので、datasheet の改版で見出しが変われば必ず人の目を通る。
KNOWN_UNSTATED = 11

CONFIDENCE_ORDER = {"confirmed": 0, "reference": 1, "conflict": 2}


def classify(row: dict) -> str | None:
    """見出しの綴りから 'swio' / 'rvswd' / None（言わない）。en と zh が食い違えば例外。"""
    votes = set()
    for text in (row["feature"], row["feature_zh"]):
        one, two = bool(ONE_WIRE.search(text)), bool(TWO_WIRE.search(text))
        if one and two:
            raise SystemExit(f"見出しが 1-wire と 2-wire の両方を名乗る: {text!r}")
        if one:
            votes.add("swio")
        elif two:
            votes.add("rvswd")
        elif ANY_WIRE.search(text):
            raise SystemExit(f"wire 数の語彙に無い見出し——ONE_WIRE/TWO_WIRE に足すこと: {text!r}")
    if len(votes) > 1:
        raise SystemExit(f"en と zh で wire 数が食い違う: {row['feature']!r} / {row['feature_zh']!r}")
    return votes.pop() if votes else None


def rows_for(features: list[dict], series_table: list[dict],
             pinout: list[dict]) -> tuple[list[dict], int]:
    family_of = {s["series"]: s["family"] for s in series_table}

    pads: dict[tuple[str, str], set[str]] = {}
    for r in pinout:
        if r["role"] in ("SWDIO", "SWCLK"):
            pads.setdefault((r["series"], r["role"]), set()).add(r["pad"])

    statements: dict[str, list[tuple[str | None, dict]]] = {}
    for r in features:
        if not (IS_DEBUG.search(r["feature"]) or IS_DEBUG_ZH in r["feature_zh"]):
            continue
        kind = classify(r)
        for series in r["series"].split(";"):
            statements.setdefault(series, []).append((kind, r))

    rows, unstated = [], 0
    for series, family in family_of.items():
        got = statements.get(series)
        if not got:
            raise SystemExit(f"{series}: features.csv に debug の節見出しが無い")
        stated = sorted((k, r) for k, r in got if k)
        if len({k for k, _ in stated}) > 1:
            raise SystemExit(f"{series}: datasheet ごとに wire 数の主張が食い違う: {stated}")
        if stated:
            # 言っている見出しを採る。複数あれば confirmed を優先し、datasheet 名で決める。
            kind, src = min(stated, key=lambda kr: (CONFIDENCE_ORDER[kr[1]["confidence"]],
                                                    kr[1]["datasheet"]))
        else:
            unstated += 1
            kind, src = "", min((r for _, r in got),
                                key=lambda r: (CONFIDENCE_ORDER[r["confidence"]], r["datasheet"]))
        if kind == "swio" and not pads.get((series, "SWDIO")):
            raise SystemExit(f"{series}: 1-wire なのに pinout に SWDIO の pad が無い")
        rows.append({"series": series, "family": family,
                     "debug_if": kind or "", "wording": src["feature"],
                     "section": src["section"],
                     "swdio_pads": ";".join(sorted(pads.get((series, "SWDIO"), set()))),
                     "swclk_pads": ";".join(sorted(pads.get((series, "SWCLK"), set()))),
                     "confidence": src["confidence"], "basis": src["basis"]})
    rows.sort(key=lambda r: r["series"])
    return rows, unstated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先の上書き（試験用）")
    args = ap.parse_args()

    rows, unstated = rows_for(paths.load("features"), paths.load("series"),
                              paths.load_index("pinout"))
    if unstated != KNOWN_UNSTATED:
        print(f"見出しが wire 数を言わない series が {unstated}（記録は {KNOWN_UNSTATED}）"
              "——datasheet の改版で見出しが変わった。KNOWN_UNSTATED と "
              "docs/table-reliability.ja.md を数え直すこと", file=sys.stderr)
        return 1

    dest = paths.index("debug_interfaces", args.out)
    paths.write(dest, rows, COLUMNS)
    kinds = {k: sum(1 for r in rows if r["debug_if"] == k) for k in ("swio", "rvswd", "")}
    print(f"{dest}: {len(rows)} 行  swio {kinds['swio']} / rvswd {kinds['rvswd']} / "
          f"unstated {kinds['']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
