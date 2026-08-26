#!/usr/bin/env python3
"""Debug module の data0/data1 レジスタの hart 側アドレス → evidence/debug_data.csv

SDI print（DMDATA0/1 の mailbox 経由の printf）は、hart から見た debug module の
data0/data1 に書く。**その番地は die で違う**（consumer の R-27。V003 は 0xE00000F4、
V4 系は 0xE0000380、V3 系の多くは 0xE0000340）。既定値を1つ持つと別 family で黙って
外れるので、family ごとに表にする。

出所は3つで、揃ったものを confirmed にする:

    evt        各 EVT の debug.c の `#define DEBUG_DATA0_ADDRESS ((volatile uint32_t*)0xE0000380)`
               （SDI_Printf の実装。family 内の全 debug.c で同じ値であることを見る）
    manual     QingKe プロセッサマニュアル（V2/V3/V4/V5）debug 章の hartinfo 表の `dataaddr`。
               V2 と V4 は固定値（0x0f4 / 0x380）、V3 と V5 は `0xXXX`（「以具体读出为准」——
               実装ごとに hartinfo を読め、と書く）。core 世代は catalog/families.csv の core 名から
    hartinfo   consumer が WCH-LinkE で hartinfo.dataaddr を読んだ実測（curated/debug-data-measured.json）

CH32H417 の EVT には define が無く（SDI_Printf 例が無い）、V5/V3 のマニュアルは値を固定しない
ので、行は残して番地は空・confidence は missing。

実行:
    uv run tools/build_debug_data.py [--mirrors <dir>] [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

COLUMNS = ["family", "core", "dm_data0_addr", "dm_data1_addr", "#", "confidence", "basis", "evt_file"]
DEFINE = re.compile(r"#define\s+DEBUG_DATA(?P<n>[01])_ADDRESS\s+\(\(volatile\s+uint32_t\s*\*\)\s*(?P<addr>0x[0-9A-Fa-f]{8})\)")
GENERATION = re.compile(r"QingKe V(?P<gen>\d)")
DATAADDR = re.compile(r"\[11:0\]\s+dataaddr\s+RO\s+(?P<value>0x[0-9A-Fa-fX]{3})")
DM_BASE = 0xE0000000


def hexaddr(value: int) -> str:
    """番地の綴りを1つに（`0xE00000F4`）。出所ごとの大文字小文字の差で食い違いに見せない。"""
    return f"0x{value:08X}"


def evt_defines(family_dir: Path) -> tuple[dict[str, str], list[str], list[str]]:
    """(番地 {0: addr, 1: addr}, 定義している debug.c の相対パス, 食い違いの注)."""
    found: dict[str, set[str]] = collections.defaultdict(set)
    files: list[str] = []
    for path in sorted((family_dir / "EVT").rglob("debug.c")):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = DEFINE.findall(text)
        if not hits:
            continue
        files.append(path.relative_to(family_dir).as_posix())
        for n, addr in hits:
            found[n].add(hexaddr(int(addr, 16)))
    notes = [f"DEBUG_DATA{n}_ADDRESS が debug.c で揺れる: {sorted(v)}" for n, v in found.items() if len(v) > 1]
    return {n: next(iter(v)) for n, v in found.items() if len(v) == 1}, files, notes


def manual_dataaddr(mirrors: Path) -> dict[int, str]:
    """世代 → hartinfo.dataaddr（`0x380` か、固定しない印の `0xXXX`）。zh 版（原典）から。"""
    import pdfplumber  # noqa: PLC0415  （CI の検査は PDF を読まない）

    out: dict[int, str] = {}
    for gen in (2, 3, 4, 5):
        pdf_path = mirrors / "WCH-common" / "datasheet_zh" / f"QingKeV{gen}_Processor_Manual.PDF"
        if not pdf_path.exists():
            continue
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:60]:
                m = DATAADDR.search(page.extract_text() or "")
                page.close()
                if m:
                    out[gen] = m.group("value")
                    break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=paths.MIRRORS)
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()

    families = paths.load("families")
    measured = json.loads((paths.CURATED / "debug-data-measured.json").read_text(encoding="utf-8"))["measured"]
    fixed = manual_dataaddr(args.mirrors)
    print(f"manual hartinfo.dataaddr: {fixed}", file=sys.stderr)

    rows: list[dict] = []
    notes: list[str] = []
    for fam in families:
        family = fam["family"]
        cores = [c.strip() for c in fam["cores"].replace(";", " + ").split(" + ") if c.strip()]
        gens = sorted({int(m.group("gen")) for c in cores for m in [GENERATION.search(c)] if m})
        defines, files, bad = evt_defines(args.mirrors / family)
        notes += [f"{family}: {n}" for n in bad]

        basis: list[str] = []
        candidates: dict[str, set[str]] = collections.defaultdict(set)  # source → {data0}
        if defines.get("0") and defines.get("1"):
            basis.append(f"evt({files[0]})" + (f"+{len(files) - 1} more" if len(files) > 1 else ""))
            candidates["evt"].add(defines["0"])
        for gen in gens:
            value = fixed.get(gen)
            if value is None:
                continue
            if "X" in value[2:].upper():  # `0xXXX`: 固定しない
                basis.append(f"manual:qingke-v{gen}(dataaddr=read hartinfo)")
            else:
                addr = hexaddr(DM_BASE + int(value, 16))
                basis.append(f"manual:qingke-v{gen}(dataaddr={value})")
                candidates["manual"].add(addr)
        if family in measured:
            basis.append("hartinfo:wch-linke(consumer 2026-08-26)")
            candidates["hartinfo"].add(hexaddr(int(measured[family]["dm_data0_addr"], 16)))

        values = {v for vs in candidates.values() for v in vs}
        if not values:
            confidence, data0, data1 = "missing", "", ""
        elif len(values) > 1:
            # 出所どうしが食い違う。EVT の値を採り（実装が書いている番地）、違う出所は
            # `!source(=値)` で並べる
            confidence = "conflict"
            data0 = defines.get("0") or sorted(values)[0]
            data1 = defines.get("1", "")
            for source in ("manual", "hartinfo"):
                other = candidates.get(source, set()) - {data0}
                if other:
                    basis = [f"!{b}(={next(iter(other))})" if b.startswith(source) and "read hartinfo" not in b else b
                             for b in basis]
        else:
            data0 = next(iter(values))
            data1 = defines.get("1") or hexaddr(int(data0, 16) + 4)
            confidence = "confirmed" if len(candidates) >= 2 else "reference"
        rows.append({"family": family, "core": " + ".join(cores), "dm_data0_addr": data0,
                     "dm_data1_addr": data1, "confidence": confidence, "basis": "+".join(basis),
                     "evt_file": files[0] if files else ""})

    rows.sort(key=lambda r: r["family"])
    dest = paths.table("debug_data", args.out)
    paths.write(dest, rows, COLUMNS)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{dest}: {len(rows)} 行  {dict(tally)}", file=sys.stderr)
    for note in notes:
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
