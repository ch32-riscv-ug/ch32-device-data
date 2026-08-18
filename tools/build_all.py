#!/usr/bin/env python3
"""Build a candidate for every SKU the datasheets list.

The product comparison table gives the SKU universe; the pin table gives one column
per variant. Joining the two needs a mapping from a SKU to its column, which is
either the part number itself or the package the comparison table assigns it.

Reading a reference manual dominates the runtime, so each family is parsed once and
reused across its SKUs.

Usage:
    uv run tools/build_all.py --out candidates [--family CH32M030] [--limit 5]

Output is unreviewed machine extraction, written outside devices/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pdfplumber  # noqa: E402

import build_candidate  # noqa: E402
import extract_pins  # noqa: E402
import extract_ordering  # noqa: E402
import extract_products  # noqa: E402

MIRRORS = Path("/home/mt/dev_wch")
# Headings the text layer loses, read off the rendered page by hand.
CURATED_COLUMNS = Path(__file__).resolve().parents[1] / "curated" / "pin-table-columns.json"
# Reference manuals are shared across products and not always named for the family.
MANUAL = re.compile(r"RM\.PDF$", re.IGNORECASE)


def family_dirs() -> list[Path]:
    return sorted(p for p in MIRRORS.glob("CH32*") if (p / "datasheet_en").is_dir())


def find_header(family: Path) -> Path | None:
    """The EVT device header, whose name varies in case and spelling."""
    candidates = sorted(family.glob("EVT/**/Peripheral/inc/ch32*.h"))
    plain = [p for p in candidates if re.fullmatch(r"ch32[a-z0-9]+\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else (candidates[0] if candidates else None)


def find_manual(family: Path) -> Path | None:
    manuals = sorted(p for p in (family / "datasheet_en").iterdir() if MANUAL.search(p.name))
    return manuals[0] if manuals else None


def curated_columns() -> dict:
    if not CURATED_COLUMNS.exists():
        return {}
    return json.loads(CURATED_COLUMNS.read_text(encoding="utf-8"))


def pin_tables(datasheet: Path) -> list[tuple[str, list[list[str]], list[str], dict]]:
    """Every pin-definition table in a datasheet, parsed once."""
    overrides = curated_columns().get(datasheet.name, {})
    out = []
    with pdfplumber.open(datasheet) as pdf:
        caps = extract_pins.captions(pdf)
        seen: set[str] = set()
        for i, (label, title, _) in enumerate(caps):
            if "pin definition" not in title.lower() or label in seen:
                continue
            seen.add(label)
            stop = extract_pins.next_caption(caps, i)
            rows, variants, layout = extract_pins.find_pin_tables(pdf, label, stop)
            fixed = overrides.get(label, {}).get("columns")
            if fixed:
                # The curated list is authoritative; the parser only found where the
                # columns are, not always what they are called.
                variants = fixed + variants[len(fixed):]
            if variants:
                out.append((label, rows, variants, layout))
    return out


# The second-to-last character of a part number names the package type. Checked
# against all eight hand-made records, which agree without exception.
PACKAGE_LETTER = {"M": "SOP", "P": "TSSOP", "U": "QFN", "T": "LQFP", "R": "QSOP"}


def pin_count_of(attributes: dict) -> int | None:
    for label, value in attributes.items():
        if "pin" in label.lower() and str(value).strip().isdigit():
            return int(str(value).strip())
    return None


def choose_column(
    part: str, attributes: dict, variants: list[str], ordering: dict[str, dict] | None = None
) -> tuple[str | None, str]:
    """Which pin-table column belongs to this SKU, and how that was decided."""
    # The ordering table states the package outright and is the best evidence there is.
    named = (ordering or {}).get(part, {}).get("package", "")
    if named:
        want = named.upper()
        for v in variants:
            # A heading may stack the packages that share a numbering, as CH32V203
            # does with "LQFP48/QFN48X7".
            for got in (part.strip() for part in v.upper().split("/")):
                # The two tables also spell one package differently: the ordering
                # table says LQFP64M where the pin table says LQFP64.
                if got and (got == want or want.startswith(got) or got.startswith(want)):
                    return v, "ordering-table"
    for v in variants:
        if v == part or part.endswith(v) or v.endswith(part):
            return v, "part-number"
    # A column may cover several SKUs that differ only in the final digit: CH32V006
    # heads one column V006E8R for both E8R6 and E8R7.
    trimmed = part.rstrip("0123456789")
    for v in variants:
        if v and trimmed.endswith(v):
            return v, "part-number-without-variant-digit"
    # Or it may spell the package and name the SKU inside it, as CH32V303 does with
    # "LQFP48(V303CBT6)".
    bare = part[4:] if part.startswith("CH32") else part
    matches = [v for v in variants if len(bare) >= 5 and bare in v]
    if len(matches) == 1:
        return matches[0], "part-number-inside-column"
    # Only CH32V003 states the package outright; elsewhere it has to be derived.
    values = {str(v).replace(" ", "").upper() for v in attributes.values()}
    for v in variants:
        if v.replace(" ", "").upper() in values:
            return v, "package-attribute"

    if named:
        return None, f"ordering表はpackage={named}だがpin表に同名の列がない"
    pins = pin_count_of(attributes)
    kind = PACKAGE_LETTER.get(part[-2]) if len(part) > 2 and part[-1].isdigit() else None
    sized = [v for v in variants if re.search(rf"\D{pins}(\D|$)", v)] if pins else []
    if len(sized) == 1:
        return sized[0], "pin-count"
    typed = [v for v in sized if kind and v.upper().startswith(kind)]
    if len(typed) == 1:
        return typed[0], "pin-count+package-letter"
    # Several columns fit; which one is a question for a person, so name them.
    rest = typed or sized
    return None, ("候補=" + ",".join(rest)) if rest else "手掛かりなし"


def merge_sku_lists(products: list[dict], ordering: dict[str, dict]) -> list[dict]:
    """The SKU universe is both tables together.

    The ordering table spells the part number in full where the comparison table
    abbreviates it -- CH32V208 appears as CH32V208CB in one and CH32V208CBU6 in the
    other -- and each table lists models the other omits.
    """
    by_pn = {p["part_number"]: p for p in products}
    merged: list[dict] = []
    claimed: set[str] = set()
    for full in sorted(ordering):
        match = by_pn.get(full)
        if match is None:
            # An abbreviated entry is a prefix of the full order model, or a
            # wildcard column: CH32V203C6x6 covers both C6T6 and C6U6.
            prefixes = [
                q for q in by_pn
                if ("x" in q and re.fullmatch(q.replace("x", "[A-Z0-9]"), full))
                or (full.startswith(q) and len(full) - len(q) <= 2)
            ]
            match = by_pn[prefixes[0]] if len(prefixes) == 1 else None
        if match is not None:
            claimed.add(match["part_number"])
        merged.append(
            {
                "part_number": full,
                "attributes": (match or {}).get("attributes", {}),
                "_listed_as": match["part_number"]
                if match and match["part_number"] != full
                else None,
            }
        )
    merged += [p for p in products if p["part_number"] not in claimed]
    return merged


def run_family(family: Path, out_dir: Path, limit: int | None) -> list[dict]:
    report: list[dict] = []
    header, manual = find_header(family), find_manual(family)
    datasheets = sorted(p for p in (family / "datasheet_en").glob("*DS0.PDF"))
    if not datasheets:
        return report

    silicon = None
    if header and manual:
        try:
            silicon = build_candidate.read_silicon(header, manual)
        except Exception as exc:  # noqa: BLE001
            report.append({"family": family.name, "error": f"silicon: {exc}"})

    for datasheet in datasheets:
        try:
            products, _ = extract_products.extract(datasheet)
            tables = pin_tables(datasheet)
            ordering = {e["part_number"]: e for e in extract_ordering.extract(datasheet)[0]}
        except Exception as exc:  # noqa: BLE001
            report.append({"family": family.name, "datasheet": datasheet.name, "error": str(exc)})
            continue
        for product in merge_sku_lists(products, ordering)[: limit or None]:
            part = product["part_number"]
            entry = {
                "part_number": part,
                "family_dir": family.name,
                "datasheet": datasheet.name,
                "attributes": len(product["attributes"]),
                "ordering": bool(ordering.get(part)),
            }
            column = table_label = how = None
            rows = variants = layout = None
            for label, r, v, lay in tables:
                found, method = choose_column(part, product["attributes"], v, ordering)
                how = how or method  # keep the reason even when nothing matched
                if found:
                    column, table_label, rows, variants, layout = found, label, r, v, lay
                    how = method
                    break
            if column is None:
                entry["pins"] = 0
                entry["note"] = f"pin表の列を特定できず {how or ''}".strip()
                report.append(entry)
                _write(out_dir, part, product, None, datasheet, family, table_label, column, ordering.get(part))
                continue
            pins, pin_notes = extract_pins.pins_for(rows, variants, layout, column)
            candidate = None
            if silicon:
                selectors, reg_fields, routes, notes = silicon
                candidate, notes = build_candidate.join(
                    selectors, reg_fields, routes, pins, list(notes) + pin_notes
                )
            entry.update(
                {
                    "table": table_label,
                    "column": column,
                    "column_by": how,
                    "pins": len(pins),
                    "functions": sum(len(p["functions"]) for p in pins),
                    "selectors": len(candidate["route_selectors"]) if candidate else 0,
                    "resolved": sum(
                        1 for p in pins for f in p["functions"] if f.get("selection")
                    ),
                    "unresolved": sum(
                        1 for p in pins for f in p["functions"] if f.get("_unresolved_selector")
                    ),
                }
            )
            report.append(entry)
            _write(out_dir, part, product, candidate or {"pins": pins}, datasheet, family, table_label, column, ordering.get(part))
    return report


def _write(out_dir, part, product, candidate, datasheet, family, table, column, ordering_entry=None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "part_number": part,
        "_provenance": {
            "datasheet": str(datasheet.relative_to(MIRRORS)),
            "manual": str(m.relative_to(MIRRORS)) if (m := find_manual(family)) else None,
            "header": str(h.relative_to(MIRRORS)) if (h := find_header(family)) else None,
            "pin_table": table,
            "pin_column": column,
        },
        "product_attributes": product["attributes"],
        "ordering": ordering_entry,
        "route_selectors": (candidate or {}).get("route_selectors", []),
        "pins": (candidate or {}).get("pins", []),
        "signal_aliases": (candidate or {}).get("_signal_aliases", {}),
    }
    (out_dir / f"{part.lower()}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("candidates"))
    ap.add_argument("--family", help="この family dir だけ処理する")
    ap.add_argument("--limit", type=int, help="family あたりの SKU 上限（試験用）")
    args = ap.parse_args()

    report: list[dict] = []
    for family in family_dirs():
        if args.family and family.name != args.family:
            continue
        print(f"### {family.name}", file=sys.stderr, flush=True)
        try:
            rows = run_family(family, args.out, args.limit)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            continue
        for row in rows:
            if "error" in row:
                print(f"    エラー {row['error'][:70]}", file=sys.stderr)
                continue
            print(
                f"    {row['part_number']:<16} pin{row.get('pins', 0):>4}"
                f" fn{row.get('functions', 0):>5} sel{row.get('selectors', 0):>3}"
                f" 解決{row.get('resolved', 0):>4} 未解決{row.get('unresolved', 0):>4}"
                f"  {row.get('note', '')}",
                file=sys.stderr,
            )
        report += rows

    ok = [r for r in report if r.get("pins")]
    print(
        f"\nSKU {len(report)} 件中 pin を得たもの {len(ok)}"
        f" / 合計 pin {sum(r.get('pins', 0) for r in ok)}"
        f" / 合計 function {sum(r.get('functions', 0) for r in ok)}"
        f" / 解決済み経路 {sum(r.get('resolved', 0) for r in ok)}",
        file=sys.stderr,
    )
    (args.out / "_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
