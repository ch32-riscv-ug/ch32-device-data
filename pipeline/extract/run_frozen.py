#!/usr/bin/env python3
"""凍結した旧toolを、入力だけbundleへ差し替えて走らせ、凍結CSVとの一致を測る。

「新経路が従来データ以上を取れる」への最短経路は、**変換層を挟んでも各CSVが
byte一致で再現できることを生成器ごとに証明する**こと（`operating_conditions`で
実証済みの方法の一般化）。凍結toolのコードは変更しない——importして、module属性の
`pdfplumber`を`pipeline/extract/pdfcompat`（bundle互換層＋原本hashの入口ゲート）に
差し替え、`--out`でcandidateへ書かせ、出力された全CSVを凍結側とbyte比較する。

multiprocessingを使うtool（`build_all`系）と、pixelを読むtool（`extract_images`）は
対象外（前者は子processへのpatchが要る＝別実装、後者はasset rendererが後継）。

実行:
    uv run pipeline/extract/run_frozen.py build_features build_timers ...
    uv run pipeline/extract/run_frozen.py --batch   # 単一プロセスの定番一式
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import pdfplumber  # noqa: E402  差し替え判定の基準（実物）
import pdfcompat  # noqa: E402

CANDIDATES = REPO / ".cache" / "pipeline-candidates" / "frozen"

# 単一プロセスでPDFを読む凍結tool。--out（D15）を持つものだけ。
BATCH = ("build_features", "build_adc_internal", "build_memory", "build_timers",
         "build_flash_geometry", "build_debug_data", "extract_package_dims")


def patch_all_modules() -> int:
    """読み込まれた全moduleの`pdfplumber`属性を互換層へ差し替える。

    toolは互いにimportし合う（`build_pins`→`extract_pins`など）ので、対象module
    だけでなく連鎖して読み込まれた全部を差し替える。
    """
    patched = 0
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "pdfplumber", None) is pdfplumber:
            module.pdfplumber = pdfcompat
            patched += 1
    return patched


def run_tool(name: str) -> list[tuple[str, str]]:
    out_dir = CANDIDATES / name
    out_dir.mkdir(parents=True, exist_ok=True)
    module = importlib.import_module(name)
    patched = patch_all_modules()
    print(f"[{name}] pdfplumber -> pdfcompat ({patched} modules)", file=sys.stderr)
    argv, sys.argv = sys.argv, [f"{name}.py", "--out", str(out_dir)]
    try:
        module.main()
    finally:
        sys.argv = argv

    results = []
    for produced in sorted(out_dir.glob("*.csv")):
        frozen = None
        for root in (REPO / "evidence", REPO / "catalog", REPO / "index"):
            if (root / produced.name).exists():
                frozen = root / produced.name
                break
        if frozen is None:
            results.append((produced.name, "NO FROZEN COUNTERPART"))
        elif produced.read_bytes() == frozen.read_bytes():
            results.append((produced.name, "byte-identical"))
        else:
            results.append((produced.name,
                            f"DIFFERS from {frozen.relative_to(REPO)} "
                            "(run pipeline/reconcile/compare_csv.py)"))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tools", nargs="*")
    ap.add_argument("--batch", action="store_true", help=f"定番一式: {', '.join(BATCH)}")
    args = ap.parse_args()
    names = list(args.tools) + (list(BATCH) if args.batch else [])
    if not names:
        ap.error("give tool names or --batch")
    verdicts: list[tuple[str, str, str]] = []
    failed = 0
    for name in names:
        try:
            for table, verdict in run_tool(name):
                verdicts.append((name, table, verdict))
        except SystemExit as exc:
            if exc.code not in (0, None):
                verdicts.append((name, "-", f"EXITED {exc.code}"))
        except Exception as exc:  # noqa: BLE001  1本の失敗で残りを止めない
            verdicts.append((name, "-", f"ERROR {type(exc).__name__}: {exc}"))
    print()
    for name, table, verdict in verdicts:
        if verdict != "byte-identical":
            failed += 1
        print(f"  {name:24} {table:28} {verdict}")
    ok = sum(1 for _, _, v in verdicts if v == "byte-identical")
    print(f"\n{ok}/{len(verdicts)} outputs byte-identical to the frozen tables")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
