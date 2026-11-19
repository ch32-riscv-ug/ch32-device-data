#!/usr/bin/env python3
"""タイマどうしの内部トリガ（ITRx にどのタイマの TRGO がつながるか）→ index/timer_itr.csv

タイマの従モード（`TIMx_SMCFGR.TS`）で ITR0〜ITR3 を選ぶと、別のタイマの TRGO を入力にできる。
どの ITR にどのタイマがつながるかは RM の表「TIMx内部触发连接」/「GTPM内部触发连接」
（en「TIMx internal trigger connection」）が書く。en 版は表題を欠くことがあるので、見出しの行
（「从定时器」/「Slave timer」と ITR の列）で表を選ぶ:

    从定时器 | ITR0（TS=000） | ITR1（TS=001） | ITR2（TS=010） | ITR3（TS=011）
    TIM1     | TIM5           | TIM2           | TIM3           | TIM4

consumer（ch32rv のコア）は RM から手で書いていた（2026-11-19 の依頼）。1行は family × 従タイマ ×
ITR。主タイマの書き方（`TIM2`・`TIM2_TRGO`）は `TIM2` に揃え、候補が並ぶもの（`TIM8/USB/ETH`）は
`;` で並べる。空欄・`0` はつながっていない（行を持たない）。zh・en 版が同じ主を言えば confirmed、
違えば conflict（zh を採る）、片方だけなら reference。RM を共有する family（CH32FV2x_V3xRM の
V20x/V307）は、その family が持つタイマ（`evidence/timers.csv`）の行だけを持つ。

実行:
    uv run pipeline/extract/rm/extract_timer_itr.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402
import paths  # noqa: E402

COLUMNS = ["family", "slave", "itr", "ts", "master", "confidence", "basis"]
HEAD = re.compile(r"ITR(?P<n>\d)")


def masters(cell: str | None) -> str:
    """`TIM2_TRGO` → `TIM2`、`TIM8/USB/ETH` → `TIM8;USB;ETH`、空欄・`0`・`-` → 空。

    >>> masters("TIM2_TRGO"), masters("TIM8/USB/ETH"), masters("0"), masters(None), masters("TIM 5")
    ('TIM2', 'TIM8;USB;ETH', '', '', 'TIM5')
    """
    text = re.sub(r"\s+", "", cell or "")
    if text in ("", "0", "-", "—", "/"):
        return ""
    parts = [re.sub(r"_TRGO$", "", p, flags=re.I) for p in text.split("/") if p]
    return ";".join(p.upper() for p in parts)


def read(bundle: str) -> dict[tuple[str, int], tuple[str, int]]:
    """(従タイマ, ITR) → (主, 頁)。"""
    # ページをまたぐ表は続きの断片が見出しの行を持たないので、`logical_id` でつなぐ（zh 版の
    # GTPM の表は TIM4/TIM5 の行が次のページに落ちる）。
    # en 版は続きの断片に別の id を振ることがあるので、**次のページの先頭の表で、見出しが無く
    # 先頭のセルが TIMn・列数が同じ**ものも直前の ITR の表の続きとみなす。
    # 見出しの行を持つ表はそれ自体で1つ（表題の無い表どうしは同じ logical_id にまとめられることが
    # あるので id では束ねない）。続きは「continues_from_previous」の断片か、次のページの先頭の
    # 見出しの無い表（先頭のセルが TIMn・列数が同じ）。
    fragments: dict[str, list[tuple[int, list]]] = collections.defaultdict(list)
    last_itr: tuple[str, int, int] | None = None   # (束ねる鍵, 頁, 列数)
    for number, page in enumerate(bundle_pages.pages(bundle), start=1):
        here = page.get("page") or number
        for position, table in enumerate(page.get("tables", [])):
            rows = table["extracted_rows"]
            if not rows or not rows[0]:
                continue
            first = re.sub(r"\s+", "", rows[0][0] or "")
            if re.search(r"从定时器|Slavetimer", first, re.I):
                last_itr = (table["id"], here, len(rows[0]))
                fragments[table["id"]].append((here, rows))
            elif (last_itr and position == 0 and here == last_itr[1] + 1
                  and len(rows[0]) == last_itr[2]
                  and (table.get("continues_from_previous") or re.fullmatch(r"TIM\d+", first, re.I))):
                fragments[last_itr[0]].append((here, rows))
                last_itr = (last_itr[0], here, last_itr[2])
    out = {}
    for parts in fragments.values():
        head = parts[0][1][0] if parts[0][1] else []
        # 表題では選ばない——en 版は汎用タイマの表に表題を付けなかったり、別の表の表題を
        # 付けたりする（V407 en の表14-2 は「encoder mode」の表題）。見出しの行で選ぶ。
        if not head or not re.search(r"从定时器|Slave\s*timer", head[0] or "", re.I):
            continue
        columns = {}
        for i, cell in enumerate(head):
            m = HEAD.search(cell or "")
            if m:
                columns[i] = int(m.group("n"))
        if not columns:
            continue
        for page, rows in parts:
            for row in rows:
                slave = re.sub(r"\s+", "", row[0] or "").upper()
                if not re.fullmatch(r"TIM\d+", slave):
                    continue
                for i, itr in columns.items():
                    found = masters(row[i] if i < len(row) else "")
                    if found:
                        out.setdefault((slave, itr), (found, page))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先のディレクトリ（試験用）")
    args = ap.parse_args()

    # 証拠の timers（index/timers.csv は索引の段で作られ、この表より後）。
    with paths.table("timers").open(newline="", encoding="utf-8") as f:
        timers = collections.defaultdict(set)
        for r in csv.DictReader(f):
            timers[r["family"]].add(r["timer"])
    rows = []
    for family in sorted(timers):
        editions = {}
        for lang, (bundle, document) in bundle_pages.rm_bundles(family).items():
            editions[lang] = (document, read(bundle.name))
        keys = sorted({k for _, found in editions.values() for k in found},
                      key=lambda k: (int(k[0][3:]), k[1]))
        for slave, itr in keys:
            if slave not in timers[family]:
                continue
            said = {lang: (doc, found[(slave, itr)]) for lang, (doc, found) in editions.items()
                    if (slave, itr) in found}
            kept_lang = "zh" if "zh" in said else "en"
            kept = said[kept_lang][1][0]
            basis = "+".join(f"rm:{doc}:{lang}(p.{page})" for lang, (doc, (m, page)) in said.items()
                             if m == kept)
            basis += "".join(f"+!rm:{doc}:{lang}(p.{page})(master={m})"
                             for lang, (doc, (m, page)) in said.items() if m != kept)
            rows.append({"family": family, "slave": slave, "itr": itr, "ts": itr,
                         "master": kept,
                         "confidence": ("conflict" if "+!" in basis
                                        else "confirmed" if len(said) == 2 else "reference"),
                         "basis": basis})
    dest = paths.table("timer_itr", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    shown = dest.relative_to(REPO) if dest.is_relative_to(REPO) else dest
    print(f"{shown}: {len(rows)} 行", dict(collections.Counter(r["confidence"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
