#!/usr/bin/env python3
"""人向けMarkdownとbundleの差ゼロ検査（D18のゴールの機械的定義）。

「PDFと差がない」を2段に分けて検査する。bundle自体はPDFとhashで結ばれている
（変換検証）ので、ここは**bundle→Markdownで何も落ちていない・順序が変わって
いない**ことを見る:

1. 本文の行（header/footer以外）と表の全セルの文字が、bundleの読み順どおりに
   Markdownへ現れること（html escapeを考慮して探す）
2. header/footerの行もコメントとして残っていること（表示から消えるが監査に残る）
3. 図のcaption行の直後に「再現していない」の印があること（既知の取りこぼしを
   隠さない、の検査）

実行:
    uv run pipeline/checks/check_markdown_parity.py --all
    uv run pipeline/checks/check_markdown_parity.py <bundle-dir> <markdown-dir>
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
import logical_tables  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
MARKDOWN = REPO / ".cache" / "structured-markdown"
FIGURE_CAPTION = re.compile(r"^(?:Figure|图)\s*\d+(?:-\d+)*", re.IGNORECASE)
NOT_REPRODUCED = "The figure itself is not reproduced"
CONTINUED = "**Table continued** — rendered in full at"


def load_page(bundle: Path, entry: dict) -> dict:
    payload = (bundle / entry["file"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
    return json.loads(payload)


def check_page(page: dict, text: str, chains: dict[str, dict]) -> list[str]:
    bad = []
    position = 0
    tables = {item["id"]: item for item in page["tables"]}
    lines = {item["id"]: item for item in page["lines"]}

    def expect(needle: str, what: str) -> None:
        nonlocal position
        if not needle:
            return
        at = text.find(needle, position)
        if at < 0:
            where = "missing" if text.find(needle) < 0 else "out of order"
            bad.append(f"p{page['number']} {what}: {where}: {needle[:60]!r}")
        else:
            position = at + len(needle)

    for item in page["reading_order"]:
        if item["type"] == "table":
            info = chains[item["id"]]
            if not info["start"]:
                # 続き断片は開始ページで結合済み。ここには可視のポインタが要る。
                expect(CONTINUED, f"table {item['id']} continuation pointer")
                continue
            record = info["merged"] or tables[item["id"]]
            for cell in record["cells"]:
                expect(html.escape(cell["text"]), f"table {item['id']} cell")
        elif item["type"] == "line":
            line = lines[item["id"]]
            expect(html.escape(line["text"]), f"{line.get('role')} {item['id']}")
            if (line.get("role") not in ("header", "footer")
                    and FIGURE_CAPTION.match(line["text"].strip())
                    and NOT_REPRODUCED not in text[position:position + 300]):
                bad.append(f"p{page['number']} {item['id']}: figure caption without "
                           "a not-reproduced notice")
    return bad


def check_document(bundle: Path, markdown: Path, limit: int = 5) -> int:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    pages = [load_page(bundle, entry) for entry in manifest["pages"]]
    chains = logical_tables.document_chains(pages)
    bad: list[str] = []
    for page in pages:
        md = markdown / "pages" / f"{page['number']:04d}.md"
        if not md.exists():
            bad.append(f"p{page['number']}: markdown page missing")
            continue
        bad.extend(check_page(page, md.read_text(encoding="utf-8"), chains))
    if bad:
        print(f"[{bundle.name}] {len(bad)} parity issue(s):", file=sys.stderr)
        for line in bad[:limit]:
            print(f"    {line}", file=sys.stderr)
        if len(bad) > limit:
            print(f"    ... {len(bad) - limit} more", file=sys.stderr)
    return len(bad)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundle", type=Path, nargs="?")
    ap.add_argument("markdown", type=Path, nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
        import convert_all  # noqa: PLC0415
        total = bad_docs = issues = 0
        for job in convert_all.targets():
            total += 1
            n = check_document(BUNDLES / job["name"], MARKDOWN / job["name"])
            if n:
                bad_docs += 1
                issues += n
        print(f"{total} documents checked: "
              f"{total - bad_docs} clean, {bad_docs} with {issues} issue(s)")
        return 1 if issues else 0
    if not (args.bundle and args.markdown):
        ap.error("give bundle and markdown paths, or --all")
    return 1 if check_document(args.bundle, args.markdown, limit=20) else 0


if __name__ == "__main__":
    raise SystemExit(main())
