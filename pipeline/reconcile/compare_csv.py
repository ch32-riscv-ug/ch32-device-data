#!/usr/bin/env python3
"""凍結CSVとcandidate CSVの多重集合比較（D16の受入手順。D18工程5の道具）。

差分を`unchanged / added / changed / missing`に分ける:

- `--key`を与えると、その列の組で行を対応付け、鍵が同じで中身が違う行を
  `changed`として列名つきで示す
- `--key`が無ければ行全体の多重集合比較（`changed`は出ない）

既存値と違うこと自体を誤りとはしない（D16）——差分は原文リンクを確認して
判定する。byte一致なら何も出さずに終了コード0。

実行:
    uv run pipeline/reconcile/compare_csv.py <frozen.csv> <candidate.csv> [--key col1,col2]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("frozen", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--key", help="行を対応付ける列（カンマ区切り）")
    ap.add_argument("--show", type=int, default=8, help="例示する行数")
    args = ap.parse_args()

    if args.frozen.read_bytes() == args.candidate.read_bytes():
        print(f"byte-identical: {args.frozen} == {args.candidate}")
        return 0

    with args.frozen.open(newline="", encoding="utf-8") as f:
        frozen = list(csv.DictReader(f))
        frozen_columns = list(frozen[0].keys()) if frozen else []
    with args.candidate.open(newline="", encoding="utf-8") as f:
        candidate = list(csv.DictReader(f))
        candidate_columns = list(candidate[0].keys()) if candidate else []
    if frozen and candidate and frozen_columns != candidate_columns:
        print(f"columns differ:\n  frozen   : {frozen_columns}\n"
              f"  candidate: {candidate_columns}", file=sys.stderr)
        return 1

    def row_key(row: dict) -> tuple:
        return tuple(sorted(row.items()))

    if not args.key:
        old = Counter(row_key(r) for r in frozen)
        new = Counter(row_key(r) for r in candidate)
        added = list((new - old).elements())
        missing = list((old - new).elements())
        unchanged = sum((old & new).values())
        print(f"unchanged {unchanged} / added {len(added)} / missing {len(missing)} "
              "(no --key: changed rows count as one added + one missing)")
        for label, rows in (("added", added), ("missing", missing)):
            for row in rows[:args.show]:
                print(f"  {label}: {dict(row)}")
        return 1 if added or missing else 0

    keys = args.key.split(",")
    old_by = {}
    new_by = {}
    for source, table in ((old_by, frozen), (new_by, candidate)):
        for r in table:
            source.setdefault(tuple(r[k] for k in keys), []).append(r)
    added, missing, changed, unchanged = [], [], [], 0
    for key in old_by.keys() | new_by.keys():
        olds = [row_key(r) for r in old_by.get(key, [])]
        news = [row_key(r) for r in new_by.get(key, [])]
        if Counter(olds) == Counter(news):
            unchanged += len(olds)
        elif not olds:
            added.append(key)
        elif not news:
            missing.append(key)
        else:
            fields = sorted({name for a, b in zip(sorted(olds), sorted(news))
                             for (name, va), (_, vb) in zip(a, b) if va != vb})
            changed.append((key, fields))
    print(f"unchanged {unchanged} / added {len(added)} / changed {len(changed)} "
          f"/ missing {len(missing)}  (key: {keys})")
    for label, entries in (("added", added), ("missing", missing)):
        for key in sorted(entries)[:args.show]:
            print(f"  {label}: {dict(zip(keys, key))}")
    for key, fields in sorted(changed)[:args.show]:
        print(f"  changed: {dict(zip(keys, key))} columns={fields}")
    return 1 if added or missing or changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
