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

更新は**三者**でずれる。①目録の版（このリポジトリ`catalog/documents.csv`。GitHub
Actionsがcommitするので**このリポジトリのpull**が要る）、②原本の実体（mirrorのPDF。
mirror側の自動取得なので**各mirrorのpull**が要る）、③変換済みの記録
（`structured/*/manifest.json`）。②vs③は通信なしで分かる（既定）。①も含めた
「どのリポジトリをpullすべきか」は`--remote`で`git ls-remote`を引いて名指しする。

**`regenerate.py`が走行の前後で呼ぶのは通信なしの②vs③だけ**——1時間強の工程の門に
ネットワークを置くと、落ちたときに原因が増える。`--remote`は人が判断するための報告。

出口:
    0  全文書が一致（走ってよい）
    1  原本が変わった文書がある／ファイルが無い／未取得のcommitがある（--remote時）

実行:
    uv run pipeline/checks/check_sources.py            # 一覧を出す（通信なし）
    uv run pipeline/checks/check_sources.py --quiet    # 食い違いだけ出す
    uv run pipeline/checks/check_sources.py --remote   # pullすべきリポジトリも名指しする
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import convert_all  # noqa: E402  目録が割り当てた文書とmirrorのパス

STRUCTURED = REPO / "structured"
BUNDLES = REPO / ".cache" / "structured-bundles"


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


def cache_drift() -> list[tuple[str, str, str]]:
    """(文書, commit済みの記録, .cacheの記録) —— **`.cache`のbundleがcommit済みmanifestと
    食い違う**文書。読み取りだけ。

    正本CSVは`.cache/structured-bundles`のbundleから作られ、その出自は
    `structured/<文書>/manifest.json`にcommitされる。この2つは常に一致していなければ
    ならない——**片方だけ戻すと壊れる**。2026-09-09に実際に起きた: 資料更新の取り込みを
    途中で止めて**tracked fileだけ**を戻したので、`structured/CH32X035DS0.zh/manifest.json`は
    旧原本（147f0d22d073・converter 1.14.0）に戻ったのに、`.cache`のbundleは新原本
    （a3f2a0f66cfc・1.16.0）のまま残った。

    この状態は**据え置き（`--hold-sources`）を黙って破る**: `survey()`はcommit済みmanifestと
    mirrorのPDFを比べて「動いた」と言い、`convert_all --skip`はそのbundleを触らず、
    `pdfcompat`は据え置き文書のsha照合を省く——だから凍結toolは**新原本のbundleを読みながら
    「旧原本で据え置いている」と信じる**。逆向き（commitが新しく`.cache`が古い）も同じく危険で、
    `up_to_date`が「最新」と判断して再変換を跳ばし、古いbundleから正本を作る。

    `.cache`が無い（初めての checkout）のは食い違いではない——`convert_all`が作る。
    """
    out: list[tuple[str, str, str]] = []
    for job in convert_all.targets():
        name = job["name"]
        committed, cached = STRUCTURED / name / "manifest.json", BUNDLES / name / "manifest.json"
        if not (committed.is_file() and cached.is_file()):
            continue
        a = json.loads(committed.read_text(encoding="utf-8"))
        b = json.loads(cached.read_text(encoding="utf-8"))
        if a == b:
            continue

        def tag(m: dict) -> str:
            return f"{m['source']['sha256'][:12]}/{m['conversion']['converter_version']}"
        out.append((name, tag(a), tag(b)))
    return out


def mirror_roots() -> dict[str, Path]:
    """mirrorのルート → そこに原本を置いている文書の数。"""
    roots: dict[Path, int] = {}
    for job in convert_all.targets():
        # 原本は <mirror>/datasheet_<lang>/<file> に置かれている
        roots[Path(job["pdf"]).parents[1]] = roots.get(Path(job["pdf"]).parents[1], 0) + 1
    return {str(k): v for k, v in sorted(roots.items())}


