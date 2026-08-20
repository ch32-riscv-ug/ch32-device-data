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
import json
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
    r"(?:system\s+(?:block\s+diagram|architecture|structure)"
    r"|系统框图|系统结构框图|系统架构)", re.IGNORECASE)
PINOUT_CHAPTER = re.compile(r"^\d+\.\d+\s+(?:Pinouts?|引脚分布|引脚图)\s*$", re.I)
NEXT_CHAPTER = re.compile(r"^\d+\.\d+\s+\S")
# 見出しは1つの型番とは限らず、`CH32V303RxT6/CH32V303RCT7` のように
# スラッシュで連ねることがある。
PART_LABEL = re.compile(r"^CH32[A-Za-z0-9]{4,}(?:/CH32[A-Za-z0-9]{4,})*$")
# 見出しは節番号形式（`4.1 TSSOP20 package`）と図番号形式
# （`Figure 4-2 QFN48X7_A package`。CH32M030）の2通りある。
PACKAGE_HEADING = re.compile(
    r"^(?:(?:Figure|图)\s*[\d.\-]+\s+|\d+\.\d+\s+)"
    r"(?P<package>[A-Z][A-Z0-9_×xX*]{2,})\s*(?:package|封装)", re.I)
FOOTER = 60          # ページ下端の版数・ページ番号の帯（罫線が無い場合の既定）
HEADER = 95          # ページ上端のヘッダ（同上）
PAD = 10          # 図の周りに残す余白


def is_rule(o, page):
    """ヘッダ・フッタの区切り罫線（横いっぱいの細い線）か。"""
    return ((o["x1"] - o["x0"]) >= page.width * 0.6
            and (o["bottom"] - o["top"]) <= 2
            and (o["top"] < page.height * 0.15 or o["top"] > page.height * 0.8))


def body_bounds(page):
    """本文の上下端。ヘッダ・フッタは横いっぱいの罫線で区切られているので、
    その罫線を見つけて内側を本文とする（版数・ページ番号・WCHロゴが図に
    混ざるのを防ぐ）。罫線が無いページは既定値で切る。"""
    top_limit, bottom_limit = HEADER * 0.5, page.height - FOOTER
    for kind in ("lines", "curves", "rects"):
        for o in getattr(page, kind):
            if (o["x1"] - o["x0"]) < page.width * 0.6:
                continue
            if (o["bottom"] - o["top"]) > 2:
                continue
            # 図が罫線に重なっている版がある（CH32V407DS0はピン番号が
            # フッタ罫線に食い込む）。少しだけ越えられるようにしておく。
            if o["top"] < page.height * 0.15:
                top_limit = max(top_limit, o["bottom"] - 6)
            elif o["top"] > page.height * 0.8:
                bottom_limit = min(bottom_limit, o["top"] + 10)
    return top_limit, bottom_limit


def caption_corrections():
    """curated/figure-captions.json — データシートの図キャプションの訂正。

    キャプションが指すシリーズを人が確認して直したもの（CH32H417DS0は
    2つの図に同じ CH32H416 と書いてしまっている）。理由もファイルに残す。
    """
    path = REPO / "curated" / "figure-captions.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("corrections", {})


