#!/usr/bin/env python3
"""RM の「有効化ビットで pad が動く」格子 → evidence/pin_conditions.csv。**bundle を直接読む**。

AFIO の重映射 field（`*_RM`）ではなく、**周辺の有効化ビットの論理積**を列見出しに持つ
重映射格子がある（worklist の F-61）。`SDIOEN=1` と `SDIOEN=1&ETHMACEN=1` のように
**条件が入れ子**なので、`remap_routes` の `(selector, value) → pad` という平らな対応では
同じビット並びに2つの pad が付いてしまう。selector に RCC の有効化ビットを置くのも誤り
——consumer はそれを `GPIO_PinRemapConfig` で書こうとする。だから別の表にする。

**この表が答える問い**: `index/pinout.csv` に同じ signal の `default` が2つ載ることがある
（実測 34 組・6 series。`SDIO_D0` は `PC8` と `PB14`、`I2S3_MCK` は `PC7` と `PA8`）。
どちらが効くかは**書き込む remap field ではなく、どの周辺を有効にしたか**で決まる。
その条件を機械可読にしたのがこの表で、行は

    series, signal, condition, pad

**条件は資料の綴りの連言**（`SDIOEN=1&ETHMACEN=1`）。`&` で並ぶ項が全部成り立つ行が
効き、**項の多い行が勝つ**（`SDIOEN=1&ETHMACEN=1` は `SDIOEN=1` を含むので、両方
成り立つときは後者ではなく前者）。同じ資料が同じ行に書いている既定側も出すので、
勝ち負けはこの表の中だけで決まる。

**載せるのは pad が条件で動く signal だけ。** 格子は動かない signal も並べる
（`SDIO` の格子は10本中8本が両列同じ pad）が、それは「pad は動かない」と言っている
だけで、`pinout` が既に言っていることと変わらない。載っていない signal の pad は
これまでどおり `pinout`／`pin_functions` を見る。

**読み方**（列の境界が版面で壊れるので、セル文字列ではなく**字形の位置**で読む）:

- 見出し行のセルから、条件の列の **x 範囲** と項（`NAME=値`）を取る。先頭列は行ラベル
- 本文の各行は、その行の帯（行を覆うセルの上端の最小・下端の最大）と各列の x 範囲で
  字形を拾って綴る（`pipeline/common/logical_tables._glyphs_in_box` と同じ読み方）
- 続き断片（`continues_from_previous`）は見出しを持たないので、**親の x 範囲を使い回す**。
  版面が違えば使えないので、断片の左右が親と 8pt 以内であることを確かめる

セル文字列で読めない実例（どれもこの読み方で直る）:

- `CH32FV2x_V3xRM.zh` 表10-44 の `PB14`/`PB15` は、セルの中に**在りもしない縦罫**が
  立って `P`／`PB1`／`4` の3つに割れている
- 同 表10-46 の `PA8`/`PA9` は3列目に落ちる（列が5つに割れる）
- 同 表10-42 の見出しは `FSMCEN=1&USBHSEN=1 &RB_UC_RS` でセル文字列が切れていて、
  条件の3項目が読めない
- `CH32V407RM` 表10-40 は `D4 PE7→PC4` が**次ページの断片**にある

**読めない表は黙って落とさず数を言う**: `CH32FV2x_V3xRM.zh` の表10-45（SPI3）は
版面の罫線が中央の1列しか囲っておらず、行ラベルも2列目も表の外にある。中文版は
読めないので、その4行は英語版だけの `reference` になる。

zh/en 両版で (signal, condition) が同じ pad なら `confirmed`、片方だけなら `reference`、
違えば `conflict`（相手の値を `basis` の `!<出所>(pad=…)` に残す）。

**pin 表が裏付けない行は出さない。** RM は family 単位なので、その family の全 series に
同じことを言ってしまう——`CH32FV2x_V3xRM` は CH32V20x（V203・V208）も担当するが、
あちらに SDIO・DVP・ETH は無い。(series, signal, pad) が `pin_functions` に在る行だけ
出し、落とした数を言う。

実行:
    uv run pipeline/extract/rm/extract_pin_conditions.py [--out <dir>] [--family F]
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
sys.path.insert(0, str(REPO / "pipeline" / "extract" / "rm"))

import bundle_pages  # noqa: E402
import extract_remap  # noqa: E402
import paths  # noqa: E402

COLUMNS = ["series", "signal", "condition", "pad", "#", "confidence", "basis"]

# 重映射の格子だけを見る。表題は zh/en どちらの綴りも受ける。
REMAP_CAPTION = re.compile(r"重映射|remapping", re.IGNORECASE)
# 見出しの項。`FSMCEN=1`・`RB_UC_RST_SIE=0`・`DVP_RM=0`。値は 0/1（`x` は `*_RM` 側の書き方）。
# **直前が数字でも項は始まる**——資料は `&` を落として `DVPEN=1DVP_RM=0默认映射` と続けて
# 刷ることがあり、数字を禁じると2つ目の `DVP_RM=0` が読めない。名前は英字始まりなので
# `1DVP_RM` のような在りもしない名前は作れない（`extract_remap.COLUMN_HEADER` と同じ歯止め）。
TERM = re.compile(r"(?<![A-Za-z_])(?P<name>[A-Z][A-Za-z0-9_]*)\s*=\s*(?P<value>[01])(?![0-9])")
# AFIO の重映射 field。この項だけで出来ている列は `extract_remap` が読む（`remap_routes`）。
RM_FIELD = re.compile(r"_RM\d?$")
PAD = re.compile(r"^P[A-H]\d{1,2}$")
# 「その条件ではこの signal は使えない」。英語版の綴りは資料の誤植のまま受ける。
UNAVAILABLE = re.compile(r"^(?:无效|Invaild|Invalid)$", re.IGNORECASE)
# 脚注の印。見出しにも値にも付く（`(2)Invaild`・`(3)SPI3EN=1&…`）。
FOOTNOTE = re.compile(r"[（(]\d+[）)]")
# 続き断片の見出しの繰り返し（行ラベル列にこれが来る）。
HEADER_WORD = re.compile(r"^(?:复用功能|Alternatefunction|AF)$", re.IGNORECASE)
FRAME_TOLERANCE = 8.0   # 続き断片の左右がこれだけ動いても同じ版面と見る


def terms_of(text: str) -> list[str]:
    """見出しの綴りから条件の項を資料の順で。`FSMCEN=1默认映射` → `['FSMCEN=1']`。"""
    return [f"{m.group('name')}={m.group('value')}"
            for m in TERM.finditer(FOOTNOTE.sub("", text or ""))]


def header_columns(table: dict, chars: list[dict]) -> list[tuple[float, float, list[str]]]:
    """見出し行の列を (x0, x1, 条件の項) で左から。項の無い先頭列が行ラベル。"""
    cells = sorted((c for c in table["cells"] if c["row_start"] == 0),
                   key=lambda c: c["bbox"][0])
    bands = row_bands(table)
    if 0 not in bands:
        return []
    return [(c["bbox"][0], c["bbox"][2],
             terms_of(glyphs_in(chars, c["bbox"][0], c["bbox"][2], *bands[0])))
            for c in cells]


def row_bands(table: dict) -> dict[int, tuple[float, float]]:
    """行番号 → その行を覆うセルの (上端の最小, 下端の最大)。"""
    bands: dict[int, tuple[float, float]] = {}
    for cell in table["cells"]:
        for row in range(cell["row_start"], cell["row_end"]):
            top, bottom = bands.get(row, (cell["bbox"][1], cell["bbox"][3]))
            bands[row] = (min(top, cell["bbox"][1]), max(bottom, cell["bbox"][3]))
    return bands


def glyphs_in(chars: list[dict], x0: float, x1: float,
              top: float, bottom: float, tol: float = 1.0) -> str:
    """箱に**中心が**入る字形を、行帯（3pt刻み）→x順で繋いだ綴り。"""
    inside = [c for c in chars
              if x0 - tol <= (c["x0"] + c["x1"]) / 2 <= x1 + tol
              and top - tol <= (c["top"] + c["bottom"]) / 2 <= bottom + tol
              and (c.get("text") or "").strip()]
    inside.sort(key=lambda c: (round(c["top"] / 3), c["x0"]))
    return "".join(c["text"] for c in inside).replace(" ", "")


def read_value(text: str) -> tuple[str, bool] | None:
    """欄の綴りから (pad, 読めたか)。pad なら (`PB14`, True)、使えないなら (``, True)。"""
    flat = FOOTNOTE.sub("", text or "").strip()
    if PAD.match(flat):
        return flat, True
    if UNAVAILABLE.match(flat):
        return "", True
    return None


def read_bundle(bundle: str) -> tuple[list[dict], list[str]]:
    """1版の格子から (signal, condition, pad, page) の行と、読めなかったものの覚書。"""
    rows: list[dict] = []
    notes: list[str] = []
    open_columns: list[tuple[float, float, list[str]]] | None = None
    open_id = open_caption = None
    open_frame: tuple[float, float] | None = None
    grids: dict[tuple[str, str], dict] = {}   # (logical_id, signal) → 列ごとの pad
    for page in bundle_pages.pages(bundle):
        chars: list[dict] | None = None
        for table in page.get("tables", []):
            caption = ((table.get("caption") or {}).get("text") or "").strip()
            logical_id = table["logical_id"]
            continuation = (table.get("continues_from_previous")
                            and logical_id == open_id and open_columns)
            if not continuation:
                if not REMAP_CAPTION.search(caption):
                    continue
                if chars is None:
                    chars = bundle_pages.chars(page)
                columns = header_columns(table, chars)
                names = {t.split("=")[0] for _x0, _x1, terms in columns for t in terms}
                if not names or all(RM_FIELD.search(n) for n in names):
                    open_columns = open_id = open_caption = None
                    continue    # `*_RM` だけの格子は `extract_remap` の担当
                open_columns, open_id, open_caption = columns, logical_id, caption
                open_frame = (table["bbox"][0], table["bbox"][2])
                first = 1
            else:
                left, right = table["bbox"][0], table["bbox"][2]
                if (abs(left - open_frame[0]) > FRAME_TOLERANCE
                        or abs(right - open_frame[1]) > FRAME_TOLERANCE):
                    # **親は開けたまま跳ばす。** 版面が違う断片は読めないだけで、格子の
                    # 終わりではない——`CH32V407RM` の表10-42 は、親と本当の続き（次ページ）
                    # の**間に**見出しの中央列だけを囲った幅 108pt の断片が挟まる。
                    # ここで親を閉じると、次ページの13行（`D2`・`D3`・`D5` が動く行を含む）が
                    # まるごと落ちる。
                    notes.append(f"{bundle} p.{page['number']} {logical_id}: "
                                 "続き断片の版面が親と違うので読まなかった")
                    continue
                columns, first = open_columns, 0
            if chars is None:
                chars = bundle_pages.chars(page)
            peripheral = extract_remap.caption_peripheral(open_caption)
            bands = row_bands(table)
            for row in sorted(bands)[first:]:
                band = bands[row]
                label = glyphs_in(chars, columns[0][0], columns[0][1], *band)
                if not label or HEADER_WORD.match(label) or terms_of(label):
                    continue    # 続き断片の先頭に繰り返された見出し
                signal = extract_remap.qualify_signal(peripheral, label)
                found = grids.setdefault((logical_id, signal),
                                         {"signal": signal, "page": page["number"],
                                          "pads": {}})
                for x0, x1, terms in columns[1:]:
                    if not terms:
                        continue
                    value = read_value(glyphs_in(chars, x0, x1, *band))
                    if value is None:
                        continue
                    found["pads"]["&".join(terms)] = value[0]
    for (logical_id, _signal), found in grids.items():
        pads = found["pads"]
        if len(pads) < 2 or len(set(pads.values())) < 2:
            continue    # pad が条件で動かない signal は `pinout` が既に言っている
        for condition, pad in pads.items():
            rows.append({"signal": found["signal"], "condition": condition,
                         "pad": pad, "page": found["page"]})
    return rows, notes


def supported(pin_table: dict, series: str, signal: str, pad: str) -> bool:
    """その series の pin 表が (signal, pad) を載せているか。

    **pad が空の行**（「その条件ではこの signal は使えない」）は pad で引けないので、
    signal がその series に在ることだけ見る。見ないと、その周辺を持たない series にも
    「使えない」と言ってしまう（`CH32V203`/`CH32V208` に SPI3_NSS の行が出た）。
    """
    if pad:
        return (signal, pad) in pin_table.get(series, {}).get("pairs", set())
    return signal in pin_table.get(series, {}).get("signals", set())


def read_pin_table() -> dict[str, dict]:
    with paths.table("products").open(newline="", encoding="utf-8") as f:
        series_of = {r["part_number"]: r["series"] for r in csv.DictReader(f)}
    out: dict[str, dict] = collections.defaultdict(
        lambda: {"pairs": set(), "signals": set()})
    with paths.table("pin_functions").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            series = series_of.get(row["part_number"])
            if series:
                out[series]["pairs"].add((row["signal"], row["pad"]))
                out[series]["signals"].add(row["signal"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    ap.add_argument("--family", action="append", default=None)
    args = ap.parse_args()

    with paths.table("families").open(newline="", encoding="utf-8") as f:
        families = {r["family"]: r["series"].split(";") for r in csv.DictReader(f)}
    if args.family:
        families = {k: v for k, v in families.items() if k in set(args.family)}
    pin_table = read_pin_table()

    out_rows: list[dict] = []
    dropped: collections.Counter = collections.Counter()
    for family, series_list in families.items():
        editions: dict[str, tuple[str, list[dict]]] = {}
        for lang, (bundle, document) in bundle_pages.rm_bundles(family).items():
            rows, notes = read_bundle(bundle.name)
            for note in notes:
                print(f"    {note}", file=sys.stderr)
            if rows:
                editions[lang] = (document, rows)
        if not editions:
            continue

        seen: dict[tuple[str, str], dict] = {}
        for lang, (document, rows) in editions.items():
            for row in rows:
                key = (row["signal"], row["condition"])
                entry = seen.setdefault(key, {**row, "said": {}})
                entry["said"][lang] = (row["pad"],
                                       f"rm:{lang}({document} p.{row['page']})")
        settled: dict[str, list[dict]] = collections.defaultdict(list)
        for (signal, condition), entry in seen.items():
            said = entry["said"]
            pads = {p for p, _b in said.values()}
            pad = said.get("zh", said.get("en"))[0]
            if len(said) < 2:
                confidence = "reference"
                basis = "+".join(b for _p, b in said.values())
            elif len(pads) == 1:
                confidence = "confirmed"
                basis = "+".join(said[l][1] for l in ("zh", "en") if l in said)
            else:
                confidence = "conflict"
                other = said["en"] if pad == said["zh"][0] else said["zh"]
                basis = (f"{said['zh'][1] if pad == said['zh'][0] else said['en'][1]}"
                         f"+!{other[1]}(pad={other[0]})")
            settled[signal].append({"signal": signal, "condition": condition,
                                    "pad": pad, "confidence": confidence, "basis": basis})
        # **裏付けは signal ごとに全部か無か。** 片方の pad だけ pin 表に在るとき、
        # 在るほうだけ出すと「その条件のときだけこの pad」と読めてしまい、選択肢が
        # 1つしかない表になる——`CH32V467` の `FSMC_D4` は pin 表が `PC4` だけを載せる
        # ので、`FSMCEN=1→PC4` だけが残って `FSMCEN=0→PE7` が消えていた。
        for series in series_list:
            for signal, group in settled.items():
                if not all(supported(pin_table, series, signal, r["pad"]) for r in group):
                    dropped[(family, series)] += len(group)
                    continue
                out_rows += [{**r, "series": series} for r in group]
        kept = sum(1 for r in out_rows if r["series"] in set(series_list))
        print(f"  {family}: 格子の行 {len(seen)} → {kept} 行"
              f"（pin 表が裏付けず落とした {sum(v for k, v in dropped.items() if k[0] == family)}）",
              file=sys.stderr)

    def order(row: dict) -> tuple:
        return (row["series"], row["signal"], row["condition"].count("&"), row["condition"])

    out_rows.sort(key=order)
    dest = paths.table("pin_conditions", args.out)
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**{c: r.get(c, "") for c in COLUMNS}, "#": "#"} for r in out_rows)
    tally = collections.Counter(r["confidence"] for r in out_rows)
    print(f"{dest}: {len(out_rows)} 行  series {len({r['series'] for r in out_rows})}"
          f"  {dict(tally)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
