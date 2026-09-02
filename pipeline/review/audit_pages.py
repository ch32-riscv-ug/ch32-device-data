#!/usr/bin/env python3
"""人向けMarkdownの「まだ変な所」を機械的に洗い出す（100%化のQA用の的出し）。

PDFとの差ゼロは`check_markdown_parity.py`が「取りこぼし・順序」を守るが、それを
通っても**読みにくい残り**はある（bit図の検出漏れ・表セルに残った添字の断片・
復号できないglyph・折り返しの塊）。ここはそれらをページ単位で数えて、疑わしい順に
並べる——安価なサブエージェントやユーザーが、viewerリンクから上位を順に確かめて
直していくための入口。判定はしない（印を出すだけ）。

信号（重み）:
  bitnum_leftover  bit番号行が本文に残っている（bit図の再構成が発火しなかった）
  subscript_orphan `DD`/`VSS`等、添字だけの行が独立して残っている
  cid              復号できなかったglyph `(cid:N)`
  pua              私用領域の記号がそのまま出ている（本来は0）
  long_line        200字を超える1行（折り返し/連結の作りそこね）
  split_bitcell    bit図セルに縦割れの断片が残っている（`Reser`等の途中切れ）
  table_issue      変換器が記録した表の重なり等

実行:
    uv run pipeline/review/audit_pages.py                 # 上位を表示
    uv run pipeline/review/audit_pages.py --json out.json # 全疑いページを機械可読で
    uv run pipeline/review/audit_pages.py --top 40 --doc CH32xRM.en
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import logical_tables  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
MARKDOWN = REPO / ".cache" / "structured-markdown"
VIEWER = "https://ch32-riscv-ug.github.io/ch32-device-data-preview/viewer.html"

WEIGHTS = {"bitnum_leftover": 5, "split_bitcell": 4, "cid": 3, "pua": 3,
           "subscript_orphan": 2, "long_line": 1, "table_issue": 1}
COMMENT = re.compile(r"<!--.*?-->", re.S)
STYLE = re.compile(r"<style>.*?</style>", re.S)
PUA = re.compile(r"[-]")
BITNUM = re.compile(r"(?m)^\s*(?:3[01]|[12]?\d)(?: \d+){7,}\s*(?:  )?$")
ORPHAN = re.compile(r"(?:DD|SS|SSA|DDA|BAT|PVD|REF|OUT|CC|IN)"
                    r"(?:\s+(?:DD|SS|SSA|DDA|BAT|PVD|REF|OUT|CC|IN))*")


def visible(md_text: str) -> str:
    return STYLE.sub("", COMMENT.sub("", md_text))


def page_signals(page: dict, md_text: str) -> dict[str, int]:
    text = visible(md_text)
    sig: dict[str, int] = {}
    n = len(BITNUM.findall(text))
    if n:
        sig["bitnum_leftover"] = n
    if "(cid:" in text:
        sig["cid"] = text.count("(cid:")
    if PUA.search(text):
        sig["pua"] = len(PUA.findall(text))
    orphans = sum(1 for ln in text.splitlines()
                  if ORPHAN.fullmatch(ln.strip().rstrip()))
    if orphans:
        sig["subscript_orphan"] = orphans
    # 長い本文行はbundleのparagraph/list-itemで測る（Markdownの1行には表HTMLが
    # 丸ごと乗るので、そのまま数えると全表が誤検出になる）。
    longs = sum(1 for l in page["lines"]
                if l.get("role") in ("paragraph", "list-item") and len(l["text"]) > 300)
    if longs:
        sig["long_line"] = longs
    issues = sum(len(t.get("issues") or []) for t in page["tables"])
    if issues:
        sig["table_issue"] = issues
    return sig


def score(sig: dict[str, int]) -> int:
    return sum(WEIGHTS.get(k, 1) * v for k, v in sig.items())


def audit(doc: str) -> list[dict]:
    bundle = BUNDLES / doc
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for entry in manifest["pages"]:
        number = entry["number"]
        md = MARKDOWN / doc / "pages" / f"{number:04d}.md"
        if not md.exists():
            continue
        page = json.loads((bundle / entry["file"]).read_bytes())
        sig = page_signals(page, md.read_text(encoding="utf-8"))
        if sig:
            out.append({"doc": doc, "page": number, "score": score(sig),
                        "signals": sig,
                        "viewer": f"{VIEWER}#doc={doc}&p={number}"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--doc", help="1文書に絞る（例 CH32xRM.en）")
    ap.add_argument("--top", type=int, default=30, help="表示件数")
    ap.add_argument("--json", type=Path, help="全疑いページをJSONで書き出す")
    args = ap.parse_args()

    import convert_all  # noqa: PLC0415
    docs = [args.doc] if args.doc else [j["name"] for j in convert_all.targets()]
    rows: list[dict] = []
    for doc in docs:
        if (BUNDLES / doc).exists():
            rows.extend(audit(doc))
    rows.sort(key=lambda r: r["score"], reverse=True)

    totals: dict[str, int] = {}
    for r in rows:
        for k, v in r["signals"].items():
            totals[k] = totals.get(k, 0) + v
    print(f"{len(rows)} suspect page(s) across {len(docs)} document(s)", file=sys.stderr)
    print("signal totals:", dict(sorted(totals.items(), key=lambda kv: -kv[1])),
          file=sys.stderr)
    for r in rows[:args.top]:
        flags = " ".join(f"{k}={v}" for k, v in
                         sorted(r["signals"].items(), key=lambda kv: -WEIGHTS.get(kv[0], 1)))
        print(f"  [{r['score']:3}] {r['doc']} p{r['page']:<4} {flags}\n        {r['viewer']}")
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
        print(f"wrote {args.json} ({len(rows)} pages)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
