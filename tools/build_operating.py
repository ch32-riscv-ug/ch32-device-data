#!/usr/bin/env python3
"""データシートの一般動作条件表 → tables/operating_conditions.csv

各データシートの「General operating conditions / 一般工作条件」表から
クロック上限(F_*)と動作電圧(V_DD)の行だけを抽出する。表示テキストは
英語版から取り、最小値/最大値/単位は中英で照合して一致すれば confirmed。
シリーズはproducts.csvの(datasheet→series)結合で展開する。

実行: uv run python tools/build_operating.py
"""

import csv
import re
import sys
from pathlib import Path

import pdfplumber

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent

MARKER = {
    "en": re.compile(r"General\s+operating\s+conditions", re.IGNORECASE),
    "zh": re.compile(r"[通一]\s*[用般]\s*工\s*作\s*条\s*件"),
}
# ヘッダー名 → 正規列。抽出時のCJK間スペースと脚注を吸収する。
HEADER_MAP = {
    "symbol": "symbol", "符号": "symbol",
    "parameter": "parameter", "参数": "parameter",
    "condition": "condition", "条件": "condition",
    "min": "min", "最小值": "min",
    "typ": "typ", "典型值": "typ",
    "max": "max", "最大值": "max",
    "unit": "unit", "单位": "unit",
}
FOOTNOTE = re.compile(r"[（(]\d+[）)]")
KEEP = re.compile(r"^F_|^V_?DD$")  # クロック上限と主電源電圧のみ
# 抽出時に潰れた表記の修繕（サブスクリプト割り込み・原文の詰まり）
SYMBOL_FIX = {"F_HCLK_OrF_SYS": "F_HCLK", "F_HCLK_orF_SYS": "F_HCLK"}
VALUE_FIX = {"FHCLK": "F_HCLK"}
TEXT_REPAIRS = [
    (re.compile(r"^T = (.+?)\s*A$"), r"T_A = \1"),
    (re.compile(r"usedUSB"), "used USB"),
]

COLUMNS = ["series", "symbol", "parameter", "condition",
           "min", "max", "unit", "#", "confidence", "basis", "datasheet"]

# データシート1ページ目の特徴リストが宣言する「系統主頻」。電気的特性表の
# F_HCLK（AHBの上限値）とは別の事実で、こちらが製品として謳われる周波数
# （例: CH32V003は本文48MHz、電気的特性の上限は50MHz）。表ではなく散文
# なので、表抽出とは別に拾う。
HEADLINE = {
    "en": [re.compile(r"(?:system|main)\s+(?:main\s+)?frequency[^.\n]{0,24}?(\d{2,3})\s*MHz",
                      re.IGNORECASE),
           re.compile(r"(\d{2,3})\s*MHz\s+system\s+(?:main\s+)?frequency",
                      re.IGNORECASE)],
    "zh": [re.compile(r"系统主频[^。\n]{0,8}?(\d{2,3})\s*MHz"),
           re.compile(r"(\d{2,3})\s*MHz\s*系统主频"),
           re.compile(r"(\d{2,3})\s*MHz\s*主频"),
           re.compile(r"主频[^。\n]{0,12}?(\d{2,3})\s*MHz")],
}


def norm_header(cell):
    text = FOOTNOTE.sub("", (cell or "")).replace(" ", "").replace(".", "")
    return HEADER_MAP.get(text.lower() if text.isascii() else text)


def norm_symbol(cell):
    parts = [p.strip() for p in (cell or "").split("\n") if p.strip()]
    sym = FOOTNOTE.sub("", "_".join(parts)).replace(" ", "")
    sym = SYMBOL_FIX.get(sym, sym)
    # 「F_HCLK or F_SYS」のような複合表記（orは英語版、或は中国語版）は、
    # サブスクリプトの折返しで語順が壊れるため HCLK を含めば F_HCLK に畳む。
    if "HCLK" in sym and not sym.startswith("F_P"):
        sym = "F_HCLK"
    return sym


def norm_text(cell):
    text = re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()
    for pattern, repl in TEXT_REPAIRS:
        text = pattern.sub(repl, text)
    return text


def norm_value(cell):
    value = FOOTNOTE.sub("", norm_text(cell)).replace(" ", "")
    return VALUE_FIX.get(value, value)


