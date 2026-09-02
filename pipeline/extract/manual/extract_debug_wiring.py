#!/usr/bin/env python3
"""WCH-Link manualのdebug配線表 → evidence/debug_wiring.csv（R-29の残りを埋める）。

datasheetの節見出しはwire数を言わないseriesが11ある（R-29）。WCH-Link manual
（WCH-LinkUserManual.PDF。catalogでassigned・mirror済み）は

1. **配線表**——「常用芯片型号 / SWDIO / SWCLK」。SWCLK欄が`-`のchipは1線のみ
2. **両対応の注記**——「…和CH32M007支持单线（SWDIO）和两线（SWDIO-SWCLK）调试接口」

を持ち、この2つで全27 seriesのwire数が確定する（D18で構造化変換して実在を確認済み。
zh版の表はページを跨ぐので、L1結合層`pipeline/common/logical_tables`で結合してから読む）。

- chip群のtoken→seriesは**総当たりの辞書**（`OURS`）。辞書に無いCH32系tokenが
  現れたら生成が落ちる（新しいchipが manualに載ったら必ず人の目を通る）。
  CH569等のCH32以外は`NOT_OURS`で明示的に落とす
- zh/enの両版を読み、値が一致した行だけconfirmed（basisは両版のページ）。
  片方にしか無い・食い違う場合はreference/conflictで残す

実行:
    uv run pipeline/extract/manual/extract_debug_wiring.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "common"))
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))

import logical_tables  # noqa: E402
import paths  # noqa: E402
import review_sidecar  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"

COLUMNS = ["series", "swdio_pad", "swclk_pad", "dual_support",
           "#", "confidence", "basis"]

# chip群のtoken → このrepositoryのseries。**辞書に無いCH32 tokenは生成が落ちる**。
OURS: dict[str, tuple[str, ...]] = {
    "CH32X035_X033": ("CH32X033", "CH32X035"),
    "CH32V003": ("CH32V003",),
    "CH32V10x": ("CH32V103",),
    # V20xの型番線。V205とV208は別tokenで来る（V208はPA13群の中に来ない版も
    # あるが、V20xがfamily線を指すのは両版で同じ）。
    "CH32V20x": ("CH32V203", "CH32V208"),
    "CH32V30x": ("CH32V303", "CH32V305", "CH32V307"),
    # M103はL103と同族だが、manualのtokenを勝手に広げない（M103のwire数は
    # datasheetの節見出しが2-wireと明記していて、そちらで足りる）。
    "CH32L103": ("CH32L103",),
    "CH32V317": ("CH32V317",),
    "CH32V205_203CC": ("CH32V205",),
    "CH32V407_467": ("CH32V407", "CH32V467"),
    "CH32X305_315": ("CH32X305", "CH32X315"),
    "CH32V002_004_005_006_007": ("CH32V002", "CH32V004", "CH32V005",
                                 "CH32V006", "CH32V007"),
    "CH32M007": ("CH32M007",),
    "CH32M030": ("CH32M030",),
    "CH32H417_415_416": ("CH32H415", "CH32H416", "CH32H417"),
    "CH32H417_416_415": ("CH32H415", "CH32H416", "CH32H417"),
}
NOT_OURS = re.compile(r"^CH(?:[56]\d|32F)")   # CH5xx/CH6xx（CH59x含む）/CH32F系はこのrepoの外

DUAL_NOTE = {
    "zh": re.compile(r"支持单线（SWDIO）和两线"),
    "en": re.compile(r"support both 1-wire \(SWDIO\) and 2-wire", re.IGNORECASE),
}
TOKEN = re.compile(r"CH[0-9A-Zx_]+")


def load_pages(name: str) -> tuple[list[dict], dict]:
    bundle = BUNDLES / name
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    pages = []
    for entry in manifest["pages"]:
        payload = (bundle / entry["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
        pages.append(json.loads(payload))
    return pages, manifest


def map_tokens(cell: str) -> tuple[list[str], list[str]]:
    """chip群のセル → (series list, 落としたtoken list)。未知のCH32 tokenは例外。"""
    ours: list[str] = []
    dropped: list[str] = []
    for token in TOKEN.findall(cell.replace("\n", "")):
        token = token.strip("_")
        if token in OURS:
            ours.extend(OURS[token])
        elif NOT_OURS.match(token):
            dropped.append(token)
        else:
            raise SystemExit(f"debug配線表に辞書に無いtoken {token!r}（セル {cell!r}）"
                             "——OURS か NOT_OURS に足すこと")
    return ours, dropped


def read_edition(lang: str) -> tuple[dict[str, dict], set[str], dict[str, int]]:
    """(series→{swdio,swclk,page}), 両対応series集合, {'table':page,'note':page}。"""
    name = f"WCH-LinkUserManual.{lang}"
    pages, _ = load_pages(name)
    chains = logical_tables.document_chains(pages)
    rejected = review_sidecar.rejected_ids(name)

    table = None
    row_pages: list[int] = []
    for page in pages:
        for t in page["tables"]:
            if t["id"] in rejected:
                continue
            info = chains[t["id"]]
            if not info["start"]:
                continue
            merged = info["merged"] or logical_tables.merge_cells(
                [(page["number"], t)])
            grid, pages_of_rows = logical_tables.text_grid(merged)
            header = [c or "" for c in grid[0]]
            if any("SWDIO" in h for h in header) and any("SWCLK" in h for h in header):
                table, row_pages = grid, pages_of_rows
                break
        if table:
            break
    if table is None:
        raise SystemExit(f"{name}: SWDIO/SWCLK配線表が見つからない")

    wiring: dict[str, dict] = {}
    for index in range(1, len(table)):
        cells = [(c or "").strip() for c in table[index]]
        if len(cells) < 3 or not cells[0]:
            continue
        ours, _ = map_tokens(cells[0])
        for series in ours:
            wiring[series] = {"swdio": cells[1], "swclk": cells[2],
                              "page": row_pages[index]}

    dual: set[str] = set()
    note_page = None
    for page in pages:
        lines = [line["text"] for line in page["lines"]]
        for index, text in enumerate(lines):
            if DUAL_NOTE[lang].search(text):
                window = " ".join(lines[max(0, index - 3):index + 1])
                ours, _ = map_tokens(window)
                dual.update(ours)
                note_page = page["number"]
        if note_page:
            break
    if not dual:
        raise SystemExit(f"{name}: 両対応の注記が見つからない")
    return wiring, dual, {"note": note_page}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    args = ap.parse_args()

    editions = {lang: read_edition(lang) for lang in ("zh", "en")}
    with paths.table("series").open(newline="", encoding="utf-8") as f:
        known = {r["series"] for r in csv.DictReader(f)}

    document = "WCH-LinkUserManual.PDF"
    rows = []
    for series in sorted(known):
        zh_w, zh_dual, zh_pages = editions["zh"]
        en_w, en_dual, en_pages = editions["en"]
        z, e = zh_w.get(series), en_w.get(series)
        if z is None and e is None:
            continue          # manualに載らないseriesは行を作らない（無いのが事実）
        dual = ("yes" if series in zh_dual and series in en_dual else
                "" if series not in zh_dual and series not in en_dual else None)
        if z and e and z["swdio"] == e["swdio"] and z["swclk"] == e["swclk"] \
                and dual is not None:
            confidence = "confirmed"
            basis = (f"{document}:zh(p.{z['page']}"
                     + (f",p.{zh_pages['note']}" if series in zh_dual else "")
                     + f")+{document}:en(p.{e['page']}"
                     + (f",p.{en_pages['note']}" if series in en_dual else "") + ")")
            record = z
        elif z and e:
            confidence = "conflict"
            diff = ",".join(f"{k}={z[k]}" for k in ("swdio", "swclk") if z[k] != e[k])
            diff = diff or f"dual=zh:{series in zh_dual}/en:{series in en_dual}"
            basis = f"{document}:en(p.{e['page']})+!{document}:zh({diff})"
            record, dual = e, ("yes" if series in en_dual else "")
        else:
            record = z or e
            lang = "zh" if z else "en"
            in_dual = series in (zh_dual if z else en_dual)
            confidence = "reference"
            basis = f"{document}:{lang}(p.{record['page']})"
            dual = "yes" if in_dual else ""
        rows.append({"series": series,
                     "swdio_pad": record["swdio"],
                     "swclk_pad": "" if record["swclk"] == "-" else record["swclk"],
                     "dual_support": dual,
                     "confidence": confidence, "basis": basis})

    dest = paths.table("debug_wiring", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows({**{c: r.get(c, "") for c in COLUMNS}, "#": "#"} for r in rows)
    from collections import Counter  # noqa: PLC0415
    print(f"{dest}: {len(rows)} 行 "
          f"{dict(Counter(r['confidence'] for r in rows))} "
          f"dual {sum(1 for r in rows if r['dual_support'] == 'yes')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
