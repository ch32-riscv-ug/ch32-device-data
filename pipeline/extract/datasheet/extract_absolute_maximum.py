#!/usr/bin/env python3
"""`evidence/absolute_maximum_ratings.csv`の正本生成器。

データシートの**絶対最大定格表**（`表3-1 绝对最大值参数表` / `Table 3-1 Absolute maximum
ratings`）だけを読む。全corpus実測（2026-09-10）: **33表・33版で1文書1表**、表題は4綴りだけ、
両版ある16文書はすべて 1/1 の対称。

**`operating_conditions`と別の表にする理由**は、混ぜると区別できなくなるから。両者はどちらも
`symbol` が `V_DD` で `min`/`max` を持つが、意味が正反対——一方は**推奨動作範囲**、他方は
**そこを超えると壊れる限界**。一度 `operating_conditions` に入れて測ったところ、
`index/parts.csv` の供給電圧が `CH32L103` で `1.8..3.6V` から `-0.3..4.0V` に化けた
（`build_index.operating_summary` は `symbol == "V_DD"` の min/max を取る）。列に印が無い以上
repository の外の consumer も区別できないので、表を分ける。

表の形も違う: `符号｜描述｜（無名の条件欄）｜最小值｜最大值｜单位`——**`条件`の見出しも
`典型值`の列も無い**。条件は見出しの無い欄に書かれ、その欄すら無い版もある。

実行:
    uv run pipeline/extract/datasheet/extract_absolute_maximum.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))
sys.path.insert(0, str(REPO / "pipeline" / "extract" / "datasheet"))

import bundle_pages  # noqa: E402
import operating_rows as operating  # noqa: E402  記号・値・文章の読み方は共通
import paths  # noqa: E402

COLUMNS = ["series", "symbol", "parameter", "condition", "min", "max", "unit",
           "#", "confidence", "basis", "datasheet"]

# 表題の4綴り（全corpus実測）。章番号は文書で 3-1 と 4-1 に分かれる。
CAPTION = re.compile(
    r"绝\s*对\s*最\s*大\s*值\s*参\s*数\s*表|Absolute\s+maximum\s+ratings",
    re.IGNORECASE)
# この表の項目名の欄は`描述`/`Description`（一般工作条件の`参数`/`Parameter`ではない）。
HEADER_MAP = dict(operating.HEADER_MAP,
                  description="parameter", 描述="parameter")


def norm_header(cell: str | None) -> str | None:
    """語彙だけ差し替えて `operating_rows` の読み方を使う（正規化を二重に持たない）。"""
    return operating.norm_header(cell, HEADER_MAP)


def align_cols(cols: list, edges: list[float], part: list[float],
               tol: float = 2.0) -> list | None:
    """続きの断片の列を、見出し表の列へ**x座標で**対応づける。

    条件の欄は**見出しを持たず、断片ごとに幅が変わる**（`CH32V007DS0.zh` の左端は
    p.28 が 254.9、p.29 が 297.5）。列数が同じでも並びがずれるので、列数の一致でも
    `same_edges`（全部一致）でも続きと見なせない。合わない列は`None`＝無名の列になり、
    そのまま条件へ流れる。

    >>> align_cols(["symbol", "parameter", None, "min"],
    ...            [10.0, 50.0, 100.0, 200.0, 260.0],
    ...            [10.0, 50.0, 140.0, 200.0, 260.0])
    ['symbol', 'parameter', None, 'min']
    >>> align_cols(["symbol", "min"], [10.0, 200.0, 260.0], [10.0, 140.0, 200.0, 260.0])
    ['symbol', None, 'min']
    >>> align_cols(["symbol", "min"], [10.0, 200.0], [10.0, 200.0, 260.0]) is None
    True
    """
    if len(edges) != len(cols) + 1:
        return None
    out = []
    for x in part[:-1]:
        hit = [c for c, y in zip(cols, edges) if abs(x - y) <= tol]
        out.append(hit[0] if len(hit) == 1 else None)
    return out


def read_edition(bundle: str, lang: str) -> list[dict]:
    """その版の絶対最大定格表の行（続きの断片を含む）。"""
    found: list[dict] = []
    head_cols: list | None = None
    head_edges: list[float] = []
    sym = unit = param = ""
    for page in bundle_pages.pages(bundle):
        for record in page.get("tables", []):
            caption = ((record.get("caption") or {}).get("text") or "").strip()
            rows = record["extracted_rows"]
            edges = operating.column_edges(record)
            if CAPTION.search(caption):
                cols = [norm_header(c) for c in rows[0]]
                if not {"symbol", "parameter", "min", "max", "unit"} <= set(cols):
                    print(f"{bundle} p.{page['number']}: 絶対最大定格表の見出しが読めない "
                          f"{rows[0]}", file=sys.stderr)
                    head_cols = None
                    continue
                head_cols, head_edges = cols, edges
                body = rows[1:]
                sym = unit = param = ""
            elif caption or head_cols is None:
                # 表題を持つ別の表が来たら連鎖は終わり。
                if caption:
                    head_cols = None
                continue
            else:
                cols = align_cols(head_cols, head_edges, edges)
                if (cols is None or len(edges) != len(rows[0]) + 1
                        or set(filter(None, cols)) != set(filter(None, head_cols))):
                    head_cols = None
                    continue
                body = rows
            for raw in body:
                cells: dict[str, str] = {}
                extra: list[str] = []
                for i, cell in enumerate(raw):
                    if i < len(cols) and cols[i]:
                        cells[cols[i]] = cell
                    elif cell:
                        extra.append(cell)
                s = operating.norm_symbol(cells.get("symbol"))
                this = operating.norm_text(cells.get("parameter"))
                if s:
                    sym, param = s, this
                else:
                    param = this or param
                # 単位は**続きの行でも継ぐ**。資料は「上と同じ」を空欄で書く。
                unit = operating.norm_value(cells.get("unit")) or unit
                row = {"symbol": sym, "parameter": param,
                       "condition": " ".join(operating.norm_text(e) for e in extra
                                             if operating.norm_text(e)),
                       "min": operating.norm_value(cells.get("min")),
                       "typ": "",
                       "max": operating.norm_value(cells.get("max")),
                       "unit": unit}
                if not (row["min"] or row["max"]):
                    continue          # 見出しの続きや空行
                if operating.keep_row(row, lang, page["number"]):
                    found.append({**row, "_page": page["number"]})
    return found


def agrees(zh: dict, en: dict) -> bool:
    """同じ事実か。`operating_rows`と同じ綴りの正規化を使う。"""
    return (operating.same_value(zh["min"], en["min"])
            and operating.same_value(zh["max"], en["max"])
            and (not (zh["unit"] and en["unit"])
                 or operating.same_unit(zh["unit"], en["unit"])))


def build() -> list[dict]:
    products = paths.load("products")
    ds_series: dict[str, set] = {}
    for p in products:
        ds_series.setdefault(p["datasheet"], set()).add(p["series"])
    out: list[dict] = []
    for datasheet in sorted(ds_series):
        editions = {}
        for lang in ("zh", "en"):
            bundle = operating._bundle(datasheet, lang)
            if bundle:
                rows = read_edition(bundle, lang)
                if rows:
                    editions[lang] = rows
        if "en" not in editions:
            print(f"{datasheet}: 英語版に絶対最大定格表が無い", file=sys.stderr)
            continue
        en_rows, zh_rows = editions["en"], editions.get("zh", [])
        series = ";".join(sorted(ds_series[datasheet]))
        # 対応付けは二段——値の一致する対を先に全部取り、余りを食い違いに回す
        # （`operating_rows`と同じ理由: 貪欲な1回走査だと先行の行が候補を食う）。
        remaining = list(zh_rows)
        paired: dict[int, dict] = {}
        for index, row in enumerate(en_rows):
            hits = [z for z in remaining
                    if z["symbol"] == row["symbol"] and agrees(z, row)]
            if not hits:
                continue
            pick = next((z for z in hits if z["condition"] == row["condition"]), hits[0])
            remaining.remove(pick)
            paired[index] = pick
        for index, row in enumerate(en_rows):
            exact = paired.get(index)
            cands = ([] if exact else
                     [z for z in remaining if z["symbol"] == row["symbol"]
                      and bool(z["condition"]) == bool(row["condition"])])
            page = row.pop("_page")
            if exact:
                confidence = "confirmed"
                basis = f"{datasheet}:zh(p.{exact['_page']})+{datasheet}:en(p.{page})"
            elif cands:
                remaining.remove(cands[0])
                confidence = "conflict"
                diff = ",".join(f"{k}={cands[0][k]}" for k in ("min", "max", "unit")
                                if cands[0][k] != row[k])
                basis = f"{datasheet}:en(p.{page})+!{datasheet}:zh({diff})"
            else:
                confidence = "reference"
                basis = f"{datasheet}:en(p.{page})"
            row.pop("typ", None)
            out.append({**row, "series": series, "#": "#",
                        "confidence": confidence, "basis": basis,
                        "datasheet": datasheet})
        if remaining:
            print(f"  {datasheet}: zhだけの行 {len(remaining)}（出さない——表示テキストは"
                  f"英語版から取る設計）", file=sys.stderr)
    out.sort(key=lambda r: (r["series"], r["symbol"], r["parameter"],
                            r["condition"], r["min"], r["max"], r["unit"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    args = ap.parse_args()
    rows = build()
    target = paths.table("absolute_maximum_ratings", args.out)
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["confidence"]] = kinds.get(r["confidence"], 0) + 1
    print(f"{target}: {len(rows)} 行 {kinds}", file=sys.stderr)
    if operating.DROPPED:
        print(f"採らなかった行: {len(operating.DROPPED)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
