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

import build_documents  # noqa: E402
import extract_ordering  # noqa: E402
import extract_package_dims  # noqa: E402
import extract_products  # noqa: E402
from crosscheck_languages import canonical_value  # noqa: E402

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent
CANDIDATES = REPO / "candidates"
SERIES_FACTS = REPO / "curated" / "series-facts.json"
CORE_FACTS = REPO / "curated" / "core-facts.json"
DOCUMENTS = REPO / "manifests" / "documents.json"
# WCH's package-drawing document: an independent statement of body size and pin
# pitch per package name, read separately from each language edition.
PACKAGE_PDF = {lang: MIRRORS / "WCH-common" / f"datasheet_{lang}" / "PACKAGE.PDF"
               for lang in ("zh", "en")}


def load_package_dims() -> dict[str, dict[str, dict]]:
    dims: dict[str, dict[str, dict]] = {}
    for lang, path in PACKAGE_PDF.items():
        if path.exists():
            dims[lang] = {e["package"]: e for e in extract_package_dims.extract(path)}
    return dims


def package_dim_evidence(dims: dict, package: str | None, key: str) -> list[tuple[str, str]]:
    """What PACKAGE.PDF states for this package, per language edition.

    A trailing variant suffix names the same outline: QFN48X7_A looks up QFN48X7.
    """
    if not package:
        return []
    names = (package, package.split("_")[0])
    out = []
    for lang in ("zh", "en"):
        entry = next((dims.get(lang, {}).get(n) for n in names if n in dims.get(lang, {})), None)
        if entry and entry.get(key):
            out.append((f"package-pdf:{lang}", entry[key]))
    return out

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
# A longer label wins, so "gpioportnumber" is not swallowed by "gpio". Within one
# field the keywords are listed most-specific-first, and that order decides which
# column gets promoted when a table has two that mean nearly the same thing.
# CH32V303/305/307 print both:
#
#     Code FLASH（字节） 480K   the whole program flash on the die
#     Flash（字节）      256K   the zero-wait execution area, R_0WAIT
#
# and the second one is what bounds a linker script's FLASH at 0x00000000, so
# `flash` outranks `codeflash`. The loser is not dropped -- it falls through to
# product_attributes.csv, because 480K is a fact about the part too.
CANONICAL_ORDER = sorted(
    ((field, kw) for field, kws in CANONICAL.items() for kw in kws),
    key=lambda x: -len(x[1]),
)
# Where two columns of one table canonicalise onto the same field, the keyword
# listed here wins the field and the other stays an attribute. Length cannot
# decide it: "codeflash" is the longer spelling but the wider quantity. Nothing
# outside this map changes -- the first match in column order still wins, which
# is what keeps CH32V208's "GPIO power supply" (a false match on "gpio") from
# taking gpio_count away from "GPIO port count".
# 中文版は同じ2列を「Code FLASH（字节）480K」と「闪存（字节）256K」と書く。
# 両方の綴りを入れないと片言語だけ直って zh/en が conflict になる。
PREFER = {"flash_bytes": frozenset({"flash", "闪存"})}

SIZE = re.compile(r"^(\d+)\s*([KMG])?B?$", re.IGNORECASE)
# A temperature range is worded freely around the same two numbers -- "Industrial
# grade -40℃~85℃", "-40~85°C", "工业级-40℃~85℃" -- so only the numbers are compared.
TEMPERATURE = re.compile(r"(-?\d+)\s*[℃°CcＣ]*\s*[~〜～\-–—到至]+\s*(-?\d+)")
# The Chinese edition writes the multiplication sign full width: QFN48×7 / QFN48X7.
WIDE = str.maketrans({"×": "X", "－": "-", "～": "~", "，": ",", "（": "(", "）": ")"})

