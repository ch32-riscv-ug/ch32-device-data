#!/usr/bin/env python3
"""凍結した`tools/scan_errata.py`を、入力だけbundleへ差し替えて走らせる。

エラッタの増分検査（KNOWN / NEW の照合）を新経路で行うrunner。凍結toolの
コードは変えない——`scan_errata`をimportして`pdfplumber`属性を
`pipeline/extract/pdfcompat`（bundle互換層＋原本hashの入口ゲート）へ
差し替え、引数（`--rm`・`--only`）はそのまま渡す。対象選定は凍結toolの
まま（mirrorの実ファイルをglob）なので、bundleが無いPDFは黙って跳ばずに
「読み取り失敗」として報告される。

旧新パリティ: `--rm`の全57 PDFで旧（PDF直読み・十数分）と新（bundle・23秒）の
出力と終了コードがbyte一致（2026-09-01実測。KNOWN 21確認・NEW 235も同一）。

実行:
    uv run pipeline/extract/run_scan_errata.py          # DS0のみ
    uv run pipeline/extract/run_scan_errata.py --rm     # RMも走査
終了コード: 凍結toolのまま（NEW候補があれば1）。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import pdfcompat  # noqa: E402
import scan_errata  # noqa: E402


def main() -> int:
    scan_errata.pdfplumber = pdfcompat
    return scan_errata.main()


if __name__ == "__main__":
    sys.exit(main())
