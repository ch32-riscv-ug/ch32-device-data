#!/usr/bin/env python3
"""**原本を読んでいる間の鍵**（`.cache/regenerate.lock`）。

入力（mirrorのPDF・目録）を数時間おきに`pull --ff-only`で追いかけるのは管理として
正しい。困るのは**原本を読んでいる工程の途中で入ること**だけなので、禁止ではなく
排他にする——`tools/pull_inputs.py`と`tools/ops/pull-all.sh`はこの鍵を見て跳ばす。

取るのは**原本を読む工程**: `pipeline/publish/regenerate.py`（全周）と
`pipeline/ingest/convert_all.py`（増分変換。handoffの手順2で単体でも呼ぶ）。
ファイル名は`regenerate.lock`のまま——既にhandoffとpull側が名指ししている。

死んだ鍵は無視して奪う（VSCodeの再起動や10分のシェル切断で残るため）。

    with runlock.acquire() as taken:
        if not taken:
            return 1     # 別の工程が原本を読んでいる
        ...
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCK = REPO / ".cache" / "regenerate.lock"


def held_by() -> dict | None:
    """鍵の持ち主（生きているプロセスのものだけ）。死んだ鍵はNone。"""
    if not LOCK.is_file():
        return None
    try:
        info = json.loads(LOCK.read_text(encoding="utf-8"))
        os.kill(int(info["pid"]), 0)
    except (ValueError, KeyError, OSError):
        return None
    return info


# 鍵を持っている工程が子へ伝える印。`regenerate.py`は`convert_all.py`を子プロセスと
# して呼ぶので、**入れ子は取り直さない**（親が持っているのに子が拒否されて第1段で
# 落ちる）。pidの祖先を辿るより環境変数の方が確実（多段の`uv run`を挟むため）。
INHERITED = "CH32_RUNLOCK_HELD"


@contextlib.contextmanager
def acquire(what: str):
    """鍵を取る。取れなければ`False`をyieldし、持ち主を標準エラーへ出す。

    既に鍵を持っている工程の**子**なら、取り直さずそのまま通す（`INHERITED`）。
    """
    import sys
    if os.environ.get(INHERITED):
        yield True
        return
    other = held_by()
    if other:
        print(f"別の工程が原本を読んでいます（{other.get('what', '?')}・"
              f"pid {other['pid']}・開始 {other['started']}）。"
              "同時に走らせると入力も出力も混ざります。", file=sys.stderr)
        yield False
        return
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps({"pid": os.getpid(), "what": what,
                                "started": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                    encoding="utf-8")
    os.environ[INHERITED] = what
    try:
        yield True
    finally:
        os.environ.pop(INHERITED, None)
        LOCK.unlink(missing_ok=True)
