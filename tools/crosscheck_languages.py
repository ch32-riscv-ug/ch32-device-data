#!/usr/bin/env python3
"""Extract the same table from both language editions and compare the two.

WCH publishes each document twice: the Chinese edition is the original and the
English one a translation, and the two drift apart -- versions differ, and a
translation can lose or alter a cell. Reading each independently and comparing the
results turns a single unverified reading into two that either agree or point at
exactly where they do not.

Agreement is the confidence signal: a value both editions state is confirmed, one
only one edition states, or where they disagree, is not.

Usage:
    uv run tools/crosscheck_languages.py --family CH32V003 --package TSSOP20
    uv run tools/crosscheck_languages.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import extract_ordering  # noqa: E402
import extract_pins  # noqa: E402
import extract_products  # noqa: E402

MIRRORS = Path("/home/mt/dev_wch")


def editions(family: str, name: str) -> dict[str, Path]:
    """The same document in whichever languages the mirror holds it."""
    out = {}
    for lang in ("en", "zh"):
        path = MIRRORS / family / f"datasheet_{lang}" / name
        if path.exists():
            out[lang] = path
    return out


# The same value is written differently in each edition: "8-channel" and "8路",
# "-40~105 C" and "-40~105℃". Comparing the reading rather than the wording keeps
# the report on real differences.
UNIT_WORDS = ("-channel", "路", "channel", "个", "组", "-group", "group")
# Translation pairs that state the same value in each language's own word. The
# longer phrase must come first so 非零等待 is not half-eaten by 零等待.
EQUIVALENTS = (("非零等待", "nonzerowait"), ("non-zero-wait", "nonzerowait"),
               ("non-zero wait", "nonzerowait"),
               ("零等待", "zerowait"), ("zero-wait", "zerowait"),
               ("zero wait", "zerowait"),
               ("supported", "support"), ("支持", "support"))
# Full-width punctuation in the Chinese edition against ASCII in the English one.
PUNCTUATION = str.maketrans({"（": "(", "）": ")", "，": ",", "、": ",",
                             "：": ":", "；": ";", "℃": "C", "　": ""})


def canonical_value(value) -> str:
    # Lower-case first, so "Supported" meets the equivalence for "supported".
    text = str(value).translate(PUNCTUATION).lower()
    for word, canon in EQUIVALENTS:
        text = text.replace(word, canon)
    for word in UNIT_WORDS:
        text = text.replace(word, "")
    return text.replace("°c", "c").replace(" ", "").strip()


def compare(left: dict, right: dict) -> tuple[list, list, list]:
    """Keys both agree on, keys only one has, and keys where they differ.

    A list is compared as a set of readings, because one edition can carry rows the
    other omits: the Chinese comparison table adds rows the translation drops. What
    matters is whether the values they both state agree.
    """
    def norm(v):
        if isinstance(v, list):
            return {canonical_value(x) for x in v}
        if isinstance(v, dict):
            return {k: canonical_value(x) for k, x in v.items() if str(x).strip()}
        return canonical_value(v)

    shared = left.keys() & right.keys()
    same, differ = [], []
    for k in shared:
        lv, rv = norm(left[k]), norm(right[k])
        # One edition listing extra rows is not a disagreement about the rest.
        if isinstance(lv, set):
            agree = lv <= rv or rv <= lv
        elif isinstance(lv, dict):
            # A column one edition leaves blank is missing information, not a
            # contradiction; only the keys both fill are compared.
            shared_keys = lv.keys() & rv.keys()
            agree = bool(shared_keys) and all(lv[k] == rv[k] for k in shared_keys)
        else:
            agree = lv == rv
        (same if agree else differ).append(k if agree else (k, left[k], right[k]))
    only = [(k, "en" if k in left else "zh") for k in left.keys() ^ right.keys()]
    return sorted(same), sorted(only), sorted(differ)


def products_of(path: Path) -> dict[str, list]:
    """Attribute values in column order.

    The two editions label the columns in their own language -- "Flash memory" and
    "闪存" -- so the labels cannot be compared. The columns are the same columns in
    the same order, so the values can be.
    """
    return {
        p["part_number"]: list(p["attributes"].values())
        for p in extract_products.extract(path)[0]
    }


# A prose column is written in each language and cannot agree across editions;
# comparing it would report a difference on every row and hide the real ones.
LANGUAGE_DEPENDENT = {"description"}


def ordering_of(path: Path) -> dict[str, dict]:
    return {
        e["part_number"]: {
            k: v
            for k, v in e.items()
            if k not in ("part_number", "page") and k not in LANGUAGE_DEPENDENT
        }
        for e in extract_ordering.extract(path)[0]
    }


def pins_of(path: Path, package: str) -> dict[str, list]:
    pins, _, _ = extract_pins.build(path, package, "", "")
    return {
        p["pad"]: [p["number"]] + sorted(
            f"{f['signal']}@{f.get('route')}" for f in p["functions"]
        )
        for p in pins
    }


def report(title: str, left: dict, right: dict, out) -> tuple[int, int]:
    same, only, differ = compare(left, right)
    total = len(same) + len(only) + len(differ)
    print(f"\n  {title}: 一致 {len(same)}/{total}", file=out)
    for key, lang in only:
        print(f"    {lang}のみ  {key}", file=out)
    for key, lv, rv in differ:
        print(f"    不一致  {key}", file=out)
        print(f"       en: {str(lv)[:90]}", file=out)
        print(f"       zh: {str(rv)[:90]}", file=out)
    return len(same), total


def run(family: str, datasheet: str, package: str | None, out) -> None:
    paths = editions(family, datasheet)
    if len(paths) < 2:
        have = ",".join(paths) or "なし"
        print(f"{family}/{datasheet}: 片方の言語しかありません ({have})", file=out)
        return
    print(f"### {family}/{datasheet}", file=out)
    report("製品比較表", products_of(paths["en"]), products_of(paths["zh"]), out)
    report("ordering表", ordering_of(paths["en"]), ordering_of(paths["zh"]), out)
    if package:
        try:
            report(f"pin表({package})", pins_of(paths["en"], package), pins_of(paths["zh"], package), out)
        except SystemExit as exc:
            print(f"\n  pin表({package}): 読めません — {exc}", file=out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--family")
    ap.add_argument("--datasheet")
    ap.add_argument("--package")
    ap.add_argument("--all", action="store_true", help="両言語が揃う全datasheetを比較する")
    args = ap.parse_args()
    out = sys.stderr

    if args.all:
        for fam in sorted(MIRRORS.glob("CH32*")):
            for ds in sorted((fam / "datasheet_en").glob("*DS0.PDF")):
                run(fam.name, ds.name, None, out)
        return 0
    if not args.family:
        ap.error("--family か --all が要ります")
    names = args.datasheet and [args.datasheet]
    if not names:
        names = [p.name for p in sorted((MIRRORS / args.family / "datasheet_en").glob("*DS0.PDF"))]
    for name in names:
        run(args.family, name, args.package, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
