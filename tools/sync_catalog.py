#!/usr/bin/env python3
"""Keep the document catalogue in step with WCH's own file listing.

WCH publishes a search API that returns, for every document, its download id per
language, its version, and the products it covers. This queries both sites,
compares the answer with `manifests/documents.json`, and reports what changed.

The two sites are separate sources: the Chinese site is the original and the
English one a translation, so a document can exist in one and not the other, and
their versions can differ. Both ids are kept per document.

Which repository a document belongs to is a human decision -- CH32V007DS0 also
covers CH32M007, CH32xRM covers both CH32F103 and CH32V103, and a product with its
own reference manual needs a new mirror. Existing assignments are therefore never
overwritten; anything new is reported as unassigned.

Usage:
    uv run tools/sync_catalog.py              # report differences
    uv run tools/sync_catalog.py --write      # apply them, keeping assignments
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "documents.json"

SITES = {
    "en": ("https://wch-ic.com", "https://www.wch-ic.com/download/file?id={id}"),
    "zh": ("https://www.wch.cn", "https://file.wch.cn/download/file?id={id}"),
}
SEARCH = "/api/official/website/common/search?searchStr={q}&type=all&pageNum=1&pageSize=500"
QUERIES = ("CH32",)
TIMEOUT = 120


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def walk_files(node, out: list) -> None:
    """The API nests files under document categories."""
    if isinstance(node, dict):
        out.extend(node.get("fileList") or [])
        for child in node.get("childCategoriesVOList") or []:
            walk_files(child, out)
    elif isinstance(node, list):
        for child in node:
            walk_files(child, out)


def survey() -> dict[str, dict]:
    """Every document each site lists, keyed by upper-case file name."""
    found: dict[str, dict] = {}
    for lang, (base, _) in SITES.items():
        for query in QUERIES:
            data = fetch_json(base + SEARCH.format(q=urllib.parse.quote(query)))["data"]
            files: list = []
            walk_files(data.get("files") or [], files)
            for f in files:
                entry = found.setdefault(f["name"].upper(), {"name": f["name"], "sources": {}})
                entry["sources"][lang] = {
                    "file_id": f["id"],
                    "version": f.get("version"),
                    "scope": f.get("scope"),
                }
    return found


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"schema_version": "0.1-draft", "primary_language": "zh", "documents": []}


def kind_of(name: str) -> str:
    upper = name.upper()
    if upper.endswith(".ZIP"):
        return "evt"
    if "RM" in upper.rsplit(".", 1)[0][-3:]:
        return "reference-manual"
    return "datasheet"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="差分をmanifestへ反映する")
    args = ap.parse_args()

    manifest = load_manifest()
    known = {d["name"].upper(): d for d in manifest["documents"]}
    remote = survey()

    added, changed, gone = [], [], []
    for key, found in sorted(remote.items()):
        doc = known.get(key)
        if doc is None:
            added.append(
                {
                    "name": found["name"],
                    "kind": kind_of(found["name"]),
                    "repositories": [],
                    "status": "unassigned",
                    "sources": found["sources"],
                }
            )
            continue
        for lang, src in found["sources"].items():
            was = doc.get("sources", {}).get(lang)
            if was is None:
                changed.append(f"{doc['name']} {lang}: 新たに公開 (v{src['version']})")
            elif was.get("version") != src.get("version"):
                changed.append(
                    f"{doc['name']} {lang}: v{was.get('version')} -> v{src['version']}"
                )
        doc.setdefault("sources", {}).update(found["sources"])
    for key, doc in known.items():
        if key not in remote and doc.get("status") != "excluded":
            gone.append(doc["name"])

    print(f"サイト掲載 {len(remote)} 件 / manifest {len(known)} 件", file=sys.stderr)
    for line in changed:
        print(f"  版更新 {line}", file=sys.stderr)
    for doc in added:
        ids = " ".join(f"{k}={v['file_id']}" for k, v in doc["sources"].items())
        print(f"  新規   {doc['name']:24} {ids}  ← 割当先の判断が要る", file=sys.stderr)
    for name in gone:
        print(f"  消失   {name}  ← サイト一覧から消えた", file=sys.stderr)
    if not (changed or added or gone):
        print("  差分なし", file=sys.stderr)

    if args.write:
        manifest["documents"] = sorted(
            list(known.values()) + added, key=lambda d: d["name"].upper()
        )
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n{MANIFEST} を更新しました", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
