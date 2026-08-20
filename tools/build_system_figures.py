#!/usr/bin/env python3
"""シリーズごとの構成図を tables/ から生成する（SVG）。

WCHの製品ページにある「系统框图」風のまとめ図を、こちらのデータから組み立て
ます。手作りの画像と違い、全シリーズ分が揃い、値を直せば図も追従します。SVG
なので差分も読めます。

  <FAMILY>/image/system_<SERIES>.svg

値はシリーズ内の全型番を集約します。型番で違う値は範囲（`6-18`）で示し、
数値でないものは併記します。データが無い項目は描きません。

実行: uv run python tools/build_system_figures.py [--family CH32V003]
"""

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent

WIDTH = 760
PAD = 16
CARD_FILL = "#ffffff"
CARD_LINE = "#c8ccd2"
INK = "#1f2328"
MUTED = "#57606a"
ACCENT = "#0b6bcb"
CHIP_FILL = "#eef3f8"


def load(name):
    with (REPO / "tables" / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def human_bytes(value):
    if not value or not value.isdigit():
        return ""
    size = int(value)
    return f"{size // 1024}K" if size % 1024 == 0 else str(size)


def collapse(values):
    """型番ごとに違う値を1つの表記にまとめる。"""
    values = {v for v in values if v and v not in ("-",)}
    if not values:
        return ""
    if values == {"√"}:
        return "yes"
    numbers = [v for v in values if re.fullmatch(r"\d+", v)]
    if len(numbers) == len(values) and numbers:
        low, high = min(map(int, numbers)), max(map(int, numbers))
        return str(low) if low == high else f"{low}-{high}"
    return "/".join(sorted(values))


def escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text_width(text, size):
    """おおよその文字幅。chipの折り返し計算に使う。"""
    return sum(size * (0.62 if ch.isupper() or ch.isdigit() else 0.52)
               for ch in text) + size * 0.4


def fit(text, size, max_width):
    """箱に収まる文字サイズと文字列。収まらなければ縮め、それでも駄目なら省く。"""
    while size > 10 and text_width(text, size) > max_width:
        size -= 0.5
    while text and text_width(text, size) > max_width:
        text = text[:-1]
        if text_width(text + "…", size) <= max_width:
            text += "…"
            break
    return text, size


def series_facts(series, data):
    """図に描く値を集める。"""
    products = [p for p in data["products"] if p["series"] == series["series"]]
    conditions = [r for r in data["operating"]
                  if series["series"] in r["series"].split(";")]

    def clock():
        for symbol in ("F_MAIN", "F_HCLK", "F_SYSCLK", "F_CORE"):
            hits = [r for r in conditions if r["symbol"].startswith(symbol)
                    and r["max"] and r["max"][0].isdigit()]
            if hits:
                values = sorted({r["max"] for r in hits}, key=float)
                return f"{'/'.join(values)} {hits[0]['unit']}"
        return ""

    def voltage():
        rows = [r for r in conditions
                if r["symbol"] == "V_DD" and r["min"] and r["max"]]
        if not rows:
            return ""
        low = min(float(r["min"]) for r in rows)
        high = max(float(r["max"]) for r in rows)
        return f"{low:g}-{high:g} V"

    metrics = [
        ("Core", f"{series['core']} / {series['isa']}".strip(" /")),
        ("Clock", clock()),
        ("Flash", collapse({human_bytes(p["flash_bytes"]) for p in products})),
        ("SRAM", collapse({human_bytes(p["sram_bytes"]) for p in products})),
        ("GPIO", collapse({p["gpio_count"] for p in products})),
        ("VDD", voltage()),
        ("Temp", collapse({p["temperature"].replace("..", " to ")
                           for p in products})),
    ]
    packages = ", ".join(sorted({p["package"] for p in products}))
    return [(k, v) for k, v in metrics if v], packages


# メトリクスの箱で既に出している項目は、周辺機能から省く
ALREADY_SHOWN = re.compile(r"general[-\s]*purpose i/?o|gpio", re.IGNORECASE)


def tidy_label(text):
    """PDFの行折り返しで割れたラベルを直す（`Advanced- control` → `Advanced-control`）。"""
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"(\w)- (\w)", r"\1-\2", text)


