#!/usr/bin/env python3
"""データシートから README が参照する画像を切り出す。

必要な画像は tools/check_images.py が定める3種類で、いずれも原典PDFの中に
図として存在します。

  architecture_<SERIES>.png    第1章のシステムブロック図（ベクタ描画）
  pinout_<PART>_<PACKAGE>.png  ピン配置章の図（ベクタ描画。型番が図の見出し）
  package_<PACKAGE>.png        パッケージ章の外形図（埋め込みラスタ）

図はキャプションや見出しの直下にあるため、見出し行の位置から次の見出しまでを
帯として、その中の描画物の外接矩形を切り出して描画します。パッケージ外形図は
チップに依存しないので WCH-common へ、他は各ミラーリポジトリへ書きます。

実行:
    uv run python tools/extract_images.py --dry-run     # 何を作るかだけ表示
    uv run python tools/extract_images.py               # 実際に書き出す
    uv run python tools/extract_images.py --family CH32V003
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent
RESOLUTION = 200

ARCH_CAPTION = re.compile(
    r"(?:Figure|图)\s*[\d.\-]+\s*(?P<scope>.*?)\s*"
    r"(?:System block diagram|system block diagram|系统框图|系统结构框图)")
PINOUT_CHAPTER = re.compile(r"^\d+\.\d+\s+(?:Pinouts?|引脚分布|引脚图)\s*$", re.I)
NEXT_CHAPTER = re.compile(r"^\d+\.\d+\s+\S")
PART_LABEL = re.compile(r"^CH32[A-Za-z0-9]{4,}$")
PACKAGE_HEADING = re.compile(
    r"^\d+\.\d+\s+(?P<package>[A-Z][A-Z0-9_×xX*]{2,})\s*(?:package|封装)", re.I)
FOOTER = 50          # ページ下端の版数・ページ番号の帯
HEADER = 95          # ページ上端のヘッダ
PAD = 6


def load(name):
    with (REPO / "tables" / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lines_of(page):
    """[(top, text)] — 行単位のテキストと縦位置。"""
    words = page.extract_words()
    rows = defaultdict(list)
    for w in words:
        rows[round(w["top"])].append(w)
    out = []
    for top in sorted(rows):
        chunk = sorted(rows[top], key=lambda w: w["x0"])
        out.append((top, " ".join(w["text"] for w in chunk)))
    return out


def region_bbox(page, top, bottom, gap=30):
    """帯 [top, bottom) の**最初の図**の外接矩形。

    図は罫線・曲線・埋め込み画像の塊で、その下に本文や表が続く。素朴に帯全体の
    外接矩形を取ると本文まで飲み込むので、描画物を縦方向の空白で塊に分け、
    最初の塊だけを図とみなす。文字は塊の内側にあるものだけ含める（ピン名や
    ブロック名は図の一部だが、図の下の注記は図ではない）。
    """
    def usable(o):
        if o["top"] < top or o["bottom"] > bottom:
            return False
        if o["bottom"] > page.height - FOOTER or o["top"] < HEADER * 0.5:
            return False
        wide = (o["x1"] - o["x0"]) > page.width * 0.85
        tall = (o["bottom"] - o["top"]) > page.height * 0.7
        return not (wide and tall)          # ページ枠の矩形

    drawings = sorted((o for kind in ("curves", "lines", "rects", "images")
                       for o in getattr(page, kind) if usable(o)),
                      key=lambda o: o["top"])
    if not drawings:
        return None
    cluster = [drawings[0]]
    reach = drawings[0]["bottom"]
    for o in drawings[1:]:
        if o["top"] - reach > gap:
            break
        cluster.append(o)
        reach = max(reach, o["bottom"])
    x0 = min(o["x0"] for o in cluster)
    x1 = max(o["x1"] for o in cluster)
    y0 = min(o["top"] for o in cluster)
    y1 = max(o["bottom"] for o in cluster)
    for ch in page.chars:
        if not usable(ch):
            continue
        cx, cy = (ch["x0"] + ch["x1"]) / 2, (ch["top"] + ch["bottom"]) / 2
        if x0 - 4 <= cx <= x1 + 4 and y0 - 4 <= cy <= y1 + 4:
            x0, x1 = min(x0, ch["x0"]), max(x1, ch["x1"])
            y0, y1 = min(y0, ch["top"]), max(y1, ch["bottom"])
    return (max(0, x0 - PAD), max(top, y0 - PAD),
            min(page.width, x1 + PAD), min(bottom, y1 + PAD))


def clusters_of(page, top, bottom, gap=30):
    """帯の中の図を塊ごとに列挙する。[(x0, top, x1, bottom), ...]"""
    def usable(o):
        if o["top"] < top or o["bottom"] > bottom:
            return False
        if o["bottom"] > page.height - FOOTER or o["top"] < HEADER * 0.5:
            return False
        wide = (o["x1"] - o["x0"]) > page.width * 0.85
        tall = (o["bottom"] - o["top"]) > page.height * 0.7
        return not (wide and tall)

    drawings = sorted((o for kind in ("curves", "lines", "rects", "images")
                       for o in getattr(page, kind) if usable(o)),
                      key=lambda o: o["top"])
    out = []
    current, reach = [], None
    for o in drawings:
        if current and o["top"] - reach > gap:
            out.append(current)
            current, reach = [], None
        current.append(o)
        reach = o["bottom"] if reach is None else max(reach, o["bottom"])
    if current:
        out.append(current)
    boxes = []
    for group in out:
        box = (min(o["x0"] for o in group), min(o["top"] for o in group),
               max(o["x1"] for o in group), max(o["bottom"] for o in group))
        area = (box[2] - box[0]) * (box[3] - box[1])
        # 罫線1本のような塊は図ではない。ただし図が1枚の埋め込み画像として
        # 入っている版（CH32V103のピン配置図）や、十分大きな塊は図とみなす。
        if len(group) < 3 and area < page.width * page.height * 0.03:
            continue
        boxes.append((min(o["x0"] for o in group), min(o["top"] for o in group),
                      max(o["x1"] for o in group), max(o["bottom"] for o in group)))
    return boxes


def with_inner_text(page, box):
    """図の内側にある文字を取り込んだ外接矩形（ピン名・ブロック名は図の一部）。"""
    x0, y0, x1, y1 = box
    for ch in page.chars:
        if ch["bottom"] > page.height - FOOTER or ch["top"] < HEADER * 0.5:
            continue
        cx, cy = (ch["x0"] + ch["x1"]) / 2, (ch["top"] + ch["bottom"]) / 2
        if x0 - 4 <= cx <= x1 + 4 and y0 - 4 <= cy <= y1 + 4:
            x0, x1 = min(x0, ch["x0"]), max(x1, ch["x1"])
            y0, y1 = min(y0, ch["top"]), max(y1, ch["bottom"])
    return (max(0, x0 - PAD), max(0, y0 - PAD),
            min(page.width, x1 + PAD), min(page.height - FOOTER, y1 + PAD))


def save_crop(page, bbox, dest, dry_run):
    if bbox is None or bbox[2] - bbox[0] < 40 or bbox[3] - bbox[1] < 40:
        return False
    if dry_run:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    page.crop(bbox).to_image(resolution=RESOLUTION).save(str(dest))
    return True


def series_in(text, known):
    """キャプションが名指しするシリーズ（`CH32V303/305/307` を展開する）。"""
    found = []
    for m in re.finditer(r"CH32([A-Z])(\d{3})((?:/\d{3})*)", text):
        prefix, first, rest = m.group(1), m.group(2), m.group(3)
        for digits in [first] + re.findall(r"\d{3}", rest):
            name = f"CH32{prefix}{digits}"
            if name in known:
                found.append(name)
    return found


def find_architecture(pdf, datasheet_series, out, dry_run, family,
                      required=None):
    """第1章のシステムブロック図。キャプション直下から次の見出しまで。"""
    done = set()
    for page in pdf.pages[:20]:
        rows = lines_of(page)
        for i, (top, text) in enumerate(rows):
            m = ARCH_CAPTION.search(text)
            if not m:
                continue
            scope = series_in(m.group("scope") or "", datasheet_series) or [
                s for s in datasheet_series if s not in done]
            bottom = page.height - FOOTER
            for later_top, later_text in rows[i + 1:]:
                if ARCH_CAPTION.search(later_text) or NEXT_CHAPTER.match(later_text):
                    bottom = later_top
                    break
            bbox = region_bbox(page, top + 8, bottom)
            for s in scope:
                if s in done:
                    continue
                name = f"architecture_{s}.png"
                if required and name not in required:
                    continue
                dest = MIRRORS / family / "image" / name
                if save_crop(page, bbox, dest, dry_run):
                    out.append((dest, f"p.{page.page_number}"))
                    done.add(s)
    return done


def expand_label(label, parts_by_series):
    """図の見出し → 実在する型番。

    見出しは完全な型番とは限らない。伏字（`CH32V203CxT6`）、温度グレードの
    桁を省いた形（`CH32V007K8U` が U6 と U7 の両方を指す）、パッケージ違いを
    まとめた形（`CH32V103Cx` が LQFP48 と QFN48×7 を指す）がある。
    """
    parts = parts_by_series["all"]
    if label in parts:
        return [label]
    pattern = re.compile("^" + re.sub(r"[xX]", ".", label) + "[A-Z0-9]*$")
    return [p for p in parts if pattern.match(p)]


def find_pinouts(pdf, group_of_part, parts_by_series, out, dry_run, family,
                 required=None):
    """ピン配置章の図。

    見出しの置き方がデータシートごとに違う（図の上に置く版、下に置く版、
    1行に2つ横並びで置く版）ため、**先に図の塊を検出**してから、縦に最も
    近い見出しを対応付ける。横並びは、同じ塊に複数の見出しがぶら下がる形で
    現れるので、見出しのx位置の中間で塊を割る。
    """
    inside = False
    done = set()
    for page in pdf.pages:
        rows = lines_of(page)
        labels = []          # (top, x中心, 型番)
        for top, text in rows:
            if PINOUT_CHAPTER.match(text):
                inside = True
                continue
            if inside and NEXT_CHAPTER.match(text):
                inside = False
            if not inside:
                continue
            for w in page.extract_words():
                if abs(w["top"] - top) < 3 and PART_LABEL.match(w["text"]):
                    hits = expand_label(w["text"], parts_by_series)
                    if hits:
                        labels.append((w["top"], (w["x0"] + w["x1"]) / 2, hits))
        if not labels:
            continue

        for box in clusters_of(page, HEADER * 0.5, page.height - FOOTER):
            x0, y0, x1, y1 = box
            near = [l for l in labels
                    if x0 - 20 <= l[1] <= x1 + 20
                    and y0 - 90 <= l[0] <= y1 + 90]
            if not near:
                continue

            # 見出しは図の上に置く版と下に置く版がある。塊の上端の近くに
            # 見出しがあれば上置き、無ければ下置き（図→見出しの順）。
            near.sort(key=lambda l: (l[0], l[1]))
            above = near[0][0] <= y0 + 40
            bands = []           # (上端, 下端, その帯の見出したち)
            rows_of_labels = []
            for label in near:
                if rows_of_labels and abs(label[0] - rows_of_labels[-1][0][0]) < 12:
                    rows_of_labels[-1].append(label)
                else:
                    rows_of_labels.append([label])
            edge = y0
            for i, row in enumerate(rows_of_labels):
                if above:
                    top_i = row[0][0] - 4
                    bottom_i = (rows_of_labels[i + 1][0][0] - 4
                                if i + 1 < len(rows_of_labels) else y1)
                else:
                    top_i = edge
                    bottom_i = row[0][0] + 12
                    edge = bottom_i
                bands.append((max(y0, top_i), min(y1, bottom_i), row))

            for band_top, band_bottom, row in bands:
                if band_bottom - band_top < 40:
                    continue
                row.sort(key=lambda l: l[1])
                edges = [x0]
                if len(row) > 1:          # 横並びは見出しのx中間で割る
                    edges += [(row[i][1] + row[i + 1][1]) / 2
                              for i in range(len(row) - 1)]
                edges.append(x1)
                for i, (_, _, parts) in enumerate(row):
                    sub = (edges[i], band_top, edges[i + 1], band_bottom)
                    bbox = with_inner_text(page, sub)
                    # 1つの図が複数のピン配置（パッケージ違い）を代表することが
                    # あるので、該当する名前すべてに同じ切り出しを書く。
                    for name in dict.fromkeys(group_of_part.get(p) for p in parts):
                        if not name or name in done:
                            continue
                        if required and name not in required:
                            continue
                        dest = MIRRORS / family / "image" / name
                        if save_crop(page, bbox, dest, dry_run):
                            out.append((dest, f"p.{page.page_number} {parts[0]}"))
                            done.add(name)
    return done


def find_packages(pdf, packages, out, dry_run):
    """パッケージ章の外形図。見出し `4.1 TSSOP20 package` の直下。"""
    done = set()
    for page in pdf.pages:
        rows = lines_of(page)
        heads = [(top, m.group("package").upper())
                 for top, text in rows
                 for m in [PACKAGE_HEADING.match(text)] if m]
        for i, (top, package) in enumerate(heads):
            if package not in packages or package in done:
                continue
            bottom = heads[i + 1][0] if i + 1 < len(heads) else page.height - FOOTER
            bbox = region_bbox(page, top + 8, bottom)
            dest = MIRRORS / "WCH-common" / "image" / f"package_{package}.png"
            if save_crop(page, bbox, dest, dry_run):
                out.append((dest, f"p.{page.page_number}"))
                done.add(package)
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--family", help="このファミリーだけ処理する")
    ap.add_argument("--dry-run", action="store_true",
                    help="書き出さずに対象だけ表示する")
    args = ap.parse_args()

    products = load("products")
    parts_by_series = {"all": [p["part_number"] for p in products]}
    packages = {p["package"] for p in load("packages")}
    series_of_datasheet = defaultdict(set)
    for p in products:
        series_of_datasheet[(p["family"], p["datasheet"])].add(p["series"])

    # 型番 → 必要なpinoutファイル名（配置が同じ型番は1枚を共有する）
    sys.path.insert(0, str(Path(__file__).parent))
    import check_images
    need = {f: set(names) for f, names in
            check_images.required().items()}
    group_of_part = {}
    for (family, name), parts in check_images.pinout_groups().items():
        for part in parts:
            group_of_part[part] = name

    for (family, datasheet), ds_series in sorted(series_of_datasheet.items()):
        if args.family and family != args.family:
            continue
        path = MIRRORS / family / "datasheet_en" / datasheet
        if not path.exists():
            print(f"{family}/{datasheet}: 英語版が無い", file=sys.stderr)
            continue
        written = []
        with pdfplumber.open(path) as pdf:
            find_architecture(pdf, sorted(ds_series), written, args.dry_run,
                              family, need.get(family))
            find_pinouts(pdf, group_of_part, parts_by_series, written,
                         args.dry_run, family, need.get(family))
            find_packages(pdf, packages, written, args.dry_run)
        print(f"== {family}/{datasheet}: {len(written)} 枚")
        for dest, note in written:
            print(f"   {dest.relative_to(MIRRORS)}  ({note})")


if __name__ == "__main__":
    main()