# The second-to-last character of a full part number names the package family.
# Checked against all 84 ordering entries and the 8 hand-made records, no exception.
PACKAGE_LETTER = {"T": "LQFP", "U": "QFN", "P": "TSSOP", "M": "SOP", "R": "QSOP"}
# The final digit names the temperature grade. Checked against all 32 stated
# temperatures with no exception; other digits (1, 3) mark package variants and
# carry no temperature claim.
TEMP_GRADE = {"6": "-40..85C", "7": "-40..105C"}
MAX_ONLY = re.compile(r"^(-?\d+)\s*[℃°CcＣ]*$")
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
    """Dimensions compare numerically: 3.0*3.0mm and 3*3 state the same size."""
    text = str(value).upper().replace("MM", "").replace("X", "*")
    parts = []
    for part in text.split("*"):
        try:
            parts.append(f"{float(part):g}")
        except ValueError:
            parts.append(part.strip())
    return canonical_value("*".join(parts))


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]", "", str(text).lower())


KEEP = re.compile(r"[a-z0-9一-鿿]")


def squash_marked(text: str) -> tuple[str, frozenset[int]]:
    """The squashed label, and where in it the original's words began.

    Squashing is what lets a keyword span a space -- `Code FLASH` has to answer
    to `codeflash` -- so the boundaries have to be carried alongside rather than
    recovered afterwards. `Non-zero wait Code FLASH` squashes to
    "nonzerowaitcodeflash", where "codeflash" no longer starts after a space but
    still starts a word.
    """
    flat: list[str] = []
    starts: set[int] = set()
    fresh = True
    for ch in str(text).lower():
        if not KEEP.match(ch):
            fresh = True
            continue
        # 中文はラベルの中で英字と地続きに書く（`非零等待Code FLASH`）。
        # 字種が変わるところは、空白が無くても語の切れ目。
        if flat and ch.isascii() != flat[-1].isascii():
            fresh = True
        if fresh:
            starts.add(len(flat))
        flat.append(ch)
        fresh = False
    return "".join(flat), frozenset(starts)


def spelt_in(keyword: str, flat: str, starts: frozenset[int]) -> bool:
    """Does the label use this keyword, rather than merely contain it?

    Squashing drops the spaces, so a bare substring test reads a word out of the
    middle of another: `FMC SDRAM` (an SDRAM controller, count 1) becomes
    "fmcsdram" and answers to `sram`, and `programmable current sink` answers to
    `ram`. Both would be read as an SRAM size. An ASCII keyword therefore has to
    begin where a word began. CJK is written without spaces, so the same test
    cannot apply to it and is not needed: those keywords are whole labels.
    """
    at = flat.find(keyword)
    while at != -1:
        if not keyword.isascii() or at in starts:
            return True
        at = flat.find(keyword, at + 1)
    return False


def canonical_match(label: str) -> tuple[str, int] | None:
    """(field, rank). Rank 0 is the spelling PREFER names, 1 is anything else."""
    flat, starts = squash_marked(label)
    for field, keyword in CANONICAL_ORDER:
        if spelt_in(keyword, flat, starts):
            return field, 0 if keyword in PREFER.get(field, ()) else 1
    return None


def canonical_field(label: str) -> str | None:
    found = canonical_match(label)
    return found[0] if found else None


def partitioned(attrs: dict, field: str) -> str | None:
    """A capacity the table states as parts of one group, added back up.

    CH32H41x does not print its SRAM total. The comparison table splits it into
    the regions it is divided into, under one group heading:

        SRAM   内核1高速ITCM       128KB
               内核1高速DTCM       256KB
               共享代码和数据区     512KB

    Reading any one of them as `sram_bytes` understates the part **sevenfold**,
    and the datasheet's own prose gives the total the three add up to（「内置総
    容量896K字節のSRAM」）, so the sum is corroborated rather than invented.

    The group heading is what says these are parts of one quantity and not two
    columns competing for one field: CH32V30x's `Code FLASH` and `Flash` differ
    from the first word onwards and are never added. Every member has to parse
    as a size, which is what keeps a count group (`定时器 高级（16位）` … ) out.
    """
    if not field.endswith("_bytes"):
        return None
    members = [(label, value) for label, value in attrs.items()
               if canonical_field(label) == field]
    if len(members) < 2 or len({label.split()[0] for label, _ in members}) != 1:
        return None
    sizes = [as_bytes(str(value).translate(WIDE).strip()) for _, value in members]
    if not all(size and size.isdigit() for size in sizes):
        return None
    return str(sum(int(size) for size in sizes))


