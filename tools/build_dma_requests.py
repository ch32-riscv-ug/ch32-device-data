#!/usr/bin/env python3
"""DMA の要求→channel の対応（R-20 の D-7）→ tables/dma_requests.csv

**EVT header には無く、reference manual の表にしかない**もの。RM の DMA 章にある
「DMAx 各通道外设映射表」（peripheral × channel の格子）を zh/en 両版から読み、
(family, variant, dma, channel, request) で突き合わせる。両版一致で confirmed、
片方だけなら reference。

**表の形は family で5通りある**（2026-08-26 に全 RM を調査）:

1. 1 DMA・7ch・1ページ（V003・V006・M030）
2. 1 DMA・次ページへ続く。続きの表は見出し行を持たない（V103・L103・X035）
3. channel が 8 を超え、`通道1〜7` と `通道8〜` の**2つの表**に割れる（X315・V407・V30x の DMA2）
4. 2 DMA で、`*` 印（`EXTEN_CTLR1` で経路を選ぶ要求）と、セルがページ境界で
   折り返す（V205・V20x/V30x）。V20x/V30x は **1つの章に variant が3組**
   （D8/D8C、D6、D8W/D8）あり、表番号で variant を決める（`VARIANT_OF`）
5. **DMAMUX の番号表**（H417 だけ）。channel は固定でなく、`表10-2` が
   「要求入力番号→周辺」を3組の列で並べる。`request_id` 列に番号を持ち channel は空

読み方の規則（全 family 共通）:

- 見出し行 = 先頭セルが `外设`/`Peripheral`、続きが `通道N`/`Channel N`。見出しの無い
  表が同じ列数で続けば前の表の続き
- 先頭セルが空の行は、前の行のセルがページ境界で折り返したもの（V205 の `TIM1_COM`）
- セル内の改行は複数の要求（`TIM1_CH4\\nTIM1_TRIG`）。ただし `_` で終わる行は
  次の行と1語（V407 の `SPI_I2S2_\\nRX`）
- 印: `*`（EXTEN で経路選択）→ `remap=selectable`、X315 の `_0`/`_1` → `default`/`remap`、
  `（1）` 等の脚注 → `note`。**綴りは資料のまま**（V407 の `13C`、H417 の `I3X_RX` も）

実行:
    uv run tools/build_dma_requests.py [--mirrors <dir>] [--out tables] [--family F]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

import signal_vocabulary  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
MIRRORS = Path("/home/mt/dev_wch")

# `request` は RM の綴りそのまま（zh 版。`TIM1_UP*` の `*`、X315 の `_0`/`_1` も
# 残す）。en 版の綴りが違えば `request_en`。印の読み（selectable / default / remap）
# と peripheral 名は索引 `index/dma.csv` が付ける（tools/build_index.py）。
COLUMNS = ["family", "variant", "dma", "channel", "request_id", "request", "request_en",
           "note", "#", "confidence", "basis"]

HEAD_FIRST = re.compile(r"^(外设|Peripheral)s?$", re.IGNORECASE)
HEAD_CHANNEL = re.compile(r"^(?:通道|Channel)\s*(\d+)$", re.IGNORECASE)
HEAD_MUX = re.compile(r"(DMA\s*请求输入|DMA\s*request\s*input)", re.IGNORECASE)
CAPTION = re.compile(r"(?:表|Table)\s*(?P<number>\d+-\d+)[^\n]*?(?P<dma>DMA\d?)", re.IGNORECASE)
# 図の題（`Table 11-2 DMA2 request mapping`）は表ではない。表の題は「映射表」/「mapping table」。
CAPTION_TABLE = re.compile(r"映射表|mapping\s+table", re.IGNORECASE)
CAPTION_MUX = re.compile(r"(?:表|Table)\s*(?P<number>\d+-\d+)[^\n]*?(?:复用器|multiplexer)", re.IGNORECASE)
FOOTNOTE = re.compile(r"[（(]\d+[)）]")
TOKEN = re.compile(r"^[A-Za-z0-9_/]+$")

# V20x/V30x の RM は1つの章に variant 3組。表番号で決める（EVT の macro 名で）。
VARIANT_OF = {
    ("CH32V307", "11-2"): "CH32V30x_D8|CH32V30x_D8C",
    ("CH32V307", "11-3"): "CH32V30x_D8|CH32V30x_D8C",
    ("CH32V307", "11-4"): "CH32V30x_D8|CH32V30x_D8C",
    ("CH32V20x", "11-5"): "CH32V20x_D6",
    ("CH32V20x", "11-6"): "CH32V20x_D8W|CH32V20x_D8",
}
# 同じ RM を共有する family が読まない表（V307 は D6/D8W の表、V20x は D8C の表）。
SKIP = {
    "CH32V307": {"11-5", "11-6"},
    "CH32V20x": {"11-2", "11-3", "11-4"},
}
# 資料の誤植。綴りは資料のまま残し、note に書く。
TYPO = {"13C": "I3C", "I3X_RX": "I3C_RX"}


REMAPPED = re.compile(r"^(?P<request>[A-Z0-9]+_(?:RX|TX|CH\dN?|UP|TRIG|COM|TC))_(?P<value>[01])$")


ROLES = {"RX", "TX", "UP", "TRIG", "COM", "TC", "RS", "DMA", "BRK", "CC", "TRG"}
# 改行無しで2つの要求が1語に見えるセル（en 版 L103/V205/X035 の `TIM1_CH4TIM1_TRIG`）。
# 周辺名の頭で切って、**両側とも完結した要求名になるときだけ**分ける
# （`SPI_I2S2_RX` は `SPI_` が完結しないので切らない）。
STARTS_REQUEST = re.compile(r"^[A-Z]{2,}\d*_")
GLUED = re.compile(r"(?<=[A-Z0-9])(?=(?:TIM|USART|UART|SPI|I2C|I2S|ADC|DAC|SDIO|SDMMC|USB|CAN|LPTIM|DVP|QSPI|SAI)\d*_)")
BARE = re.compile(r"^[A-Z][A-Z0-9]{2,}\*?$")          # ADC1・QSPI1・ADC・SPI
QUALIFIED = re.compile(r"^[A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?:_[01])?\*?$")


def complete(text: str) -> bool:
    """要求名として完結しているか。英語版はセル内で語の途中で折り返す（`TIM1_CH`/`1`、
    `USART3_T`/`X_0`）ので、完結していない行は次の行と繋ぐ。"""
    text = FOOTNOTE.sub("", text).rstrip("*")
    if "_" not in text:
        return bool(BARE.match(text)) and text not in ROLES
    if not QUALIFIED.match(text):
        return False
    parts = text.split("_")
    tail = parts[-1]
    if tail in ("0", "1") and len(parts) >= 3:
        tail = parts[-2]
    return tail in ROLES or bool(re.fullmatch(r"CH\dN?|CH\d_ETR|[A-Z]\d?_(?:TX|RX)|[A-Z]{1,2}", tail)) \
        or (len(tail) >= 2 and tail.isupper() and tail.isalpha() and tail not in {"T", "R", "C", "CH", "TRI", "CO", "U"}) \
        or bool(re.fullmatch(r"[A-Z]+\d+", tail))


def cell_tokens(cell: str) -> list[tuple[str, str, str, str]]:
    """セル → [(request の正規形, 綴りそのまま, remap の印, note)]。

    改行は複数の要求（`TIM1_CH4\\nTIM1_TRIG`）。ただし **`_` で終わる行**は次の行と
    1語（V407 の `SPI_I2S2_\\nRX`）、**1〜2文字の大文字だけの行**は前の行の切れ端
    （英語版が `TIM1_TRI` / `G` と割る）。要求名に1〜2文字の語は無いので取り違えない。
    """
    lines = [ln.strip() for ln in (cell or "").split("\n") if ln.strip()]
    joined: list[str] = []
    for ln in lines:
        # 前の行が語として完結していなければ（`TIM1_CH`・`USART3_T`・`SPI_I2S2_`）、
        # または今の行が語の切れ端なら（`1`・`X_0`・`G`）、前の行に繋ぐ
        # ただし、完結していない行でも**周辺名で始まる**なら新しい要求の先頭
        # （`TIM1_TRI` の後に `G` が来る形）。前の完結した要求に繋ぐと
        # `TIM1_CH4TIM1_TRIG` になる。
        starts_new = bool(STARTS_REQUEST.match(ln))
        if joined and (not complete(joined[-1]) or (not complete(ln) and not starts_new)):
            joined[-1] += ln
        else:
            joined.append(ln)
    split: list[str] = []
    for text in joined:
        pieces = GLUED.split(text)
        split.extend(pieces if len(pieces) > 1 and all(complete(x) for x in pieces) else [text])
    out = []
    for text in split:
        note = "".join(FOOTNOTE.findall(text))
        text = FOOTNOTE.sub("", text).replace(" ", "")
        verbatim = text
        remap = ""
        if text.endswith("*"):
            remap, text = "selectable", text.rstrip("*")
        m = REMAPPED.match(text)
        if m:
            remap, text = ("default" if m.group("value") == "0" else "remap"), m.group("request")
        if not text or text in ("-", "—", "保留", "Reserved") or not TOKEN.match(text):
            # 要求名は ASCII。脚注の文（`仅适用于CH32F20x_D8…`）が表に入ったものは捨てる
            continue
        out.append((text, verbatim, remap, note))
    return out


def peripheral_of(request: str) -> str:
    # V407 は `SPI_I2S2_RX` と書く（SPI2 と I2S2 が同じ block）。語彙は `SPI` を SPI1 と
    # 読んでしまうので、I2S の番号を SPI の instance にする。
    m = re.match(r"^SPI[_/]I2S(\d)_", request)
    if m:
        return f"SPI{m.group(1)}"
    pair = signal_vocabulary.split(request)
    if pair:
        return pair[0]
    head = request.split("_")[0]
    return signal_vocabulary.canonical_peripheral(head) if head else request


def read_manual(pdf_path: Path, family: str) -> tuple[list[dict], list[str]]:
    """1冊の RM から [{variant, dma, channel, request_id, request, remap, note, page}]。"""
    rows: list[dict] = []
    notes: list[str] = []
    grid: dict | None = None      # 読みかけの格子 {dma, variant, channels:[...], last_row}
    # 遅延 import: tools/build_index.py と check_tables.py がこのモジュールの
    # 正規化規則（REMAPPED・TYPO・peripheral_of）だけを使う。CI は標準ライブラリ
    # だけの python で検査を回すので、PDF を読むときにだけ pdfplumber を要る。
    import pdfplumber  # noqa: PLC0415

    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not re.search(r"DMA", text):
                page.close()
                grid = None
                continue
            captions = [(m.start(), m.group("number"), m.group("dma").upper())
                        for m in CAPTION.finditer(text)
                        if CAPTION_TABLE.search(text[m.start():m.start() + 80])]
            mux_captions = [(m.start(), m.group("number")) for m in CAPTION_MUX.finditer(text)]
            tables = page.find_tables()
            used_captions = 0
            page_has_grid = False
            for table in tables:
                cells = [[(c or "").strip() for c in row] for row in table.extract()]
                if not cells:
                    continue
                head = cells[0]
                # DMAMUX の番号表（H417）。見出しの無い続き（英語版は次ページへ割れる）は
                # 「数字・名前」が交互に並ぶ行の表として認める。
                mux_head = sum(1 for c in head if HEAD_MUX.search(c)) >= 2
                mux_body = (grid is not None and grid.get("mux")
                            and len(head) % 2 == 0
                            and all(r[i].replace("\n", "").isdigit() or not r[i]
                                    for r in cells for i in range(0, len(r) - 1, 2))
                            and any(r[0].replace("\n", "").isdigit() for r in cells))
                if mux_head or mux_body:
                    number = mux_captions[0][1] if mux_captions else (grid or {}).get("table", "")
                    for row in (cells[1:] if mux_head else cells):
                        row = [c.replace("\n", "") for c in row]
                        for i in range(0, len(row) - 1, 2):
                            if row[i].isdigit():
                                for req, verbatim, remap, note in cell_tokens(row[i + 1]):
                                    rows.append({"variant": "", "dma": "", "channel": "",
                                                 "request_id": int(row[i]), "request": req,
                                                 "verbatim": verbatim, "remap": remap, "note": note,
                                                 "page": pno, "table": number})
                    grid = {"mux": True, "table": number, "skip": True, "width": -1}
                    page_has_grid = True
                    continue
                channels = [HEAD_CHANNEL.match(c.replace("\n", "")) for c in head[1:]]
                is_header = bool(head and HEAD_FIRST.match(head[0].replace("\n", ""))
                                 and any(channels))
                if is_header:
                    # 結合セルの None 列（V30x の DMA2 表）は直前の channel に畳む
                    col_channel: list[int | None] = []
                    current = None
                    for m in channels:
                        current = int(m.group(1)) if m else current
                        col_channel.append(current)
                    number, dma = "", "DMA1"
                    if used_captions < len(captions):
                        _, number, dma = captions[used_captions]
                        used_captions += 1
                    elif grid:
                        number, dma = grid["table"], grid["dma"]   # ch8〜 の続きの表
                    if number in SKIP.get(family, set()):
                        grid = {"skip": True}
                        continue
                    grid = {"dma": dma if dma != "DMA" else "DMA1", "table": number,
                            "variant": VARIANT_OF.get((family, number), ""),
                            "cols": col_channel, "width": len(head), "last": None,
                            "skip": False}
                    body = cells[1:]
                    page_has_grid = True
                elif grid and not grid.get("skip") and len(head) == grid["width"]:
                    body = cells          # 見出しの無い続き
                    page_has_grid = True
                elif grid and grid.get("skip") and len(head) == grid.get("width", -1):
                    continue
                else:
                    continue
                for row in body:
                    if not row or all(not c for c in row):
                        continue
                    label = row[0].replace("\n", "")
                    if label and not TOKEN.match(label.replace("（", "(").replace("）", ")").replace("(", "").replace(")", "")):
                        # 脚注の文が表に入ったもの
                        if len(label) > 24 or re.search(r"[一-鿿]{3,}", label):
                            continue
                    if not label and grid["last"] is None:
                        continue
                    for ci, cell in enumerate(row[1:]):
                        channel = grid["cols"][ci] if ci < len(grid["cols"]) else None
                        if channel is None or not cell:
                            continue
                        for req, verbatim, remap, note in cell_tokens(cell):
                            rows.append({"variant": grid["variant"], "dma": grid["dma"],
                                         "channel": channel, "request_id": "",
                                         "request": req, "verbatim": verbatim,
                                         "remap": remap, "note": note,
                                         "page": pno, "table": grid["table"]})
                    if label:
                        grid["last"] = label
            if not page_has_grid and grid and not grid.get("skip"):
                # 格子の無いページが挟まったら読みかけは終わり
                grid = None
            page.close()
    return rows, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    ap.add_argument("--family", action="append", default=None)
    args = ap.parse_args()

    with paths.table("families").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    if args.family:
        families = [x for x in families if x in set(args.family)]

    out_rows: list[dict] = []
    for family in families:
        family_dir = args.mirrors / family
        editions: dict[str, tuple[Path, list[dict]]] = {}
        for lang in ("zh", "en"):
            manuals = sorted((family_dir / f"datasheet_{lang}").glob("*RM.PDF"))
            if not manuals:
                continue
            rows, _ = read_manual(manuals[0], family)
            editions[lang] = (manuals[0], rows)
        if not editions:
            print(f"  - {family}: RM が無い", file=sys.stderr)
            continue

        def key(r: dict) -> tuple:
            # `*` 印（remap=selectable）は zh 版だけが付けることがあるので鍵に入れない。
            # 印は付いている版のものを採り、片方だけなら note に残す。
            return (r["variant"], r["dma"], r["channel"], r["request_id"], r["request"])

        seen: dict[tuple, dict] = {}
        for lang, (path, rows) in editions.items():
            for r in rows:
                k = key(r)
                entry = seen.setdefault(k, {**r, "langs": {}, "spelled": {}})
                entry["langs"][lang] = f"rm:{lang}({path.name} p.{r['page']})"
                entry["spelled"][lang] = r["verbatim"]
                if r["note"] and not entry["note"]:
                    entry["note"] = r["note"]
        for k, e in seen.items():
            langs = e["langs"]
            confidence = "confirmed" if len(langs) == 2 else "reference"
            note = e["note"]
            if e["request"] in TYPO:
                note = (note + "; " if note else "") + f"as printed; RM typo for {TYPO[e['request']]}"
            # 綴りは原典（zh）を採り、en 版が違う綴り（`*` を落とす等）なら並べて残す
            spelled = e["spelled"].get("zh") or e["spelled"].get("en")
            spelled_en = e["spelled"].get("en", "")
            out_rows.append({
                "family": family, "variant": e["variant"], "dma": e["dma"],
                "channel": e["channel"], "request_id": e["request_id"],
                "request": spelled,
                "request_en": spelled_en if spelled_en and spelled_en != spelled else "",
                "note": note,
                "confidence": confidence, "basis": "+".join(langs[l] for l in ("zh", "en") if l in langs),
            })
        tally = collections.Counter(r["confidence"] for r in out_rows if r["family"] == family)
        only = {lang: sum(1 for e in seen.values() if list(e["langs"]) == [lang]) for lang in editions}
        print(f"  {family}: {sum(tally.values())} 行 {dict(tally)} 片翼 {only}", file=sys.stderr)

    out_rows.sort(key=lambda r: (r["family"], r["variant"], r["dma"],
                                 int(r["channel"] or 0), int(r["request_id"] or 0), r["request"]))
    dest = paths.table("dma_requests", args.out)
    if args.family:
        try:
            with dest.open(newline="", encoding="utf-8") as f:
                keep = [r for r in csv.DictReader(f) if r["family"] not in set(args.family)]
        except FileNotFoundError:
            keep = []
        out_rows = sorted(keep + out_rows, key=lambda r: (r["family"], r["variant"], r["dma"],
                                                          int(r["channel"] or 0), int(r["request_id"] or 0), r["request"]))
    with dest.open("w", encoding="utf-8", newline="") as out:
        w = csv.DictWriter(out, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows({**{c: r.get(c, "") for c in COLUMNS}, "#": "#"} for r in out_rows)
    tally = collections.Counter(r["confidence"] for r in out_rows)
    print(f"{dest}: {len(out_rows)} 行  family {len({r['family'] for r in out_rows})}  {dict(tally)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
