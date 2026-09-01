#!/usr/bin/env python3
"""2つのbundle manifestを突き合わせ、ズレたpageを名指しする（D18の環境差検証）。

`structured/<doc>/manifest.json`（コミット済みの正本）と、別環境で再変換した
manifestを比べる。原本SHA-256が違えば「原本が変わった」（環境差ではない）、
page/geometryのhashが違えば「変換がその環境で再現しない」で、どちらかを
明確に区別して報告する。

実行:
    uv run pipeline/checks/compare_manifest.py <committed-manifest> <regenerated-manifest>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("committed", type=Path)
    ap.add_argument("regenerated", type=Path)
    args = ap.parse_args()

    a = json.loads(args.committed.read_text(encoding="utf-8"))
    b = json.loads(args.regenerated.read_text(encoding="utf-8"))

    if a["source"]["sha256"] != b["source"]["sha256"]:
        print(f"SOURCE CHANGED: {a['source']['document']} committed "
              f"{a['source']['sha256'][:12]} vs regenerated {b['source']['sha256'][:12]} "
              "-- not an environment issue; reconvert and commit the manifest",
              file=sys.stderr)
        return 2
    for key in ("engine", "engine_version", "converter_version"):
        va, vb = a["conversion"].get(key), b["conversion"].get(key)
        if va != vb:
            print(f"TOOL CHANGED: {key} committed {va!r} vs regenerated {vb!r} "
                  "-- pin the versions before comparing environments", file=sys.stderr)
            return 2

    diverged = []
    for pa, pb in zip(a["pages"], b["pages"], strict=True):
        if pa != pb:
            what = [k for k in pa if pa[k] != pb.get(k)]
            diverged.append((pa["number"], what))
    if diverged:
        print(f"NOT REPRODUCIBLE: {len(diverged)} of {len(a['pages'])} pages differ "
              f"({a['source']['document']} {a['source']['language']}); first: "
              + "; ".join(f"p{n}:{w}" for n, w in diverged[:5]), file=sys.stderr)
        return 1
    print(f"OK: {a['source']['document']} {a['source']['language']} "
          f"{len(a['pages'])} pages byte-identical across environments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
