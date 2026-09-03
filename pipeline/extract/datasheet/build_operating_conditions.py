#!/usr/bin/env python3
"""`evidence/operating_conditions.csv`の正本生成器（**最初に移行したCSV**）。

D18工程4-5。2つの部品を合成する:

1. **基礎行**——凍結した`tools/build_operating.py`のロジックを、入力だけ
   構造化bundle（`pipeline/extract/pdfcompat`。原本hashの入口ゲート付き）へ
   差し替えて走らせる。凍結時の1,588行を**byte一致**で再現する（2026-09-01実測）
2. **A11の行**——消費電流とウェイクアップ時間（`extract_low_power.collect_rows`。
   caption選定・断片結合・表番号スコープの2段階zh/en照合）

受入判定（2026-09-01、ユーザー委任で実施）: 旧新比較は
unchanged 1,588 / added 1,208 / changed 0 / missing 0。追加行の内訳は
confirmed 1,200 / conflict 6 / reference 2で、conflict 6件は原文突き合わせで
**全て資料側のzh/en齟齬**と裁定（詳細はworklist A11）、reference 2件は
en版だけが行を持つもの。これをもって`operating_conditions.csv`の正本生成元は
このtoolになり、旧`build_operating.py`は参照実装（凍結）のまま。

実行:
    uv run pipeline/extract/datasheet/build_operating_conditions.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))
sys.path.insert(0, str(REPO / "pipeline" / "extract" / "datasheet"))

import build_operating as operating  # noqa: E402  凍結ロジック（読むだけ）
import extract_low_power  # noqa: E402
import paths  # noqa: E402
import pdfcompat  # noqa: E402


def frozen_base_rows() -> list[dict]:
    """凍結ロジックをbundle入力で走らせ、基礎行を得る。"""
    operating.pdfplumber = pdfcompat
    with tempfile.TemporaryDirectory() as scratch:
        argv, sys.argv = sys.argv, ["build_operating.py", "--out", scratch]
        try:
            operating.main()
        finally:
            sys.argv = argv
        with (Path(scratch) / "operating_conditions.csv").open(
                newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))


_BASIS_EN = re.compile(r"([^\s:+!]+)\.PDF:en\(p\.(\d+)\)")


class FoldedCells:
    """bundleごとに、ページ跨ぎの表を続き断片と結合して`fold_page_continuations`を掛け、
    **折り返しで繋がったセル**の全文（正規化済み）をページ番号で引けるようにする（遅延）。

    凍結`build_operating`はページ単位の`extract_text`なので、次ページ先頭行に落ちた
    rowspanセルの続き（`Accuracy of HSI oscillator (after`＋`calibration)`、
    `PLS[2:0] = 100 (falling`＋`edge)`）を拾えず、CSVの括弧が閉じない。続きは
    bundle（L1）側の結合gridには在るので、この層で全文に差し替える。"""

    def __init__(self) -> None:
        self.jobs = {job["name"]: job for job in extract_low_power.convert_all.targets()
                     if job["document_type"] == "datasheet"}
        self._cells: dict[str, dict[int, list[str]]] = {}

    def on_page(self, name: str, page: int) -> list[str]:
        if name not in self._cells:
            self._cells[name] = self._build(name)
        return self._cells[name].get(page, [])

    def _build(self, name: str) -> dict[int, list[str]]:
        out: dict[int, list[str]] = defaultdict(list)
        job = self.jobs.get(name)
        if job is None:
            return out
        fragments: dict[str, list[tuple[int, dict]]] = defaultdict(list)
        for page_number, table in extract_low_power.bundle_tables(name, job["pdf"]):
            fragments[table["logical_id"]].append((page_number, table))
        for parts in fragments.values():
            if len(parts) < 2:
                continue   # 続き断片が無い表は割れない
            joined, row_pages = extract_low_power.join_fragments(parts)
            schema = extract_low_power.infer_schema(joined)
            if schema is None:
                continue
            if not extract_low_power.fold_page_continuations(joined, row_pages, schema):
                continue
            for row, page in zip(joined, row_pages):
                for cell in row:
                    if cell and "\n" in cell:   # 繋いだセルは改行を含む
                        out[page].append(extract_low_power._clean_text(operating.norm_text(cell)))
        return out


def complete_truncated_cells(base: list[dict]) -> int:
    """括弧が閉じていない基礎行の parameter/condition を、bundleの結合gridにある
    同じセルの全文で置き換える。全文は「切れた文の直後が語境界で、括弧が閉じている」
    候補が**1つだけ**のとき採る。置き換えた欄の数を返す。"""
    folded = FoldedCells()
    fixed = 0
    for row in base:
        match = _BASIS_EN.search(row.get("basis") or "")
        if not match:
            continue
        name, page = f"{match.group(1)}.en", int(match.group(2))
        for column in ("parameter", "condition"):
            text = row.get(column) or ""
            if not text or not extract_low_power._unbalanced(text):
                continue
            cands = {full for pg in (page, page + 1) for full in folded.on_page(name, pg)
                     if full.startswith(text) and full[len(text):][:1] == " "
                     and not extract_low_power._unbalanced(full)}
            if len(cands) == 1:
                row[column] = cands.pop()
                fixed += 1
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    args = ap.parse_args()

    base = frozen_base_rows()
    added = extract_low_power.collect_rows()

    # 電源レール名の下付きがセル内折り返しで`V DD`と割れる。凍結`build_operating`
    # （byte再現の参照実装）は触れず、この合成層でbase行の parameter/condition にも
    # 下付き結合を後処理として掛ける（addedはextract_low_power側で結合済み）。
    # build_operatingの「旧出力をbyte再現」は保ったまま、正本CSVだけ綺麗にする層。
    for row in base:
        row["parameter"] = extract_low_power._clean_text(row.get("parameter"))
        row["condition"] = extract_low_power._clean_text(row.get("condition"))
    # ページ跨ぎで切れたセル（括弧未閉じ）はbundleの結合gridの全文で補う（同じ合成層の仕事）。
    completed = complete_truncated_cells(base)
    print(f"括弧未閉じの基礎行をbundleの結合gridで補完: {completed} 欄", file=sys.stderr)

    combined = base + added
    seen: set[tuple] = set()
    rows = []
    for r in combined:
        key = tuple(r.get(c, "") for c in operating.COLUMNS)
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    rows.sort(key=lambda r: (r["series"], r["symbol"], r["condition"], r["typ"]))

    dest = paths.table("operating_conditions", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=operating.COLUMNS)
        w.writeheader()
        w.writerows({**{c: r.get(c, "") for c in operating.COLUMNS}, "#": "#"}
                    for r in rows)
    from collections import Counter  # noqa: PLC0415
    print(f"{dest}: {len(rows)} 行 "
          f"{dict(Counter(r['confidence'] for r in rows))} "
          f"(base {len(base)} + added {len(combined) - len(base)}"
          f", dedup {len(combined) - len(rows)})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
