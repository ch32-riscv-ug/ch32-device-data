#!/usr/bin/env python3
"""入力（このリポジトリと原本mirror）を`pull --ff-only`で追いかける。**人が回す**。

数時間おきに入力を追いかけるのは管理として正しい。困るのは**再生成の途中で入ること**
だけで、そうなると出力はどの入力状態にも対応しなくなる（2026-09-08に実際に起きた）。
だから禁止ではなく**排他**にする——このスクリプトは
`pipeline/publish/regenerate.py`が置く鍵（`.cache/regenerate.lock`）を見て跳ばす。

**pullの順序は「このリポジトリ → 該当mirror」**。mirrorはこのリポジトリが公開する
目録（`manifests/documents.json`）を読んで原本を落とすので、機械の順序が
「目録が先・mirrorが後」。同じ向きで追えば「mirrorがまだ追いついていない」が
*待ちの状態*として見える。逆順だと、古い目録で落ちた原本を新しい目録で解釈することに
なり、どちらが遅れているのか分からなくなる。

**このリポジトリは作業ツリーがcleanなときだけpullする**。作業中に目録が変わると、
そのあとCSVが動いたときに「コードのせいか資料のせいか」を分けられなくなる
（`--ff-only`は重なれば自分で拒否するが、重ならなければ黙って通ってしまう）。
mirrorは読み取り専用の入力なのでこの制約は要らない。

pullし終えたら、通信なしの照合（`pipeline/checks/check_sources.py`）を出す——
変換済みが遅れていれば「取り込みが要る」と分かる。取り込みは
`regenerate.py --accept-sources`で、**コード変更とは別のcommit**にする。

出口:
    0  何もすることが無い／全部cleanにpullできた
    1  再生成中・作業ツリーがdirtyで跳ばした（あとで回す）
    2  pullが失敗した（force-push等。人が見る）

実行（cron / systemd timer から。例: 4時間ごと）:
    uv run tools/pull_inputs.py
    uv run tools/pull_inputs.py --dry-run   # 何をするかだけ出す
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
sys.path.insert(0, str(REPO / "pipeline" / "checks"))
import check_sources  # noqa: E402
import convert_all  # noqa: E402

LOCK = REPO / ".cache" / "regenerate.lock"


def busy() -> dict | None:
    """再生成が走っていればその情報（死んだ鍵は無視）。"""
    if not LOCK.is_file():
        return None
    try:
        info = json.loads(LOCK.read_text(encoding="utf-8"))
        os.kill(int(info["pid"]), 0)
    except (ValueError, KeyError, OSError):
        return None
    return info


def git(repo: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(("git", "-C", str(repo), *argv),
                          capture_output=True, text=True, timeout=180)


def dirty(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain").stdout.strip())


def mirrors() -> list[Path]:
    """原本を置いているmirrorのルート（重複なし・名前順）。"""
    roots = {Path(job["pdf"]).parents[1] for job in convert_all.targets()}
    return sorted(roots)


def pull(repo: Path, label: str, dry_run: bool, skip_when_dirty: bool) -> int:
    if not (repo / ".git").exists():
        print(f"  - {label}: git管理外——跳ばす")
        return 0
    if skip_when_dirty and dirty(repo):
        print(f"  ! {label}: 作業ツリーがdirty——跳ばす（作業中に入力を変えない）")
        return 1
    if dry_run:
        print(f"  · {label}: git pull --ff-only（--dry-runなので実行しない）")
        return 0
    done = git(repo, "pull", "--ff-only")
    if done.returncode != 0:
        print(f"  ★ {label}: pullが失敗しました\n{done.stderr.strip()}")
        return 2
    head = git(repo, "log", "-1", "--format=%h %s").stdout.strip()
    moved = "Already up to date" not in done.stdout
    print(f"  {'↓' if moved else '='} {label}: {head}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="何をするかだけ出す")
    args = ap.parse_args()

    running = busy()
    if running:
        print(f"再生成が走っています（pid {running['pid']}・開始 {running['started']}）"
              "——pullは跳ばします。工程の途中で入力が変わると出力が無効になります。")
        return 1

    worst = 0
    print("=== このリポジトリ")
    worst = max(worst, pull(REPO, REPO.name, args.dry_run, skip_when_dirty=True))
    print("=== 原本mirror")
    for root in mirrors():
        worst = max(worst, pull(root, root.name, args.dry_run, skip_when_dirty=True))

    if args.dry_run:
        return 0
    print()
    same, moved, missing = check_sources.survey()
    total = len(same) + len(moved) + len(missing)
    print(f"=== 原本とmanifestの照合: {len(same)}/{total} 一致")
    for name, recorded, actual in moved:
        print(f"  ★ {name}: manifest={recorded[:12]} いまの原本={actual[:12]}")
    for line in missing:
        print(f"  ★ {line}")
    if moved or missing:
        print("\n取り込みが要ります: `uv run pipeline/publish/regenerate.py "
              "--full --verify --human --accept-sources`")
        print("**コード変更とは別のcommitにしてください**——CSVが動いたときに"
              "原因を分けられなくなります。")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
