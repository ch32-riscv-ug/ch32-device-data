#!/usr/bin/env python3
"""Check that every reference between the normalised tables actually joins.

The tables are meant to be used relationally -- products join series, pins join
products, everything that names a document joins documents.csv -- so a value
that fails to join is a defect, whether a typo, a normalisation gap, or a row
that never got generated. Prints each violation and exits non-zero on any.

Usage:
    uv run tools/check_tables.py [--tables tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import signal_vocabulary  # noqa: E402


import paths  # noqa: E402


def load(tables: Path | None, name: str) -> list[dict]:
    """catalog/evidence の表。``tables`` は試験用の上書きディレクトリ。"""
    path = paths.table(name, tables)
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_index(name: str) -> list[dict]:
    with paths.index(name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# 索引 `pinout` が語彙で覆えなかった signal。**目標は 0** で、ここに並んでいるのは
# まだ埋まっていない穴の実測値。増えたら失敗させ、減らしたらこの表も一緒に減らす。
#
#   AETR / AETR2 / TIETR   CH32V003。ADCのトリガがADC2 fieldのどちらか資料が
#                          決めていない（worklist の F-8）。資料側なので埋まらない
#   HO* / LO* / IS* / QII  CH32M030 のモータ駆動。比較表が
#                          `Source current module ISOURCE` のように群を名乗る
#   SWIM                   CH32M030 PA3。資料に対応の記述が見つかっていない
#   Q_DET* / V_DET         CH32M030 の検出入力。周辺名を名乗らない綴り
# 2026-08-25 に最後の26種（CH32M030 の専用機能・CH32V003 の略記・CH32V208 の
# `ANT`）を語彙へ入れて空になった。**空であることが検査の対象**——新しい綴りが
# 資料に現れれば、ここに名前が無いので落ちる。
KNOWN_ROLE_GAPS: dict[str, int] = {}

# 索引 `pinout` の `remap-N` 行のうち、**どの selector がその経路を選ぶのか
# 名前を付けられなかった行**の実測値。`(series, signal)` ごとに数える。
#
# `candidates/_report.json` の `unresolved`（worklist の F-6 の32）とは**別の
# 数**です。あちらは candidate 1件ごとの function 数、こちらは 103 型番へ
# 展開したあとの行数で、しかも candidate を作る経路（RM格子）を通らない
# 事実——datasheet の pin 表が片方の版だけで書いた経路——はあちらに現れま
# せん。「未解決は32件だけ」を index に対する主張として読むと合わないので、
# index 側の数はここで別に持ちます（2026-08-28 に監査で指摘された）。
#
#   I2S3_*   CH32V303/305/307/317。`SPI3_REMAP` が経路を決めるが V30x の RM
#            格子がその経路を書かない（F-6。資料側）
#   UHSIF_*  CH32H417 の PF12/PF13/PE7。**中文版だけ**が remap 欄に
#            `UHSIF_PORT0_1` と書き、英語版の同じ欄は空。RM 格子は値1を
#            PC1→PORT3 のようにずらして書き、この3 pad を値0（既定）に
#            当てているので、中文版の主張を裏づける行がない（F-51。資料側）
KNOWN_SELECTOR_GAPS: dict[tuple[str, str], int] = {}

# catalog/toolchains.csv の語彙。上流（MounRiver）の綴りではなく、こちらで
# 正規化した名前（build_toolchains.py の OS_NAME / ARCH_NAME / KIND_ORDER と対）。
TOOLCHAIN_KINDS = {"toolchain", "ide", "ide-community", "components"}
TOOLCHAIN_OSES = {"windows", "linux", "macos"}
TOOLCHAIN_ARCHES = {"", "x86", "x64", "arm64"}
TOOLCHAIN_API = "https://api.mounriver.com/mountriver/api/version/"

GPIO_NAME = re.compile(r"^P[A-H]\d{1,2}$")
GRID_VALUE = re.compile(r"!rm-remap-grid\(=(?P<route>remap-\d+)\)")


def build_index_grid(basis: str) -> str | None:
    m = GRID_VALUE.search(basis)
    return m.group("route") if m else None


# 同じ lead 番号を複数の pad が持つ組の数。**目標は「資料のとおり」**で、
# 増減はどちらも異常——増えれば結合セルの読み違い、減れば pad の取りこぼし。
# 内訳は kind の組で持つ。gpio どうしなら内部短絡、power どうしなら同じ節点。
KNOWN_SHARED_LEADS = {
    ("gpio", "gpio"): 65,
    ("gpio", "other"): 15,
    ("power", "power"): 12,
    ("gpio", "gpio", "gpio"): 2,
    ("power", "power", "power"): 2,
}


def shared_leads(t: dict) -> list[str]:
    """同じ (part_number, pin) を持つ pad の組を数え、記録と突き合わせる。"""
    together: dict[tuple[str, str], list[dict]] = {}
    for r in t["pins"]:
        if r["pin"] in ("", "EP"):
            continue
        together.setdefault((r["part_number"], r["pin"]), []).append(r)
    found: dict[tuple, int] = {}
    for members in together.values():
        if len(members) < 2:
            continue
        shape = tuple(sorted(m["kind"] for m in members))
        found[shape] = found.get(shape, 0) + 1
    out = []
    for shape in sorted(set(found) | set(KNOWN_SHARED_LEADS)):
        now, before = found.get(shape, 0), KNOWN_SHARED_LEADS.get(shape, 0)
        if now != before:
            out.append(f"pins: 同じ lead 番号を共有する {'+'.join(shape)} の組が "
                       f"{before} から {now} に変わった——結合セルの読み方か "
                       "pad の拾い方が動いている（tables/README.ja.md の"
                       "「同じlead番号を複数のpadが持つ行」）")
    return out


def pin_numbering(t: dict) -> list[str]:
    """封装の公称 lead 数と、pins が持つ番号の連番が一致するか。

    **これは資料に依らない検査です。** LQFP100 の足は 1〜100 の100本しかなく、
    それは package 名が言っていること——pin 表の読み方が正しいかどうかを、
    pin 表とは別の出所（`catalog/packages.pin_count`）で測れる唯一の不変条件
    です。番号は行のキーなので、抜けても他の行はずれず、読み比べるだけでは
    気付けません。

    実際にこれで5型番が見つかりました（2026-08-28）。資料が「使わない」と
    書いた足（`NC`・`未使用`・`Unused`）を pad と見ていなかったため、
    CH32V203RBT6 の lead 47 は直前の pad 名 `VDD_2` を継いで**別の pad に
    化け**、48 は落ち、CH32V205VCT6・CH32V303/307/317VCT6 の lead 73 が
    落ちていました（`extract_pins.NO_CONNECT`）。

    exposed pad は番号を持たない（`EP`）ので数に入れない。同じ番号を複数の
    pad が持つ行（内部短絡・共用節点）は `shared_leads` が別に見るので、
    ここは番号の**集合**だけを見る。
    """
    count_of = {r["package"]: r["pin_count"] for r in t["packages"]}
    leads: dict[str, set[int]] = collections.defaultdict(set)
    for r in t["pins"]:
        if r["pin"].isdigit():
            leads[r["part_number"]].add(int(r["pin"]))
    out = []
    for product in sorted(t["products"], key=lambda r: r["part_number"]):
        part, package = product["part_number"], product["package"]
        want = count_of.get(package)
        if not want or not want.isdigit():
            continue
        got = leads.get(part, set())
        expected = set(range(1, int(want) + 1))
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        if missing:
            out.append(f"pins: {part} ({package}, {want} lead) の lead 番号 "
                       f"{missing} が無い——pin 表の行を落としている"
                       "（NC の足も番号を持つ。extract_pins.NO_CONNECT）")
        if extra:
            out.append(f"pins: {part} ({package}, {want} lead) に範囲外の lead 番号 "
                       f"{extra} がある——列の対応か番号の読みが違う")
    return out


def pin_role_coverage(t: dict) -> list[str]:
    """索引 `pinout` が覆えていない signal を、記録してある実測値と突き合わせる。

    **数の閾値ではなく名前で持つ。** 「95%以上あればよい」にすると、片方が
    直って別の穴が開いても気付けない。名前で持てば、新しい綴りが増えたことも
    埋まったことも、どちらも同じ検査が言う。
    """
    import build_index  # noqa: PLC0415

    _, unresolved = build_index.pinout_rows(t["products"], t["pins"], t["pin_functions"],
                                            t["remap_routes"])
    found: dict[str, int] = {}
    for (_, signal), count in unresolved.items():
        found[signal] = found.get(signal, 0) + count
    out = []
    for signal in sorted(set(found) | set(KNOWN_ROLE_GAPS)):
        now, before = found.get(signal, 0), KNOWN_ROLE_GAPS.get(signal, 0)
        if now > before:
            out.append(f"pinout: 語彙で覆えない {signal!r} が {before} 行から "
                       f"{now} 行に増えた（tools/signal_vocabulary.py に規則を足すか"
                       "、抽出を直す）")
        elif now < before:
            out.append(f"pinout: 語彙で覆えない {signal!r} が {before} 行から "
                       f"{now} 行に減った——KNOWN_ROLE_GAPS を更新すること")
    return out


def remap_selector_coverage(t: dict) -> list[str]:
    """`remap-N` の行が selector まで辿れているか、記録した実測値と突き合わせる。

    `pinout` の `remap-N` 行は「この pad にこの signal がこの経路で出る」と
    言っているだけで、**どのレジスタ field のどの値がその経路か**は
    `remap_routes` と結合して初めて分かります。結合できなかった行は
    `selector` が空になり、consumer からは「remap すれば出るが、書くレジスタが
    分からない」に見えます。

    `pin_role_coverage` と同じ持ち方——閾値ではなく `(series, signal)` の名前で
    持つ。片方が埋まって別の穴が開いたことも、増えたことも同じ検査が言う。
    """
    found: dict[tuple[str, str], int] = collections.Counter()
    for r in t["index:pinout"]:
        if r["route"].startswith("remap-") and not r["selector"]:
            found[(r["series"], r["signal"])] += 1
    out = []
    for key in sorted(set(found) | set(KNOWN_SELECTOR_GAPS)):
        now, before = found.get(key, 0), KNOWN_SELECTOR_GAPS.get(key, 0)
        if now == before:
            continue
        where = f"{key[0]} の {key[1]}"
        if now > before:
            out.append(f"pinout: selector を決められない {where} が {before} 行から "
                       f"{now} 行に増えた（remap_routes に経路が無いか、"
                       "pin 表の読みが壊れている）")
        else:
            out.append(f"pinout: selector を決められない {where} が {before} 行から "
                       f"{now} 行に減った——KNOWN_SELECTOR_GAPS を更新すること")
    return out


def index_checks(t: dict) -> list[str]:
    """索引は証拠から機械生成したもので、証拠に無い行が無いこと。manifest が中身と一致すること。

    pinout の戻し方は main() にある（route だけ格子の値を採る行があるため）。
    """
    bad: list[str] = []
    # routes ⊆ remap_routes
    routes = {(r["series"], r["selector"], r["value"], r["signal"], r["pad"]) for r in t["remap_routes"]}
    for r in t["index:routes"]:
        if (r["series"], r["selector"], r["value"], r["signal"], r["pad"]) not in routes:
            bad.append(f"routes: remap_routes にない行 {r['series']} {r['selector']} 値{r['value']} {r['signal']}")
    # registers（索引）⊆ register_fields ∪ registers（証拠）
    defines = {(r["family"], r["define"]) for r in t["register_fields"]}
    regs = {(r["family"], r["type"], r["register"]) for r in t["registers"]}
    for r in t["index:registers"]:
        if r["define"]:
            if (r["family"], r["define"]) not in defines:
                bad.append(f"registers(index): register_fields にない define {r['family']} {r['define']}")
        elif (r["family"], r["type"], r["register"]) not in regs:
            bad.append(f"registers(index): registers にない {r['family']} {r['type']}.{r['register']}")
    # register_map ⊆ register_blocks × registers、address = base + offset
    base_of = {(r["family"], r["block"]): int(r["base_address"], 16) for r in t["register_blocks"]}
    for r in t["index:register_map"]:
        base = base_of.get((r["family"], r["block"]))
        if base is None:
            bad.append(f"register_map: register_blocks にない block {r['family']} {r['block']}")
        elif r["register"] and (r["family"], r["type"], r["register"]) not in regs:
            bad.append(f"register_map: registers にない {r['family']} {r['type']}.{r['register']}")
        elif r["offset"] and int(r["address"], 16) != base + int(r["offset"], 16):
            bad.append(f"register_map: {r['family']} {r['block']}.{r['register']} の address が base+offset でない")
    # dma ⊆ dma_requests（綴りそのままの列で戻す）
    requests = {(r["family"], r["variant"], r["dma"], r["channel"], r["request_id"], r["request"])
                for r in t["dma_requests"]}
    for r in t["index:dma"]:
        if (r["family"], r["variant"], r["dma"], r["channel"], r["request_id"], r["spelled"]) not in requests:
            bad.append(f"dma: dma_requests にない行 {r['family']} {r['spelled']}")
        if r["remap"] not in ("", "selectable", "default", "remap"):
            bad.append(f"dma: {r['family']} {r['request']} の remap {r['remap']!r}")
        if not r["peripheral"]:
            bad.append(f"dma: {r['family']} {r['request']} の peripheral が空")
    # timers（索引）⊆ timers（証拠）
    timers = {(r["family"], r["timer"]) for r in t["timers"]}
    for r in t["index:timers"]:
        if (r["family"], r["timer"]) not in timers:
            bad.append(f"timers(index): timers にない {r['family']} {r['timer']}")
    # parts ⊆ products
    products = {r["part_number"] for r in t["products"]}
    if {r["part_number"] for r in t["index:parts"]} != products:
        bad.append("parts: 型番の集合が products と違う")

    # manifest: index/ の全ファイルと sha256 が一致
    import hashlib  # noqa: PLC0415
    listed = {}
    with (paths.INDEX / "manifest.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            listed[r["path"]] = r["sha256"]
    actual = {p.relative_to(paths.INDEX).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths.INDEX.rglob("*.csv") if p.name != "manifest.csv"}
    if listed != actual:
        changed = sorted(set(listed) ^ set(actual)) or sorted(k for k in listed if listed[k] != actual.get(k))
        bad.append(f"manifest: index/ の内容と一致しない（{len(changed)} ファイル。例 {changed[:3]}）"
                   "——tools/build_index.py を回し直す")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", type=Path, default=None,
                    help="catalog/evidence の表を読むディレクトリ（試験用の上書き）")
    args = ap.parse_args()
    # 目録と証拠は名前で、索引は `index:` を付けて持つ（`registers`・`timers` が
    # 証拠と索引の両方にあるので）。
    t = {name: load(args.tables, name)
         for name in paths.CATALOG_TABLES + paths.EVIDENCE_TABLES}
    for name in paths.INDEX_TABLES:
        t[f"index:{name}"] = load_index(name)
    if len(t) != len(paths.CATALOG_TABLES) + len(paths.EVIDENCE_TABLES) + len(paths.INDEX_TABLES):
        raise SystemExit("paths.py の表の名前が重複している")

    families = {r["family"] for r in t["families"]}
    series = {r["series"] for r in t["series"]}
    products = {r["part_number"] for r in t["products"]}
    packages = {r["package"] for r in t["packages"]}
    cores = {r["core"] for r in t["cores"]}
    documents = {r["document"] for r in t["documents"]}
    pin_pads = {(r["part_number"], r["pad"]) for r in t["pins"]}

    bad: list[str] = []

    def check(table: str, row_key: str, value: str, target: set, target_name: str,
              split: str | None = None) -> None:
        values = [v.strip() for v in value.split(split)] if split else [value]
        for v in values:
            if v and v not in target:
                bad.append(f"{table}: {row_key} の {v!r} が {target_name} にない")

    for r in t["series"]:
        check("series", r["series"], r["family"], families, "families")
        check("series", r["series"], r["datasheets"], documents, "documents", ";")
        check("series", r["series"], r["core"], cores, "cores", " + ")
    for r in t["products"]:
        check("products", r["part_number"], r["family"], families, "families")
        check("products", r["part_number"], r["series"], series, "series")
        check("products", r["part_number"], r["package"], packages, "packages")
        check("products", r["part_number"], r["datasheet"], documents, "documents")
    for r in t["packages"]:
        check("packages", r["package"], r["families"], families, "families", ";")
    for r in t["families"]:
        for column in ("datasheets", "reference_manuals", "evt"):
            check("families", r["family"], r[column], documents, "documents", ";")
        for token in r["cores"].split(";"):
            check("families", r["family"], token, cores, "cores", " + ")
    for r in t["cores"]:
        check("cores", r["core"], r["manual"], documents, "documents")

    # toolchains は上流（MounRiver）が「いま最新」と言っている配布物の一覧で、
    # 毎週 build_toolchains.py が取り直す（結合先を持たない目録なので、見るのは形）。
    # 語彙・重複・日付・URL の宛先まで。実体があるかは生成時に配信側を HEAD して見る。
    toolchain_files: set[str] = set()
    for r in t["toolchains"]:
        if r["kind"] not in TOOLCHAIN_KINDS:
            bad.append(f"toolchains: {r['file']} の kind {r['kind']!r} が語彙にない")
        if r["os"] not in TOOLCHAIN_OSES:
            bad.append(f"toolchains: {r['file']} の os {r['os']!r} が語彙にない")
        if r["arch"] not in TOOLCHAIN_ARCHES:
            bad.append(f"toolchains: {r['file']} の arch {r['arch']!r} が語彙にない")
        if not r["file"] or not r["version"]:
            bad.append(f"toolchains: file か version が空: {r!r}")
        if r["file"] in toolchain_files:
            bad.append(f"toolchains: {r['file']} が重複している")
        toolchain_files.add(r["file"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["released"]):
            bad.append(f"toolchains: {r['file']} の released {r['released']!r}")
        # サイズは配信側の HEAD で埋まる。空でよいのは配信側が Content-Length を
        # 言わなかった行（basis がそう名乗る）と、配信側を見ていない行だけ。
        sized = r["confidence"] == "confirmed" and "head(no size)" not in r["basis"]
        if not re.fullmatch(r"[1-9]\d*", r["size_bytes"]) and (sized or r["size_bytes"]):
            bad.append(f"toolchains: {r['file']} の size_bytes {r['size_bytes']!r}")
        if not (r["download_api"].startswith(TOOLCHAIN_API) and "resourceId=" in r["download_api"]):
            bad.append(f"toolchains: {r['file']} の download_api {r['download_api'][:60]!r}")
        if r["confidence"] not in ("confirmed", "reference", "conflict"):
            bad.append(f"toolchains: {r['file']} の confidence {r['confidence']!r}")
    kinds = collections.Counter(r["kind"] for r in t["toolchains"])
    # 上流の仕様変更は「空の表」として現れる。**使う側が当てにする形**を数で固定する。
    if kinds["toolchain"] < 1 or kinds["ide"] < 3:
        bad.append(f"toolchains: 行が足りない（上流の取得が壊れた？）: {dict(kinds)}")
    for r in t["errata"]:
        check("errata", r["id"], r["series"], series, "series", ";")
    for r in t["evt_examples"]:
        check("evt_examples", r["example"], r["family"], families, "families")
    for r in t["operating_conditions"]:
        check("operating_conditions", r["symbol"], r["series"], series,
              "series", ";")
        check("operating_conditions", r["symbol"], r["datasheet"], documents,
              "documents")
    for name in ("pins", "pin_functions"):
        for r in t[name]:
            check(name, r["part_number"], r["part_number"], products, "products")
            check(name, r["part_number"], r["datasheet"], documents, "documents")
    for r in t["pin_functions"]:
        if (r["part_number"], r["pad"]) not in pin_pads:
            bad.append(f"pin_functions: {r['part_number']} の pad {r['pad']!r} が pins にない")
    # `route=alias` は「pad 名に資料が括弧で添えた GPIO 名」（CH32M007 の `LO1 (PA0)`）。
    # signal は GPIO 名、pad は GPIO 名でない、pad ごとに1つ——それ以外の形で
    # 出たら抽出の読み違い。
    alias_of: dict[tuple[str, str], set[str]] = {}
    for r in t["pin_functions"]:
        if r["route"] != "alias":
            continue
        if not GPIO_NAME.match(r["signal"]) or GPIO_NAME.match(r["pad"]):
            bad.append(f"pin_functions: alias 行の形が違う {r['part_number']} "
                       f"{r['pad']!r} -> {r['signal']!r}（GPIO 名の別名だけを許す）")
        alias_of.setdefault((r["part_number"], r["pad"]), set()).add(r["signal"])
    for key, names in alias_of.items():
        if len(names) > 1:
            bad.append(f"pin_functions: {key} に alias が複数 {sorted(names)}")
    # **1本の足に2つの pad が出る行**（内部で短絡された IO ペア、共用の電源
    # 節点）。番号が一致していることが「同じ足」そのもので、内部接続を別の列で
    # 持たない代わりに、その形が壊れていないことをここで見る。
    bad += shared_leads(t)
    # 封装の公称 lead 数と番号の連番。pin 表とは別の出所で読みを測る。
    bad += pin_numbering(t)

    for r in t["product_attributes"]:
        check("product_attributes", r["attribute"], r["part_number"], products, "products")

    # 索引 pinout は pins × pin_functions を語彙で言い換えたもので、**新しい事実は
    # 足さない**。行が pin_functions に戻せること（route だけは RM 格子の値を採る
    # 行があり、その場合 basis に `!rm-remap-grid(=その値)` があること）、lead が
    # pins にあること、覆えなかった数が増えていないことを見る。
    lead_of = {(r["part_number"], r["pad"], r["pin"]) for r in t["pins"]}
    grid_route = {}
    for r in t["pin_functions"]:
        m = build_index_grid(r["basis"])
        if m:
            grid_route[(r["part_number"], r["pad"], r["signal"], r["route"])] = m
    verbatim = {(r["part_number"], r["pad"], r["route"], r["signal"])
                for r in t["pin_functions"]}
    invented = []
    for r in t["index:pinout"]:
        check("pinout", r["part_number"], r["part_number"], products, "products")
        check("pinout", r["part_number"], r["series"], series, "series")
        if (r["part_number"], r["pad"], r["pin"]) not in lead_of:
            bad.append(f"pinout: {r['part_number']} の lead {r['pin']} pad {r['pad']!r} が pins にない")
        if not r["signal"]:
            continue
        key = (r["part_number"], r["pad"], r["route"], r["signal"])
        if key in verbatim:
            continue
        stated = [k for k in verbatim if k[:2] == key[:2] and k[3] == key[3]]
        if not any(grid_route.get((k[0], k[1], k[3], k[2])) == r["route"] for k in stated):
            invented.append(key)
    if invented:
        bad.append(f"pinout: pin_functions にない行が {len(invented)} 件ある"
                   f"（索引は言い換えるだけで足さない）: {sorted(invented)[:3]}")
    bad += pin_role_coverage(t)
    # 語彙で読めても selector まで辿れない `remap-N` 行が残る。別の数として持つ。
    bad += remap_selector_coverage(t)

    # register_*: EVT header から機械的に集めたレジスタマップ（R-20 の機械収集ぶん）。
    # blocks の型は layouts にあること、registers/fields の (family, 型) も layouts に
    # あること、bits/mask/kind の書式、layout key が (family, 型) で一意であること。
    layouts = {(r["family"], r["type"]): r["layout"] for r in t["index:register_layouts"]}
    if len(layouts) != len(t["index:register_layouts"]):
        bad.append("register_layouts: (family, type) が重複している")
    for r in t["index:register_layouts"]:
        check("register_layouts", r["type"], r["family"], families, "families")
    for r in t["register_blocks"]:
        check("register_blocks", r["block"], r["family"], families, "families")
        # 型の構造体が header に無い block（V407/X315 の `USBHSH`——別 header の型）は
        # layout が空。base address は事実なので行は残す。
        if r["layout"] and (r["family"], r["type"]) not in layouts:
            bad.append(f"register_blocks: {r['family']} {r['block']} の型 {r['type']} が register_layouts にない")
        elif r["layout"] and r["layout"] != layouts[(r["family"], r["type"])]:
            bad.append(f"register_blocks: {r['family']} {r['block']} の layout が register_layouts と違う")
        if not re.fullmatch(r"0x[0-9a-f]{8}", r["base_address"]):
            bad.append(f"register_blocks: {r['family']} {r['block']} の base_address {r['base_address']!r}")
    for r in t["registers"]:
        if (r["family"], r["type"]) not in layouts:
            bad.append(f"registers: {r['family']} {r['type']}.{r['register']} の型が register_layouts にない")
        if not re.fullmatch(r"0x[0-9a-f]+", r["offset"]) or r["width_bits"] not in ("8", "16", "32", "64"):
            bad.append(f"registers: {r['family']} {r['type']}.{r['register']} の offset/width {r['offset']!r}/{r['width_bits']!r}")
    for r in t["register_fields"]:
        check("register_fields", r["register"], r["family"], families, "families")
        if r["kind"] not in ("field", "value"):
            bad.append(f"register_fields: {r['family']} {r['register']}.{r['field']} の kind {r['kind']!r}")
        if r["bits"] and not re.fullmatch(r"\d+(?::\d+)?", r["bits"]):
            bad.append(f"register_fields: {r['family']} {r['register']}.{r['field']} の bits {r['bits']!r}")
        if not re.fullmatch(r"0x[0-9a-f]+", r["mask"]):
            bad.append(f"register_fields: {r['family']} {r['register']}.{r['field']} の mask {r['mask']!r}")
        if r["kind"] == "field" and not r["bits"] and r["mask"] != "0x0":
            # 連続しない mask の field（bits が空）は許すが数は見える形にしておく
            pass
        if r["member"] and (r["family"], r["member"].split(".")[0]) not in layouts:
            bad.append(f"register_fields: {r['family']} {r['register']} の member {r['member']} の"
                       "構造体が register_layouts にない")

    # dma_requests: 格子（dma+channel）か DMAMUX（request_id）のどちらか一方を持つこと。
    # variant は evt_variants の macro（`|` 区切り）にあること。remap の値。
    macros = {r["macro"] for r in t["evt_variants"]} if t.get("evt_variants") else set()
    for r in t["dma_requests"]:
        check("dma_requests", r["request"], r["family"], families, "families")
        has_channel = bool(r["dma"]) and r["channel"].isdigit()
        has_mux = r["request_id"].isdigit()
        if has_channel == has_mux:
            bad.append(f"dma_requests: {r['family']} {r['request']} は dma+channel か request_id の"
                       f"どちらか一方を持つこと（dma={r['dma']!r} channel={r['channel']!r} "
                       f"request_id={r['request_id']!r}）")
        if not r["request"]:
            bad.append(f"dma_requests: {r['family']} の request が空")
        for macro in filter(None, r["variant"].split("|")):
            if macros and macro not in macros:
                bad.append(f"dma_requests: {r['family']} の variant {macro!r} が evt_variants にない")

    # debug_data は family ごと1行。data1 は data0 の次の word、番地は DM の 0xE0000000 台。
    # 番地が空なのは missing の行だけ（H417: EVT に define が無く、V5/V3 のマニュアルは固定しない）。
    for r in t["debug_data"]:
        check("debug_data", r["family"], r["family"], families, "families")
        if r["confidence"] == "missing":
            if r["dm_data0_addr"] or r["dm_data1_addr"]:
                bad.append(f"debug_data: {r['family']} は missing なのに番地がある")
            continue
        for column in ("dm_data0_addr", "dm_data1_addr"):
            if not re.fullmatch(r"0xE000[0-9A-F]{4}", r[column]):
                bad.append(f"debug_data: {r['family']} の {column} {r[column]!r}")
        if (r["dm_data0_addr"] and r["dm_data1_addr"]
                and int(r["dm_data1_addr"], 16) != int(r["dm_data0_addr"], 16) + 4):
            bad.append(f"debug_data: {r['family']} の data1 が data0+4 でない")

    # flash_geometry は family ごと1行。参照と、幾何の常識的な不変量
    # （fast page は標準 page より小さい・2の冪）を見る。
    for r in t["flash_geometry"]:
        check("flash_geometry", r["family"], r["family"], families, "families")
        for column in ("page_erase_bytes", "fast_erase_bytes",
                       "fast_program_bytes", "block_erase_bytes"):
            value = r[column]
            if value and (not value.isdigit() or int(value) & (int(value) - 1)):
                bad.append(f"flash_geometry: {r['family']} の {column}={value!r} が"
                           "2の冪でない")
        if (r["page_erase_bytes"] and r["fast_erase_bytes"]
                and int(r["fast_erase_bytes"]) >= int(r["page_erase_bytes"])):
            bad.append(f"flash_geometry: {r['family']} の fast_erase が標準 page 以上")

    # opa_cmp_registers は EVT header の構造体＋bit define。address が memory_map の
    # block base と整合すること（base + offset）、mask と bits が同じことを言う
    # ことを見る。
    block_base = {(r["family"], r["region"]): int(r["base_address"], 16)
                  for r in t["memory_map"] if r["kind"] == "peripheral"}
    for r in t["opa_cmp_registers"]:
        check("opa_cmp_registers", r["field"], r["family"], families, "families")
        base = block_base.get((r["family"], r["block"]))
        if base is not None and r["address"]:
            if int(r["address"], 16) != base + int(r["offset"], 16):
                bad.append(f"opa_cmp_registers: {r['family']} {r['block']}.{r['register']} の "
                           f"address {r['address']} が memory_map の base+offset と合わない")
        mask = int(r["mask"], 16)
        if r["bits"]:
            hi, _, lo = r["bits"].partition(":")
            lo = lo or hi
            expected = ((1 << (int(hi) + 1)) - 1) ^ ((1 << int(lo)) - 1)
            if expected != mask:
                bad.append(f"opa_cmp_registers: {r['family']} {r['register']}.{r['field']} の "
                           f"bits {r['bits']} と mask {r['mask']} が合わない")

    # clock_enables: family と、RCC の base + offset が memory_map と整合すること。
    rcc_base = {r["family"]: int(r["base_address"], 16) for r in t["memory_map"]
                if r["kind"] == "peripheral" and r["region"] == "RCC"}
    for r in t["clock_enables"]:
        check("clock_enables", r["macro"], r["family"], families, "families")
        base = rcc_base.get(r["family"])
        if base is not None and r["address"] and int(r["address"], 16) != base + int(r["offset"], 16):
            bad.append(f"clock_enables: {r['family']} {r['register']} の address が "
                       "memory_map の RCC base+offset と合わない")
    # adc_internal: family と、チャネル番号が数であること。
    for r in t["adc_internal"]:
        check("adc_internal", r["source"], r["family"], families, "families")
        if r["channel"] and not r["channel"].isdigit():
            bad.append(f"adc_internal: {r['family']} {r['source']} の channel が数でない")
    # usbpd_plumbing: clock_enables の USBPD 行と一致すること。
    enable_bits = {(r["family"], r["peripheral"]): (r["register"], r["bit"])
                   for r in t["clock_enables"]}
    for r in t["usbpd_plumbing"]:
        check("usbpd_plumbing", r["peripheral"], r["family"], families, "families")
        if enable_bits.get((r["family"], r["peripheral"])) != (r["rcc_register"], r["rcc_bit"]):
            bad.append(f"usbpd_plumbing: {r['family']} {r['peripheral']} の RCC が "
                       "clock_enables と合わない")

    # timers.csv は RM の register 見出しから読む。**周辺として実在すること**と、
    # 更新割り込みが interrupts.csv にあることを見る。
    irq_names = {(r["family"], r["name"]) for r in t["interrupts"]}
    variant_macros = {(r["family"], r["macro"]) for r in t["evt_variants"]}
    for r in t["timers"]:
        check("timers", r["timer"], r["family"], families, "families")
        if r["update_vector"] and (r["family"], r["update_vector"]) not in irq_names:
            bad.append(f"timers: {r['family']} の {r['timer']} が指す割り込み "
                       f"{r['update_vector']!r} が interrupts にない")
        for macro in (m for m in r["condition"].split(";") if m):
            if (r["family"], macro) not in variant_macros:
                bad.append(f"timers: {r['family']} の condition が呼ぶ {macro} が "
                           "evt_variants にない")
    # The two remap tables have to agree with each other as well as join, because
    # the ways they can disagree are the ways a consumer writes the wrong register
    # and gets a different route with no error at all.
    remap_fields = {(r["series"], r["selector"]) for r in t["remap_fields"]}
    field_by_key: dict[tuple[str, str], dict] = {}
    for r in t["remap_fields"]:
        check("remap_fields", r["selector"], r["series"], series, "series")
        where = f"{r['series']} {r['selector']}"
        field_by_key[(r["series"], r["selector"])] = r

        bits = [b for b in r["bits"].split(";") if b]
        if not bits:
            bad.append(f"remap_fields: {where} に bits がない")
            continue
        if any(not re.fullmatch(r"[A-Z][A-Z0-9]*:(?:[0-9]|[12][0-9]|3[01])", b) for b in bits):
            bad.append(f"remap_fields: {where} の bits が register:bit 形式でない: {r['bits']}")
            continue
        if len(set(bits)) != len(bits):
            bad.append(f"remap_fields: {where} の bits に重複がある: {r['bits']}")
        named = list(dict.fromkeys(b.split(":")[0] for b in bits))
        if r["register"] != "|".join(named):
            bad.append(
                f"remap_fields: {where} の register {r['register']!r} が bits の register と一致しない"
            )

        values = [int(v) for v in r["valid_values"].split(";") if v != ""]
        if not values:
            bad.append(f"remap_fields: {where} に valid_values がない")
            continue
        # A value wider than the field cannot be written. Where this fired it was
        # never a bad value: it was a field whose upper bits live in a second
        # register that the row failed to name.
        limit = 1 << len(bits)
        outside = [v for v in values if v >= limit]
        if outside:
            bad.append(
                f"remap_fields: {where} の valid_values {outside} が bits {len(bits)}bit に収まらない"
            )
        if r["reset_value"] and int(r["reset_value"]) not in values:
            bad.append(f"remap_fields: {where} の reset_value が valid_values にない")

    for r in t["remap_routes"]:
        where = f"{r['series']} {r['selector']} 値{r['value']}"
        field = field_by_key.get((r["series"], r["selector"]))
        if field is None:
            bad.append(f"remap_routes: ({r['series']}, {r['selector']}) が remap_fields にない")
            continue
        values = {int(v) for v in field["valid_values"].split(";") if v != ""}
        if int(r["value"]) not in values:
            bad.append(f"remap_routes: {where} が remap_fields の valid_values にない")

    # A route must sit on the selector its own peripheral owns. The ways it can
    # end up elsewhere are silent: a manual's grid split across two pages reads
    # as one table and puts TIM4's routes under TIM3_RM, and matching a route on
    # (pad, value) picks whichever peripheral sharing the pad the manual happened
    # to describe. Both produce a row a consumer would write the wrong register
    # for. Only refutable cases are reported -- either the peripheral has a
    # selector of its own in this series, or it differs from the selector's
    # peripheral in the instance number alone -- which is what leaves the
    # genuinely shared fields alone: CH32V407's I2S3_WS really is routed by
    # SPI3_REMAP, and nothing on that silicon is named I2S3.
    owners: dict[str, set[str]] = {}
    for r in t["remap_fields"]:
        key = signal_vocabulary.canonical_field(r["field"])
        owners.setdefault(r["series"], set()).add(key.split("_")[0])
    def same_name_other_instance(a: str, b: str) -> bool:
        # The same rule build_candidate refutes an answer with, read from the
        # one module that owns how a peripheral name is spelled.
        ma, mb = (signal_vocabulary.INSTANCE.match(a),
                  signal_vocabulary.INSTANCE.match(b))
        return bool(ma and mb and ma.group(1) == mb.group(1)
                    and ma.group(2) != mb.group(2))

    for r in t["index:routes"]:
        peripheral = r.get("peripheral")
        field = field_by_key.get((r["series"], r["selector"]))
        # An empty pair means the vocabulary has no rule for that spelling, which
        # is a recorded gap. One half filled is a bug in the rule.
        if bool(r.get("peripheral")) != bool(r.get("role")):
            bad.append(f"routes: {r['series']} {r['selector']} 値{r['value']} の peripheral と role が片方だけ埋まっている")
        if not peripheral or field is None:
            continue
        key = signal_vocabulary.canonical_field(field["field"])
        if key == peripheral or key.split("_")[0] == peripheral:
            continue
        if (peripheral in owners.get(r["series"], set())
                or same_name_other_instance(key, peripheral)):
            bad.append(f"routes: {r['series']} {r['selector']} 値{r['value']} の "
                       f"{r['signal']} ({r['pad']}) は {peripheral} の信号なので "
                       f"{key} の selector には載らない")

    bad += index_checks(t)

    # The clock tables come from EVT's system_ch32*.c, one row per configuration
    # and #if branch. What can be checked without EVT is that they join, that a
    # divider a configuration selects is one the family actually encodes, and
    # that the frequencies parse.
    prescalers = {(r["family"], r["field"], r["divider"]) for r in t["clock_prescalers"]}
    for r in t["clock_prescalers"]:
        check("clock_prescalers", r["field"], r["family"], families, "families")
        if not r["divider"].isdigit() or int(r["divider"]) < 1:
            bad.append(f"clock_prescalers: {r['family']} {r['field']} の divider "
                       f"{r['divider']!r} が分周比でない")
    for r in t["clock_sources"]:
        check("clock_sources", r["consumer"], r["family"], families, "families")
        if not r["value"].isdigit() or not r["shift"].isdigit():
            bad.append(f"clock_sources: {r['family']} {r['consumer']} の value/shift が数でない")
    for r in t["clock_configs"]:
        where = f"{r['family']} {r['config']}"
        check("clock_configs", r["config"], r["family"], families, "families")
        for column, field in (("hpre", "HPRE"), ("ppre1", "PPRE1"), ("ppre2", "PPRE2")):
            divider = r[column]
            if divider and (r["family"], field, divider) not in prescalers:
                bad.append(f"clock_configs: {where} の {column}={divider} が "
                           f"clock_prescalers に無い")
        for domain in (d for d in r["domains"].split(";") if d):
            name, _, hz = domain.partition("=")
            if not name or not hz.isdigit():
                bad.append(f"clock_configs: {where} の domains {domain!r} が "
                           "名前=Hz の形でない")
        if r["flash_latency"] and not r["flash_latency"].isdigit():
            bad.append(f"clock_configs: {where} の flash_latency が数でない")
        # A flash clock divider, not a wait count. Keeping it out of
        # flash_latency is the whole point, so it has to look like a divider.
        div = r["flash_sck_div"]
        if div and not (div.isdigit() and int(div) >= 1
                        and int(div) & (int(div) - 1) == 0):
            bad.append(f"clock_configs: {where} の flash_sck_div {div!r} が"
                       "2のべき乗の分周比でない")
        if div and r["flash_latency"]:
            bad.append(f"clock_configs: {where} が flash_latency と flash_sck_div の"
                       "両方を持つ（単位が違うので同時には書けない）")

    # A `pll` or `outside_rcc` cell names symbols. Without clock_symbols the
    # name is all there is, and the name does not give the number away:
    # CH32V307's RCC_PLLMULL18 is 0x003C0000 and RCC_PLLMULL18_EXTEN is 0.
    address = re.compile(r"^0x[0-9a-f]{8}$")
    symbols = {(r["family"], r["symbol"]) for r in t["clock_symbols"]}
    # A prescaler symbol is in two tables, keyed differently: clock_prescalers
    # enumerates the header's whole divider table, clock_symbols records what a
    # configuration wrote. Where they overlap they have to say the same number,
    # which is a real cross-check because the two are built from different reads.
    prescaler_value = {(r["family"], r["field"], r["divider"]): r["value"]
                       for r in t["clock_prescalers"]}
    prescaler_symbol = re.compile(r"^RCC_(?P<field>[A-Za-z0-9]+?)_[Dd]iv(?P<divider>\d+)$")
    for r in t["clock_symbols"]:
        check("clock_symbols", r["symbol"], r["family"], families, "families")
        if r["role"] not in ("value", "mask", "poll"):
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の role "
                       f"{r['role']!r} が value/mask/poll でない")
        if not r["value"].isdigit():
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の value が数でない")
        if r["address"] and not address.match(r["address"]):
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の address "
                       f"{r['address']!r} が 0x のあと8桁でない")
        if "->" not in r["register"]:
            bad.append(f"clock_symbols: {r['family']} {r['symbol']} の register "
                       f"{r['register']!r} が BLOCK->REGISTER の形でない")
        m = prescaler_symbol.match(r["symbol"])
        if m:
            key = (r["family"], m.group("field").upper(), m.group("divider"))
            other = prescaler_value.get(key)
            if other is not None and other != r["value"]:
                bad.append(f"clock_symbols: {r['family']} {r['symbol']} の value "
                           f"{r['value']} が clock_prescalers の {other} と違う")
    for r in t["clock_configs"]:
        for cell in (r["pll"], r["outside_rcc"]):
            for entry in (e for e in cell.split(";") if e):
                symbol = entry.split(" ")[-1]
                if (r["family"], symbol) not in symbols:
                    bad.append(f"clock_configs: {r['family']} {r['config']} が呼ぶ "
                               f"{symbol} が clock_symbols にない")

    # SystemInit's steps. The order is the fact here, so it has to be a dense
    # run per (family, function) -- a gap means a line the reader dropped.
    init_steps: dict[tuple[str, str], list[int]] = {}
    for r in t["clock_init"]:
        check("clock_init", r["function"], r["family"], families, "families")
        if r["action"] not in ("set", "clear", "write", "poll", "trim"):
            bad.append(f"clock_init: {r['family']} {r['function']} の action "
                       f"{r['action']!r} が set/clear/write/poll/trim でない")
        if not r["value"].isdigit() or not r["step"].isdigit():
            bad.append(f"clock_init: {r['family']} {r['function']} の value/step が数でない")
            continue
        if r["register"] and "->" not in r["register"]:
            bad.append(f"clock_init: {r['family']} {r['function']} の register "
                       f"{r['register']!r} が BLOCK->REGISTER の形でない")
        if r["address"] and not address.match(r["address"]):
            bad.append(f"clock_init: {r['family']} {r['function']} の address "
                       f"{r['address']!r} が 0x のあと8桁でない")
        # Only a trim reads from somewhere; a register step's address is the
        # register itself and naming a source as well would be two answers.
        if bool(r["source"]) and r["action"] != "trim":
            bad.append(f"clock_init: {r['family']} {r['function']} の "
                       f"{r['action']} が source を持っている")
        init_steps.setdefault((r["family"], r["function"]), []).append(int(r["step"]))
        # A poll condition or a trim source that names a symbol is a reference
        # to clock_symbols, and a reference to a row that does not exist leaves
        # the consumer to guess the bit. CH32X315's RCC_HSIRDY was exactly that.
        for symbol in re.findall(r"\b(?:RCC|FLASH|EXTEN)_[A-Za-z0-9_]+", r["condition"]):
            if (r["family"], symbol) not in symbols:
                bad.append(f"clock_init: {r['family']} {r['function']} の condition が呼ぶ "
                           f"{symbol} が clock_symbols にない")
    for (family, function), steps in init_steps.items():
        if sorted(steps) != list(range(min(steps), min(steps) + len(steps))):
            bad.append(f"clock_init: {family} {function} の step が連番でない: "
                       f"{sorted(steps)}")

    # SysTick's layout. The one thing a consumer must not get wrong is where the
    # compare register is, so the offsets have to be a consistent non-overlapping
    # map and the write granularity has to divide the width.
    seen_offsets: dict[tuple[str, str], set[int]] = {}
    for r in t["systick"]:
        check("systick", r["register"], r["family"], families, "families")
        where = f"{r['family']} {r['block']} {r['register']}"
        try:
            at, width, writable = (int(r["offset"], 16), int(r["width_bits"]),
                                   int(r["write_bits"]))
        except ValueError:
            bad.append(f"systick: {where} の offset/width_bits/write_bits が数でない")
            continue
        if width % writable:
            bad.append(f"systick: {where} の write_bits {writable} が "
                       f"width_bits {width} を割り切らない")
        if r["address"] and not address.match(r["address"]):
            bad.append(f"systick: {where} の address {r['address']!r} が "
                       "0x のあと8桁でない")
        if r["address"] and int(r["address"], 16) % 4:
            bad.append(f"systick: {where} の address が4byte境界にない")
        occupied = seen_offsets.setdefault((r["family"], r["block"]), set())
        span = set(range(at, at + width // 8))
        if span & occupied:
            bad.append(f"systick: {where} の offset {at:#x} が同じ block の"
                       "他の register と重なる")
        occupied |= span

    # AF番号の書き込み先。**af-N の行があるのに書き込み先が無いと、経路の情報が
    # そこで行き止まりになる**（F-10/F-12 がまさにそれだった）ので、pin_functions
    # の af-N と (family, pad) で結合できることを見る。pad は "PA0-WKUP" のように
    # 役割つきで書かれることがあるので、頭の P?? だけで突き合わせる。
    pad_head = re.compile(r"^(P[A-H]\d{1,2})")
    alternate = {(r["family"], r["pad"]) for r in t["pin_alternate"]}
    family_of = {r["part_number"]: r["family"] for r in t["products"]}
    seen_bits: dict[tuple[str, str], set[int]] = {}
    for r in t["pin_alternate"]:
        check("pin_alternate", r["pad"], r["family"], families, "families")
        where = f"{r['family']} {r['pad']}"
        if not pad_head.fullmatch(r["pad"]):
            bad.append(f"pin_alternate: {where} の pad が P<port><pin> でない")
        bits = [b for b in r["bits"].split(";") if b]
        if len(bits) != int(r["width_bits"]):
            bad.append(f"pin_alternate: {where} の bits が {len(bits)} 個で "
                       f"width_bits {r['width_bits']} と合わない")
        indices = set()
        for bit in bits:
            register, _, index = bit.partition(":")
            if register != r["register"] or not index.isdigit() or int(index) > 31:
                bad.append(f"pin_alternate: {where} の bits {bit!r} が "
                           f"{r['register']} の 0-31 でない")
            else:
                indices.add(int(index))
        occupied = seen_bits.setdefault((r["family"], r["register"]), set())
        if indices & occupied:
            bad.append(f"pin_alternate: {where} の bit が同じ register の"
                       "他の pad と重なる")
        occupied |= indices
        if not address.match(r["address"]) or int(r["address"], 16) % 4:
            bad.append(f"pin_alternate: {where} の address が 0x8桁の4byte境界でない")
    for r in t["pin_functions"]:
        if not r["route"].startswith("af-"):
            continue
        head = pad_head.match(r["pad"])
        family = family_of.get(r["part_number"])
        if head and family and (family, head.group(1)) not in alternate:
            bad.append(f"pin_functions: {r['part_number']} {r['pad']} の "
                       f"{r['route']} を書く先が pin_alternate にない")

    # FLASH/SRAM の可変な分割。**間違えると linker script が黙って壊れる**ので、
    # ここで見るのは (1) 出荷時の1組が products.csv と一致すること、(2) 符号が
    # 互いに排他であること、(3) フィールド幅が符号を表せること。
    sram_of = {r["part_number"]: r["sram_bytes"] for r in t["products"]}
    flash_of = {r["part_number"]: r["flash_bytes"] for r in t["products"]}
    by_part: dict[str, list[dict]] = {}
    for r in t["memory_configs"]:
        check("memory_configs", r["part_number"], r["part_number"], products, "products")
        by_part.setdefault(r["part_number"], []).append(r)
        if not re.fullmatch(r"[01x]+", r["value"]):
            bad.append(f"memory_configs: {r['part_number']} の value "
                       f"{r['value']!r} が 0/1/x でない")
        for column in ("code_bytes", "sram_bytes"):
            if not r[column].isdigit() or int(r[column]) <= 0:
                bad.append(f"memory_configs: {r['part_number']} の {column} が正の数でない")
    span = re.compile(r"^\[(\d+):(\d+)\]$")
    for part, rows in sorted(by_part.items()):
        # 「既定」と呼べる1組は資料が決めていない（build_memory.py の説明）。
        # 列が言うのは「datasheet の比較表が載せる組」だけで、それは1つ。
        quoted = [r for r in rows if r["datasheet_value"]]
        if len(quoted) != 1:
            bad.append(f"memory_configs: {part} の datasheet_value が "
                       f"{len(quoted)} 行ある（比較表が載せる組は1つ）")
        if len(quoted) == 1:
            if quoted[0]["sram_bytes"] != sram_of.get(part):
                bad.append(f"memory_configs: {part} の datasheet_value の sram_bytes "
                           f"{quoted[0]['sram_bytes']} が products.csv の "
                           f"{sram_of.get(part)} と違う")
            elif quoted[0]["code_bytes"] != flash_of.get(part):
                # ここが合わないのは products.csv が零等待領域ではなく総容量を
                # 取っているとき（worklist の F-14）。linker script が壊れる。
                bad.append(f"memory_configs: {part} の datasheet_value の code_bytes "
                           f"{quoted[0]['code_bytes']} が products.csv の "
                           f"flash_bytes {flash_of.get(part)} と違う")
        # 2つの符号が同じビット並びに当たってはいけない。x は don't care なので
        # 桁ごとに「どちらかが x」なら重なる。
        values = [r["value"] for r in rows]
        for i, one in enumerate(values):
            for other in values[i + 1:]:
                if all(a == b or "x" in (a, b) for a, b in zip(one, other)):
                    bad.append(f"memory_configs: {part} の符号 {one} と {other} が"
                               "同じ値に当たる")
        needed = max(len(v.rstrip("x")) for v in values)
        for column in ("option_byte_bits", "obr_bits"):
            cell = rows[0][column]
            if not cell:
                continue
            found = span.match(cell)
            if not found:
                bad.append(f"memory_configs: {part} の {column} {cell!r} が [hi:lo] でない")
                continue
            hi, lo = int(found.group(1)), int(found.group(2))
            if hi - lo + 1 < needed:
                bad.append(f"memory_configs: {part} の {column} {cell} は "
                           f"{hi - lo + 1}bit だが符号は {needed}bit 要る")

    # 機能の索引。1 series 1 タグで、precision がどちらの読みかを言う。
    seen_tag: set[tuple[str, str]] = set()
    for r in t["index:features"]:
        check("feature_tags", r["tag"], r["family"], families, "families")
        check("feature_tags", r["tag"], r["series"], series, "series")
        if r["precision"] not in ("part", "datasheet"):
            bad.append(f"feature_tags: {r['tag']} の precision "
                       f"{r['precision']!r} が part/datasheet でない")
        if r["parent"] and r["parent"] not in {x["tag"] for x in t["index:features"]}:
            bad.append(f"feature_tags: {r['tag']} の parent {r['parent']} が"
                       "タグとして存在しない")
        key = (r["tag"], r["series"])
        if key in seen_tag:
            bad.append(f"feature_tags: {r['tag']} / {r['series']} が重複")
        seen_tag.add(key)

    # 評価ボード。`parts` は空でもよい（catalogue に無い型番の板が3枚ある）が、
    # 書いてあるなら products.csv に居ること。同じ板が2行あってはいけない。
    seen_board: set[tuple[str, str, str]] = set()
    for r in t["eval_boards"]:
        check("eval_boards", r["path"], r["family"], families, "families")
        check("eval_boards", r["path"], r["parts"], products, "products", ";")
        if r["kind"] not in ("board", "board-variant", "board-manual:en",
                             "board-manual:zh", "schematic-pdf"):
            bad.append(f"eval_boards: {r['path']} の kind {r['kind']!r} が想定外")
        if r["revision"] and not r["revision"].isdigit():
            bad.append(f"eval_boards: {r['board']} の revision "
                       f"{r['revision']!r} が数でない")
        key = (r["family"], r["kind"], r["path"])
        if key in seen_board:
            bad.append(f"eval_boards: {r['family']} の {r['path']} が重複")
        seen_board.add(key)

    # 読んだ原典の版。全 family が揃っていないと、生成物の差分の原因を
    # 「入力が変わった」と「再生成を忘れた」に切り分けられない。
    recorded = {r["family"] for r in t["sources"]}
    for family in families - recorded:
        bad.append(f"sources: {family} の版が記録されていない"
                   "——差分の原因を切り分けられなくなる")
    for r in t["sources"]:
        check("sources", r["family"], r["family"], families, "families")
        if not re.fullmatch(r"[0-9a-f]{40}", r["commit"]):
            bad.append(f"sources: {r['family']} の commit "
                       f"{r['commit']!r} が 40 桁の hash でない")
        if r["dirty"]:
            bad.append(f"sources: {r['family']} の mirror に未コミットの変更が"
                       "あった——commit は読んだ中身を説明しない")

    # アドレス空間の地図。番地は 0x 付きの 32bit、同じ (family, kind, region) は1行。
    span = re.compile(r"^0x[0-9a-f]{8}$")
    seen_region: set[tuple[str, str, str, str]] = set()
    for r in t["memory_map"]:
        check("memory_map", r["region"], r["family"], families, "families")
        if not span.match(r["base_address"]):
            bad.append(f"memory_map: {r['family']} {r['region']} の base_address "
                       f"{r['base_address']!r} が 0x8桁でない")
        key = (r["family"], r["kind"], r["region"], r["condition"])
        if key in seen_region:
            bad.append(f"memory_map: {r['family']} の {r['kind']}/{r['region']} が重複")
        seen_region.add(key)

    # 機能の一覧は datasheet が覆う series の事実。節番号は1冊の中でだけ一意なので、
    # (series群, section) で重ならないこと。
    seen_feature: set[tuple[str, str]] = set()
    for r in t["features"]:
        check("features", r["section"], r["family"], families, "families")
        check("features", r["section"], r["series"], series, "series", ";")
        check("features", r["section"], r["datasheet"], documents, "documents")
        if not r["feature"] and not r["feature_zh"]:
            bad.append(f"features: {r['series']} {r['section']} が両言語とも空")
        key = (r["series"], r["section"])
        if key in seen_feature:
            bad.append(f"features: {r['series']} の節 {r['section']} が重複")
        seen_feature.add(key)

    # 割り込みは family ごとに1つの列挙で、番号は variant で入れ替わる。
    # 同じ (family, condition) の中では番号が1つの名前しか指さないこと。
    seen_irq: dict[tuple[str, int, str], str] = {}
    for r in t["interrupts"]:
        check("interrupts", r["name"], r["family"], families, "families")
        if r["kind"] not in ("exception", "irq"):
            bad.append(f"interrupts: {r['family']} {r['name']} の kind "
                       f"{r['kind']!r} が exception/irq でない")
        if not r["number"].isdigit():
            bad.append(f"interrupts: {r['family']} {r['name']} の number が数でない")
            continue
        key = (r["family"], int(r["number"]), r["condition"])
        if key in seen_irq and seen_irq[key] != r["name"]:
            bad.append(f"interrupts: {r['family']} の {r['number']} 番が "
                       f"{seen_irq[key]} と {r['name']} で重なる"
                       f"（condition={r['condition'] or 'なし'}）")
        seen_irq[key] = r["name"]
    # 例外の番号は全部、周辺割り込みの番号より小さい。境目の番号は family で
    # 違う（CH32H417 は 32 番から。IPC と HSEM がプロセッサ側の枠にいる）ので、
    # 番号そのものではなく2群が交ざらないことを見る。
    for family in {r["family"] for r in t["interrupts"]}:
        mine = [r for r in t["interrupts"] if r["family"] == family
                and r["number"].isdigit()]
        highest = [int(r["number"]) for r in mine if r["kind"] == "exception"]
        lowest = [int(r["number"]) for r in mine if r["kind"] == "irq"]
        if highest and lowest and max(highest) >= min(lowest):
            bad.append(f"interrupts: {family} の例外 {max(highest)} 番が "
                       f"周辺割り込みの最小 {min(lowest)} 番以上")

    # A `condition` naming a compile-time variant macro is unresolvable for a
    # part unless evt_variants says which parts set it.
    macros = {(r["family"], r["macro"]) for r in t["evt_variants"]}
    for r in t["evt_variants"]:
        check("evt_variants", r["macro"], r["family"], families, "families")
        check("evt_variants", r["macro"], r["part_number"], products, "products")
    named = re.compile(r"\bCH32[A-Za-z0-9_]+\b")
    for table in ("clock_configs", "clock_sources", "interrupts"):
        for r in t[table]:
            for macro in named.findall(r["condition"]):
                if (r["family"], macro) not in macros:
                    bad.append(f"{table}: {r['family']} の condition が呼ぶ "
                               f"{macro} が evt_variants にない")

    # No Japanese anywhere, and no Chinese outside the columns that quote the
    # source: the tables are published data. Chinese readings live in `*_zh`
    # columns (`label_zh`, `features_zh`); `path` is a file name that exists in
    # Chinese in the EVT tree (`EVT/PUB/CH32V30x评估板说明书.pdf`) and is an
    # identifier, not a displayed value. Everything else -- data columns and the
    # provenance columns right of `#` alike -- is English. A leak means the
    # translation dictionary in curated/translations.json is missing an entry,
    # a curated basis string was written in Japanese, or an extractor let prose
    # fragments through.
    cjk = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
    LITERAL = ("path",)
    for name, rows in t.items():
        if not rows:
            continue
        columns = [c for c in rows[0] if c != "#" and not c.endswith("_zh") and c not in LITERAL]
        for r in rows:
            for column in columns:
                value = r.get(column, "")
                if value and cjk.search(value):
                    bad.append(f"{name}: {column} にCJKが残っている: {value[:40]!r}")

    counts = {name: len(rows) for name, rows in t.items()}
    print("行数:", counts, file=sys.stderr)
    if bad:
        seen: list[str] = []
        for b in bad:
            if b not in seen:
                seen.append(b)
        print(f"結合できない参照 {len(seen)} 種:", file=sys.stderr)
        for b in seen[:40]:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print("全テーブルの参照が結合可能です", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