def load(name):
    with (REPO / "tables" / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lines_of(page):
    """[(top, bottom, text)] — 行単位のテキストと縦位置。

    下端も返すのは、見出し行の**下**から図が始まるため。行の上端だけを見て
    切ると、キャプションの文字の下半分が図に写り込む。
    """
    words = page.extract_words()
    rows = defaultdict(list)
    for w in words:
        rows[round(w["top"])].append(w)
    out = []
    for top in sorted(rows):
        chunk = sorted(rows[top], key=lambda w: w["x0"])
        out.append((top, max(w["bottom"] for w in chunk),
                    " ".join(w["text"] for w in chunk)))
    return out


def region_bbox(page, top, bottom, gap=30):
    """帯 [top, bottom) の**最初の図**の外接矩形。

    図は罫線・曲線・埋め込み画像の塊で、その下に本文や表が続く。素朴に帯全体の
    外接矩形を取ると本文まで飲み込むので、描画物を縦方向の空白で塊に分け、
    最初の塊だけを図とみなす。文字は塊の内側にあるものだけ含める（ピン名や
    ブロック名は図の一部だが、図の下の注記は図ではない）。
    """
    body_top, body_bottom = body_bounds(page)

    def usable(o):
        if o["top"] < top or o["bottom"] > bottom:
            return False
        if o["bottom"] > body_bottom or o["top"] < body_top:
            return False
        wide = (o["x1"] - o["x0"]) > page.width * 0.85
        tall = (o["bottom"] - o["top"]) > page.height * 0.7
        return not (wide and tall) and not is_rule(o, page)          # ページ枠の矩形

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
    body_top, body_bottom = body_bounds(page)
    bbox = (max(0, x0 - PAD), max(top, y0 - PAD),
            min(page.width, x1 + PAD), min(bottom, y1 + PAD))
    # 帯の外へは広げない。上はキャプション、下は次の見出しがあるため。
    limits = (0, max(body_top, top), page.width, min(body_bottom, bottom))
    return bbox, limits


def clusters_of(page, top, bottom, gap=30, x_range=None):
    """帯の中の図を塊ごとに列挙する。[(x0, top, x1, bottom), ...]

    gap は「これ以上の縦の空白があれば別の図」とみなす閾値。x_range を渡すと
    その横幅の中の描画物だけを見る（1つの塊をさらに割るときに使う）。
    """
    body_top, body_bottom = body_bounds(page)

    def usable(o):
        if o["top"] < top or o["bottom"] > bottom:
            return False
        if x_range and not (x_range[0] - 1 <= (o["x0"] + o["x1"]) / 2
                            <= x_range[1] + 1):
            return False
        if o["bottom"] > body_bottom or o["top"] < body_top:
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


def x_boundary(page, piece, left, right):
    """横並びの図の境目。見出しのx中間ではなく、**図と図の間の空白**で割る。

    見出しは図の中央に置かれるとは限らず、中間で割ると図の端（左側のピン名や
    ピン番号）を切り落とす。piece の中の描画物と文字が占めるxを1pt刻みで
    調べ、2つの見出しの間にある最も広い空白の中央を境目にする。
    """
    x0, y0, x1, y1 = piece
    span = int(x1 - x0) + 1
    occupied = bytearray(span)
    for kind in ("curves", "lines", "rects", "images", "chars"):
        for o in getattr(page, kind):
            if o["bottom"] < y0 or o["top"] > y1:
                continue
            start = max(0, int(o["x0"] - x0))
            end = min(span - 1, int(o["x1"] - x0))
            for i in range(start, end + 1):
                occupied[i] = 1
    lo, hi = int(left - x0), int(right - x0)
    best, run_start = None, None
    for i in range(max(0, lo), min(span, hi + 1)):
        if not occupied[i]:
            run_start = i if run_start is None else run_start
        elif run_start is not None:
            if best is None or i - run_start > best[1] - best[0]:
                best = (run_start, i)
            run_start = None
    if run_start is not None and (best is None or span - run_start > best[1] - best[0]):
        best = (run_start, min(span, hi + 1))
    if best is None:
        return (left + right) / 2
    return x0 + (best[0] + best[1]) / 2


def grow(piece, others, page, reach=14):
    """図の帯を、隣にぶつかる手前（最大 reach pt）まで広げる。

    上下のピン番号は罫線の塊から離れており、塊の範囲のままだと図の外の要素と
    見なして切ってしまう。広げる先には見出しや本文もあるので、他の図
    （others）だけでなくページ上の要素も見て、その中間で止める。
    """
    x0, y0, x1, y1 = piece
    top_limit, bottom_limit = HEADER * 0.5, page.height - FOOTER
    left_limit, right_limit = 0, page.width

    def consider(box):
        nonlocal top_limit, bottom_limit, left_limit, right_limit
        if box[2] > x0 and box[0] < x1:            # 縦に並ぶもの
            if box[3] <= y0:
                top_limit = max(top_limit, box[3])
            elif box[1] >= y1:
                bottom_limit = min(bottom_limit, box[1])
        if box[3] > y0 and box[1] < y1:            # 横に並ぶもの
            if box[2] <= x0:
                left_limit = max(left_limit, box[2])
            elif box[0] >= x1:
                right_limit = min(right_limit, box[0])

    for box in others:
        consider(box)
    for kind in ("curves", "lines", "rects", "images", "chars"):
        for o in getattr(page, kind):
            cx, cy = (o["x0"] + o["x1"]) / 2, (o["top"] + o["bottom"]) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                continue                            # この図の要素
            if is_rule(o, page):
                continue
            if (o["x1"] - o["x0"]) > page.width * 0.85:
                continue                            # ページ枠
            consider((o["x0"], o["top"], o["x1"], o["bottom"]))

    return (max(x0 - reach, (left_limit + x0) / 2),
            max(y0 - reach, (top_limit + y0) / 2),
            min(x1 + reach, (x1 + right_limit) / 2),
            min(y1 + reach, (y1 + bottom_limit) / 2))


def with_inner_text(page, box):
    """帯の中に**中心が入っている**ものだけを集めた外接矩形。

    帯の縦は図の塊、横は図と図の間の空白で決めてあるので、あとはその中の
    実体（枠・引出線・ピン名・ピン番号）に合わせて詰めるだけでよい。中心で
    判定するのは、隣の図から少しはみ出した線や、帯の端に載った注記を
    巻き込まないため。
    """
    x0, y0, x1, y1 = box

    def frame(o):
        return ((o["x1"] - o["x0"]) > page.width * 0.85
                and (o["bottom"] - o["top"]) > page.height * 0.7)

    content = []
    for kind in ("curves", "lines", "rects", "images", "chars"):
        for o in getattr(page, kind):
            cx, cy = (o["x0"] + o["x1"]) / 2, (o["top"] + o["bottom"]) / 2
            if (x0 <= cx <= x1 and y0 <= cy <= y1
                    and not frame(o) and not is_rule(o, page)):
                content.append(o)
    if not content:
        return None
    # 切り出しは実体の外接矩形。帯は「どれがこの図の要素か」の判定にだけ
    # 使い、範囲そのものは詰め戻さない（中心が内側でも端がはみ出す文字が
    # あり、帯で切ると右端のピン名やピン番号が欠ける）。
    mine = {id(o) for o in content}
    left = min(o["x0"] for o in content)
    right = max(o["x1"] for o in content)
    top = min(o["top"] for o in content)
    bottom = max(o["bottom"] for o in content)

    # 余白は、この図に属さない要素（隣の図・上の見出し・下の注記）に
    # ぶつかる手前まで。上下左右のどちらも同じ扱いにする。
    body_top, body_bottom = body_bounds(page)
    ceiling, floor, wall_left, wall_right = body_top, body_bottom, 0, page.width
    for kind in ("curves", "lines", "rects", "images", "chars"):
        for o in getattr(page, kind):
            if id(o) in mine or frame(o) or is_rule(o, page):
                continue
            if o["x1"] > left and o["x0"] < right:      # 縦に効く障害物
                if o["bottom"] <= top:
                    ceiling = max(ceiling, o["bottom"])
                elif o["top"] >= bottom:
                    floor = min(floor, o["top"])
            if o["bottom"] > top and o["top"] < bottom:  # 横に効く障害物
                if o["x1"] <= left:
                    wall_left = max(wall_left, o["x1"])
                elif o["x0"] >= right:
                    wall_right = min(wall_right, o["x0"])
    # 隣が近いときは、すき間を等分して両方に余白を残す（2pt手前で止めると
    # 図の縁に文字が接して窮屈に見える）。
    bbox = (max((wall_left + left) / 2, left - PAD),
            max((ceiling + top) / 2, top - PAD),
            min((right + wall_right) / 2, right + PAD),
            min((bottom + floor) / 2, bottom + PAD))
    limits = (max(0, wall_left), max(body_top, ceiling),
              min(page.width, wall_right), min(body_bottom, floor))
    return bbox, limits


def touching_edges(image):
    """描いた画像の最外周にインクが接している辺。切れているか、隣が入っている。"""
    grey = image.convert("L")
    width, height = grey.size
    px = grey.load()
    edges = set()
    for x in range(width):
        if px[x, 0] < 200:
            edges.add("top")
        if px[x, height - 1] < 200:
            edges.add("bottom")
    for y in range(height):
        if px[0, y] < 200:
            edges.add("left")
        if px[width - 1, y] < 200:
            edges.add("right")
    return edges


def save_crop(page, boxes, dest, dry_run):
    """切り出して描く。

    PDFの座標だけでは縁が決まらない（90度回転した文字は座標が実際の描画と
    ずれる）。描いた画像の縁にインクが接していたら、限界の手前まで少しずつ
    広げて描き直す。
    """
    if boxes is None:
        return False
    bbox, limits = boxes
    if bbox is None or bbox[2] - bbox[0] < 40 or bbox[3] - bbox[1] < 40:
        return False
    if dry_run:
        return True
    x0, y0, x1, y1 = bbox
    image = None
    for _ in range(8):
        image = page.crop((x0, y0, x1, y1)).to_image(resolution=RESOLUTION)
        edges = touching_edges(image.original)
        if not edges:
            break
        grew = False
        if "left" in edges and x0 > limits[0]:
            x0, grew = max(limits[0], x0 - 6), True
        if "top" in edges and y0 > limits[1]:
            y0, grew = max(limits[1], y0 - 6), True
        if "right" in edges and x1 < limits[2]:
            x1, grew = min(limits[2], x1 + 6), True
        if "bottom" in edges and y1 < limits[3]:
            y1, grew = min(limits[3], y1 + 6), True
        if not grew:
            break
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(dest))
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
                      required=None, corrections=None):
    """第1章のシステムブロック図。キャプション直下から次の見出しまで。"""
    done = set()
    corrections = corrections or {}
    for page in pdf.pages[:20]:
        rows = lines_of(page)
        for i, (top, line_bottom, text) in enumerate(rows):
            m = ARCH_CAPTION.search(text)
            if not m:
                continue
            number = re.match(r"(?:Figure|图)\s*[\d.\-]+", text)
            fix = corrections.get(number.group(0).strip()) if number else None
            if fix:
                scope = [fix["series"]]
            else:
                scope = series_in(m.group("scope") or "", datasheet_series) or [
                    s for s in datasheet_series if s not in done]
            bottom = body_bounds(page)[1]
            for later_top, _, later_text in rows[i + 1:]:
                if ARCH_CAPTION.search(later_text) or NEXT_CHAPTER.match(later_text):
                    bottom = later_top
                    break
            bbox = region_bbox(page, line_bottom + 4, bottom)
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
    # 8文字はシリーズ名そのもの（`CH32L103`）。ページヘッダの
    # 「CH32L103 Datasheet」を見出しと取り違えないよう、パッケージや
    # 温度グレードの桁が付いたものだけを展開の対象にする。
    if len(label) <= 8:
        return []
    pattern = re.compile("^" + re.sub(r"[xX]", ".", label) + "[A-Z0-9]*$")
    return [p for p in parts if pattern.match(p)]


