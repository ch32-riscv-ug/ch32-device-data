#!/usr/bin/env python3
"""新経路の一括再生成entry point（D18工程5の運用化）。

**PDFを直接読む旧`tools/`を実行経路から外す**ための正面玄関。原本（mirror）が
更新されたとき・pipelineの抽出器を直したときは、これ1本を回せば
「bundle再変換 → 切替済みevidenceの再生成 → 下流indexの再導出 → 検査」まで
進む。各段は既存のCLIをそのまま呼ぶ（このtoolは順序と停止だけを持つ）。

段:
    bundles   convert_all（incremental。原本SHA・tool版が一致すれば跳ばす）
    evidence  新経路の正本生成器（operating_conditions・debug_wiring・
              option bytes 2表・device_id 2表）
    index     evidenceから導出する索引（debug_interfaces・conflicts・build_index）
    checks    check_tables / check_counts / check_docs
    legacy    --full: **全CSVの再生成**（D18工程(5)の切替後の正規実行形）——
              凍結toolをコード不変のままbundle入力で走らせて正本へ書かせる
              （`run_patched.py`。PDFを読まないEVT系toolはそのまま）。
              build_all（直列）→ datasheet/RM表群 → EVT系 → 索引 → README生成。
              committedと同一入力なら`git status`差分ゼロで終わる
    verify    --verify: 凍結toolのbundle入力パリティ（run_frozen --batch）＋
              エラッタ増分検査（run_scan_errata。NEW候補があれば失敗）
    human     --human: 図の描画 → 人向けMarkdown → PDFとの差ゼロ検査

実行:
    uv run pipeline/publish/regenerate.py [--full] [--verify] [--human] [--jobs N] [--list]

既定（--fullなし）は新経路の生成器と索引だけの速い再生成。原本（mirror）が
更新されたときの全再生成は`--full`（1時間強）。失敗した段で止まる（後続は
走らない）。2回目の実行が全段成功かつ`git status`が空なら再生成は冪等。
network越しのtool（build_toolchains）と各family repoの画像（extract_images・
check_images）はここに入れない。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

Step = tuple[str, list[str]]  # (label, argv after the interpreter)


# --fullの旧tool群（bundle入力の正規実行形）。PATCHED=PDFを読むので
# run_patched.py経由、PLAIN=EVT・candidates・配布物しか読まないのでそのまま。
# 並びはevidence/READMEの「生成」の依存順。
FULL_PATCHED_1 = ["build_all --jobs 1", "build_tables", "build_pins", "build_remap"]
FULL_PLAIN_1 = ["build_evt_examples", "build_clock", "build_systick",
                "build_pin_alternate"]
FULL_PATCHED_2 = ["build_memory"]
FULL_PLAIN_2 = ["build_interrupts", "build_memory_map"]
FULL_PATCHED_3 = ["build_features", "build_timers", "build_flash_geometry",
                  "build_opa_cmp_registers", "build_clock_enables",
                  "build_adc_internal", "build_usbpd_plumbing",
                  "build_registers --rm-cache .cache/rm", "build_dma_requests",
                  "build_debug_data"]
FULL_PLAIN_3 = ["build_eval_boards", "build_sources", "build_evt_variants",
                "build_link_firmware"]


def legacy_steps() -> list[Step]:
    steps: list[Step] = []
    for patched, names in ((True, FULL_PATCHED_1), (False, FULL_PLAIN_1),
                           (True, FULL_PATCHED_2), (False, FULL_PLAIN_2),
                           (True, FULL_PATCHED_3), (False, FULL_PLAIN_3)):
        for spec in names:
            name, *extra = spec.split()
            argv = (["pipeline/extract/run_patched.py", name, *extra] if patched
                    else [f"tools/{name}.py", *extra])
            steps.append((spec, argv))
    return steps


def plan(args: argparse.Namespace) -> list[tuple[str, list[Step]]]:
    stages: list[tuple[str, list[Step]]] = [
        ("bundles", [
            ("convert_all (incremental)",
             ["pipeline/ingest/convert_all.py", "--jobs", str(args.jobs)]),
        ]),
    ]
    if args.full:
        stages.append(("legacy", legacy_steps()))
    stages += [
        ("evidence", [
            ("operating_conditions",
             ["pipeline/extract/datasheet/build_operating_conditions.py"]),
            ("debug_wiring",
             ["pipeline/extract/manual/extract_debug_wiring.py"]),
            ("option_bytes + option_byte_fields",
             ["pipeline/extract/rm/extract_option_bytes.py"]),
            ("device_id_addresses + device_ids",
             ["tools/build_device_ids.py"]),
        ]),
        ("index", ([
            ("feature_tags", ["tools/build_feature_tags.py"]),
            ("capabilities", ["tools/build_capabilities.py"]),
        ] if args.full else []) + [
            ("debug_interfaces", ["tools/build_debug_interfaces.py"]),
            ("conflicts", ["tools/build_conflicts.py"]),
            ("index + manifest", ["tools/build_index.py"]),
        ] + ([
            ("family READMEs", ["tools/build_readme.py"]),
        ] if args.full else [])),
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
    ap.add_argument("--full", action="store_true",
                    help="全CSVを再生成する（旧tool群をbundle入力で。1時間強）")
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
