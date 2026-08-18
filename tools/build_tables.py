#!/usr/bin/env python3
"""Turn the two language editions into normalised tables, marked by confidence.

Every document is published twice, the Chinese edition being the original and the
English one a translation. Each is read on its own and the two readings compared:
a value both editions state is confirmed, a value only one states is not, and a
value they contradict is a conflict for a person to settle.

The output is CSV rather than one large JSON so that the silicon, the orderable
products and their pins can each be looked at on their own -- seeing what CH32V006
is should not require opening a file per package.

Usage:
    uv run tools/build_tables.py --out tables [--family CH32V006]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import extract_ordering  # noqa: E402
import extract_pins  # noqa: E402
import extract_products  # noqa: E402
from crosscheck_languages import canonical_value  # noqa: E402

MIRRORS = Path("/home/mt/dev_wch")

# Datasheet labels, in both languages, that mean the same measurement. Each family
# words these differently -- "Flash memory", "Code FLASH（字节）", "闪存" -- so the
# comparison needs a name of its own rather than the document's.
CANONICAL = {
    "flash_bytes": ("flash", "闪存", "codeflash"),
    "sram_bytes": ("sram", "ram", "零等待sram"),
    "pin_count": ("pinno", "pincount", "pinnumber", "chippinnumber", "芯片引脚数", "引脚数"),
    "gpio_count": ("gpio", "gpioportnumber", "gpioportcount", "numberofgpios",
                   "gpio端口数", "通用io"),
    "package": ("packageform", "package", "封装形式", "封装"),
    "temperature": ("operatingtemperature", "maximumworkingtemperature",
                    "maxoperatingambienttemperature", "工作温度", "最大工作环境温度",
                    "工作环境温度"),
}
# A longer label wins, so "gpioportnumber" is not swallowed by "gpio".
CANONICAL_ORDER = sorted(
    ((field, kw) for field, kws in CANONICAL.items() for kw in kws),
    key=lambda x: -len(x[1]),
)

SIZE = re.compile(r"^(\d+)\s*([KMG])?B?$", re.IGNORECASE)
# A temperature range is worded freely around the same two numbers -- "Industrial
# grade -40℃~85℃", "-40~85°C", "工业级-40℃~85℃" -- so only the numbers are compared.
TEMPERATURE = re.compile(r"(-?\d+)\s*[℃°CcＣ]*\s*[~〜～\-–—到至]+\s*(-?\d+)")
# The Chinese edition writes the multiplication sign full width: QFN48×7 / QFN48X7.
WIDE = str.maketrans({"×": "X", "－": "-", "～": "~", "，": ",", "（": "(", "）": ")"})


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]", "", str(text).lower())


def canonical_field(label: str) -> str | None:
    flat = squash(label)
    for field, keyword in CANONICAL_ORDER:
        if keyword in flat:
            return field
    return None


def as_range(value: str) -> str:
    """The two numbers a temperature range states, or the text if it is not one."""
    m = TEMPERATURE.search(str(value))
    return f"{int(m.group(1))}..{int(m.group(2))}C" if m else str(value).strip()


def as_bytes(value: str) -> str:
    """Normalise 62K / 64KB / 20K to a byte count, leaving anything else alone."""
    m = SIZE.match(str(value).strip().replace("（1）", "").replace("(1)", ""))
    if not m:
        return str(value).strip()
    scale = {"K": 1024, "M": 1024**2, "G": 1024**3}.get((m.group(2) or "").upper(), 1)
    return str(int(m.group(1)) * scale)


def read_edition(datasheet: Path) -> tuple[dict, dict]:
    """One edition's products and ordering rows, keyed by part number."""
    products = {
        p["part_number"]: p["attributes"] for p in extract_products.extract(datasheet)[0]
    }
    ordering = {e["part_number"]: e for e in extract_ordering.extract(datasheet)[0]}
    return products, ordering


