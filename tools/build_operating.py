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

# 対象の表。「一般動作条件」に加えて発振器の表も読む。後者はクロック源の
# 許容範囲と確度で、R-24のC-2（HSIの確度・HSEの許容範囲）がここにある。
# 表題は表のキャプションなので、そのページの表を読む形は同じ。
MARKER = {
    "en": re.compile(
        r"General\s+operating\s+conditions"
        r"|(?:Internal|External)\s+(?:high|low)[-\s]speed"
        r"|From\s+external\s+(?:high|low)[-\s]speed\s+clock"
        r"|(?:High|Low)[-\s]speed\s+external\s+clocks?\s+generated"
        # 周辺固有のクロック上限。ADCは ADCCLK に独自の上限を持ち、しかも
        # familyで違う（CH32V103は14MHz、CH32V003は12MHz）。表題は
        # "ADC characteristics" と "10-bit ADC characteristics" が混在する。
        r"|(?:\d+[-\s]?bit\s+)?ADC\s+characteristic",
        re.IGNORECASE),
    "zh": re.compile(
        r"[通一]\s*[用般]\s*工\s*作\s*条\s*件"
        r"|内\s*部\s*(?:高|低)\s*速"
        r"|来\s*自\s*外\s*部\s*(?:高|低)\s*速\s*时\s*钟"
        r"|谐\s*振\s*器\s*产\s*生\s*的\s*(?:高|低)\s*速\s*外\s*部\s*时\s*钟"
        r"|(?:\d+\s*位\s*)?ADC\s*特\s*性"),
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
# クロック上限と主電源電圧、そして発振器の周波数・確度・デューティ。
# 起動時間や消費電流（t_SU、I_DD）は同じ表にあるが、クロックの事実ではない
# ので採らない。
# ADCのクロック上限だけは記号が小文字 f で始まる（"f ADC"）。
KEEP = re.compile(r"^F_|^f_ADC$|^V_?DD$"
                  r"|^ACC_(?:HSI|LSI|HSE|LSE)|^DuCy_(?:HSI|LSI|HSE|LSE)")
# 継承した記号が行の中身と合わないことがある。発振器の表はデューティ比の行が
# 記号セル空で続くため、F_* の行に単位 % が付く。単位で弾ける。
UNIT_FOR = [(re.compile(r"^[Ff]_"), re.compile(r"^(?:[MmKk]?Hz)$")),
            (re.compile(r"^V_"), re.compile(r"^m?V$")),
            (re.compile(r"^ACC_"), re.compile(r"^(?:%|ppm)$")),
            (re.compile(r"^DuCy_"), re.compile(r"^%$"))]
# 値の欄に条件文が流れ込むことがある（CH32M007の ACC_HSI は min に
# "HSI_LP = 0 TA = -10℃~70℃" が入る）。一方で上限が別の記号で書かれることは
# 正当で、"F_PCLK1 の max は F_HCLK" はC-5が求めているバス上限そのもの。
# 数値か、空白を含まない短い記号なら採る。
NUMERIC = re.compile(r"^[-+]?(?:\d+(?:\.\d+)?|\.\d+)$")
SYMBOLIC = re.compile(r"^[0-9.]*[A-Za-z][A-Za-z0-9_.+]{0,15}$")
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
    sym = FOOTNOTE.sub("", "_".join(parts))
    # 添字はセル内で改行にも空白にもなる。"F HSE_ext" は F_HSE_ext、
    # "ACC HSI" は ACC_HSI。空白を消してしまうと FHSE_ext になり引けない。
    # 脚注を落とした跡が空白として残るので（"V (6)\nDD" → "V _DD"）、
    # 連続したアンダースコアは1つに畳む。
    sym = re.sub(r"[\s_]+", "_", sym).strip("_")
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


DROPPED: list[str] = []


def keep_row(row, lang, page_no):
    """その行を採るか。記号・単位・値がそれぞれ噛み合っていることを確かめる。

    表の継承（記号セルが空の続き行）は多条件の行には正しいが、別のパラメータが
    続いている場合は記号を取り違える。単位と値で弾けるので弾く。
    """
    symbol = row["symbol"]
    if not KEEP.match(symbol):
        return False
    unit = row.get("unit") or ""
    for name, want in UNIT_FOR:
        if name.match(symbol) and unit and not want.match(unit):
            DROPPED.append(f"{lang} p.{page_no} {symbol}: 単位が {unit!r} なので別の行の続き")
            return False
    for key in ("min", "max"):
        value = row.get(key) or ""
        if value and not (NUMERIC.match(value) or SYMBOLIC.match(value)):
            DROPPED.append(f"{lang} p.{page_no} {symbol}: {key} が {value[:28]!r}")
            return False
    return True


def read_edition(pdf_path, lang):
    """対象表の行。行ごとに読み取ったページ番号を `_page` で持つ。

    対象表は1ページに収まらない。一般動作条件のほかに発振器の表が5つあり
    （HSI/LSI/外部高速/外部低速/水晶）、それぞれ別ページにある。最初に見つけた
    ページで打ち切ると一般動作条件しか取れない。
    """
    marker = MARKER[lang]
    found = []
    carry = False
    last_cols = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            hit = bool(marker.search(text))
            if not hit and not carry:
                continue
            # 表はページを跨ぐ。CH32V003の "Table 3-23 ADC characteristics" は
            # キャプションがp28で、ADCクロック上限の行はp29にある。キャプションの
            # 無い続きページも1ページだけ見る。列の並びが同じ表しか読まないので、
            # 無関係な表を拾っても記号の絞り込みで落ちる。
            carry_from, carry = carry and not hit, hit
            for tbl in page.extract_tables():
                cols = [norm_header(c) for c in tbl[0]]
                body = tbl[1:]
                # 条件列は動作条件表にしかない（絶対最大定格表は符号+描述のみ）
                if {"symbol", "min", "condition"} <= set(cols):
                    last_cols = cols
                elif (carry_from and last_cols
                      and len(tbl[0]) == len(last_cols)):
                    # 続きページの表はヘッダ行を持たない。列数が同じなら直前の
                    # 並びをそのまま当てる。CH32V003のADCクロック上限の行は
                    # このページにしかない。
                    cols, body = last_cols, tbl
                else:
                    continue
                rows, sym, unit, param = [], "", "", ""
                for raw in body:
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
                kept = [r for r in rows if keep_row(r, lang, page.page_number)]
                if kept:
                    found += [{**r, "_page": page.page_number} for r in kept]
    return found


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
            rows = read_edition(path, lang)
            if rows:
                editions[lang] = rows
        if "en" not in editions:
            print(f"{datasheet}: 英語版で対象表が見つからない", file=sys.stderr)
            continue
        en_rows = editions["en"]
        zh_rows = editions.get("zh", [])
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
            en_page = row.pop("_page")
            if exact:
                remaining.remove(exact)
                confidence = "confirmed"
                basis = (f"{datasheet}:zh(p.{exact['_page']})"
                         f"+{datasheet}:en(p.{en_page})")
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
    if DROPPED:
        print(f"  噛み合わないので採らなかった行 {len(DROPPED)}:", file=sys.stderr)
        for line in dict.fromkeys(DROPPED):
            print(f"    - {line}", file=sys.stderr)


if __name__ == "__main__":
    main()
