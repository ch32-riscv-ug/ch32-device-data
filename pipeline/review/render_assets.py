#!/usr/bin/env python3
"""図のpixel描画（asset renderer。D16が分離を予告した工程の実装）。

bundleは意味データ（文字・表・座標）だけを持ち、図のpixelは持たない。この
rendererが**原本PDFのhashをmanifestと照合してから**（入口ゲート）、図の領域を
切り出してPNGに描き、`assets.json`（原本SHA-256・領域bbox・PNGのSHA-256）と
一緒にMarkdownの隣へ置く。exporterはこれがあれば図caption直後の警告の代わりに
画像を埋め込む。

**図の領域は文字ではなくgraphicsの縦クラスタで決める**。図の中のラベル
（block名・pin名）は`paragraph`の行として写るので、文字を境界にすると領域が
潰れる（V003 p3の系統図で実測）。手順:

1. 表の外にあるgeometry層の描画要素（line/rect/curve/image）に、
   **無captionで面積が小さい「表」**（波形図の箱がmicro-tableとして誤検出される
   ——FV2x RM p173で実測: 2×2・24×23ptの"表"）と、**図captionの直下
   （NEAR以内）にある無caption表**（図全体が1つの"表"として誤検出される——
   过滤器编号の示例は2セルで97,759pt²、Sinc3滤波器の応答グラフは35セル。
   本物の継続断片はページ先頭が定位置なのでcaptionの下には来ない）を
   図の部品として合流させ、縦に走査して15ptを超える空隙でクラスタに分ける
2. 重み8以上（micro-tableはセル数で重む）、または高さ40pt以上のクラスタだけを
   図の候補にする（文の下線などの小さな飾りを弾く）
3. 図のcaption行（`Figure N-N`／`图N-N`。**本文の参照文は除く**——判定は
   `pipeline/common/figure_captions.py`）に、**caption直下**のクラスタを優先して
   対応付ける。同ページに無く、captionがページ下部にあれば**次ページ先頭**の
   クラスタ（次ページのどのcaptionよりも上にあるもの）へfallbackする
4. 領域はクラスタのbboxに、縦に重なる文字の行（図中ラベル）を合成して4pt広げる
5. caption行を跨がないようにclipして150dpiで描画する

対応するクラスタが無いcaptionは**そのまま**（exporterの「再現していない」警告が
残る——取りこぼしを隠さない）。captionを持たない大きめのraster画像
（封装図など。40×40pt以上）は、その画像のbboxで個別に描く。

実行:
    uv run pipeline/review/render_assets.py --all
    uv run pipeline/review/render_assets.py .cache/structured-bundles/CH32V003DS0.en
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pdfplumber
from io import BytesIO

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
import figure_captions  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
MARKDOWN = REPO / ".cache" / "structured-markdown"

GAP = 15.0            # pt。これを超える縦の空隙でクラスタを分ける
MIN_WEIGHT = 8        # クラスタが図と呼べる最小の重み
MIN_HEIGHT = 40.0     # または最小の高さ（pt）
NEAR = 100.0          # captionとクラスタの最大距離（pt）
PAD = 4.0
LARGE_IMAGE = 40.0
SUSPECT_TABLE_AREA = 15000.0   # pt²。無captionでこれより小さい「表」は図の部品
BOTTOM_BAND = 0.70    # 次ページfallbackを試すcaption位置（ページ高比）
TOP_BAND = 0.30       # 次ページ側で拾ってよいクラスタの上限位置
RESOLUTION = 150


def load_page(bundle: Path, entry: dict) -> tuple[dict, dict]:
    payload = (bundle / entry["file"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
    geometry_raw = gzip.decompress((bundle / entry["geometry_file"]).read_bytes())
    # hashは非圧縮のJSONに対して（gzipのバイト列はzlibの版で変わる）
    if hashlib.sha256(geometry_raw).hexdigest() != entry["geometry_sha256"]:
        raise SystemExit(f"{bundle}/{entry['geometry_file']}: hash differs from manifest")
    return json.loads(payload), json.loads(geometry_raw)


def graphic_clusters(page: dict, geometry: dict) -> list[dict]:
    caption_bottoms = [line["bbox"][3] for line in page_captions(page)]

    def below_caption(bbox: list[float]) -> bool:
        return any(0 <= bbox[1] - bottom <= NEAR for bottom in caption_bottoms)

    real_boxes: list[list[float]] = []
    items: list[dict] = []
    for table in page["tables"]:
        x0, top, x1, bottom = table["bbox"]
        if table.get("caption") is None and (
                (x1 - x0) * (bottom - top) < SUSPECT_TABLE_AREA
                or below_caption(table["bbox"])):
            items.append({"bbox": table["bbox"], "weight": max(len(table["cells"]), 4)})
        else:
            real_boxes.append(table["bbox"])

    def in_real_table(d: dict) -> bool:
        cx = (d["bbox"][0] + d["bbox"][2]) / 2
        cy = (d["bbox"][1] + d["bbox"][3]) / 2
        return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in real_boxes)

    items += [{"bbox": d["bbox"], "weight": 1}
              for d in geometry["drawings"] if not in_real_table(d)]
    items.sort(key=lambda d: d["bbox"][1])
    clusters: list[dict] = []
    for d in items:
        x0, top, x1, bottom = d["bbox"]
        if clusters and top - clusters[-1]["bbox"][3] <= GAP:
            c = clusters[-1]
            c["bbox"] = [min(c["bbox"][0], x0), min(c["bbox"][1], top),
                         max(c["bbox"][2], x1), max(c["bbox"][3], bottom)]
            c["weight"] += d["weight"]
        else:
            clusters.append({"bbox": [x0, top, x1, bottom], "weight": d["weight"]})
    return [c for c in clusters
            if c["weight"] >= MIN_WEIGHT
            or c["bbox"][3] - c["bbox"][1] >= MIN_HEIGHT]


def expand_with_labels(page: dict, bbox: list[float]) -> list[float]:
    """クラスタに縦へ重なる文字の行（図中ラベル）を領域へ合成する。"""
    x0, top, x1, bottom = bbox
    for line in page["lines"]:
        if line.get("role") in ("header", "footer"):
            continue
        if figure_captions.caption_match(line["text"]):
            continue
        lt, lb = line["bbox"][1], line["bbox"][3]
        if lb < top or lt > bottom:
            continue
        x0 = min(x0, line["bbox"][0])
        x1 = max(x1, line["bbox"][2])
        top = min(top, lt)
        bottom = max(bottom, lb)
    return [x0, top, x1, bottom]


def page_captions(page: dict) -> list[dict]:
    return sorted((line for line in page["lines"]
                   if line.get("role") not in ("header", "footer")
                   and figure_captions.caption_match(line["text"])),
                  key=lambda line: line["bbox"][1])


def assign_regions(pages: list[dict],
                   clusters: list[list[dict]]) -> tuple[list[tuple[str, int, list[float]]],
                                                        int, list[set[int]]]:
    """caption → (caption line id, 領域のページ番号, bbox)。次ページfallback込み。
    3つ目の戻りは「ページごとに使われたクラスタ番号」（独立asset化の判定に使う）。"""
    taken: list[set[int]] = [set() for _ in pages]
    found: list[tuple[str, int, list[float]]] = []
    missed = 0
    for index, page in enumerate(pages):
        captions = page_captions(page)
        for caption in captions:
            c_top, c_bottom = caption["bbox"][1], caption["bbox"][3]

            def pick(below: bool) -> int | None:
                best, best_gap = None, NEAR
                for ci, cluster in enumerate(clusters[index]):
                    if ci in taken[index]:
                        continue
                    gap = (cluster["bbox"][1] - c_bottom if below
                           else c_top - cluster["bbox"][3])
                    # 少しの重なり（-5pt）は許す。captionの行間に図の枠が食い込む
                    if -5 <= gap <= best_gap:
                        best, best_gap = ci, max(gap, 0.0)
                return best

            chosen = pick(below=True)
            if chosen is None:
                chosen = pick(below=False)
            if chosen is not None:
                taken[index].add(chosen)
                bbox = expand_with_labels(page, list(clusters[index][chosen]["bbox"]))
                if bbox[1] >= c_bottom:
                    bbox[1] = max(bbox[1], c_bottom + 1)
                elif bbox[3] <= c_top:
                    bbox[3] = min(bbox[3], c_top - 1)
                found.append((caption["id"], page["number"], bbox))
                continue
            # 次ページの先頭のクラスタ（次ページのどのcaptionよりも上）へfallback
            if (c_bottom > page["height"] * BOTTOM_BAND and index + 1 < len(pages)
                    and pages[index + 1]["number"] == page["number"] + 1):
                next_page = pages[index + 1]
                next_captions = page_captions(next_page)
                limit = (min(c["bbox"][1] for c in next_captions)
                         if next_captions else next_page["height"])
                for ci, cluster in enumerate(clusters[index + 1]):
                    if ci in taken[index + 1]:
                        continue
                    if (cluster["bbox"][1] < next_page["height"] * TOP_BAND
                            and cluster["bbox"][3] <= limit + 5):
                        taken[index + 1].add(ci)
                        bbox = expand_with_labels(next_page, list(cluster["bbox"]))
                        found.append((caption["id"], next_page["number"], bbox))
                        break
                else:
                    missed += 1
                continue
            missed += 1
    return found, missed, taken


def _looks_blank(path: Path) -> bool:
    """描いたPNGが（ほぼ）真っ白か。暗号化PDFの埋め込みJPEG（DCTDecode）をpdfiumが描けず
    白紙になる図がある（M030RM p103の図9-1＝ブロック図とNoteが丸ごと消える。PDF↔MD突合
    サブエージェントが発見、2026-09-03）。暗い画素が全体の0.05%未満なら白紙とみる。"""
    with Image.open(path) as im:
        gray = im.convert("L")
        dark = sum(gray.histogram()[:128])
        return dark < max(1, gray.width * gray.height) * 0.0005


def _decode_indexed(img: dict) -> Image.Image | None:
    """FlateDecodeの生サンプル（Indexed/DeviceRGB・8bit）をパレットで復元する。PILはPDFの
    生サンプル列を開けないので、幅×高さの1byte indexにcolorspaceのlookupを当てる
    （V103DS0 p38/p39・WCH-Link p11/p15の図はこの形。JPEGでなくpdfiumも白紙にした）。"""
    try:
        bits = img.get("bits")
        cs = img.get("colorspace")
        if not (isinstance(cs, list) and len(cs) >= 4
                and str(cs[0]).strip("/'") == "Indexed"):
            return None
        lookup = cs[3]
        if hasattr(lookup, "get_data"):
            lookup = lookup.get_data()
        if not isinstance(lookup, bytes):
            return None
        width, height = img["srcsize"]
        data = img["stream"].get_data()
        if bits == 8:
            if len(data) < width * height:
                return None
            paletted = Image.frombytes("P", (width, height), data[:width * height])
            paletted.putpalette(lookup[:768].ljust(768, b"\x00"))
            return paletted.convert("RGB")
        if bits == 1:
            # 2色パレット（V103DS0 p39の図）。PDFの1bit行は byte 境界で詰められ、PILの
            # "1"モードと同じ並び。0/255のLへ変換してindex 0/255にパレット2色を当てる。
            stride = (width + 7) // 8
            if len(data) < stride * height:
                return None
            gray = Image.frombytes("1", (width, height), data[:stride * height]).convert("L")
            paletted = Image.frombytes("P", (width, height), gray.tobytes())
            palette = bytearray(768)
            palette[0:3] = lookup[0:3].ljust(3, b"\x00")
            palette[765:768] = lookup[3:6].ljust(3, b"\x00")
            paletted.putpalette(bytes(palette))
            return paletted.convert("RGB")
        return None
    except Exception:
        return None


def _paste_embedded_rasters(pdf_page, crop: tuple[float, float, float, float],
                            path: Path) -> int:
    """白紙になった描画へ、領域内の埋め込みrasterをpdfminerのstreamから直接復号して
    貼る（`stream.get_data()`は暗号を解いた生JPEGを返す——pdfiumが失敗しても中身は
    健在）。150dpiの座標系へ位置・大きさを合わせる。貼れた枚数を返す。"""
    x0, top, x1, bottom = crop
    scale = RESOLUTION / 72.0
    canvas = None
    pasted = 0
    for img in pdf_page.images:
        cx = (img["x0"] + img["x1"]) / 2
        cy = (img["top"] + img["bottom"]) / 2
        if not (x0 <= cx <= x1 and top <= cy <= bottom):
            continue
        try:
            raster = Image.open(BytesIO(img["stream"].get_data()))
            raster.load()
        except Exception:
            raster = _decode_indexed(img)   # 生のIndexedサンプルはパレットで復元
            if raster is None:
                continue
        if canvas is None:
            canvas = Image.open(path).convert("RGB")
        left, upper = int((img["x0"] - x0) * scale), int((img["top"] - top) * scale)
        width = max(1, int((img["x1"] - img["x0"]) * scale))
        height = max(1, int((img["bottom"] - img["top"]) * scale))
        canvas.paste(raster.convert("RGB").resize((width, height)), (left, upper))
        pasted += 1
    if canvas is not None:
        canvas.save(path)
    return pasted


def render_document(bundle: Path, pdf_path: Path, out_doc: Path) -> dict:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    source_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if manifest["source"]["sha256"] != source_sha:
        raise SystemExit(f"{bundle}: bundle was converted from a different original")

    pages: list[dict] = []
    clusters: list[list[dict]] = []
    rotated_boxes: list[list[list[float]]] = []   # ページごとの回転文字のbbox
    for entry in manifest["pages"]:
        page, geometry = load_page(bundle, entry)
        pages.append(page)
        clusters.append(graphic_clusters(page, geometry))
        rotated_boxes.append([c["bbox"] for c in geometry["chars"]
                              if c["text"].strip() and not c["upright"]])

    regions, missed, taken = assign_regions(pages, clusters)
    by_page: dict[int, list[tuple[str, list[float]]]] = {}
    for key, number, bbox in regions:
        by_page.setdefault(number, []).append((key, bbox))

    # captionと対にならなかったクラスタでも、**回転文字を含むもの**は独立assetに
    # する。封装図・引脚配置図はcaptionを持たず（節見出しで導入される）、図中の
    # pin番号・pad名が90°回転の文字として本文へ流出していた（2026-09-02に全DSで
    # 3,515行を実測——RMは0）。描画すればexporterが領域内の行を折りたたみへ移す。
    for index, page in enumerate(pages):
        counter = 0
        for ci, cluster in enumerate(clusters[index]):
            if ci in taken[index]:
                continue
            bbox = cluster["bbox"]
            rotated = sum(1 for rb in rotated_boxes[index]
                          if bbox[0] <= (rb[0] + rb[2]) / 2 <= bbox[2]
                          and bbox[1] <= (rb[1] + rb[3]) / 2 <= bbox[3])
            if rotated < 10:
                continue
            counter += 1
            expanded = expand_with_labels(page, list(bbox))
            by_page.setdefault(page["number"], []).append(
                (f"p{page['number']}-cluster-{counter:02d}", expanded))

    # captionの無い大きめのraster画像。図領域が既に含むものは除く。
    for page in pages:
        covered = [bbox for _, bbox in by_page.get(page["number"], [])]
        for image in page["images"]:
            x0, top, x1, bottom = image["bbox"]
            if x1 - x0 < LARGE_IMAGE or bottom - top < LARGE_IMAGE:
                continue
            cx, cy = (x0 + x1) / 2, (top + bottom) / 2
            if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in covered):
                continue
            by_page.setdefault(page["number"], []).append(
                (image["id"], [x0, top, x1, bottom]))

    assets_dir = out_doc / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for number in sorted(by_page):
            pdf_page = pdf.pages[number - 1]
            for key, bbox in by_page[number]:
                x0 = max(0.0, bbox[0] - PAD)
                top = max(0.0, bbox[1] - PAD)
                x1 = min(float(pdf_page.width), bbox[2] + PAD)
                bottom = min(float(pdf_page.height), bbox[3] + PAD)
                if x1 - x0 < 8 or bottom - top < 8:
                    continue
                name = f"{key}.png"
                image = pdf_page.crop((x0, top, x1, bottom)).to_image(
                    resolution=RESOLUTION)
                image.save(assets_dir / name)
                if _looks_blank(assets_dir / name):
                    # pdfiumが白紙を返した——埋め込みJPEGを直接復号して貼り直す。
                    _paste_embedded_rasters(pdf_page, (x0, top, x1, bottom), assets_dir / name)
                payload = (assets_dir / name).read_bytes()
                entries[key] = {
                    "file": f"assets/{name}",
                    "page": number,
                    "bbox": [round(v, 2) for v in (x0, top, x1, bottom)],
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            pdf_page.flush_cache()

    record = {
        "source_sha256": source_sha,
        "resolution": RESOLUTION,
        "assets": entries,
    }
    (out_doc / "assets.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  {bundle.name}: {len(entries)} assets"
          + (f", {missed} captions without a matching cluster" if missed else ""),
          file=sys.stderr)
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundle", type=Path, nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", type=Path, default=MARKDOWN,
                    help="Markdown出力の根directory（assetsはその文書folderの中）")
    args = ap.parse_args()
    sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
    import convert_all  # noqa: PLC0415
    jobs = {job["name"]: job for job in convert_all.targets()}
    if args.all:
        for name, job in jobs.items():
            render_document(BUNDLES / name, job["pdf"], args.out / name)
        return 0
    if not args.bundle:
        ap.error("give a bundle path or --all")
    job = jobs[args.bundle.name]
    render_document(args.bundle, job["pdf"], args.out / args.bundle.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