def find_pinouts(pdf, group_of_part, parts_by_series, out, dry_run, family,
                 required=None, lead_of_name=None):
    """ピン配置章の図。

    見出しの置き方がデータシートごとに違う（図の上に置く版、下に置く版、
    1行に2つ横並びで置く版）ため、**先に図の塊を検出**してから、縦に最も
    近い見出しを対応付ける。横並びは、同じ塊に複数の見出しがぶら下がる形で
    現れるので、見出しのx位置の中間で塊を割る。
    """
    inside = False
    done = {}            # ファイル名 → 代表型番の図で作ったか
    lead_of_name = lead_of_name or {}

    # 1周目: ピン配置章のページから、図の塊と見出しを集める。
    pages = []
    for page in pdf.pages:
        rows = lines_of(page)
        labels = []          # (top, 下端, x中心, 型番)
        label_rects = []
        body_top, body_bottom = body_bounds(page)
        for top, _, text in rows:
            if PINOUT_CHAPTER.match(text):
                inside = True
                continue
            if inside and NEXT_CHAPTER.match(text):
                inside = False
            if not inside or not body_top <= top <= body_bottom:
                continue
            for w in page.extract_words():
                if abs(w["top"] - top) < 3 and PART_LABEL.match(w["text"]):
                    hits = []
                    for token in w["text"].split("/"):
                        hits += [h for h in expand_label(token, parts_by_series)
                                 if h not in hits]
                    if hits:
                        labels.append((w["top"], w["bottom"],
                                       (w["x0"] + w["x1"]) / 2, hits))
                        label_rects.append((w["x0"], w["top"],
                                            w["x1"], w["bottom"]))
        if labels:
            boxes = clusters_of(page, body_top, body_bottom)
            if boxes:
                pages.append((page, labels, boxes, label_rects))

    # 見出しを図の上に置くか下に置くかはデータシートごとに一貫している。
    # どちらで読むと辻褄が合うかを、全ページの距離の合計で決める。図の中に
    # 置く版（CH32M030）は、内側判定が先に効くのでどちらでも構わない。
    def outside_gap(label, box):
        dx = max(box[0] - label[2], 0, label[2] - box[2])
        dy = max(box[1] - label[0], 0, label[0] - box[3])
        return (dx * dx + dy * dy) ** 0.5

    score = {"above": 0.0, "below": 0.0}
    for page, labels, boxes, _ in pages:
        for label in labels:
            under = [b for b in boxes if b[1] >= label[1] - 2]
            over = [b for b in boxes if b[3] <= label[0] + 2]
            score["above"] += min((outside_gap(label, b) for b in under),
                                  default=500)
            score["below"] += min((outside_gap(label, b) for b in over),
                                  default=500)
    label_above = score["above"] <= score["below"]

    # 2周目: 見出しを担当の塊へ割り当てて切り出す。
    for page, labels, boxes, label_rects in pages:
        by_box = {i: [] for i in range(len(boxes))}
        for label in labels:
            inside_box = [i for i, b in enumerate(boxes)
                          if b[1] <= label[0] <= b[3] and b[0] <= label[2] <= b[2]]
            if inside_box:
                by_box[inside_box[0]].append(label)
                continue
            if label_above:      # 見出しの下にある図
                side = [i for i, b in enumerate(boxes) if b[1] >= label[1] - 2]
            else:                # 見出しの上にある図
                side = [i for i, b in enumerate(boxes) if b[3] <= label[0] + 2]
            candidates = side or list(range(len(boxes)))
            index = min(candidates, key=lambda i: outside_gap(label, boxes[i]))
            if outside_gap(label, boxes[index]) <= 90:
                by_box[index].append(label)

        for index, box in enumerate(boxes):
            x0, y0, x1, y1 = box
            near = by_box[index]
            if not near:
                continue
            # 同じ型番が図の中にも書かれていることがある（CH32V203DS0の
            # QFN32図）。重複は1つに畳む。
            unique = {}
            for label in near:
                unique.setdefault(tuple(label[3]), label)
            near = sorted(unique.values(), key=lambda l: (l[0], l[2]))

            # 図の数だけ塊に割れるまで、縦の空白の判定を細かくしていく。
            pieces = [box]
            if len(near) > 1:
                for gap in (20, 14, 10, 8, 6, 4):
                    sub = clusters_of(page, y0 - 1, y1 + 1, gap, (x0, x1))
                    if len(sub) > len(pieces):
                        pieces = sub
                    if len(sub) >= len(near):
                        break

            per_piece = {i: [] for i in range(len(pieces))}
            for label in near:
                index2 = min(range(len(pieces)),
                             key=lambda i: outside_gap(label, pieces[i]))
                per_piece[index2].append(label)

            owned = {}
            for index2, piece in enumerate(pieces):
                mine = sorted(per_piece[index2], key=lambda l: l[2])
                if not mine:
                    continue
                width = piece[2] - piece[0]
                if len(mine) > 1 and (mine[-1][2] - mine[0][2]) > width * 0.25:
                    edges = ([piece[0]]
                             + [x_boundary(page, piece, mine[i][2], mine[i + 1][2])
                                for i in range(len(mine) - 1)]
                             + [piece[2]])
                    for i, label in enumerate(mine):
                        owned[tuple(label[3])] = (edges[i], piece[1],
                                                  edges[i + 1], piece[3])
                else:
                    for label in mine:
                        owned.setdefault(tuple(label[3]), piece)

            for parts, piece in owned.items():
                # 帯を隣との中間まで広げてから要素を拾う。上下のピン番号は
                # 罫線の塊から離れた位置にあり、塊の範囲のままだと図の外の
                # 要素と見なして切ってしまう。
                others = ([q for q in owned.values() if q is not piece]
                          + [b for b in boxes if b is not box]
                          + [r for r in label_rects
                             if not (piece[0] <= (r[0] + r[2]) / 2 <= piece[2]
                                     and piece[1] <= (r[1] + r[3]) / 2 <= piece[3])])
                bbox = with_inner_text(page, grow(piece, others, page))
                # 1つの図が複数のピン配置（パッケージ違い）を代表することが
                # あるので、該当する名前すべてに同じ切り出しを書く。
                for name in dict.fromkeys(group_of_part.get(p) for p in parts):
                    if not name or (required and name not in required):
                        continue
                    # 同じピン配置でも、データシートは型番ごとに図を描いて
                    # いることがある。ファイル名に使う代表型番の図が見つかった
                    # ら、先に作ったものを差し替える（名前と図中の型番が
                    # 食い違わないようにする）。
                    is_lead = lead_of_name.get(name) in parts
                    if name in done and (done[name] or not is_lead):
                        continue
                    dest = MIRRORS / family / "image" / name
                    if save_crop(page, bbox, dest, dry_run):
                        out.append((dest, f"p.{page.page_number} {parts[0]}"))
                        done[name] = is_lead
    return done


