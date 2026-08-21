#!/usr/bin/env python3
"""Which EVT compile-time variant macro each part number needs.

Three families ship one header for several silicon variants and pick between
them with a macro the user is expected to set:

    #if !defined(CH32V20x_D8W) && !defined(CH32V20x_D8) && !defined(CH32V20x_D6)
    #define CH32V20x_D6    /* CH32V203F6-CH32V203F8-...-CH32V203C8-CH32V203G8*/
    //#define CH32V20x_D8   /* CH32V203RBT */
    //#define CH32V20x_D8W  /* CH32V208 */
    #endif

The macro is not cosmetic. It moves the peripheral set, changes HSE_VALUE, and
decides branches the clock tables record verbatim -- clock_configs says
CH32V20x's SetSysClockTo144 multiplies by 9 under CH32V20x_D8W and by 18
otherwise, and clock_sources says the RTC's 0x300 means HSE/512 under D8 or D8W
and HSE/128 otherwise. Without this table those `condition` cells name a macro
nothing says how to set, so the branch cannot be resolved for a part.

The mapping is stated once, as the comment beside each `#define`, listing part
number prefixes (a trailing "x" is a wildcard: CH32V307x). One source and a
comment at that, so every row is `reference`; what can be checked is coverage,
and every part of an affected family landing on exactly one macro is reported.

Note that the header ships with one of them already enabled -- CH32V20x_D6,
CH32V30x_D8C, CH32V006 -- so a project that never sets the macro silently builds
for that variant. `default` says which.

Usage:
    uv run tools/build_evt_variants.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import extract_clock_tree  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "macro", "part_number", "default",
           "#", "confidence", "basis"]
BASIS = "evt(device-header-comment)"
# One source, and prose at that. The reference manual does not use these names.
CONFIDENCE = "reference"

# The guard that opens the block, so only the variant defines are read and not
# every commented-out define in the header.
GUARD = re.compile(r"^#\s*if\s+!\s*defined\s*\(")
DEFINE = re.compile(r"^(?P<off>//\s*)?#\s*define\s+(?P<macro>CH32\w+)\s*"
                    r"(?:/\*(?P<comment>.*?)\*/)?\s*$")
ENDIF = re.compile(r"^#\s*endif\b")
PREFIX = re.compile(r"^CH32[A-Z0-9]+$")


def variants(header: Path) -> list[tuple[str, list[str], bool]]:
    """(macro, part-number prefixes, is the header's default) for one header."""
    found: list[tuple[str, list[str], bool]] = []
    inside = False
    for line in header.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not inside:
            inside = bool(GUARD.match(line))
            continue
        if ENDIF.match(line):
            break
        m = DEFINE.match(line)
        if not m:
            continue
        # "CH32V307x-CH32V305x-CH32V317x" and "CH32V007 - CH32M007" both list
        # several prefixes; the separator is a dash, a comma or just space.
        tokens = re.split(r"[-,\s]+", (m.group("comment") or "").upper())
        prefixes = [t.rstrip("X") if t.rstrip("X").startswith("CH32") else t
                    for t in tokens if PREFIX.match(t)]
        found.append((m.group("macro"), prefixes, not m.group("off")))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    with (args.out / "products.csv").open(newline="", encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    parts_of: dict[str, list[str]] = collections.defaultdict(list)
    for p in products:
        parts_of[p["family"]].append(p["part_number"])

    rows: list[dict] = []
    notes: list[str] = []
    for family in sorted(parts_of):
        header = extract_clock_tree.find_device_header(args.mirrors / family)
        if header is None:
            continue
        found = variants(header)
        if not found:
            continue
        for part in sorted(parts_of[family]):
            hits = [(macro, is_default) for macro, prefixes, is_default in found
                    if any(part.startswith(prefix) for prefix in prefixes)]
            if not hits:
                notes.append(f"{family} {part}: どの macro のコメントにも載っていない")
                continue
            if len(hits) > 1:
                notes.append(f"{family} {part}: {len(hits)} 個の macro に該当 "
                             f"({', '.join(m for m, _ in hits)})")
            for macro, is_default in hits:
                rows.append({"family": family, "macro": macro,
                             "part_number": part,
                             "default": "yes" if is_default else "",
                             "confidence": CONFIDENCE, "basis": BASIS})
        listed = {macro for macro, _ in
                  ((m, d) for m, _, d in found)} - {r["macro"] for r in rows
                                                    if r["family"] == family}
        for macro in sorted(listed):
            notes.append(f"{family} {macro}: 該当する部品が products.csv に無い")

    rows.sort(key=lambda r: (r["family"], r["macro"], r["part_number"]))
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / "evt_variants.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    print(f"{dest}: {len(rows)} 行", file=sys.stderr)
    per_family = collections.Counter(r["family"] for r in rows)
    for family, n in sorted(per_family.items()):
        macros = sorted({r["macro"] + ("(既定)" if r["default"] else "")
                         for r in rows if r["family"] == family})
        print(f"  {family}: {n} 部品 / {' '.join(macros)}", file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
