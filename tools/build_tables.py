#!/usr/bin/env python3
"""Build normalised tables whose every value carries its evidence.

"Confirmed" is not a property of any single reading but a judgement over the
evidence as a whole. Each value records which sources state it -- the Chinese
edition (the original), the English edition (its translation), the comparison
table, the ordering table, and structural rules of the part number itself --
and the confidence is derived from that list:

    confirmed   independent pieces of evidence agree
    reference   stated once, nothing corroborates or contradicts it
    conflict    the evidence disagrees; a person must settle it
    missing     nothing states it

So a value stated in only one edition can still be confirmed when a rule backs
it (the second-to-last character of a part number names its package with no
known exception), and a value printed in both editions is confirmed because a
translation error would have broken the agreement. The *_basis column keeps the
list itself, so what a value rests on is never implicit.

Usage:
    uv run tools/build_tables.py --out tables [--family CH32V006]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import extract_ordering  # noqa: E402
import extract_products  # noqa: E402
from crosscheck_languages import canonical_value  # noqa: E402

MIRRORS = Path("/home/mt/dev_wch")
CANDIDATES = Path(__file__).resolve().parent.parent / "candidates"

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

# The second-to-last character of a full part number names the package family.
# Checked against all 84 ordering entries and the 8 hand-made records, no exception.
PACKAGE_LETTER = {"T": "LQFP", "U": "QFN", "P": "TSSOP", "M": "SOP", "R": "QSOP"}
FULL_PART = re.compile(r"^CH32[A-Z]\d{3}[A-Z][0-9A-Z][A-Z]\d$")
SERIES = re.compile(r"^(CH32[A-Z]\d{3})")
# The lead count a package name itself states: LQFP100 -> 100, QFN48X7_A -> 48.
PACKAGE_PINS = re.compile(r"^[A-Z]+(\d+)")
# The comparison table inlines the body size that the ordering table states
# separately: "LQFP64M(10*10)" against "LQFP64M" + "10*10mm". The same fact,
# packaged differently, must not read as a conflict.
DIMENSION = re.compile(r"^(.*?)\s*\((\d+(?:\.\d+)?[X*]\d+(?:\.\d+)?)(?:MM|mm)?\)$")


def split_package(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    m = DIMENSION.match(value)
    return (m.group(1), m.group(2)) if m else (value, None)


def size_canon(value) -> str:
    return canonical_value(str(value).upper().replace("MM", "").replace("X", "*"))


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


class Judgement:
    """A value, the confidence it earned, and the evidence list it rests on."""

    def __init__(self) -> None:
        self.readings: list[tuple[str, str]] = []  # (source, value), original first
        self.checks: list[tuple[str, bool, bool]] = []  # (rule, agreed, soft)

    def state(self, source: str, value: str | None) -> None:
        if value:
            self.readings.append((source, value))

    def check(self, rule: str, agreed: bool, soft: bool = False) -> None:
        """A soft check corroborates when it agrees but cannot raise a conflict.

        The pin-definition table is read by a lossy table extractor, so its lead
        count running short usually means a dropped row, not a contradiction in
        the document. Agreement is still meaningful evidence.
        """
        self.checks.append((rule, agreed, soft))

    def settle(self, canon=canonical_value) -> tuple[str, str, str]:
        basis = "+".join(
            [s for s, _ in self.readings]
            + [r if ok else ("?" if soft else "!") + r for r, ok, soft in self.checks]
        )
        if not self.readings:
            return "", "missing", basis
        distinct = {canon(v) for _, v in self.readings}
        value = self.readings[0][1]
        if len(distinct) > 1 or any(not ok and not soft for _, ok, soft in self.checks):
            return value, "conflict", basis
        independent = len(self.readings) + sum(1 for _, ok, _ in self.checks if ok)
        return value, "confirmed" if independent >= 2 else "reference", basis


def judge_field(row: dict, field: str, sources: list[tuple[str, str | None]],
                checks: list[tuple] = (), canon=canonical_value) -> None:
    j = Judgement()
    for source, value in sources:
        j.state(source, value)
    for rule, ok, *soft in checks:
        j.check(rule, ok, bool(soft and soft[0]))
    value, confidence, basis = j.settle(canon)
    row[field] = value
    row[f"{field}_confidence"] = confidence
    row[f"{field}_basis"] = basis


def select_package(value: str | None, family: str | None) -> str | None:
    """The one alternative in a shared package cell that fits the part number.

    A wildcard column's package cell describes the whole group -- CH32V203C6x6
    lists "LQFP48、QFN48X7" -- so the part-number letter picks which alternative
    is this part's. No unique fit means the cell says nothing about this part
    (the F8x6 cell states only TSSOP20, leaving F8U6 to the ordering table).
    """
    if not value or not family:
        return None
    options = [o.strip() for o in re.split(r"[、,/]", value) if o.strip()]
    hits = [o for o in options if canonical_value(o).startswith(family.lower())]
    return hits[0] if len(hits) == 1 else None


def package_letter_check(part: str, package: str | None) -> list[tuple[str, bool]]:
    """Does the part number's package letter agree with the stated package?"""
    if not package or not FULL_PART.match(part):
        return []
    family = PACKAGE_LETTER.get(part[-2])
    if not family:
        return []
    return [("rule:pn-letter", canonical_value(package).startswith(family.lower()))]


