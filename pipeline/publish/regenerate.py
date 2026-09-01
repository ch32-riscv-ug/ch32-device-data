#!/usr/bin/env python3
"""新経路の一括再生成entry point（D18工程5の運用化）。

**PDFを直接読む旧`tools/`を実行経路から外す**ための正面玄関。原本（mirror）が
更新されたとき・pipelineの抽出器を直したときは、これ1本を回せば
「bundle再変換 → 切替済みevidenceの再生成 → 下流indexの再導出 → 検査」まで
進む。各段は既存のCLIをそのまま呼ぶ（このtoolは順序と停止だけを持つ）。

段:
    bundles   convert_all（incremental。原本SHA・tool版が一致すれば跳ばす）
    evidence  切替済みの正本生成器（operating_conditions・debug_wiring）
    index     evidenceから導出する索引（debug_interfaces・conflicts・build_index）
    checks    check_tables / check_counts / check_docs
    verify    --verify: 凍結toolのbundle入力パリティ（run_frozen --batch）＋
              エラッタ増分検査（run_scan_errata。NEW候補があれば失敗）
    human     --human: 図の描画 → 人向けMarkdown → PDFとの差ゼロ検査

**まだ旧経路に残っている生成器**（datasheet表群・RM表群・EVT系）はここに
入れない——凍結中で、再生成の必要が無い。CSVが新経路へ切り替わるたびに
`evidence`段へ1行足す。

実行:
    uv run pipeline/publish/regenerate.py [--verify] [--human] [--jobs N] [--list]

失敗した段で止まる（後続は走らない）。2回目の実行が全段成功かつ
`git status`が空なら再生成は冪等。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

Step = tuple[str, list[str]]  # (label, argv after the interpreter)


def plan(args: argparse.Namespace) -> list[tuple[str, list[Step]]]:
    stages: list[tuple[str, list[Step]]] = [
        ("bundles", [
            ("convert_all (incremental)",
             ["pipeline/ingest/convert_all.py", "--jobs", str(args.jobs)]),
        ]),
        ("evidence", [
            ("operating_conditions",
             ["pipeline/extract/datasheet/build_operating_conditions.py"]),
            ("debug_wiring",
             ["pipeline/extract/manual/extract_debug_wiring.py"]),
            ("option_bytes + option_byte_fields",
             ["pipeline/extract/rm/extract_option_bytes.py"]),
        ]),
        ("index", [
            ("debug_interfaces", ["tools/build_debug_interfaces.py"]),
            ("conflicts", ["tools/build_conflicts.py"]),
            ("index + manifest", ["tools/build_index.py"]),
        ]),
        ("checks", [
            ("check_tables", ["tools/check_tables.py"]),
            ("check_counts", ["tools/check_counts.py"]),
            ("check_docs", ["tools/check_docs.py"]),
        ]),
    ]
    if args.verify:
        stages.append(("verify", [
            ("frozen parity (run_frozen --batch)",
             ["pipeline/extract/run_frozen.py", "--batch"]),
            ("errata incremental scan",
             ["pipeline/extract/run_scan_errata.py"]),
        ]))
    if args.human:
        stages.append(("human", [
            ("render figure assets", ["pipeline/review/render_assets.py", "--all"]),
            ("export markdown", ["pipeline/review/export_markdown.py", "--all"]),
            ("markdown parity", ["pipeline/checks/check_markdown_parity.py", "--all"]),
        ]))
    return stages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verify", action="store_true",
                    help="凍結toolのパリティ一式とエラッタ増分検査も回す")
    ap.add_argument("--human", action="store_true",
                    help="図の描画と人向けMarkdownと差ゼロ検査も回す")
    ap.add_argument("--jobs", type=int, default=4, help="convert_allの並列数")
    ap.add_argument("--list", action="store_true", help="計画だけ表示して実行しない")
    args = ap.parse_args()

    stages = plan(args)
    if args.list:
        for stage, steps in stages:
            print(f"{stage}:")
            for label, argv in steps:
                print(f"  {label:36} uv run {argv[0]} {' '.join(argv[1:])}".rstrip())
        return 0

    done: list[tuple[str, str, float]] = []
    for stage, steps in stages:
        for label, argv in steps:
            print(f"\n=== [{stage}] {label}: uv run {' '.join(argv)}", file=sys.stderr)
            started = time.perf_counter()
            code = subprocess.run(
                [sys.executable, str(REPO / argv[0]), *argv[1:]], cwd=REPO).returncode
            took = time.perf_counter() - started
            done.append((stage, label, took))
            if code != 0:
                print(f"\nFAILED [{stage}] {label} (exit {code}) -- 後続は走らせない",
                      file=sys.stderr)
                return code
    print("\n=== 全段成功", file=sys.stderr)
    for stage, label, took in done:
        print(f"  {stage:9} {label:36} {took:6.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