def promoted(label: str, attrs: dict) -> bool:
    """Does this label win its field in this table?

    A table can hold two columns that canonicalise onto one field. Only the
    more specific one becomes the field; the other stays an attribute rather
    than disappearing.
    """
    found = canonical_match(label)
    if not found:
        return False
    field, rank = found
    # 足し合わせて得た値は、どの1行のものでもない。分割はそれ自体が事実なので
    # 子行は全部 product_attributes へ残す（F-14 で 480K を残したのと同じ）。
    if partitioned(attrs, field) is not None:
        return False
    return not any(other != label
                   and (m := canonical_match(other))
                   and m[0] == field and m[1] < rank
                   for other in attrs)


def as_range(value: str) -> str:
    """The two numbers a temperature range states, or the text if it is not one."""
    m = TEMPERATURE.search(str(value))
    return f"{int(m.group(1))}..{int(m.group(2))}C" if m else str(value).strip()


def as_bytes(value: str) -> str:
    """Normalise 62K / 64KB / 20K to a byte count, leaving anything else alone."""
    text = re.sub(r"\s*[（(]\d+[)）]\s*$", "", str(value).strip())
    m = SIZE.match(text)
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
    for field in {f for label in attributes if (f := canonical_field(label))}:
        total = partitioned(attributes, field)
        if total:
            out[field] = total
    for label, value in sorted(attributes.items(),
                               key=lambda kv: (canonical_match(kv[0]) or ("", 0))[1]):
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


def build_rows(family: Path, datasheet_name: str, dims: dict) -> list[dict]:
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

        row = {"part_number": part, "family": family.name, "datasheet": datasheet_name}
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

        for field in ("flash_bytes", "sram_bytes"):
            judge_field(row, field, [
                ("products:zh", zh_attr.get(field)), ("products:en", en_attr.get(field)),
            ])

        # Temperature: the comparison table states a range or only a maximum
        # ("最大工作环境温度 105℃"); the part number's final digit states the grade.
        # A stated range is a reading, a stated maximum is a check against the
        # grade's range, and the grade rule supplies the range where nothing else
        # does -- a reference value until something corroborates it.
        grade = TEMP_GRADE.get(part[-1]) if FULL_PART.match(part) else None
        temp_sources, temp_checks = [], []
        for source, value in (("products:zh", zh_attr.get("temperature")),
                              ("products:en", en_attr.get("temperature"))):
            if not value:
                continue
            m = MAX_ONLY.match(value)
            if m and grade:
                temp_checks.append((f"{source}(max)", grade.endswith(f"..{m.group(1)}C")))
            elif m:
                temp_sources.append((source, f"max{m.group(1)}C"))
            else:
                temp_sources.append((source, value))
        if grade:
            temp_sources.append(("rule:pn-temp-grade", grade))
        judge_field(row, "temperature", temp_sources, temp_checks)

        # The full attribute rows, judged later into product_attributes.csv.
        row["_zh_attrs"] = zh_products.get(part, {})
        row["_en_attrs"] = en_products.get(part, {})
        table_leads, table_gpio = pin_table_counts(part)
        # Sizes and lead counts are properties of the package, not the product.
        # The statements made here are stashed and judged once per package name.
        row["_body"] = [("ordering:zh", zh_ord.get("body_size")),
                        ("ordering:en", en_ord.get("body_size"))] + inline_sizes
        row["_pitch"] = [("ordering:zh", zh_ord.get("pin_pitch")),
                         ("ordering:en", en_ord.get("pin_pitch"))]
        row["_pins"] = [("products:zh", zh_attr.get("pin_count")),
                        ("products:en", en_attr.get("pin_count"))]
        row["_leads"] = table_leads

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

        judge_field(row, "packing", [
            ("ordering:zh", zh_ord.get("packing")), ("ordering:en", en_ord.get("packing")),
        ])
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("tables"))
    ap.add_argument("--family")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    dims = load_package_dims()
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
                rows.extend(build_rows(family, name, dims))
            except Exception as exc:  # noqa: BLE001
                print(f"{family.name}/{name}: 読めません {exc}", file=sys.stderr)

    if not rows:
        print("対象がありません", file=sys.stderr)
        return 1
    # Rows sort by the row's identity -- part number alone is not guaranteed
    # unique (one model can appear in several datasheets), so the full key keeps
    # regeneration and later insertions reproducible with no tie left to chance.
    rows.sort(key=lambda r: (r["part_number"], r["family"], r["datasheet"]))
    attributes = attribute_rows(rows)  # removes the stashed attribute dicts
    packages = package_rows(rows, dims)  # also removes the stashed evidence
    series = series_rows(rows)
    write_csv(args.out / "products.csv", rows, PRODUCT_COLUMNS)
    write_csv(args.out / "packages.csv", packages, PACKAGE_COLUMNS)
    write_csv(args.out / "series.csv", series, SERIES_COLUMNS)
    write_csv(args.out / "families.csv", family_rows(series), FAMILY_COLUMNS)
    write_csv(args.out / "cores.csv", core_rows(), CORE_COLUMNS)
    write_csv(args.out / "errata.csv", errata_rows(), ERRATA_COLUMNS)
    write_csv(args.out / "product_attributes.csv", attributes, ATTRIBUTE_COLUMNS)
    build_documents.write(args.out)
    print(f"{args.out}/product_attributes.csv: {len(attributes)} 行", file=sys.stderr)
    (args.out / "silicon.csv").unlink(missing_ok=True)  # 旧名。series.csvに置き換え
    tally(args.out / "products.csv", rows)
    print(f"{args.out}/series.csv: {len(series)} 行", file=sys.stderr)
    return 0


