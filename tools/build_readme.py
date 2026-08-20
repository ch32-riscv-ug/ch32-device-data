#!/usr/bin/env python3
"""Generate each mirror repository's README.md from the normalised tables.

This is the project's target direction: the mirrors' human-facing pin tables
are rendered from tables/ -- the judged, evidence-carrying data -- instead of
being maintained by hand or linking to hand-made pages. The output goes to
generated/readme/<FAMILY>.md in this repository; each mirror's daily update
fetches its own file, the same way it fetches the document catalogue, so no
cross-repository token is needed and the copy follows the data.

Content is data-driven so it resists going stale: series facts, document links
(original page, both languages, plus the mirror copy), debug/serial default
pads found by signal role, per-product pin maps, and the alternate-function
and remap-selector tables. Images are the one hand-made part: the generator
keeps whatever image/ files the mirror already has, listed as of generation.

Usage:
    uv run tools/build_readme.py [--out generated/readme] [--family CH32V003]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
TABLES = REPO / "tables"
MIRRORS = Path("/home/mt/dev_wch")
PAGES = "https://ch32-riscv-ug.github.io"

# Signal spellings per role, as the datasheets write them. Route "default" only:
# the point is what the pin does before any remap.
ROLES = (
    ("SWDIO", {"SWIO", "SWDIO", "PA13"}),
    ("SWCLK", {"SWCLK", "SWCK", "PA14"}),
    ("UART TX", {"UTX", "TX", "TX1", "USART1_TX", "U1TX", "TXD1"}),
    ("UART RX", {"URX", "RX", "RX1", "USART1_RX", "U1RX", "RXD1"}),
)
OSC = {"OSCI", "OSCO", "OSC_IN", "OSC_OUT", "XTAL1", "XTAL2", "OSC32_IN", "OSC32_OUT"}

NOTICE = ("<!-- This file is generated from ch32-riscv-ug/ch32-device-data "
          "(tables/ + tools/build_readme.py). Edit there, not here. -->")


def load(name: str) -> list[dict]:
    with (TABLES / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pad_key(pad: str) -> tuple:
    m = re.match(r"^P([A-Z])(\d+)$", pad)
    if m:
        return (0, m.group(1), int(m.group(2)))
    return (1, pad, 0)


def pin_sort(value: str) -> tuple:
    try:
        return (0, int(value), "")
    except ValueError:
        return (1, 0, value)


def human_bytes(value: str) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return value or "-"
    return f"{n // 1024}K" if n % 1024 == 0 else str(n)


def md_escape(text: str) -> str:
    return text.replace("|", "\\|")


class Data:
    def __init__(self) -> None:
        self.series = load("series")
        self.products = load("products")
        self.documents = load("documents")
        self.pins = load("pins")
        self.functions = load("pin_functions")
        self.remap_fields = load("remap_fields")
        self.packages = {r["package"]: r for r in load("packages")}
        self.pins_by_part = collections.defaultdict(list)
        for r in self.pins:
            self.pins_by_part[r["part_number"]].append(r)
        self.fns_by_part = collections.defaultdict(list)
        for r in self.functions:
            self.fns_by_part[r["part_number"]].append(r)
        self.attributes = load("product_attributes")
        self.operating = load("operating_conditions")
        self.evt_examples = load("evt_examples")
        try:
            self.errata = load("errata")
        except FileNotFoundError:
            self.errata = []

    def family_series(self, family: str) -> list[dict]:
        return [s for s in self.series if s["family"] == family]

    def series_products(self, series: str) -> list[dict]:
        return sorted((p for p in self.products if p["series"] == series),
                      key=lambda p: p["part_number"])


def operating_summary(data: Data, series: str) -> tuple[str, str]:
    """(クロック, VDD範囲) -- tables/operating_conditions.csv のシリーズ行から。

    クロックはデータシート1ページ目が謳う系統主頻(F_MAIN)を最優先する。
    電気的特性表のF_HCLKはAHBの上限値で、製品として謳われる周波数とは別物
    （CH32V003は本文48MHz・上限50MHz）。F_MAINが無いシリーズはF_HCLK→
    コア周波数の順で代替する。条件違いで複数値があるときは "200/240" と併記。
    VDDは条件行をまとめた包絡（最小のmin〜最大のmax）を出す。
    """
    rows = [r for r in data.operating
            if series in r["series"].split(";")]
    clock = "-"
    for prefix in ("F_MAIN", "F_HCLK", "F_SYSCLK", "F_CORE"):
        hits = [r for r in rows if r["symbol"].startswith(prefix)
                and r["max"] and r["max"][0].isdigit()]
        if hits:
            values = list(dict.fromkeys(r["max"] for r in hits))
            clock = "/".join(values) + " " + hits[0]["unit"]
            break
    vdd = "-"
    vdd_rows = [r for r in rows if r["symbol"] == "V_DD" and r["min"] and r["max"]]
    if vdd_rows:
        lo = min(vdd_rows, key=lambda r: float(r["min"]))["min"]
        hi = max(vdd_rows, key=lambda r: float(r["max"]))["max"]
        vdd = f"{lo}-{hi}V"
    return clock, vdd


def series_section(data: Data, family: str) -> list[str]:
    if not data.family_series(family):
        return []
    out = ["## Series", "",
           "| Series | Core | ISA | Flash | SRAM | Clock | VDD "
           "| Packages | Products | Official |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for s in data.family_series(family):
        official = (f"[en]({s['product_url_en']}) / [zh]({s['product_url_zh']})")
        clock, vdd = operating_summary(data, s["series"])
        out.append(
            f"| **{s['series']}** | {s['core'] or '-'} | {s['isa'] or '-'} "
            f"| {human_bytes(s['flash_bytes'])} | {human_bytes(s['sram_bytes'])} "
            f"| {clock} | {vdd} "
            f"| {s['packages'] or '-'} | {s['part_number_count']} | {official} |")
    out.append("")
    return out


def documents_section(data: Data, family: str) -> list[str]:
    rows = [d for d in data.documents
            if family in d["repositories"].split(";") and d["status"] == "assigned"]
    if not rows:
        return []
    order = {"datasheet": 0, "reference-manual": 1, "evt": 2}
    rows.sort(key=lambda d: (order.get(d["kind"], 9), d["document"]))
    out = ["## Documents", "",
           "| Document | Kind | English | 中文 |", "|---|---|---|---|"]
    for d in rows:
        cells = {}
        for lang in ("en", "zh"):
            links = []
            if d[f"page_url_{lang}"]:
                links.append(f"[page]({d[f'page_url_{lang}']})")
            mirror = d[f"mirror_url_{lang}"]
            if mirror:
                links.append(f"[mirror]({mirror})")
            version = f" v{d[f'version_{lang}']}" if d[f"version_{lang}"] else ""
            cells[lang] = " ".join(links) + version if links else "-"
        out.append(f"| {d['document']} | {d['kind']} | {cells['en']} | {cells['zh']} |")
    out.append("")
    return out


def default_signals(data: Data, part: str) -> dict[str, set[str]]:
    """pad -> its default-route (and main) signal names."""
    result = collections.defaultdict(set)
    for fn in data.fns_by_part[part]:
        if fn["route"] in ("default", "main"):
            result[fn["pad"]].add(fn["signal"])
    return result


def all_signals(data: Data, part: str) -> dict[str, set[str]]:
    """pad -> every signal name on it, any route.

    The oscillator pins state OSCI/OSCO without a route number, so the OSC
    note has to look past the default route.
    """
    result = collections.defaultdict(set)
    for fn in data.fns_by_part[part]:
        result[fn["pad"]].add(fn["signal"])
    return result


def roles_section(data: Data, family: str) -> list[str]:
    if not data.family_series(family):
        return []
    out = ["## Debug / serial defaults", "",
           "| Series | " + " | ".join(name for name, _ in ROLES) + " |",
           "|---|" + "---|" * len(ROLES)]
    for s in data.family_series(family):
        products = data.series_products(s["series"])
        if not products:
            continue
        defaults = default_signals(data, products[0]["part_number"])
        cells = []
        for _, names in ROLES:
            pads = sorted({pad for pad, signals in defaults.items()
                           if signals & names and pad not in names})
            cells.append(",".join(pads) or "-")
        out.append(f"| {s['series']} | " + " | ".join(cells) + " |")
    out.append("")
    return out


def notes_for(pad: str, defaults: dict[str, set[str]],
              everything: dict[str, set[str]]) -> str:
    notes = []
    for role, names in ROLES:
        if defaults.get(pad, set()) & names and pad not in names:
            notes.append(role)
    if everything.get(pad, set()) & OSC:
        notes.append("OSC")
    return ", ".join(notes)


VIEWER = f"{PAGES}/ch32-device-data/pins.html"


def comparison_section(data: Data, series: dict) -> list[str]:
    """The datasheet-style product comparison table, transposed: one column per
    product, one row per stated attribute. This is the in-repository selector
    the old README served with images -- which product of this series to pick.
    """
    products = data.series_products(series["series"])
    if len(products) < 2:
        return []
    parts = [p["part_number"] for p in products]
    by_part = {p: {} for p in parts}
    labels: dict[str, str] = {}
    order: list[str] = []
    for r in data.attributes:
        if r["part_number"] not in by_part:
            continue
        by_part[r["part_number"]][r["attribute"]] = r["value"]
        labels.setdefault(r["attribute"], r["label_en"] or r["label_zh"])
        if r["attribute"] not in order:
            order.append(r["attribute"])

    def head(part: str) -> str:
        pkg = next(p["package"] for p in products if p["part_number"] == part)
        return f"{part[:8]}&#8203;{part[8:]}&#8203;({pkg})"

    out = [f"### {series['series']} product comparison", "",
           "| | " + " | ".join(head(p) for p in parts) + " |",
           "|---|" + "---|" * len(parts)]
    fixed = [("Flash", "flash_bytes"), ("SRAM", "sram_bytes"),
             ("GPIO", "gpio_count"), ("Temperature", "temperature")]
    prod_by_part = {p["part_number"]: p for p in products}
    for title, field in fixed:
        values = [human_bytes(prod_by_part[p].get(field, "")) if "bytes" in field
                  else (prod_by_part[p].get(field, "") or "-") for p in parts]
        if any(v not in ("", "-") for v in values):
            out.append(f"| **{title}** | " + " | ".join(values) + " |")
    for attr in order:
        values = [md_escape(by_part[p].get(attr, "-") or "-") for p in parts]
        label = md_escape(labels.get(attr, attr))
        out.append(f"| {label} | " + " | ".join(values) + " |")
    out.append("")
    return out
FEATURES = ("ADC", "I2C", "SPI", "SYS", "TIM", "UART", "USB")


def filter_links(series: str) -> str:
    """The filterable pin-function viewer, pre-filtered per feature."""
    links = [f"[ALL]({VIEWER}?chip={series})"]
    links += [f"[{f}]({VIEWER}?chip={series}&features={f})" for f in FEATURES]
    return "Pin functions (filterable): " + " ".join(links)


def pin_map_section(data: Data, series: dict) -> list[str]:
    products = data.series_products(series["series"])
    parts = [p["part_number"] for p in products if data.pins_by_part[p["part_number"]]]
    if not parts:
        return []
    per_part: dict[str, dict[str, str]] = {}
    types: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for part in parts:
        cells: dict[str, str] = {}
        for r in data.pins_by_part[part]:
            cells[r["pad"]] = (cells.get(r["pad"]) + "/" + r["pin"]
                               if r["pad"] in cells else r["pin"])
            if r["type"]:
                types[r["pad"]][r["type"]] += 1
        per_part[part] = cells
    pads = sorted({pad for cells in per_part.values() for pad in cells}, key=pad_key)
    defaults = default_signals(data, parts[0])
    everything = all_signals(data, parts[0])

    def head(part: str) -> str:
        package = next(p["package"] for p in products if p["part_number"] == part)
        return (f"[{part[:8]}&#8203;{part[8:]}]({VIEWER}?chip={part})"
                f"&#8203;({package})")

    out = [f"### {series['series']} pin map", "",
           filter_links(series["series"]), "",
           "| Pin name | Type | " + " | ".join(head(p) for p in parts)
           + " | Notes |",
           "|---|---|" + "---|" * len(parts) + "---|"]
    for pad in pads:
        type_counter = types.get(pad)
        pin_type = type_counter.most_common(1)[0][0] if type_counter else ""
        cells = [per_part[p].get(pad, "-") for p in parts]
        out.append(f"| {md_escape(pad)} | {md_escape(pin_type)} | "
                   + " | ".join(cells)
                   + f" | {notes_for(pad, defaults, everything)} |")
    out.append("")
    return out


def functions_section(data: Data, series: dict) -> list[str]:
    products = data.series_products(series["series"])
    parts = [p["part_number"] for p in products if data.fns_by_part[p["part_number"]]]
    if not parts:
        return []
    # The function set is a property of the pad row, so the union over the
    # series' products is shown once; a pad only on some packages still shows.
    by_pad: dict[str, dict[str, set]] = collections.defaultdict(
        lambda: collections.defaultdict(set))
    for part in parts:
        for fn in data.fns_by_part[part]:
            if fn["route"] != "main":
                by_pad[fn["pad"]][fn["route"]].add(fn["signal"])
    if not by_pad:
        return []
    routes = sorted({route for pad in by_pad.values() for route in pad},
                    key=lambda r: (r != "default", r))
    # A signal the datasheet lists without a route number (OSCI, SWDIO on some
    # parts) sits under an unnumbered column rather than an empty heading.
    heading = {"": "(no route stated)"}
    out = [f"<details><summary><b>{series['series']} alternate functions</b>"
           f"</summary>", "",
           "| Pad | " + " | ".join(heading.get(r, r) for r in routes) + " |",
           "|---|" + "---|" * len(routes)]
    for pad in sorted(by_pad, key=pad_key):
        cells = [", ".join(sorted(by_pad[pad].get(route, ()))) or "-"
                 for route in routes]
        out.append(f"| {md_escape(pad)} | " + " | ".join(md_escape(c) for c in cells) + " |")
    out += ["", "</details>", ""]
    return out


def remap_section(data: Data, family: str) -> list[str]:
    series_names = {s["series"] for s in data.family_series(family)}
    rows = [r for r in data.remap_fields if r["series"] in series_names]
    if not rows:
        return []
    out = ["<details><summary><b>Remap selectors (AFIO)</b></summary>", "",
           "| Series | Field | Register | Bits | Values | Reset |",
           "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["series"], r["selector"])):
        # A field spanning two registers reads PCFR1|PCFR2, and a bare pipe would
        # end the cell.
        register = r["register"].replace("|", "\\|")
        out.append(f"| {r['series']} | {r['field']} | {register} "
                   f"| {r['bits']} | {r['valid_values']} | {r['reset_value']} |")
    out += ["", "</details>", ""]
    return out


def errata_section(data: Data, family: str) -> list[str]:
    """Errata rows for this family's series, from tables/errata.csv."""
    mine = {s["series"] for s in data.family_series(family)}
    rows = [e for e in data.errata
            if mine & set(e["series"].split(";"))]
    if not rows:
        return []
    out = ["## Errata", ""]
    for e in sorted(rows, key=lambda e: e["id"]):
        applies = ", ".join(e["series"].split(";"))
        out.append(f"- {e['description']} *(applies: {applies}; {e['condition']})*")
    out.append("")
    return out


