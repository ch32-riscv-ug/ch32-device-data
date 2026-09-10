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

`tools/build_operating.py`（凍結tool。PDFをpdfplumberで直読み）からpdfplumber依存だけを
外した移植（2026-09-09。退役の第8号）。`operating_conditions.csv`の正本生成器は
`build_operating_conditions.py`で、そちらが**このmoduleをライブラリとして**呼ぶ
（基礎行の組み立て・記号と値の正規化・行の採否）。読む欄はbundleの`text`（ページ本文）と
`tables[].extracted_rows`（`Table.extract()`の平坦化行）だけで、抽出の規則は1行も変えていない。
ページの読み手は`pipeline/extract/bundle_pages.py`（sha照合つき）。

移植で消えたもの: `pdfplumber`のimport、mirrorのパス組み立て（bundle名`<stem>.<lang>`で引く）、
`page.flush_cache()`（`bundle_pages.pages`はgeneratorでページを溜めない）。**呼ぶ側が
`operating.pdfplumber = pdfcompat`を差し替える必要も無くなった**——原本を開かないので、
据え置き（`--hold-sources`）でもゲートと食い違わない。

実行: uv run python pipeline/extract/datasheet/operating_rows.py [--out <dir>]
"""

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402
import wrap_rules  # noqa: E402


def _bundle(document: str, lang: str) -> str | None:
    """原本のPDF名と言語 → bundle名。無ければNone（`path.exists()`の置き換え）。"""
    name = f"{Path(document).stem}.{lang}"
    return name if (bundle_pages.BUNDLES / name / "manifest.json").exists() else None
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
# **表題で選ぶ表**（ページの見出し語では届かないもの）。`MARKER`はページ本文に見出し語が
# 出るページ＋続き1ページの表を読む規則で、pdfplumberの`extract_tables()`が表題を持たない
# ことに由来する（凍結toolはページ単位でしか選べなかった）。bundleは表ごとに表題を持つので、
# **表そのもの**を選べる——ページの隣接に依らないので、章が伸びて表がずれても届く。
#
# 出力電圧特性の表を足した。全corpus実測: 48表あり、**31表がページ規則では届いていなかった**
# （版で非対称なのが特に悪く、`CH32V103DS0` は zh だけ届いて en が届かない——片翼だけ増えると
# zh/en の対応がずれて既存の行が消える。ページ規則を緩める案は実際に34行を消した）。
# `CH32X035DS0.zh` V2.3 が出力電圧特性をポート群ごとに分けたとき、章が伸びて見出し語が
# p26→p25 に動き、新しい表（p27）が窓の外に出たのが再突入の詰まりだった。
#
# ページ規則で届くページは**そのページの表を全部**見る（従来のまま）。表題で届いた表は
# **その表だけ**を見る——ページを丸ごと開くと隣の無関係な表まで入る。
# OPA/CMP の特性表も足した（2026-09-09）。X035 V2.3 の取り込みで残った唯一の誤り
# （`V_DD Recommended not less than 2.5V` の偽 conflict）の原因がこれだった——正しい相手は
# zh p.34 `表3-26 OPA运放特性`／p.35 `表3-27 CMP电压比较器特性` の `建议不低于2.5V 2/5/5.5` で
# en 行と値も条件も完全一致するのに、**その2ページが窓の外**だった（読めていた zh は
# 9・23–27・32・33 だけ。en は OPA 表 p.37 に届いていたので片翼だけ入り、相手を失った en 行が
# p.32 ADC 表の `额定性能` を取って偽の conflict になった）。
#
# 表題は `OPA`／`CMP` を含み、かつ `特性`／`characteristic` を含むもの（後読み）。全corpus実測:
# OPA/CMP を含む表78のうち**68が特性表で全部当たり**、残る10は`引脚功能`／`Pin Functions`で
# **全部落ちる**（pin表を電気特性に混ぜない）。**zh/en の表数は全文書で対称**
# （H417 3/3・L103 4/4・M030 6/6・V003 1/1・V006DS0 2/2・V007 4/4・V203 1/1・V205 4/4・
# V208 1/1・V20x_30x 2/2・V407 2/2・X035 2/2）——片翼だけ増えると zh/en の対応が崩れて
# 既存の行が消えるので、これが入れる前提だった。`CH32V006DS2` は zh 4・en 0 だが
# 目録範囲外の文書（対象SKUがproductsに無い）。
TABLE_CAPTION = re.compile(
    r"输\s*出\s*电\s*压\s*特\s*性"
    r"|Output\s+voltage\s+characteristic"
    r"|(?:OPA|CMP)(?=.*特\s*性)"
    r"|(?:OPA|CMP)(?=.*characteristic)",
    re.IGNORECASE)

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
# **脚注の括弧が添字を挟んで割れる。** `CH32V007DS0.en` p.63 の記号セルは
# `V (2⏎OHSAT⏎)` で、閉じ括弧が添字のうしろに落ちている（同じ表の次ページは
# `V (2)⏎OHSAT` で正しい）。`FOOTNOTE` は `(2)` の形しか落とさないので、
# 行を `_` で繋ぐと **`V_(2_OHSAT_)` という記号**になっていた。
# 全corpus実測: この壊れ方をするのは `V_OHSAT`・`V_OLSAT` の4行だけ。
FOOTNOTE_SPLIT = re.compile(r"[（(]\d+\s*\n\s*([A-Za-z]\w*)\s*\n?\s*[）)]")
# 中文だけの表記。`operating_conditions.csv`は**CJKを1文字も含まない英語の表**（表示テキストは
# 英語版から取る設計。実測: 2,797行の parameter/condition に CJK は0）。zh だけが持つ行を出すときも
# その性格を保つ——中文の項目名を入れない（下の`zh_only_rows`）。
CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
# **記号は頭字で物理量を名乗る。** 採る／採らないを記号の一覧で決めるのではなく、
# 「その頭字が言う量に単位が合っているか」で決める（元からある `UNIT_FOR` の
# 考えを、対象を広げたぶん量も増やして引き継いだもの）。データシートの電気的
# 特性表が使う記法は決まっているので、一覧を持つより崩れにくい。
KEEP = re.compile(r"^(?:[FfTtVIiRCEN]_|C$|E[DLOT0]|ACC_|Du[CT]y_|g_m$|Avg_Slope$|f_|F_)")
# **記号セルが2つの記号を畳んでしまった行は採らない。** `t_/t_r(SCK)_f(SCK)` は
# `t_r(SCK)` と `t_f(SCK)` の2行が、サブスクリプトの折返しで1つになったもので、
# 値がどちらのものか決められない（`f_/t_SCK_SCK`・`C_/C_L1_L2` も同型）。
# 添字を行で対応づけられるようになって綴りが変わった（`f_/t_SCK_SCK` → `f_SCK/t_SCK`）ので、
# **斜線の右にも添字がある**形を足す。`V_POR/PDR` のように斜線が1つの名前の中にあるものは
# 右側に `_` が無いので残る。
MERGED_SYMBOL = re.compile(r"^[A-Za-z]+_/|/[A-Za-z]+_")
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
# `I_LOAD_PG_A` は**添字そのものが2行に割れた**跡（`CH32V007DS0.en` p.62 のセルは
# `I⏎LOAD_PG⏎A`。同じ文書の p.63 と中文版は `I⏎LOAD_PGA` で正しい）。行を `_` で繋ぐ
# のが既定なので、割れ目に `_` が入ってしまう——一般に「単独の大文字は添字だから `_` で
# 繋ぐ」（`V (2)⏎DD` → `V_DD`）のが正しいので、ここだけ綴りで直す。
# 全corpus実測: `_` を除くと同じになる記号の組はこの1組だけ。
SYMBOL_FIX = {"F_HCLK_OrF_SYS": "F_HCLK", "F_HCLK_orF_SYS": "F_HCLK",
              "I_LOAD_PG_A": "I_LOAD_PGA"}
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


# 表全体に掛かる限定が**条件ヘッダの中に**書かれている形（`条件：V_DD = 5V`／
# `Condition: V_DD = 5V`）。これを`条件`と読めないと`{symbol,min,condition}`が揃わず、
# 表そのものが落ちる。全corpus実測で**4表だけ**——`CH32X035DS0` の OPA/CMP 特性表
# （zh 2・en 2）。素の`条件`ヘッダは1,053表なので、これは例外の形。
#
# **限定そのものは行に写さない。** 表全体の条件を持つ列が無いので、写すには表の設計を
# 変えるか条件欄に混ぜるかしかなく、混ぜると`V_DD 供电电压 建议不低于2.5V`の行が
# `V_DD = 5V, Recommended not less than 2.5V`という自己矛盾した書き方になる。
# en 側の同じ行は隣接ページの繰り越しで**すでに限定なしで正本に入っている**ので、
# zh を足すことで悪くはならない（表全体の条件を表せないことは既知の穴として記録）。
CONDITION_HEADER = re.compile(r"^\s*(?:条\s*件|condition)\s*[：:]", re.IGNORECASE)


# **表の範囲**（食い違いの相手を絞るのに使う）。表題に出る**大文字の略語**の集合。
# 略語は両版で同じ綴りで出るので言語に依らない——`表3-37-1 CMP1特性` と
# `Table 3-37-1 CMP1 characteristics` はどちらも `{CMP1}`、`表3-36-3 OPA3和OPA4特性` と
# `Table 3-36-3 OPA3 and OPA4 characteristics` はどちらも `{OPA3, OPA4}`。表番号は使わない
# ——版で振り方が違う（`CH32X035DS0` の OPA 表は zh 3-26・en 3-24）。
#
# なぜ要るか: 記号は**同じ文書の複数の表に出る**（`V_hys`・`t_D`・`I_DDOPAMP` は OPA/CMP の
# 表ごとに別の値を持つ）。記号だけで突き合わせると、片版で行数が違うときに余りが
# **別の表の行**と組んで**偽の食い違い**になる。実測（OPA/CMP の特性表を読めるようにした
# 2026-09-09）: `CH32M030DS0` は zh が CMP2 の表に、en が CMP1 の表に同じ記号を置いていて
# `I_DDOPAMP`(35/55)・`V_hys`(100/5・200/50)・`t_D`(40/30) の4件が偽の食い違いになり、
# `CH32V007DS0` は en の CMP2 の `V_hys` が zh の一般I/Oの `V_hys`(min=150) と組んだ。
# **一致するのは confirmed（値が一致）のときは要求しない**——値が一致するなら別の表でも
# 同じ規格の裏付けとして正しい。
# 略語の取り方は2つ捨てるものがある。(1) **括弧の中**——zh の表題は周波数を括弧で足すことが
# あり（`表4-12 …低速外部时钟（fLSE=32.768KHz）`）、en 側（`Table 4-12 Low-speed external
# clock generated from…`）には無いので**版で非対称な鍵**になる。両版が括弧で書く修飾
# （`（高速模式）`/`(High-speed mode)`）は略語を持たないので落としても同じ。
# (2) **単位の綴り**——`MHz`・`KHz` は `MH`・`KH` に化ける。大文字の直後が小文字なら単位と
# みなして採らない（`HSI)`・`OPA3 `・`CMP1特`は採る）。
TABLE_ACRONYM = re.compile(r"[A-Z]{2,}[0-9]*(?![a-z])")
PARENTHESISED = re.compile(r"[（(][^）)]*[）)]")


def table_scope(caption: str) -> frozenset:
    return frozenset(TABLE_ACRONYM.findall(PARENTHESISED.sub(" ", caption or "")))


def column_edges(record: dict) -> list[float]:
    """表の列の境界（セルの左端＋表の右端）。続きの断片かを幾何で確かめるのに使う。"""
    xs = {round(cell["bbox"][0], 1) for cell in record.get("cells", []) if "bbox" in cell}
    if "bbox" in record:
        xs.add(round(record["bbox"][2], 1))
    return sorted(xs)


def same_edges(a: list[float], b: list[float], tol: float = 2.0) -> bool:
    """列の境界がだいたい同じか（同じ表の続きなら版面が同じなので揃う）。

    >>> same_edges([10.0, 50.0, 90.0], [10.4, 50.0, 91.5])
    True
    >>> same_edges([10.0, 50.0, 90.0], [10.0, 60.0, 90.0])
    False
    >>> same_edges([10.0], [10.0, 50.0])
    False
    """
    return (bool(a) and len(a) == len(b)
            and all(abs(x - y) <= tol for x, y in zip(a, b)))


def norm_header(cell):
    if CONDITION_HEADER.search(cell or ""):
        return "condition"
    text = FOOTNOTE.sub("", (cell or "")).replace(" ", "").replace(".", "")
    return HEADER_MAP.get(text.lower() if text.isascii() else text)


# 記号セルの末尾に付く**ピン群**（`VOH（PA0-PA23）`・`VOL（PC0-PC7，PC14-…）`）。これは記号の
# 一部ではなく**適用範囲の条件**なので、条件欄へ回す（`split_pin_group`）。
#
# 2026-09-09に`CH32X035DS0.zh` V2.3が出力電圧特性をポート群ごとに分け（PAは50mA、PBは6/10mA、
# PCは8/16mA）、記号が`VOH（PA0-PA23）`になった。`norm_symbol`はそれを`VOH_(PA0-PA23)`にし、
# `keep_row`の白名簿`KEEP`（`V_`の形しか通さない）が**全部落としていた**。落ちると en 版の
# 一般I/O行が相手を失い、別表（p32の静态输出高电平）の`V_OH`と突き合わされて**偽のconflict**に
# なる。記号を`V_OH`に戻し、群を条件に置けばその取り違えが消える。
#
# **括弧つきの記号は他にもある**が、そちらは下付きの修飾で記号の一部（`t_SU(LSI)`・`I_DD(HSI)`・
# `C_in(HSE)`・`F_max(IO)out`・`V_IH(RST)`）。全corpus実測: 括弧を含む記号は399件・31種類で、
# **ピン群は0件**——だから「`P`＋英字＋数字で始まる中身」に絞れば既存の記号は1つも動かない。
# 閉じ括弧は無くてもよい（セルが`（PC0-PC7，⏎PC14-PC1`で切れている実例がある）。
PIN_GROUP = re.compile(r"[（(]\s*(?P<group>P[A-Z]\d[^）)]*?)\s*[）)]?\s*$")


def split_pin_group(cell):
    """記号セル → (ピン群を外した記号セル, ピン群 or "")。"""
    text = cell or ""
    flat = " ".join(text.split())
    m = PIN_GROUP.search(flat)
    if not m:
        return cell, ""
    # 群はピンの並びなので、区切りの全角読点は半角へ（`PC0-PC7， PC14-PC19`）。この表は
    # CJK を1文字も含まない英語の表なので、群を条件へ置くときに全角が混ざると弾かれてしまう。
    group = m.group("group").replace("，", ",").replace("、", ",")
    return flat[:m.start()].strip(), " ".join(group.split())


def norm_symbol(cell):
    # 添字を挟んで割れた脚注を先に畳む（`V (2⏎OHSAT⏎)` → `V ⏎OHSAT`）。
    cell = FOOTNOTE_SPLIT.sub(lambda m: "\n" + m.group(1), cell or "")
    # **基底が1行目に並び添字が2行目に並ぶ組版**は、行を`_`で繋ぐだけでは読めない
    # （`V -V`／`DD SS` は `V_-V_DD_SS` になってしまう）。絶対最大定格表を読み始めて
    # 実物が出たので呼ぶ（`V_DD-V_SS`・`V_HV-GND`・`|△V_DD_x|`。全corpus 30セル）。
    # **記号は2行のときだけ**——3行以上は添字そのものが割れた形で、最後の行を添字と
    # 読むと語順が壊れる（`I⏎LOAD_PG⏎A` は `I_LOAD_PGA`。`I_A_LOAD_PG` になっていた）。
    if len([x for x in cell.split("\n") if x.strip()]) == 2:
        paired = pair_line_subscripts(cell, sep="_")
        if paired is not None:
            cell = paired
    parts = [p.strip() for p in cell.split("\n") if p.strip()]
    sym = FOOTNOTE.sub("", "_".join(parts))
    # 添字はセル内で改行にも空白にもなる。"F HSE_ext" は F_HSE_ext、
    # "ACC HSI" は ACC_HSI。空白を消してしまうと FHSE_ext になり引けない。
    # 脚注を落とした跡が空白として残るので（"V (6)\nDD" → "V _DD"）、
    # 連続したアンダースコアは1つに畳む。
    sym = re.sub(r"[\s_]+", "_", sym).strip("_")
    # 添字の括弧は版で全角になる（`C_in（LSE）`）。同じ記号として引けるように揃える。
    sym = sym.translate(WIDE_PARENS)
    # **`I/O` と `IO` は同じ添字**。版で綴りが割れる（zh は `I IO`、en は `I I/O`）ので
    # 揃えないと同じ事実が別の記号として並ぶ——絶対最大定格表を読み始めて14行が
    # 相手を失い reference になった。斜線を一律に潰すのは誤り（`V_POR/PDR`・
    # `f_SCK/t_SCK`・`C_L1/C_L2` は2つの名前を繋ぐ斜線）なので `I/O` だけを揃える。
    sym = sym.replace("I/O", "IO")
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
    # 行末のハイフンで割れた語を先に繋ぐ（`high-`⏎`speed`。規則と実測は wrap_rules）
    cell = wrap_rules.join_hyphen_wrap(cell or "")
    # **基底が本文に並び、添字が最後の行にまとめて置かれる**組版（`Total current of all
    # V /V power lines (source)`⏎`DD DDA`）。平坦化してから `attach_subscript` で戻すのは
    # 比較演算子の前の裸の記号だけなので、この形は届かない——行の構造が残るうちに戻す
    # （絶対最大定格表の `描述` 欄に集中。全corpus 66セル）。
    paired = pair_line_subscripts(cell, sep="_", flatten=False)
    if paired is not None:
        cell = paired
    text = re.sub(r"\s+", " ", cell.replace("\n", " ")).strip()
    for pattern, repl in TEXT_REPAIRS:
        text = pattern.sub(repl, text)
    return attach_subscript(text)


# 値の欄でも添字は離れて出る。条件欄の `attach_subscript` と同じ壊れ方で、
# `V_DD-0.4` が `V-0.4DD`、`0.45*V_DD+0.41` が `0.45*V+DD0.41` になる。
# **添字を、離れた場所から裸の記号のうしろへ戻す。**
# 長いものを先に置く（`DD33A` を `DD33` より先に見ないと末尾の `A` が値のうしろに
# 取り残される。`CH32H417DS0` の `V_OHSAT` は `V -160`＋添字`DD33A` で、`DD33` と読むと
# `VDD33-160A` になり、en 版の別ページ（`V -16`＋`DD33A`＋`0`）では `VDD33-16A0` という
# 壊れた数になっていた——同じ事実が3通りに綴られて偽の食い違いが3件出た。2026-09-09）
VALUE_SUBSCRIPTS = ("DD33A", "DD12A", "DD33", "DDIO", "DDA", "DD8", "CC12V", "HCLK",
                    "SCK", "DD", "IO")
# `I/O` の `I` は基底ではない（語そのもの）。除かないと、折り返しの2行目を添字と
# 取り違える——`I/O pin voltage when using`⏎`HSADC` が `I_HSADC/O pin voltage when using`
# になった（`CH32H417DS0`。2026-09-10の実測）。
BARE_BASE = re.compile(r"(?<![A-Za-z])([VtIfCRT])(?![A-Za-z]|/O)")
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

    **添字が数字で終わらないこともある。** 長いほうを先に見ないと末尾の英字が残る。

    >>> attach_value_subscript("V-160DD33A"), attach_value_subscript("V-16DD33A0")
    ('VDD33A-160', 'VDD33A-160')
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


# **添字を次の行にまとめて置く組版**。基底が1行目に並び、その添字が2行目に同じ順で並ぶ:
#
#     V +V        ← 基底2つ（V と V）
#     CC12V S     ← その添字2つ（CC12V と S）＝ `V_CC12V + V_S`
#
# 平坦化してから添字を戻す `attach_value_subscript` はこれを解けない——`V+VCC12VS` からでは
# `CC12V` がどちらの `V` の添字か決まらず、`CH32V007DS0.zh` の `V_B` が `V+VCC12VS` のまま出て
# en 版（`VCC12V+VS`。行が別々なので正しく戻る）と**偽の食い違い**になっていた。行の構造が
# 残っているうちに対応させれば曖昧さが無い。
#
# 全corpus実測（2026-09-10）: 値の欄でこの形は**この1セルだけ**。同じ形は記号セルに19件ある
# （`V -V`/`DD SS` ＝ 絶対最大定格の `V_DD-V_SS`）が、そちらは記号の経路なので触らない。
# 添字らしいトークン: **大文字で始まる短い綴り**（`DD33A`・`SS`・`IO18`・`DD_ETH`・`DD_x`）。
# 一覧で持つと絶対最大定格表の語彙（`HV`・`DDK`・`DD12A`・`B`・`S`・`DD_ETH`）で足りなくなる。
# 括弧を含む添字（`ESD(HBM)`・`INJ(PIN)`）はここで落ちて従来の連結へ回る——結果は同じ。
SUB_TOKEN = re.compile(r"^[A-Z][A-Za-z0-9/]*(?:_[A-Za-z0-9]+)*$")


def pair_line_subscripts(cell: str | None, sep: str = "",
                         flatten: bool = True) -> str | None:
    r"""**最後の行**の添字を、それより前の行の基底へ順に対応させる。合わなければ None。

    `sep` は基底と添字の間に置く字。値の欄は地続き（`VCC12V+VS`）、記号と文章の欄は `_`
    （`V_DD-V_SS`・`T_A = -40℃~85℃`）。`flatten` は値の欄のための空白潰し——文章では
    残す代わりに、添字を挿した跡に残る `)` `/` の前の空白だけ詰める（`(V )`＋`DD` は
    `(VDD)`）。

    >>> pair_line_subscripts("V +V\nCC12V S")
    'VCC12V+VS'
    >>> pair_line_subscripts("V -V\nDD SS", sep="_")
    'V_DD-V_SS'
    >>> pair_line_subscripts("V -0.3\nSS")
    'VSS-0.3'
    >>> pair_line_subscripts("V -GND\nHV", sep="_")
    'V_HV-GND'
    >>> pair_line_subscripts("External main supply voltage (V )\nDD",
    ...                      sep="_", flatten=False)
    'External main supply voltage (V_DD)'
    >>> pair_line_subscripts("Total current of all V pins\nSS", sep="_", flatten=False)
    'Total current of all V_SS pins'
    >>> pair_line_subscripts("3.3") is None
    True

    3行以上でも読む——**添字の行は最後の1行**で、その前は版面の折り返し
    （`External mains supply voltage⏎(including V and V )⏎DDA DD`）。

    >>> pair_line_subscripts("supply voltage\n(including V and V )\nDDA DD",
    ...                      sep="_", flatten=False)
    'supply voltage (including V_DDA and V_DD)'
    """
    lines = [x for x in (cell or "").split("\n") if x.strip()]
    if len(lines) < 2:
        return None
    # 脚注は**値と記号の欄でだけ**落とす（`flatten`＝そちらの経路）。文章の欄で落とすと
    # `R_S = 60Ω(1)` の `(1)` が消えて注記への手がかりを失う（14行が該当）。
    head = " ".join(lines[:-1])
    if flatten:
        head = FOOTNOTE.sub("", head)
    bases = list(BARE_BASE.finditer(head))
    tokens = [x for x in re.split(r"[\s,]+", lines[-1].strip()) if x]
    if not bases or len(bases) != len(tokens):
        return None
    if not all(SUB_TOKEN.match(tok) for tok in tokens):
        return None
    out, last = [], 0
    for base, tok in zip(bases, tokens):
        out.append(head[last:base.end(1)])
        out.append(sep + tok)
        last = base.end(1)
    out.append(head[last:])
    text = "".join(out)
    if flatten:
        return text.replace(" ", "")
    return re.sub(r" +(?=[)/,.;])", "", text)


def same_unit(a: str | None, b: str | None) -> bool:
    """単位が同じか。**先頭の `M` だけ大小を保って残りを小文字にする。**

    `m`（ミリ）と `M`（メガ）だけが大小で意味が変わるので、そこだけ残せば
    `mS`/`ms`・`us`/`uS`・`kHz`/`KHz`・`kΩ`/`KΩ`・`Times`/`times` が揃い、
    `mΩ`/`MΩ`・`mV`/`MV` は揃わない（単純な大小無視を入れなかった理由がこれ）。

    >>> same_unit("mS", "ms"), same_unit("KHz", "kHz"), same_unit("mV", "MV")
    (True, True, False)
    """
    def canon(u):
        return "".join(c if i == 0 and c == "M" else c.lower()
                       for i, c in enumerate(u or ""))
    return canon(a) == canon(b)


def same_value(a: str | None, b: str | None) -> bool:
    """値が同じか。`*`（掛け算）と `I/O` の綴りの差は無視する。

    `0.8*VDD` と `0.8VDD`、`VI/O` と `VIO` は同じ値の別の書き方。全corpus実測: 値に `/` を
    含むセルは7つで、うち `I/O` は2つ、残る5つは本物の割り算（`VDD/4`・`VDDA/2`）なので
    `/` を一律に落とすことはしない。**公開する綴りは変えない**——ここは対応付けのための
    正規化だけで、揃った結果は `basis` に両版が並ぶ形で見える。

    >>> same_value("0.8*VDD", "0.8VDD"), same_value("VI/O", "VIO"), same_value("VDD/4", "VDD")
    (True, True, False)
    """
    def canon(v):
        return (v or "").replace("*", "").replace("I/O", "IO")
    return canon(a) == canon(b)


def norm_value(cell):
    paired = pair_line_subscripts(cell)
    if paired is not None:
        return paired
    value = FOOTNOTE.sub("", norm_text(cell)).replace(" ", "")
    return VALUE_FIX.get(value, attach_value_subscript(value))


DROPPED: list[str] = []


def keep_row(row, lang, page_no):
    """その行を採るか。記号・単位・値がそれぞれ噛み合っていることを確かめる。

    表の継承（記号セルが空の続き行）は多条件の行には正しいが、別のパラメータが
    続いている場合は記号を取り違える。単位と値で弾けるので弾く。
    """
    # **min/typ/max がどれも空の行は事実を持たない。** 記号と単位だけの行で、
    # 説明の折り返しが独立した行として読まれたもの（`t_D` の条件の2行目など）。
    # 縦結合の取りこぼし（`fill_rowspans`）を先に直したので、これで消えるのは
    # 本当に値の無い行だけ——実測: この規則を入れる前の正本に該当行は0。
    if not (row["min"] or row["typ"] or row["max"]):
        return False
    symbol = row["symbol"]
    if symbol in HEADER_ROW:
        return False          # 表の見出しが本文として読まれたもの。黙って落とす
    if not KEEP.match(symbol):
        return False
    if MERGED_SYMBOL.search(symbol):
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


VALUE_COLUMNS = ("min", "typ", "max")


def fill_rowspans(record: dict, cols: list) -> list[list]:
    """**縦に結合された値のセル**を、覆われている行にも写した `extracted_rows`。

    資料は「2つの条件で同じ値」を値の欄の縦結合で書く——`t_erase_32k` の
    `DBMODE = 0, single 32K bytes` と `DBMODE = 1, single 64K bytes` は `3`/`10 ms` を
    共有し、`V_DDA` の「ADC を使う／使わない」は `2.4`/`3.6 V` を共有する。
    `extracted_rows` は結合セルを先頭の行にだけ置くので、覆われた行が**値ゼロ**になり、
    正本に「単位だけの行」として出ていた（実測: 全corpus 10行・18セル・5文書の zh/en 対称。
    2026-09-10に原本を描画して、版面が確かに縦結合であることを確かめた）。

    写すのは**min/typ/max の欄だけ**。記号と項目名は呼ぶ側が自前で継いでいて（継ぎ方が
    違う——記号は空欄なら前の行、項目名は空欄でなければ更新）、ここで写すと二重になる。
    """
    rows = [list(r) for r in record["extracted_rows"]]
    head = sorted((c for c in record["cells"] if c["row_start"] == 0),
                  key=lambda c: c["column_start"])
    if len(head) != len(cols) or not rows:
        return rows
    spans = [c for c in record["cells"]
             if c["row_end"] - c["row_start"] >= 2 and (c.get("text") or "").strip()]
    if not spans:
        return rows
    for index, name in enumerate(cols):
        if name not in VALUE_COLUMNS:
            continue
        start = head[index]["column_start"]
        for r in range(1, len(rows)):
            if index >= len(rows[r]) or (rows[r][index] or "").strip():
                continue
            for cell in spans:
                if (cell["column_start"] <= start < cell["column_end"]
                        and cell["row_start"] < r < cell["row_end"]):
                    rows[r][index] = cell["text"]
                    break
    return rows


def read_edition(bundle, lang):
    """対象表の行。行ごとに読み取ったページ番号を `_page` で持つ。

    対象表は1ページに収まらない。一般動作条件のほかに発振器の表が5つあり
    （HSI/LSI/外部高速/外部低速/水晶）、それぞれ別ページにある。最初に見つけた
    ページで打ち切ると一般動作条件しか取れない。
    """
    marker = MARKER[lang]
    found = []
    carry = False
    last_cols = None
    # **表題の無い表は直前の表題を継ぐ。** 表がページを跨ぐと続きの断片は表題を持たない
    # （表題は表の上の行から取るので、続きページには無い）。継がないと2つ困る:
    # (1) 表題で届く表の**続きの断片が読まれない**（`CH32V006DS0` の OPA 特性表は
    # zh p.38 に断片があり、そこの `C_LOAD 50pF` が落ちて en の 50 が zh の高速モード表の
    # 20 と組み、偽の食い違いになっていた）、(2) **表の範囲**（`table_scope`）が空になり、
    # 食い違いの相手を絞れない（`CH32V205DS0` の zh p.55 の ADC 特性表は表題が欠けていて、
    # en の `Table 3-28 ADC characteristics` と別の表に見えた——`f_ADC` の 64/96MHz は
    # **本物の食い違い**なので、絞りすぎると本物を隠す）。
    # 表題は**跳ばすページの表でも**更新する（最後に見た表題が続く、という意味だから）。
    last_caption = ""
    last_edges: list[float] = []
    sym = unit = param = group = ""
    for page in bundle_pages.pages(bundle):
        text = page.get("text") or ""
        hit = bool(marker.search(text))
        tables = []
        for record in page.get("tables", []):
            caption = ((record.get("caption") or {}).get("text") or "")
            if caption.strip():
                last_caption = caption
            tables.append((last_caption, record, column_edges(record)))
        if not hit and not carry and not any(
                TABLE_CAPTION.search(cap) for cap, _, _ in tables):
            continue
        # 表はページを跨ぐ。CH32V003の "Table 3-23 ADC characteristics" は
        # キャプションがp28で、ADCクロック上限の行はp29にある。キャプションの
        # 無い続きページも1ページだけ見る。列の並びが同じ表しか読まないので、
        # 無関係な表を拾っても記号の絞り込みで落ちる。
        carry_from, carry = carry and not hit, hit
        page_ok = hit or carry_from
        for caption, record, edges in tables:
            # ページ規則で届いていないページでは、**表題が当たった表だけ**を見る。
            if not page_ok and not TABLE_CAPTION.search(caption):
                continue
            tbl = record["extracted_rows"]
            cols = [norm_header(c) for c in tbl[0]]
            body = tbl[1:]
            # 条件列は動作条件表にしかない（絶対最大定格表は符号+描述のみ）
            fresh = True
            if {"symbol", "min", "condition"} <= set(cols):
                last_cols, last_edges = cols, edges
            elif (last_cols and len(tbl[0]) == len(last_cols)
                  and (carry_from or TABLE_CAPTION.search(caption)
                       or same_edges(edges, last_edges))):
                # 続きページの表はヘッダ行を持たない。列数が同じなら直前の
                # 並びをそのまま当てる。CH32V003のADCクロック上限の行は
                # このページにしかない。
                #
                # **表題で届いた表の続き**も同じ扱いにする（2026-09-09）。表題は
                # 直前の表から継ぐので（`last_caption`）、続きの断片も表題では届くが、
                # 1行目がデータ行なのでヘッダの検査に落ちて捨てられていた。
                # `CH32V006DS0.zh` p.38 の OPA 特性表の続き（`C_LOAD 50pF`）がそれで、
                # 落ちると en の 50 が zh の**高速モード表**の 20 と組んで偽の食い違いに
                # なっていた。
                #
                # **`carry_from` の限定も外した**（2026-09-10）。「そのページ自身が見出し語を
                # 持つ」と `carry_from` は False になるので、**同じページに載った続きの断片**が
                # 読まれなかった——`CH32V203DS0.zh` p39 は上半分が高速外部時钟の続き
                # （ヘッダは p38）で下半分が表4-12。zh は下だけ・en は上だけを読み、
                # `g_m` が 17 mA/V（HSE）と 25.3 uA/V（LSE）で**偽の食い違い**になっていた。
                # 続きページ（`carry_from`）と表題で届いた表の続きは**列数だけ**で続きと
                # 見なす（従来どおり）。**同じページに載った続きの断片**は新しく足した経路で、
                # そちらは**列の境界の一致**も要る——列数だけだと、たまたま同じ列数の別の表を
                # 続きと見なして**条件の語が値の欄に入る**（`CH32V002DS0` の待機電流で
                # `typ=5V`・`min=Disable` という行が6つ出た。2026-09-10の実測）。
                # 逆に境界を全経路に課すと、版面がわずかに違うページ跨ぎの続きが落ちる
                # （同実測で既存の21行が消えた）。
                cols, body = last_cols, tbl
                fresh = False
            else:
                continue
            # 縦に結合された値のセルを、覆われている行にも写す。列の並びが決まってからで
            # ないと写す先が分からないので、続きの断片は `last_cols` の並びで写す。
            filled = fill_rowspans(record, cols)
            body = filled[len(filled) - len(body):]
            # **記号・単位・項目名は続きの断片へ持ち越す。** 表の途中でページが変わると
            # そこから単位の欄が空になる（資料は「上の行と同じ」を空欄で書く）——
            # `CH32V103DS0.en` は p.21 の `I_VDD … mA` の続きが p.22 に在り、`I_Vss`・`I_IO` の
            # 単位が落ちて zh（1ページに収まる）と食い違っていた。新しいヘッダを見つけた
            # ときだけ捨てる。
            if fresh:
                sym, unit, param, group = "", "", "", ""
            rows = []
            for index, raw in enumerate(body):
                cells = dict()
                extra = []
                for i, cell in enumerate(raw):
                    if i < len(cols) and cols[i]:
                        cells[cols[i]] = cell
                    elif cell:
                        extra.append(cell)
                symbol_cell, pin_group = split_pin_group(cells.get("symbol"))
                s = norm_symbol(symbol_cell)
                this_param = norm_text(cells.get("parameter"))
                if s:  # 新しい記号の行。継続行は記号と参数を引き継ぐ
                    sym, param, group = s, this_param, pin_group
                elif (not fresh and index == 0 and param and this_param
                      and (this_param[0] == "(" or this_param[0].islower())):
                    # **続きの断片の1行目は、項目名の折り返しの後半**——`t_CONV` の
                    # `Total conversion time` は前ページで切れ、この断片には
                    # `(including sampling time)` だけが載る。置き換えると項目名が
                    # 断片になるので繋ぐ。小文字か括弧で始まるものだけ（データは
                    # 大文字か数字で始まる。`fold_header_wrap` と同じ見分け方）。
                    param = f"{param} {this_param}"
                else:
                    param = this_param or param
                    group = pin_group or group
                unit = norm_value(cells.get("unit")) or unit
                condition = " ".join(
                    filter(None, [norm_text(cells.get("condition"))]
                           + [norm_text(e) for e in extra]))
                # ピン群は**条件の先頭**に置く（`PA0-PA23, I_IO = 50mA V_DD = 3.3V`）。
                # 記号は`V_OH`のまま引けて、群ごとの行が別の条件として並ぶ。
                if group:
                    condition = f"{group}, {condition}" if condition else group
                rows.append({
                    "symbol": sym,
                    "parameter": param,
                    "condition": condition,
                    # ピン群は言語に依らないので、版をまたいで比べられる（`main`の対応付け）。
                    "_group": group,
                    "min": norm_value(cells.get("min")),
                    "typ": norm_value(cells.get("typ")),
                    "max": norm_value(cells.get("max")),
                    "unit": unit,
                })
            kept = [r for r in rows if keep_row(r, lang, page["number"])]
            if kept:
                scope = table_scope(caption)
                found += [{**r, "_page": page["number"], "_table": scope}
                          for r in kept]
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


def scan_prose(bundle, hit):
    """ページ本文を1行と次行の窓で読み、hit が返した値を (page_no, 値) で返す。

    折り返しで文が2行に割れるため、行単体ではなく隣接2行の窓を渡す。最初に
    当たったページで止める——同じ事実が章ごとに繰り返されるだけなので。
    """
    for page in bundle_pages.pages(bundle):
        lines = (page.get("text") or "").splitlines()
        for i, _ in enumerate(lines):
            found = hit(" ".join(lines[i:i + 2]))
            if found:
                return page["number"], found
    return None, None


def read_usb_clock(bundle, lang):
    """(page_no, "48") — 全速 USB block が 48MHz を要求すると書いてあれば。"""
    def hit(window):
        if FULL_SPEED.search(window) and MHZ_48.search(window):
            return "48"
        return None
    return scan_prose(bundle, hit)


def read_cpu_with_usb(bundle, lang):
    """(page_no, ["48", "96", "144"]) — USB 使用時に許される CPU 周波数の列挙。"""
    pattern = CPU_WITH_USB[lang]

    def hit(window):
        found = pattern.search(window)
        if not found or not USB_MENTIONED.search(window):
            return None
        values = MHZ_VALUE.findall(found.group("list"))
        return values or None
    return scan_prose(bundle, hit)


def read_headline_clock(bundle, lang):
    """(page_no, MHz) — 1ページ目付近の特徴リストが謳う系統主頻。無ければ(None, None)。"""
    for page in bundle_pages.pages(bundle, 3):
        text = page.get("text") or ""
        values = {m.group(1) for pattern in HEADLINE[lang]
                  for m in pattern.finditer(text)}
        if values:
            # 同一ページに複数表記があるときは高い方（「最高NNMHz」表記）
            return page["number"], max(values, key=int)
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
            bundle = _bundle(datasheet, lang)
            if bundle is None:
                continue
            rows = read_edition(bundle, lang)
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
        # **綴りの差は食い違いではない。** 対応付けは値と単位の一致で決めるので、同じ事実を
        # 版が別の綴りで書くと conflict になる。長く「conflict のうち何件は綴りの差」と
        # 台帳に書いてきた分（`docs/table-reliability.ja.md`）を、ここで外す。
        #
        # 単位: **先頭の `M` だけ大小を保って残りを小文字にする。** `m`（ミリ）と `M`（メガ）
        # だけが大小で意味が変わるので、そこだけ残せば `mS`/`ms`・`us`/`uS`・`kHz`/`KHz`・
        # `kΩ`/`KΩ`・`Times`/`times` が揃い、`mΩ`/`MΩ`・`mV`/`MV` は揃わない
        # （単純な大小無視を入れなかった理由がこれ）。全corpus実測で大小が揺れる単位は
        # `kHz`/`KHz`（10/32）・`kΩ`/`KΩ`（73/4）・`ms`/`mS`（82/13）・`us`/`uS`（190/1）・
        # `Times`/`times`・`year`/`Year`・`time`/`Time` の7組。
        #
        # 値: `*`（掛け算）と `I/O` の綴り。`0.8*VDD` と `0.8VDD`、`VI/O` と `VIO` は
        # 同じ値の別の書き方（`VI/O` は `V` に添字 `I/O` が付いた綴りで、同じ行の中で
        # `min=0.8VI/O` と `max=VIO` が混ざる実例がある）。全corpus実測: 値に `/` を含む
        # セルは7つで、うち `I/O` は2つ、残る5つは本物の割り算（`VDD/4`・`VDDA/2`）なので
        # `/` を一律に落とすことはしない。`*` を含むセルは42で全部掛け算。
        # **公開する綴りは変えない**（英語版の書き方をそのまま出す）。ここは対応付けの
        # ためだけの正規化で、揃った結果は `basis` に両版が並ぶ形で見える。
        def agrees(zh, en):
            # **ピン群が違う行は同じ事実ではない。** 群は`PA0-PA23`のように言語に依らないので
            # 版をまたいで比べられる。`CH32X035DS0` V2.3（zh）は出力電圧特性をポート群ごとに
            # 分けたが en は V2.2 の一般I/Oの1組のまま——値だけで突き合わせると en の 6mA の行が
            # zh の PA 30mA の行と「一致」してしまい、**zh が言っていない条件に confirmed が付く**。
            # 群が揃っている版どうしなら従来どおり対応する。
            if (zh.get("_group") or "") != (en.get("_group") or ""):
                return False
            if not same_value(zh["min"], en["min"]) or not same_value(zh["max"], en["max"]):
                return False
            # 単位と典型値は、片方の版だけが列を持つことがある（rowspanの空セル、
            # 版によって典型値の列を落とす表）。空は不一致ではないので、
            # 両方が値を持つときだけ突き合わせる。
            if zh["unit"] and en["unit"] and not same_unit(zh["unit"], en["unit"]):
                return False
            if zh["typ"] and en["typ"] and not same_value(zh["typ"], en["typ"]):
                return False
            return True

        # **対応付けは二段**。一段目で値の一致する対を全部取り、二段目で残りを
        # 食い違い（conflict）に回す。1回の貪欲な走査だと、**先に来たen行が
        # conflictとして候補を消費**し、後から来る「値が一致するはずのen行」が
        # 相手を失う——`CH32V205DS0`の`V_OL 静态输出低电平`(0.3)が、先行の
        # `输出低电平`(0.4)行のconflictに食われてconfirmed→referenceに落ちた
        # （2026-09-09、出力電圧特性の表を表題で拾えるようにしたときに露出）。
        # 値の一致は曖昧さのない根拠なので先に確定させ、conflictは余りで作る。
        #
        # 一致する候補が複数あるときは**条件が同じもの**を優先する。条件の文は
        # 言語ごとなので一致率は低い（実測: 両方空45%・一致12%・不一致28%）が、
        # 一致するなら同じ行のことなので、そちらを選ぶ方が正しい。
        remaining = list(zh_rows)
        paired: dict[int, dict] = {}
        for index, row in enumerate(en_rows):
            agreeing = [z for z in remaining
                        if z["symbol"] == row["symbol"] and agrees(z, row)]
            if not agreeing:
                continue
            pick = next((z for z in agreeing if z["condition"] == row["condition"]),
                        agreeing[0])
            remaining.remove(pick)
            paired[index] = pick
        for index, row in enumerate(en_rows):
            exact = paired.get(index)
            # 食い違いの相手も**群が揃っているものだけ**。群が違えば別の適用範囲の話で、
            # 「同じ事実で値が食い違う」ではない——揃えないと、en の一般I/Oの行が zh の
            # `PA0-PA23` の行を食って偽のconflictになり、zh の行も消える。
            # 食い違いの相手は**群が揃い、条件の有無も揃う**ものだけ。群が違えば別の適用範囲、
            # 条件の有無が違えば別の行のことで、「同じ事実で値が食い違う」ではない。
            # 全corpus実測: この条件でconflictの候補23件のうち21件は残り、外れる2件は
            # `CH32V103DS0`の`F_PLL_IN`/`F_PLL_OUT`で**zh側の条件欄に値が流れ込んだ読み違い**
            # （条件が`'16'`）——en単独のreferenceにするのが正しい。
            # `CH32X035DS0` V2.3 では、en の一般I/O（条件あり）が zh の`静态输出高电平`
            # （条件なし・別の表）と突き合わされて偽のconflictになるのを防ぐ。
            cands = ([] if exact else
                     [z for z in remaining if z["symbol"] == row["symbol"]
                      and (z.get("_group") or "") == (row.get("_group") or "")
                      and z.get("_table") == row.get("_table")
                      and bool(z["condition"]) == bool(row["condition"])])
            en_page = row.pop("_page")
            row.pop("_table", None)
            if exact:
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
            row.pop("_group", None)
            out.append({**row, "series": series, "#": "#",
                        "confidence": confidence, "basis": basis,
                        "datasheet": datasheet})

        # **zh だけが持つ「ピン群つき」の行**を`reference`で出す。
        #
        # これが無いと、**zh だけが改版された資料の新しい行は原理的に出ない**（表示テキストは英語版から
        # 取る設計なので、en に無い行は落ちる。実測: 正本2,797行に zh のみ根拠の行は0）。
        # `CH32X035DS0` V2.3 は出力電圧特性をポート群ごとに分けた——en（まだV2.2）は一般I/Oの1組の
        # ままなので、この経路が無いと `PA0-PA23 は 50mA` という新しい事実が入らない。
        #
        # **ピン群を持つ行に限る**のが要点。群がある＝「en が一般名で言っている同じ規格の、
        # 適用範囲を分けた版」なので、en の同じ記号の英語名を借りるのが正しい。群が無い zh 余りは
        # 別の表の別の事実であることが多く（`CH32X035DS0.zh` p32 の`静态输出高电平`は
        # 一般I/Oの`V_OH`とは別物）、記号だけで英語名を借りると**名前を偽る**。だから出さない。
        # 条件と借りる名前に CJK があるものも出さない——この表は CJK を1文字も含まない英語の表
        # （実測: 2,797行の parameter/condition に CJK は0）で、その性格を保つ。
        # 全corpus実測（V2.2時点）: 群を持つ zh 余りは**0行**——つまりこの経路は
        # 「ポート群で分けた資料」だけで働き、既存の出力は1バイトも動かない。
        english = {}
        for row in en_rows:
            english.setdefault(row["symbol"], row["parameter"])
        # 同じ文書で**値まで同じ行が既に出ている**なら足さない。資料が同じ規格を2つの表に
        # 書くことがあり（`CH32V20x_30xDS0`の`I_L`はzhがp.57とp.58の両方に持つ）、片方が
        # en と対応して confirmed で出た後に、もう片方を zh のみの reference で足すと
        # **同じ事実が信頼度違いで2行**になる。
        already = {(r["symbol"], r["parameter"], r["condition"],
                    r["min"], r["typ"], r["max"], r["unit"])
                   for r in out if r["datasheet"] == datasheet}
        skipped: dict[str, int] = {}
        for zh in remaining:
            if not (zh.get("_group") or ""):
                skipped["ピン群が無い"] = skipped.get("ピン群が無い", 0) + 1
                continue
            name = english.get(zh["symbol"])
            if name is None:
                skipped["enに記号が無い"] = skipped.get("enに記号が無い", 0) + 1
                continue
            if CJK.search(zh["condition"] or "") or CJK.search(name):
                skipped["中文の表記"] = skipped.get("中文の表記", 0) + 1
                continue
            same = (zh["symbol"], name, zh["condition"],
                    zh["min"], zh["typ"], zh["max"], zh["unit"])
            if same in already:
                skipped["既に同じ行がある"] = skipped.get("既に同じ行がある", 0) + 1
                continue
            already.add(same)
            out.append({"symbol": zh["symbol"], "parameter": name,
                        "condition": zh["condition"], "min": zh["min"],
                        "typ": zh["typ"], "max": zh["max"], "unit": zh["unit"],
                        "series": series, "#": "#", "confidence": "reference",
                        "basis": f"{datasheet}:zh(p.{zh['_page']})",
                        "datasheet": datasheet})
        if skipped:
            print(f"  {datasheet}: zhだけの行のうち出さなかったもの {skipped}",
                  file=sys.stderr)

        heads = {}
        for lang in ("zh", "en"):
            bundle = _bundle(datasheet, lang)
            if bundle:
                page_no, value = read_headline_clock(bundle, lang)
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
                    bundle = _bundle(paper, lang)
                    if bundle and (paper, lang) not in seen:
                        page_no, value = reader(bundle, lang)
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
    # **根拠が違うだけの重複も1行にする**（2026-09-09）。資料は同じ規格を複数の表に
    # 繰り返す——`CH32L103DS0` は OPA と CMP の特性表4つが同じ `V_CM 0〜V_DDA` を載せ、
    # `CH32V407DS0` は OPA 表2つが同じ飽和出力電圧を載せる。表題で表を選べるように
    # なって OPA/CMP の表が全部読めると、この繰り返しがそのまま行の重複になった
    # （実測: 同じ主張が2行以上あるのが 6 件 → 49 件）。この表は「どの表から来たか」を
    # 持たないので、重複は**読む側に何も足さない**。
    # **確度の良い方を残す**（confirmed > conflict > reference）——同じ主張が、ある表では
    # 両版が揃って confirmed になり、別の表では片版だけで reference になることがある
    # （`CH32H417DS0` の `V_DD33A`・`CH32V407DS0` の `I_LOAD`/`V_IOFFSET`）。裏付けの
    # 強い方が正しい。
    RANK = {"confirmed": 0, "conflict": 1, "reference": 2}
    # **確度は鍵に入れない。** 入れると「同じ主張で確度が違う2行」が残る
    # （`CH32H417DS0` の `V_DD33A 1.8/3.3/3.6` は OPA 表で confirmed・CMP 表で reference）。
    claim = [c for c in COLUMNS if c not in ("basis", "#", "confidence")]
    best: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in out:
        key = tuple(r.get(c, "") for c in claim)
        if key not in best:
            best[key] = r
            order.append(key)
        elif RANK[r["confidence"]] < RANK[best[key]["confidence"]]:
            best[key] = r
    unique = [best[k] for k in order]
    if len(unique) != len(out):
        print(f"同じ主張の重複行を落とした: {len(out) - len(unique)} 行", file=sys.stderr)
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