# Value columns left to right by how much a reader wants them first; the matching
# _confidence and _basis columns follow as blocks in the same order.
PRODUCT_COLUMNS = [
    "part_number", "series", "family", "package", "flash_bytes", "sram_bytes",
    "gpio_count", "temperature", "packing", "listed_as", "datasheet",
]
PACKAGE_COLUMNS = [
    "package", "pin_count", "body_size", "pin_pitch", "product_count", "families",
]
SERIES_COLUMNS = [
    "series", "family", "core", "isa", "flash_bytes", "sram_bytes",
    "gpio_count", "temperature", "packages", "part_number_count", "datasheets",
    "product_url_zh", "product_url_en",
]
FAMILY_COLUMNS = [
    "family", "repository", "series", "series_count", "part_number_count",
    "cores", "datasheets", "reference_manuals", "evt",
]
CORE_COLUMNS = ["core", "isa", "manual", "note"]
ERRATA_COLUMNS = ["id", "series", "condition", "description"]
ATTRIBUTE_COLUMNS = ["part_number", "attribute", "value", "label_zh", "label_en"]


def write_csv(path: Path, rows: list[dict], priority: list[str]) -> None:
    keys = {k for r in rows for k in r}
    plain = [k for k in keys if not k.endswith(("_confidence", "_basis"))]
    values = [k for k in priority if k in keys]
    values += sorted(k for k in plain if k not in values)  # safety net for new fields
    # An empty column named "#" separates the data from its metadata: everything
    # to its right is confidence/basis, not the data itself. One file, so the two
    # can never drift apart, and a reader can simply drop the columns from "#" on.
    meta = (
        [f"{k}_confidence" for k in values if f"{k}_confidence" in keys]
        + [f"{k}_basis" for k in values if f"{k}_basis" in keys]
    )
    columns = values + ["#"] + meta if meta else values
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        # The separator carries "#" in every row too, so the boundary is visible
        # wherever one lands in the file, not only next to the header.
        writer.writerows(({**row, "#": "#"} for row in rows) if meta else rows)


def tally(path: Path, rows: list[dict]) -> None:
    counts = collections.Counter(
        v for r in rows for k, v in r.items() if k.endswith("_confidence")
    )
    print(f"{path}: {len(rows)} 行", file=sys.stderr)
    for state, n in counts.most_common():
        print(f"  {state:12} {n}", file=sys.stderr)


def load_series_facts() -> dict:
    """Hand-verified facts per series (core, ISA), recorded with their evidence.

    Confirmation is a judgement, not necessarily an automated one: these were read
    off the datasheets with a throwaway script and checked by eye in both language
    editions, then written down here so the basis survives.
    """
    import json

    if not SERIES_FACTS.exists():
        return {}
    return json.loads(SERIES_FACTS.read_text()).get("series", {})


