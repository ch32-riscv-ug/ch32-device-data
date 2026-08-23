#!/usr/bin/env python3
"""Build a candidate for every SKU the datasheets list.

The product comparison table gives the SKU universe; the pin table gives one column
per variant. Joining the two needs a mapping from a SKU to its column, which is
either the part number itself or the package the comparison table assigns it.

Reading a reference manual dominates the runtime, so each family is parsed once and
reused across its SKUs.

**Families are independent and run in parallel.** Each one reads its own documents
and writes its own `candidates/<part>.json`, sharing nothing, so the only thing the
parent does is collect the reports. Sequentially the twelve take about 35 minutes
and the cost is very uneven -- CH32H417 alone is 6m35s where CH32V003 is 1m28s --
so the longest are started first and the wall clock ends up close to the longest
single family.

The worker prints nothing while it runs; its block is printed when it finishes, so
**families appear in completion order, not in catalogue order**. Interleaving the
lines live would make them unreadable.

Memory, not cores, is what bounds `--jobs`. A worker walks a whole reference manual,
and pdfplumber keeps both parsed page objects and a text-map LRU, so both caches are
dropped as each page is finished. Without that, one small family peaked at 581 MiB;
with it, the largest family peaks at about 360 MiB. The default is 4 rather than the
core count because **on WSL the memory a worker can actually have is not what
`free` reports**: `free` describes the Linux VM, the Windows host underneath may
have far less, and overcommitting there thrashes instead of failing.

Usage:
    uv run tools/build_all.py --out candidates [--family CH32M030] [--limit 5]
        [--jobs N]

Output is unreviewed machine extraction, written outside devices/.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
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


def find_manuals(family: Path) -> list[Path]:
    """Every edition of the reference manual, oldest first.

    English then Chinese, because the Chinese edition is the newer of the two and
    the later one wins where they state a scalar differently. CH32V407's manual is
    mirrored only in Chinese, so looking in datasheet_en alone left that family
    with no manual at all.
    """
    found = []
    for directory in ("datasheet_en", "datasheet_zh"):
        if not (family / directory).is_dir():
            continue
        found += sorted(p for p in (family / directory).iterdir()
                        if MANUAL.search(p.name))
    return found


def find_gpio(family: Path) -> Path | None:
    """The EVT GPIO driver, whose GPIO_PinRemapConfig() names the legal routes."""
    sources = sorted(family.glob("EVT/**/Peripheral/src/*_gpio.c"))
    return sources[0] if sources else None


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
            # Both editions: "... Pin definition" / "...引脚定义".
            if not any(t in title.lower() for t in extract_pins.PIN_TABLE_TITLE)                     or label in seen:
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
    """Which pin-table column belongs to this SKU, and how that was decided.

    `-` is the pin table's "this package has no such lead" marker, and it heads a
    column in some tables. **It is never a package.** Without dropping it here the
    package-attribute rule below matches it against any attribute whose value is
    `-` (`Ethernet: -`), and the SKU is resolved to a column where every lead is
    `-` -- three CH32V203 parts lost all 74 of their pins that way.
    """
    variants = [v for v in variants if v and v.strip() != "-"]
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
    header, manuals = find_header(family), find_manuals(family)
    gpio = find_gpio(family)
    datasheets = sorted(p for p in (family / "datasheet_en").glob("*DS0.PDF"))
    if not datasheets:
        return report

    silicon = None
    if header:
        try:
            silicon = build_candidate.read_silicon(header, manuals, gpio)
        except Exception as exc:  # noqa: BLE001
            report.append({"family": family.name, "error": f"silicon: {exc}"})

    for datasheet in datasheets:
        try:
            products, _ = extract_products.extract(datasheet)
            tables = pin_tables(datasheet)
            # 名前の語彙は datasheet 単位。片方の表でしか綴られない名前がある。
            spelled = extract_pins.datasheet_names([(r, lay) for _, r, _, lay in tables])
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
            pins, pin_notes = extract_pins.pins_for(rows, variants, layout, column, spelled)
            candidate = None
            if silicon:
                selectors, reg_fields, routes, evt_values, notes = silicon
                candidate, notes = build_candidate.join(
                    selectors, reg_fields, routes, pins, evt_values,
                    list(notes) + pin_notes
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
            "manuals": [str(m.relative_to(MIRRORS)) for m in find_manuals(family)],
            "header": str(h.relative_to(MIRRORS)) if (h := find_header(family)) else None,
            "pin_table": table,
            "pin_column": column,
        },
        "product_attributes": product["attributes"],
        "ordering": ordering_entry,
        "route_selectors": (candidate or {}).get("route_selectors", []),
        "pins": (candidate or {}).get("pins", []),
    }
    (out_dir / f"{part.lower()}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def weight(family: Path) -> int:
    """How much this family costs, near enough to order the queue by.

    Wall clock tracks the size of the documents that have to be parsed, and the
    spread is wide (CH32H417 6m35s against CH32V003 1m28s). Starting the heavy
    ones first is what keeps the tail from being one lone family.
    """
    return sum(p.stat().st_size
               for d in ("datasheet_en", "datasheet_zh")
               if (family / d).is_dir()
               for p in (family / d).iterdir() if p.is_file())


def _one(family: Path, out_dir: Path, limit: int | None) -> tuple[str, list[dict], float, str]:
    """One family, in a worker process. Returns its report rather than printing it."""
    started = time.monotonic()
    try:
        rows = run_family(family, out_dir, limit)
        return family.name, rows, time.monotonic() - started, ""
    except Exception:  # noqa: BLE001
        return family.name, [], time.monotonic() - started, traceback.format_exc()


def show(name: str, rows: list[dict], seconds: float, error: str) -> None:
    print(f"### {name}  {seconds / 60:.1f}分", file=sys.stderr, flush=True)
    if error:
        print(error, file=sys.stderr)
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


def default_jobs() -> int:
    """How many families to read at once. Deliberately far below the core count.

    Cores are not the constraint -- memory is, and **on WSL the memory a worker
    can actually have is not what `free` reports**. `free` describes the Linux
    VM's own allocation; the Windows host underneath may have much less free, and
    overcommitting there does not fail loudly, it thrashes. Six workers hung this
    machine even though `free` showed 8 GB available.

    After dropping both pdfplumber's page properties and its per-page text-map
    LRU, one CH32H417 worker peaks at about **360 MiB**. Four workers therefore
    need roughly 1.5 GiB plus the parent and OS; `--jobs` can raise or lower this
    for a machine's actual headroom.
    """
    return max(1, min(6, (os.cpu_count() or 2) - 1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("candidates"))
    ap.add_argument("--family", help="この family dir だけ処理する")
    ap.add_argument("--limit", type=int, help="family あたりの SKU 上限（試験用）")
    ap.add_argument("--jobs", type=int, default=default_jobs(),
                    help=f"同時に処理する family 数（既定 {default_jobs()}）。"
                         "1 で逐次（例外がそのまま上がる）")
    args = ap.parse_args()

    families = [f for f in family_dirs()
                if not args.family or f.name == args.family]
    # 重いものから。最後に1 family だけ残るのを避ける。
    families.sort(key=weight, reverse=True)
    started = time.monotonic()

    report: list[dict] = []
    if args.jobs <= 1 or len(families) == 1:
        for family in families:
            name, rows, seconds, error = _one(family, args.out, args.limit)
            show(name, rows, seconds, error)
            report += rows
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        print(f"family {len(families)} 件を最大 {args.jobs} 並列で処理します"
              f"（終わった順に出ます）", file=sys.stderr, flush=True)
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(_one, f, args.out, args.limit) for f in families]
            for future in concurrent.futures.as_completed(futures):
                name, rows, seconds, error = future.result()
                show(name, rows, seconds, error)
                report += rows

    report.sort(key=lambda r: r.get("part_number", ""))
    ok = [r for r in report if r.get("pins")]
    print(
        f"\nSKU {len(report)} 件中 pin を得たもの {len(ok)}"
        f" / 合計 pin {sum(r.get('pins', 0) for r in ok)}"
        f" / 合計 function {sum(r.get('functions', 0) for r in ok)}"
        f" / 解決済み経路 {sum(r.get('resolved', 0) for r in ok)}"
        f" / 所要 {(time.monotonic() - started) / 60:.1f}分",
        file=sys.stderr,
    )
    # **`_report.json` は candidates/ 全体の目録**で、この実行の記録ではない。
    # `--family` や `--limit` で一部だけ作り直したときに丸ごと書き換えると、
    # 作り直していない SKU の行が消える——`--family CH32V407` の後に 6 件しか
    # 残っていない目録がコミットされた。今回触った SKU だけ差し替える。
    dest = args.out / "_report.json"
    catalogue = list(report)
    if (args.family or args.limit) and dest.exists():
        touched = {r.get("part_number") for r in report}
        kept = [r for r in json.loads(dest.read_text(encoding="utf-8"))
                if r.get("part_number") not in touched]
        catalogue += kept
        catalogue.sort(key=lambda r: r.get("part_number", ""))
        print(f"目録は {len(report)} 件を差し替え、{len(kept)} 件を残して "
              f"{len(catalogue)} 件になりました", file=sys.stderr)
    dest.write_text(
        json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
