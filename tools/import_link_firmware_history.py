#!/usr/bin/env python3
"""WCH-Link 系の過去のファームの指紋を、非公開の保存庫の一覧から curated に写す。**人が回す**。

    uv run tools/import_link_firmware_history.py [--archive ../wch-binary-archive]

WCH は古いファームを配らないので、ファイルそのものは非公開の保存庫
（ch32-riscv-ug/wch-binary-archive。再配布にあたるため非公開）に置いてある。ここに写すのは
**指紋（sha256・サイズ）と、どの配布物に入っていたか**だけで、`build_link_firmware.py` が
今配っている ZIP の行と合わせて `link_firmware` の表にする。公開の再生成が非公開の
リポジトリに頼らないよう、写しは commit する。

写すのは **今も MounRiver の API から落とせる配布物**に入っていたものだけ（外の人も同じ
ファイルを落として確かめられる）。ユーザーの手元の写ししか無い配布物（WCH-LinkUtility 3.1
の ZIP など）は写さない。WCH-LinkUtility の今の ZIP は生成器がじかに読むので写さない。

書くもの: `curated/link-firmware-history.csv`（1 行 = 1 つの配布物に入っていた 1 ファイル）
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "common"))
import paths  # noqa: E402

OUT = paths.CURATED / "link-firmware-history.csv"
API = "https://api.mounriver.com/mountriver/api/version/"
COLUMNS = ["sha256", "file", "device", "mcu", "mode", "role", "size", "wcfg_version",
           "set_version", "package", "released", "resource_id"]
RESOURCE = re.compile(r"resourceId=(\d+)")


def api(endpoint: str, **params) -> object:
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                timeout=60) as r:
        payload = json.load(r)
    if not payload.get("success"):
        raise SystemExit(f"{endpoint}: {payload}")
    return payload.get("result")


def releases() -> dict[str, tuple[str, str]]:
    """{resourceId: (配布物のファイル名, 公開日)}。MounRiver の API が今言うもの。"""
    found = {}
    for os_type in ("WINDOWS", "LINUX", "MAC"):
        for sw in (1, 2):
            result = api("querySoftVList", pageNo=1, pageSize=9999, swType=sw, osType=os_type, lang="en") or {}
            for it in result.get("records") or []:
                found[str(it["softId"])] = (it.get("softFileName", ""), (it.get("crtTime") or "")[:10])
        for it in api("fetchRecentCommunity", osType=os_type, lang="en") or []:
            for rel in it.get("relationList") or []:
                found[str(rel["softReId"])] = (rel.get("softFileName", ""), (it.get("crtTime") or "")[:10])
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=paths.REPO.parent / "wch-binary-archive")
    args = ap.parse_args()
    index = args.archive / "link" / "index.csv"
    with index.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    known = releases()
    out, skipped = [], set()
    for r in rows:
        m = RESOURCE.search(r["source"])
        if not m:
            skipped.add(f"{r['package']}-{r['version']}（API の配布物ではない）")
            continue
        rid = m.group(1)
        if rid not in known:
            raise SystemExit(f"{r['package']}-{r['version']}: resourceId={rid} を API が今は返さない")
        name, released = known[rid]
        out.append({"sha256": r["sha256"], "file": r["file"], "device": r["device"], "mcu": r["mcu"],
                    "mode": r["mode"], "role": r["role"], "size": r["size"],
                    "wcfg_version": r["wcfg_version"], "set_version": r["set_version"],
                    "package": name, "released": released, "resource_id": rid})
    out.sort(key=lambda r: (r["released"], r["package"], r["file"]))
    paths.write(OUT, out, COLUMNS)
    print(f"{OUT.relative_to(paths.REPO)}: {len(out)} 行（配布物 {len({r['package'] for r in out})}、"
          f"ファイル {len({r['sha256'] for r in out})}）", file=sys.stderr)
    for s in sorted(skipped):
        print(f"  写さない: {s}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
