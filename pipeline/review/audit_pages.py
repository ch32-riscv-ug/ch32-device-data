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
  long_line        本文に実際に描かれる300字超の1行（折り返し/連結の作りそこね）
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
sys.path.insert(0, str(REPO / "pipeline" / "review"))
import export_markdown  # noqa: E402  cross-pageまで含めた消費集合を得る

BUNDLES = REPO / ".cache" / "structured-bundles"
MARKDOWN = REPO / ".cache" / "structured-markdown"
VIEWER = "https://ch32-riscv-ug.github.io/ch32-device-data-preview/viewer.html"

WEIGHTS = {"bitnum_leftover": 5, "nonstd_bitdiagram": 3, "cid": 3, "pua": 3,
           "subscript_orphan": 2, "long_line": 1, "table_issue": 1}
COMMENT = re.compile(r"<!--.*?-->", re.S)
STYLE = re.compile(r"<style>.*?</style>", re.S)
PUA = re.compile(r"[-]")
BITNUM = re.compile(r"\d+(?: \d+){7,}")   # 8個以上の空白区切り整数（fullmatch用）
ORPHAN = re.compile(r"(?:DD|SS|SSA|DDA|BAT|PVD|REF|OUT|CC|IN)"
                    r"(?:\s+(?:DD|SS|SSA|DDA|BAT|PVD|REF|OUT|CC|IN))*")


def visible(md_text: str) -> str:
    return STYLE.sub("", COMMENT.sub("", md_text))


def page_signals(page: dict, md_text: str, consumed: set[str] | None = None,
                 figure_regions: list[list[float]] | None = None) -> dict[str, int]:
    text = visible(md_text)
    sig: dict[str, int] = {}
    # bit図として組み直せていない番号行（表・synth・cross-pageのどれにも載らなかった
    # 標準の降順列）。consumedはdocument_bitfieldsのskip（cross_note行込み）。
    consumed = consumed or (set(logical_tables.bitfield_pairs(page).values())
                            | set(logical_tables.bitfield_singletons(page).keys()))
    leftover = sum(1 for l in page["lines"]
                   if logical_tables.bit_numbers(l["text"]) and l["id"] not in consumed)
    # 降順でない特殊な並び（`31 24 23 16 …`のbyte境界図）は別枠で拾う（要目視）。
    nonstd = sum(1 for l in page["lines"]
                 if logical_tables.bit_numbers(l["text"]) is None
                 and BITNUM.fullmatch(l["text"].strip()))
    if leftover:
        sig["bitnum_leftover"] = leftover
    if nonstd:
        sig["nonstd_bitdiagram"] = nonstd
    if "(cid:" in text:
        sig["cid"] = text.count("(cid:")
    if PUA.search(text):
        sig["pua"] = len(PUA.findall(text))
    orphans = sum(1 for ln in text.splitlines()
                  if ORPHAN.fullmatch(ln.strip().rstrip()))
    if orphans:
        sig["subscript_orphan"] = orphans
    regions = figure_regions or []

    def in_figure(bb: list[float]) -> bool:
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        return any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in regions)

    # 長い本文行はbundleのparagraph/list-itemで測る（Markdownの1行には表HTMLが
    # 丸ごと乗るので、そのまま数えると全表が誤検出になる）。**図領域の中は数えない**——
    # 250字を超える行は全corpus35行すべてが画像化された図（pin配置図・I3Cプロトコル図・
    # 充放電の波形図）のラベルが文字単位に交錯した塊で、exporterが既に
    # `<details>🖼 Text parsed from the figure above`へ畳んでおり本文は崩れていない
    # （2026-09-04に35行を1件ずつ出力位置まで追って確認）。図の外に出るものだけが手当て
    # の要る信号。
    # さらに**exporterが実際に描く行だけ**を数える（`reading_stream`にある行）。残った2件
    # （H417RM.en p402/p408）は、変換器がreading_orderから外した図テキストの幽霊行で、
    # 出力では同じ内容が綺麗な表として描かれていた——数えるべき崩れではない。
    rendered = {item["id"] for item in logical_tables.reading_stream(page, regions)
                if item["type"] == "line"} - set(consumed)
    longs = sum(1 for l in page["lines"]
                if l.get("role") in ("paragraph", "list-item")
                and len(l["text"]) > 300 and l["id"] in rendered
                and not in_figure(l["bbox"]))
    if longs:
        sig["long_line"] = longs
    # 重なりissueのある表のうち、**図領域に畳まれていない**もの（本文で崩れて見える
    # もの）だけ数える。clock tree等の図をtable抽出したものは大半が図の<details>へ畳まれ
    # 表示は綺麗なので、それは除く。
    broken = sum(1 for t in page["tables"]
                 if t.get("issues") and not in_figure(t["bbox"]))
    if broken:
        sig["table_issue"] = broken
    return sig


def score(sig: dict[str, int]) -> int:
    return sum(WEIGHTS.get(k, 1) * v for k, v in sig.items())


def audit(doc: str) -> list[dict]:
    bundle = BUNDLES / doc
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    pages = [json.loads((bundle / entry["file"]).read_bytes())
             for entry in manifest["pages"]]
    plans = export_markdown.document_bitfields(bundle, manifest, pages)
    assets_path = MARKDOWN / doc / "assets.json"
    assets = (json.loads(assets_path.read_text(encoding="utf-8"))["assets"]
              if assets_path.exists() else {})
    out = []
    for page in pages:
        number = page["number"]
        md = MARKDOWN / doc / "pages" / f"{number:04d}.md"
        if not md.exists():
            continue
        # 消費された番号行 = skip（表ペア・cross_note）＋synthの番号行（描画trigger）。
        consumed = plans[number]["skip"] | set(plans[number]["synth"])
        regions = [a["bbox"] for a in assets.values() if a["page"] == number]
        sig = page_signals(page, md.read_text(encoding="utf-8"), consumed, regions)
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
