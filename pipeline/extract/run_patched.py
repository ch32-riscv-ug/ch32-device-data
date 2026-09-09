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
    # **関数内の遅延import**（`build_debug_data`は`import pdfplumber`を
    # 関数の中で行う）は属性の差し替えを迂回する——patch時点で属性が無いから。
    # `sys.modules`ごと差し替えれば、後から解決されるimportも互換層を受け取る。
    sys.modules["pdfplumber"] = pdfcompat
    module = importlib.import_module(name)
    # **基準は局所に控える。** `pdfplumber`はこのmoduleのグローバルなので、ループが
    # `__main__`（このrunner自身）を差し替えた瞬間に基準そのものがpdfcompatへ変わり、
    # `sys.modules`で後に来るmodule——**差し替えたい凍結tool本体**——が全部素通りして
    # いた（`sys.modules`は`__main__`が先。ログの`(1 modules)`がその印）。
    # 2026-09-08まで凍結toolはbundleではなく**原本PDFを直読みしていた**。
    real = pdfplumber
    patched = 0
    for loaded in list(sys.modules.values()):
        if loaded is not None and getattr(loaded, "pdfplumber", None) is real:
            loaded.pdfplumber = pdfcompat
            patched += 1
    # `sys.modules`を先に差し替えるので、toolの属性は最初からpdfcompat——属性ループが
    # 数えるのは先にimport済みのmodule（runner自身）だけ。数は指標にならない。
    print(f"[{name}] pdfplumber -> pdfcompat (sys.modules swapped; {patched} earlier import(s) patched)",
          file=sys.stderr)
    sys.argv = [f"{name}.py", *sys.argv[2:]]
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
