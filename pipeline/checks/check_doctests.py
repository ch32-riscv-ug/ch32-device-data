#!/usr/bin/env python3
"""`pipeline/` と `tools/` の doctest を走らせる。

正規化の規則（`norm_value`・`same_unit`・`reads_as_value`・`wrap_rules` ほか）は
**doctest が仕様**で、規則を直すたびに例を足してきた。ところが**その例はどの検査でも
走っていなかった**——`uv run` で通るのは各ファイルを直に叩いたときだけで、
`regenerate.py` の checks 段にも CI にも載っていない（2026-09-11に気づいた。
12ファイル・103例）。規則を書き換えて例のほうを直し忘れても、誰も落ちない。

検査は2つ:

1. **例が全部通ること。**
2. **`>>>` を書いてあるファイルから例が1つも集まらない、が起きないこと。**
   これは実際に踏んだ罠で、`doctest.testmod` は
   `inspect.getmodule(obj) is module` で「そのモジュールの関数か」を見る——
   `importlib.util.module_from_spec` で作った別インスタンスに対して走らせると、
   `sys.modules` に載っている**先に import された同名モジュール**の方が返り、
   例が**0件のまま黙って通る**。だから `import_module` で sys.modules と同じ実体を
   使い、そのうえで「`>>>` があるのに0件」を落とす。

実行:
    uv run pipeline/checks/check_doctests.py
"""

from __future__ import annotations

import doctest
import importlib
import io
import contextlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# 走らせる先。`tools/` は平置き、`pipeline/` は役割ごとの階層で、どちらも
# パッケージではない（各スクリプトが `sys.path` に兄弟ディレクトリを足して import する）。
# 同じ流儀でパスを通してから、ファイル名で import する。
ROOTS = ("pipeline", "tools")


def modules() -> list[tuple[Path, str]]:
    """`>>>` を含む .py を、パスと import 名で返す。"""
    found = []
    here = Path(__file__).resolve()
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            # 自分自身は外す——上の説明が `>>>` を語として含むだけで例は無い。
            if path.resolve() == here:
                continue
            if ">>>" in path.read_text(encoding="utf-8"):
                found.append((path, path.stem))
    return found


def main() -> int:
    files = modules()
    for path, _ in files:
        sys.path.insert(0, str(path.parent))
    bad: list[str] = []
    total = 0
    for path, name in files:
        rel = path.relative_to(REPO)
        try:
            # 出力を飲む——import しただけで進捗を刷るモジュールがある。
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                module = importlib.import_module(name)
                result = doctest.testmod(module, verbose=False, report=False)
        except Exception as error:                      # noqa: BLE001  何であれ落とす
            bad.append(f"{rel}: import できない（{type(error).__name__}: {error}）")
            continue
        if not result.attempted:
            bad.append(f"{rel}: `>>>` を書いてあるのに doctest が1件も集まらない")
            continue
        total += result.attempted
        if result.failed:
            # 失敗の中身は doctest 自身に刷らせる（どの例がどう違ったか）。
            doctest.testmod(module, verbose=False)
            bad.append(f"{rel}: doctest {result.failed} 件が失敗")
        print(f"  {result.attempted:4} 例  {rel}")
    print(f"doctest {total} 例 / {len(files)} ファイル")
    for line in bad:
        print(f"NG {line}", file=sys.stderr)
    if bad:
        print(f"\ndoctest がずれています（{len(bad)} ファイル）。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
