#!/usr/bin/env python3
"""Cross-check tables/remap_fields.csv against ch32-rs/ch32-data.

ch32-data is the other machine-readable CH32 register database (MIT/Apache-2.0).
Its data comes from a different place than ours -- SVD files from MounRiver
Studio, post-processed, plus hand-written definitions -- so where the two agree
the fact has two independent sources, and where they disagree one of them is
wrong. That is the same role the compiled EVT decoder plays in
tools/extract_remap_fields.py: a check, never an input.

It is a check and not an upstream because of what it does not cover. Of the
series this repository carries, ch32-data has no register definitions for
CH32V205 / V407 / V467 / X305 / X315 / M030 / M103 -- which is close to the set
this repository covers that nothing else does. Taking it as upstream would leave
those seven in a separate scheme.

Their layout: data/chips/<SKU>.yaml names the peripherals it includes, directly
or through data/family/*.yaml; each names a register `kind` and `version`, which
resolves to data/registers/<kind>_<version>.yaml, whose fieldsets hold the bit
positions. This walks that chain for AFIO and compares the PCFR1/PCFR2 fields.

Usage:
    uv run tools/crosscheck_ch32data.py --ch32-data <clone> [--tables tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import paths  # noqa: E402
import signal_vocabulary  # noqa: E402

SERIES = re.compile(r"^(CH32[A-Z]\d{2}[0-9A-Za-z])")
# The registers we can compare: ours are AFIO remap selectors.
CONTROLLER = "afio"


def load(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def peripheral_versions(root: Path) -> dict[str, dict[str, tuple[str, str]]]:
    """series -> peripheral name -> (register kind, version), from the chip yamls.

    A chip lists peripherals inline and by including family/peripheral files, so
    the includes are followed one level, which is as deep as this data goes.
    """
    out: dict[str, dict[str, tuple[str, str]]] = collections.defaultdict(dict)
    for chip_path in sorted((root / "data" / "chips").glob("*.yaml")):
        chip = load(chip_path) or {}
        m = SERIES.match(str(chip.get("name") or chip_path.stem))
        if not m:
            continue
        series = m.group(1).upper()
        for core in chip.get("cores") or []:
            groups = [core.get("peripherals") or []]
            for include in core.get("include_peripherals") or []:
                target = (chip_path.parent / include).resolve()
                if target.exists():
                    groups.append(load(target) or [])
            for group in groups:
                for peripheral in group or []:
                    registers = (peripheral or {}).get("registers") or {}
                    kind, version = registers.get("kind"), registers.get("version")
                    if kind and version:
                        out[series][peripheral["name"]] = (kind, str(version))
    return out


def fieldsets(root: Path, kind: str, version: str) -> dict[str, dict[str, tuple[int, int]]]:
    """register name -> field name -> (bit offset, bit size)."""
    path = root / "data" / "registers" / f"{kind}_{version}.yaml"
    if not path.exists():
        return {}
    doc = load(path) or {}
    sets: dict[str, dict[str, tuple[int, int]]] = {}
    for key, body in doc.items():
        if not key.startswith("fieldset/"):
            continue
        sets[key.split("/", 1)[1]] = {
            f["name"]: (int(f.get("bit_offset", 0)), int(f.get("bit_size", 1)))
            for f in (body or {}).get("fields") or []
            if f.get("name")
        }
    return sets


def ours(tables: Path) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """(series, canonical field) -> our bits, as (register, bit)."""
    out = {}
    with (tables / "remap_fields.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["controller"] != CONTROLLER:
                continue
            bits = [b.split(":") for b in r["bits"].split(";") if b]
            out[(r["series"], signal_vocabulary.canonical_field(r["field"]))] = [
                (register, int(bit)) for register, bit in bits
            ]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ch32-data", type=Path, required=True, dest="root",
                    help="ch32-rs/ch32-data の clone")
    ap.add_argument("--tables", type=Path, default=None, help="remap_fields.csv のあるディレクトリ（既定 evidence/）")
    ap.add_argument("--verbose", action="store_true",
                    help="うちが持たない field を1件ずつ出す")
    args = ap.parse_args()

    mine = ours(args.tables or paths.EVIDENCE)
    versions = peripheral_versions(args.root)
    our_series = sorted({series for series, _ in mine})

    agree, differ, missing_there, missing_here = 0, [], [], []
    covered = []
    for series in our_series:
        found = versions.get(series, {})
        afio = found.get("AFIO")
        if afio is None:
            missing_there.append(series)
            continue
        covered.append(f"{series}={afio[0]}_{afio[1]}")
        theirs = fieldsets(args.root, *afio)
        flat: dict[str, list[tuple[str, int]]] = {}
        for register, fields in theirs.items():
            if not register.startswith("PCFR"):
                continue
            for name, (offset, size) in fields.items():
                key = signal_vocabulary.canonical_field(name)
                flat.setdefault(key, []).extend(
                    (register, offset + i) for i in range(size)
                )
        for key, bits in sorted(flat.items()):
            ourbits = mine.get((series, key))
            if ourbits is None:
                missing_here.append((series, key, bits))
                continue
            if sorted(ourbits) == sorted(bits):
                agree += 1
            else:
                differ.append((series, key, bits, ourbits))
        for (series_key, key), ourbits in sorted(mine.items()):
            if series_key == series and key not in flat:
                missing_there.append(f"{series} {key}")

    def show(bits):
        return ",".join(f"{r}:{b}" for r, b in sorted(bits))

    print(f"照合できた series {len(covered)}: {' '.join(covered)}", file=sys.stderr)
    print(f"\n一致 {agree} / 不一致 {len(differ)}", file=sys.stderr)
    for series, key, theirs_bits, our_bits in differ:
        print(f"  {series:9} {key:16} ch32-data={show(theirs_bits):26} "
              f"うち={show(our_bits)}", file=sys.stderr)

    # ch32-data describes every AFIO field; we keep only the ones a pin route
    # refers to, so most of this list is fields that are not pin remaps at all
    # (SW_CFG, the ADC triggers, the HSLV I/O settings). It is a coverage
    # difference by design, not a disagreement.
    only_theirs = collections.Counter(key for _, key, _ in missing_here)
    print(f"\nうちが持たない field {len(missing_here)} 件 / {len(only_theirs)} 種"
          f"（pin経路が参照しないfieldは載せない方針のため）", file=sys.stderr)
    if args.verbose:
        for series, key, bits in missing_here:
            print(f"  {series:9} {key:16} ch32-data={show(bits)}", file=sys.stderr)
    else:
        print("  " + " ".join(f"{k}×{n}" for k, n in only_theirs.most_common(12))
              + (" ..." if len(only_theirs) > 12 else ""), file=sys.stderr)

    absent = sorted(s for s in missing_there if " " not in s)
    if absent:
        print(f"\nch32-dataがAFIOのレジスタ定義を持たない series ({len(absent)}): "
              f"{' '.join(absent)}", file=sys.stderr)
    theirs_absent = [s for s in missing_there if " " in s]
    if theirs_absent:
        print(f"\nうちにあって ch32-data に無い field {len(theirs_absent)} 件:",
              file=sys.stderr)
        print("  " + " ".join(sorted(set(theirs_absent))), file=sys.stderr)
    return 1 if differ else 0


if __name__ == "__main__":
    raise SystemExit(main())