def package_pins(package: str | None) -> str | None:
    m = PACKAGE_PINS.match((package or "").upper())
    return m.group(1) if m else None


def pin_table_counts(part: str) -> tuple[str | None, str | None]:
    """Lead and GPIO-pad counts as the pin-definition table states them.

    Read from candidates/, which build_all.py extracted from the same datasheet's
    pin table. Distinct lead numbers, because a small package can bond several
    pads onto one lead (CH32V003J4M6 lists 11 rows on 8 leads); the exposed pad
    is numbered 0 and is not a lead.
    """
    path = CANDIDATES / f"{part.lower()}.json"
    if not path.exists():
        return None, None
    import json
    pins = json.loads(path.read_text()).get("pins") or []
    leads = {p["number"] for p in pins if isinstance(p.get("number"), int) and p["number"] >= 1}
    gpio = {p["pad"] for p in pins if re.match(r"^P[A-Z]\d+$", p.get("pad", ""))}
    return (str(len(leads)) if leads else None, str(len(gpio)) if gpio else None)


def resolve_full_names(parts: set[str], full: set[str]) -> dict[str, list[str]]:
    """Map a comparison-table abbreviation to the order models it prefixes.

    The ordering table spells the part number in full where the comparison table
    abbreviates it: CH32V208CB there is CH32V208CBU6 here. One abbreviation can
    cover several order models -- CH32V303RC is both RCT6 and RCT7 -- and its
    attributes describe the silicon, so they apply to each.
    """
    mapping = {}
    for part in parts:
        if part in full:
            continue
        if "x" in part:
            # A lower-case x in the comparison table stands for either package
            # letter: CH32V203F8x6 covers both F8P6 and F8U6.
            pattern = re.compile("^" + part.replace("x", "[A-Z0-9]") + "$")
            matches = [f for f in full if pattern.match(f)]
        else:
            matches = [f for f in full if f.startswith(part) and len(f) - len(part) <= 2]
        if matches:
            mapping[part] = sorted(matches)
    return mapping


