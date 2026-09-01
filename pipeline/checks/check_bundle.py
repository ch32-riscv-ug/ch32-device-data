#!/usr/bin/env python3
"""本番bundleの独立検証ゲート（PoCのtools/check_document_bundle.pyのfork）。

PoC版との違いは1点: **geometry_sha256は非圧縮のJSONに対するhash**。gzipの
圧縮バイト列はzlibの版で変わり、GitHub Actions上の再変換で全ページの
geometry_sha256だけが不一致になった（2026-09-01、structured-repro.ymlが検出）。
圧縮は保存の都合であって内容ではない。converter 1.1.0以降のbundle用。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[2]

MANIFEST_SCHEMA = REPO / "schemas" / "structured-document-manifest.schema.json"
PAGE_SCHEMA = REPO / "schemas" / "structured-document-page.schema.json"
GEOMETRY_SCHEMA = REPO / "schemas" / "structured-document-geometry.schema.json"
REVIEW_SCHEMA = REPO / "schemas" / "structured-document-review.schema.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_VALIDATORS: dict[Path, jsonschema.Draft202012Validator] = {}


def validate(value: dict, schema_path: Path) -> None:
    validator = _VALIDATORS.get(schema_path)
    if validator is None:
        validator = jsonschema.Draft202012Validator(load(schema_path))
        _VALIDATORS[schema_path] = validator
    validator.validate(value)


def validate_geometry(value: dict, path: Path) -> None:
    required = {"schema_version", "source_sha256", "number", "chars", "drawings"}
    if set(value) != required:
        raise ValueError(f"{path}: precision geometry has unexpected or missing keys")
    if value["schema_version"] != "0.2":
        raise ValueError(f"{path}: unsupported precision geometry version")
    if not isinstance(value["chars"], list) or not isinstance(value["drawings"], list):
        raise ValueError(f"{path}: precision geometry arrays are invalid")


def inside(bbox: list[float], width: float, height: float) -> bool:
    x0, top, x1, bottom = bbox
    # PDF content streams legitimately contain crop marks, clipped glyphs and
    # drawing endpoints just outside the media box.  Reject gross coordinate
    # errors while allowing the small bleed present in the source documents.
    tolerance = max(10.0, width * 0.01, height * 0.01)
    return (-tolerance <= x0 <= x1 <= width + tolerance
            and -tolerance <= top <= bottom <= height + tolerance)


def check(bundle: Path, source: Path | None = None,
          require_all_pages: bool = True) -> tuple[int, int]:
    manifest_path = bundle / "manifest.json"
    manifest = load(manifest_path)
    validate(manifest, MANIFEST_SCHEMA)
    source_meta = manifest["source"]

    if require_all_pages and manifest["conversion"]["scope"] != "all-pages":
        raise ValueError(f"{bundle}: excerpt bundle cannot feed production extraction")
    page_numbers = [entry["number"] for entry in manifest["pages"]]
    expected = list(range(1, source_meta["page_count"] + 1))
    if manifest["conversion"]["scope"] == "all-pages" and page_numbers != expected:
        raise ValueError(f"{bundle}: pages are not the complete ordered range")
    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError(f"{bundle}: duplicate page numbers")

    if source is not None:
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != source_meta["sha256"]:
            raise ValueError(f"{source}: source hash differs from manifest")
        if source.name != source_meta["document"]:
            raise ValueError(f"{source}: filename differs from manifest")

    all_ids: set[str] = set()
    warnings = 0
    for entry in manifest["pages"]:
        page_path = bundle / entry["file"]
        payload = page_path.read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != entry["sha256"]:
            raise ValueError(f"{page_path}: content hash differs from manifest")
        page = json.loads(payload)
        validate(page, PAGE_SCHEMA)
        geometry_raw = gzip.decompress((bundle / entry["geometry_file"]).read_bytes())
        # hashは非圧縮のJSONに対して（gzipのバイト列はzlibの版で変わる）
        if hashlib.sha256(geometry_raw).hexdigest() != entry["geometry_sha256"]:
            raise ValueError(f"{bundle / entry['geometry_file']}: content hash differs from manifest")
        geometry = json.loads(geometry_raw)
        validate_geometry(geometry, bundle / entry["geometry_file"])
        if page["source_sha256"] != source_meta["sha256"]:
            raise ValueError(f"{page_path}: source hash differs from manifest")
        if page["number"] != entry["number"]:
            raise ValueError(f"{page_path}: page number differs from manifest")
        if page["width"] != entry["width"] or page["height"] != entry["height"]:
            raise ValueError(f"{page_path}: dimensions differ from manifest")

        local_ids: set[str] = set()
        if geometry["source_sha256"] != source_meta["sha256"] or geometry["number"] != page["number"]:
            raise ValueError(f"{bundle / entry['geometry_file']}: identity differs from page")
        objects = page["lines"] + page["words"] + geometry["chars"] + geometry["drawings"]
        for item in objects:
            if not isinstance(item.get("id"), str) or not isinstance(item.get("bbox"), list):
                raise ValueError(f"{page_path}: invalid precision object")
            if len(item["bbox"]) != 4 or not all(isinstance(v, (int, float)) for v in item["bbox"]):
                raise ValueError(f"{page_path}: invalid bbox for {item['id']}")
            if item["id"] in all_ids or item["id"] in local_ids:
                raise ValueError(f"{page_path}: duplicate id {item['id']}")
            local_ids.add(item["id"])
            x0, top, x1, bottom = item["bbox"]
            if x0 > x1 or top > bottom:
                raise ValueError(f"{page_path}: inverted bbox for {item['id']}")
        # Individual glyphs and drawing commands can intentionally lie far
        # outside the media box (clipping and rotated text).  User-visible
        # text/image blocks, however, must be on the page.
        for item in page["lines"] + page["words"] + page["images"]:
            if not inside(item["bbox"], page["width"], page["height"]):
                raise ValueError(f"{page_path}: out-of-page bbox for {item['id']}")
        for table in page["tables"]:
            if table["id"] in all_ids or table["id"] in local_ids:
                raise ValueError(f"{page_path}: duplicate id {table['id']}")
            local_ids.add(table["id"])
            if not inside(table["bbox"], page["width"], page["height"]):
                raise ValueError(f"{page_path}: out-of-page bbox for {table['id']}")
            for cell in table["cells"]:
                if cell["row_start"] >= cell["row_end"] or cell["row_end"] > table["row_count"]:
                    raise ValueError(f"{page_path}: invalid row span for {cell['id']}")
                if (cell["column_start"] >= cell["column_end"]
                        or cell["column_end"] > table["column_count"]):
                    raise ValueError(f"{page_path}: invalid column span for {cell['id']}")
                if not inside(cell["bbox"], page["width"], page["height"]):
                    raise ValueError(f"{page_path}: out-of-page bbox for {cell['id']}")
            warnings += len(table["issues"])
        all_ids.update(local_ids)
        order_ids = {item["id"] for item in page["reading_order"]}
        def outside_tables(line: dict) -> bool:
            x0, top, x1, bottom = line["bbox"]
            center_x, center_y = (x0 + x1) / 2, (top + bottom) / 2
            return not any(table["bbox"][0] <= center_x <= table["bbox"][2]
                           and table["bbox"][1] <= center_y <= table["bbox"][3]
                           for table in page["tables"])
        known_order_ids = ({item["id"] for item in page["lines"] if outside_tables(item)}
                           | {item["id"] for item in page["tables"]}
                           | {item["id"] for item in page["images"]
                              if item["type"] == "image"})
        if order_ids != known_order_ids:
            raise ValueError(f"{page_path}: reading_order is incomplete or has unknown ids")

    review = load(bundle / "review.json")
    validate(review, REVIEW_SCHEMA)
    if review["source_sha256"] != source_meta["sha256"]:
        raise ValueError(f"{bundle / 'review.json'}: source hash differs from manifest")
    unknown_decisions = set(review["decisions"]) - all_ids
    if unknown_decisions:
        raise ValueError(f"{bundle / 'review.json'}: unknown ids {sorted(unknown_decisions)}")
    return len(manifest["pages"]), warnings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--allow-excerpt", action="store_true")
    args = parser.parse_args()
    pages, warnings = check(args.bundle, args.source, not args.allow_excerpt)
    manifest = load(args.bundle / "manifest.json")
    print(f"OK: {manifest['source']['document']} "
          f"({manifest['source']['document_type']}, {pages} pages, "
          f"{warnings} recorded table issues, review="
          f"{load(args.bundle / 'review.json')['status']})")


if __name__ == "__main__":
    main()
