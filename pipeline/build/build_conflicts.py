#!/usr/bin/env python3
"""資料どうしが食い違っている箇所を1表に集める → index/conflicts.csv

**証拠は食い違いを片方に寄せず `conflict` として両論を残します**（`docs/handoff.ja.md`
の規則）。その記録は多くの表に散っているので、ここで1表に集めます。

新しい事実は足しません——`confidence` が `conflict` の行を集め、`basis`（文法は
`pipeline/common/basis_grammar.py`）の `!` の項から「どの出所が異を唱えているか」と「その出所は何と
言っているか」を、食い違う列の名前つきで取り出すだけです。

    どの表の・何について（field）・どの出所が（dissenting）・何と言っているか（alternative）

`basis` に `!` の項が無い conflict の行（食い違いを散文で記録している行）は、表ごとの主張の列
（`ASSERTS`）があればそれを `field` にし、`dissenting` と `alternative` は空になります。

実行:
    uv run pipeline/build/build_conflicts.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))
import basis_grammar  # noqa: E402
import paths  # noqa: E402

COLUMNS = ["table", "family", "series", "part_number", "subject", "field",
           "kept", "dissenting", "alternative", "basis"]

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
    "flash_program_method": ("family",),
    "eval_boards": ("family", "board"),
    "evt_examples": ("family", "example"),
    "link_firmware": ("device", "mcu", "mode", "role"),
    "link_firmware_issues": ("device", "mcu", "mode", "version"),
    "operating_conditions": ("series", "symbol", "parameter", "condition"),
    "absolute_maximum_ratings": ("series", "symbol", "parameter", "condition"),
    "remap_fields": ("series", "selector"),
    "remap_routes": ("series", "selector", "value", "signal"),
    "pin_conditions": ("series", "signal", "condition"),
    "figures": ("part_number", "kind"),
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
    "device_id_addresses": ("family",),
    "device_ids": ("part_number", "id_source"),
    "esig": ("family", "register"),
}

# `basis` の文法は `pipeline/common/basis_grammar.py`。異を唱える出所は `!` で始まり、その出所が言う値を
# 食い違う列の名前つきで持つ（`!CH32V007DS0.PDF:zh(max=115)`・`!rm-remap-grid(route=remap-2)`）。
# 列の名前が `field` に、その出所の値が `alternative` に、採った値が `kept` に入る。

# **その表が1行につき主張している列。** 行ごと `conflict` と印が付く表では、
# 食い違っているのはこの列の値。鍵（KEYS）と同じで表の形についての静的な事実で、
# その食い違いが何についてかの推測ではない。分からない表は載せない（空欄になる）。
ASSERTS: dict[str, str] = {
    "pin_functions": "route",
    "product_attributes": "value",
    "register_fields": "bits",
    # 格子が既定の pad について異を唱えた経路（F-73）。食い違っているのは値。
    "remap_routes": "value",
    "pin_conditions": "pad",
    "opa_cmp_registers": "bits",
}
# `operating_conditions` はここに載せない。1行が min/typ/max/unit の4つを主張して
# いて、争っているのがどれかは行ごとに違う（`basis` の `(min=60,typ=82,…)` が
# 名指ししている）。1つの列を決め打つと、min の食い違いを max の話として書く。
#
# `figures` も載せない。主張しているのは `page_zh`・`page_en` の2つで、**両版で
# 違うのが当たり前**（版面の割り付けが違う）——この表は構造上 `conflict` を持たない。


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
            dissents = [t for t in basis_grammar.parse(basis) if t["mark"] == "!" and t["dissent"]]
            columns = list(dict.fromkeys(c for t in dissents for c in t["dissent"]))
            about = [field] if field else (columns or ([ASSERTS[name]] if name in ASSERTS else []))
            out.append({
                "table": name,
                "family": row.get("family", ""),
                "series": row.get("series", ""),
                "part_number": row.get("part_number", ""),
                "subject": " ".join(f"{k}={row.get(k, '')}" for k in key if row.get(k)),
                "field": ";".join(about),
                "kept": ";".join(row.get(c, "") for c in about),
                "dissenting": ";".join(t["term"][1:t["term"].rfind("(")] for t in dissents),
                "alternative": ";".join(t["dissent"].get(c, "") for t in dissents for c in about
                                        if c in t["dissent"]),
                "basis": basis,
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先の上書き（試験用）")
    args = ap.parse_args()

    tables = paths.SOURCE_TABLES
    missing = [n for n in tables if n not in KEYS]
    if missing:
        print(f"行を名指す鍵が決まっていない表 {missing}"
              "——pipeline/build/build_conflicts.py の KEYS に足すこと", file=sys.stderr)
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
    print(f"  - basis に ! の項を持たない conflict の行（食い違いは散文で記録）: {silent}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
