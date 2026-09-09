#!/usr/bin/env python3
"""Extract package dimensions from the table of contents of PACKAGE.PDF.

WCH's package-drawing document states each package's dimensions in its own TOC
entry -- "QFN48X7（QFN48-7*7-0.5）" names the body 7x7mm and the 0.5mm pitch, and
"LQFP64M（LQFP64-10*10）" the body alone. The drawing pages themselves are images
with no text layer, so the TOC is the machine-readable statement.

読み手は `pipeline/extract/bundle_pages.py`（sha 照合つき。凍結
`tools/extract_package_dims.py` の移植＝退役 第11号）。使うのは TOC 6ページの本文だけ。

`extract()` は **bundle 名でも原本PDFのパスでも受ける**——凍結 `tools/build_tables.py`
（退役は別企画）が `MIRRORS/WCH-common/datasheet_<lang>/PACKAGE.PDF` を渡してくるので、
親ディレクトリから言語を読んで bundle 名（`PACKAGE.zh` / `PACKAGE.en`）に直す。原本は開かない。

Usage:
    uv run pipeline/extract/package/extract_package_dims.py <bundle名 or PACKAGE.PDF> [--emit]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402

# bundle 名の言語は原本の置き場から決まる（`pdfcompat` と同じ規則）。
_LANG_DIR = re.compile(r"^datasheet_(zh|en)$")


def bundle_name(argument: str) -> str:
    """`PACKAGE.zh` はそのまま。原本PDFのパスなら親ディレクトリから言語を読む。"""
    path = Path(argument)
    if path.suffix.upper() != ".PDF":
        return argument
    found = _LANG_DIR.match(path.parent.name)
    if not found:
        raise SystemExit(f"{argument}: 言語が分からない"
                         "——`datasheet_zh`/`datasheet_en` の下のPDFか、bundle名を渡してください")
    return f"{path.stem}.{found.group(1)}"


TOC_PAGES = 6
# "QFN48X7（QFN48-7*7-0.5） .... ９１" -> name, then a spec in parentheses.
# The spec's dash-separated tail is body [ *height ] [ -pitch ]:
#   QFN48-7*7-0.5      body 7*7, pitch 0.5
#   QFN12-2*2*0.5-0.4  body 2*2, height 0.5, pitch 0.4
#   LQFP64-10*10       body 10*10, no pitch stated
# The English edition puts a space between the name and its parenthesis.
ENTRY = re.compile(r"^\.?\s*([A-Za-z][A-Za-z0-9]+(?:\s*[、，,（(].*)?)\s*\.{2,}")
NAME = re.compile(r"^([A-Za-z][A-Za-z0-9]+)")
SPEC = re.compile(
    r"[（(][^（()）]*?-\s*"
    r"(\d+(?:\.\d+)?\*\d+(?:\.\d+)?)"        # body W*H
    r"(?:\*\d+(?:\.\d+)?)?"                   # optional height, not kept
    r"(?:-(\d+(?:\.\d+)?))?"                  # optional pitch
    r"[)）]"
)


def normalise(line: str) -> str:
    """Full-width digits and punctuation appear in the Chinese TOC."""
    wide = "０１２３４５６７８９＊．－"
    return line.translate(str.maketrans(wide, "0123456789*.-")).replace("　", " ")


def extract(source) -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    for pno, (_number, text) in enumerate(
            bundle_pages.texts(bundle_name(str(source)), TOC_PAGES), start=1):
        for raw in text.splitlines():
            line = normalise(raw.strip())
            if not ENTRY.match(line):
                continue
            m = NAME.match(line.lstrip(". "))
            if not m:
                continue
            name = m.group(1)
            if name in seen:
                continue
            spec = SPEC.search(line)
            entry = {
                "package": name,
                "body_size": spec.group(1) if spec else None,
                "pin_pitch": spec.group(2) if spec else None,
                "toc_page": pno,
            }
            seen.add(name)
            entries.append(entry)
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()
    entries = extract(args.pdf)
    print(f"入力: {args.pdf}", file=sys.stderr)
    print(f"package: {len(entries)} 件", file=sys.stderr)
    for e in entries:
        print(f"    {e['package']:16} body={e['body_size'] or '-':10} pitch={e['pin_pitch'] or '-'}",
              file=sys.stderr)
    if args.emit:
        json.dump(entries, sys.stdout, indent=2, ensure_ascii=False)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
