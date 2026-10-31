#!/usr/bin/env python3
"""索引 index/ を証拠から組む → index/*.csv

証拠（evidence/）は資料の綴りのまま、目録（catalog/）は名前。この索引は
その2つ**だけ**から作る、利用者が引くための表（docs/data-layout.ja.md）。
新しい事実は足さない——ここに証拠に無い行が現れたら、語彙か抽出を直す
（tools/check_tables.py が「索引の行は証拠に戻せる」ことを毎回見る）。

    parts.csv          型番の比較表（U2: 型番を選ぶ）
    pinout.csv         型番 × lead × 機能（U1/U3: この足は何か・この機能はどの足か）
    routes.csv         series × remap selector × 値 → 信号と pad（U3: remap 値を選ぶ）
    registers.csv      family × 型 × register × field（U4: ヘッダ生成）
    register_map.csv   family × block × register → 絶対番地
    dma.csv            family × DMA 要求 → channel、peripheral と印の読み
    timers.csv         family × timer。pin に出ているチャネル数を足したもの
    manifest.csv       index/ の全ファイルと sha256（consumer が固定する鍵）

**index/ の下が公開面の全部**（docs/public-surface.ja.md）。目録と証拠のうちそのまま公開する表
（`paths.PUBLISHED`）は、それぞれの生成器が index/ に直接書く。manifest はそれも覆う。

人が絞り込んで読むのは CSV ではなく viewer（pins.html）の仕事。CSV は機械が読む。

`features.csv` と `register_layouts.csv` も索引だが、それぞれ
pipeline/build/build_feature_tags.py と pipeline/extract/rm/extract_registers.py が書く。

証拠と違う値を索引が持つのは1箇所だけ: pin 表の remap 値が RM の格子と
食い違う行（`pin_functions` の basis に `!rm-remap-grid(route=remap-N)`）は格子の
値を採る（worklist F-41。格子はその値の定義そのもので、pin 表は写し）。

実行:
    uv run pipeline/build/build_index.py [--only pinout,routes,...] [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

import paths  # noqa: E402
import signal_vocabulary  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline" / "extract" / "rm"))
from extract_dma_requests import REMAPPED, TYPO, peripheral_of  # noqa: E402  新経路（凍結toolは退役）

# **pad 名には役割が継ぎ足されることがある**（`PA0-WKUP`・`PC13-TAMPER-RTC`）。
# GPIO としての読み（port と番号）はその装飾を落として取る。
GPIO_PAD = re.compile(r"^P(?P<port>[A-H])(?P<gpio>\d{1,2})(?:[-_]|$)")
GPIO_NAME = re.compile(r"P[A-H]\d{1,2}")
GRID_VALUE = re.compile(r"!rm-remap-grid\(route=(?P<route>remap-\d+)\)")

PINOUT_COLUMNS = ["part_number", "series", "family", "pin", "pad", "port", "gpio", "kind",
                  "peripheral", "role", "signal", "route", "selector", "value", "af", "confidence", "basis"]
ROUTES_COLUMNS = ["series", "selector", "controller", "register", "bits", "value", "peripheral", "role",
                  "signal", "pad", "port", "gpio", "confidence", "basis"]
REGISTERS_COLUMNS = ["family", "type", "register", "offset", "width_bits", "count",
                     "field", "define", "kind", "of_field", "bits", "mask", "value",
                     "description", "access", "reset", "confidence", "basis",
                     "access_confidence", "access_basis"]
MAP_COLUMNS = ["family", "block", "type", "register", "address", "offset", "width_bits",
               "count", "confidence", "basis"]
DMA_COLUMNS = ["family", "variant", "dma", "channel", "request_id", "peripheral", "request",
               "remap", "spelled", "note", "confidence", "basis"]
TIMERS_COLUMNS = ["family", "timer", "kind", "counter_width_bits", "channels", "complementary",
                  "update_vector", "condition", "confidence", "basis"]

CONFIDENCE_ORDER = {"confirmed": 0, "reference": 1, "conflict": 2, "": 3}


def weakest(*values: str) -> str:
    """複数の証拠行を1行に畳むときの confidence（いちばん弱いもの）。"""
    return max((v for v in values if v), key=lambda v: CONFIDENCE_ORDER.get(v, 5), default="")


def pin_key(pin: str) -> tuple:
    return (0, int(pin)) if pin.isdigit() else (1, pin)


def gpio_of(pad: str, alias: str = "") -> tuple[str, str]:
    m = GPIO_PAD.match(pad) or GPIO_PAD.match(alias)
    return (m.group("port"), m.group("gpio")) if m else ("", "")


# ---------------------------------------------------------------- pinout

def pinout_rows(products: list[dict], pins: list[dict], functions: list[dict],
                remap_routes: list[dict]) -> tuple[list[dict], collections.Counter]:
    """(pinout の行, 語彙で覆えなかった {(datasheet, signal): 行数})。

    tools/check_tables.py が同じ計算をして、覆えない数が増えていないかを見る。
    """
    catalogue = {p["part_number"]: p for p in products}
    by_pad: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for fn in functions:
        by_pad[(fn["part_number"], fn["pad"])].append(fn)
    # **GPIO 名を括弧で添えられた pad の、GPIO としての読み。** CH32M007/M103 の
    # ゲートドライバ出力は pad 名が `LO1` で、資料が `(PA0)` と別名を添える
    # （`pin_functions` では `route=alias` の行）。`port`/`gpio` はそこから採る。
    alias_of = {(fn["part_number"], fn["pad"]): fn["signal"]
                for fn in functions if fn["route"] == "alias"}
    # **機能名の pad が、GPIO 名を route の無い機能として持つもの。** `OSC_IN` の行に
    # `PD0`（route 空）と書く datasheet がある（L103・V20x/V30x・V103・V407 ほか 81 pad）。
    # その pad の GPIO としての読みなので `port`/`gpio` に採る——ただし**同じ型番の別の lead が
    # その GPIO を名乗っていない**ときだけ。100ピン封装では `PD0` が独立した lead（V307VCT6 の
    # 81番）で、`OSC_IN`（12番）の `PD0` は別の足の話なので、採ると1つの GPIO を2本が名乗る。
    # 同じ lead に `OSC_IN` と `PD0` が並ぶ形（V203CCT6 の5番）は同じ足なので採ってよい。
    leads_of: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for pin in pins:
        port, gpio = gpio_of(pin["pad"], alias_of.get((pin["part_number"], pin["pad"]), ""))
        if port:
            leads_of[(pin["part_number"], f"P{port}{gpio}")].add(pin["pin"])
    lead_of = {(p["part_number"], p["pad"]): p["pin"] for p in pins}
    for fn in functions:
        key = (fn["part_number"], fn["pad"])
        if (fn["route"] == "" and key not in alias_of and not GPIO_PAD.match(fn["pad"])
                and GPIO_NAME.fullmatch(fn["signal"])
                and leads_of[(fn["part_number"], fn["signal"])] <= {lead_of.get(key)}):
            alias_of[key] = fn["signal"]
    # remap selector と値: (series, signal, pad) → {value: [selector]}
    selectors: dict[tuple[str, str, str], dict[str, list[str]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for r in remap_routes:
        selectors[(r["series"], r["signal"], r["pad"])][r["value"]].append(r["selector"])

    rows: list[dict] = []
    unresolved: collections.Counter = collections.Counter()
    for pin in pins:
        part, pad = pin["part_number"], pin["pad"]
        product = catalogue.get(part)
        if not product:
            continue
        port, gpio = gpio_of(pad, alias_of.get((part, pad), ""))
        base = {"part_number": part, "series": product["series"], "family": product["family"],
                "pin": pin["pin"], "pad": pad, "port": port, "gpio": gpio, "kind": pin["kind"]}
        emitted = 0
        for fn in by_pad.get((part, pad), []):
            if fn["route"] == "alias":
                continue
            signal = fn["signal"]
            # **pad 自身の名前は役割ではない。** `PA9` の主機能が `PA9`、`VSS` の
            # 主機能が `VSS` と書かれるのは、その pad が何であるかを言っているだけ。
            # ただし `NRST`・`OSC_IN`・`BOOT0` のように自分の名前が機能そのもの
            # である pad は、リセット直後に生きている機能として索引に要る。
            if fn["route"] == "main" and signal == pad:
                if pin["kind"] == "power" or signal_vocabulary.is_pad_name(signal):
                    continue
            elif signal_vocabulary.is_pad_name(signal):
                continue
            if signal in signal_vocabulary.NOT_A_ROLE:
                continue
            found = signal_vocabulary.roles(signal)
            if not found:
                unresolved[(fn.get("datasheet", ""), signal)] += 1
                continue
            route = fn["route"]
            grid = GRID_VALUE.search(fn["basis"])
            if grid:
                route = grid.group("route")  # 格子の値を採る（F-41）
            value = ""
            if route.startswith("remap-"):
                value = route[len("remap-"):]
            elif route in ("default", "main"):
                value = "0"
            chosen = selectors.get((product["series"], signal, pad), {}).get(value, []) if value else []
            af = route[len("af-"):] if route.startswith("af-") else ""
            for peripheral, role in found:
                rows.append({**base, "peripheral": peripheral, "role": role, "signal": signal,
                             "route": route,
                             "selector": ";".join(sorted(set(chosen))),
                             "value": value if chosen else "",
                             "af": af,
                             "confidence": fn["confidence"], "basis": fn["basis"]})
                emitted += 1
        if not emitted:
            # 機能の行が無い lead（電源・NC・GPIO だけの足）も1行。port+gpio → lead
            # が1表で引けるのはこの行があるから。
            rows.append({**base, "peripheral": "", "role": "", "signal": "", "route": "",
                         "selector": "", "value": "", "af": "",
                         "confidence": pin["confidence"], "basis": pin["basis"]})
    rows.sort(key=lambda r: (r["part_number"], pin_key(r["pin"]), r["pad"],
                             r["peripheral"], r["role"], r["route"], r["signal"]))
    return rows, unresolved


# ---------------------------------------------------------------- routes

def routes_rows(remap_fields: list[dict], remap_routes: list[dict]) -> tuple[list[dict], collections.Counter]:
    fields = {(r["series"], r["selector"]): r for r in remap_fields}
    rows, undecided = [], collections.Counter()
    for r in remap_routes:
        field = fields.get((r["series"], r["selector"]), {})
        pair = signal_vocabulary.split(r["signal"])
        if pair is None:
            undecided[r["signal"]] += 1
        port, gpio = gpio_of(r["pad"])
        rows.append({"series": r["series"], "selector": r["selector"],
                     "controller": field.get("controller", ""),
                     "register": field.get("register", ""), "bits": field.get("bits", ""),
                     "value": r["value"],
                     "peripheral": pair[0] if pair else "", "role": pair[1] if pair else "",
                     "signal": r["signal"], "pad": r["pad"], "port": port, "gpio": gpio,
                     "confidence": r["confidence"], "basis": r["basis"]})
    rows.sort(key=lambda r: (r["series"], r["selector"], int(r["value"]), r["signal"], r["pad"]))
    return rows, undecided


# ---------------------------------------------------------------- registers

# 資料どうしが食い違う field を実機で測った位置（`register_fields` の basis に
# `obr-readback:wch-linke(bits=19:12)` の形で載る）。索引はこれを採る——F-41 で格子の値を
# 採るのと同じ規則で、証拠の行は `conflict` のまま両論と実測を持ち続ける。
MEASURED_BITS = re.compile(r"(?:^|\+)[a-z][a-z0-9-]*:[a-z][a-z0-9-]*\(bits=(?P<bits>\d+(?::\d+)?)\)")


def measured_bits(basis: str) -> str | None:
    """basis が実測の位置を持っていればその bits。

    >>> measured_bits("evt(ch32l103.h)+!rm:CH32L103RM.PDF(bits=19:12)+obr-readback:wch-linke(bits=19:12)")
    '19:12'
    >>> measured_bits("evt(ch32l103.h)+!rm:CH32L103RM.PDF(bits=19:12)") is None
    True
    """
    m = MEASURED_BITS.search(basis)
    return m.group("bits") if m else None


def bits_mask(bits: str) -> str:
    """`19:12` → `0xff000`・`7` → `0x80`。

    >>> bits_mask("19:12"), bits_mask("7")
    ('0xff000', '0x80')
    """
    hi, _, lo = bits.partition(":")
    lo = lo or hi
    return f"{((1 << (int(hi) - int(lo) + 1)) - 1) << int(lo):#x}"


def registers_rows(registers: list[dict], fields: list[dict]) -> list[dict]:
    """register ごとの offset に、その register の bit define を並べる。

    `register_fields.member` は `型.メンバー`（`CAN.sTxMailBox[0].TXMDHR`）で、
    `registers` の (type, register) と同じもの。member が空の define（banner を
    構造体のメンバーに結べなかったもの）は offset 無しで載せる——bit 位置と
    define 名は事実なので落とさない。
    """
    regs = {(r["family"], r["type"], r["register"]): r for r in registers}
    used: set[tuple] = set()
    rows: list[dict] = []
    for f in fields:
        type_name, _, register = f["member"].partition(".")
        # 配列の要素（`AFIO.EXTICR[1]`）は `registers` の配列（`EXTICR`, count=4）
        # の中の1つ。offset は先頭 + 添字 × 幅。
        element = re.fullmatch(r"(?P<name>.+)\[(?P<i>\d+)\]", register)
        key = (f["family"], type_name, element.group("name") if element else register)
        reg = regs.get(key) if f["member"] else None
        if reg is None and element:
            reg = regs.get((f["family"], type_name, register))
            element = None
        if reg is None:
            type_name, register = f["type"], f["member"].partition(".")[2] or f["register"]
            offset = ""
        else:
            used.add(key)
            offset = reg["offset"]
            if element:
                offset = f"{int(reg['offset'], 16) + int(element.group('i')) * int(reg['width_bits']) // 8:#05x}"
        bits, mask = f["bits"], f["mask"]
        adopted = measured_bits(f["basis"]) if f["kind"] == "field" else None
        if adopted:
            bits, mask = adopted, bits_mask(adopted)
        rows.append({"family": f["family"], "type": type_name, "register": register,
                     "offset": offset,
                     "width_bits": reg["width_bits"] if reg else "",
                     "count": reg["count"] if reg else "",
                     "field": f["field"], "define": f["define"], "kind": f["kind"],
                     "of_field": f["of_field"], "bits": bits, "mask": mask,
                     "value": f["value"], "description": f["description"],
                     "access": f["rm_access"], "reset": f["rm_reset"],
                     "access_confidence": f["rm_access_confidence"],
                     # 証拠の列名 `rm_access` を、索引の列名 `access` に読み替える。
                     "access_basis": f["rm_access_basis"].replace("(rm_access=", "(access="),
                     "confidence": f["confidence"], "basis": f["basis"]})
    for key, reg in regs.items():
        if key not in used:
            rows.append({"family": reg["family"], "type": reg["type"], "register": reg["register"],
                         "offset": reg["offset"], "width_bits": reg["width_bits"],
                         "count": reg["count"], "field": "", "define": "", "kind": "register",
                         "of_field": "", "bits": "", "mask": "", "value": "", "description": "",
                         "access": "", "reset": reg["rm_reset"],
                         "confidence": reg["confidence"], "basis": reg["basis"]})
    rows.sort(key=lambda r: (r["family"], r["type"],
                             int(r["offset"], 16) if r["offset"] else 1 << 30, r["register"],
                             int(r["mask"], 16) if r["mask"] else -1, r["define"]))
    return rows


def map_rows(blocks: list[dict], registers: list[dict]) -> list[dict]:
    by_type: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in registers:
        by_type[(r["family"], r["type"])].append(r)
    rows: list[dict] = []
    for b in blocks:
        base = int(b["base_address"], 16)
        regs = by_type.get((b["family"], b["type"]), [])
        if not regs:
            rows.append({"family": b["family"], "block": b["block"], "type": b["type"],
                         "register": "", "address": f"{base:#010x}", "offset": "",
                         "width_bits": "", "count": "",
                         "confidence": b["confidence"], "basis": b["basis"]})
        for r in regs:
            rows.append({"family": b["family"], "block": b["block"], "type": b["type"],
                         "register": r["register"],
                         "address": f"{base + int(r['offset'], 16):#010x}",
                         "offset": r["offset"], "width_bits": r["width_bits"], "count": r["count"],
                         "confidence": weakest(b["confidence"], r["confidence"]),
                         "basis": r["basis"]})
    rows.sort(key=lambda r: (r["family"], int(r["address"], 16), r["block"], r["register"]))
    return rows


# ---------------------------------------------------------------- dma / timers

def dma_rows(requests: list[dict]) -> list[dict]:
    rows = []
    for r in requests:
        spelled = r["request"]
        text, remap = spelled, ""
        if text.endswith("*"):
            remap, text = "selectable", text.rstrip("*")
        m = REMAPPED.match(text)
        if m:
            remap, text = ("default" if m.group("value") == "0" else "remap"), m.group("request")
        note = r["note"]
        if r["request_id"]:
            note = (note + "; " if note else "") + "DMAMUX: any channel can take this request"
        rows.append({"family": r["family"], "variant": r["variant"], "dma": r["dma"],
                     "channel": r["channel"], "request_id": r["request_id"],
                     "peripheral": peripheral_of(TYPO.get(text, text)),
                     "request": text, "remap": remap, "spelled": spelled, "note": note,
                     "confidence": r["confidence"], "basis": r["basis"]})
    rows.sort(key=lambda r: (r["family"], r["variant"], r["dma"], int(r["channel"] or 0),
                             int(r["request_id"] or 0), r["request"]))
    return rows


def timers_rows(timers: list[dict], pinout: list[dict]) -> list[dict]:
    channels: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for r in pinout:
        if r["peripheral"].startswith("TIM") and r["role"].startswith("CH"):
            channels[(r["family"], r["peripheral"])].add(r["role"])
    rows = []
    for t in timers:
        seen = channels.get((t["family"], t["timer"]), set())
        plain = {c for c in seen if not c.endswith("N")}
        rows.append({**{k: t[k] for k in ("family", "timer", "kind", "counter_width_bits",
                                          "update_vector", "condition", "confidence", "basis")},
                     # **pin に出ている最大のチャネル番号**で、silicon の上限ではない。
                     # 番号は `CH` の**直後の数字だけ**を読む。役目の綴りには番号の後ろに
                     # 続きが付くものがあり（`CH1_ETR` はチャネル1と外部トリガの兼用、
                     # `CH1_3` の `_3` は CH32V407 の remap 変種の番号）、数字を全部
                     # 繋ぐと `CH1_3` が 13 チャネルになる（実測: `CH32V407 TIM1` が
                     # 13 と出ていた。2026-09-15）。
                     "channels": max((int(m.group(1)) for c in plain
                                      if (m := re.match(r"CH(\d+)", c))), default=""),
                     "complementary": "1" if any(c.endswith("N") for c in seen) else ""})
    rows.sort(key=lambda r: (r["family"], r["timer"]))
    return rows


# ---------------------------------------------------------------- parts

# 比較表の属性キー（evidence/product_attributes.attribute。資料の見出しから機械的に
# 作った鍵で family ごとに綴りが違う）→ 比較表の列。**数える規則は持たない**——
# 資料の値（`4`・`1/10`・`√`）をそのまま並べる。同じ列に2属性が当たれば `;` で繋ぐ。
ATTRIBUTE_COLUMNS: dict[str, re.Pattern] = {
    "usart": re.compile(r"^(usart|serial_port|communication_interfaces?_(usart(_uart)?|uart))$"),
    "spi": re.compile(r"^(spi(_i2s)?|communication_interfaces?_spi)$"),
    "i2c": re.compile(r"^(i2c|communication_interfaces?_i2c)$"),
    "can": re.compile(r"^(can|communication_interfaces?_can(_fd)?)$"),
    "usb": re.compile(r"^(usb_device|pdusb_usb(fs|hs|ss).*|pdusb_usb_host|usbhs_include_phy"
                      r"|communication_interfaces?_usb.*|communication_interface_pdusb_usb_host_device)$"),
    "adc": re.compile(r"^(adc|adc_channel.*|adc_tkey_channel.*|adc_tkey_number_of_channels|adc_adc\d_channel)$"),
    "dac": re.compile(r"^dac"),
    "opa": re.compile(r"^(opa|opa\d|opa_cmp)$"),
    "cmp": re.compile(r"^(cmp|cmp\d)$"),
    "timers_advanced": re.compile(r"^(adtm|advanced_control_timer|timer_adtm_16_bit|timer_advanced.*)$"),
    "timers_general": re.compile(r"^(gptm|general_purpose_timer|timer_gptm_.*|timer_general_purpose.*)$"),
    "rtc": re.compile(r"^rtc$"),
    "ethernet": re.compile(r"^(ethernet|communication_interfaces?_ethernet)$"),
}


# 型番の表。目録の型番の列（識別・主要仕様・ordering・掲載 datasheet）に、ピン数・最大クロック・電源電圧・
# 比較表の周辺の数を並べる。**値の列ごとに確度と根拠**を持つ（目録の鍵の表の形）。family・listed_as・
# datasheet は series と目録が決める名前なので確度を持たない。
PARTS_COLUMNS = ["part_number", "series", "family", "package", "pins", "flash_bytes", "sram_bytes",
                 "gpio_count", "clock_max", "vdd_min", "vdd_max", "temperature", "usart", "spi", "i2c",
                 "can", "usb", "adc", "dac", "opa", "cmp", "timers_advanced", "timers_general", "rtc",
                 "ethernet", "packing", "listed_as", "datasheet", "part_number_confidence",
                 "series_confidence", "package_confidence", "pins_confidence", "flash_bytes_confidence",
                 "sram_bytes_confidence", "gpio_count_confidence", "clock_max_confidence",
                 "vdd_min_confidence", "vdd_max_confidence", "temperature_confidence",
                 "usart_confidence", "spi_confidence", "i2c_confidence", "can_confidence",
                 "usb_confidence", "adc_confidence", "dac_confidence", "opa_confidence",
                 "cmp_confidence", "timers_advanced_confidence", "timers_general_confidence",
                 "rtc_confidence", "ethernet_confidence", "packing_confidence", "part_number_basis",
                 "series_basis", "package_basis", "pins_basis", "flash_bytes_basis", "sram_bytes_basis",
                 "gpio_count_basis", "clock_max_basis", "vdd_min_basis", "vdd_max_basis",
                 "temperature_basis", "usart_basis", "spi_basis", "i2c_basis", "can_basis", "usb_basis",
                 "adc_basis", "dac_basis", "opa_basis", "cmp_basis", "timers_advanced_basis",
                 "timers_general_basis", "rtc_basis", "ethernet_basis", "packing_basis"]
PARTS_VALUES = [c for c in PARTS_COLUMNS if not c.endswith(("_confidence", "_basis"))]
PARTS_STATED = [c[:-len("_confidence")] for c in PARTS_COLUMNS if c.endswith("_confidence")]
assert [c for c in PARTS_VALUES if c in ATTRIBUTE_COLUMNS] == list(ATTRIBUTE_COLUMNS)


def joined_basis(rows: list[dict], column: str = "basis") -> str:
    """複数の証拠行の basis を、項を重ねずに `+` で繋ぐ。"""
    terms: dict[str, None] = {}
    for r in rows:
        for term in re.split(r"\+(?![^()]*\))", r.get(column, "")):
            if term:
                terms[term] = None
    return "+".join(terms)


def operating_summary(operating: list[dict], series: str) -> dict[str, tuple[str, str, str]]:
    """{clock_max|vdd_min|vdd_max: (値, 確度, 根拠)}。pipeline/build/build_readme.py と同じ読み方。"""
    rows = [r for r in operating if series in r["series"].split(";")]
    out = {"clock_max": ("", "", ""), "vdd_min": ("", "", ""), "vdd_max": ("", "", "")}
    for prefix in ("F_MAIN", "F_HCLK", "F_SYSCLK", "F_CORE"):
        hits = [r for r in rows if r["symbol"].startswith(prefix)
                and r["max"] and r["max"][0].isdigit()]
        if hits:
            out["clock_max"] = ("/".join(dict.fromkeys(r["max"] for r in hits)) + " " + hits[0]["unit"],
                                weakest(*(r["confidence"] for r in hits)), joined_basis(hits))
            break
    vdd = [r for r in rows if r["symbol"] == "V_DD" and r["min"] and r["max"]]
    if vdd:
        lo = min((r["min"] for r in vdd), key=float)
        hi = max((r["max"] for r in vdd), key=float)
        for column, value, side in (("vdd_min", lo, "min"), ("vdd_max", hi, "max")):
            chosen = [r for r in vdd if r[side] == value]
            out[column] = (value, weakest(*(r["confidence"] for r in chosen)), joined_basis(chosen))
    return out


def parts_rows(products: list[dict], packages: list[dict], attributes: list[dict],
               operating: list[dict]) -> list[dict]:
    package_of = {p["package"]: p for p in packages}
    attrs: dict[str, dict[str, list[dict]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for a in attributes:
        for column, pattern in ATTRIBUTE_COLUMNS.items():
            if pattern.search(a["attribute"]):
                attrs[a["part_number"]][column].append(a)
    rows = []
    for p in products:
        row = {c: p.get(c, "") for c in PARTS_VALUES}
        for c in PARTS_STATED:
            row[f"{c}_confidence"] = p.get(f"{c}_confidence", "")
            row[f"{c}_basis"] = p.get(f"{c}_basis", "")
        package = package_of.get(p["package"], {})
        row.update(pins=package.get("pin_count", ""),
                   pins_confidence=package.get("pin_count_confidence", ""),
                   pins_basis=package.get("pin_count_basis", ""))
        for column, (value, confidence, basis) in operating_summary(operating, p["series"]).items():
            row.update({column: value, f"{column}_confidence": confidence, f"{column}_basis": basis})
        for column in ATTRIBUTE_COLUMNS:
            stated = attrs[p["part_number"]].get(column, [])
            row[column] = ";".join(dict.fromkeys(a["value"] for a in stated))
            row[f"{column}_confidence"] = weakest(*(a["confidence"] for a in stated))
            row[f"{column}_basis"] = joined_basis(stated)
        rows.append(row)
    rows.sort(key=lambda r: r["part_number"])
    return rows


# ---------------------------------------------------------------- manifest

def manifest_files(root: Path) -> list[Path]:
    """manifest が覆うファイル: index/ の CSV と VERSION（README と manifest 自身は除く）。"""
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and (p.suffix == ".csv" or p.name == "VERSION")
                  and p.name != "manifest.csv")


def write_manifest(out: Path | None) -> Path:
    root = out if out is not None else paths.INDEX
    rows = []
    for p in manifest_files(root):
        data = p.read_bytes()
        rows.append({"path": p.relative_to(root).as_posix(), "rows": data.count(b"\n") - 1,
                     "sha256": hashlib.sha256(data).hexdigest()})
    dest = root / "manifest.csv"
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "rows", "sha256"])
        w.writeheader()
        w.writerows(rows)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="作る表（カンマ区切り。既定は全部）")
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else set(paths.INDEX_TABLES)

    def emit(name: str, rows: list[dict], columns: list[str]) -> None:
        dest = paths.index(name, args.out)
        paths.write(dest, rows, columns)
        tally = collections.Counter(r.get("confidence", "-") for r in rows)
        print(f"{dest}: {len(rows)} 行  {dict(tally)}", file=sys.stderr)

    products = paths.load("products")
    pinout: list[dict] = []
    if {"pinout", "timers"} & only:
        pinout, unresolved = pinout_rows(products, paths.load("pins"), paths.load("pin_functions"),
                                         paths.load("remap_routes"))
        if "pinout" in only:
            emit("pinout", pinout, PINOUT_COLUMNS)
            if unresolved:
                names = collections.Counter()
                for (_, signal), n in unresolved.items():
                    names[signal] += n
                print(f"  - 語彙に無い signal {len(names)} 種 / {sum(names.values())} 行"
                      "（pipeline/common/signal_vocabulary.py に規則を足すか、抽出を直す）:", file=sys.stderr)
                for signal, n in names.most_common(15):
                    print(f"      {signal} ×{n}", file=sys.stderr)
    if "routes" in only:
        rows, undecided = routes_rows(paths.load("remap_fields"), paths.load("remap_routes"))
        emit("routes", rows, ROUTES_COLUMNS)
        if undecided:
            print(f"  - peripheral/role を決められない signal: {len(undecided)} 種 "
                  f"{sum(undecided.values())} 行: {dict(undecided.most_common(8))}", file=sys.stderr)
    if "registers" in only:
        emit("registers", registers_rows(paths.load("registers"), paths.load("register_fields")),
             REGISTERS_COLUMNS)
    if "register_map" in only:
        emit("register_map", map_rows(paths.load("register_blocks"), paths.load("registers")), MAP_COLUMNS)
    if "dma" in only:
        emit("dma", dma_rows(paths.load("dma_requests")), DMA_COLUMNS)
    if "timers" in only:
        emit("timers", timers_rows(paths.load("timers"), pinout), TIMERS_COLUMNS)
    if "parts" in only:
        emit("parts", parts_rows(products, paths.load("packages"), paths.load("product_attributes"),
                                 paths.load("operating_conditions")), PARTS_COLUMNS)
    dest = write_manifest(args.out)
    print(f"{dest}: index/ の全ファイルの sha256", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