def extras_section(family: str) -> list[str]:
    """Hand-written content the tables cannot state (errata, repository notes).

    Lives in curated/readme-extras/<FAMILY>.md and is carried into the generated
    page verbatim, so regeneration never loses it.
    """
    path = REPO / "curated" / "readme-extras" / f"{family}.md"
    if not path.exists():
        return []
    return [path.read_text(encoding="utf-8").rstrip(), ""]


PACKAGE_IMAGES = ("https://raw.githubusercontent.com/ch32-riscv-ug/"
                  "WCH-common/main/image")


def block_diagrams(data: Data, family: str) -> list[str]:
    """シリーズごとのブロック図。データシートの第1章から切り出したもので、
    名前は固定（存在確認はしない）。"""
    series = data.family_series(family)
    if not series:
        return []
    out = ["## Block diagrams", ""]
    for s in series:
        out += [f"### {s['series']}",
                f'<img src="image/architecture_{s["series"]}.png" '
                f'alt="{s["series"]} block diagram" />', ""]
    return out


def pinout_reference(data: Data, family: str) -> list[str]:
    """ピン配置図はデータシートの中にある。READMEには並べず、
    どのパッケージがどの型番のものかだけを示して原典へ送る。

    画像として切り出す仕組み（tools/extract_images.py）はあるが、切り出し
    品質の調整が済むまで生成物は使わない。
    """
    import check_images
    package_of = {p["part_number"]: p["package"] for p in data.products}
    groups = [(name, parts) for (fam, name), parts
              in check_images.pinout_groups().items() if fam == family]
    if not groups:
        return []
    out = ["## Pinouts", "",
           "Pinout drawings are in the datasheet (chapter *Pinouts*):", "",
           "| Package | Products | Datasheet | Outline |", "|---|---|---|---|"]
    documents = {d["document"]: d for d in data.documents}
    for _, parts in sorted(groups, key=lambda g: g[1][0]):
        product = next(p for p in data.products if p["part_number"] == parts[0])
        document = documents.get(product["datasheet"], {})
        links = " / ".join(
            f"[{lang}]({document[f'mirror_url_{lang}']})"
            for lang in ("en", "zh") if document.get(f"mirror_url_{lang}"))
        package = package_of[parts[0]]
        out.append(f"| {package} | {', '.join(parts)} "
                   f"| {links or product['datasheet']} "
                   f"| [drawing]({PACKAGE_IMAGES}/package_{package}.png) |")
    out.append("")
    return out