def unpulled(repo: Path) -> str | None:
    """originのHEADが手元に**無い**なら、その短いhashを返す（読み取りだけ）。

    hashの不一致で判断していたので、**未pushのcommitが1つあると毎回「pullが要る」**と
    言っていた（2026-09-09に発覚。このリポジトリでコード変更を3つcommitした直後の
    セッション開始検査が誤警報を出した）。引くものがあるかは**祖先関係**で決まる——
    originのHEADが手元のHEADの祖先なら、こちらが先行しているだけで引くものは無い。
    手元にそのcommitが無ければ `--is-ancestor` は失敗するので、そのまま「要る」と読む
    （分岐しているときも「要る」＝正しい）。
    """
    if not (repo / ".git").exists():
        return None
    def git(*argv: str) -> str:
        return subprocess.run(("git", "-C", str(repo), *argv), capture_output=True,
                              text=True, timeout=30).stdout.strip()
    local = git("rev-parse", "HEAD")
    remote = git("ls-remote", "origin", "HEAD").split()
    if not local or not remote:
        return None      # originが無い/引けない——判断の材料にしない
    if remote[0] == local:
        return None
    ancestor = subprocess.run(
        ("git", "-C", str(repo), "merge-base", "--is-ancestor", remote[0], "HEAD"),
        capture_output=True, timeout=30)
    return None if ancestor.returncode == 0 else remote[0][:12]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quiet", action="store_true", help="食い違いだけ出す")
    ap.add_argument("--remote", action="store_true",
                    help="originを引いて、pullすべきリポジトリを名指しする")
    args = ap.parse_args()
    same, moved, missing = survey()
    total = len(same) + len(moved) + len(missing)
    if not args.quiet:
        print(f"原本とmanifestの照合: {len(same)}/{total} 一致")
    drift = cache_drift()
    for name, committed, cached in drift:
        print(f"  ★ {name}: commit済み={committed} .cacheのbundle={cached}"
              " ——**片方だけ戻した状態**")
    for name, recorded, actual in moved:
        print(f"  ★ {name}: manifest={recorded[:12]} いまの原本={actual[:12]}")
    for line in missing:
        print(f"  ★ {line}")
    behind: list[str] = []
    if args.remote:
        print("\n未取得のcommit（originを引いた結果）:")
        for label, repo in [("このリポジトリ", REPO)] + [
                (f"mirror {Path(root).name}（原本{count}件）", Path(root))
                for root, count in mirror_roots().items()]:
            head = unpulled(repo)
            if head:
                behind.append(label)
                print(f"  ★ {label}: origin={head} ——**pullが要る**")
        if not behind:
            print("  すべて最新")
    if drift:
        print("\n**`.cache`のbundleがcommit済みの記録と食い違っています。**"
              "正本はbundleから作られ、その出自はmanifestにcommitされるので、"
              "この2つは常に一致していなければなりません。")
        print("片方だけ戻すと、据え置き（`--hold-sources`）が黙って破れます"
              "——`convert_all --skip`は`.cache`を触らず、`pdfcompat`は据え置き文書の"
              "sha照合を省くので、凍結toolは**新原本を読みながら旧原本で据え置いていると信じます**。")
        print("直し方: 取り込むなら `uv run pipeline/ingest/convert_all.py --force --only <文書>` で"
              "両方を揃える。撤退するなら`.cache`のbundleも控えから戻す（tracked fileだけでは足りない）。")
        return 1
    if moved or missing:
        print("\n**原本が動いています。**この状態で再生成すると、出力が"
              "どの入力状態にも対応しなくなります。")
        print("資料の更新として取り込むなら、**コード変更とは別のcommitで**"
              "再生成してください——CSVが動いたときに原因を分けられなくなります。")
        print("手順は docs/handoff.ja.md 「原本（mirror）にPDFが追加・更新されたとき」。")
        return 1
    if behind:
        print("\n未取得のcommitがあります。**pullの順序は「このリポジトリ → 該当mirror」**"
              "——mirrorは目録を読んで原本を落とすので、機械の順序と同じ向きで追う。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
