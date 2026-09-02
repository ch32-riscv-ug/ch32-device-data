#!/usr/bin/env python3
"""zh/enの表対応のreview候補を出す（読むだけ。判断は書かない）。

対応付けの土台は**caption番号の一致**（D17実測: V003 30/30・H417 DS 104/104が
1:1）。2026-09-02の全コーパス実測では、**32文書ペア中16ペアに番号の非対称が
あるが、残差は合計83番号だけ**（大半は±1ずれ——L103 DSの2-2/2-3、X315 RMの
23-4/23-5等）。番号が一致する表は自動で対、**残差だけが人のreview対象**になる。

このtoolは残差を「zh側の番号・ページ・caption原文」と「en側の未対応候補
（同じ章のもの）」を並べて出す。人が読んで対を決めたら、両blockに同じ
canonical番号を記録する:

    uv run pipeline/review/record_decision.py CH32X315RM.zh <zh表のid> approved --canonical 23-4
    uv run pipeline/review/record_decision.py CH32X315RM.en <en表のid> approved --canonical 23-4

実行:
    uv run pipeline/review/propose_pairs.py CH32X315RM   # 1文書ペア
    uv run pipeline/review/propose_pairs.py --all        # 非対称のあるペア全部
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUNDLES = REPO / ".cache" / "structured-bundles"


def load_pages(name: str) -> list[dict]:
    bundle = BUNDLES / name
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    pages = []
    for entry in manifest["pages"]:
        payload = (bundle / entry["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
        pages.append(json.loads(payload))
    return pages


def captioned_tables(name: str) -> dict[str, list[dict]]:
    """caption番号 → [{id, page, text}]（同番号が複数のこともある）。"""
    out: dict[str, list[dict]] = defaultdict(list)
    for page in load_pages(name):
        for table in page["tables"]:
            caption = table.get("caption")
            if caption and caption.get("source_number"):
                out[caption["source_number"]].append(
                    {"id": table["id"], "page": page["number"],
                     "text": caption["text"]})
    return out


def chapter(number: str) -> str:
    return number.split("-", 1)[0]


def report(stem: str) -> int:
    """非対称の数を返す（0なら全表が番号で自動対応）。"""
    zh = captioned_tables(f"{stem}.zh")
    en = captioned_tables(f"{stem}.en")
    only_zh = {n: v for n, v in zh.items()
               if len(v) != len(en.get(n, []))}
    only_en = {n: v for n, v in en.items()
               if len(v) != len(zh.get(n, []))}
    matched = sum(min(len(v), len(en.get(n, []))) for n, v in zh.items())
    if not only_zh and not only_en:
        print(f"{stem}: 表{matched}対が番号で1:1——review不要")
        return 0
    print(f"##### {stem}: 番号一致 {matched} 対、残差 zh {len(only_zh)} / en {len(only_en)} 番号")
    for number in sorted(only_zh):
        for t in only_zh[number]:
            print(f"  zh {number} (p.{t['page']}, {t['id']}): {t['text'][:60]}")
        candidates = [n for n in sorted(only_en)
                      if chapter(n) == chapter(number)]
        for n in candidates:
            for t in only_en[n]:
                print(f"     en候補 {n} (p.{t['page']}, {t['id']}): {t['text'][:60]}")
        if not candidates:
            print("     en候補なし（zh単独の表）")
    orphan_en = [n for n in sorted(only_en)
                 if not any(chapter(n) == chapter(z) for z in only_zh)]
    for number in orphan_en:
        for t in only_en[number]:
            print(f"  en {number} (p.{t['page']}, {t['id']}): {t['text'][:60]}"
                  "  ——zh候補なし（en単独の表）")
    return len(only_zh) + len(only_en)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stem", nargs="?", help="文書名（CH32X315RM の形・言語なし）")
    ap.add_argument("--all", action="store_true", help="両版のあるペア全部")
    args = ap.parse_args()

    if args.all:
        stems = sorted({b.name.rsplit(".", 1)[0] for b in BUNDLES.iterdir()})
        residue = 0
        for stem in stems:
            if (BUNDLES / f"{stem}.zh").exists() and (BUNDLES / f"{stem}.en").exists():
                residue += report(stem)
        print(f"\nreviewの残差: {residue} 番号", file=sys.stderr)
        return 0
    if not args.stem:
        ap.error("文書名か --all を指定する")
    report(args.stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