def load_documents() -> dict[str, dict[str, list[str]]]:
    """Assigned documents per mirror repository, from the daily-synced catalogue."""
    import json

    data = json.loads(DOCUMENTS.read_text())
    items = data["documents"] if isinstance(data, dict) else data
    by_repo: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for doc in items:
        if doc.get("status") == "excluded":
            continue
        for repo in doc.get("repositories", []):
            by_repo[repo][doc.get("kind", "other")].append(doc["name"])
    return by_repo


def series_rows(rows: list[dict]) -> list[dict]:
    """One row per series: the die as the datasheets describe it.

    The middle of the hierarchy families -> series -> products -> pins. Looking at
    what CH32V006 is should not mean opening a file per package: a value every
    package shares belongs here, one that varies stays in products.csv. A series
    can span datasheets -- CH32V203CCT6 is documented in CH32V205DS0.
    """
    facts = load_series_facts()
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        grouped[row.get("series") or row["part_number"]].append(row)
    fields = ["flash_bytes", "sram_bytes", "gpio_count", "temperature"]
    out = []
    for series, members in sorted(grouped.items()):
        entry = {
            "series": series,
            "family": members[0]["family"],
            "part_number_count": len(members),
            "datasheets": ";".join(sorted({m["datasheet"] for m in members})),
            # Product-page URL shape verified live on both sites (2026-08-18).
            "product_url_zh": f"https://www.wch.cn/products/{series}.html",
            "product_url_en": f"https://www.wch-ic.com/products/{series}.html",
        }
        fact = facts.get(series, {})
        for key in ("core", "isa"):
            entry[key] = fact.get(key, "")
            entry[f"{key}_confidence"] = fact.get(f"{key}_confidence",
                                                  "missing" if not fact.get(key) else "reference")
            entry[f"{key}_basis"] = fact.get(f"{key}_basis", "")
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
                # Differs between packages, so it is not a property of the series.
                entry[field] = ""
                entry[f"{field}_confidence"] = "varies-by-package"
        entry["packages"] = ",".join(
            sorted({m["package"] for m in members if m.get("package")})
        )
        out.append(entry)
    out.sort(key=lambda e: e["series"])
    return out


def dedup_evidence(evidence: list[tuple[str, str | None]], canon=canonical_value) -> list:
    """One reading per (source, value): many products repeating the same statement
    are one statement, but one source stating two values must stay visible."""
    seen: set = set()
    out = []
    for source, value in evidence:
        if not value:
            continue
        key = (source, canon(value))
        if key not in seen:
            seen.add(key)
            out.append((source, value))
    return out


def package_rows(rows: list[dict], dims: dict) -> list[dict]:
    """One row per package name: the master table of physical outlines.

    Body size, pin pitch and lead count belong to the package, so every product's
    ordering-table statement is pooled with PACKAGE.PDF's drawing entry and judged
    once. Products refer to the package by name and carry none of it themselves.
    """
    agg: dict[str, dict] = {}
    for row in rows:
        body = row.pop("_body", [])
        pitch = row.pop("_pitch", [])
        pins = row.pop("_pins", [])
        leads = row.pop("_leads", None)
        name = row.get("package")
        if not name:
            continue
        a = agg.setdefault(name, {"body": [], "pitch": [], "pins": [],
                                  "leads": set(), "count": 0, "families": set()})
        a["count"] += 1
        a["families"].add(row["family"])
        a["body"] += body
        a["pitch"] += pitch
        a["pins"] += pins
        if leads:
            a["leads"].add(leads)
    out = []
    for name, a in sorted(agg.items()):
        entry = {"package": name, "product_count": a["count"],
                 "families": ";".join(sorted(a["families"]))}
        readings = []
        counted = package_pins(name)
        if counted:
            readings.append(("rule:package-name", counted))
        readings += dedup_evidence(a["pins"])
        checks = []
        if a["leads"] and readings:
            agreed = a["leads"] == {canonical_value(readings[0][1])}
            checks.append(("pin-table", agreed, True))
        elif a["leads"]:
            readings = [("pin-table", sorted(a["leads"])[0])]
        judge_field(entry, "pin_count", readings, checks)
        judge_field(entry, "body_size",
                    dedup_evidence(a["body"], size_canon)
                    + package_dim_evidence(dims, name, "body_size"), canon=size_canon)
        judge_field(entry, "pin_pitch",
                    dedup_evidence(a["pitch"], size_canon)
                    + package_dim_evidence(dims, name, "pin_pitch"), canon=size_canon)
        out.append(entry)
    return out


