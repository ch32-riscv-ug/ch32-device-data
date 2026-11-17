#!/usr/bin/env python3
"""PVD（電圧監視）の段 → index/pvd_levels.csv

PVD は `PWR_CTLR.PLS` で閾値の段を選び、電源がその電圧を上下に横切ると `PVD` 事象（EXTI の線、
`exti_lines`）を起こす。段ごとの電圧は datasheet の表「复位及电压监测」/「Reset and voltage monitor」
が `PLS[2:0] = 000(上升沿) … 1.75 V` の形で書く。consumer（ch32rv のコア）の依頼（2026-11-17）。

**`operating_conditions` の `V_PVD` から作らない理由。** あの表はページの本文を行に読む凍結時の
規則で作っていて、表がページをまたぐと続きの段を落とす（L103 は 8 段のうち 5 段、V004/V007/M007 の
datasheet は 0 段）。ここでは bundle の表を `logical_id` で続きの断片とつなぎ、セルとして読む。

1行は datasheet × `PLS` の値 × 向き（`rising` = 上昇時、`falling` = 下降時）。同じ series が
2つの datasheet に載ることがある（V203 は CH32V203DS0 と、V205 のダイの品番を載せる CH32V205DS0）
ので、どちらの datasheet の値かは `datasheet` 列で持ち、品番からは `index/parts.csv` の `datasheet`
で引く。zh・en 版の値が一致すれば confirmed、違えば conflict（zh を採る）、片方だけなら reference。

実行:
    uv run pipeline/extract/datasheet/extract_pvd_levels.py [--out <dir>]
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

import bundle_pages  # noqa: E402
import paths  # noqa: E402

COLUMNS = ["datasheet", "series", "field", "pls", "edge", "min", "typ", "max", "unit",
           "confidence", "basis"]
CAPTION = re.compile(r"电压监测|voltage monitor", re.IGNORECASE)
CONDITION = re.compile(r"(?P<field>PLS\[\d+:0\])\s*=\s*(?P<code>[01]+)\s*[（(]?\s*"
                       r"(?P<edge>上升沿|下降沿|rising\s*edge|falling\s*edge)", re.IGNORECASE)
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


def tables_by_id(bundle: str) -> dict[str, list[tuple[int, dict]]]:
    """logical_id → [(頁, 表)]。ページをまたぐ表の続きの断片も同じ id に入る。"""
    out: dict[str, list[tuple[int, dict]]] = collections.defaultdict(list)
    for number, page in enumerate(bundle_pages.pages(bundle), start=1):
        for table in page.get("tables", []):
            out[table["logical_id"]].append((page.get("page") or number, table))
    return out


def columns_of(header: list[str | None]) -> dict[str, int]:
    found = {}
    for i, cell in enumerate(header):
        text = (cell or "").replace("\n", "")
        for key, pattern in (("min", r"最小|Min"), ("typ", r"典型|Typ"), ("max", r"最大|Max"),
                             ("unit", r"单位|Unit")):
            if re.search(pattern, text, re.IGNORECASE):
                found.setdefault(key, i)
    return found


def read(bundle: str) -> dict[tuple[str, int, str], dict]:
    """(field, PLS の値, 向き) → {min, typ, max, unit, page}。"""
    out = {}
    for fragments in tables_by_id(bundle).values():
        caption = ((fragments[0][1].get("caption") or {}).get("text") or "")
        if not CAPTION.search(caption):
            continue
        header = fragments[0][1]["extracted_rows"][0]
        cols = columns_of(header)
        if not {"typ", "unit"} <= set(cols):
            continue
        # 単位のセルは上昇・下降の2行で縦に結合されることがあり（V002/V006/V007/X035）、
        # 下の行は空で来る。同じ表の直前の単位を引き継ぐ。
        last_unit = ""
        for page, table in fragments:
            for row in table["extracted_rows"]:
                unit_i = cols["unit"]
                if unit_i < len(row) and (row[unit_i] or "").strip():
                    last_unit = row[unit_i].strip()
                for cell in row:
                    m = CONDITION.search((cell or "").replace("\n", ""))
                    if not m:
                        continue
                    values = {k: (row[i] or "").strip() if i < len(row) else ""
                              for k, i in cols.items()}
                    if not any(NUMBER.match(values.get(k, "")) for k in ("min", "typ", "max")):
                        continue
                    edge = "rising" if re.search(r"上升|rising", m.group("edge"), re.I) else "falling"
                    key = (m.group("field"), int(m.group("code"), 2), edge)
                    out.setdefault(key, {**{k: values.get(k, "") for k in ("min", "typ", "max")},
                                         "unit": values.get("unit") or last_unit, "page": page})
                    break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先のディレクトリ（試験用）")
    args = ap.parse_args()

    # 品番 → datasheet は目録（`index/parts.csv` は索引の段で作られ、この表より後）。
    with paths.table("products").open(newline="", encoding="utf-8") as f:
        parts = list(csv.DictReader(f))
    series_of: dict[str, set[str]] = collections.defaultdict(set)
    for p in parts:
        if p["datasheet"]:
            series_of[p["datasheet"]].add(p["series"])
    rows = []
    for datasheet in sorted(series_of):
        stem = datasheet.removesuffix(".PDF")
        editions = {}
        for lang in ("zh", "en"):
            try:
                editions[lang] = read(f"{stem}.{lang}")
            except (FileNotFoundError, KeyError, SystemExit):
                continue
        keys = sorted({k for found in editions.values() for k in found},
                      key=lambda k: (k[0], k[1], k[2] != "rising"))
        for key in keys:
            said = {lang: found[key] for lang, found in editions.items() if key in found}
            kept_lang = "zh" if "zh" in said else "en"
            kept = said[kept_lang]
            values = lambda v: (v["min"], v["typ"], v["max"], v["unit"])  # noqa: E731
            basis = "+".join(f"{datasheet}:{lang}(p.{v['page']})" for lang, v in said.items()
                             if values(v) == values(kept))
            for lang, v in said.items():
                if values(v) != values(kept):
                    basis += (f"+!{datasheet}:{lang}(p.{v['page']})"
                              f"(min={v['min']},typ={v['typ']},max={v['max']},unit={v['unit']})")
            confidence = ("conflict" if "+!" in basis
                          else "confirmed" if len(said) == 2 else "reference")
            field, code, edge = key
            rows.append({"datasheet": datasheet, "series": ";".join(sorted(series_of[datasheet])),
                         "field": field, "pls": code, "edge": edge,
                         "min": kept["min"], "typ": kept["typ"], "max": kept["max"],
                         "unit": kept["unit"], "confidence": confidence, "basis": basis})
    dest = paths.table("pvd_levels", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    shown = dest.relative_to(REPO) if dest.is_relative_to(REPO) else dest
    print(f"{shown}: {len(rows)} 行", dict(collections.Counter(r["confidence"] for r in rows)))
    by_sheet = collections.Counter(r["datasheet"] for r in rows)
    for datasheet in sorted(series_of):
        print(f"  {datasheet}: {by_sheet.get(datasheet, 0)} 行", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
