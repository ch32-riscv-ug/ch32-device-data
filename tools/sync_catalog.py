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
import os
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


def note(message: str) -> None:
    """A GitHub Actions warning annotation, so the run page shows it."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{message}")


def summary(lines: list[str], remote: int, total: int, unassigned: list[str]) -> None:
    """Write the run summary GitHub shows above the log."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as out:
        out.write(f"## 文書カタログ\n\nサイト掲載 {remote} 件 / manifest {total} 件\n\n")
        out.write("\n".join(lines) + "\n" if lines else "差分なし\n")
        if unassigned:
            out.write(f"\n### 割当先が未定 ({len(unassigned)})\n\n")
            out.write("\n".join(f"- `{n}`" for n in unassigned) + "\n")


class CatalogueError(RuntimeError):
    """The site did not answer in the shape this tool expects.

    WCH changes download ids and occasionally the API itself. Failing loudly is the
    point: a silent empty answer would quietly empty the catalogue.
    WCHはdownload idを変えることがあり、API自体が変わることもある。黙って空の
    結果を書き込むより、失敗させて気付ける方がよい。
    """


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - the cause is reported, not swallowed
        raise CatalogueError(f"{url} を取得できませんでした: {exc}") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CatalogueError(f"{url} の応答がJSONではありません: {body[:120]!r}") from exc
    if not isinstance(payload, dict) or "data" not in payload:
        raise CatalogueError(f"{url} の応答に data がありません: {str(payload)[:120]}")
    return payload


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
    try:
        remote = survey()
    except CatalogueError as exc:
        print(f"::error::{exc}" if os.environ.get("GITHUB_ACTIONS") else f"error: {exc}",
              file=sys.stderr)
        return 1
    # A shape change upstream would come back as a handful of documents rather than
    # an error. Treat a sudden collapse as a failure instead of writing it down.
    # API側の仕様変更は「エラー」ではなく「極端に少ない結果」として現れる。
    if known and len(remote) < len(known) * 0.8:
        message = (
            f"サイトから {len(remote)} 件しか取得できませんでした"
            f"（manifestは {len(known)} 件）。APIの仕様変更を疑ってください"
        )
        print(f"::error::{message}" if os.environ.get("GITHUB_ACTIONS") else f"error: {message}",
              file=sys.stderr)
        return 1

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

    report = []
    print(f"サイト掲載 {len(remote)} 件 / manifest {len(known)} 件", file=sys.stderr)
    for line in changed:
        print(f"  版更新 {line}", file=sys.stderr)
        report.append(f"- 版更新 `{line}`")
    for doc in added:
        ids = " ".join(f"{k}={v['file_id']}" for k, v in doc["sources"].items())
        print(f"  新規   {doc['name']:24} {ids}  ← 割当先の判断が要る", file=sys.stderr)
        report.append(f"- 新規 `{doc['name']}` ({ids}) — 割当先が未定")
        note(f"新しい文書 {doc['name']} は割当先が未定です")
    for name in gone:
        print(f"  消失   {name}  ← サイト一覧から消えた", file=sys.stderr)
        report.append(f"- 消失 `{name}`")
        note(f"{name} がサイトの一覧から消えました")
    unassigned = [d["name"] for d in known.values() if d.get("status") == "unassigned"]
    for name in unassigned:
        note(f"{name} は割当先が未定のままです")
    if not (changed or added or gone):
        print("  差分なし", file=sys.stderr)

    summary(report, len(remote), len(known) + len(added), unassigned)

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
