#!/usr/bin/env python3
"""凍結した`build_operating`のロジックを構造化bundle入力で走らせる（D18工程4）。

最初の移行CSVは`operating_conditions.csv`（D17項目7で決定）。このrunnerは
**抽出規則を1行も変えず**、凍結した`tools/build_operating.py`をimportして
入力だけを`pipeline/extract/pdfcompat`（bundle互換層＋原本hashの入口ゲート）へ
差し替え、candidateを`.cache/pipeline-candidates/operating_conditions.csv`に書く。

凍結CSVとの一致は`pipeline/reconcile/compare_csv.py`で確認する:

    uv run pipeline/extract/datasheet/run_operating.py
    uv run pipeline/reconcile/compare_csv.py \
        evidence/operating_conditions.csv \
        .cache/pipeline-candidates/operating_conditions.csv

一致すれば「変換層を挟んでも既存1,588行を失わない」の実証で、A11の追加行は
この土台の上に**新しい表選択規則**として実装する（別作業）。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CANDIDATES = REPO / ".cache" / "pipeline-candidates"

sys.path.insert(0, str(REPO / "pipeline" / "extract"))
sys.path.insert(0, str(REPO / "tools"))

import pdfcompat  # noqa: E402
import build_operating  # noqa: E402


def main() -> int:
    # 凍結した抽出ロジックの入力だけを差し替える。正本には書かない。
    build_operating.pdfplumber = pdfcompat
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    sys.argv = [sys.argv[0], "--out", str(CANDIDATES)]
    build_operating.main()
    print(f"candidate: {CANDIDATES / 'operating_conditions.csv'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