def evt_examples_section(data: Data, family: str) -> list[str]:
    """EVT例題の要約。1600行超あるので周辺グループ単位の件数だけを出し、
    中身はEVTツリーへのリンクで辿らせる。"""
    rows = [r for r in data.evt_examples if r["family"] == family]
    if not rows:
        return []
    groups: dict[str, int] = {}
    for r in rows:
        groups[r["group"]] = groups.get(r["group"], 0) + 1
    base = f"https://github.com/ch32-riscv-ug/{family}/tree/main/EVT/EXAM"
    listed = " · ".join(f"[{g}]({base}/{g}) {n}"
                        for g, n in sorted(groups.items()))
    return ["## EVT examples", "",
            f"{len(rows)} routines in [EVT/EXAM]({base}):", "",
            listed, ""]


def render(data: Data, family: str) -> str:
    lines = [f"# {family}", "", NOTICE, ""]
    lines += series_section(data, family)
    lines += roles_section(data, family)
    lines += documents_section(data, family)
    lines += pinout_reference(data, family)
    if data.family_series(family):
        lines += ["## Product comparison", ""]
        for s in data.family_series(family):
            lines += comparison_section(data, s)
        lines += ["## Pin definitions", ""]
    for s in data.family_series(family):
        lines += pin_map_section(data, s)
        lines += functions_section(data, s)
    lines += remap_section(data, family)
    lines += block_diagrams(data, family)
    lines += errata_section(data, family)
    lines += evt_examples_section(data, family)
    lines += extras_section(family)
    lines += ["---",
              "Data: [ch32-device-data](https://github.com/ch32-riscv-ug/"
              "ch32-device-data) (tables/ -- each value carries its evidence "
              "and confidence there).", ""]
    return "\n".join(lines)