def read_edition(pdf_path, lang):
    """(page_no, [row dict]) — マーカーページの直後にある対象表の行を返す。"""
    marker = MARKER[lang]
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not marker.search(text):
                continue
            for tbl in page.extract_tables():
                cols = [norm_header(c) for c in tbl[0]]
                # 条件列は動作条件表にしかない（絶対最大定格表は符号+描述のみ）
                if not {"symbol", "min", "condition"} <= set(cols):
                    continue
                rows, sym, unit, param = [], "", "", ""
                for raw in tbl[1:]:
                    cells = dict()
                    extra = []
                    for i, cell in enumerate(raw):
                        if i < len(cols) and cols[i]:
                            cells[cols[i]] = cell
                        elif cell:
                            extra.append(cell)
                    s = norm_symbol(cells.get("symbol"))
                    this_param = norm_text(cells.get("parameter"))
                    if s:  # 新しい記号の行。継続行は記号と参数を引き継ぐ
                        sym, param = s, this_param
                    else:
                        param = this_param or param
                    unit = norm_value(cells.get("unit")) or unit
                    condition = " ".join(
                        filter(None, [norm_text(cells.get("condition"))]
                               + [norm_text(e) for e in extra]))
                    rows.append({
                        "symbol": sym,
                        "parameter": param,
                        "condition": condition,
                        "min": norm_value(cells.get("min")),
                        "max": norm_value(cells.get("max")),
                        "unit": unit,
                    })
                kept = [r for r in rows if KEEP.match(r["symbol"])]
                if kept:
                    return page.page_number, kept
    return None, []


def read_headline_clock(pdf_path, lang):
    """(page_no, MHz) — 1ページ目付近の特徴リストが謳う系統主頻。無ければ(None, None)。"""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:3]:
            text = page.extract_text() or ""
            values = {m.group(1) for pattern in HEADLINE[lang]
                      for m in pattern.finditer(text)}
            if values:
                # 同一ページに複数表記があるときは高い方（「最高NNMHz」表記）
                return page.page_number, max(values, key=int)
    return None, None


def main():
    with (REPO / "tables/products.csv").open(encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    ds_series = {}
    ds_family = {}
    for p in products:
        ds_series.setdefault(p["datasheet"], set()).add(p["series"])
        ds_family[p["datasheet"]] = p["family"]

    out = []
    for datasheet in sorted(ds_series):
        family = ds_family[datasheet]
        editions = {}
        for lang in ("zh", "en"):
            path = MIRRORS / family / f"datasheet_{lang}" / datasheet
            if not path.exists():
                continue
            page_no, rows = read_edition(path, lang)
            if rows:
                editions[lang] = (page_no, rows)
        if "en" not in editions:
            print(f"{datasheet}: 英語版で対象表が見つからない", file=sys.stderr)
            continue
        en_page, en_rows = editions["en"]
        zh_page, zh_rows = editions.get("zh", (None, []))
        series = ";".join(sorted(ds_series[datasheet]))

        # 行対応は記号ごとの値照合。中国語版は行の増減（極限行の同居等）や
        # rowspanの空単位があるため、序数でなく値で突き合わせる。
        def agrees(zh, en):
            if zh["min"] != en["min"] or zh["max"] != en["max"]:
                return False
            return not (zh["unit"] and en["unit"] and zh["unit"] != en["unit"])

        remaining = list(zh_rows)
        for row in en_rows:
            cands = [z for z in remaining if z["symbol"] == row["symbol"]]
            exact = next((z for z in cands if agrees(z, row)), None)
            if exact:
                remaining.remove(exact)
                confidence = "confirmed"
                basis = f"{datasheet}:zh(p.{zh_page})+{datasheet}:en(p.{en_page})"
            elif cands:
                remaining.remove(cands[0])
                confidence = "conflict"
                diff = ",".join(f"{k}={cands[0][k]}"
                                for k in ("min", "max", "unit")
                                if cands[0][k] != row[k])
                basis = f"{datasheet}:en(p.{en_page})+!{datasheet}:zh({diff})"
            else:
                confidence = "reference"
                basis = f"{datasheet}:en(p.{en_page})"
            out.append({**row, "series": series, "#": "#",
                        "confidence": confidence, "basis": basis,
                        "datasheet": datasheet})

        heads = {}
        for lang in ("zh", "en"):
            path = MIRRORS / family / f"datasheet_{lang}" / datasheet
            if path.exists():
                page_no, value = read_headline_clock(path, lang)
                if value:
                    heads[lang] = (page_no, value)
        if heads:
            value = heads.get("en", heads.get("zh"))[1]
            if len(heads) == 2 and heads["zh"][1] == heads["en"][1]:
                confidence = "confirmed"
                basis = "+".join(f"{datasheet}:{lang}(p.{heads[lang][0]})"
                                 for lang in ("zh", "en"))
            elif len(heads) == 2:
                confidence = "conflict"
                basis = (f"{datasheet}:en(p.{heads['en'][0]})"
                         f"+!{datasheet}:zh(max={heads['zh'][1]})")
            else:
                lang, (page_no, _) = next(iter(heads.items()))
                confidence = "reference"
                basis = f"{datasheet}:{lang}(p.{page_no})"
            out.append({"series": series, "symbol": "F_MAIN",
                        "parameter": "System main frequency", "condition": "",
                        "min": "", "max": value, "unit": "MHz", "#": "#",
                        "confidence": confidence, "basis": basis,
                        "datasheet": datasheet})

    out.sort(key=lambda r: (r["series"], r["symbol"], r["condition"]))
    dest = REPO / "tables/operating_conditions.csv"
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print(f"{dest.relative_to(REPO)}: {len(out)} 行",
          dict(Counter(r["confidence"] for r in out)))


if __name__ == "__main__":
    main()
