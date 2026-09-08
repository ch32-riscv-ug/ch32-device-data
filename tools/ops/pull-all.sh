#!/usr/bin/env bash
# このリポジトリを入れている入れ物の中の全リポジトリを pull --ff-only で追いかける
# （人が回す。cron/timer から）。基点はスクリプトの位置から辿るので、checkoutを
# どこへ置いても動く——`$HOME`にも特定のパスにも依存しない。
#
# 目録に載っている原本mirrorだけを追いかけるなら tools/pull_inputs.py で足りる。
# これは「配下の全部」を見る版（ArduinoCore・サンプル集など目録に無いものも含む）。
#
# --ff-only はリポジトリを守る（merge も履歴書き換えもしない）が、**入力が悪い
# タイミングで変わること**は止めない——再生成中の fast-forward は「成功する pull」。
# そこだけは鍵で排他する（`.cache/regenerate.lock`。regenerate.py が置く）。
set -uo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1   # 何をするかだけ出す（pullしない）

# **場所を直書きしない**——このスクリプトの位置から辿る。
#   <collection>/<repo>/tools/ops/pull-all.sh  なので repo は ../.. 、
#   mirrorを並べている入れ物は その親（../../..）。
# `${BASH_SOURCE[0]}` は source されても効く。`pwd -P` でsymlinkを解く。
SELF="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd -- "$SELF/../.." && pwd -P)"
BASE="$(cd -- "$REPO/.." && pwd -P)"
LOCK="$REPO/.cache/regenerate.lock"

# 再生成中は何もしない（工程の途中で入力が変わると出力が無効になる）
if [ -f "$LOCK" ]; then
    pid="$(sed -n 's/.*"pid": *\([0-9]*\).*/\1/p' "$LOCK")"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "SKIP ALL: 再生成が走っています (pid $pid)"
        exit 1
    fi
    echo "NOTE: 死んだ鍵を無視します"
fi

worst=0
# .git は dir（通常）と file（worktree/submodule）の両方があり得る。
# -prune で .git の中は走査しない。
while IFS= read -r -d '' gitpath; do
    repo="$(dirname "$gitpath")"
    echo "=== $repo"

    # untracked も見る——git diff だけでは見落とし、pull が
    # "would be overwritten by merge" で落ちる
    if [ -n "$(git -C "$repo" status --porcelain)" ]; then
        echo "  SKIP: local changes"
        continue
    fi
    # **branchに乗っていない/upstreamが無いものは対象外**（失敗ではない）。
    # この入れ物にはこのリポジトリ自身の作業用checkout（`tools/ch32-device-data`・
    # `ArduinoCore-CH32/.tools/ch32-device-data`）がdetached HEADで置かれていて、
    # pullは必ず失敗する。それをFAILEDに数えると**cronが毎回赤くなり読まれなくなる**。
    if ! git -C "$repo" symbolic-ref -q HEAD >/dev/null; then
        echo "  n/a: detached HEAD"
        continue
    fi
    if ! git -C "$repo" rev-parse -q --verify '@{upstream}' >/dev/null 2>&1; then
        echo "  n/a: upstream 未設定"
        continue
    fi
    if [ "$DRY" = 1 ]; then
        echo "  · git pull --ff-only（--dry-run なので実行しない）"
        continue
    fi
    if ! git -C "$repo" pull --ff-only; then
        echo "  FAILED: $repo"
        worst=2
    fi
done < <(find "$BASE" -name .git -prune -print0 | sort -z)

exit "$worst"
