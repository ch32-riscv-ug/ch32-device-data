#!/usr/bin/env python3
"""A11: 消費電流とウェイクアップ時間の行を構造化bundleから抽出する（D18工程4）。

出力は`.cache/pipeline-candidates/`のcandidateで、**正本には書かない**。

旧経路のA11実装が差し戻された根因は表の選択だった——markerが当たったページの
「次のページも1ページだけ見る」継続規則で対象表を拾っていたため、どの表を読むかが
ページ割りに依存し、zh/enで読む表の集合が食い違って`I_DD`83行のうち18行が
偽conflictになった。この抽出器は**表をcaption（表題）で選ぶ**。captionは
bundleが`source_number`つきで持ち、zh/enの表番号は1:1に対応する（D17実測）ので、
両版は必ず同じ論理表の集合を読む。

対象captionの語彙（増えたら生成が落ちるのではなく、単に選ばれないだけなので、
worklist A11の完了判定は行数の突き合わせで行う）:

- zh: 电流消耗／功耗／唤醒的时间／FLASH进入低功耗模式（L103・V205系のrun-mode表は
  表題が設定条件で、消耗の語を含まない）
- en: current consumption／power consumption／wakeup time／FLASH enters low-power mode

**選ばない**もの（語彙が当たらないことを確認済み・2026-09-01の34版棚卸し）:
I/O出力駆動電流特性（输出驱动电流特性）、ISINK/ISOURCE模块电流特性、
OPA/CMP特性（低功耗模式）——消費電流ではなく別領域の特性表。

表のパーサ規則（先行PoC `tools/extract_operating_structured.py` で
V003/L103/H417/V007の全件一致を実証したものを、0.2 bundle向けに移植）:

- **物理断片は`logical_id`で束ね、x座標で1つの格子に結合してから読む**
  （L1「列構造一致」の最初の実装）。header断片とdata断片は物理列数が
  違うことがある——空の列は罫線が引かれるまで物理セルにならないので、
  header-only断片では消える（V203 4-6-1のzh版で実測: header断片6列・
  data断片7列。幅比較でschemaを継いだ実装はここで劣化パスに落ち、
  en36行/zh18行の非対称→偽conflictの連鎖を作った）。列は幅ではなく
  **セルのx座標を全断片で束ねた辺の集合**で対応付ける
- **結合セルの引き継ぎは記号が変わったら捨てる**（新しい記号の行でstateを作り直す）
- **値の列を割るのは、同じ種類（min/typ/max）の列が2箇所以上ある表だけ**。
  普通のmin/typ/max表を3行に割らない（doctestで固定）
- 行の採否・記号/値の正規化は凍結した`tools/build_operating.py`の規則を
  そのまま使う（`keep_row`・`UNIT_FOR`）
- **zh/en照合は表番号のスコープで2段階**: まず同じ表番号（zh/enで1:1に
  対応する）の中で照合し、残りをdatasheet全体で照合する。第2段は
  版どうしで表番号がずれる既知の1件（CH32V007 enの3-9-2重複）のため。
  照合規則そのもの（symbol＋min/max一致、unit/typは両方あるときだけ）は
  凍結`build_operating`と同じ

実行:
    uv run pipeline/extract/datasheet/extract_low_power.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
sys.path.insert(0, str(REPO / "pipeline" / "common"))

import build_operating as operating  # noqa: E402  凍結ロジック（読むだけ）
import convert_all  # noqa: E402
import review_sidecar  # noqa: E402
import logical_tables  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
CANDIDATES = REPO / ".cache" / "pipeline-candidates"

CAPTION_PAT = {
    # `功耗`は`低功耗模式`（OPA/CMP特性の表題）にも当たるので負の後読みで除く。
    # 蓝牙BLE功耗（V208 4-6-2）は当たる。L103系のrun-mode表は表題が設定条件で、
    # 「FLASH（不）进入低功耗模式」の肯定・否定の両形がある（3-7-1〜3-7-3）。
    "zh": re.compile(r"电流消耗|(?<!低)功耗|唤醒的时间|FLASH不?进入低功耗模式"),
    "en": re.compile(r"current\s+consumption|power\s+consumption|wakeup\s+time"
                     r"|FLASH\s+(?:enters|does\s+not\s+enter)\s+low-power\s+mode",
                     re.IGNORECASE),
}
TABLE_PREFIX = re.compile(r"^(?:Table|表)\s*\d+(?:-\d+)*\s*", re.IGNORECASE)


def norm_header(cell: str | None) -> str | None:
    """headerの正規化。多段headerの`Condition:`型見出しも受ける（PoCと同じ）。"""
    text = operating.FOOTNOTE.sub("", cell or "")
    text = re.sub(r"\s+", "", text).replace(".", "")
    if text.lower().startswith("condition:"):
        text = "condition"
    return operating.HEADER_MAP.get(text.lower() if text.isascii() else text)


def _header_labels(table: list[list[str | None]], header_end: int) -> dict[int, str]:
    labels = {}
    for column in range(max(map(len, table))):
        parts = []
        for row in table[:header_end]:
            cell = row[column] if column < len(row) else None
            text = operating.norm_text(cell)
            if text and norm_header(cell) is None and text not in parts:
                parts.append(text)
        labels[column] = " ".join(parts)
    return labels


def infer_schema(table: list[list[str | None]]) -> dict | None:
    """物理表の格子 → 列の割り当て（symbol/parameter/条件列/値列/単位）。

    入力は`join_fragments`が結合済みの1論理表なので、headerは（あれば）
    先頭側にある。普通のmin/typ/max表は値列が1本ずつで、行は割れない:

    >>> schema = infer_schema([["Symbol", "Parameter", "Min", "Typ", "Max", "Unit"],
    ...                        ["V_X", "x", "1", "2", "3", "V"]])
    >>> sorted(schema["values"].items())
    [(2, 'min'), (3, 'typ'), (4, 'max')]
    """
    if not table:
        return None
    width = max(map(len, table))
    padded = [list(row) + [None] * (width - len(row)) for row in table]
    header_at = None
    headers = None
    for index, row in enumerate(padded[:4]):
        candidate = [norm_header(cell) for cell in row]
        if "symbol" in candidate and "parameter" in candidate and "unit" in candidate:
            header_at, headers = index, candidate
            break
    if header_at is None:
        data_start = next((index for index, row in enumerate(padded[:4])
                           if operating.KEEP.match(operating.norm_symbol(row[0]))), None)
        if data_start is None or width < 5:
            return None
        first = padded[data_start]
        if not operating.norm_text(first[1]) or not operating.norm_value(first[-1]):
            return None
        return {
            "width": width,
            "symbol": 0,
            "parameter": 1,
            "unit": width - 1,
            "conditions": list(range(2, width - 2)),
            "values": {width - 2: "typ"},
            "labels": _header_labels(padded, data_start),
            "data_start": data_start,
            "continued": False,
        }

    positions = {name: index for index, name in enumerate(headers) if name}
    values = {index: name for index, name in enumerate(headers)
              if name in {"min", "typ", "max"}}
    if not values:
        return None
    symbol_column = positions["symbol"]
    data_start = header_at + 1
    while data_start < min(len(padded), header_at + 5):
        symbol = operating.norm_symbol(padded[data_start][symbol_column])
        if symbol and symbol not in operating.HEADER_ROW:
            break
        data_start += 1
    labels = _header_labels(padded[header_at:data_start], data_start - header_at)
    unit_column = positions["unit"]
    # 多段headerで値種の右に無名の列が続くとき（周波数別のtyp列など）は
    # 同じ種として広げる。ここで同種が2列以上になった表だけ、あとで行を割る。
    for column, kind in list(sorted(values.items())):
        following = min([position for position in list(values) + [unit_column]
                         if position > column], default=unit_column)
        for extra in range(column + 1, following):
            if headers[extra] is None and labels.get(extra):
                values[extra] = kind
    first_value = min(values)
    assigned = {symbol_column, positions["parameter"], unit_column, *values}
    conditions = [index for index in range(positions["parameter"] + 1, first_value)
                  if index not in assigned]
    if "condition" in positions and positions["condition"] not in conditions:
        conditions.insert(0, positions["condition"])
    return {
        "width": width,
        "symbol": symbol_column,
        "parameter": positions["parameter"],
        "unit": unit_column,
        "conditions": sorted(set(conditions)),
        "values": dict(sorted(values.items())),
        "labels": labels,
        "data_start": data_start,
        "continued": False,
    }


def _condition_text(state: dict, schema: dict, value_column: int | None,
                    table_context: str) -> str:
    parts = [table_context] if table_context else []
    for column in schema["conditions"]:
        value = state["conditions"].get(column, "")
        if value:
            label = schema["labels"].get(column, "")
            parts.append(f"{label}={value}" if label else value)
    if value_column is not None:
        label = schema["labels"].get(value_column, "")
        if label:
            parts.append(label)
    return "; ".join(parts)


def parse_table(table: list[list[str | None]], schema: dict,
                lang: str, row_pages: list[int], table_context: str) -> list[dict]:
    width = schema["width"]
    output = []
    state: dict = {}
    counts = Counter(schema["values"].values())
    split_kinds = {kind for kind, count in counts.items() if count > 1}
    for row_index in range(schema["data_start"], len(table)):
        raw = table[row_index]
        page = row_pages[row_index]
        cells = list(raw) + [None] * (width - len(raw))
        # ページ跨ぎの続き断片はheader行を繰り返す。stateに触れずに読み飛ばす
        # ——「Symbol」を記号として引き継ぐと以降の行が全部落ち、「Unit」が
        # 単位として残る（V208 4-8で実測）。
        if operating.norm_text(cells[schema["symbol"]]) in operating.HEADER_ROW:
            continue
        symbol = operating.norm_symbol(cells[schema["symbol"]])
        parameter = operating.norm_text(cells[schema["parameter"]])
        if symbol:
            # 新しい記号の行。結合セルの引き継ぎは記号が変わったら捨てる。
            state = {"symbol": symbol, "parameter": parameter,
                     "unit": state.get("unit", ""), "conditions": {}}
        elif not state.get("symbol"):
            continue
        elif parameter:
            state["parameter"] = parameter
        unit = operating.norm_value(cells[schema["unit"]])
        if unit:
            state["unit"] = unit
        for column in schema["conditions"]:
            value = operating.norm_text(cells[column])
            if value:
                state["conditions"][column] = value
        values = {column: operating.norm_value(cells[column])
                  for column in schema["values"]}
        if not (symbol or parameter or unit or any(values.values())):
            continue
        duplicate = next(iter(split_kinds), None)
        selected = ([column for column, kind in schema["values"].items()
                     if kind == duplicate and values[column]] if duplicate else [None])
        if duplicate and not selected:
            selected = [None]
        for value_column in selected:
            row_values = {"min": "", "typ": "", "max": ""}
            for column, kind in schema["values"].items():
                if kind != duplicate or column == value_column:
                    row_values[kind] = values[column]
            if not any(row_values.values()):
                continue          # 条件だけの継続行。値の主張が無いので採らない
            row = {
                "symbol": state["symbol"],
                "parameter": state["parameter"],
                "condition": _condition_text(state, schema, value_column, table_context),
                **row_values,
                "unit": state["unit"],
            }
            if operating.keep_row(row, lang, page):
                output.append({**row, "_page": page})
    return output


def join_fragments(fragments: list[tuple[int, dict]]) -> tuple[list[list[str | None]],
                                                               list[int]]:
    """同じ論理表の物理断片を1つの格子に結合する（共通L1層の部品を使う）。

    列の対応付け規則（列数が同じなら位置・違えばx和集合）と、その根拠の実測は
    `pipeline/common/logical_tables.py`に移した。
    """
    return logical_tables.text_grid(logical_tables.merge_cells(fragments))


def caption_context(table: dict) -> str:
    caption = table.get("caption")
    if not caption:
        return ""
    # 表題の設定条件（V=3.3V・LDOTRIM=…・対象chip名）はその表全体の条件。
    # 原文の綴りのまま条件の先頭に残す（意味づけはreviewの仕事）。
    return TABLE_PREFIX.sub("", caption["text"]).strip()


def bundle_tables(name: str, pdf: Path):
    """bundleの表を文書順に返す。入口ゲート: 原本SHA-256とmanifestを照合。
    L2 sidecarでrejectedのblockは正本生成に使わない（黙って跳ばさず数を言う）。"""
    bundle = BUNDLES / name
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    actual = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if manifest["source"]["sha256"] != actual:
        raise SystemExit(f"{bundle}: bundle was converted from a different original "
                         "-- run pipeline/ingest/convert_all.py first")
    rejected = review_sidecar.rejected_ids(name)
    skipped = 0
    for entry in manifest["pages"]:
        payload = (bundle / entry["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
        page = json.loads(payload)
        for table in page["tables"]:
            if table["id"] in rejected:
                skipped += 1
                continue
            yield page["number"], table
    if skipped:
        print(f"    {name}: reviewでrejectedの表 {skipped} 個を外した", file=sys.stderr)


def read_edition(name: str, pdf: Path, lang: str,
                 selected_numbers: set[str]) -> list[dict]:
    """caption番号で選んだ表（と、その続き断片）を結合してから行を取る。"""
    fragments: dict[str, list[tuple[int, dict]]] = {}
    order: list[str] = []
    selected_logical: set[str] = set()
    for page_number, table in bundle_tables(name, pdf):
        logical_id = table["logical_id"]
        caption = table.get("caption")
        if caption:
            if caption["source_number"] not in selected_numbers:
                continue
            selected_logical.add(logical_id)
        elif not (table["continues_from_previous"] and logical_id in selected_logical):
            continue
        if logical_id not in fragments:
            fragments[logical_id] = []
            order.append(logical_id)
        fragments[logical_id].append((page_number, table))

    rows: list[dict] = []
    for logical_id in order:
        parts = fragments[logical_id]
        joined, row_pages = join_fragments(parts)
        schema = infer_schema(joined)
        if schema is None:
            print(f"    {name} {logical_id}: 列割り当てを決められない"
                  f"（{len(parts)}断片）", file=sys.stderr)
            continue
        context = next((caption_context(t) for _, t in parts if t.get("caption")), "")
        for row in parse_table(joined, schema, lang, row_pages, context):
            rows.append({**row, "_table": logical_id})
    return rows


def selected_numbers_for(names: dict[str, str], pdfs: dict[str, Path]) -> set[str]:
    """zh/enどちらかのcaptionが対象語彙に当たる表番号の和集合。"""
    numbers: set[str] = set()
    for lang, name in names.items():
        for _, table in bundle_tables(name, pdfs[lang]):
            caption = table.get("caption")
            if caption and CAPTION_PAT[lang].search(caption["text"]):
                numbers.add(caption["source_number"])
    return numbers


def merge_editions(datasheet: str, series: str, en_rows: list[dict],
                   zh_rows: list[dict]) -> list[dict]:
    """zh/en照合。照合規則（symbol＋min/max、unit/typは両方あるときだけ）と
    basis表記は凍結build_operatingと同じ。**対応付けは表番号のスコープで2段階**——
    まず同じ論理表の中で値の一致を探し、残りだけをdatasheet全体で探す。
    ずれの影響が表の中に閉じ、旧経路の「表の集合の食い違いが偽conflictの連鎖に
    なる」再発を防ぐ。第2段は版どうしで表番号がずれる既知の1件
    （CH32V007 enの3-9-2重複）のためにある。
    """
    def agrees(zh, en):
        if zh["min"] != en["min"] or zh["max"] != en["max"]:
            return False
        for key in ("unit", "typ"):
            if zh[key] and en[key] and zh[key] != en[key]:
                return False
        return True

    remaining = list(zh_rows)
    resolved: dict[int, tuple[str, dict | None]] = {}

    # 第1段: 同じ論理表の中の値一致。
    for index, row in enumerate(en_rows):
        cands = [z for z in remaining
                 if z["symbol"] == row["symbol"] and z["_table"] == row["_table"]]
        exact = next((z for z in cands if agrees(z, row)), None)
        if exact:
            remaining.remove(exact)
            resolved[index] = ("confirmed", exact)

    # 第2段: 残りをdatasheet全体で。値一致→confirmed、同表候補→conflict、
    # 他表候補→conflict、無ければreference。
    for index, row in enumerate(en_rows):
        if index in resolved:
            continue
        cands = [z for z in remaining if z["symbol"] == row["symbol"]]
        exact = next((z for z in cands if agrees(z, row)), None)
        if exact:
            remaining.remove(exact)
            resolved[index] = ("confirmed", exact)
            continue
        same_table = [z for z in cands if z["_table"] == row["_table"]]
        pick = (same_table or cands)[0] if cands else None
        if pick:
            remaining.remove(pick)
            resolved[index] = ("conflict", pick)
        else:
            resolved[index] = ("reference", None)

    out = []
    for index, row in enumerate(en_rows):
        row = dict(row)
        en_page = row.pop("_page")
        row.pop("_table", None)
        verdict, partner = resolved[index]
        if verdict == "confirmed":
            if not row["typ"] and partner["typ"]:
                row["typ"] = partner["typ"]
            basis = (f"{datasheet}:zh(p.{partner['_page']})"
                     f"+{datasheet}:en(p.{en_page})")
        elif verdict == "conflict":
            diff = ",".join(f"{k}={partner[k]}"
                            for k in ("min", "typ", "max", "unit")
                            if partner[k] != row[k])
            basis = f"{datasheet}:en(p.{en_page})+!{datasheet}:zh({diff})"
        else:
            basis = f"{datasheet}:en(p.{en_page})"
        out.append({**row, "series": series, "#": "#",
                    "confidence": verdict, "basis": basis,
                    "datasheet": datasheet})
    return out


def collect_rows() -> list[dict]:
    """全datasheetからA11の行を集める（正本生成器も使う入口）。"""
    with (REPO / "catalog" / "products.csv").open(newline="", encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    ds_series: dict[str, set] = {}
    for p in products:
        ds_series.setdefault(p["datasheet"], set()).add(p["series"])

    jobs: dict[str, dict] = {}
    for job in convert_all.targets():
        if job["document_type"] != "datasheet":
            continue
        stem = job["name"].rsplit(".", 1)[0]
        jobs.setdefault(stem, {})[job["lang"]] = job

    rows: list[dict] = []
    for stem, langs in sorted(jobs.items()):
        datasheet = f"{stem}.PDF"
        if datasheet not in ds_series:
            continue
        if "en" not in langs:
            # 旧経路と同じ扱い: 英語版の無いdatasheet（DS2系）はまだ採らない。
            print(f"{datasheet}: 英語版が無いので見送り（zh単独版の扱いはreview設計後）",
                  file=sys.stderr)
            continue
        names = {lang: job["name"] for lang, job in langs.items()}
        pdfs = {lang: job["pdf"] for lang, job in langs.items()}
        numbers = selected_numbers_for(names, pdfs)
        if not numbers:
            print(f"{datasheet}: 対象captionが1つも無い", file=sys.stderr)
            continue
        editions = {lang: read_edition(names[lang], pdfs[lang], lang, numbers)
                    for lang in names}
        series = ";".join(sorted(ds_series[datasheet]))
        merged = merge_editions(datasheet, series,
                                editions.get("en", []), editions.get("zh", []))
        print(f"  {datasheet}: tables {len(numbers)}  en {len(editions.get('en', []))}"
              f" / zh {len(editions.get('zh', []))} -> {len(merged)} rows",
              file=sys.stderr)
        rows.extend(merged)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=CANDIDATES,
                    help="candidateの出力先の上書き（試験用）")
    args = ap.parse_args()

    new_rows = collect_rows()

    # 凍結CSVに新しい行を足した candidate を作る（正本には書かない）。
    frozen_path = REPO / "evidence" / "operating_conditions.csv"
    with frozen_path.open(newline="", encoding="utf-8") as f:
        frozen = list(csv.DictReader(f))
    combined = frozen + new_rows
    seen: set[tuple] = set()
    unique = []
    for r in combined:
        key = tuple(r.get(c, "") for c in operating.COLUMNS)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    unique.sort(key=lambda r: (r["series"], r["symbol"], r["condition"], r["typ"]))

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("low_power_rows.csv", new_rows),
                       ("operating_conditions_with_a11.csv", unique)):
        with (args.out / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=operating.COLUMNS)
            w.writeheader()
            w.writerows({**{c: r.get(c, "") for c in operating.COLUMNS}, "#": "#"}
                        for r in rows)

    kinds = Counter(r["confidence"] for r in new_rows)
    symbols = Counter(r["symbol"] for r in new_rows)
    print(f"new rows: {len(new_rows)}  {dict(kinds)}", file=sys.stderr)
    print(f"top symbols: {symbols.most_common(10)}", file=sys.stderr)
    print(f"combined candidate: {len(unique)} rows "
          f"({len(unique) - len(frozen)} added over frozen {len(frozen)})", file=sys.stderr)
    if operating.DROPPED:
        print(f"  噛み合わないので採らなかった行 {len(operating.DROPPED)}:", file=sys.stderr)
        for line in dict.fromkeys(operating.DROPPED):
            print(f"    - {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
