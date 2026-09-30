#!/usr/bin/env python3
"""RM の電子署名（ESIG）の章 → evidence/esig.csv

**flash 容量と UID を読む番地**（consumer の依頼 R-35。`getFlashChipSize()`・チップ ID）。
工場で system 領域に焼かれる読み出し専用のレジスタで、EVT のヘッダには構造体が無い
（`registers`/`register_map` は構造体から作るので、ここに現れない）。RM は章の冒頭に表を置く:

    表15-1 ESIG相关寄存器列表
    R16_ESIG_FLACAP  0x1FFFF7E0  闪存容量寄存器  0xXXXX
    R32_ESIG_UNIID1  0x1FFFF7E8  UID寄存器1      0xXXXXXXXX

名前の接頭辞 `R16_`/`R32_` が幅。`FLACAP` の単位は field の説明が言う
（`以Kbyte为单位的闪存容量` / `Flash capacity in Kbyte` / `in unit of Kbyte`）ので、見つかれば
`unit=KiB`。UID は 32 bit の語が3つで96 bit（`UNIID1` が下位）。**番地は family で違うことがある**
——CH32M030 だけ `0x1FFFF3A0` 起点（他は `0x1FFFF7E0`）。

zh と en の両方の表を読み、同じ名前が同じ番地・幅なら confirmed、違えば conflict、片方の版に
しか無ければ reference。英語の説明（`Flash capacity register`）は en 版の表から採る。

実行:
    uv run pipeline/extract/rm/extract_esig.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402
import paths  # noqa: E402

COLUMNS = ["family", "register", "address", "width_bits", "unit", "description",
           "#", "confidence", "basis"]

# 表の1行: 名前・番地・（en なら）説明・復位値。説明は復位値の `0xX…` の手前まで。
ROW = re.compile(r"R(?P<width>8|16|32)_ESIG_(?P<name>[A-Z0-9]+)\s+(?P<address>0x[0-9A-Fa-f]{8})"
                 r"(?:\s+(?P<description>[A-Za-z][A-Za-z0-9 ]*?)\s+0x[Xx]+)?")
UNIT = re.compile(r"以\s*K\s*byte\s*为单位|in\s+(?:unit\s+of\s+)?K\s*bytes?", re.IGNORECASE)


def read(bundle: str) -> tuple[dict[str, dict], int | None]:
    """{名前: {width, address, description, page}} と、FLACAP の単位（KB）を言うページ。"""
    found: dict[str, dict] = {}
    unit_page = None
    for pno, text in bundle_pages.texts(bundle):
        flat = re.sub(r"\s+", " ", text)
        for m in ROW.finditer(flat):
            found.setdefault(m.group("name"), {
                "width": m.group("width"), "address": m.group("address").lower(),
                "description": (m.group("description") or "").strip(), "page": pno})
        if unit_page is None and "ESIG" in flat and UNIT.search(flat):
            unit_page = pno
    return found, unit_page


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()

    rows: list[dict] = []
    notes: list[str] = []
    for family in sorted(r["family"] for r in paths.load("families")):
        editions = {lang: (read(bundle.name), document)
                    for lang, (bundle, document) in bundle_pages.rm_bundles(family).items()}
        if not editions:
            notes.append(f"{family}: RM が無い")
            continue
        names = sorted({n for ((found, _), _) in editions.values() for n in found},
                       key=lambda n: min(int(found[n]["address"], 16)
                                         for ((found, _), _) in editions.values() if n in found))
        if not names:
            notes.append(f"{family}: RM に ESIG の表が無い")
        for name in names:
            said = {lang: found[name] for lang, ((found, _), _) in editions.items() if name in found}
            first = said.get("zh") or said["en"]
            basis = "+".join(f"{editions[lang][1]}:{lang}(p.{said[lang]['page']})"
                             for lang in ("zh", "en") if lang in said)
            if len({(s["address"], s["width"]) for s in said.values()}) > 1:
                confidence = "conflict"
                other = said["en"]
                basis += f"+!{editions['en'][1]}:en(={other['address']}/{other['width']})"
            else:
                confidence = "confirmed" if len(said) == 2 else "reference"
            unit = ""
            if name == "FLACAP":
                pages = [f"{editions[lang][1]}:{lang}(p.{unit_page})"
                         for lang, ((_, unit_page), _) in editions.items() if unit_page]
                if pages:
                    unit = "KiB"
                    basis += "+unit(" + "+".join(pages) + ")"
                else:
                    notes.append(f"{family}: FLACAP の単位を言う説明が見つからない")
            rows.append({"family": family, "register": name, "address": first["address"],
                         "width_bits": first["width"], "unit": unit,
                         "description": said.get("en", {}).get("description", ""),
                         "confidence": confidence, "basis": basis})

    paths.write(paths.table("esig", args.out), rows, COLUMNS)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{paths.table('esig', args.out)}: {len(rows)} 行  family {len({r['family'] for r in rows})}"
          f"  {dict(tally)}", file=sys.stderr)
    for note in notes:
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
