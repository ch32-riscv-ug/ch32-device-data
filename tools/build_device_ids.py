#!/usr/bin/env python3
"""chip ID（device_id）の証拠2表を作る（R-28: ch32rv依頼0001）。

1. **`evidence/device_id_addresses.csv`**——familyごとの読み出し番地。一次資料は
   EVTの`DBGMCU_GetCHIPID()`（`*_dbgmcu.c`の即値、または`CHIPID`マクロ→
   device headerの`CHIPID_BASE`）。**全12 familyで取れる**（ch32-dataの表に無い
   gap 4 family——V205/V407/X315/M030——も埋まる。M030は0x1ffff384で他と違う）。
   `memory_map.csv`にCHIPID行があるfamily（L103/V205）とは`check_tables`が突き合わせる。

2. **`evidence/device_ids.csv`**——型番（package）ごとの32bit値。値の一次資料は
   実機だが、まずは**ch32-rs/ch32-data（第三者の機械可読DB）の取り込み**を
   confidence=referenceで持つ（basisにcloneのcommitとfile）。実測（WCH-LinkE。
   `device-id:wch-linke`のbasisを想定——`debug_data`の`hartinfo:wch-linke`と同じ
   流儀）が届いた行だけconfirmedへ上がる。ch32rv側は暫定overlayと突き合わせて
   受け入れる（依頼書の受け入れ方法）。

   - `dont_care_bits`は`[7:4]`（silicon revision。ch32-dataのbit割り文書と
     probe-rsの照合mask 0xffffff0f が根拠——どちらも二次資料なのでreferenceの
     一部として持つ）
   - V103のdevice_idは下位16bitがSTM32互換IDCODE形式（`note`列）

実行:
    uv run tools/build_device_ids.py [--ch32-data <clone>] [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
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
    args = ap.parse_args()

    addresses = family_addresses()
    address_of = {r["family"]: r["address"] for r in addresses}

    with paths.table("products").open(newline="", encoding="utf-8") as f:
        family_of = {r["part_number"]: r["family"] for r in csv.DictReader(f)}

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
    id_rows.sort(key=lambda r: r["part_number"])

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
    print(f"{dest}: {len(id_rows)} 行（ch32-data {commit} から取り込み・全行reference）",
          file=sys.stderr)
    if dropped:
        # CH32系の不一致は目で見る——末尾のグレード桁が違うニアミス
        # （ch32-data CH32V006F8P6 vs 目録 CH32V006F8P7 等）を勝手に対応付けない
        print(f"  目録に無い型番 {len(dropped)} 件（うちCH32系 {len(ch32_dropped)}: "
              f"{', '.join(ch32_dropped)}）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
