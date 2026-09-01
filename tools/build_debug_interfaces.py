#!/usr/bin/env python3
"""datasheetの節見出しから debug 配線の種別を series 単位に → index/debug_interfaces.csv

`evidence/features.csv` は datasheet の機能説明章の**節見出し**を持っていて、
debug 接続の節は wire 数まで名乗るものがあります（`1-wire Serial Debug Interface
(SDI)`・`串行2线调试接口`）。書き込みツール（ch32rv。R-29）は SKU ごとに
「1線 SWIO か、2線 RVSWD か」を fail-closed で知りたいので、この見出しの主張を
series 単位の索引に組み直します。

**新しい事実は足しません。** `debug_if`は2つの証拠の突き合わせ——datasheetの
節見出し（`evidence/features.csv`）と、WCH-Link manualの配線表＋両対応の注記
（`evidence/debug_wiring.csv`。R-29の残り11 seriesを埋めた2026-09-01の追加）。
manualが両対応と言えば`both`、配線表のSWCLK欄が空なら`swio`、あれば`rvswd`。
見出しがwire数を言う場合はmanualと矛盾しないことを確かめる（見出し`swio`は
`both`の部分集合として整合——実際V007(+M007)は見出し1-wireでmanualは両対応）。
どちらの証拠でも決まらないseriesが残ったら生成が落ちる。padの裏付けは
`index/pinout.csv`の正規化role（SWDIO/SWCLK）で、manualのpadがpinoutに
無ければ生成が落ちる（相互検証）。

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


def resolve(heading: str | None, wiring: dict | None, series: str) -> str:
    """見出しの分類とmanualの配線から debug_if を決める。矛盾は例外。"""
    if wiring is None:
        if heading is None:
            raise SystemExit(f"{series}: 見出しもmanualの配線表もwire数を言わない")
        return heading
    manual = ("both" if wiring["dual_support"] == "yes"
              else "swio" if not wiring["swclk_pad"] else "rvswd")
    if heading and heading != manual and manual != "both":
        raise SystemExit(f"{series}: 見出し({heading})とmanual({manual})が矛盾")
    return manual


def rows_for(features: list[dict], series_table: list[dict],
             pinout: list[dict], wiring_rows: list[dict]) -> list[dict]:
    family_of = {s["series"]: s["family"] for s in series_table}

    pads: dict[tuple[str, str], set[str]] = {}
    for r in pinout:
        if r["role"] in ("SWDIO", "SWCLK"):
            pads.setdefault((r["series"], r["role"]), set()).add(r["pad"])

    wiring = {r["series"]: r for r in wiring_rows}
    statements: dict[str, list[tuple[str | None, dict]]] = {}
    for r in features:
        if not (IS_DEBUG.search(r["feature"]) or IS_DEBUG_ZH in r["feature_zh"]):
            continue
        kind = classify(r)
        for series in r["series"].split(";"):
            statements.setdefault(series, []).append((kind, r))

    rows = []
    for series, family in family_of.items():
        got = statements.get(series)
        if not got:
            raise SystemExit(f"{series}: features.csv に debug の節見出しが無い")
        stated = sorted((k, r) for k, r in got if k)
        if len({k for k, _ in stated}) > 1:
            raise SystemExit(f"{series}: datasheet ごとに wire 数の主張が食い違う: {stated}")
        if stated:
            heading, src = min(stated, key=lambda kr: (CONFIDENCE_ORDER[kr[1]["confidence"]],
                                                       kr[1]["datasheet"]))
        else:
            heading, src = None, min((r for _, r in got),
                                     key=lambda r: (CONFIDENCE_ORDER[r["confidence"]],
                                                    r["datasheet"]))
        w = wiring.get(series)
        # manualのpadはpinoutで裏を取る。SWDIOが無いのは写し間違いなので落ちる。
        # **SWCLKをmanualが言うのにpin表に無い**のは資料間の齟齬（V002/V004で実在:
        # manualはV00x群を両対応と括るが、V002/V004のpin表にSWCLKは無く見出しも
        # 1-wire）——manualの主張は採らず、異議としてbasisへ記録する（自動で
        # どちらかに寄せない規約）。
        dissent = None
        if w:
            if w["swdio_pad"] not in pads.get((series, "SWDIO"), set()):
                raise SystemExit(f"{series}: manualのSWDIO {w['swdio_pad']} がpinoutに無い")
            if w["swclk_pad"] and w["swclk_pad"] not in pads.get((series, "SWCLK"), set()):
                dissent, w = w, None
        kind = resolve(heading, w, series)
        if kind == "swio" and not pads.get((series, "SWDIO")):
            raise SystemExit(f"{series}: 1-wire なのに pinout に SWDIO の pad が無い")
        confidence = w["confidence"] if w else src["confidence"]
        basis = f"{src['basis']}+{w['basis']}" if w else src["basis"]
        if dissent:
            basis = (f"{src['basis']}+!WCH-LinkUserManual.PDF"
                     f"(swclk={dissent['swclk_pad']},dual={dissent['dual_support'] or 'no'})")
        rows.append({"series": series, "family": family,
                     "debug_if": kind, "wording": src["feature"],
                     "section": src["section"],
                     "swdio_pads": ";".join(sorted(pads.get((series, "SWDIO"), set()))),
                     "swclk_pads": ";".join(sorted(pads.get((series, "SWCLK"), set()))),
                     "confidence": confidence, "basis": basis})
    rows.sort(key=lambda r: r["series"])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先の上書き（試験用）")
    args = ap.parse_args()

    rows = rows_for(paths.load("features"), paths.load("series"),
                    paths.load_index("pinout"), paths.load("debug_wiring"))

    dest = paths.index("debug_interfaces", args.out)
    paths.write(dest, rows, COLUMNS)
    kinds = {k: sum(1 for r in rows if r["debug_if"] == k)
             for k in ("swio", "rvswd", "both")}
    print(f"{dest}: {len(rows)} 行  swio {kinds['swio']} / rvswd {kinds['rvswd']} / "
          f"both {kinds['both']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
