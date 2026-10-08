#!/usr/bin/env python3
"""chip ID（device_id）の証拠2表を作る（R-28: ch32rv依頼0001）。

1. **`evidence/device_id_addresses.csv`**——familyごとの読み出し番地。一次資料は
   EVTの`DBGMCU_GetCHIPID()`（`*_dbgmcu.c`の即値、または`CHIPID`マクロ→
   device headerの`CHIPID_BASE`）。**全12 familyで取れる**（ch32-dataの表に無い
   gap 4 family——V205/V407/X315/M030——も埋まる。M030は0x1ffff384で他と違う）。
   `memory_map.csv`にCHIPID行があるfamily（L103/V205）とは`check_tables`が突き合わせる。

2. **`evidence/device_ids.csv`**——型番（package）ごとの32bit値。
   ch32-rs/ch32-dataの取り込みに加え、公式EVTのChipID Listを目録へ照合する。
   完全一致または末尾の温度グレード6/7だけを省いた名前を採る。IDのrevision
   nibble以外のwildcardや、複数IDを持つ曖昧な行は推測しない。
   資料だけの行はreference、curated/device-ids-measured.jsonのmemory/attach
   実測と一致した行だけconfirmed。dont_care_bitsは[7:4]。
   clone不在時は--reuse-ch32-dataで既存の取り込み行と出所を据え置く。

実行:
    uv run tools/build_device_ids.py [--ch32-data <clone>] [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

MIRRORS = paths.MIRRORS
CH32DATA_DEFAULT = MIRRORS / "ch32-data"

ADDRESS_COLUMNS = ["family", "address", "#", "confidence", "basis"]
ID_COLUMNS = ["part_number", "device_id", "id_addr", "dont_care_bits",
              "id_source", "note", "#", "confidence", "basis"]

CHIPID_LITERAL = re.compile(
    r"uint32_t\s+DBGMCU_GetCHIPID\s*\(\s*void\s*\)\s*\{[^}]*?(0x1[Ff]{3}[0-9A-Fa-f]{4})",
    re.DOTALL)
CHIPID_MACRO = re.compile(
    r"uint32_t\s+DBGMCU_GetCHIPID\s*\(\s*void\s*\)\s*\{[^}]*?\bCHIPID\b", re.DOTALL)
CHIPID_BASE = re.compile(r"#define\s+CHIPID_BASE\s+\(\(uint32_t\)(0x[0-9A-Fa-f]+)\)")

# ch32-dataのchips YAML。構造が浅いので依存を増やさずに行で読む。
YAML_NAME = re.compile(r"^\s*-\s*name:\s*(\S+)")
YAML_DEVICE_ID = re.compile(r"^\s*device_id:\s*(0x[0-9A-Fa-f]{8})\b")

V103_NOTE = ("low 16 bits use the STM32-compatible IDCODE format "
             "(per ch32-data docs/device-ids.md)")

EVT_ID = re.compile(r"\b(CH32[A-Z0-9]+)\s*-\s*(0x[0-9a-fA-FxX]{8})\b")


def evt_ids(family_of: dict[str, str], address_of: dict[str, str]) -> list[dict]:
    """Match exact EVT names, or names omitting only the temperature grade.

    Never prefix-match a package variant (e.g. M030 C8U3 versus C8U7).
    Only the revision nibble may be a wildcard in the documented ID.
    """
    rows = {}
    for family in sorted(address_of):
        repo = MIRRORS / family
        commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        for source in sorted(repo.glob("EVT/EXAM/SRC/Peripheral/src/*dbgmcu*.c")):
            text = source.read_text(encoding="utf-8", errors="replace")
            ambiguous = {name for line in text.splitlines()
                         if len(re.findall(r"0x[0-9a-fA-FxX]{8}\b", line)) > 1
                         for name, _ in EVT_ID.findall(line)}
            for name, raw in EVT_ID.findall(text):
                if name in ambiguous:
                    print(f"  Multiple EVT IDs, retained import only: {family}/{name}",
                          file=sys.stderr)
                    continue
                digits = raw[2:]
                if any(c in "xX" and i != 6 for i, c in enumerate(digits)):
                    raise SystemExit(f"{source}: unsupported ID wildcard {raw}")
                value = int(re.sub("[xX]", "0", digits), 16) & 0xffffff0f
                matches = [pn for pn, fam in family_of.items() if fam == family and
                           (pn == name or re.fullmatch(re.escape(name) + r"[67]", pn))]
                if not matches:
                    print(f"  EVT name absent from catalog: {family}/{name}", file=sys.stderr)
                for pn in matches:
                    row = {"part_number": pn, "device_id": f"0x{value:08X}",
                           "id_addr": address_of[family], "dont_care_bits": "[7:4]",
                           "id_source": "", "note": "", "confidence": "reference",
                           "basis": f"evt({family}@{commit},{source.relative_to(repo)},"
                                    f"DBGMCU_GetCHIPID:{name}={raw})"}
                    if pn in rows and rows[pn]["device_id"] != row["device_id"]:
                        raise SystemExit(f"{pn}: conflicting EVT IDs")
                    rows[pn] = row
    return list(rows.values())


def supplement_ids(id_rows: list[dict], additions: list[dict]) -> list[dict]:
    rows = {r["part_number"]: r for r in id_rows}
    result = list(id_rows)
    for row in additions:
        pn = row["part_number"]
        if pn in rows:
            if (int(rows[pn]["device_id"], 16) & 0xffffff0f) != int(row["device_id"], 16):
                raise SystemExit(f"{pn}: ch32-data and EVT IDs disagree")
        else:
            rows[pn] = row
            result.append(row)
    return sorted(result, key=lambda r: r["part_number"])


def confirm_measurements(rows: list[dict]) -> None:
    measured = json.loads((paths.CURATED / "device-ids-measured.json").read_text())
    by_part = {r["part_number"]: r for r in rows}
    for pn, measurement in measured["measured"].items():
        row = by_part[pn]
        expected = int(row["device_id"], 16) & 0xffffff0f
        if (int(measurement["memory_id"], 16) & 0xffffff0f != expected or
                int(measurement["attach_id"], 16) & 0xffffff0f != expected or
                int(measurement["id_addr"], 16) != int(row["id_addr"], 16)):
            raise SystemExit(f"{pn}: measurement disagrees with documented ID/address")
        row["confidence"] = "confirmed"
        row["id_source"] = "memory"
        row["note"] = "AttachChip and memory IDs agree; flash programming not verified"
        row["basis"] += f"+device-id:wch-linke({measurement['evidence']})"


def family_addresses() -> list[dict]:
    rows = []
    for repo in sorted(MIRRORS.glob("CH32*")):
        hits = sorted(repo.glob("EVT/EXAM/SRC/Peripheral/src/*dbgmcu*.c"))
        if not hits:
            continue
        source = hits[0]
        text = source.read_text(encoding="utf-8", errors="replace")
        rel = source.relative_to(repo)
        m = CHIPID_LITERAL.search(text)
        if m:
            rows.append({"family": repo.name, "address": m.group(1).lower(),
                         "basis": f"evt({rel.name})"})
            continue
        if not CHIPID_MACRO.search(text):
            raise SystemExit(f"{source}: DBGMCU_GetCHIPIDの形が読めない")
        headers = sorted(repo.glob("EVT/EXAM/SRC/Peripheral/inc/ch32*.h"))
        for header in headers:
            hm = CHIPID_BASE.search(header.read_text(encoding="utf-8",
                                                     errors="replace"))
            if hm:
                rows.append({"family": repo.name, "address": hm.group(1).lower(),
                             "basis": f"evt({rel.name})+evt({header.name})"})
                break
        else:
            raise SystemExit(f"{repo.name}: CHIPIDマクロのCHIPID_BASEが見つからない")
    if not rows:
        raise SystemExit("EVTのdbgmcu.cが1つも見つからない（mirrorの場所を確認）")
    return rows


def ch32data_ids(root: Path) -> tuple[str, list[dict]]:
    if not (root / "data" / "chips").is_dir():
        raise SystemExit(f"{root}: ch32-dataのcloneではない（data/chipsが無い）")
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    entries = []
    for path in sorted((root / "data" / "chips").glob("*.yaml")):
        name = None
        for line in path.read_text(encoding="utf-8").splitlines():
            nm = YAML_NAME.match(line)
            if nm:
                name = nm.group(1)
            dm = YAML_DEVICE_ID.match(line)
            if dm and name:
                entries.append({"part_number": name, "device_id": dm.group(1),
                                "file": f"data/chips/{path.name}"})
                name = None
    return commit, entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ch32-data", type=Path, default=CH32DATA_DEFAULT, dest="root",
                    help="ch32-rs/ch32-data の clone（値の取り込み元）")
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    ap.add_argument("--reuse-ch32-data", action="store_true",
                    help="既存証拠表のch32-data取り込み行を据え置く（clone不在時）")
    args = ap.parse_args()

    addresses = family_addresses()
    address_of = {r["family"]: r["address"] for r in addresses}

    with paths.table("products").open(newline="", encoding="utf-8") as f:
        family_of = {r["part_number"]: r["family"] for r in csv.DictReader(f)}

    if args.reuse_ch32_data:
        with paths.table("device_ids").open(newline="", encoding="utf-8") as f:
            retained = [r for r in csv.DictReader(f) if r["basis"].startswith("ch32-data(")]
        if not retained:
            raise SystemExit("No imported ch32-data rows to retain")
        commit, entries = "retained", []
    else:
        commit, entries = ch32data_ids(args.root)
    id_rows = []
    dropped = []
    for e in entries:
        family = family_of.get(e["part_number"])
        if family is None:
            dropped.append(e["part_number"])
            continue
        id_rows.append({
            "part_number": e["part_number"],
            "device_id": e["device_id"],
            "id_addr": address_of[family],
            "dont_care_bits": "[7:4]",
            "id_source": "",
            "note": V103_NOTE if family == "CH32V103" else "",
            "confidence": "reference",
            "basis": f"ch32-data({commit},{e['file']})",
        })
    if args.reuse_ch32_data:
        id_rows = retained
    id_rows = supplement_ids(id_rows, evt_ids(family_of, address_of))
    confirm_measurements(id_rows)

    dest = paths.table("device_id_addresses", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ADDRESS_COLUMNS)
        w.writeheader()
        w.writerows({**r, "#": "#", "confidence": "reference"} for r in addresses)
    print(f"{dest}: {len(addresses)} 行（EVTのDBGMCU_GetCHIPIDから）", file=sys.stderr)

    dest = paths.table("device_ids", args.out)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ID_COLUMNS)
        w.writeheader()
        w.writerows({**{c: r.get(c, "") for c in ID_COLUMNS}, "#": "#"}
                    for r in id_rows)
    ch32_dropped = sorted(p for p in dropped if p.startswith("CH32"))
    print(f"{dest}: {len(id_rows)} 行（ch32-data {commit} + EVT + 実測）",
          file=sys.stderr)
    if dropped:
        # CH32系の不一致は目で見る——末尾のグレード桁が違うニアミス
        # （ch32-data CH32V006F8P6 vs 目録 CH32V006F8P7 等）を勝手に対応付けない
        print(f"  目録に無い型番 {len(dropped)} 件（うちCH32系 {len(ch32_dropped)}: "
              f"{', '.join(ch32_dropped)}）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
