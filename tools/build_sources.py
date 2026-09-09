#!/usr/bin/env python3
"""どの版の原典を読んで生成したか → tables/sources.csv

**このリポジトリは自分の中に原典を持たない。** datasheet の PDF も EVT も
`/home/mt/dev_wch/<FAMILY>/` にある別々の git リポジトリ（mirror）にあり、
それらは GitHub Actions が毎日 15:07 UTC に WCH から取り直して commit/push する。
**入力が勝手に動く**ということで、版を控えておかないと生成物の差分の原因が

    1. 抽出のコードを変えた
    2. mirror が更新された
    3. 誰かが再生成を忘れた

のどれなのか区別できない。`tools/build_all.py` は入力とコードが同じなら何度
回しても差分が出ない（実測済み）ので、**版さえ控えれば差分は 1 か 3 に絞れる**。

**生成時刻は記録しない。** 記録すると回すたびに行が変わり、その「差分が出たら
異常」という判定そのものが使えなくなる。控えるのは commit hash と、その commit
自身が持つ日付だけ——どちらも回しても動かない。

`dirty` は生成した時点で mirror に未コミットの変更があったという印で、これが
立っている行は **commit hash が読んだ中身を説明しない**。

この表は `tables/` を作り直す一連の実行の中で回す（順番は tables/README.ja.md）。
mirror を同期した後・生成の前後どちらでもよいが、**生成の途中で同期しないこと**。

実行:
    uv run tools/build_sources.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
sys.path.insert(0, str(REPO / "pipeline" / "common"))
import held_sources  # noqa: E402  据え置き文書の名簿（regenerate --hold-sources）
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "repository", "commit", "committed_at", "dirty",
           "#", "confidence", "basis"]


def git(repo: Path, *args: str) -> str | None:
    """git の出力。リポジトリでない・コマンドが無い場合は None。"""
    try:
        done = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()

    with paths.table("families").open(newline="", encoding="utf-8") as f:
        families = [(r["family"], r.get("repository", "")) for r in csv.DictReader(f)]

    # 据え置き（`regenerate.py --hold-sources`）: 原本が動いた文書の bundle は前の原本のままなので、
    # その mirror の family は**前の行を保つ**——この表は「出力がどの入力状態に対応するか」を言う表で、
    # mirror の HEAD を書くと bundle（前の commit の PDF）と食い違う（2026-09-09 の走行3で
    # `check_baseline` が捕捉）。取り込み（`--accept-sources`）の走行で HEAD に揃う。
    dest = paths.table("sources", args.out)
    held_repos: set[str] = set()
    if held_sources.names():
        with (REPO / "catalog" / "documents.csv").open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if any(f"{Path(row['document']).stem}.{lang}" in held_sources.names()
                       for lang in ("zh", "en")):
                    held_repos.update(r for r in row["repositories"].split(";") if r)
    previous: dict[str, dict] = {}
    if held_repos and dest.exists():
        with dest.open(newline="", encoding="utf-8") as f:
            previous = {r["family"]: r for r in csv.DictReader(f)}

    rows: list[dict] = []
    notes: list[str] = []
    for family, repository in families:
        if family in held_repos and family in previous:
            rows.append(previous[family])
            notes.append(f"{family}: 据え置き——sources の行を前のまま保つ"
                         f"（commit {previous[family]['commit'][:7]}。bundle が前の原本のため）")
            continue
        path = args.mirrors / family
        if not path.is_dir():
            notes.append(f"{family}: mirror が {path} に無い")
            continue
        commit = git(path, "rev-parse", "HEAD")
        if not commit:
            notes.append(f"{family}: git リポジトリとして読めない——"
                         "版を控えられないので差分の原因を切り分けられない")
            continue
        # 未コミットの変更があると hash は読んだ中身を説明しない。黙って
        # 通すと「版は同じなのに差分が出る」が起きるので、印を立てて言う。
        dirty = bool(git(path, "status", "--porcelain"))
        if dirty:
            notes.append(f"{family}: mirror に未コミットの変更がある——"
                         f"commit {commit[:7]} は読んだ中身を説明しない")
        rows.append({
            "family": family,
            "repository": repository,
            "commit": commit,
            # commit 自身が持つ日付。回しても動かないので冪等性を壊さない。
            "committed_at": git(path, "log", "-1", "--format=%cI") or "",
            "dirty": "1" if dirty else "",
            "confidence": "confirmed",
            "basis": f"git({family})",
        })

    rows.sort(key=lambda r: r["family"])
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    stale = sum(1 for r in rows if r["dirty"])
    print(f"{dest}: {len(rows)} 行"
          + (f"  うち未コミットの変更あり {stale}" if stale else ""), file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