def attribute_name(label: str) -> str:
    """A join-friendly name for a table row: 'ADC/TKey (channel@unitcount)' ->
    'adc_tkey_channel_unitcount'. The original labels stay in their own columns."""
    text = FOOTNOTE_TAIL.sub("", str(label))
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", text).strip("_").lower()
    return text or "attr"


FOOTNOTE_TAIL = re.compile(r"\s*[（(]\d+[)）]")
COUNT = re.compile(r"\d+(?:[+/x*]\d+)*")
TRANSLATIONS = REPO / "curated" / "translations.json"


def load_translations() -> dict:
    import json

    if not TRANSLATIONS.exists():
        return {"labels": {}, "values": {}}
    return json.loads(TRANSLATIONS.read_text(encoding="utf-8"))


def translated(text: str, table: dict) -> str:
    """Look up the hand-made translation, spaces the PDF inserted removed.

    A row-group label is the group heading and the child heading joined by a
    space（`通信接口 CAN`）, and the dictionary is worth keeping in parts rather
    than in every combination the table happens to print, so a label that is not
    there whole is translated a part at a time.
    """
    flat = text.replace(" ", "").replace("　", "")
    if flat in table:
        return table[flat]
    parts = text.split()
    if len(parts) > 1:
        rendered = [table.get(part, part) for part in parts]
        if rendered != parts:
            return " ".join(rendered)
    return text


def display_value(value_en: str, value_zh: str, confidence: str) -> str:
    """The value to print: counts as bare numbers, otherwise readable but true.

    "8路" and "8-channel" both state the count 8, so the number alone carries it
    in either language. Elsewhere the English spelling reads better and the two
    are verified equal when confirmed; a conflict keeps the Chinese original,
    which is the authoritative edition.
    """
    for value in (value_en, value_zh):
        if value and COUNT.fullmatch(canonical_value(value)):
            return canonical_value(value)
    # Chinese never carries the display when an English statement exists -- even
    # a conflict shows the English value; the Chinese original moves to basis.
    return value_en or value_zh


def attribute_rows(rows: list[dict]) -> list[dict]:
    """Every comparison-table row, long format: (part_number, attribute, value).

    The promoted fields (flash, sram, package, ...) live as columns elsewhere and
    are skipped here; everything else the table states is kept, so nothing the
    document says is dropped just because the schema has no column yet.

    The two editions word the labels differently (定时器 / Timer), so rows pair
    by the longest common subsequence of their normalised values -- a translation
    keeps the table's row order, so equal values in equal order are the same row.
    A single unpaired row on each side between two anchors can only be the same
    row stating different values: a conflict.
    """
    import difflib

    translations = load_translations()
    out = []
    for row in rows:
        zh_attrs = row.pop("_zh_attrs", {}) or {}
        en_attrs = row.pop("_en_attrs", {}) or {}
        def keep(attrs: dict) -> list[tuple[str, str]]:
            return [(label, str(value).strip())
                    for label, value in attrs.items()
                    if not promoted(label, attrs)
                    and str(value).strip() not in ("", "-", "—")]
        zh = keep(zh_attrs)
        en = keep(en_attrs)
        zh_canon = [canonical_value(v) for _, v in zh]
        en_canon = [canonical_value(v) for _, v in en]
        matcher = difflib.SequenceMatcher(a=zh_canon, b=en_canon, autojunk=False)
        pairs: list[tuple[int | None, int | None]] = []
        zi = ei = 0
        for block in matcher.get_matching_blocks():
            gap_zh = list(range(zi, block.a))
            gap_en = list(range(ei, block.b))
            if len(gap_zh) == 1 and len(gap_en) == 1:
                pairs.append((gap_zh[0], gap_en[0]))  # same row, different value
            else:
                pairs += [(i, None) for i in gap_zh]
                pairs += [(None, j) for j in gap_en]
            pairs += [(block.a + k, block.b + k) for k in range(block.size)]
            zi, ei = block.a + block.size, block.b + block.size
        used: set[str] = set()
        for zh_i, en_i in pairs:
            label_zh, value_zh = zh[zh_i] if zh_i is not None else ("", "")
            label_en, value_en = en[en_i] if en_i is not None else ("", "")
            if zh_i is not None and en_i is not None:
                agree = canonical_value(value_zh) == canonical_value(value_en)
                confidence = "confirmed" if agree else "conflict"
                # basis も `#` より左のデータ列なので中国語は残せない。
                basis = "products:zh+products:en" if agree \
                    else ("products:en+!products:zh("
                          f"={translated(value_zh, translations['values'])})")
            elif zh_i is not None:
                confidence, basis = "reference", "products:zh"
            else:
                confidence, basis = "reference", "products:en"
            if not label_en and label_zh:
                label_en = ""  # no English source; the id gets the translation
            name = attribute_name(
                label_en or translated(label_zh, translations["labels"]))
            while name in used:
                name += "_"
            used.add(name)
            out.append({
                "part_number": row["part_number"],
                "attribute": name,
                "value": translated(
                    display_value(value_en, value_zh, confidence),
                    translations["values"]),
                "label_zh": label_zh, "label_en": label_en,
                "confidence": confidence, "basis": basis,
            })
    out.sort(key=lambda r: (r["part_number"], r["attribute"]))
    return out


