#!/usr/bin/env python3
"""PDF全ページ → 構造化bundle（本番converter。D18工程1）。

PoCの`tools/document_converter.py`を出発点に、D17の調査
（docs/structured-migration-survey.ja.md）が特定した2つの欠陥を直したもの。

1. **決定性**——pdfminerはinline imageに`id()`（メモリアドレス）由来の名前を
   付けるので、そのまま写すと同一入力でもbundleが毎回変わる（D17実測:
   1,042ページ中14ページ）。数字だけの長い名前は**捨てる**——converter自身の
   安定ID（`p66-draw-image-00002`）が既に識別子で、実在するXObject名
   （`Im1`等）だけを`name`に残す。
2. **header/footerの検出**——PoCのy閾値（上6%・下94%）はzh版のfooter
   （下端比93.8%）を系統的に取りこぼした。本文はページ高90%の位置まで来るので
   閾値は緩めず、**反復ベース**を足す: 全ページを先に1回歩き、上下12%の帯で
   「数字を`#`に畳んだ同じ綴りが同じ高さに、全ページの25%以上（最低3ページ）
   繰り返し現れる」行を集め、その行だけ帯を12%まで広げて判定する。

出力は2系統:
- **bundle**（`.cache/structured-bundles/<stem>.<lang>/`）——非保存の導出物。
  同一原本＋同一engine＋同一converterでbyte一致に再生成できる
- **manifest**（`structured/<stem>.<lang>/manifest.json`）——コミットする正本。
  原本SHA-256と全page/geometryのSHA-256を持ち、再生成bundleとの突き合わせで
  「どのpageがいつからズレたか」をpage単位で言える

review sidecar（人の判断）は`structured/<stem>.<lang>/review.json`が正本で、
再変換はそれを上書きしない（bundle内のreview.jsonはcacheへの写し）。

実行:
    uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import statistics
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

import jsonschema
import pdfplumber

REPO = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "0.2"
CONVERTER_VERSION = "1.0.0"
DEFAULT_BUNDLES = REPO / ".cache" / "structured-bundles"
DEFAULT_STRUCTURED = REPO / "structured"
MANIFEST_SCHEMA = REPO / "schemas" / "structured-document-manifest.schema.json"
PAGE_SCHEMA = REPO / "schemas" / "structured-document-page.schema.json"
REVIEW_SCHEMA = REPO / "schemas" / "structured-document-review.schema.json"

HEADING_NUMBER = re.compile(r"^(?P<number>\d+(?:\.\d+)+)\s+\S")
CHAPTER_HEADING = re.compile(r"^(?:第\s*\d+\s*章|Chapter\s+\d+)", re.I)
LIST_ITEM = re.compile(r"^(?:[•●▪◆◇*-]|\(\d+\)|[a-z]\))\s*")
TABLE_NUMBER = {
    "en": re.compile(r"Table\s+(\d+(?:-\d+)+)", re.I),
    "zh": re.compile(r"表\s*(\d+(?:-\d+)+)"),
}

# 反復ベースのheader/footer判定の帯と敷居。厳格帯（6%/94%）はPoCと同じで、
# 拡張帯（12%/88%）は反復が裏付ける行だけに適用する。
STRICT_BAND = 0.06
REPEAT_BAND = 0.12
REPEAT_FLOOR = 3
REPEAT_RATIO = 0.25


def dump_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


_VALIDATORS: dict[Path, jsonschema.Draft202012Validator] = {}


def validate(value: dict, schema_path: Path) -> None:
    validator = _VALIDATORS.get(schema_path)
    if validator is None:
        validator = jsonschema.Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8")))
        _VALIDATORS[schema_path] = validator
    validator.validate(value)


def validate_geometry(value: dict) -> None:
    """精密層の封筒だけを見る（全文字のDraft-2020検査は大型RMで1時間を超える）。"""
    if set(value) != {"schema_version", "source_sha256", "number", "chars", "drawings"}:
        raise ValueError("precision geometry has unexpected or missing keys")
    if value["schema_version"] != SCHEMA_VERSION or len(value["source_sha256"]) != 64:
        raise ValueError("precision geometry has invalid identity")
    if not isinstance(value["number"], int) or value["number"] < 1:
        raise ValueError("precision geometry has invalid page number")
    if not isinstance(value["chars"], list) or not isinstance(value["drawings"], list):
        raise ValueError("precision geometry arrays are invalid")


def rounded_box(box) -> list[float]:
    return [round(float(value), 3) for value in box]


def margin_key(text: str, edge_distance: float) -> tuple[str, float]:
    """反復判定の鍵。数字を畳む（ページ番号・版番号が変わっても同じ行）＋
    **ページの縁からの距離**（絶対yではなく。横向きページでも running footer は
    下端から同じ距離に印字される）。"""
    return (re.sub(r"\s+", " ", re.sub(r"\d+", "#", text)).strip(),
            round(edge_distance, 1))


def margin_repeats(pdf) -> tuple[set, set]:
    """第1パス: 上下の帯で全ページの25%以上に同位置・同形で繰り返す行を集める。"""
    top_pages: dict[tuple, set[int]] = defaultdict(set)
    bottom_pages: dict[tuple, set[int]] = defaultdict(set)
    for page in pdf.pages:
        height = float(page.height)
        for line in page.extract_text_lines(return_chars=False) or []:
            if line["top"] < height * REPEAT_BAND:
                top_pages[margin_key(line["text"], line["top"])].add(page.page_number)
            if line["bottom"] > height * (1 - REPEAT_BAND):
                bottom_pages[margin_key(line["text"], height - line["bottom"])].add(
                    page.page_number)
        page.flush_cache()
    threshold = max(REPEAT_FLOOR, int(len(pdf.pages) * REPEAT_RATIO))
    repeated_top = {key for key, pages in top_pages.items() if len(pages) >= threshold}
    repeated_bottom = {key for key, pages in bottom_pages.items() if len(pages) >= threshold}
    return repeated_top, repeated_bottom


def text_items(page, kind: str) -> list[dict]:
    source = (page.extract_text_lines(return_chars=False) if kind == "line"
              else page.extract_words())
    out = []
    for index, item in enumerate(source or [], 1):
        out.append({
            "id": f"p{page.page_number}-{kind}-{index:05d}",
            "text": item["text"],
            "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
        })
    return out


def chars(page) -> list[dict]:
    out = []
    for index, item in enumerate(page.chars, 1):
        out.append({
            "id": f"p{page.page_number}-char-{index:06d}",
            "text": item.get("text", ""),
            "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
            "font": str(item.get("fontname") or ""),
            "size": round(float(item.get("size") or 0), 3),
            "upright": bool(item.get("upright", True)),
        })
    return out


def classify_lines(lines: list[dict], page_chars: list[dict], height: float,
                   repeated_top: set, repeated_bottom: set) -> None:
    sizes = [item["size"] for item in page_chars
             if item["text"].strip() and item["size"] > 0]
    body_size = statistics.median(sizes) if sizes else 0
    for line in lines:
        x0, top, x1, bottom = line["bbox"]
        members = [item for item in page_chars
                   if item["bbox"][2] >= x0 and item["bbox"][0] <= x1
                   and item["bbox"][3] >= top and item["bbox"][1] <= bottom]
        line_sizes = [item["size"] for item in members if item["text"].strip()]
        line["font_size"] = round(statistics.median(line_sizes), 3) if line_sizes else 0
        named = [item for item in members if item["text"].strip()]
        line["bold"] = bool(named) and sum(
            "bold" in item["font"].lower() for item in named) >= len(named) / 2
        text = line["text"].strip()
        numbered = HEADING_NUMBER.match(text)
        # 反復する余白行はheading判定より先に決める——TOC等の小さい本文フォントの
        # ページでは、footerの9ptが「本文中央値の1.25倍」を満たしてheadingに
        # 化けることがある（D18実装時にV003 zhの3ページで実測）。全ページの
        # 25%以上で同じ縁距離に繰り返す行が見出しであることはない。
        if (top < height * REPEAT_BAND
                and margin_key(line["text"], top) in repeated_top):
            line["role"] = "header"
        elif (bottom > height * (1 - REPEAT_BAND)
                and margin_key(line["text"], height - bottom) in repeated_bottom):
            line["role"] = "footer"
        elif CHAPTER_HEADING.match(text) or numbered or (
                len(text) <= 120 and body_size and line["font_size"] >= body_size * 1.25):
            line["role"] = "heading"
            line["level"] = (min(6, numbered.group("number").count(".") + 1)
                             if numbered else 1)
        elif top < height * STRICT_BAND:
            line["role"] = "header"
        elif bottom > height * (1 - STRICT_BAND):
            line["role"] = "footer"
        elif LIST_ITEM.match(text):
            line["role"] = "list-item"
        else:
            line["role"] = "paragraph"


def drawings(page) -> list[dict]:
    out = []
    for kind in ("line", "rect", "curve", "image"):
        for index, item in enumerate(getattr(page, f"{kind}s"), 1):
            record = {
                "id": f"p{page.page_number}-draw-{kind}-{index:05d}",
                "type": kind,
                "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
            }
            if kind == "image":
                name = str(item.get("name") or "")
                # pdfminerはinline imageへid()由来の数字名を付ける（process毎に
                # 変わる）。実在するresource名だけを残す——安定IDは`id`が持つ。
                if name and not (name.isdigit() and len(name) >= 10):
                    record["name"] = name
                size = item.get("srcsize")
                if size and len(size) == 2:
                    record["source_size"] = [int(size[0]), int(size[1])]
            out.append(record)
    return out


def overlap_issues(cells: list[dict]) -> list[str]:
    occupied: dict[tuple[int, int], str] = {}
    overlaps = []
    for cell in cells:
        for row in range(cell["row_start"], cell["row_end"]):
            for column in range(cell["column_start"], cell["column_end"]):
                previous = occupied.get((row, column))
                if previous:
                    overlaps.append(f"{cell['id']} overlaps {previous} at {row},{column}")
                occupied[(row, column)] = cell["id"]
    return overlaps


def cell_text(page, bbox) -> str:
    # `Table.extract()`は結合セルを矩形行列に平坦化する。物理セルの矩形で
    # cropし、rowspan/colspanを持つセルに文字を残す。
    return (page.crop(bbox).extract_text(x_tolerance=3, y_tolerance=3) or "").strip()


def physical_cells(page, table, table_id: str) -> tuple[list[dict], int, int]:
    xs = sorted({round(value, 6) for cell in table.cells for value in (cell[0], cell[2])})
    ys = sorted({round(value, 6) for cell in table.cells for value in (cell[1], cell[3])})
    x_index = {value: index for index, value in enumerate(xs)}
    y_index = {value: index for index, value in enumerate(ys)}
    cells = []
    for index, bbox in enumerate(sorted(table.cells, key=lambda box: (box[1], box[0])), 1):
        x0, top, x1, bottom = (round(value, 6) for value in bbox)
        cells.append({
            "id": f"{table_id}-cell-{index:04d}",
            "row_start": y_index[top],
            "row_end": y_index[bottom],
            "column_start": x_index[x0],
            "column_end": x_index[x1],
            "bbox": rounded_box(bbox),
            "text": cell_text(page, bbox),
        })
    return cells, len(ys) - 1, len(xs) - 1


def captions(lines: list[dict], lang: str) -> list[dict]:
    found = []
    for line in lines:
        match = TABLE_NUMBER[lang].search(line["text"])
        if match:
            found.append({
                "line_id": line["id"],
                "source_number": match.group(1),
                "text": line["text"],
                "top": line["bbox"][1],
            })
    return found


def page_record(page, lang: str, source_sha256: str,
                previous_logical_id: str | None,
                previous_page: int | None,
                number_occurrences: dict[str, int],
                repeated_top: set, repeated_bottom: set) -> tuple[dict, dict, str | None]:
    page_chars = chars(page)
    lines = text_items(page, "line")
    classify_lines(lines, page_chars, float(page.height), repeated_top, repeated_bottom)
    words = text_items(page, "word")
    page_drawings = drawings(page)
    page_captions = captions(lines, lang)
    detected = sorted(page.find_tables(), key=lambda item: (item.bbox[1], item.bbox[0]))
    tables = []
    previous_bottom = 0.0
    for table_index, table in enumerate(detected, 1):
        candidates = [item for item in page_captions
                      if previous_bottom <= item["top"] < table.bbox[1]]
        caption = candidates[-1] if candidates else None
        if caption:
            number = caption["source_number"]
            occurrence = number_occurrences.get(number, 0) + 1
            number_occurrences[number] = occurrence
            logical_id = f"table-{number}@{occurrence}"
            previous_logical_id = logical_id
            caption_record = {key: caption[key]
                              for key in ("line_id", "source_number", "text")}
            continues = False
        else:
            consecutive = previous_page is not None and page.page_number == previous_page + 1
            logical_id = (previous_logical_id if consecutive and previous_logical_id
                          else f"unlabelled-p{page.page_number}-{table_index}")
            caption_record = None
            continues = bool(consecutive and previous_logical_id)
        table_id = f"p{page.page_number}-table-{table_index:03d}"
        cells, row_count, column_count = physical_cells(page, table, table_id)
        tables.append({
            "id": table_id,
            "logical_id": logical_id,
            "bbox": rounded_box(table.bbox),
            "caption": caption_record,
            "continues_from_previous": continues,
            "row_count": row_count,
            "column_count": column_count,
            # 平坦化行（pdfplumber互換）と物理セルの両方を保つ——結合セルの
            # 表で答える問いが違い、既存抽出器の無損失移行に両方要る。
            "extracted_rows": table.extract(),
            "row_cells": [[rounded_box(cell) if cell is not None else None
                           for cell in row.cells] for row in table.rows],
            "cells": cells,
            "issues": overlap_issues(cells),
        })
        previous_bottom = table.bbox[3]

    def outside_tables(line: dict) -> bool:
        x0, top, x1, bottom = line["bbox"]
        center_x, center_y = (x0 + x1) / 2, (top + bottom) / 2
        return not any(table["bbox"][0] <= center_x <= table["bbox"][2]
                       and table["bbox"][1] <= center_y <= table["bbox"][3]
                       for table in tables)

    order = ([{"id": line["id"], "type": "line", "bbox": line["bbox"]}
              for line in lines if outside_tables(line)]
             + [{"id": table["id"], "type": "table", "bbox": table["bbox"]}
                for table in tables]
             + [{"id": item["id"], "type": "image", "bbox": item["bbox"]}
                for item in page_drawings if item["type"] == "image"])
    order.sort(key=lambda item: (item["bbox"][1], item["bbox"][0], item["type"]))
    record = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "number": page.page_number,
        "width": round(float(page.width), 3),
        "height": round(float(page.height), 3),
        "rotation": int(getattr(page, "rotation", 0) or 0),
        "text": page.extract_text() or "",
        "lines": lines,
        "words": words,
        "images": [item for item in page_drawings if item["type"] == "image"],
        "tables": tables,
        "reading_order": order,
    }
    geometry = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "number": page.page_number,
        "chars": page_chars,
        "drawings": page_drawings,
    }
    return record, geometry, previous_logical_id


def convert(pdf_path: Path, lang: str, document_type: str,
            bundles: Path = DEFAULT_BUNDLES,
            structured: Path = DEFAULT_STRUCTURED) -> Path:
    source_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    name = f"{pdf_path.stem}.{lang}"
    bundle = bundles / name
    committed = structured / name

    # review の正本はコミット側。原本が変わっていたら流用せず止まる
    # （D16「原本更新時に古いreviewを自動流用しない」）。
    committed_review = committed / "review.json"
    if committed_review.exists():
        review = json.loads(committed_review.read_text(encoding="utf-8"))
        validate(review, REVIEW_SCHEMA)
        if review["source_sha256"] != source_sha256:
            raise ValueError(f"{committed_review}: source hash differs; "
                             "review it against the new original before reconversion")
    else:
        review = {
            "schema_version": SCHEMA_VERSION,
            "source_sha256": source_sha256,
            "status": "unreviewed",
            "decisions": {},
        }
        validate(review, REVIEW_SCHEMA)

    page_dir = bundle / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir = bundle / "geometry"
    geometry_dir.mkdir(parents=True, exist_ok=True)

    page_entries = []
    number_occurrences: dict[str, int] = {}
    previous_logical_id = None
    previous_page = None
    with pdfplumber.open(pdf_path) as pdf:
        repeated_top, repeated_bottom = margin_repeats(pdf)
        for page in pdf.pages:
            record, geometry, previous_logical_id = page_record(
                page, lang, source_sha256, previous_logical_id,
                previous_page, number_occurrences, repeated_top, repeated_bottom)
            validate(record, PAGE_SCHEMA)
            validate_geometry(geometry)
            payload = dump_bytes(record)
            geometry_payload = gzip.compress(dump_bytes(geometry), compresslevel=9, mtime=0)
            relative = Path("pages") / f"{page.page_number:04d}.json"
            geometry_relative = Path("geometry") / f"{page.page_number:04d}.json.gz"
            (bundle / relative).write_bytes(payload)
            (bundle / geometry_relative).write_bytes(geometry_payload)
            page_entries.append({
                "number": page.page_number,
                "file": relative.as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "geometry_file": geometry_relative.as_posix(),
                "geometry_sha256": hashlib.sha256(geometry_payload).hexdigest(),
                "width": record["width"],
                "height": record["height"],
            })
            previous_page = page.page_number
            page.flush_cache()
        page_count = len(pdf.pages)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "document": pdf_path.name,
            "document_type": document_type,
            "language": lang,
            "sha256": source_sha256,
            "page_count": page_count,
        },
        "conversion": {
            "engine": "pdfplumber",
            "engine_version": version("pdfplumber"),
            "converter_version": CONVERTER_VERSION,
            "coordinates": "PDF points, origin at top-left",
            "scope": "all-pages",
            "table_settings": {},
        },
        "pages": page_entries,
    }
    validate(manifest, MANIFEST_SCHEMA)
    payload = dump_bytes(manifest)
    (bundle / "manifest.json").write_bytes(payload)
    committed.mkdir(parents=True, exist_ok=True)
    (committed / "manifest.json").write_bytes(payload)
    # bundle側のreview.jsonは正本（structured/）の写し。検査toolが読む。
    (bundle / "review.json").write_bytes(dump_bytes(review))
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--lang", choices=("zh", "en"), required=True)
    parser.add_argument(
        "--document-type",
        choices=("datasheet", "reference-manual", "core-manual",
                 "package-drawing", "other", "unknown"),
        default="unknown")
    parser.add_argument("--out", type=Path, default=DEFAULT_BUNDLES,
                        help="bundleの出力先の上書き（試験用）")
    parser.add_argument("--structured", type=Path, default=DEFAULT_STRUCTURED,
                        help="コミットするmanifest/reviewの置き場の上書き（試験用）")
    args = parser.parse_args()
    bundle = convert(args.pdf, args.lang, args.document_type, args.out, args.structured)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    print(f"{bundle}: {len(manifest['pages'])}/{manifest['source']['page_count']} pages "
          f"(converter {CONVERTER_VERSION})")


if __name__ == "__main__":
    main()
