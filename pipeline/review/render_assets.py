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

1. 表の外にあるgeometry層の描画要素（line/rect/curve/image）を縦に走査し、
   15ptを超える空隙でクラスタに分ける
2. 8要素以上、または高さ40pt以上のクラスタだけを図の候補にする
   （文の下線などの小さな飾りを弾く）
3. 図のcaption行（`Figure N-N`／`图N-N`）に、**caption直下**のクラスタを
   優先して対応付ける（WCHの版面はcaptionが図の上。無ければ直上を試す）
4. 領域はクラスタのbboxに、縦に重なる文字の行（図中ラベル）を合成して4pt広げる
5. caption行を跨がないようにclipして150dpiで描画する

対応するクラスタが無いcaptionは**そのまま**（exporterの「再現していない」警告が
残る——取りこぼしを隠さない）。caption を持たない大きめのraster画像
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
import re
import sys
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parents[2]
BUNDLES = REPO / ".cache" / "structured-bundles"
MARKDOWN = REPO / ".cache" / "structured-markdown"

FIGURE_CAPTION = re.compile(r"^(?:Figure|图)\s*\d+(?:-\d+)*", re.IGNORECASE)
GAP = 15.0           # pt。これを超える縦の空隙でクラスタを分ける
MIN_ELEMENTS = 8     # クラスタが図と呼べる最小の要素数
MIN_HEIGHT = 40.0    # または最小の高さ（pt）
NEAR = 100.0         # captionとクラスタの最大距離（pt）
PAD = 4.0
LARGE_IMAGE = 40.0
RESOLUTION = 150


def load_page(bundle: Path, entry: dict) -> tuple[dict, dict]:
    payload = (bundle / entry["file"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
    geometry_payload = (bundle / entry["geometry_file"]).read_bytes()
    if hashlib.sha256(geometry_payload).hexdigest() != entry["geometry_sha256"]:
        raise SystemExit(f"{bundle}/{entry['geometry_file']}: hash differs from manifest")
    return json.loads(payload), json.loads(gzip.decompress(geometry_payload))


def graphic_clusters(page: dict, geometry: dict) -> list[dict]:
    boxes = [t["bbox"] for t in page["tables"]]

    def in_table(d: dict) -> bool:
        cx = (d["bbox"][0] + d["bbox"][2]) / 2
        cy = (d["bbox"][1] + d["bbox"][3]) / 2
        return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)

    items = sorted((d for d in geometry["drawings"] if not in_table(d)),
                   key=lambda d: d["bbox"][1])
    clusters: list[dict] = []
    for d in items:
        x0, top, x1, bottom = d["bbox"]
        if clusters and top - clusters[-1]["bbox"][3] <= GAP:
            c = clusters[-1]
            c["bbox"] = [min(c["bbox"][0], x0), min(c["bbox"][1], top),
                         max(c["bbox"][2], x1), max(c["bbox"][3], bottom)]
            c["count"] += 1
        else:
            clusters.append({"bbox": [x0, top, x1, bottom], "count": 1})
    return [c for c in clusters
            if c["count"] >= MIN_ELEMENTS
            or c["bbox"][3] - c["bbox"][1] >= MIN_HEIGHT]


def expand_with_labels(page: dict, bbox: list[float]) -> list[float]:
    """クラスタに縦へ重なる文字の行（図中ラベル）を領域へ合成する。"""
    x0, top, x1, bottom = bbox
    for line in page["lines"]:
        if line.get("role") in ("header", "footer"):
            continue
        if FIGURE_CAPTION.match(line["text"].strip()):
            continue
        lt, lb = line["bbox"][1], line["bbox"][3]
        if lb < top or lt > bottom:
            continue
        x0 = min(x0, line["bbox"][0])
        x1 = max(x1, line["bbox"][2])
        top = min(top, lt)
        bottom = max(bottom, lb)
    return [x0, top, x1, bottom]


def figure_regions(page: dict, geometry: dict) -> tuple[list[tuple[str, list[float]]],
                                                        list[str]]:
    """caption行 → 図領域。(caption line id, bbox)のリストと、当たらなかった
    caption line idのリストを返す。"""
    captions = [line for line in page["lines"]
                if line.get("role") not in ("header", "footer")
                and FIGURE_CAPTION.match(line["text"].strip())]
    if not captions:
        return [], []
    clusters = graphic_clusters(page, geometry)
    taken: set[int] = set()
    found: list[tuple[str, list[float]]] = []
    missed: list[str] = []
    for caption in sorted(captions, key=lambda c: c["bbox"][1]):
        c_top, c_bottom = caption["bbox"][1], caption["bbox"][3]

        def pick(below: bool) -> int | None:
            best, best_gap = None, NEAR
            for index, cluster in enumerate(clusters):
                if index in taken:
                    continue
                gap = (cluster["bbox"][1] - c_bottom if below
                       else c_top - cluster["bbox"][3])
                # 少しの重なり（-5pt）は許す。captionの行間に図の枠が食い込む版面がある
                if -5 <= gap <= best_gap:
                    best, best_gap = index, max(gap, 0.0)
            return best

        chosen = pick(below=True)
        if chosen is None:
            chosen = pick(below=False)
        if chosen is None:
            missed.append(caption["id"])
            continue
        taken.add(chosen)
        bbox = expand_with_labels(page, list(clusters[chosen]["bbox"]))
        # caption行を跨がない
        if bbox[1] >= c_bottom:            # 図は下
            bbox[1] = max(bbox[1], c_bottom + 1)
        elif bbox[3] <= c_top:             # 図は上
            bbox[3] = min(bbox[3], c_top - 1)
        found.append((caption["id"], bbox))
    return found, missed


def render_document(bundle: Path, pdf_path: Path, out_doc: Path) -> dict:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    source_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if manifest["source"]["sha256"] != source_sha:
        raise SystemExit(f"{bundle}: bundle was converted from a different original")
    assets_dir = out_doc / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    missed_total = 0
    with pdfplumber.open(pdf_path) as pdf:
        for entry in manifest["pages"]:
            page, geometry = load_page(bundle, entry)
            regions, missed = figure_regions(page, geometry)
            missed_total += len(missed)
            covered: list[list[float]] = [bbox for _, bbox in regions]
            for image in page["images"]:
                x0, top, x1, bottom = image["bbox"]
                if x1 - x0 < LARGE_IMAGE or bottom - top < LARGE_IMAGE:
                    continue
                cx, cy = (x0 + x1) / 2, (top + bottom) / 2
                if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in covered):
                    continue          # 図領域が既に含む
                regions.append((image["id"], [x0, top, x1, bottom]))
            if not regions:
                continue
            pdf_page = pdf.pages[page["number"] - 1]
            for key, bbox in regions:
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
                payload = (assets_dir / name).read_bytes()
                entries[key] = {
                    "file": f"assets/{name}",
                    "page": page["number"],
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
          + (f", {missed_total} captions without a matching cluster" if missed_total else ""),
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
