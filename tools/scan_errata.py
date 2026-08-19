#!/usr/bin/env python3
"""データシート横断のエラッタ収集スキャナ（用途別・単体実行）。

ミラーのデータシート（既定は DS0、--rm でリファレンスマニュアルも）から
ロット依存・シリコン版依存・訂正系の記述を機械的に抽出し、
curated/errata.csv の match 列（正規表現）と照合して KNOWN / NEW を表示する。

エラッタは後から増える可能性があるため、データシート更新後などに
単体で実行して NEW が出ないか確認する運用:

    uv run python tools/scan_errata.py            # DS0 のみ（数分）
    uv run python tools/scan_errata.py --rm       # RM も走査（十数分かかる）

NEW が出たら curated/errata.csv に行を追加し（match 列にその記述を
識別する正規表現を書く）、再実行して NEW: 0 になることを確認する。
match は「リポジトリ相対パス + 空白 + 前後文脈」に対して検索される。

終了コード: NEW 候補があれば 1、なければ 0。
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import pdfplumber

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent

# エラッタらしさのシグナル。広すぎる語（注/Note 単独など）はノイズに
# なるため、ロット・版数・訂正の文脈を示す語だけに絞る。
PATTERNS = {
    "zh": re.compile(r"批号|批次|勘误|倒数第|流片|芯片版本"),
    "en": re.compile(
        r"lot\s*number|batch\s*(?:number|code)|errat|penultimate"
        r"|silicon\s*(?:revision|version)|chip\s*version",
        re.IGNORECASE,
    ),
}
WINDOW = 160  # マッチ位置の前後をこの文字数だけ文脈として拾う


def load_known():
    """curated/errata.csv の match 列 → [(id, compiled_regex)]"""
    known = []
    with (REPO / "curated/errata.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("match"):
                known.append((row["id"], re.compile(row["match"])))
    return known


def scan_pdf(path, lang):
    """ページ全文に対して finditer し、行またぎのマッチも文脈窓で拾う。"""
    hits = []
    pat = PATTERNS[lang]
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            last_end = -1
            for m in pat.finditer(text):
                if m.start() < last_end:  # 直前の窓に含まれる分は割愛
                    continue
                lo = max(0, m.start() - WINDOW)
                hi = min(len(text), m.end() + WINDOW)
                last_end = hi
                snip = " / ".join(
                    s.strip() for s in text[lo:hi].splitlines() if s.strip())
                hits.append((page.page_number, snip))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rm", action="store_true",
                    help="リファレンスマニュアル(RM)も走査する")
    ap.add_argument("--only", help="ファイル名の部分一致でPDFを絞る")
    args = ap.parse_args()

    known = load_known()
    targets = []
    for repo in sorted(MIRRORS.glob("CH32*")):
        for lang in ("zh", "en"):
            for pdf in sorted((repo / f"datasheet_{lang}").glob("*.PDF")):
                if "RM" in pdf.name and not args.rm:
                    continue
                if args.only and args.only not in pdf.name:
                    continue
                targets.append((pdf, lang))

    new_count = 0
    found_ids = set()
    for pdf, lang in targets:
        rel = pdf.relative_to(MIRRORS)
        try:
            hits = scan_pdf(pdf, lang)
        except Exception as exc:  # 壊れたPDFはスキップして報告
            print(f"{rel}: 読み取り失敗 {exc}", file=sys.stderr)
            continue
        for page_no, snip in hits:
            target = f"{rel} {snip}"
            labels = [kid for kid, kre in known if kre.search(target)]
            if labels:
                found_ids.update(labels)
                print(f"{rel} p.{page_no} [KNOWN:{';'.join(labels)}]")
            else:
                new_count += 1
                print(f"{rel} p.{page_no} [NEW]")
                print(f"    {snip[:320]}")

    known_ids = {kid for kid, _ in known}
    missing = known_ids - found_ids
    print()
    print(f"既知 {len(known_ids)} 件中 {len(known_ids) - len(missing)} 件を"
          f"データシート上で確認")
    if missing:
        print(f"未確認(要手動確認): {sorted(missing)}")
    print(f"NEW 候補: {new_count} 件")
    return 1 if new_count else 0


if __name__ == "__main__":
    sys.exit(main())
