#!/usr/bin/env python3
"""ADC の内部チャネル（温度センサ・内部参考電圧・VDD/2）→ tables/adc_internal.csv

**`temperatureRead()` 相当の API の前提**（consumer の依頼 R-26-3）。温度センサと
内部参考電圧が **ADC のどのチャネルに繋がっているか**は family で違い、そもそも
温度センサを持たない family もある。換算定数（25℃での電圧 V25・平均傾き
Avg_Slope・内部参考電圧 VREFINT）と、読むときに必要なサンプル時間もここに置く。

**出所は datasheet の2箇所。**

    機能説明の散文   「温度传感器在内部被连接到IN16输入通道上」
                     「内部参考电压被连接到 IN17 输入通道上」「V/2 被连接到 IN18」
                     CH32H417 は表で `ADC_IN16 温度传感器` と書く
    電気的特性の表   表「温度传感器特性」: Avg_Slope（mV/℃）・V25（在25℃时的电压）・
                     T_S_temp（ADC采样时间）・測定範囲・測定誤差
                     表「内置参考电压」: VREFINT（min/typ/max）・T_S_vrefint

**サンプル時間の単位が family で違う。** L103/V103 は `20 us`（f_ADC=14MHz の条件
付き）、X035/V006 は `11 1/f_ADC`（ADC クロックの周期数）。単位を揃えると条件を
落とすので、`sample_time` と `sample_time_unit`（`us` / `adc_cycles`）で持つ。

英語版に同じ表があるので、数値が一致すれば confirmed、英語版に無ければ reference。
温度センサを持たない family（V003/V006/M030/X035/X315）は温度の行を持たない。

**datasheet がチャネル番号を書かない family がある。** CH32V003 と CH32X035 は
「内部通道」があるとだけ書き、番号は RM の ADC 章が書く
（`Vref内部参考电压：连接ADC_IN8通道` / `连接ADC_IN15通道`）。datasheet に無ければ
RM を読み、basis にそう書く。

`tools/build_adc_internal.py`（凍結tool。PDF を pdfplumber で直読み）から pdfplumber 依存だけを
外した移植（D18 の退役手順: bundle 入力で凍結tool と **byte 一致**を確認 → `regenerate.py` を
こちらへ切替 → 凍結tool を削除。2026-09-09。退役の第5号）。読む欄は bundle の `text`
（ページ本文）だけで、読みの規則は変えていない。ページの読み手は
`pipeline/extract/bundle_pages.py`（sha 照合つき）。datasheet は `catalog/products.csv` の
`datasheet` 列と言語、RM は目録の `repositories` で引く。ここでは PDF を開かない。

実行:
    uv run pipeline/extract/datasheet/extract_adc_internal.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402
import paths  # noqa: E402
sys.path.insert(0, str(REPO / "pipeline" / "extract" / "rm"))
import register_fields  # noqa: E402

COLUMNS = ["family", "source", "channel", "sample_time", "sample_time_unit",
           "sample_clock_mhz", "v25_mv", "v25_mv_min", "v25_mv_max",
           "avg_slope_uv_c", "avg_slope_uv_c_min", "avg_slope_uv_c_max",
           "vrefint_mv", "vrefint_mv_min", "vrefint_mv_max",
           "temp_range_c", "temp_error_c",
           "enable_register", "enable_field", "enable_bit", "enable_confidence",
           "#", "confidence", "basis"]

# **チャネルを使うのに要る有効化ビット**（R-35。2026-10-01）。RM の ADC 章の field 表で、
# 説明が「（温度传感器和）内部电压（V_REFINT）通道使能位」/「(Temperature sensor and) internal
# voltage (V_REFINT) channel enable」と書く field。多くの family は `ADC_CTLR2.TSVREFE`（温度と
# VREFINT の両方）、X315 は `VREFE`（VREFINT だけ。温度センサを持たない）。X035/V003/V006/M030 の
# RM はそういう field を持たない（CTLR2 の [31:23] は Reserved）ので空——「RM に有効化ビットが無い」。
# 「参考电压」「使能」だけで探すと `BUFEN`（説明が TKENABLE に触れる）まで当たるので、説明の
# **書き出し**で当てる。
ENABLE_ZH = re.compile(r"^(?P<temp>温度传感器和)?内部电压[^：:]{0,20}通道使能")
ENABLE_EN = re.compile(r"^(?P<temp>temperature sensor and )?internal voltage.{0,30}channel enable",
                       re.IGNORECASE)

NUM = r"(-?\d+(?:\.\d+)?)"
# --- チャネルの散文（zh）。文の途中で改行されるので、ページ内の行を繋いで見る。
CH_TEMP = re.compile(r"温度传感器[^。]{0,40}?(?:ADC\d?_)?IN\s*(\d+)")
CH_VREF = re.compile(r"(?:内部参考电压|内部参考电源电压|内置参考电压)[^。]{0,40}?(?:ADC\d?_)?IN\s*(\d+)")
CH_HALF = re.compile(r"V\s*(?:DD)?\s*/\s*2[^。]{0,30}?(?:ADC\d?_)?IN\s*(\d+)")
# CH32H417 は表で書く。
TBL_TEMP = re.compile(r"ADC\d?_IN(\d+)\s+温度传感器")
TBL_VREF = re.compile(r"ADC\d?_IN(\d+)\s+内部参考电压")
# --- 電気的特性（zh）。
SLOPE = re.compile(rf"Avg_Slope\s+平均斜率[^\d\n]*{NUM}\s+{NUM}\s+{NUM}\s+mV")
V25 = re.compile(rf"在25℃时的电压\s+{NUM}\s+{NUM}\s+{NUM}\s+V")
T_TEMP = re.compile(rf"当读取温度时，ADC采样时间(?:\s+f\s*=\s*(\d+)\s*MHz)?\s+{NUM}\s+(us|1/f)")
RANGE = re.compile(rf"温度传感器测量范围\s+{NUM}\s+{NUM}\s+℃")
ERROR = re.compile(rf"温度传感器的测量误差\s+±{NUM}\s+℃")
# 条件欄の `T = -40℃～105℃` に数字が入るので、`[^\d]` では止まれない。数が3つ
# 空白区切りで並んで V で終わる所まで非貪欲に進む（`-40℃` は直後が ℃ なので
# `{NUM}\s+` に当たらない）。CH32V20x は条件欄が無く添字の `A` だけが残る。
# **典型值の列を持たない表がある**（CH32V103DS0 表3-5 は `最小值 最大值` だけ＝`1.12 1.28 V`）。
# 真ん中の数は任意にし、無ければ typ は空（min・max だけを採る）。3つ並ぶ表は従来どおり3つ取る。
VREF = re.compile(rf"内置参考电压[^\n]*?{NUM}\s+(?:{NUM}\s+)?{NUM}\s+V\b")
# **「建议慢速采样」を書かない表がある**（V003 `T 3 500 1/f S_vrefint`、V20x/V307 `T 17.1 us`、
# V407 `T 8 us`、X315 `T 3.6 us`）。どの版面でも記号の `T` と添字の `S_vrefint` が値と単位を
# 挟むので、そこで当てる。数が2つ並ぶ表（V006 `3 240`・V003 `3 500`）は2つ目＝最大（推奨の遅い
# サンプリング）を採る——従来の規則のまま。
T_VREF = re.compile(rf"(?:建议慢速采样\s+{NUM}(?:\s+{NUM})?\s+(us|1/f)"
                    rf"|\bT\s+{NUM}(?:\s+{NUM})?\s+(us|1/f)\s+S_vrefint)")
# RM の ADC 章。datasheet がチャネル番号を書かない family の逃げ道。
RM_VREF = re.compile(r"内部参考电压[：:][^。\n]{0,10}?ADC\d?_IN\s*(\d+)")
RM_TEMP = re.compile(r"温度传感器[：:][^。\n]{0,10}?ADC\d?_IN\s*(\d+)")
# --- 英語版で同じ数を探すための鍵。
EN_SLOPE = re.compile(rf"Avg_Slope[^\d\n]*{NUM}\s+{NUM}\s+{NUM}\s+mV")
EN_V25 = re.compile(rf"at\s*25\s*(?:°\s*C|℃|C)\s+{NUM}\s+{NUM}\s+{NUM}\s+V\b")
# 「参考電圧」は ADC の正参考電圧（`-0.3 … +0.3 V`）など別の行にも出るので、
# 内蔵（internal / built-in）と限定する。
EN_VREF = re.compile(rf"(?:internal|built-?in)\s+reference\s+voltage[^\n]*?{NUM}\s+(?:{NUM}\s+)?{NUM}\s+V\b",
                     re.IGNORECASE)


def pages_of(bundle: str) -> list[str]:
    """bundle の全ページの本文（`pdf.pages`＋`extract_text()` の置き換え）。"""
    return [text for _number, text in bundle_pages.texts(bundle)]


def mv(value: str | None) -> str:
    return "" if value is None else str(round(float(value) * 1000))


def uv(value: str) -> str:
    return str(round(float(value) * 1000))


def read_zh(pages: list[str]) -> tuple[dict, dict[str, int]]:
    """{項目: 値} と {項目: ページ}。"""
    found: dict = {}
    where: dict[str, int] = {}

    def keep(key: str, value, pno: int) -> None:
        if key not in found:
            found[key] = value
            where[key] = pno

    for pno, text in enumerate(pages, 1):
        flat = text.replace("\n", "")
        for key, pattern in (("ch_temp", CH_TEMP), ("ch_vref", CH_VREF), ("ch_half", CH_HALF),
                             ("ch_temp", TBL_TEMP), ("ch_vref", TBL_VREF)):
            m = pattern.search(flat)
            if m:
                keep(key, int(m.group(1)), pno)
        for key, pattern in (("slope", SLOPE), ("v25", V25), ("t_temp", T_TEMP),
                             ("range", RANGE), ("error", ERROR), ("vref", VREF),
                             ("t_vref", T_VREF)):
            m = pattern.search(text)
            if m:
                keep(key, m.groups(), pno)
    return found, where


def read_en(pages: list[str]) -> dict:
    found: dict = {}
    for text in pages:
        for key, pattern in (("slope", EN_SLOPE), ("v25", EN_V25), ("vref", EN_VREF)):
            m = pattern.search(text)
            if m and key not in found:
                found[key] = m.groups()
    return found


def enable_fields(family: str) -> dict[str, tuple[str, str, str, str, str]]:
    """{source: (register, field, bit, confidence, basis)}。RM の zh と en を両方読み、同じ field を
    同じ bit で言えば confirmed、片方だけなら reference。"""
    found: dict[str, dict[str, tuple[str, str, int]]] = {}
    documents: dict[str, str] = {}
    for lang, (bundle, document) in bundle_pages.rm_bundles(family).items():
        fields, _ = register_fields.extract(bundle.name, None)
        documents[lang] = document
        pattern = ENABLE_ZH if lang == "zh" else ENABLE_EN
        for f in fields:
            m = pattern.match((f.get("description") or "").strip())
            if not m or not f["register"].upper().startswith("ADC") or f["bit_width"] != 1:
                continue
            register = re.sub(r"^ADCx?_", "", f["register"])
            for source in (("temperature_sensor", "vrefint") if m.group("temp") else ("vrefint",)):
                found.setdefault(source, {}).setdefault(lang, (register, f["field"], f["bit_offset"]))
    out = {}
    for source, by_lang in found.items():
        said = set(by_lang.values())
        register, field, bit = by_lang.get("zh") or by_lang["en"]
        langs = "+".join(f"rm-enable({documents[lang]}:{lang})" for lang in ("zh", "en") if lang in by_lang)
        if len(said) > 1:
            out[source] = (register, field, str(bit), "conflict", langs)
        else:
            out[source] = (register, field, str(bit),
                           "confirmed" if len(by_lang) == 2 else "reference", langs)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()

    with paths.table("products").open(newline="", encoding="utf-8") as f:
        sheets: dict[str, str] = {}
        for r in csv.DictReader(f):
            sheets.setdefault(r["datasheet"], r["family"])

    rows: list[dict] = []
    notes: list[str] = []
    for datasheet, family in sorted(sheets.items()):
        stem = Path(datasheet).stem
        zh_name, en_name = f"{stem}.zh", f"{stem}.en"
        if not (bundle_pages.BUNDLES / zh_name / "manifest.json").exists():
            continue
        zh, where = read_zh(pages_of(zh_name))
        en = (read_en(pages_of(en_name))
              if (bundle_pages.BUNDLES / en_name / "manifest.json").exists() else {})
        rm_basis = ""
        if ("ch_vref" not in zh and "vref" in zh) or ("ch_temp" not in zh and "slope" in zh):
            manuals = bundle_pages.rm_bundles(family)
            if "zh" in manuals:
                manual_bundle, manual_document = manuals["zh"]
                for pno, text in bundle_pages.texts(manual_bundle.name):
                    flat = text.replace("\n", "")
                    for key, pattern in (("ch_vref", RM_VREF), ("ch_temp", RM_TEMP)):
                        m = pattern.search(flat)
                        if m and key not in zh:
                            zh[key] = int(m.group(1))
                            where[key] = pno
                            rm_basis = f"+rm({manual_document}:p.{pno})"

        def judged(*keys: str) -> tuple[str, str]:
            """zh の値が en にもあるか。keys のどれかで比べる。"""
            agree = [k for k in keys if k in zh and k in en and tuple(zh[k][:3]) == tuple(en[k][:3])]
            disagree = [k for k in keys if k in zh and k in en and tuple(zh[k][:3]) != tuple(en[k][:3])]
            pages = "+".join(dict.fromkeys(f"{datasheet}:zh(p.{where[k]})" for k in keys if k in where))
            if disagree:
                return "conflict", pages + "+!" + datasheet + ":en"
            if agree:
                return "confirmed", pages + f"+{datasheet}:en"
            return "reference", pages

        if "slope" in zh or "v25" in zh or "ch_temp" in zh:
            confidence, basis = judged("slope", "v25")
            slope, v25 = zh.get("slope"), zh.get("v25")
            t = zh.get("t_temp")
            rows.append({
                "family": family, "source": "temperature_sensor",
                "channel": zh.get("ch_temp", ""),
                "sample_time": t[1] if t else "",
                "sample_time_unit": ("adc_cycles" if t and t[2] == "1/f" else "us") if t else "",
                "sample_clock_mhz": (t[0] or "") if t else "",
                "v25_mv": mv(v25[1]) if v25 else "", "v25_mv_min": mv(v25[0]) if v25 else "",
                "v25_mv_max": mv(v25[2]) if v25 else "",
                "avg_slope_uv_c": uv(slope[1]) if slope else "",
                "avg_slope_uv_c_min": uv(slope[0]) if slope else "",
                "avg_slope_uv_c_max": uv(slope[2]) if slope else "",
                "vrefint_mv": "", "vrefint_mv_min": "", "vrefint_mv_max": "",
                "temp_range_c": f"{zh['range'][0]}..{zh['range'][1]}" if "range" in zh else "",
                "temp_error_c": zh["error"][0] if "error" in zh else "",
                "confidence": confidence, "basis": basis,
            })
            if "ch_temp" not in zh:
                notes.append(f"{family}: 温度センサの表はあるがチャネル番号が散文に無い")
        if "vref" in zh or "ch_vref" in zh:
            confidence, basis = judged("vref")
            basis += rm_basis if "ch_vref" in zh and rm_basis else ""
            vref, t = zh.get("vref"), zh.get("t_vref")
            if t:
                t = t[:3] if t[2] else t[3:]  # どちらの形で当たったか
            rows.append({
                "family": family, "source": "vrefint",
                "channel": zh.get("ch_vref", ""),
                "sample_time": (t[1] or t[0]) if t else "",
                "sample_time_unit": ("adc_cycles" if t and t[2] == "1/f" else "us") if t else "",
                "sample_clock_mhz": "",
                "v25_mv": "", "v25_mv_min": "", "v25_mv_max": "",
                "avg_slope_uv_c": "", "avg_slope_uv_c_min": "", "avg_slope_uv_c_max": "",
                "vrefint_mv": mv(vref[1]) if vref else "",
                "vrefint_mv_min": mv(vref[0]) if vref else "",
                "vrefint_mv_max": mv(vref[2]) if vref else "",
                "temp_range_c": "", "temp_error_c": "",
                "confidence": confidence, "basis": basis,
            })
            if "ch_vref" not in zh:
                notes.append(f"{family}: 内部参考電圧の表はあるがチャネル番号が datasheet にも RM にも無い")
        if "ch_half" in zh:
            rows.append({
                "family": family, "source": "vdd_half", "channel": zh["ch_half"],
                **{c: "" for c in COLUMNS if c not in ("family", "source", "channel", "#",
                                                        "confidence", "basis")},
                "confidence": "reference",
                "basis": f"{datasheet}:zh(p.{where['ch_half']})",
            })

    # 同じ family を複数 datasheet が言うとき（CH32V006 の 4 冊）は 1 行に畳む。
    unique: dict[tuple[str, str], dict] = {}
    for row in rows:
        unique.setdefault((row["family"], row["source"]), row)
    rows = list(unique.values())

    # **資料に内部参考電圧が無い family も行で言う**（R-35）。行が無いだけだと「読み落とし」と
    # 「資料に無い」が区別できない（V103 は前者だった）。datasheet と RM のどこにも無いときだけ
    # `missing` の行を置き、basis に探した資料を並べる。温度センサは従来どおり行を持たない
    # （持たない family が多く、無いことが仕様）。
    have_vref = {r["family"] for r in rows if r["source"] == "vrefint"}
    for family in sorted({f for f in sheets.values()} - have_vref):
        searched = sorted({d for d, fam in sheets.items() if fam == family}
                          | {doc for _, doc in bundle_pages.rm_bundles(family).values()})
        rows.append({"family": family, "source": "vrefint",
                     **{c: "" for c in COLUMNS if c not in ("family", "source", "#",
                                                            "confidence", "basis")},
                     "confidence": "missing",
                     "basis": "searched(" + "+".join(searched) + ")"})

    for family in sorted({r["family"] for r in rows}):
        enables = enable_fields(family)
        for row in rows:
            if row["family"] == family and row["source"] in enables and row["confidence"] != "missing":
                register, field, bit, confidence, basis = enables[row["source"]]
                row.update({"enable_register": register, "enable_field": field,
                            "enable_bit": bit, "enable_confidence": confidence})
                row["basis"] += "+" + basis
    rows = sorted(rows, key=lambda r: (r["family"], r["source"]))

    dest = paths.table("adc_internal", args.out)
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**{c: "" for c in COLUMNS}, **row, "#": "#"} for row in rows)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{dest}: {len(rows)} 行  family {len({r['family'] for r in rows})}  {dict(tally)}",
          file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
