#!/usr/bin/env python3
"""catalogのassigned文書を全部bundle化する一括変換器（D18工程1）。

対象は`catalog/documents.csv`のassigned行のうち、datasheet・reference-manual・
core-manual・package-drawing・other（＝WCH-LinkUserManual）。言語は
`version_zh`/`version_en`の有無で決める。原本はローカルmirror
（`/home/mt/dev_wch/<repo>/datasheet_<lang>/<document>`）から読む。

**incremental**: `structured/<stem>.<lang>/manifest.json`が既にあり、原本SHA-256・
engine版・converter版が全部同じなら変換を跳ばす（`--force`で全部やり直す）。
manifestが同じでもbundle（`.cache/`）が消えていれば作り直す。

実行:
    uv run pipeline/ingest/convert_all.py [--jobs N] [--force] [--only <doc.lang>,...]
"""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import sys
import time
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert  # noqa: E402

REPO = convert.REPO
MIRRORS = Path("/home/mt/dev_wch")
TARGET_KINDS = ("datasheet", "reference-manual", "core-manual",
                "package-drawing", "other")


def targets() -> list[dict]:
    out = []
    with (REPO / "catalog" / "documents.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] != "assigned" or row["kind"] not in TARGET_KINDS:
                continue
            for lang in ("zh", "en"):
                if not row[f"version_{lang}"]:
                    continue
                hits = [MIRRORS / repo / f"datasheet_{lang}" / row["document"]
                        for repo in row["repositories"].split(";") if repo]
                hits = [p for p in hits if p.exists()]
                if not hits:
                    raise SystemExit(f"mirror not found: {row['document']} {lang} "
                                     f"(repositories={row['repositories']!r})")
                out.append({
                    "name": f"{Path(row['document']).stem}.{lang}",
                    "pdf": hits[0],
                    "lang": lang,
                    "document_type": row["kind"],
                })
    return out


def up_to_date(job: dict, bundles: Path, structured: Path) -> bool:
    import hashlib
    committed = structured / job["name"] / "manifest.json"
    cached = bundles / job["name"] / "manifest.json"
    if not committed.exists() or not cached.exists():
        return False
    manifest = json.loads(committed.read_text(encoding="utf-8"))
    if manifest != json.loads(cached.read_text(encoding="utf-8")):
        return False
    conversion = manifest["conversion"]
    return (manifest["source"]["sha256"]
            == hashlib.sha256(job["pdf"].read_bytes()).hexdigest()
            and conversion["engine_version"] == version("pdfplumber")
            and conversion.get("converter_version") == convert.CONVERTER_VERSION)


def run_one(args: tuple[dict, str, str]) -> tuple[str, float, int]:
    job, bundles, structured = args
    started = time.perf_counter()
    bundle = convert.convert(job["pdf"], job["lang"], job["document_type"],
                             Path(bundles), Path(structured))
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    return job["name"], time.perf_counter() - started, len(manifest["pages"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="incremental判定を無視して全部変換")
    ap.add_argument("--only", help="対象を絞る（`CH32V003DS0.en`のようにカンマ区切り）")
    ap.add_argument("--out", type=Path, default=convert.DEFAULT_BUNDLES,
                    help="bundleの出力先の上書き（試験用）")
    ap.add_argument("--structured", type=Path, default=convert.DEFAULT_STRUCTURED,
                    help="manifest/reviewの置き場の上書き（試験用）")
    args = ap.parse_args()

    jobs = targets()
    if args.only:
        wanted = set(args.only.split(","))
        jobs = [j for j in jobs if j["name"] in wanted]
        missing = wanted - {j["name"] for j in jobs}
        if missing:
            raise SystemExit(f"unknown targets: {sorted(missing)}")

    skipped = []
    if not args.force:
        fresh = [j for j in jobs if not up_to_date(j, args.out, args.structured)]
        skipped = [j["name"] for j in jobs if j not in fresh]
        jobs = fresh

    started = time.perf_counter()
    results = []
    if jobs:
        with multiprocessing.Pool(args.jobs) as pool:
            for name, took, pages in pool.imap_unordered(
                    run_one, [(j, str(args.out), str(args.structured)) for j in jobs]):
                results.append((name, took, pages))
                print(f"  {name}: {pages}p {took:.0f}s", file=sys.stderr)
    total_pages = sum(pages for _, _, pages in results)
    print(f"converted {len(results)} versions / {total_pages} pages "
          f"in {time.perf_counter() - started:.0f}s "
          f"({args.jobs} jobs), skipped {len(skipped)} up-to-date", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