ORG_INTRO = """# CH32 RISC-V User Group

This is a user group that uses RISC-V chips such as WCH's CH32V series.
"""

# Repositories the tables know nothing about; edited here, in the generator.
ORG_STATIC = """## Toolchain mirror

- https://github.com/ch32-riscv-ug/MounRiver_Studio_Community_miror

## Arduino IDE

- https://github.com/ch32-riscv-ug/arduino_core_ch32_riscv_noneos \
  (runs EVT code on the Arduino IDE)
- https://github.com/ch32-riscv-ug/arduino_core_ch32_riscv_arduino \
  (Arduino-compatible core)
"""


def org_profile(data: Data) -> str:
    """The organisation landing page: which series live in which repository.

    The family repositories are named after document families (CH32V20x holds
    V203, V205 and V208), which hides what is inside; this table states it.
    """
    families = load("families")
    lines = [ORG_INTRO, NOTICE, "", "## Device documentation mirrors", "",
             "| Repository | Series inside | Cores | Products | Documents |",
             "|---|---|---|---|---|"]
    for f in families:
        url = f"https://github.com/{f['repository']}"
        series = ", ".join(f["series"].split(";"))
        cores = ", ".join(sorted({c for token in f["cores"].split(";")
                                  for c in token.split(" + ") if c}))
        docs = []
        if f["datasheets"]:
            docs.append(f"DS×{len(f['datasheets'].split(';'))}")
        if f["reference_manuals"]:
            docs.append("RM")
        if f["evt"]:
            docs.append("EVT")
        lines.append(f"| [{f['family']}]({url}) | {series} | {cores} "
                     f"| {f['part_number_count']} | {' '.join(docs)} |")
    # 型番から辿れるように。リポジトリ名は文書ファミリーの名前なので、
    # CH32M007がCH32V006に、CH32M103がCH32L103に入っている等は
    # 型番を知っているだけでは辿り着けない。
    lines += ["", "## Find your part", "",
              "Repository names follow the document family, not the part "
              "number. Look up the series (the first 8 characters of a part "
              "number) here:", "",
              "| Series | Repository | Products | Example part numbers |",
              "|---|---|---|---|"]
    for s in data.series:
        parts = [p["part_number"] for p in data.products
                 if p["series"] == s["series"]]
        shown = ", ".join(parts[:3]) + (", …" if len(parts) > 3 else "")
        url = f"https://github.com/ch32-riscv-ug/{s['family']}"
        lines.append(f"| **{s['series']}** | [{s['family']}]({url}) "
                     f"| {len(parts)} | {shown} |")

    common = sorted(d["document"] for d in data.documents
                    if "WCH-common" in d["repositories"].split(";")
                    and d["status"] == "assigned")
    lines += ["",
              "## Cross-family documents",
              "",
              "- [WCH-common](https://github.com/ch32-riscv-ug/WCH-common): "
              + ", ".join(common),
              "",
              "## Data",
              "",
              "- [ch32-device-data](https://github.com/ch32-riscv-ug/"
              "ch32-device-data): the normalised tables (series, products, "
              "packages, pins, remap) every mirror README is generated from. "
              "Each value carries its evidence and confidence.",
              "",
              ORG_STATIC]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "generated" / "readme")
    ap.add_argument("--family")
    args = ap.parse_args()
    data = Data()
    args.out.mkdir(parents=True, exist_ok=True)
    # Every mirror repository gets a README: the families, and the common-
    # document repository, which renders as its document list alone.
    families = sorted(
        {s["family"] for s in data.series}
        | {repo for d in data.documents if d["status"] == "assigned"
           for repo in d["repositories"].split(";")
           if repo and repo != "ch32-device-data"}
    )
    for family in families:
        if args.family and family != args.family:
            continue
        text = render(data, family)
        (args.out / f"{family}.md").write_text(text, encoding="utf-8")
        print(f"{args.out}/{family}.md: {len(text.splitlines())} 行", file=sys.stderr)
    if not args.family:
        profile = org_profile(data)
        (args.out / "_profile.md").write_text(profile, encoding="utf-8")
        print(f"{args.out}/_profile.md: {len(profile.splitlines())} 行", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