def normalise(attributes: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for label, value in attributes.items():
        field = canonical_field(label)
        if not field or not str(value).strip() or str(value).strip() in {"-", "—"}:
            continue
        text = str(value).translate(WIDE).strip()
        if field.endswith("_bytes"):
            text = as_bytes(text)
        elif field == "temperature":
            text = as_range(text)
        out.setdefault(field, text)
    return out


def agree(left: str | None, right: str | None) -> tuple[str, str]:
    """The value to record and how far the two editions back it."""
    if left and right:
        return (left, "confirmed") if canonical_value(left) == canonical_value(right) else (left, "conflict")
    if left:
        return left, "en-only"
    if right:
        return right, "zh-only"
    return "", "missing"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("tables"))
    ap.add_argument("--family")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for family in sorted(MIRRORS.glob("CH32*")):
        if args.family and family.name != args.family:
            continue
        for datasheet in sorted((family / "datasheet_en").glob("*DS0.PDF")):
            zh = family / "datasheet_zh" / datasheet.name
            try:
                en_products, en_ordering = read_edition(datasheet)
                zh_products, zh_ordering = (
                    read_edition(zh) if zh.exists() else ({}, {})
                )
            except Exception as exc:  # noqa: BLE001
                print(f"{datasheet.name}: 読めません {exc}", file=sys.stderr)
                continue
            for part in sorted(set(en_products) | set(zh_products)):
                en = normalise(en_products.get(part, {}))
                zhn = normalise(zh_products.get(part, {}))
                order_en = en_ordering.get(part, {})
                order_zh = zh_ordering.get(part, {})
                row = {
                    "part_number": part,
                    "family_dir": family.name,
                    "datasheet": datasheet.name,
                }
                for field in CANONICAL:
                    value, state = agree(en.get(field), zhn.get(field))
                    row[field] = value
                    row[f"{field}_confidence"] = state
                for field in ("package", "body_size", "pin_pitch", "packing"):
                    value, state = agree(
                        (order_en.get(field) or "").translate(WIDE).strip() or None,
                        (order_zh.get(field) or "").translate(WIDE).strip() or None,
                    )
                    if value:
                        key = "package_ordering" if field == "package" else field
                        row[key] = value
                        row[f"{key}_confidence"] = state
                rows.append(row)

    if not rows:
        print("対象がありません", file=sys.stderr)
        return 1
    write_csv(args.out / "products.csv", rows)
    write_csv(args.out / "silicon.csv", roll_up(rows))
    tally(args.out / "products.csv", rows)
    return 0


def write_csv(path: Path, rows: list[dict]) -> None:
    columns = sorted({k for r in rows for k in r}, key=lambda k: (k.endswith("_confidence"), k))
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def tally(path: Path, rows: list[dict]) -> None:
    import collections

    counts = collections.Counter(
        v for r in rows for k, v in r.items() if k.endswith("_confidence")
    )
    print(f"{path}: {len(rows)} 行", file=sys.stderr)
    for state, n in counts.most_common():
        print(f"  {state:12} {n}", file=sys.stderr)


def silicon_of(part: str) -> str:
    """CH32V006K8U7 -> CH32V006. The family is the part number without its suffix."""
    m = re.match(r"^(CH32[A-Z]\d{3})", part)
    return m.group(1) if m else part


def roll_up(rows: list[dict]) -> list[dict]:
    """One row per silicon, holding what all its packages agree on.

    Looking at what CH32V006 is should not mean opening a file per package. A value
    every package shares belongs to the silicon; one that varies is a property of the
    package and is left to products.csv.
    """
    import collections

    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        grouped[silicon_of(row["part_number"])].append(row)
    fields = [f for f in CANONICAL if f not in ("package",)]
    out = []
    for silicon, members in sorted(grouped.items()):
        entry = {
            "silicon": silicon,
            "part_numbers": len(members),
            "family_dir": members[0]["family_dir"],
            "datasheet": members[0]["datasheet"],
        }
        for field in fields:
            values = {m[field] for m in members if m.get(field)}
            states = {m.get(f"{field}_confidence") for m in members if m.get(field)}
            if not values:
                entry[field] = ""
                entry[f"{field}_confidence"] = "missing"
            elif len(values) == 1:
                entry[field] = values.pop()
                entry[f"{field}_confidence"] = (
                    "confirmed" if states == {"confirmed"} else "partial"
                )
            else:
                # Differs between packages, so it is not a property of the silicon.
                entry[field] = ""
                entry[f"{field}_confidence"] = "varies-by-package"
        entry["packages"] = ",".join(
            sorted({m["package"] for m in members if m.get("package")})
        )
        out.append(entry)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
