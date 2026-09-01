#!/usr/bin/env python3
"""凍結toolを、入力だけbundleへ差し替えて**正本へ**書かせる汎用runner。

`run_frozen.py`と同じ差し替え（読み込まれた全moduleの`pdfplumber`属性を
`pipeline/extract/pdfcompat`＝bundle互換層＋原本hashの入口ゲートへ）だが、
`--out`へ逸らさず、引数をそのまま渡して本来の出力先（正本CSV・candidates）に
書かせる。**D18工程(5)の切替後の正規実行形**——凍結toolのコードは変えず、
入力層だけがPDF直読みからbundleに替わる。呼ぶのは`regenerate.py --full`。

実行:
    uv run pipeline/extract/run_patched.py <tool> [args...]
    uv run pipeline/extract/run_patched.py build_all --jobs 1
終了コード: toolのまま。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import pdfplumber  # noqa: E402  差し替え判定の基準（実物）
import pdfcompat  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_patched.py <tool> [args...]", file=sys.stderr)
        return 2
    name = sys.argv[1]
    module = importlib.import_module(name)
    patched = 0
    for loaded in list(sys.modules.values()):
        if loaded is not None and getattr(loaded, "pdfplumber", None) is pdfplumber:
            loaded.pdfplumber = pdfcompat
            patched += 1
    print(f"[{name}] pdfplumber -> pdfcompat ({patched} modules)", file=sys.stderr)
    sys.argv = [f"{name}.py", *sys.argv[2:]]
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
