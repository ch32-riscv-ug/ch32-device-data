#!/usr/bin/env python3
"""Report whether each mirror still matches the catalogue.

A mirror fetches what the catalogue assigns to it, so the two can drift: a document
newly assigned has not been downloaded yet, and one that was reassigned leaves a
stale copy behind, because the fetch script never deletes. This lists both by
reading each mirror's file listing over the GitHub API.

Usage:
    uv run tools/check_mirrors.py [--owner ch32-riscv-ug]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "documents.json"
API = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"
TIMEOUT = 60


def api(url: str) -> list | None:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None if exc.code == 404 else []


def note(kind: str, message: str) -> None:
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{kind}::{message}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--owner", default="ch32-riscv-ug")
    args = ap.parse_args()

    catalogue = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected: dict[str, set[tuple[str, str]]] = {}
    for doc in catalogue["documents"]:
        if doc.get("status") != "assigned":
            continue
        for repo in doc["repositories"]:
            if repo == "ch32-device-data" or doc["name"].upper().endswith(".ZIP"):
                continue
            for lang, src in doc["sources"].items():
                if src.get("file_id") is not None:
                    expected.setdefault(repo, set()).add((lang, doc["name"]))

    lines = []
    for repo in sorted(expected):
        present: set[tuple[str, str]] = set()
        reachable = True
        for lang in ("en", "zh"):
            listing = api(API.format(owner=args.owner, repo=repo, path=f"datasheet_{lang}"))
            if listing is None:
                continue  # the directory does not exist yet
            if listing == []:
                reachable = False
                break
            present |= {
                (lang, f["name"]) for f in listing if f["name"].upper().endswith(".PDF")
            }
        if not reachable:
            lines.append(f"- `{repo}` — 一覧を取得できず")
            note("warning", f"{repo} の内容を取得できませんでした")
            continue
        missing = sorted(expected[repo] - present)
        stale = sorted(present - expected[repo])
        state = "一致" if not (missing or stale) else "差分"
        detail = ""
        if missing:
            detail += " 未取得=" + ",".join(f"{a}/{b}" for a, b in missing)
        if stale:
            detail += " 余剰=" + ",".join(f"{a}/{b}" for a, b in stale)
            note("warning", f"{repo} にカタログ外のファイルが残っています:{detail}")
        print(f"{repo:12} {state}{detail}", file=sys.stderr)
        lines.append(f"- `{repo}` {state}{detail}")

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write("\n## mirrorの追随状況\n\n" + "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
