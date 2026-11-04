#!/usr/bin/env python3
"""WCH の製品ページの「系统框图」（System Block Diagram）を取り、mirror に置く。

図は series ごとの製品ページにだけあり、データシートには無い。製品ページの無い
series（他の series のページの中で触れられるだけのもの）には図が無いので、
README にも出さない。自前で描いて埋めることはしない（2026-11-04 ユーザー判断）。

製品ページは SPA で、本文は WCH の API が返す:
  https://api1.wch.cn/api/official/website/articles/getArticle?alias=<SERIES>.html
本文（markdown か HTML）の「系统框图」の見出しの直後の画像が図。

書くもの:
  curated/system-diagrams.csv            series, image_url（図のある series だけ）
  <mirror>/image/system_<SERIES>.<ext>   画像そのもの（ext は WCH の URL のまま）

build_readme.py は csv を読み、ある series にだけ図を出す。WCH は図を差し替える
（URL の日付が変わる）ので、ときどき再実行して csv と mirror の差分を見る。
mirror の commit は手で行う。

実行: uv run python tools/fetch_system_diagrams.py [--no-download]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "common"))
import paths  # noqa: E402

API = "https://api1.wch.cn/api/official/website/articles/getArticle?alias={}.html"
OUT = paths.CURATED / "system-diagrams.csv"
HEADING = re.compile(r"系统框图")
IMAGE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)|<img[^>]*\bsrc=\"(https?://[^\"]+)\"")


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def diagram_url(content: str) -> str:
    """「系统框图」の見出しから次の見出しまでの最初の画像。無ければ空。

    V103 のページは HTML で、画像が次の見出し（产品特点）の <h4> の中に入って
    いるので、次の見出しの開始タグまでではなく、見出しの文字までで区切る。"""
    m = HEADING.search(content)
    if not m:
        return ""
    rest = content[m.end():]
    end = re.search(r"产品特点|主要参数|应用|#{2,}\s*\S|<h\d>[^<]", rest)
    image = IMAGE.search(rest[:end.start()] if end else rest)
    return (image.group(1) or image.group(2)) if image else ""


def file_name(series: str, url: str) -> str:
    return f"system_{series}{Path(url).suffix.lower() or '.png'}"


def load() -> list[dict]:
    if not OUT.exists():
        return []
    with OUT.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-download", action="store_true", help="csv だけ更新する")
    args = parser.parse_args()

    series = paths.load_index("series")
    rows = []
    for s in series:
        data = json.loads(get(API.format(s["series"]))).get("data") or {}
        url = diagram_url(data.get("content") or "")
        print(f"{s['series']:10} {url or '-'}")
        if url:
            rows.append({"series": s["series"], "image_url": url})

    before = {r["series"]: r["image_url"] for r in load()}
    paths.write(OUT, rows, ["series", "image_url"])

    if not args.no_download:
        family = {s["series"]: s["family"] for s in series}
        for r in rows:
            image = paths.MIRRORS / family[r["series"]] / "image" / file_name(r["series"], r["image_url"])
            if image.exists() and before.get(r["series"]) == r["image_url"]:
                continue
            image.parent.mkdir(exist_ok=True)
            for old in image.parent.glob(f"system_{r['series']}.*"):
                old.unlink()
            image.write_bytes(get(r["image_url"]))
            print(f"saved {image}")
    print(f"{len(rows)}/{len(series)} series have a system block diagram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
