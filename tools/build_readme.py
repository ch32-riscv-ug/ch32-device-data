#!/usr/bin/env python3
"""Generate each mirror repository's README.md from the normalised tables.

This is the project's target direction: the mirrors' human-facing pin tables
are rendered from evidence/ and index/ -- the judged, evidence-carrying data -- instead of
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
import urllib.parse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import signal_vocabulary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
MIRRORS = Path("/home/mt/dev_wch")
PAGES = "https://ch32-riscv-ug.github.io"

# **綴りの集合を持たない。** 同じ役割を資料ごとに違う名前で書く
# （`USART1_TX` / `TX1` / `UTX` / `UART_TX`、`SWDIO` / `DIO`）ので、集合で書くと
# 必ず取りこぼす——実際 CH32M030 の `UART_TX` が漏れ、pad 名を入れたせいで
# 2線式SDIの family 全部で SWDIO の列が空だった。綴りを揃えた索引が
# `index/pinout.csv` にあるので、そこから (peripheral, role) で引く。
# **UART は instance を決め打たない。** CH32X033 の 20 ピン品は USART1 を既定の
# route に持たず、既定で出ているのは USART2 と USART4。`USART1` で引くと
# 「UART が無い」という誤った空欄になる。
USART = re.compile(r"^USART\d+$")
OSC = {"OSCI", "OSCO", "OSC_IN", "OSC_OUT", "XTAL1", "XTAL2", "OSC32_IN", "OSC32_OUT"}

NOTICE = ("<!-- This file is generated from ch32-riscv-ug/ch32-device-data "
          "(index/ + evidence/ + tools/build_readme.py). Edit there, not here. -->")


def load(name: str) -> list[dict]:
    """目録・証拠の表は名前で、索引は `index:` を付けて読む（tools/paths.py）。"""
    if name.startswith("index:"):
        return paths.load_index(name[len("index:"):])
    return paths.load(name)


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


def series_bytes(data: "Data", series: dict, column: str) -> str:
    """Series 行の Flash/SRAM。**型番で違う series は実値を全部並べる**（`128K/256K`）。

    `catalog/series.csv` は「その series の全型番で同じ値」だけを持ち、型番で変わる
    ものは空にして `confidence` に `varies-by-package` と書く（値は products 側）。
    表示までそれに従うと空欄になり、**資料に無い**のか**1つに決まらない**のかが
    読む側から区別できない。決まらない理由は型番差なので、その差そのものを出す。
    条件で複数値になる Clock 列（`200/240`）と同じ `/` 区切り。
    """
    if series[column]:
        return human_bytes(series[column])
    values = sorted({int(p[column]) for p in data.series_products(series["series"])
                     if p[column].isdigit()})
    return "/".join(human_bytes(str(v)) for v in values) or "-"


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
        # B4 で足した節が読むもの。無くても頁は組めるようにしておく。
        for name in ("eval_boards", "memory_map", "sources", "families"):
            try:
                setattr(self, name, load(name))
            except FileNotFoundError:
                setattr(self, name, [])
        self.feature_tags = load("index:features")
        # 索引 pinout の、機能を持つ行だけ（lead だけの行は peripheral が空）。
        self.roles_by_part = collections.defaultdict(list)
        for r in load("index:pinout"):
            if r["peripheral"]:
                self.roles_by_part[r["part_number"]].append(r)

    def family_series(self, family: str) -> list[dict]:
        return [s for s in self.series if s["family"] == family]

    def series_products(self, series: str) -> list[dict]:
        return sorted((p for p in self.products if p["series"] == series),
                      key=lambda p: p["part_number"])


def operating_summary(data: Data, series: str) -> tuple[str, str]:
    """後方互換のまま (クロック, VDD)。記号まで要るときは operating_detail。"""
    clock, vdd, _ = operating_detail(data, series)
    return clock, vdd


def operating_detail(data: Data, series: str) -> tuple[str, str, str]:
    """(クロック, VDD範囲) -- evidence/operating_conditions.csv のシリーズ行から。

    クロックはデータシート1ページ目が謳う系統主頻(F_MAIN)を最優先する。
    電気的特性表のF_HCLKはAHBの上限値で、製品として謳われる周波数とは別物
    （CH32V003は本文48MHz・上限50MHz）。F_MAINが無いシリーズはF_HCLK→
    コア周波数の順で代替する。条件違いで複数値があるときは "200/240" と併記。
    VDDは条件行をまとめた包絡（最小のmin〜最大のmax）を出す。
    """
    rows = [r for r in data.operating
            if series in r["series"].split(";")]
    clock, symbol = "-", ""
    for prefix in ("F_MAIN", "F_HCLK", "F_SYSCLK", "F_CORE"):
        hits = [r for r in rows if r["symbol"].startswith(prefix)
                and r["max"] and r["max"][0].isdigit()]
        if hits:
            values = list(dict.fromkeys(r["max"] for r in hits))
            clock = "/".join(values) + " " + hits[0]["unit"]
            symbol = prefix
            break
    vdd = "-"
    vdd_rows = [r for r in rows if r["symbol"] == "V_DD" and r["min"] and r["max"]]
    if vdd_rows:
        lo = min(vdd_rows, key=lambda r: float(r["min"]))["min"]
        hi = max(vdd_rows, key=lambda r: float(r["max"]))["max"]
        vdd = f"{lo}-{hi}V"
    return clock, vdd, symbol


def series_section(data: Data, family: str) -> list[str]:
    if not data.family_series(family):
        return []
    rows, varies, electrical = [], False, False
    for s in data.family_series(family):
        official = (f"[en]({s['product_url_en']}) / [zh]({s['product_url_zh']})")
        clock, vdd, symbol = operating_detail(data, s["series"])
        # **「主頻」と「電気的上限」は別のもの。** 22 series は datasheet が謳う
        # 系統主頻（F_MAIN）を持つが、5 series は持たず電気的特性表の上限で
        # 埋めている（CH32V003 は本文 48MHz・上限 50MHz）。列名ひとつでは
        # どちらとも言えないので、代替した series に印を付ける（worklist G10）。
        if symbol and symbol != "F_MAIN":
            clock += "\\*"
            electrical = True
        flash, sram = series_bytes(data, s, "flash_bytes"), series_bytes(data, s, "sram_bytes")
        varies = varies or "/" in flash or "/" in sram
        rows.append(
            f"| **{s['series']}** | {s['core'] or '-'} | {s['isa'] or '-'} "
            f"| {flash} | {sram} | {clock} | {vdd} "
            f"| {s['packages'] or '-'} | {s['part_number_count']} | {official} |")
    out = ["## Series", ""]
    if varies:
        out += ["Flash and SRAM list every value the series has; more than one "
                "means it varies by part number, and the per-part values are in "
                "the comparison table below.", ""]
    out += ["| Series | Core | ISA | Flash | SRAM | Main clock | VDD "
            "| Packages | Products | Official |",
            "|---|---|---|---|---|---|---|---|---|---|"] + rows + [""]
    if electrical:
        out += ["\\* the datasheet states no nominal system main frequency for "
                "this series, so the figure is the electrical maximum (HCLK) "
                "from the characteristics table -- a limit, not a rating.", ""]
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


def roles_section(data: Data, family: str, level: str = "##") -> list[str]:
    """Quick start の「とりあえずどこに繋ぐか」の表。

    **`index/pinout.csv` から素直に引く。** 綴りを揃えるのはあちらの仕事で、
    ここで `USART1_TX` / `TX1` / `UTX` / `UART_TX` の4通りを知っている必要は無い
    ——以前はここが綴りを抱え込み、`UART_TX` を取りこぼして CH32M030 の欄が
    空になっていた。

    **USART は2つまで。** 資料には8つ持つ series があるが、この表は「基本は
    SWD と USART1 が分かればよく、USART1 が無いときに他をどこへ繋ぐか」を見る
    ためのもの。全部並べると読む表ではなくなるので、USART1 を先に、無ければ
    番号の小さいほうから2つに絞り、残りは Pin definitions に譲る。
    """
    if not data.family_series(family):
        return []
    out = [f"{level} Debug / serial defaults", "",
           "Where these land **without writing a remap register**. SWD is live at "
           "reset; the UART pads are not -- the pin must still be put into "
           "alternate-function mode. See `route` in evidence/README.ja.md.", "",
           "| Series | SWDIO | SWCLK | UART TX | UART RX |",
           "|---|---|---|---|---|"]
    marked = False
    for s in data.family_series(family):
        products = data.series_products(s["series"])
        if not products:
            continue
        # **1型番だけ見ない。** 小さい package にその pad が無いことがあり、
        # CH32V006 の先頭品では USART1 が remap にしか出ない。series の全品を
        # 合わせて「この series のどこに出るか」を答える。
        # **`main` と `default` の両方を見る。** どちらの列に書くかは datasheet が
        # family ごとに違い（SWD は 4 family が主功能列、7 family が既定代替功能列）、
        # `main` だけで引くと 7 family の SWD を落とす。意味の違いは
        # evidence/README.ja.md の「`route` の値の意味」にある。
        default: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
        alternate: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
        for product in products:
            for r in data.roles_by_part[product["part_number"]]:
                key = (r["peripheral"], r["role"])
                if r["route"] in ("default", "main"):
                    default[key].add(r["pad"])
                elif r["route"].startswith("af-"):
                    # **AF 方式の family（V205・X315・H41x）に「既定」は無い。**
                    # どの機能もレジスタで選ぶので、`af-7` に出る USART1 は
                    # 「そこへ出せる」であって「そこに出ている」ではない。
                    alternate[key].add(r["pad"])
        cells = [",".join(sorted(default.get(("SDI", role), set()), key=pad_key)) or "-"
                 for role in ("SWDIO", "SWCLK")]
        for role in ("TX", "RX"):
            chosen = usart_choice(default, role)
            if chosen:
                cells.append("; ".join(
                    f"{','.join(sorted(pads, key=pad_key))} ({name})"
                    for name, pads in chosen))
            elif any(USART.match(p) and r == role for p, r in alternate):
                # **既定が無いことは空欄ではない。** AF 方式は電源投入時に
                # どの USART も出ていないので、「無い」ではなく「既定が無い」。
                cells.append("none by default[^af]")
                marked = True
            else:
                cells.append("-")
        out.append(f"| {s['series']} | " + " | ".join(cells) + " |")
    if marked:
        out += ["",
                "[^af]: This series selects every pin function through "
                "`AFIO->GPIOx_AFLR/AFHR` rather than through AFIO remap, so no "
                "USART is routed out until software picks one -- the pads it "
                "**can** go on are listed under Pin definitions. The reset "
                "value of `GPIOx_AFLR/AFHR` is 0, which selects AF0 (a real "
                "function, not \"none\"), and a pad only drives its alternate "
                "function once its GPIO mode is set to alternate."]
    out.append("")
    return out


# 群の名前を剥がしても意味が残る見出し。略語か数を含んでいれば、それ自身が
# 何かを名指している（`CAN`・`Basic (16-bit)`・`Core 1 HS ITCM`）。
# 含まないものは普通の英単語で、群が無いと何のことか分からなくなる
# （`ADC/TKey Unit` の `Unit`、`3-phase gate drive Voltage` の `Voltage`）。
NAMES_ITSELF = re.compile(r"[A-Z]{2,}|\d")

# **群の名前自体が分類語でしかない群**は、葉が普通の英単語1つでも剥がしてよい。
# `Communication interfaces Ethernet` の葉は `Ethernet` で、大文字が1つしかない
# ので NAMES_ITSELF に当たらないが、この群の葉は全部が周辺の名前
# （CAN・I2C・SPI・USART/UART・SDIO・DVP・BLE 5.3 …）なので、群を残すと
# 「Ethernet」だけが他と違う体裁になる（worklist G5）。
CLASSIFYING_GROUPS = ("Communication interface", "Communication interfaces",
                      "Communication Interface")

# **資料の見出しは PDF の折り返しでハイフンが割れる**（`General- purpose I/O`）。
# 証拠（`evidence/product_attributes.label`）は資料の綴りのまま持つのが規則なので、
# 直すのは表示のここだけ。`Three-phase` のように割れていないものは触らない。
SPLIT_HYPHEN = re.compile(r"(?<=[A-Za-z])-\s+(?=[a-z])")


def tidy_label(label: str) -> str:
    """表示用に見出しを整える。**意味は変えず、資料側の崩れだけ畳む。**"""
    return re.sub(r"\s{2,}", " ", SPLIT_HYPHEN.sub("-", label)).strip()


def leaf_of(label: str, group: str) -> str:
    """群の名前を剥がした見出し。剥がすと分からなくなるものは剥がさない。

    比較表の見出し列は2段組みで、同じ群の行が固まって並ぶ。`Communication
    interface` が全行に付くのは読みにくいだけなので落とす（worklist の F-20）。
    """
    label, group = tidy_label(label), tidy_label(group)
    if not group or not label.startswith(group):
        return label
    leaf = label[len(group):].strip()
    if not leaf:
        return label
    return leaf if NAMES_ITSELF.search(leaf) or group in CLASSIFYING_GROUPS else label


# 固定列と同じ事実を言い直しているだけの属性。**いまは当たらない**——
# 英語版の `General- purpose I/O` が同義語表に無くて昇格せず、比較表に `GPIO` と
# 同じ値で2行並んでいた件は F-58 で証拠側を直した（属性そのものが消えた）。
# 同じ形の重複が別の綴りで再発したときの歯止めとして残す。**値が全型番で
# 一致するときだけ**落とす——違っていればそれは見せるべき差なので残す。
RESTATES = {"general_purpose_i_o": "gpio_count"}


# この表に並べる USART の数。全部は要らない——SWD と USART1 が分かれば足り、
# USART1 が無いときの逃げ場が1つ見えればよい。
USART_LIMIT = 2


def usart_choice(default: dict[tuple[str, str], set[str]],
                 role: str) -> list[tuple[str, set[str]]]:
    """既定経路に出ている USART を、USART1 を先頭に番号順で最大2つ。"""
    found = {peripheral: pads for (peripheral, r), pads in default.items()
             if r == role and USART.match(peripheral) and pads}

    def rank(name: str) -> tuple[int, int]:
        number = int(name[len("USART"):])
        # USART1 が既定にあるならそれが答。無いときだけ番号の小さい順。
        return (0 if number == 1 else 1, number)

    return [(name, found[name]) for name in sorted(found, key=rank)[:USART_LIMIT]]


def notes_for(pad: str, defaults: dict[str, set[str]],
              everything: dict[str, set[str]]) -> str:
    """pin 表の Notes 欄。debug と UART の pad に印を付ける。

    綴りではなく (peripheral, role) で見る——`DIO` と `SWDIO`、`UART_TX` と
    `TX1` と `USART1_TX` は同じもの。**USART は instance を添える**
    （`UART TX (USART2)`）——どこに繋ぐかを決めるとき、TX であることと同じだけ
    どの USART かが要る。
    """
    pairs = {signal_vocabulary.split(name)
             for name in defaults.get(pad, set())} - {None}
    notes = []
    for peripheral, role in sorted(pairs):
        if (peripheral, role) in (("SDI", "SWDIO"), ("SDI", "SWCLK")):
            notes.append(role)
        elif USART.match(peripheral) and role in ("TX", "RX"):
            notes.append(f"UART {role} ({peripheral})")
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
    leaves: dict[str, str] = {}
    # **資料が並べた順に出す。** 比較表は関連する行を固めて組んでいるので、
    # 属性名の順に並べ替えると読みにくい。型番ごとに持つ行が違うので、
    # 「その属性がいちばん早く出てくる位置」で並べる——後の型番にしか無い行を
    # 末尾に足していくと、そこだけ資料の並びから外れる（worklist の F-23）。
    rank: dict[str, int] = {}
    seen: list[str] = []
    for r in data.attributes:
        if r["part_number"] not in by_part:
            continue
        attribute = r["attribute"]
        by_part[r["part_number"]][attribute] = r["value"]
        label = r.get("label") or r["label_en"] or r["label_zh"]
        group = r.get("group") or ""
        labels.setdefault(attribute, label)
        leaves.setdefault(attribute, leaf_of(label, group))
        # `order` を持たない古い表でも組めるようにする。無ければ出現順が残る。
        position = int(r.get("order") or 0)
        rank[attribute] = min(rank.get(attribute, position), position)
        if attribute not in seen:
            seen.append(attribute)
    order = sorted(seen, key=lambda a: (rank[a], seen.index(a)))
    # 群を剥がすと別の行と同じ名前になることがある（`ADC/TKey Units` と
    # `HSADC Units`）。**そのときは剥がさない。**
    collisions = {leaf for leaf in leaves.values()
                  if list(leaves.values()).count(leaf) > 1}
    display = {a: labels[a] if leaves[a] in collisions else leaves[a] for a in leaves}

    def head(part: str) -> str:
        pkg = next(p["package"] for p in products if p["part_number"] == part)
        # **型番から、その型番の pin map へ。** ここは「どれにするか」を決める表で、
        # 決めた次の問いは必ず「その足はどうなっているか」になる（worklist G6）。
        return (f"[{part[:8]}&#8203;{part[8:]}]({VIEWER}?chip={part})"
                f"&#8203;({pkg})")

    header = ["| | " + " | ".join(head(p) for p in parts) + " |",
              "|---|" + "---|" * len(parts)]
    # **`Flash` と `Code FLASH (bytes)` は別の事実。** 比較表が両方を書く family
    # では、`catalog/products.flash_bytes` は**零等待領域**で、比較表の
    # `Code FLASH` が総容量（CH32V307 は 256K と 480K。F-14）。同じ表に数字だけ
    # 並ぶと矛盾に見えるので、両方が出るときだけ何のことか名前に足す（G10）。
    total_flash = any(a.startswith("code_flash") for a in seen)
    fixed = [("Flash (zero-wait)" if total_flash else "Flash", "flash_bytes"),
             ("SRAM", "sram_bytes"),
             ("GPIO", "gpio_count"), ("Temperature", "temperature")]
    prod_by_part = {p["part_number"]: p for p in products}
    shown_fixed: dict[str, list[str]] = {}
    body: list[tuple[str, list[str]]] = []
    for title, field in fixed:
        values = [human_bytes(prod_by_part[p].get(field, "")) if "bytes" in field
                  else (prod_by_part[p].get(field, "") or "-") for p in parts]
        if any(v not in ("", "-") for v in values):
            shown_fixed[field] = values
            body.append((f"**{title}**", values))
    for attr in order:
        values = [md_escape(by_part[p].get(attr, "-") or "-") for p in parts]
        restated = shown_fixed.get(RESTATES.get(attr, ""))
        if restated is not None and [md_escape(v) for v in restated] == values:
            continue
        label = tidy_label(display.get(attr, labels.get(attr, attr)))
        if attr.startswith("code_flash"):
            label = "Code FLASH, total (bytes)"
        body.append((md_escape(label), values))

    def table(rows: list[tuple[str, list[str]]]) -> list[str]:
        return header + [f"| {label} | " + " | ".join(values) + " |"
                         for label, values in rows]

    # **選ぶために要るのは、型番どうしで違う行だけ。** 同じ値が並ぶ行は
    # 「この series は何か」であって「どれにするか」ではないので、差のある行を
    # 先に出し、全仕様は畳んでおく（worklist G6。CH32V307 の比較表は29行あって
    # 差があるのは3行）。差が無い series では畳まずそのまま出す。
    differing = [row for row in body if len(set(row[1])) > 1]
    out = [f"### {series['series']} product comparison", ""]
    if differing and len(differing) < len(body):
        out += [f"Only the {len(differing)} rows that differ between these "
                f"{len(parts)} products; the other {len(body) - len(differing)} "
                "are the same for all of them.", ""]
        out += table(differing)
        out += ["",
                f"<details><summary>All {len(body)} rows</summary>", ""]
        out += table(body)
        out += ["", "</details>"]
    else:
        out += table(body)
    out.append("")
    return out
FEATURES = ("ADC", "I2C", "SPI", "SYS", "TIM", "UART", "USB")


def filter_links(series: str) -> str:
    """The filterable pin-function viewer, pre-filtered per feature."""
    links = [f"[ALL]({VIEWER}?chip={series})"]
    links += [f"[{f}]({VIEWER}?chip={series}&features={f})" for f in FEATURES]
    return "Pin functions (filterable): " + " ".join(links)


def pin_map_section(data: Data, series: dict, collapse: bool = False) -> list[str]:
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
    # datasheet が pad 名に括弧で添える GPIO の別名（CH32M007 の `LO1 (PA0)`）。
    # pin_functions では `route=alias` の行。pad 名の隣に資料どおり括弧で出す。
    alias = {fn["pad"]: fn["signal"] for part in parts
             for fn in data.fns_by_part[part] if fn["route"] == "alias"}
    defaults = default_signals(data, parts[0])
    everything = all_signals(data, parts[0])

    def head(part: str) -> str:
        package = next(p["package"] for p in products if p["part_number"] == part)
        return (f"[{part[:8]}&#8203;{part[8:]}]({VIEWER}?chip={part})"
                f"&#8203;({package})")

    rows = ["| Pin name | Type | " + " | ".join(head(p) for p in parts)
            + " | Notes |",
            "|---|---|" + "---|" * len(parts) + "---|"]
    for pad in pads:
        type_counter = types.get(pad)
        pin_type = type_counter.most_common(1)[0][0] if type_counter else ""
        cells = [per_part[p].get(pad, "-") for p in parts]
        shown = f"{pad} ({alias[pad]})" if pad in alias else pad
        rows.append(f"| {md_escape(shown)} | {md_escape(pin_type)} | "
                    + " | ".join(cells)
                    + f" | {notes_for(pad, defaults, everything)} |")
    out = [f"### {series['series']} pin map", "", filter_links(series["series"]), ""]
    # **series が複数ある family では pin map を畳む。** CH32V307 の README は
    # 1,064行のうち 818行（77%）が4つの pin map で、目次代わりに読める長さでは
    # なかった。畳めば「どの型番か」までが1画面に収まり、足の話は viewer が
    # 主導線になる（上の filter links はたたまない。worklist G6）。
    if collapse:
        out += [f"<details><summary><b>{series['series']} pin map</b> "
                f"({len(pads)} pads x {len(parts)} products)</summary>", ""]
        out += rows
        out += ["", "</details>", ""]
    else:
        out += rows + [""]
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
            # `alias` は機能ではなく pad の GPIO 名（`LO1 (PA0)`）。pin map の側で出す。
            if fn["route"] not in ("main", "alias"):
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
    """Errata rows for this family's series, from evidence/errata.csv."""
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
    # **節名は中身を言う。** `Pinouts` は「pin 配置」全般に読めるが、この節が
    # 持っているのは封装ごとの外形図と datasheet へのリンクだけで、
    # どの足が何かは下の `Pin maps & alternate functions`（worklist G6）。
    out = ["## Packages & pinout drawings", "",
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


def quick_start_section(data: Data, family: str) -> list[str]:
    """最初に触る人が要るもの——**どうやって書き込むか**と、debug/serial のpad。

    書き込み方式は `index/features.csv` の SDI の行が持つ。CH32V003 系は1線式、
    CH32V20x 系は2線式で、**線数が違うと配線が違う**ので最初に要る
    （worklist の A8）。見出しの綴りは版で揺れるので `features` 列の原文から
    線数を読む。
    """
    tags = [r for r in data.feature_tags
            if r["family"] == family and r["tag"] == "SDI"]
    if not tags:
        return []
    wires = sorted({("1-wire" if "1-wire" in r["features"] else
                     "2-wire" if "2-wire" in r["features"] else "")
                    for r in tags} - {""})
    out = ["## Quick start", ""]
    if wires:
        out += [f"Programming and debug: **{' / '.join(wires)} SDI** "
                "(WCH-Link, `Serial Debug Interface`).", ""]
    out += roles_section(data, family, "###")
    return out


def reference_section(data: Data, family: str) -> list[str]:
    """アドレス空間の入口。`memory_map.csv` の記憶域とバスだけを出す。

    周辺の番地は 700 行近くあって頁に置くものではないので、**FLASH と SRAM と
    バスの先頭**——linker script を書くときに要るぶん——に絞る。
    `link-origin` は linker script が実際に使う先頭で、ヘッダーの `FLASH_BASE`
    とは別の窓口を指すことがある（CH32V307 は 0x08000000 と 0x00000000）。
    """
    rows = [r for r in data.memory_map
            if r["family"] == family and r["kind"] in ("memory", "bus", "link-origin")]
    if not rows:
        return []
    out = ["## Reference", "", "### Address map", "",
           "| Region | Base | Kind |", "|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["kind"], r["base_address"])):
        note = f" ({r['condition']})" if r["condition"] else ""
        out.append(f"| {r['region']}{note} | `{r['base_address']}` | {r['kind']} |")
    out += ["",
            "`link-origin` is what the EVT linker scripts use; the `memory` row "
            "for FLASH is the address the device header states. Both windows are "
            "real -- CH32V307 answers at `0x08000000` and at `0x00000000`.", "",
            "Peripheral base addresses are in "
            "[memory_map.csv](https://github.com/ch32-riscv-ug/ch32-device-data"
            "/blob/main/evidence/memory_map.csv); interrupt numbers in "
            "[interrupts.csv](https://github.com/ch32-riscv-ug/ch32-device-data"
            "/blob/main/evidence/interrupts.csv).", ""]
    return out


def eval_board_lines(data: Data, family: str) -> list[str]:
    """評価ボードの資料。**EVT 同梱**なので Documents 節の中に置く。"""
    rows = [r for r in data.eval_boards if r["family"] == family]
    if not rows:
        return []
    # `repository` は families.csv の列（series.csv には無い）。
    repo = next((f.get("repository") for f in data.families
                 if f["family"] == family and f.get("repository")), None)
    base = f"https://github.com/{repo}/blob/main" if repo else None
    papers = [r for r in rows if r["kind"].startswith(("board-manual", "schematic"))]
    boards = [r for r in rows if r["kind"].startswith("board")
              and not r["kind"].startswith("board-manual")]
    out = ["### Evaluation boards", ""]
    for r in sorted(papers, key=lambda r: r["kind"]):
        name = r["path"].rsplit("/", 1)[-1]
        # 資料の名前に空白と中文が入る（`CH32V20x Evaluation Board Reference-EN.pdf`、
        # `CH32V20x评估板说明书.pdf`）。素で埋めると Markdown のリンクが切れる。
        link = urllib.parse.quote(r["path"])
        out.append(f"- {r['kind']}: "
                   + (f"[{name}]({base}/{link})" if base else f"`{r['path']}`"))
    if boards:
        listed = ", ".join(f"`{r['board']}`" for r in sorted(boards,
                                                            key=lambda r: r["board"]))
        out += ["", f"{len(boards)} board schematics under `EVT/PUB/SCHPCB/`: "
                    f"{listed}", ""]
    return out


def synced_line(data: Data, family: str) -> list[str]:
    """いつの原典から作ったか（worklist の D4）。U5（原典に届かない人）が最初に見る。

    `catalog/sources.csv` が持つ mirror の commit と日付を出す。生成時刻は出さない
    （冪等性——入力が同じなら出力も同じ、を保つため。sources.csv も同じ方針）。
    """
    row = next((r for r in data.sources if r["family"] == family), None)
    if not row or not row.get("commit"):
        return []
    date = row["committed_at"][:10]
    short = row["commit"][:7]
    return [f"*Generated from the mirror at commit "
            f"[`{short}`](https://github.com/{row['repository']}/tree/{row['commit']}) "
            f"({date}). Newer PDFs may exist upstream; see Documents below.*", ""]


# 冒頭のジャンプ行に出す節。(見出し文, 出す名前)。**その README に実際に
# ある見出しだけ**を出すので、Errata の無い family には Errata が出ない。
NAV = (("Product comparison", "Choose a part"),
       ("Pin maps & alternate functions", "Pin maps"),
       ("Errata", "Errata"),
       ("EVT examples", "Examples"),
       ("Documents", "Documents"),
       ("Address map", "Address map"))


def anchor(heading: str) -> str:
    """GitHub が見出しに振る id。小文字化し、英数と `-`・`_` 以外を落として空白を `-` に。"""
    kept = "".join(c for c in heading.lower() if c.isalnum() or c in " -_")
    return kept.replace(" ", "-")


def nav_line(body: list[str], family: str, data: Data) -> list[str]:
    """節へのジャンプ行。長い README で、上から読まずに済むようにするもの。

    **見出しの一覧から作る。** 節を足したり名前を変えたりしたときに、ここだけ
    古くなるのを避けるため（worklist G6）。
    """
    present = {line.lstrip("#").strip() for line in body if line.startswith("#")}
    links = [f"[{shown}](#{anchor(heading)})"
             for heading, shown in NAV if heading in present]
    series = data.family_series(family)
    if series:
        links.insert(1, f"[Pin viewer]({VIEWER}?chip={series[0]['series']})")
    # 1つしか行き先が無いなら案内にならない（WCH-common は Documents だけ）。
    return [" &middot; ".join(links), ""] if len(links) > 1 else []


def render(data: Data, family: str) -> str:
    # **節の順は U1（初めて触る人）→ U2 → U3。** 以前は U3（開発中の人）向けに
    # Series・Debug defaults・Documents が先に来ていた。最初に触る人が要るのは
    # 「どう書き込むか」と「どの型番か」で、資料の一覧はその後（worklist の B4）。
    lines = [f"# {family}", "", NOTICE, ""]
    lines += synced_line(data, family)
    body: list[str] = []
    lines, out = body, lines  # 以降は body に積み、最後に nav を挟んで戻す
    lines += quick_start_section(data, family)
    lines += series_section(data, family)
    if data.family_series(family):
        lines += ["## Product comparison", ""]
        for s in data.family_series(family):
            lines += comparison_section(data, s)
    lines += pinout_reference(data, family)
    if data.family_series(family):
        # **pin 表は silicon の機能の和で、型番の周辺一覧ではない。** datasheet が
        # 表の直前でそう断っている（`所有功能，不涉及具体型号产品`）——同じ pinout を
        # 共有する型番は同じ pad 行を読むので、USART を3つしか持たない CH32V303CBT6 の
        # 欄にも UART8 の pad が並ぶ。`tools/check_counts.py` は表とpinの数を
        # 突き合わせているが、**読む人にはどこにも書いていなかった**（worklist G2）。
        lines += ["## Pin maps & alternate functions", "",
                  "> [!NOTE]",
                  "> These are the **pin-table superset**: the datasheet prints one "
                  "pad table for every product that shares a pinout, so a pad row "
                  "does not mean this part has the peripheral. Use the product "
                  "comparison table above for what a given part number contains.",
                  ""]
    collapse = len(data.family_series(family)) > 1
    for s in data.family_series(family):
        lines += pin_map_section(data, s, collapse)
        lines += functions_section(data, s)
    lines += remap_section(data, family)
    lines += block_diagrams(data, family)
    lines += errata_section(data, family)
    lines += evt_examples_section(data, family)
    lines += documents_section(data, family)
    lines += eval_board_lines(data, family)
    lines += reference_section(data, family)
    lines += extras_section(family)
    lines += ["---",
              "Data: [ch32-device-data](https://github.com/ch32-riscv-ug/"
              "ch32-device-data) (evidence/ and index/ -- each value carries its evidence "
              "and confidence there).", ""]
    return "\n".join(out + nav_line(body, family, data) + body)


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


# 「Find by feature」の分類。**選ぶときに効く軸**でまとめる。
# ここに無いタグが現れたら生成を落とす（分類の穴を黙って作らないため）。
FEATURE_CATEGORIES = (
    ("Connectivity", ("USB", "USBD", "USBFS", "USBHS", "USBSS", "USB-PD",
                      "CAN", "ETHERNET", "USART", "UART", "I2C", "I3C", "SPI",
                      "I2S", "SWPMI", "SIDO", "SERDES", "UHSIF", "PIOC")),
    ("Analog", ("ADC", "TKey", "HSADC", "DAC", "OPA", "CMP", "DFSDM")),
    ("Motor and power drive", ("GATE-DRIVER", "ISP", "ISINK", "ISOURCE", "QII")),
    ("Display, audio and camera", ("LTDC", "DVP", "ARGB", "GPHA", "SAI")),
    ("Memory and storage", ("MEMORY", "PSRAM", "FMC", "FSMC", "QSPI", "SDIO",
                            "SDMMC")),
    ("Timers", ("TIM", "LPTIM", "SYSTICK", "RTC", "WDG", "IWDG", "WWDG")),
    ("Security", ("RNG", "CRC", "ECDC")),
    ("System", ("CLOCK", "DMA", "EXTI", "GPIO", "PFIC", "SDI", "RESET",
                "POWER", "LDO", "LOW-POWER", "PVD")),
)


def org_profile(data: Data) -> str:
    """The organisation landing page: which series live in which repository.

    The family repositories are named after document families (CH32V20x holds
    V203, V205 and V208), which hides what is inside; this table states it.
    """
    families = load("families")
    # **節の順は用途の順**（worklist G4）。以前は「文書 mirror の一覧」が先頭で、
    # いちばん多い用いられ方である「自分の型番はどこか」がその下にあった。
    # 資料の置き場所は、探しているものが見つかったあとに要るもの。
    mirrors = ["## Device documentation mirrors", "",
               "Where each document family is mirrored. "
               "Repository names follow the document family, not the part number.", "",
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
        mirrors.append(f"| [{f['family']}]({url}) | {series} | {cores} "
                       f"| {f['part_number_count']} | {' '.join(docs)} |")
    # 型番から辿れるように。リポジトリ名は文書ファミリーの名前なので、
    # CH32M007がCH32V006に、CH32M103がCH32L103に入っている等は
    # 型番を知っているだけでは辿り着けない。
    # **型番は viewer への直リンクにする**（G4）——例示だけして行き先が無いと、
    # 読む人はここから型番名をコピーして別の場所を探すことになる。
    find = ["## Find your part", "",
            "Look up the series (the first 8 characters of a part number). "
            "The example part numbers open that part's pin map.", "",
            "| Series | Repository | Products | Example part numbers |",
            "|---|---|---|---|"]
    for s in data.series:
        parts = [p["part_number"] for p in data.products
                 if p["series"] == s["series"]]
        shown = ", ".join(f"[{n}]({VIEWER}?chip={n})" for n in parts[:3])
        if len(parts) > 3:
            shown += f", [… all {len(parts)}]({VIEWER}?chip={s['series']})"
        url = f"https://github.com/ch32-riscv-ug/{s['family']}"
        find.append(f"| **{s['series']}** | [{s['family']}]({url}) "
                    f"| {len(parts)} | {shown} |")

    viewer = ["## Pin-function viewer", "",
              f"**[Pin and alternate-function viewer]({VIEWER})** -- every part "
              "and every series in one page: pad x function matrix, remap "
              "selector values and AF numbers, filterable by function and "
              "shareable by URL.", "",
              f"- by series: `{VIEWER}?chip=CH32V307`",
              f"- by part: `{VIEWER}?chip=CH32V307VCT6`",
              f"- one function: `{VIEWER}?chip=CH32V307&features=UART`", ""]

    # 機能から辿れるように（worklist の B5）。`feature_tags.csv` は datasheet の
    # 機能説明章の節見出しから作ったタグ（A6）で、series 単位。比較表が型番単位で
    # 裏付けるものは precision=part、節見出しだけのものは precision=datasheet。
    # **印は series ごと。** `precision` は (tag, series) の性質で、tag の性質では
    # ない。tag 名に付けていたときは「1つでも datasheet 粒度なら feature 全体に印」
    # になり、**どの series が型番単位で裏付けられているのか読み取れなかった**
    # （55タグ中23に印が付き、うち7タグは part と datasheet が混在。worklist G3）。
    #
    # **子タグは親にも足す。** `curated/feature-tags.json` の註が言うとおり
    # 「USB が使えるか」で探す人と「USBHS が要る」人の両方に答えるための親子だが、
    # 以前は子を `continue` で落とすだけで親に足しておらず、**`USB` は
    # `parent` が自分自身なので表から丸ごと消えていた**（worklist G7）。
    by_tag: dict[str, dict[str, set[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(set))
    confirmed: set[tuple[str, str]] = set()
    stated: set[tuple[str, str]] = set()
    for r in data.feature_tags:
        for tag in {r["tag"], r["parent"] or r["tag"]}:
            by_tag[tag][r["family"]].add(r["series"])
            stated.add((tag, r["series"]))
            if r["precision"] == "part":
                confirmed.add((tag, r["series"]))
    child_of = {r["tag"]: r["parent"] for r in data.feature_tags
                if r["parent"] and r["parent"] != r["tag"]}
    every = {r["series"] for r in data.series}

    feature: list[str] = []
    if by_tag:
        uncategorised = sorted(set(by_tag) - {t for _, tags in FEATURE_CATEGORIES
                                              for t in tags})
        if uncategorised:
            raise SystemExit(
                f"build_readme: 分類の無い feature タグ {uncategorised}"
                " -- FEATURE_CATEGORIES に足すこと")

        def row(tag: str) -> str:
            shown = f"{child_of[tag]} / {tag}" if tag in child_of else tag
            if by_tag[tag].keys() and {s for f in by_tag[tag]
                                       for s in by_tag[tag][f]} == every:
                return f"| **{shown}** | every series |"
            cells = []
            for family in sorted(by_tag[tag]):
                names = ", ".join(
                    name + ("" if (tag, name) in confirmed else "\\*")
                    for name in sorted(by_tag[tag][family]))
                url = f"https://github.com/ch32-riscv-ug/{family}"
                cells.append(f"{names} ([{family}]({url}))")
            return f"| **{shown}** | {'; '.join(cells)} |"

        # **選定に効く順。** 全 series が持つ機能は「どれを選ぶか」を決めないので
        # 畳み、少数の series にしかない機能を上に出す（worklist G7）。
        def covers(tag: str) -> int:
            return len({s for f in by_tag[tag] for s in by_tag[tag][f]})
        common = sorted(t for t in by_tag if covers(t) == len(every))
        feature += ["## Find by feature", "",
                    "Which series have a given peripheral, from the feature "
                    "chapter of each datasheet, grouped by what a choice usually "
                    "turns on. A series marked \\* is tagged at datasheet "
                    "granularity (the whole datasheet lists the feature; the "
                    "comparison table does not confirm it for that series' "
                    "parts); an unmarked series is confirmed per part. "
                    "Counts per part number are in "
                    "[`index/capabilities.csv`](https://github.com/ch32-riscv-ug/"
                    "ch32-device-data/blob/main/index/capabilities.csv).", ""]
        for name, tags in FEATURE_CATEGORIES:
            listed = sorted((t for t in tags if t in by_tag and t not in common),
                            key=lambda t: (covers(t), t))
            if not listed:
                continue
            feature += [f"### {name}", "", "| Feature | Series (repository) |",
                        "|---|---|"] + [row(t) for t in listed] + [""]
        if common:
            feature += [f"<details><summary>On every series "
                        f"({len(common)} features)</summary>", "",
                        "| Feature | Series (repository) |", "|---|---|"]
            feature += [row(t) for t in common]
            feature += ["", "</details>", ""]

    lines = [ORG_INTRO, NOTICE, ""] + find + [""] + feature + viewer + mirrors

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
    if args.out:
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
