#!/usr/bin/env python3
"""Regenerate tables/documents.csv from manifests/documents.json.

Standard library only, because the daily catalogue workflow runs it right after
sync_catalog.py: the catalogue is the one input of the normalised tables that
changes without a person touching the repository, so its CSV projection must
follow in the same commit or silently go stale.

A name like CH32L103DS0.PDF locates nothing on its own; each row carries the
original page and download URL on both language sites plus the mirror copy, so
every document reference in the other tables joins to something fetchable.

Usage:
    python3 tools/build_documents.py [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
DOCUMENTS = REPO / "manifests" / "documents.json"

# URL shapes verified live on 2026-08-18; a red daily run is the signal that
# one of them moved.
PAGE_URL = {"zh": "https://www.wch.cn/downloads/{stem}_{ext}.html",
            "en": "https://www.wch-ic.com/downloads/{stem}_{ext}.html"}
DOWNLOAD_URL = {"zh": "https://file.wch.cn/download/file?id={id}",
                "en": "https://www.wch-ic.com/download/file?id={id}"}
# GitHub Pages, not raw.githubusercontent: Pages serves PDFs inline with the
# right content type, raw forces a download. Requires Pages enabled per mirror.
MIRROR_PDF = "https://ch32-riscv-ug.github.io/{repo}/datasheet_{lang}/{name}"
MIRROR_EVT = "https://github.com/ch32-riscv-ug/{repo}/tree/main/EVT"

DOCUMENT_COLUMNS = [
    "document", "kind", "status", "repositories", "version_zh", "version_en",
    "page_url_zh", "page_url_en", "download_url_zh", "download_url_en",
    "mirror_url_zh", "mirror_url_en",
]


def document_rows() -> list[dict]:
    data = json.loads(DOCUMENTS.read_text(encoding="utf-8"))
    items = data["documents"] if isinstance(data, dict) else data
    out = []
    for doc in sorted(items, key=lambda d: d["name"]):
        name = doc["name"]
        stem, _, ext = name.rpartition(".")
        repos = sorted(doc.get("repositories", []))
        entry = {
            "document": name,
            "kind": doc.get("kind", ""),
            "status": doc.get("status", ""),
            "repositories": ";".join(repos),
        }
        for lang in ("zh", "en"):
            source = doc.get("sources", {}).get(lang)
            entry[f"version_{lang}"] = (source or {}).get("version", "")
            entry[f"page_url_{lang}"] = \
                PAGE_URL[lang].format(stem=stem, ext=ext) if source else ""
            entry[f"download_url_{lang}"] = \
                DOWNLOAD_URL[lang].format(id=source["file_id"]) if source else ""
            if not repos or not source:
                entry[f"mirror_url_{lang}"] = ""
            elif ext.upper() == "ZIP":
                # The archive itself is not committed; the mirror holds the tree.
                entry[f"mirror_url_{lang}"] = MIRROR_EVT.format(repo=repos[0])
            else:
                entry[f"mirror_url_{lang}"] = MIRROR_PDF.format(
                    repo=repos[0], lang=lang, name=name)
        out.append(entry)
    return out


def write(out_dir: Path) -> int:
    rows = document_rows()
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "documents.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DOCUMENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{out_dir}/documents.csv: {len(rows)} 行", file=sys.stderr)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
    args = ap.parse_args()
    write(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
