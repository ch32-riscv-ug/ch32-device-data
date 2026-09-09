#!/usr/bin/env python3
"""新経路の一括再生成entry point（D18工程5の運用化）。

**PDFを直接読む旧`tools/`を実行経路から外す**ための正面玄関。原本（mirror）が
更新されたとき・pipelineの抽出器を直したときは、これ1本を回せば
「bundle再変換 → 切替済みevidenceの再生成 → 下流indexの再導出 → 検査」まで
進む。各段は既存のCLIをそのまま呼ぶ（このtoolは順序と停止だけを持つ）。

段:
    bundles   convert_all（incremental。原本SHA・tool版が一致すれば跳ばす）
    evidence  新経路の正本生成器（operating_conditions・debug_wiring・
              option bytes 2表・device_id 2表ほか）。--full では RM を丸ごと読む
              5本（registers 3表＋register_layouts・opa_cmp_registers・
              clock_enables・usbpd_plumbing・flash_program_method）も加わる
    index     evidenceから導出する索引（debug_interfaces・conflicts・build_index）
    checks    check_tables / check_counts / check_docs
    legacy    --full: **全CSVの再生成**（D18工程(5)の切替後の正規実行形）——
              旧`tools/`の生成器（**もう原本は読まない**。読み手は全部新経路）と
              退役済みの生成器を、依存順どおりに走らせて正本へ書かせる。
              build_all（直列）→ datasheet/RM表群 → EVT系 → 索引 → README生成。
              committedと同一入力なら`git status`差分ゼロで終わる
    verify    --verify: エラッタ増分検査（scan_errata。NEW候補があれば失敗）。
              凍結toolのbundle入力パリティは相手が居なくなって2026-09-10に外した
    human     --human: 図の描画 → 人向けMarkdown → PDFとの差ゼロ検査

実行:
    uv run pipeline/publish/regenerate.py [--full] [--verify] [--human] [--jobs N] [--list]

既定（--fullなし）は新経路の生成器と索引だけの速い再生成。原本（mirror）が
更新されたときの全再生成は`--full`（**約12分**。2026-09-10に原本直読みが無くなって
1時間強から縮んだ）。失敗した段で止まる（後続は
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



# --fullの全再生成の**順序そのもの**（evidence/READMEの「生成」の依存順）。
# 実行の仕方を kind で持つ:
#   plain … 旧`tools/`の生成器。そのまま呼ぶ（**原本はもう読まない**——読み手は
#           全部新経路で、この段に残っているのは候補と目録を組み立てる側だけ）
#   new   … 退役済みの新経路の生成器。argv をそのまま持つ
#
# 2026-09-10 まではもう1つ `patched` があった——PDFを読む凍結toolを `run_patched.py` で
# 互換層に向けて走らせる形。読み手が全部退役して相手が居なくなったので、互換層ごと消した。
#
# **退役した生成器がこの並びの中に残るのは、凍結toolがその出力を読むとき。**
# `extract_pin_tables`（退役 第10号）がそれ——`build_remap` と `build_pin_alternate` が
# `pin_functions.csv` を読むので、evidence 段（legacy の後に走る）へ移すと前回の走行の
# 値を読んでしまう（`timers`・`flash_program_method` で踏んだ形）。読む側が退役したら
# evidence 段へ移せる。
#
# 以前は PATCHED/PLAIN の5つのリストだった。退役が進んで「凍結かどうか」より
# **順序**が本質になったので、1つの並びに畳んだ（2026-09-09）。退役済み:
# `build_memory`（旧 FULL_PATCHED_2）・`build_opa_cmp_registers`・`build_clock_enables`・
# `build_usbpd_plumbing`・`build_registers`・`build_flash_program_method`（旧 FULL_PATCHED_3）
# は evidence 段の `pipeline/extract/rm/` へ。
FULL_ORDER: list[tuple[str, str]] = [
    # `build_all`・`build_tables` は **2026-09-10 に原本を読まなくなった**（退役 第12・13号。
    # 読み手は全部新経路で、この2本は候補と目録を組み立てるだけ）。`run_patched` 経由をやめて
    # そのまま呼ぶ。
    #
    # `--jobs 1` も外した。あれは**互換層の差し替えが worker 子プロセスに効かない**ための
    # 直列化で、互換層が消えた時点で理由が無い。実測（2026-09-10）: 並列 **6.7秒**・
    # 直列 24.3秒で、**出力103ファイルは byte 一致**。PDF を読んでいた頃は直列で約35分だった。
    ("plain", "build_all"),
    ("plain", "build_tables"),
    ("new", "pipeline/extract/datasheet/extract_pin_tables.py"),
    # `build_remap` は `candidates/*.json` と `pin_functions.csv` から作る（原本を読まない）。
    ("plain", "build_remap"),
    ("plain", "build_evt_examples"),
    ("plain", "build_clock"),
    ("plain", "build_systick"),
    ("plain", "build_pin_alternate"),
    ("plain", "build_interrupts"),
    ("plain", "build_memory_map"),
    ("plain", "build_eval_boards"),
    ("plain", "build_sources"),
    ("plain", "build_evt_variants"),
    ("plain", "build_link_firmware"),
]


def legacy_steps() -> list[Step]:
    steps: list[Step] = []
    for kind, spec in FULL_ORDER:
        name, *extra = spec.split()
        if kind == "new":
            steps.append((Path(name).stem, [name, *extra]))
            continue
        steps.append((spec, [f"tools/{name}.py", *extra]))
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
        ] + ([
            # 退役 第9号（2026-09-09）。**`--full` のときだけ**走らせる——この5本は
            # 12 family の RM を丸ごと読むので合わせて約20分かかり、「既定は速い
            # 再生成」という約束を壊す。凍結時も legacy 段（`--full` 専用）に居たので
            # 走る条件は変わっていない。
            #
            # 順序は凍結時のまま: `usbpd_plumbing` は `clock_enables.csv` を読み、
            # `flash_program_method` は `register_fields.csv` を読む（`ctlr_bit_names`）。
            # 先に走ると空になる（R-32）。
            ("register_blocks + registers + register_fields + register_layouts",
             ["pipeline/extract/rm/extract_registers.py"]),
            ("opa_cmp_registers", ["pipeline/extract/rm/extract_opa_cmp_registers.py"]),
            ("clock_enables", ["pipeline/extract/rm/extract_clock_enables.py"]),
            ("usbpd_plumbing", ["pipeline/extract/rm/extract_usbpd_plumbing.py"]),
            ("flash_program_method",
             ["pipeline/extract/rm/extract_flash_program_method.py"]),
        ] if args.full else [])),
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
        # 凍結パリティ（`run_frozen --batch`）は **2026-09-10 に役目を終えて外した**。
        # あれが証明していたのは「凍結toolがbundle入力でも原本直読みと同じバイトを出す」
        # ことで、**原本を読む凍結toolがpipelineから居なくなった**時点で相手が無い
        # （最後まで残った `build_remap` は `candidates/*.json` と `pin_functions.csv` から
        # 作るので、そもそもPDFを読まない）。互換層 `pdfcompat` ごと消した。
        # いま同じ役目を果たしているのは `check_baseline`（正本のバイトを台帳と照合）と
        # `markdown parity`（人向けMarkdownを原本と照合。68/68）で、退役ごとの byte 一致は
        # そのときに実測して `docs/markdown-qa-log.ja.md` に残している。
        stages.append(("verify", [
            ("errata incremental scan",
             ["pipeline/extract/scan_errata.py"]),
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
                    help="全CSVを再生成する（旧tool群も含めて全部。約12分）")
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
    # **`.cache`のbundleとcommit済みmanifestの食い違い**は、走る前に必ず止める。片方だけ戻した
    # 状態で走ると、据え置き（`--hold-sources`）が黙って破れる（`convert_all --skip`は`.cache`を
    # 触らず、当時の互換層は据え置き文書のsha照合を省いた）。逆向きなら古いbundleから正本を作る。
    # 2026-09-09に実際に起きた——取り込みを途中で止めてtracked fileだけ戻した。
    drift = check_sources.cache_drift()
    if drift:
        for name, committed, cached in drift:
            print(f"  ★ {name}: commit済み={committed} .cacheのbundle={cached}", file=sys.stderr)
        print("\n`.cache`のbundleがcommit済みの記録と食い違っています——**片方だけ戻した状態**。\n"
              "取り込むなら `uv run pipeline/ingest/convert_all.py --force --only <文書>` で揃え、\n"
              "撤退するなら`.cache`のbundleも控えから戻してください。", file=sys.stderr)
        return 1
    if moved and not missing and args.hold_sources and not args.accept_sources:
        # 作業中に原本が動いた（mirrorのpullは数時間おきに走る）。据え置いた文書は
        # 前の原本のbundleのままなので、この走行の出力は「コード変更＋前の入力状態」に
        # 対応する。資料更新は次の走行で別のcommitに。
        held = [name for name, _, _ in moved]
        for name, recorded, actual in moved:
            print(f"  ↺ 据え置き {name}: manifest={recorded[:12]} いまの原本={actual[:12]}"
                  "（再変換しない）", file=sys.stderr)
        stages = plan(args, held)
        # 図の描画（render_assets）ほかの入口ゲートに、据え置きを伝える。
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
