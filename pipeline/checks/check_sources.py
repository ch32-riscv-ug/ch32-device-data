#!/usr/bin/env python3
"""mirrorのPDFが、コミット済みmanifestの原本SHAと一致しているかを報告する。

**入力が走行中に変わるのを見つけるための検査**。`pipeline/publish/regenerate.py` は
1時間強かかるので、その途中でmirrorが`git pull`されると、出力は**どの入力状態にも
対応しない**ものになる。2026-09-08に実際に起きた: 目録（`catalog/documents.csv`）は
CH32X315の`version_en`を1.2と言い、bundleは1.1のPDFから作られたまま、その状態で
全再生成が走った。`check_baseline`が赤くなったが原因は別（目録の自動更新が凍結台帳を
書き直していない）で、**CSVが動いたのがコードのせいか資料のせいか区別できなくなった**。

`compare_manifest.py`が2つのmanifestで同じ区別（原本が変わった／環境で再現しない）を
しているのと同じ考えを、**全文書 × いまのmirror**へ広げたもの。読み取りだけで、
ネットワークも要らない。

出口:
    0  全文書が一致（走ってよい）
    1  原本が変わった文書がある／ファイルが無い

実行:
    uv run pipeline/checks/check_sources.py            # 一覧を出す
    uv run pipeline/checks/check_sources.py --quiet    # 食い違いだけ出す
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import convert_all  # noqa: E402  目録が割り当てた文書とmirrorのパス

STRUCTURED = REPO / "structured"


def survey() -> tuple[list[str], list[tuple[str, str, str]], list[str]]:
    """(一致した文書, 原本が変わった文書, 見つからない文書)。"""
    same: list[str] = []
    moved: list[tuple[str, str, str]] = []
    missing: list[str] = []
    for job in convert_all.targets():
        name = job["name"]
        manifest = STRUCTURED / name / "manifest.json"
        pdf = Path(job["pdf"])
        if not manifest.is_file():
            missing.append(f"{name}: structured/{name}/manifest.json が無い")
            continue
        if not pdf.is_file():
            missing.append(f"{name}: 原本 {pdf} が無い")
            continue
        recorded = json.loads(manifest.read_text(encoding="utf-8"))["source"]["sha256"]
        actual = hashlib.sha256(pdf.read_bytes()).hexdigest()
        (same.append(name) if actual == recorded
         else moved.append((name, recorded, actual)))
    return same, moved, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quiet", action="store_true", help="食い違いだけ出す")
    args = ap.parse_args()
    same, moved, missing = survey()
    total = len(same) + len(moved) + len(missing)
    if not args.quiet:
        print(f"原本とmanifestの照合: {len(same)}/{total} 一致")
    for name, recorded, actual in moved:
        print(f"  ★ {name}: manifest={recorded[:12]} いまの原本={actual[:12]}")
    for line in missing:
        print(f"  ★ {line}")
    if moved or missing:
        print("\n**原本が動いています。**この状態で再生成すると、出力が"
              "どの入力状態にも対応しなくなります。")
        print("資料の更新として取り込むなら、**コード変更とは別のcommitで**"
              "再生成してください——CSVが動いたときに原因を分けられなくなります。")
        print("手順は docs/handoff.ja.md 「原本（mirror）にPDFが追加・更新されたとき」。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