def find_packages(pdf, packages, out, dry_run):
    """パッケージ章の外形図。見出し `4.1 TSSOP20 package` の直下。"""
    done = set()
    for page in pdf.pages:
        rows = lines_of(page)
        heads = [(top, line_bottom, m.group("package").upper())
                 for top, line_bottom, text in rows
                 for m in [PACKAGE_HEADING.match(text)] if m]
        for i, (top, line_bottom, package) in enumerate(heads):
            if package not in packages or package in done:
                continue
            bottom = (heads[i + 1][0] if i + 1 < len(heads)
                      else body_bounds(page)[1])
            bbox = region_bbox(page, line_bottom + 4, bottom)
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
    ap.add_argument("--kind", choices=("architecture", "pinout", "package"),
                    action="append",
                    help="この種類だけ処理する（既定は全部）")
    args = ap.parse_args()

    corrections = caption_corrections()
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
    lead_of_name = {}
    for (family, name), parts in check_images.pinout_groups().items():
        lead_of_name[name] = sorted(parts)[0]
        for part in parts:
            group_of_part[part] = name

    # 生成対象を先に消す。古いファイルが残っていると、抽出に失敗しても
    # check_images.py には「ある」と見えてしまい、失敗が隠れる。
    kinds = set(args.kind or ("architecture", "pinout", "package"))
    need = {family: {n for n in names if n.split("_")[0] in kinds}
            for family, names in need.items()}

    if not args.dry_run:
        for family, names in sorted(need.items()):
            # --family 指定時は WCH-common を消さない。そのファミリーの
            # データシートに載っているパッケージしか作り直せないため。
            if args.family and family != args.family:
                continue
            image_dir = MIRRORS / family / "image"
            for name in names:
                path = image_dir / name
                if path.exists():
                    path.unlink()

    for (family, datasheet), ds_series in sorted(series_of_datasheet.items()):
        if args.family and family != args.family:
            continue
        path = MIRRORS / family / "datasheet_en" / datasheet
        if not path.exists():
            print(f"{family}/{datasheet}: 英語版が無い", file=sys.stderr)
            continue
        written = []
        with pdfplumber.open(path) as pdf:
            if "architecture" in kinds:
                find_architecture(pdf, sorted(ds_series), written, args.dry_run,
                                  family, need.get(family),
                                  corrections.get(datasheet))
            if "pinout" in kinds:
                find_pinouts(pdf, group_of_part, parts_by_series, written,
                             args.dry_run, family, need.get(family),
                             lead_of_name)
            if "package" in kinds:
                find_packages(pdf, packages, written, args.dry_run)
        print(f"== {family}/{datasheet}: {len(written)} 枚")
        for dest, note in written:
            print(f"   {dest.relative_to(MIRRORS)}  ({note})")


if __name__ == "__main__":
    main()