def peripherals(series, data):
    """周辺機能。product_attributes をシリーズ単位に集約する。"""
    of_series = {p["part_number"] for p in data["products"]
                 if p["series"] == series["series"]}
    values = defaultdict(set)
    labels = {}
    for row in data["attributes"]:
        if row["part_number"] not in of_series:
            continue
        values[row["attribute"]].add(row["value"])
        labels.setdefault(row["attribute"], tidy_label(row["label_en"]))
    out = []
    for attribute, found in sorted(values.items()):
        label = labels[attribute] or attribute
        value = collapse(found)
        if not value or ALREADY_SHOWN.search(label):
            continue
        # 型番ごとの差が大きい項目は数を出さない（`Ethernet MAC+10/100M
        # PHY/MAC+10/100MPHY` のような羅列になる）。詳細は比較表にある。
        if value == "yes" or len(value) > 10:
            out.append(label)
        else:
            out.append(f"{label} {value}")
    return out


def render(series, facts, packages, chips):
    """SVGを組み立てる。"""
    columns = 4
    box_w = (WIDTH - PAD * 2 - 8 * (columns - 1)) / columns
    rows = (len(facts) + columns - 1) // columns
    metrics_h = rows * 52
    head_h = 54

    chip_lines, line, used = [], [], 0.0
    for chip in chips:
        w = text_width(chip, 12) + 16
        if used + w > WIDTH - PAD * 2 and line:
            chip_lines.append(line)
            line, used = [], 0.0
        line.append((chip, w))
        used += w + 8
    if line:
        chip_lines.append(line)
    chips_h = (len(chip_lines) * 30 + 24) if chip_lines else 0
    packages_h = 26 if packages else 0
    height = head_h + metrics_h + packages_h + chips_h + PAD

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{height:.0f}" viewBox="0 0 {WIDTH} {height:.0f}" '
        f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">',
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1:.0f}" '
        f'rx="10" fill="{CARD_FILL}" stroke="{CARD_LINE}"/>',
        f'<text x="{PAD}" y="34" font-size="22" font-weight="600" '
        f'fill="{INK}">{escape(series["series"])}</text>',
        f'<text x="{WIDTH - PAD}" y="34" font-size="13" text-anchor="end" '
        f'fill="{MUTED}">{escape(series["part_number_count"])} products</text>',
    ]

    for index, (name, value) in enumerate(facts):
        col, row = index % columns, index // columns
        x = PAD + col * (box_w + 8)
        y = head_h + row * 52
        shown, size = fit(value, 13.5, box_w - 20)
        parts += [
            f'<rect x="{x:.1f}" y="{y}" width="{box_w:.1f}" height="44" rx="6" '
            f'fill="{CHIP_FILL}"/>',
            f'<text x="{x + 10:.1f}" y="{y + 17}" font-size="10.5" '
            f'letter-spacing="0.4" fill="{MUTED}">{escape(name.upper())}</text>',
            f'<text x="{x + 10:.1f}" y="{y + 34}" font-size="{size:g}" '
            f'fill="{INK}">{escape(shown)}</text>',
        ]

    y = head_h + metrics_h
    if packages:
        shown, size = fit(packages, 12, WIDTH - PAD * 2 - 80)
        parts.append(
            f'<text x="{PAD}" y="{y + 14}" font-size="{size:g}" fill="{MUTED}">'
            f'<tspan letter-spacing="0.4">PACKAGES</tspan>  '
            f'<tspan fill="{INK}">{escape(shown)}</tspan></text>')
        y += packages_h
    y += 6
    if chip_lines:
        parts.append(f'<text x="{PAD}" y="{y + 10}" font-size="10.5" '
                     f'letter-spacing="0.4" fill="{MUTED}">PERIPHERALS</text>')
        y += 22
        for line in chip_lines:
            x = PAD
            for chip, w in line:
                parts += [
                    f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="22" '
                    f'rx="11" fill="none" stroke="{CARD_LINE}"/>',
                    f'<text x="{x + w / 2:.1f}" y="{y + 15}" font-size="12" '
                    f'text-anchor="middle" fill="{ACCENT}">{escape(chip)}</text>',
                ]
                x += w + 8
            y += 30
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--family", help="このファミリーだけ生成する")
    args = ap.parse_args()

    data = {"products": load("products"), "attributes": load("product_attributes"),
            "operating": load("operating_conditions")}
    written = 0
    for series in load("series"):
        if args.family and series["family"] != args.family:
            continue
        facts, packages = series_facts(series, data)
        chips = peripherals(series, data)
        dest = (MIRRORS / series["family"] / "image"
                / f"system_{series['series']}.svg")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render(series, facts, packages, chips),
                        encoding="utf-8")
        written += 1
        print(f"   {dest.relative_to(MIRRORS)}  "
              f"({len(facts)}項目 / 周辺{len(chips)}件)")
    print(f"{written} 枚")


if __name__ == "__main__":
    main()
