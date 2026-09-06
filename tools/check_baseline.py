#!/usr/bin/env python3
"""凍結台帳（`pipeline/baseline/tables.csv`）と正本CSVの実物を突き合わせる。

台帳は正本53表の**行数とSHA-256**を凍結時点で記録したもので、`pipeline/README`は
「解凍は明示的な行為として台帳を書き直す」と約束しています。ところが**台帳を読む
コードが1本も無かった**ため、約束を守り忘れても何も落ちず、2026-09-06に数えたら
**27表がずれていました**（正本は正しく、台帳だけが古い状態）。腐り検出器そのものが
腐っていたわけです。この検査はその穴を塞ぎます——**正本が動いたら同じcommitで台帳も
動かす**、それだけを見ます。

ずれたときは、その変化が意図したものかを**先に確かめてから**書き直してください
（生成器を`--out`でスクラッチに走らせて正本とbyte比較するのが確実です）。確かめた後は:

    uv run tools/check_baseline.py --record

実行:
    uv run tools/check_baseline.py [--record]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "pipeline" / "baseline" / "tables.csv"
COLUMNS = ["table", "rows", "sha256"]
# 正本CSVはこの3ディレクトリにしか置かない（`tools/paths.py`が場所を1箇所で決めている）。
# **台帳に載っていない正本が1つでもあれば、その表には腐り検出が無い**ので落とす——
# 凍結後に新設した5表（`option_bytes`ほか）が実際にその状態で漏れていた（2026-09-06）。
CANONICAL_DIRS = ("catalog", "evidence", "index")


def actual(path: Path) -> tuple[str, str]:
    """(行数, sha256)。行数はヘッダを除いた**CSVのレコード数**（改行を含む値があるので
    `wc -l`では数えられない）。hashはファイルのバイト列に対して。"""
    with path.open(newline="", encoding="utf-8") as f:
        rows = sum(1 for _ in csv.reader(f)) - 1
    return str(rows), hashlib.sha256(path.read_bytes()).hexdigest()


def canonical() -> list[str]:
    """正本CSVのリポジトリ相対パス（並びは台帳と同じ辞書順）。"""
    return sorted(str(p.relative_to(REPO))
                  for d in CANONICAL_DIRS
                  for p in (REPO / d).glob("*.csv"))


def drift() -> tuple[list[dict], list[tuple[dict, str, str]], list[dict], list[str]]:
    """(台帳の全行, ずれ[(行, 実際の行数, 実際のhash)], 実物が無い行, 台帳に無い正本)。"""
    with LEDGER.open(newline="", encoding="utf-8") as f:
        entries = list(csv.DictReader(f))
    moved, missing = [], []
    for entry in entries:
        path = REPO / entry["table"]
        if not path.exists():
            missing.append(entry)
            continue
        rows, sha = actual(path)
        if (rows, sha) != (entry["rows"], entry["sha256"]):
            moved.append((entry, rows, sha))
    uncovered = [t for t in canonical() if t not in {e["table"] for e in entries}]
    return entries, moved, missing, uncovered


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true",
                    help="ずれた分を台帳に書き直す（**変化を確かめた後で**）")
    args = ap.parse_args()

    entries, moved, missing, uncovered = drift()
    for entry in missing:
        print(f"{entry['table']}: 台帳にあるのに実物が無い", file=sys.stderr)
    for entry, rows, sha in moved:
        change = (f"{entry['rows']} 行 → {rows} 行" if rows != entry["rows"]
                  else f"{entry['rows']} 行のまま中身が変わった")
        print(f"{entry['table']}: {change}", file=sys.stderr)
        if args.record:
            entry["rows"], entry["sha256"] = rows, sha
    for table in uncovered:
        print(f"{table}: 正本なのに台帳に無い（腐り検出が掛かっていない）", file=sys.stderr)
        if args.record:
            rows, sha = actual(REPO / table)
            entries.append({"table": table, "rows": rows, "sha256": sha})

    if args.record and (moved or uncovered):
        entries.sort(key=lambda e: e["table"])
        with LEDGER.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(entries)
        print(f"台帳を書き直しました（更新 {len(moved)} 表・追加 {len(uncovered)} 表）",
              file=sys.stderr)
        return 1 if missing else 0

    if moved or missing or uncovered:
        print(f"\n凍結台帳と正本がずれています（更新が要る {len(moved)} 表・"
              f"実物なし {len(missing)}・台帳に無い {len(uncovered)}）。"
              "\n**まずその変化が意図したものかを確かめてください**——生成器を `--out` で"
              "スクラッチに走らせ、\n正本と byte 比較するのが確実です。確かめたら "
              "`uv run tools/check_baseline.py --record` で台帳を\n同じcommitに含めてください。",
              file=sys.stderr)
        return 1
    print(f"凍結台帳と正本は一致しています（{len(entries)} 表）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
