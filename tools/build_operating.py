#!/usr/bin/env python3
"""データシートの電気的特性の表 → tables/operating_conditions.csv

各データシートの「General operating conditions / 一般工作条件」表と、
同じ章に並ぶ電気的特性の表（発振器・ADC・Flash・I/O・リセット）から、
**記号のある行**を抽出する。表示テキストは英語版から取り、最小値/典型値/
最大値/単位は中英で照合して一致すれば confirmed。シリーズは products.csv の
(datasheet→series) 結合で展開する。

**採る／採らないは記号の一覧では決めない。** 記号は頭字で物理量を名乗る
（`V_*` は電圧、`I_*` は電流、`t_*` は時間）ので、「その量に単位が合っているか」
で決める（`UNIT_FOR`）。データシートの記法は決まっているので、記号の一覧を
持つより崩れにくく、新しい family の記号も取りこぼさない。

**取れていないもの**（2026-08-29 時点）:

    消費電流の条件つきの行   I_DD は動作条件（`F_HCLK = 48MHz`・`开启`）が
                             min の欄に流れ込む表で書かれていて、値として
                             読めない。表の形の問題で、記号の問題ではない
    添字が `*` に化けた式     `0.45*V+*0.41` は `0.45*V_DD+0.41` のはずだが、
                             文字層に `DD` が残っていないので復元できない
                             （`LOST_SUBSCRIPT` で落とす。推測で埋めない）

典型値の列が必要な理由。発振器は「公称値 + 確度」で規定されていて、
上下限を持たない。HSIは F_HSI の typ が 8MHz や 24MHz で、ばらつきは
ACC_HSI の ±% 側にある。min/max だけを載せると、公称周波数そのものが
落ちる — つまりPLL入力が決まらず、逓倍後のSYSCLKが計算できない。

実行: uv run python tools/build_operating.py [--out <dir>]
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import pdfplumber

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

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
# **記号は頭字で物理量を名乗る。** 採る／採らないを記号の一覧で決めるのではなく、
# 「その頭字が言う量に単位が合っているか」で決める（元からある `UNIT_FOR` の
# 考えを、対象を広げたぶん量も増やして引き継いだもの）。データシートの電気的
# 特性表が使う記法は決まっているので、一覧を持つより崩れにくい。
KEEP = re.compile(r"^(?:[FfTtVIiRCEN]_|C$|E[DLOT0]|ACC_|Du[CT]y_|g_m$|Avg_Slope$|f_|F_)")
# **記号セルが2つの記号を畳んでしまった行は採らない。** `t_/t_r(SCK)_f(SCK)` は
# `t_r(SCK)` と `t_f(SCK)` の2行が、サブスクリプトの折返しで1つになったもので、
# 値がどちらのものか決められない（`f_/t_SCK_SCK`・`C_/C_L1_L2` も同型）。
MERGED_SYMBOL = re.compile(r"^[A-Za-z]+_/")
# 表の見出しが本文の行として読まれることがある（記号欄が `Symbol`、単位欄が
# `Unit`）。ページ内で表が続くときに起きる。
HEADER_ROW = frozenset({"Symbol", "符号", "Parameter", "参数"})
# 頭字 → その量の単位。**上から順に、最初に当たった規則だけを見る**——
# `T_S_vrefint`（ADC のサンプリング時間）は `T_*`（温度）ではなく時間、
# `t_RET`（保持期間）は年、`N_END`（書換回数）は回数で、いずれも一般の
# 規則より先に置かないと弾かれる。単位の大小文字は資料で揺れる（`ms`/`mS`、
# `kΩ`/`KΩ`、`Times`/`times`）ので、比較は大小を無視する。
UNIT_FOR = [
    (re.compile(r"^T_S_"), re.compile(r"^(?:[munp]?s|1/f[A-Za-z]+)$", re.I)),
    (re.compile(r"^t_RET$"), re.compile(r"^years?$", re.I)),
    (re.compile(r"^N_"), re.compile(r"^times?$", re.I)),
    (re.compile(r"^t_VDDA?$"), re.compile(r"^[munp]?s/V$", re.I)),
    (re.compile(r"^[Ff]_"), re.compile(r"^[MmKk]?Hz$")),
    (re.compile(r"^[Tt]_"), re.compile(r"^(?:[munp]?s|1/f[A-Za-z]+|℃)$", re.I)),
    (re.compile(r"^V_|^V$"), re.compile(r"^m?V$")),
    (re.compile(r"^[Ii]_"), re.compile(r"^[munp]?A$", re.I)),
    (re.compile(r"^R_"), re.compile(r"^[kKM]?Ω$")),
    (re.compile(r"^C"), re.compile(r"^[munp]?F$", re.I)),
    (re.compile(r"^E"), re.compile(r"^LSB$", re.I)),
    (re.compile(r"^ACC_"), re.compile(r"^(?:%|ppm)$")),
    (re.compile(r"^Du[CT]y_"), re.compile(r"^%$")),
    (re.compile(r"^g_m$"), re.compile(r"^[munp]?A/V$", re.I)),
    (re.compile(r"^Avg_Slope$"), re.compile(r"^mV/℃$")),
]
# 値の欄に条件文が流れ込むことがある（CH32M007の ACC_HSI は min に
# "HSI_LP = 0 TA = -10℃~70℃" が入る）。一方で上限が別の記号で書かれることは
# 正当で、"F_PCLK1 の max は F_HCLK" はC-5が求めているバス上限そのもの。
# 確度の典型値は符号が ± で書かれる（CH32M030の ACC_LSI は typ が "±500"）。
NUMERIC = re.compile(r"^[-+±]?(?:\d+(?:\.\d+)?|\.\d+)$")
# 式に使ってよい字。空白・`=`・全角はここに無いので、条件文は自動的に外れる。
FORMULA_CHARS = re.compile(r"^[0-9A-Za-z._+\-*/()]+$")
# **`*` が演算子の隣か末尾にあるのは、添字が文字層で `*` に化けた跡。**
# `0.45*V+*0.41` は `0.45*VDD+0.41` のはずで、`*` から `DD` は復元できない
# （兄弟の行を見れば人には分かるが、それは推測になる）。採らずに落とす。
LOST_SUBSCRIPT = re.compile(r"[*][-+*/)]|[-+*/(][*]|[*]$")


def reads_as_value(text: str) -> bool:
    """min/typ/max の欄として採ってよい値か。

    数のほかに、**別の記号で書かれた上限**（`F_HCLK`）と、記号を含む式
    （`0.8*VDD`・`VDD-0.4`・`0.22*(VDD-2.7)+1.55`）を採る。条件文や見出しは
    採らない。

    >>> [reads_as_value(v) for v in ("3.6", "±500", "∞", "0.8*VDD", "VDD-0.4")]
    [True, True, True, True, True]
    >>> [reads_as_value(v) for v in ("F_HCLK", "VREF-", "2*tHCLK")]
    [True, True, True]
    >>> [reads_as_value(v) for v in ("F=8MHzHCLK", "HSI_LP = 0", "关闭", "6～24")]
    [False, False, False, False]
    >>> [reads_as_value(v) for v in ("Enableallperipherals", "0.7*V*", "0.45*V+*0.41")]
    [False, False, False]
    """
    if NUMERIC.match(text) or text == "∞":
        return True
    if not FORMULA_CHARS.match(text) or LOST_SUBSCRIPT.search(text):
        return False
    if any(c.isdigit() for c in text):
        return len(text) <= 24          # 式（数と記号が混じる）
    return len(text) <= 8               # 記号そのもの（`VREFP`・`F_HCLK`）
# 抽出時に潰れた表記の修繕（サブスクリプト割り込み・原文の詰まり）
WIDE_PARENS = str.maketrans({"（": "(", "）": ")"})
SYMBOL_FIX = {"F_HCLK_OrF_SYS": "F_HCLK", "F_HCLK_orF_SYS": "F_HCLK"}
VALUE_FIX = {"FHCLK": "F_HCLK"}
TEXT_REPAIRS = [
    (re.compile(r"^T = (.+?)\s*A$"), r"T_A = \1"),
    (re.compile(r"usedUSB"), "used USB"),
]

COLUMNS = ["series", "symbol", "parameter", "condition",
           "min", "typ", "max", "unit", "#", "confidence", "basis", "datasheet"]

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
    # 添字の括弧は版で全角になる（`C_in（LSE）`）。同じ記号として引けるように揃える。
    sym = sym.translate(WIDE_PARENS)
    sym = SYMBOL_FIX.get(sym, sym)
    # 「F_HCLK or F_SYS」のような複合表記（orは英語版、或は中国語版）は、
    # サブスクリプトの折返しで語順が壊れるため HCLK を含めば F_HCLK に畳む。
    if "HCLK" in sym and not sym.startswith("F_P"):
        sym = "F_HCLK"
    return sym


# 条件欄の添字。`f_S`・`V_DD33`・`T_A` の添字は PDF の文字層で別の行になり、
# 改行を空白で繋ぐと `f > 1MHz S` / `V ≥ 3V DD33` / `T = Ambient A temperature`
# と**孤立した大文字の語**になる（worklist の F-36）。この表に出る添字は
# 数えられるほどしか無いので、孤立したそれを、手前の裸の記号（f / V / T / I が
# 比較演算子の前に単独で立っている所）へ戻す。
SUBSCRIPTS = ("DD33", "DDIO", "DDA", "DD", "SS", "IO", "REF", "A", "S")
BARE_SYMBOL = re.compile(r"(?<![\w_])([fVTI])(?=\s*[=≥≤<>＝~～])")


def attach_subscript(text: str) -> str:
    tokens = text.split(" ")
    for i, token in enumerate(tokens):
        if token in SUBSCRIPTS and i > 0:
            head = " ".join(tokens[:i])
            m = BARE_SYMBOL.search(head)
            if m:
                head = head[:m.start(1)] + f"{m.group(1)}_{token}" + head[m.end(1):]
                return attach_subscript(" ".join([head] + tokens[i + 1:]))
    return text


def norm_text(cell):
    text = re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()
    for pattern, repl in TEXT_REPAIRS:
        text = pattern.sub(repl, text)
    return attach_subscript(text)


# 値の欄でも添字は離れて出る。条件欄の `attach_subscript` と同じ壊れ方で、
# `V_DD-0.4` が `V-0.4DD`、`0.45*V_DD+0.41` が `0.45*V+DD0.41` になる。
# **添字を、離れた場所から裸の記号のうしろへ戻す。**
VALUE_SUBSCRIPTS = ("DD33", "DDIO", "DDA", "DD8", "CC12V", "HCLK", "SCK", "DD", "IO")
BARE_BASE = re.compile(r"(?<![A-Za-z])([VtIfCRT])(?![A-Za-z])")
# 小数点のあとに数が続かない＝添字を数の途中から抜いてしまった跡。
BROKEN_NUMBER = re.compile(r"\d\.(?!\d)|\.\.")


def attach_value_subscript(value: str) -> str:
    """離れて出た添字を、裸の記号のうしろへ戻す。

    >>> attach_value_subscript("V-0.4DD")
    'VDD-0.4'
    >>> attach_value_subscript("0.45*V+DD0.41")
    '0.45*VDD+0.41'
    >>> attach_value_subscript("0.22*(V-DD2.7)+1.55")
    '0.22*(VDD-2.7)+1.55'
    >>> attach_value_subscript("V-0.5DD33"), attach_value_subscript("0.5t-4SCK")
    ('VDD33-0.5', '0.5tSCK-4')

    すでに記号に付いているものは動かさない。

    >>> attach_value_subscript("0.8*VDD"), attach_value_subscript("15-0.5tSCK")
    ('0.8*VDD', '15-0.5tSCK')

    **添字が数の途中に落ちることがある。** `0.41*(V-1.DD8)+1.3` の `DD` は
    `1.8` を割って入っている。長いほうから当てると `DD8` を添字と読んで
    `(VDD8-1.)` という壊れた数が残るので、**数が壊れない読みだけを採る**。

    >>> attach_value_subscript("0.41*(V-1.DD8)+1.3")
    '0.41*(VDD-1.8)+1.3'
    """
    for sub in VALUE_SUBSCRIPTS:
        at = value.find(sub)
        if at <= 0 or value[at - 1].isalpha():
            continue
        bare = None
        for m in BARE_BASE.finditer(value[:at]):
            bare = m
        if bare is None:
            continue
        rest = value[:at] + value[at + len(sub):]
        candidate = rest[:bare.end(1)] + sub + rest[bare.end(1):]
        if BROKEN_NUMBER.search(candidate):
            continue          # この添字の読みは数を割ってしまう。次を試す
        return candidate
    return value


def norm_value(cell):
    value = FOOTNOTE.sub("", norm_text(cell)).replace(" ", "")
    return VALUE_FIX.get(value, attach_value_subscript(value))


DROPPED: list[str] = []


def keep_row(row, lang, page_no):
    """その行を採るか。記号・単位・値がそれぞれ噛み合っていることを確かめる。

    表の継承（記号セルが空の続き行）は多条件の行には正しいが、別のパラメータが
    続いている場合は記号を取り違える。単位と値で弾けるので弾く。
    """
    symbol = row["symbol"]
    if symbol in HEADER_ROW:
        return False          # 表の見出しが本文として読まれたもの。黙って落とす
    if not KEEP.match(symbol):
        return False
    if MERGED_SYMBOL.match(symbol):
        DROPPED.append(f"{lang} p.{page_no} {symbol}: 2つの記号が1行に畳まれている")
        return False
    unit = row.get("unit") or ""
    # **最初に当たった規則だけを見る。** 具体的なものを上に置いてあるので、
    # `T_S_vrefint` は `T_*`（温度）ではなく `T_S_*`（時間）として見られる。
    for name, want in UNIT_FOR:
        if not name.match(symbol):
            continue
        if unit and not want.match(unit):
            DROPPED.append(f"{lang} p.{page_no} {symbol}: 単位が {unit!r} "
                           "なので別の行の続き")
            return False
        break
    for key in ("min", "typ", "max"):
        value = row.get(key) or ""
        if value and not reads_as_value(value):
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
                        "typ": norm_value(cells.get("typ")),
                        "max": norm_value(cells.get("max")),
                        "unit": unit,
                    })
                kept = [r for r in rows if keep_row(r, lang, page.page_number)]
                if kept:
                    found += [{**r, "_page": page.page_number} for r in kept]
    return found


# USB のクロックは表ではなく散文にある。**48MHz は全 family の話ではない**——
# USBHS/USBSS を持つ family（CH32V407/V467、CH32X315）は専用 PLL を別に持ち
# （480MHz・625MHz・357MHz・125MHz・320MHz）、48MHz の USBCLK を一切使わない。
# 全文書を走査して確かめた（worklist の F-9）。全速側の block 名を必ず伴う形で
# だけ拾えば、高速側の family には当たらない——あちらの文に 48MHz は出てこない。
FULL_SPEED = re.compile(r"USBD|USBFS|USBHD|USBCLK|USBClock|OTG_FS", re.IGNORECASE)
# `\b48` は使えない。中文は「的48MHz时钟」と続けて書き、CJK も語構成文字なので
# 境界にならず、CH32X035 の中文版だけ取り逃す。数字の続きでないことだけ見る。
MHZ_48 = re.compile(r"(?<![\d.])48\s*MHz", re.IGNORECASE)
# 「USB を使うなら CPU はこの周波数のどれか」。**family ごとに違う**
# （V103 は 48/72、L103 は 48/72/96、V20x・V30x は 48/96/144）ので、
# 分周器から導かず資料の列挙をそのまま採る。資料が直接書いている。
# 英語版は "the CPU frequency must be" とも "CPU must be" とも書く（CH32V103 は
# 「the frequency of using PLL, CPU must be 48MHz or 72MHz」）。文が USB の話で
# あることは窓の中の USB で確かめるので、CPU 側の言い回しは緩めてよい。
CPU_WITH_USB = {
    "zh": re.compile(r"CPU\s*的频率必须是(?P<list>[^。；]*)"),
    "en": re.compile(r"CPU\s+(?:frequency\s+|clock\s+speed\s+)?must\s+be(?P<list>[^.;]*)",
                     re.IGNORECASE),
}
USB_MENTIONED = re.compile(r"USB", re.IGNORECASE)
MHZ_VALUE = re.compile(r"(\d+(?:\.\d+)?)\s*MHz", re.IGNORECASE)


def scan_prose(pdf_path, hit):
    """ページ本文を1行と次行の窓で読み、hit が返した値を (page_no, 値) で返す。

    折り返しで文が2行に割れるため、行単体ではなく隣接2行の窓を渡す。最初に
    当たったページで止める——同じ事実が章ごとに繰り返されるだけなので。
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            for i, _ in enumerate(lines):
                found = hit(" ".join(lines[i:i + 2]))
                if found:
                    page_no = page.page_number
                    page.flush_cache()
                    return page_no, found
            page.flush_cache()
    return None, None


