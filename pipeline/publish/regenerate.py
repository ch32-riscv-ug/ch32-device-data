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
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "checks"))
sys.path.insert(0, str(REPO / "pipeline" / "common"))
import check_sources  # noqa: E402  走行の前後で原本を照合する
import held_sources  # noqa: E402  据え置き文書の名簿（--hold-sources）
import runlock  # noqa: E402  原本を読む間の鍵（pull側が見て跳ばす。入れ子は通る）

Step = tuple[str, list[str]]  # (label, argv after the interpreter)



# --fullの旧tool群（bundle入力の正規実行形）。PATCHED=PDFを読むので
# run_patched.py経由、PLAIN=EVT・candidates・配布物しか読まないのでそのまま。
# 並びはevidence/READMEの「生成」の依存順。
FULL_PATCHED_1 = ["build_all --jobs 1", "build_tables", "build_pins", "build_remap"]
FULL_PLAIN_1 = ["build_evt_examples", "build_clock", "build_systick",
                "build_pin_alternate"]
# FULL_PATCHED_2（`build_memory`）は2026-09-09に退役して evidence 段の
# `pipeline/extract/rm/extract_memory.py` になった。PDFを読む段が1つ減った。
FULL_PLAIN_2 = ["build_interrupts", "build_memory_map"]
# build_registersに--rm-cacheを渡さない——cacheは原本更新後も**無検証で再利用され、
# 正本を古い読みへ戻す**（2026-09-02の初回--fullで実際に踏んだ: 08-26製のcacheが
# X315 RM改版前のARGB番地0x40023400を返し、registers 9行が偽conflictになった。
# check_docsが捕捉→revert）。bundle入力ならcache無しでも数分で済む。
FULL_PATCHED_3 = ["build_opa_cmp_registers", "build_clock_enables",
                  "build_usbpd_plumbing",
                  "build_registers",
                  # build_registers の後でなければならない——`ctlr_bit_names` は
                  # `register_fields.csv` の綴りをそのまま出す列なので、先に走ると
                  # 空になる（R-32。登録漏れで --full が拾っていなかった）。
                  "build_flash_program_method"]
FULL_PLAIN_3 = ["build_eval_boards", "build_sources", "build_evt_variants",
                "build_link_firmware"]


def legacy_steps() -> list[Step]:
    steps: list[Step] = []
    for patched, names in ((True, FULL_PATCHED_1), (False, FULL_PLAIN_1),
                           (False, FULL_PLAIN_2),
                           (True, FULL_PATCHED_3), (False, FULL_PLAIN_3)):
        for spec in names:
            name, *extra = spec.split()
            argv = (["pipeline/extract/run_patched.py", name, *extra] if patched
                    else [f"tools/{name}.py", *extra])
            steps.append((spec, argv))
    return steps


