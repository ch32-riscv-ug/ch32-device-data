#!/usr/bin/env python3
"""資料どうしが食い違っている箇所を1表に集める → index/conflicts.csv

**証拠は食い違いを片方に寄せず `conflict` として両論を残します**（`docs/handoff.ja.md`
の規則）。ただしその記録は33の表に散っていて、「両版で食い違う仕様を全部見せて」
に答えるには全表を grep するしかありませんでした（2026-08-29 の監査の指摘。
`basis` が1セル内の DSL なので横断で引けない、というのがその内容）。

この索引はその一番安い切り出しです。**新しい事実は足しません**——`confidence` が
`conflict` の行を集め、`basis` の DSL から「どの出所が異を唱えているか」
（`!<source>`）と「その出所は何と言っているか」（`(=<value>)`）を取り出すだけ。

    どの表の・何について・どの出所が・何と言っているか

`basis` が異論を DSL で書いていない表もあります（`memory_configs` の67行と
`timers` の1行）。**そこは空欄になり、それ自体が「食い違いは散文で記録されている」
という情報**です——`evidence/README` の当該節を読むしかない、と分かります。

実行:
    uv run tools/build_conflicts.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

COLUMNS = ["table", "family", "series", "part_number", "subject", "field",
           "kept", "dissenting", "alternative", "#", "basis"]

# その表の行を名指すのに要る列。**総当たりで持つ**——表を足したら、その行を
# どう名指すかを決めないと生成が落ちる。値の列は入れない（行を指す鍵だけ）。
KEYS: dict[str, tuple[str, ...]] = {
    "families": ("family",),
    "series": ("series",),
    "products": ("part_number",),
    "packages": ("package",),
    "cores": ("core",),
    "documents": ("document",),
    "sources": ("family",),
    "toolchains": ("file",),
    "pins": ("part_number", "pin", "pad"),
    "pin_functions": ("part_number", "pad", "signal", "route"),
    "pin_alternate": ("family", "pad", "block"),
    "product_attributes": ("part_number", "attribute"),
    "features": ("series", "section"),
    "errata": ("id",),
    "memory_configs": ("part_number", "value"),
    "adc_internal": ("family", "source", "channel"),
    "flash_geometry": ("family",),
    "eval_boards": ("family", "board"),
    "evt_examples": ("family", "example"),
    "link_firmware": ("device", "mcu", "mode", "role"),
    "operating_conditions": ("series", "symbol", "parameter", "condition"),
    "remap_fields": ("series", "selector"),
    "remap_routes": ("series", "selector", "value", "signal"),
    "timers": ("family", "timer"),
    "register_blocks": ("family", "block"),
    "registers": ("family", "type", "register"),
    "register_fields": ("family", "type", "register", "field"),
    "dma_requests": ("family", "variant", "dma", "channel", "request"),
    "opa_cmp_registers": ("family", "block", "register", "field"),
    "clock_enables": ("family", "peripheral", "register", "field"),
    "usbpd_plumbing": ("family", "peripheral"),
    "interrupts": ("family", "number", "name"),
    "memory_map": ("family", "region"),
    "systick": ("family", "block", "register"),
    "clock_configs": ("family", "config"),
    "clock_prescalers": ("family", "field", "value"),
    "clock_sources": ("family", "consumer", "option"),
    "clock_symbols": ("family", "symbol", "role"),
    "clock_init": ("family", "function", "step"),
    "evt_variants": ("family", "macro"),
    "debug_data": ("family", "core"),
    "debug_wiring": ("series",),
    "option_bytes": ("family", "address"),
    "option_byte_fields": ("family", "byte", "bits"),
}

# `basis` の DSL。異を唱える出所は `!` で始まり、その出所が言う値は `(=…)`。
#   `pin-table:zh+pin-table:en+!rm-remap-grid(=remap-2)`
#   `evt(ch32l103.h)+!rm(CH32L103RM.PDF)(=29:24)`
#   `evt(ch32v10x_flash.c)+rm(CH32xRM.PDF)+!evt-comment:fast_program_bytes(=256)`
# **括弧は入れ子になる**（`!products:zh(=1（OPA1）)`）ので、`(=` からは対応する
# 閉じ括弧まで数えて取る。正規表現の最短一致だと値を途中で切る。
def dissenting_tokens(basis: str) -> list[str]:
    """`basis` の `!` で始まる項。**`+` は括弧の外だけが区切り**。

    値そのものに `+` が入る（`!…:zh(typ=V+VCC12VS)`）ので、素朴に `+` で
    割ると値が途中で切れる。

    >>> dissenting_tokens("a(p.1)+!b:zh(typ=V+VCC12VS)+c")
    ['b:zh(typ=V+VCC12VS)']
    >>> dissenting_tokens("pin-table:zh+pin-table:en+!rm-remap-grid(=remap-2)")
    ['rm-remap-grid(=remap-2)']
    """
    out, depth, token = [], 0, []
    for ch in basis:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "+" and depth == 0:
            out.append("".join(token))
            token = []
        else:
            token.append(ch)
    out.append("".join(token))
    return [t[1:].strip() for t in out if t.startswith("!") and t[1:].strip()]
# 異を唱える出所が列名を名乗ることがある（`!evt-comment:fast_program_bytes(=256)`）。
# **その表に本当にある列のときだけ採る**——`!products:zh(=…)` の `zh` や
# `!rm-remap-grid(=…)` の `grid` は出所の名前であって列ではないので、
# 綴りの形だけで決めると列名でないものを列名として書いてしまう。
NAMES_FIELD = re.compile(r"[:\-]([a-z][a-z0-9_]*)\(=")

# **その表が1行につき主張している列。** 行ごと `conflict` と印が付く表では、
# 食い違っているのはこの列の値。鍵（KEYS）と同じで表の形についての静的な事実で、
# その食い違いが何についてかの推測ではない。分からない表は載せない（空欄になる）。
ASSERTS: dict[str, str] = {
    "pin_functions": "route",
    "product_attributes": "value",
    "register_fields": "bits",
    "opa_cmp_registers": "bits",
}
# `operating_conditions` はここに載せない。1行が min/typ/max/unit の4つを主張して
# いて、争っているのがどれかは行ごとに違う（`basis` の `(min=60,typ=82,…)` が
# 名指ししている）。1つの列を決め打つと、min の食い違いを max の話として書く。


# 相手の値の書き方は表で3通りある。1つの値を争う表は `(=<値>)`、欄ごとに
# 争う表（`operating_conditions`）は `(min=…,typ=…,max=…,unit=…)`、
# 新経路の抽出器は列名を名指す `(address=…)`・`(field=…)`・`(default=…)`。
# どの `<列名>=` でも「相手の値」として中身ごと写す（`(p.614)` のような
# ページ参照は `=` を含まないので巻き込まれない）。
STATED = re.compile(r"\((?==|[a-z_][a-z0-9_]*=)")


def stated_value(token: str) -> str:
    """相手の出所が言う値。**括弧は入れ子になる**ので深さを数えて閉じを探す。

    >>> stated_value("evt-comment:fast_program_bytes(=256)")
    '256'
    >>> stated_value("products:zh(=1（OPA1）)")
    '1（OPA1）'
    >>> stated_value("CH32V203DS0.PDF:zh(min=60,typ=82,max=110,unit=)")
    'min=60,typ=82,max=110,unit='
    >>> stated_value("CH32V203DS0.PDF:en")
    ''
    """
    m = STATED.search(token)
    at = m.start() if m else -1
    if at == -1:
        return ""
    depth, out = 0, []
    for ch in token[at:]:
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        out.append(ch)
    return "".join(out).lstrip("=").strip()


def conflicts_in(name: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    key = KEYS[name]
    out = []
    for row in rows:
        for column in row:
            if not column or "confidence" not in column or row[column].strip() != "conflict":
                continue
            field = "" if column == "confidence" else column[:-len("_confidence")]
            basis = row.get("basis" if not field else f"{field}_basis", "") or ""
            tokens = dissenting_tokens(basis)
            named = [m.group(1) for t in tokens if (m := NAMES_FIELD.search("!" + t))
                     and m.group(1) in row]
            about = field or (named[0] if named else ASSERTS.get(name, ""))
            out.append({
                "table": name,
                "family": row.get("family", ""),
                "series": row.get("series", ""),
                "part_number": row.get("part_number", ""),
                "subject": " ".join(f"{k}={row.get(k, '')}" for k in key if row.get(k)),
                "field": about,
                "kept": row.get(about, ""),
                "dissenting": ";".join(
                    t[:m.start()] if (m := STATED.search(t)) else t for t in tokens),
                "alternative": ";".join(v for t in tokens if (v := stated_value(t))),
                "basis": basis,
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先の上書き（試験用）")
    args = ap.parse_args()

    tables = paths.CATALOG_TABLES + paths.EVIDENCE_TABLES
    missing = [n for n in tables if n not in KEYS]
    if missing:
        print(f"行を名指す鍵が決まっていない表 {missing}"
              "——tools/build_conflicts.py の KEYS に足すこと", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for name in tables:
        rows += conflicts_in(name, paths.load(name))
    rows.sort(key=lambda r: (r["table"], r["subject"], r["field"]))

    dest = paths.index("conflicts", args.out)
    paths.write(dest, rows, COLUMNS)
    tally = collections.Counter(r["table"] for r in rows)
    silent = sum(1 for r in rows if not r["dissenting"])
    print(f"{dest}: {len(rows)} 行  {dict(tally.most_common())}", file=sys.stderr)
    print(f"  - 異論を basis の DSL に持たない行（食い違いは散文で記録）: {silent}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