def read_usb_clock(pdf_path, lang):
    """(page_no, "48") — 全速 USB block が 48MHz を要求すると書いてあれば。"""
    def hit(window):
        if FULL_SPEED.search(window) and MHZ_48.search(window):
            return "48"
        return None
    return scan_prose(pdf_path, hit)


def read_cpu_with_usb(pdf_path, lang):
    """(page_no, ["48", "96", "144"]) — USB 使用時に許される CPU 周波数の列挙。"""
    pattern = CPU_WITH_USB[lang]

    def hit(window):
        found = pattern.search(window)
        if not found or not USB_MENTIONED.search(window):
            return None
        values = MHZ_VALUE.findall(found.group("list"))
        return values or None
    return scan_prose(pdf_path, hit)


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
    # **`--out` が無いと安全に試せない。** 他の生成器はどれも試験用の出力先を
    # 受けるのに、この tool だけ受けず、`--out` を渡しても黙って無視して
    # `evidence/` に書いていた。抽出を変えて様子を見るのに正本を上書きするしか
    # 手が無い、というのは事故のもとで、実際に一度やった（2026-08-29）。
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    args = ap.parse_args()
    with paths.table("products").open(encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    ds_series = {}
    ds_family = {}
    for p in products:
        ds_series.setdefault(p["datasheet"], set()).add(p["series"])
        ds_family[p["datasheet"]] = p["family"]
    with paths.table("families").open(encoding="utf-8") as f:
        family_manuals = {r["family"]: r["reference_manuals"]
                          for r in csv.DictReader(f)}

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
            # 単位と典型値は、片方の版だけが列を持つことがある（rowspanの空セル、
            # 版によって典型値の列を落とす表）。空は不一致ではないので、
            # 両方が値を持つときだけ突き合わせる。
            for key in ("unit", "typ"):
                if zh[key] and en[key] and zh[key] != en[key]:
                    return False
            return True

        remaining = list(zh_rows)
        for row in en_rows:
            cands = [z for z in remaining if z["symbol"] == row["symbol"]]
            exact = next((z for z in cands if agrees(z, row)), None)
            en_page = row.pop("_page")
            if exact:
                remaining.remove(exact)
                # 表示テキストは英語版から取るが、典型値は数値なので言語に
                # 依らない。英語版が列を落としていれば中国語版で埋める。
                if not row["typ"] and exact["typ"]:
                    row["typ"] = exact["typ"]
                confidence = "confirmed"
                basis = (f"{datasheet}:zh(p.{exact['_page']})"
                         f"+{datasheet}:en(p.{en_page})")
            elif cands:
                remaining.remove(cands[0])
                confidence = "conflict"
                diff = ",".join(f"{k}={cands[0][k]}"
                                for k in ("min", "typ", "max", "unit")
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
                        "min": "", "typ": "", "max": value, "unit": "MHz", "#": "#",
                        "confidence": confidence, "basis": basis,
                        "datasheet": datasheet})

        # USB のクロックは表ではなく散文にあり、しかも **datasheet に無く
        # reference manual にしか無い family がある**（CH32L103 の CPU 周波数、
        # CH32H417 の 48MHz）。family の manual も読む。
        papers = [datasheet] + [d for d in (family_manuals.get(family) or "").split(";") if d]
        for symbol, reader, parameter in (
                ("F_USBCLK", read_usb_clock, "USB module clock frequency"),
                ("F_HCLK(USB)", read_cpu_with_usb,
                 "CPU frequency permitted while USB is in use")):
            seen = {}
            for paper in papers:
                for lang in ("zh", "en"):
                    path = MIRRORS / family / f"datasheet_{lang}" / paper
                    if path.exists() and (paper, lang) not in seen:
                        page_no, value = reader(path, lang)
                        if value:
                            seen[(paper, lang)] = (page_no, value)
                if seen:
                    break  # 同じ事実を章ごとに繰り返すだけなので最初の文書で足りる
            if not seen:
                continue
            paper = next(iter(seen))[0]
            langs = {lang for (_, lang) in seen}
            readings = {lang: seen[(paper, lang)] for lang in langs}
            value = readings.get("en", readings.get("zh"))[1]
            if len(readings) == 2 and readings["zh"][1] == readings["en"][1]:
                confidence = "confirmed"
                basis = "+".join(f"{paper}:{lang}(p.{readings[lang][0]})"
                                 for lang in ("zh", "en"))
            elif len(readings) == 2:
                confidence = "conflict"
                basis = (f"{paper}:en(p.{readings['en'][0]})"
                         f"+!{paper}:zh(={readings['zh'][1]})")
            else:
                lang = next(iter(readings))
                confidence = "reference"
                basis = f"{paper}:{lang}(p.{readings[lang][0]})"
            # 許容値の列挙は min/typ/max では表せないので1値1行にする。
            for one in (value if isinstance(value, list) else [value]):
                out.append({"series": series, "symbol": symbol,
                            "parameter": parameter, "condition": "USB in use",
                            "min": one if symbol == "F_USBCLK" else "",
                            "typ": one,
                            "max": one if symbol == "F_USBCLK" else "",
                            "unit": "MHz", "#": "#", "confidence": confidence,
                            "basis": basis, "datasheet": paper})

    # **同じ事実を2度書かない。** 1ページに PLL の表が変種ごとに複数あり
    # （CH32V20x_30xDS0 の p.60/p.68 は F_PLL_OUT が 144／75／100MHz の3表）、
    # F_PLL_OUT は表ごとに違うが F_PLL_IN は 3〜25MHz と同じことを書く表が
    # 2つある。この表はどの表から来たかを持たない（列がない）ので、両者は
    # 完全同一行になる——数える意味のない重複で、CH32V303/305/307/317 の
    # F_PLL_IN が2行あった。値・確度・根拠まで同じ行は1行にする。
    seen: set[tuple] = set()
    unique = []
    for r in out:
        key = tuple(r.get(c, "") for c in COLUMNS)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    if len(unique) != len(out):
        print(f"完全同一の重複行を落とした: {len(out) - len(unique)} 行", file=sys.stderr)
    out = unique

    out.sort(key=lambda r: (r["series"], r["symbol"], r["condition"], r["typ"]))
    dest = paths.table("operating_conditions", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    shown = dest.relative_to(REPO) if dest.is_relative_to(REPO) else dest
    print(f"{shown}: {len(out)} 行",
          dict(Counter(r["confidence"] for r in out)))
    if DROPPED:
        print(f"  噛み合わないので採らなかった行 {len(DROPPED)}:", file=sys.stderr)
        for line in dict.fromkeys(DROPPED):
            print(f"    - {line}", file=sys.stderr)


if __name__ == "__main__":
    main()