def build_rows(family: Path, datasheet_name: str) -> list[dict]:
    en_path = family / "datasheet_en" / datasheet_name
    zh_path = family / "datasheet_zh" / datasheet_name
    en_products, en_ordering = read_edition(en_path) if en_path.exists() else ({}, {})
    zh_products, zh_ordering = read_edition(zh_path) if zh_path.exists() else ({}, {})

    full = set(en_ordering) | set(zh_ordering)
    alias = resolve_full_names(set(en_products) | set(zh_products), full)
    listed_as = {long: short for short, longs in alias.items() for long in longs}
    for short, longs in alias.items():
        for products in (en_products, zh_products):
            if short in products:
                attributes = products.pop(short)
                for long in longs:
                    products.setdefault(long, dict(attributes))

    rows = []
    for part in sorted(set(en_products) | set(zh_products) | full):
        zh_attr = normalise(zh_products.get(part, {}))
        en_attr = normalise(en_products.get(part, {}))
        def clean(entry: dict) -> dict:
            return {k: v.translate(WIDE).strip() or None
                    for k, v in entry.items() if isinstance(v, str)}
        zh_ord = clean(zh_ordering.get(part, {}))
        en_ord = clean(en_ordering.get(part, {}))

        row = {"part_number": part, "family_dir": family.name, "datasheet": datasheet_name}
        if part in listed_as:
            row["listed_as"] = listed_as[part]

        # The part number itself: attested by each table that prints the row.
        attested = [
            (name, part)
            for name, present in (
                ("products:zh", part in zh_products), ("products:en", part in en_products),
                ("ordering:zh", part in zh_ordering), ("ordering:en", part in en_ordering),
            )
            if present
        ]
        judge_field(row, "part_number", attested)
        row["part_number"] = part  # judge_field would keep it, but be explicit

        # The series is read off the part number's own structure.
        m = SERIES.match(part)
        judge_field(row, "series",
                    [(s, m.group(1)) for s, _ in attested] if m else [],
                    [("rule:part-number-structure", True)] if m else [])

        # Package: both tables in both editions, plus the part-number letter rule.
        # A body size inlined into the package cell is split off as size evidence.
        if "x" in row.get("listed_as", ""):
            letter = PACKAGE_LETTER.get(part[-2]) if FULL_PART.match(part) else None
            for attr in (zh_attr, en_attr):
                chosen = select_package(attr.get("package"), letter)
                if chosen:
                    attr["package"] = chosen
                else:
                    attr.pop("package", None)
        split = [
            (source, *split_package(value))
            for source, value in (
                ("products:zh", zh_attr.get("package")),
                ("products:en", en_attr.get("package")),
                ("ordering:zh", zh_ord.get("package")),
                ("ordering:en", en_ord.get("package")),
            )
        ]
        pkg_sources = [(s, v) for s, v, _ in split]
        inline_sizes = [(s, d) for s, _, d in split if d]
        stated = next((v for _, v in pkg_sources if v), None)
        judge_field(row, "package", pkg_sources, package_letter_check(part, stated))

        for field in ("flash_bytes", "sram_bytes", "temperature"):
            judge_field(row, field, [
                ("products:zh", zh_attr.get(field)), ("products:en", en_attr.get(field)),
            ])

        table_leads, table_gpio = pin_table_counts(part)

        # GPIO count: the comparison table states it; the pin table's P-pad count
        # corroborates it where the extraction kept every row.
        gpio_sources = [
            ("products:zh", zh_attr.get("gpio_count")), ("products:en", en_attr.get("gpio_count")),
        ]
        gpio_checks = []
        stated_gpio = next((v for _, v in gpio_sources if v), None)
        if stated_gpio and table_gpio:
            gpio_checks = [("pin-table", canonical_value(stated_gpio) == table_gpio, True)]
        elif table_gpio:
            gpio_sources = [("pin-table", table_gpio)]
        judge_field(row, "gpio_count", gpio_sources, gpio_checks)

        # Pin count: three statements of the same number -- the comparison table's
        # pin column, the digits in the package name, the pin-definition table's
        # lead count -- the strongest available carrying the value.
        counted = package_pins(row["package"])
        pin_sources = [
            ("products:zh", zh_attr.get("pin_count")), ("products:en", en_attr.get("pin_count")),
        ]
        stated_pins = next((v for _, v in pin_sources if v), None)
        checks = []
        if not stated_pins and counted:
            pin_sources = [("rule:package-name", counted)]
            stated_pins, counted = counted, None
        if stated_pins and counted:
            checks.append(("rule:package-name", canonical_value(stated_pins) == counted))
        if stated_pins and table_leads:
            checks.append(("pin-table", canonical_value(stated_pins) == table_leads, True))
        elif not stated_pins and table_leads:
            pin_sources = [("pin-table", table_leads)]
        judge_field(row, "pin_count", pin_sources, checks)

        judge_field(row, "body_size", [
            ("ordering:zh", zh_ord.get("body_size")),
            ("ordering:en", en_ord.get("body_size")),
        ] + inline_sizes, canon=size_canon)
        for field in ("pin_pitch", "packing"):
            judge_field(row, field, [
                ("ordering:zh", zh_ord.get(field)), ("ordering:en", en_ord.get(field)),
            ])
        rows.append(row)
    return rows


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
        names = {
            p.name
            for sub in ("datasheet_en", "datasheet_zh")
            for p in (family / sub).glob("*DS0.PDF")
        }
        for name in sorted(names):
            try:
                rows.extend(build_rows(family, name))
            except Exception as exc:  # noqa: BLE001
                print(f"{family.name}/{name}: 読めません {exc}", file=sys.stderr)

    if not rows:
        print("対象がありません", file=sys.stderr)
        return 1
    write_csv(args.out / "products.csv", rows)
    write_csv(args.out / "silicon.csv", roll_up(rows))
    tally(args.out / "products.csv", rows)
    return 0


def write_csv(path: Path, rows: list[dict]) -> None:
    columns = sorted(
        {k for r in rows for k in r},
        key=lambda k: (k.endswith("_basis"), k.endswith("_confidence"), k),
    )
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def tally(path: Path, rows: list[dict]) -> None:
    counts = collections.Counter(
        v for r in rows for k, v in r.items() if k.endswith("_confidence")
    )
    print(f"{path}: {len(rows)} 行", file=sys.stderr)
    for state, n in counts.most_common():
        print(f"  {state:12} {n}", file=sys.stderr)


def roll_up(rows: list[dict]) -> list[dict]:
    """One row per silicon, holding what all its packages agree on.

    Looking at what CH32V006 is should not mean opening a file per package. A value
    every package shares belongs to the silicon; one that varies is a property of the
    package and is left to products.csv.
    """
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        grouped[row.get("series") or row["part_number"]].append(row)
    fields = ["flash_bytes", "sram_bytes", "pin_count", "gpio_count", "temperature"]
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