def errata_rows() -> list[dict]:
    """curated/errata.csv, carried into tables/ with its judgement attached.

    source_zh / source_en record where the statement appears in each
    datasheet edition (PDF page numbers, verified via tools/scan_errata.py).
    Both editions agreeing makes the row confirmed; a single edition stays
    reference.  The match column only serves scan_errata.py and is dropped.
    """
    path = REPO / "curated" / "errata.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row.pop("match", "")
        parts = []
        for lang in ("zh", "en"):
            source = row.pop(f"source_{lang}", "").strip()
            if source:
                doc, _, pages = source.partition(" ")
                parts.append(f"{doc}:{lang}({pages})")
        row["description_confidence"] = (
            "confirmed" if len(parts) == 2 else "reference")
        row["description_basis"] = "+".join(parts) or "manual:unsourced"
    return sorted(rows, key=lambda r: r["id"])


def core_rows() -> list[dict]:
    """One row per QingKe core: the master the series' core column joins to."""
    import json

    data = json.loads(CORE_FACTS.read_text())
    out = []
    for core, fact in sorted(data.get("cores", {}).items()):
        entry = {"core": core, "isa": fact.get("isa", ""),
                 "manual": fact.get("manual", ""), "note": fact.get("note", "")}
        entry["isa_confidence"] = data.get("isa_confidence", "reference")
        entry["isa_basis"] = data.get("isa_basis", "")
        out.append(entry)
    return out


def family_rows(series: list[dict]) -> list[dict]:
    """One row per family: the top of the hierarchy, one mirror repository each.

    A family is the documentation unit -- the series that share datasheets, a
    reference manual and an EVT. Everything here is a roll-up of series.csv plus
    the document catalogue, so the whole tree is visible before descending.
    """
    documents = load_documents()
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in series:
        grouped[row["family"]].append(row)
    out = []
    for family, members in sorted(grouped.items()):
        docs = documents.get(family, {})
        out.append({
            "family": family,
            "repository": f"ch32-riscv-ug/{family}",
            "series": ";".join(sorted(m["series"] for m in members)),
            "series_count": len(members),
            "part_number_count": sum(m["part_number_count"] for m in members),
            "cores": ";".join(sorted({m["core"] for m in members if m["core"]})),
            "datasheets": ";".join(sorted(docs.get("datasheet", []))),
            "reference_manuals": ";".join(sorted(docs.get("reference-manual", []))),
            "evt": ";".join(sorted(docs.get("evt", []))),
        })
    return out


if __name__ == "__main__":
    raise SystemExit(main())
