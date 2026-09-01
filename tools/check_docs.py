#!/usr/bin/env python3
"""文書の主張が生成物と合っているかを見る → docs/*.md・README

`check_tables.py` は表どうしを見て、`check_counts.py` は資料の数と pin を見る。
どちらも**表を説明する文章**は見ない。そこで起きるのが「データは正しいのに、
利用者が古い説明を読む」型の腐りで、2026-08-29 の監査が実例を挙げた:

    F-11（WCH-Link の版番号）は解決して CSV も直っているのに、7つの文書と
    1つの tool の説明がまだ「未解決」と書いていた
    table-reliability の pinout 行数が 24,977 のまま（実際は 24,982）と、
    clock 5表の合計が 1,066 のまま（実際は 1,067）

**文書側に印は足さない。** 印は書き忘れるので検査の対象にならない。代わりに
この tool が「どの綴りがどの数か」を持ち、綴りが変われば当たらなくなったことを
失敗として言う（`PROSE` は1件も当たらなければ落ちる）。

見るのは3つ:

    行数    docs/table-reliability.ja.md の「行数」列 × 実際の行数
    総数    README（両言語）が数える family・series・型番・表の数
    状態    worklist の F 台帳で ✅ と印した穴を、別の文書が「未解決」と
            書いていないか（逆に、台帳が開いている穴を「解決」と書いていないか）

実行:
    uv run tools/check_docs.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

RELIABILITY = REPO / "docs" / "table-reliability.ja.md"
WORKLIST = REPO / "docs" / "worklist.ja.md"

# docs/table-reliability.ja.md の「行数」列。**左端のセルの綴りそのまま** →
# 数え直す量。索引の表は `index:` を付ける（`features`・`timers`・`registers`
# は証拠と索引の両方にあるので、綴りだけでは決まらない）。複数なら合計。
ROW_COUNTS: dict[str, tuple[str, ...]] = {
    "products": ("products",),
    "product_attributes": ("product_attributes",),
    "packages": ("packages",),
    "pins": ("pins",),
    "pin_functions": ("pin_functions",),
    "operating_conditions": ("operating_conditions",),
    "features": ("features",),
    "memory_configs": ("memory_configs",),
    "errata": ("errata",),
    "remap_fields": ("remap_fields",),
    "remap_routes": ("remap_routes",),
    "timers": ("timers",),
    "flash_geometry": ("flash_geometry",),
    "opa_cmp_registers": ("opa_cmp_registers",),
    "clock_enables": ("clock_enables",),
    "adc_internal": ("adc_internal",),
    "usbpd_plumbing": ("usbpd_plumbing",),
    "debug_data": ("debug_data",),
    "debug_wiring": ("debug_wiring",),
    "option_bytes": ("option_bytes",),
    "option_byte_fields": ("option_byte_fields",),
    "device_id_addresses": ("device_id_addresses",),
    "device_ids": ("device_ids",),
    "dma_requests": ("dma_requests",),
    "interrupts": ("interrupts",),
    "memory_map": ("memory_map",),
    "systick": ("systick",),
    "evt_variants": ("evt_variants",),
    "pin_alternate": ("pin_alternate",),
    "clock_configs 他 clock_* 5表": ("clock_configs", "clock_prescalers", "clock_sources",
                                     "clock_symbols", "clock_init"),
    "evt_examples": ("evt_examples",),
    "eval_boards": ("eval_boards",),
    "register_blocks": ("register_blocks",),
    "registers": ("registers",),
    "register_fields": ("register_fields",),
    "register_layouts（`index/`）": ("index:register_layouts",),
    "pinout（旧 pin_roles）": ("index:pinout",),
    "features（旧 feature_tags）": ("index:features",),
    "capabilities（`index/`）": ("index:capabilities",),
    "conflicts（`index/`）": ("index:conflicts",),
    "debug_interfaces（`index/`）": ("index:debug_interfaces",),
    "sources": ("sources",),
    "series / families / cores / documents": ("series", "families", "cores", "documents"),
    "toolchains": ("toolchains",),
    "link_firmware": ("link_firmware",),
}

# 文章の中の数。(ファイル, 正規表現, 量の名前)。正規表現は数を `n` で取る。
# **当たった全てが一致し、かつ1件以上当たること**を見る——文章を書き換えて
# 綴りが変わったとき、黙って通ってしまわないように。
PROSE: tuple[tuple[str, str, str], ...] = (
    ("README.md", r"\((?P<n>\d+) families,", "families"),
    ("README.md", r"families,\s+(?P<n>\d+) series", "series"),
    ("README.md", r"series,\s*\n?\s*(?P<n>\d+) part numbers", "products"),
    ("README.md", r"\[`catalog/`\]\([^)]*\) \((?P<n>\d+) tables\)", "catalog_tables"),
    ("README.md", r"\[`evidence/`\]\([^)]*\) \((?P<n>\d+) tables\)", "evidence_tables"),
    ("README.ja.md", r"（(?P<n>\d+) family・", "families"),
    ("README.ja.md", r"family・(?P<n>\d+) series", "series"),
    ("README.ja.md", r"series・(?P<n>\d+)型番）", "products"),
    ("README.ja.md", r"目録 (?P<n>\d+)表", "catalog_tables"),
    ("README.ja.md", r"証拠 (?P<n>\d+)表", "evidence_tables"),
    # pinout の内訳。合計は ROW_COUNTS が見るので、ここは分解のほう。
    ("docs/table-reliability.ja.md", r"機能行 (?P<n>[\d,]+)＋", "pinout_functions"),
    ("docs/table-reliability.ja.md", r"＋機能の無い lead (?P<n>[\d,]+)", "pinout_leads"),
    # 「埋めようがない」と言い切っている残数。埋まれば説明のほうが古くなる。
    ("docs/table-reliability.ja.md", r"残り(?P<n>[\d,]+)行は header に構造体が無く",
     "register_fields_without_member"),
    ("docs/worklist.ja.md", r"\*\*1,591 → (?P<n>[\d,]+) 行\*\*",
     "register_fields_without_member"),
    ("docs/worklist.ja.md", r"置き場所がそもそも無い\*\* (?P<n>[\d,]+)行",
     "register_fields_without_member"),
    ("docs/worklist.ja.md", r"証拠の表の conflict は (?P<n>[\d,]+) 行", "conflict_rows"),
    ("README.ja.md", r"比較表の属性（(?P<n>\d+)種類の綴り", "product_attributes:kinds"),
    ("README.ja.md", r"種類の綴り・(?P<n>[\d,]+)行", "product_attributes"),
    # confidence の分布。**行数より先に動く**（資料の版が変わらなくても、
    # 読み方を直せば confirmed が増える）ので、書いてあるなら数え直す。
    ("docs/table-reliability.ja.md", r"\| product_attributes \| [\d,]+ \| confirmed (?P<n>[\d,]+)",
     "product_attributes:confirmed"),
    ("docs/table-reliability.ja.md", r"\| product_attributes \|[^|]*\|[^|]*conflict (?P<n>[\d,]+)",
     "product_attributes:conflict"),
    ("docs/table-reliability.ja.md", r"\| product_attributes \|[^|]*\|[^|]*ref (?P<n>[\d,]+)",
     "product_attributes:reference"),
    ("docs/worklist.ja.md", r"`index/capabilities.csv`新設（2026-08-29。(?P<n>[\d,]+)行）",
     "index:capabilities"),
    ("docs/handoff.ja.md", r"目録(?P<n>\d+)表", "catalog_tables"),
    ("docs/handoff.ja.md", r"証拠(?P<n>\d+)表", "evidence_tables"),
    ("docs/handoff.ja.md", r"索引(?P<n>\d+)表", "index_tables"),
    # 進捗の要約と、下の台帳（F＝既知の穴、G＝表示）。**要約のほうが先に古くなる**ので
    # 台帳から数え直す。
    ("docs/worklist.ja.md", r"\| 既知の穴（F系） \| (?P<n>\d+) \|", "holes_resolved"),
    ("docs/worklist.ja.md", r"\| 既知の穴（F系） \| \d+ \| (?P<n>\d+)（", "holes_open"),
    ("docs/worklist.ja.md", r"\| 表示（G系） \| (?P<n>\d+) \|", "display_done"),
    ("docs/worklist.ja.md", r"\| 表示（G系） \| \d+ \| (?P<n>\d+) \|", "display_open"),
)

# 「この穴はまだ開いている／閉じた」と読める書き方。**節単位で見る**——
# 1行に複数の穴の話が並ぶ（`F-6/7・F-51（資料側）。F-40/F-41 は修正済み`）ので、
# 行全体を窓にすると隣の穴の状態を拾う。句点と表の区切りで切れば混ざらない。
OPEN_WORDS = re.compile(r"未解決|未確定|決まらない|確定しない|🔴")
CLOSED_WORDS = re.compile(r"✅|解決済|修理済|修正済")
CLAUSE = re.compile(r"[。|]")
# 台帳が ✅ でも「残り」が名指しで残る穴（F-4 の6行・F-24 の8セル）。
# **その残りを開いた穴として書くのは正しい**ので、番号の直後が「残り」なら見ない。
REMAINDER = re.compile(r"\s*(の)?残り")


def rows(name: str) -> list[dict]:
    return paths.load_index(name[len("index:"):]) if name.startswith("index:") else paths.load(name)


def quantities() -> dict[str, int]:
    """文書が名指しで書いている数を、生成物から数え直す。"""
    out = {name: len(rows(name)) for name in
           paths.CATALOG_TABLES + paths.EVIDENCE_TABLES}
    out.update({f"index:{name}": len(paths.load_index(name)) for name in paths.INDEX_TABLES})
    # 表ごとの confidence の分布と、product_attributes の属性の種類数。
    for name in paths.CATALOG_TABLES + paths.EVIDENCE_TABLES:
        table = rows(name)
        for level in ("confirmed", "reference", "conflict"):
            out[f"{name}:{level}"] = sum(
                1 for r in table for c, v in r.items()
                if c and "confidence" in c and (v or "").strip() == level)
    out["product_attributes:kinds"] = len({r["attribute"] for r in
                                           paths.load("product_attributes")})
    out["catalog_tables"] = len(paths.CATALOG_TABLES)
    out["evidence_tables"] = len(paths.EVIDENCE_TABLES)
    # 索引は manifest.csv も1表として数える（文書がそう数えている）。
    out["index_tables"] = len(list(paths.INDEX.glob("*.csv")))
    pinout = paths.load_index("pinout")
    functions = [r for r in pinout if r["peripheral"] or r["role"] or r["signal"]]
    out["pinout_functions"] = len(functions)
    out["pinout_leads"] = len(pinout) - len(functions)
    out["register_fields_without_member"] = sum(
        1 for r in paths.load("register_fields") if not r["member"])
    # 証拠の表にある conflict の総数（`*_confidence` 列を持つ表は列ごとに数える）。
    out["conflict_rows"] = sum(
        1 for name in paths.EVIDENCE_TABLES for r in rows(name)
        if any((v or "").strip() == "conflict"
               for k, v in r.items() if k and "confidence" in k))
    # `ledger()` は下で定義している（呼ぶのは main のあと）。
    holes = ledger()
    out["holes_resolved"] = sum(1 for done in holes.values() if done)
    out["holes_open"] = sum(1 for done in holes.values() if not done)
    display = ledger(r"G-?\d+", column=3)
    out["display_done"] = sum(1 for done in display.values() if done)
    out["display_open"] = sum(1 for done in display.values() if not done)
    return out


def tables_of(text: str):
    """markdown の表を (見出し行, データ行) で返す。"""
    header: list[str] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if header is None:
            header = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        yield header, cells, number


def check_row_counts(known: dict[str, int]) -> list[str]:
    """「行数」列を持つ表の主張と、実際の行数。"""
    bad = []
    seen = set()
    for header, cells, number in tables_of(RELIABILITY.read_text(encoding="utf-8")):
        if len(header) < 2 or header[1] != "行数" or len(cells) < 2:
            continue
        label, claim = cells[0], cells[1]
        seen.add(label)
        m = re.match(r"([\d,]+)", claim)
        if not m:
            bad.append(f"table-reliability.ja.md:{number}: 「{label}」の行数を数として読めない: {claim!r}")
            continue
        stated = int(m.group(1).replace(",", ""))
        names = ROW_COUNTS.get(label)
        if names is None:
            bad.append(f"table-reliability.ja.md:{number}: 「{label}」がどの表の数か "
                       "check_docs.py の ROW_COUNTS に無い——表を足したら対応も足すこと")
            continue
        actual = sum(known[n] for n in names)
        if stated != actual:
            bad.append(f"table-reliability.ja.md:{number}: 「{label}」の行数が {stated:,} と"
                       f"書いてあるが実際は {actual:,}")
    for label in ROW_COUNTS:
        if label not in seen:
            bad.append(f"check_docs.py: ROW_COUNTS の「{label}」が "
                       "table-reliability.ja.md に無い——文書側の綴りが変わった")
    return bad


def check_prose(known: dict[str, int]) -> list[str]:
    """文章の中の数。当たった全てが一致し、かつ1件以上当たること。"""
    bad = []
    for name, pattern, quantity in PROSE:
        path = REPO / name
        text = path.read_text(encoding="utf-8")
        hits = list(re.finditer(pattern, text))
        if not hits:
            bad.append(f"{name}: /{pattern}/ が1件も当たらない——文章の綴りが変わったなら "
                       "check_docs.py の PROSE を直すこと")
            continue
        actual = known[quantity]
        for m in hits:
            stated = int(m.group("n").replace(",", ""))
            if stated != actual:
                line = text[:m.start()].count("\n") + 1
                bad.append(f"{name}:{line}: {quantity} を {stated:,} と書いてあるが "
                           f"実際は {actual:,}")
    return bad


def ledger(numbering: str = r"F-\d+", column: int = 4) -> dict[str, bool]:
    """worklist の台帳: 番号 → 済みか（判断の欄が ✅ で始まる）。

    F 台帳（既知の穴）は5列で判断が4番目、G 台帳（表示）は4列で状態が3番目。
    """
    out: dict[str, bool] = {}
    for _, cells, _ in tables_of(WORKLIST.read_text(encoding="utf-8")):
        if len(cells) <= column or not re.fullmatch(numbering, cells[0]):
            continue
        out.setdefault(cells[0], cells[column].startswith("✅"))
    return out


def check_holes(open_or_not: dict[str, bool]) -> list[str]:
    """台帳の状態と、他の文書が同じ穴について書いていること。

    worklist.ja.md 自身は見ない——穴の名前（「版番号が確定しない」）を列に持つのが
    台帳の仕事で、そこは状態の主張ではない。
    """
    bad = []
    for path in sorted(REPO.glob("**/*.md")):
        if any(part.startswith(".") for part in path.parts) or path.name == WORKLIST.name:
            continue
        rel = path.relative_to(REPO)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for clause in CLAUSE.split(line):
                for m in re.finditer(r"F-\d+", clause):
                    resolved = open_or_not.get(m.group(0))
                    if resolved is None or REMAINDER.match(clause[m.end():]):
                        continue
                    said = clause.strip()[:70]
                    if resolved and OPEN_WORDS.search(clause):
                        bad.append(f"{rel}:{number}: {m.group(0)} は台帳で解決済みだが "
                                   f"「{said}」と書いてある")
                    if not resolved and CLOSED_WORDS.search(clause):
                        bad.append(f"{rel}:{number}: {m.group(0)} は台帳で未解決だが "
                                   f"「{said}」と書いてある")
    return bad


def check_liquid() -> list[str]:
    """コミットするMarkdownにLiquidが特別扱いする並びが無いこと。

    このrepositoryはGitHub Pagesで配信され、PagesのJekyllはmarkdown処理の前に
    **全.mdへLiquidを走らせる**。波括弧2連や波括弧+percentが生で書いてあると
    Pagesのビルドごと落ちる——バッククォートでは保護されない。実際に
    pipeline/README.ja.mdの「Liquid危険文字の説明」自身がビルドを壊した
    （2026-09-01、ユーザーがPagesのエラーで発見）。
    """
    dangerous = ("{" + "{", "{" + "%")
    bad = []
    for path in Path(".").rglob("*.md"):
        parts = path.parts
        if parts[0].startswith(".") or parts[0] in ("node_modules",):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for sequence in dangerous:
            at = text.find(sequence)
            if at >= 0:
                line = text[:at].count("\n") + 1
                bad.append(f"{path}:{line}: Liquidが特別扱いする並び {sequence!r} "
                           "——GitHub PagesのJekyllビルドが落ちる。言い換えること")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.parse_args()

    known = quantities()
    holes = ledger()
    bad = (check_row_counts(known) + check_prose(known) + check_holes(holes)
           + check_liquid())
    if bad:
        seen: list[str] = []
        for b in bad:
            if b not in seen:
                seen.append(b)
        print(f"文書と生成物が食い違っている箇所 {len(seen)} 件:", file=sys.stderr)
        for b in seen:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"文書の数と状態は生成物と一致しています"
          f"（行数 {len(ROW_COUNTS)} 行・文章 {len(PROSE)} 箇所・穴 {len(holes)} 件）",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