def plan(args: argparse.Namespace, held: list[str] = ()) -> list[tuple[str, list[Step]]]:
    stages: list[tuple[str, list[Step]]] = [
        ("bundles", [
            ("convert_all (incremental)",
             ["pipeline/ingest/convert_all.py", "--jobs", str(args.jobs),
              *(["--skip", ",".join(held)] if held else [])]),
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
            # 凍結tool `build_dma_requests` の退役（2026-09-09）: bundle 入力で byte 一致を確認して
            # 新経路へ切替。毎回走る（数秒）。
            ("dma_requests", ["pipeline/extract/rm/extract_dma_requests.py"]),
            # 凍結tool `build_features` の退役（2026-09-09）: 同じく byte 一致で切替。
            ("features", ["pipeline/extract/datasheet/extract_features.py"]),
            # 退役の第3・4号（2026-09-09）。`timers` は legacy 段では `evt_variants` より**前**に
            # 走っていて前回の走行の値を読んでいた——evidence 段なら同じ走行の値を読む。
            ("timers", ["pipeline/extract/rm/extract_timers.py"]),
            ("debug_data", ["pipeline/extract/manual/extract_debug_data.py"]),
            # 退役の第5〜7号（2026-09-09）。**`memory_configs` は `flash_geometry` より前**
            # ——後者が前者を読む（option byte で領域が動く family の zero-wait 注記）。
            ("memory_configs", ["pipeline/extract/rm/extract_memory.py"]),
            ("flash_geometry", ["pipeline/extract/rm/extract_flash_geometry.py"]),
            ("adc_internal", ["pipeline/extract/datasheet/extract_adc_internal.py"]),
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
            # 正本が動いたのに凍結台帳を書き直していないと落ちる。台帳を読むコードが
            # 無かったせいで27表が黙ってずれていた（2026-09-06）。
            ("check_baseline", ["tools/check_baseline.py"]),
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
    ap.add_argument("--accept-sources", action="store_true",
                    help="原本が動いている状態で走る（資料更新の取り込みとして。"
                         "コード変更と混ぜないこと）")
    ap.add_argument("--hold-sources", action="store_true",
                    help="動いた原本を**据え置いて**走る——その文書のbundleは前の原本のまま"
                         "再変換せず、他の文書だけ回す（コード変更の検証を資料更新と混ぜない"
                         "ため。取り込みは別のcommitで`--accept-sources`）")
    args = ap.parse_args()

    stages = plan(args)
    if args.list:
        for stage, steps in stages:
            print(f"{stage}:")
            for label, argv in steps:
                print(f"  {label:36} uv run {argv[0]} {' '.join(argv[1:])}".rstrip())
        return 0

    # **入力が走行中に変わるのを見つける**（2026-09-08に実際に起きた。1時間強かかる
    # 工程の途中でmirrorが`git pull`されると、出力はどの入力状態にも対応しなくなり、
    # CSVが動いたのがコードのせいか資料のせいか区別できなくなる）。
    before = check_sources.survey()
    same, moved, missing = before
    print(f"=== 原本の照合: {len(same)}/{len(same) + len(moved) + len(missing)} 一致",
          file=sys.stderr)
    if moved and not missing and args.hold_sources and not args.accept_sources:
        # 作業中に原本が動いた（mirrorのpullは数時間おきに走る）。据え置いた文書は
        # 前の原本のbundleのままなので、この走行の出力は「コード変更＋前の入力状態」に
        # 対応する。資料更新は次の走行で別のcommitに。
        held = [name for name, _, _ in moved]
        for name, recorded, actual in moved:
            print(f"  ↺ 据え置き {name}: manifest={recorded[:12]} いまの原本={actual[:12]}"
                  "（再変換しない）", file=sys.stderr)
        stages = plan(args, held)
        # 凍結tool（pdfcompat）と図の描画（render_assets）の入口ゲートに、据え置きを伝える。
        # 伝えないとゲートが拒否して**その文書が落ち、family が目録から消える**（2026-09-09）。
        os.environ[held_sources.ENV] = ",".join(held)
    elif (moved or missing) and not args.accept_sources:
        for name, recorded, actual in moved:
            print(f"  ★ {name}: manifest={recorded[:12]} いまの原本={actual[:12]}",
                  file=sys.stderr)
        for line in missing:
            print(f"  ★ {line}", file=sys.stderr)
        print("\n原本が動いています。資料更新の取り込みなら `--accept-sources` を付けて、"
              "**コード変更とは別のcommitで**走らせてください。", file=sys.stderr)
        return 1

    with runlock.acquire("regenerate") as taken:
        if not taken:
            return 1
        return run(stages, before)


def run(stages: list[tuple[str, list[Step]]], before: tuple) -> int:
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
    # 走行の**後**にもう一度照合する。集合が変わっていればこの走行は無効——
    # 出力は「途中まで旧原本・途中から新原本」の混合で、再現もできない。
    after = check_sources.survey()
    if after != before:
        print("\n★ 走行中に原本が変わりました（mirrorがpullされた）。"
              "この出力はどの入力状態にも対応しません——**やり直してください**。",
              file=sys.stderr)
        was = {n for n, _, _ in before[1]} | set(before[2])
        now = {n for n, _, _ in after[1]} | set(after[2])
        for name in sorted(now - was):
            print(f"  ★ 走行中に動いた: {name}", file=sys.stderr)
        for name in sorted(was - now):
            print(f"  ★ 走行中に取り込まれた: {name}", file=sys.stderr)
        return 1
    print("\n=== 全段成功", file=sys.stderr)
    for stage, label, took in done:
        print(f"  {stage:9} {label:36} {took:6.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
