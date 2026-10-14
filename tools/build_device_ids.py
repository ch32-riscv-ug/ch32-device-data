#!/usr/bin/env python3
"""chip ID（device_id）の証拠2表を作る（R-28: ch32rv依頼0001）。

1. **`evidence/device_id_addresses.csv`**——familyごとの読み出し番地。一次資料は
   EVTの`DBGMCU_GetCHIPID()`（`*_dbgmcu.c`の即値、または`CHIPID`マクロ→
   device headerの`CHIPID_BASE`）。**全12 familyで取れる**（M030は0x1ffff384で他と違う）。
   `memory_map.csv`にCHIPID行があるfamily（L103/V205）とは`check_tables`が突き合わせる。

2. **`evidence/device_ids.csv`**——型番（package）ごとの32bit値。
   **出所は公式EVTのChipID List（`*_dbgmcu.c`の`DBGMCU_GetCHIPID`の註）だけ**。
   完全一致または末尾の温度グレード1/6/7だけを省いた名前を採る。IDのrevision
   nibble以外のwildcardや、複数IDを持つ曖昧な行は推測しない。
   資料だけの行はreference、curated/device-ids-measured.jsonのmemory/attach
   実測と一致した行だけconfirmed。dont_care_bitsは[7:4]。

   2026-10-14 まで第三者DB ch32-rs/ch32-data の chips YAML も取り込んでいたが、
   外部サイトにデータを依存させないため外した。72行のうち67行はEVTに同じ値があり、
   残り5行は EVT に無いか曖昧（V103C6T6/C8U6 は ch32-data でも `0x00000000`、
   V203F6P6 は EVT が2つのIDを書く）。V004F6P1/U1 はグレード1の照合で EVT から取れる。

実行:
    uv run tools/build_device_ids.py [--out <dir>]
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

ADDRESS_COLUMNS = ["family", "address", "#", "confidence", "basis"]
ID_COLUMNS = ["part_number", "device_id", "id_addr", "dont_care_bits",
              "id_source", "note", "#", "confidence", "basis"]

CHIPID_LITERAL = re.compile(
    r"uint32_t\s+DBGMCU_GetCHIPID\s*\(\s*void\s*\)\s*\{[^}]*?(0x1[Ff]{3}[0-9A-Fa-f]{4})",
    re.DOTALL)
CHIPID_MACRO = re.compile(
    r"uint32_t\s+DBGMCU_GetCHIPID\s*\(\s*void\s*\)\s*\{[^}]*?\bCHIPID\b", re.DOTALL)
CHIPID_BASE = re.compile(r"#define\s+CHIPID_BASE\s+\(\(uint32_t\)(0x[0-9A-Fa-f]+)\)")

# V103のEVTは同じ語を DBGMCU_GetDEVID が下位16bit、DBGMCU_GetREVID が上位16bitとして読む。
V103_NOTE = ("low 16 bits use the STM32-compatible IDCODE format "
             "(EVT ch32v10x_dbgmcu.c reads the same word in DBGMCU_GetDEVID)")

EVT_ID = re.compile(r"\b(CH32[A-Z0-9]+)\s*-\s*(0x[0-9a-fA-FxX]{8})\b")


def evt_ids(family_of: dict[str, str], address_of: dict[str, str]) -> list[dict]:
    """Match exact EVT names, or names omitting only the temperature grade (1/6/7).

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
                    print(f"  Multiple EVT IDs, not listed: {family}/{name}",
                          file=sys.stderr)
                    continue
                digits = raw[2:]
                if any(c in "xX" and i != 6 for i, c in enumerate(digits)):
                    raise SystemExit(f"{source}: unsupported ID wildcard {raw}")
                value = int(re.sub("[xX]", "0", digits), 16) & 0xffffff0f
                matches = [pn for pn, fam in family_of.items() if fam == family and
                           (pn == name or re.fullmatch(re.escape(name) + r"[167]", pn))]
                if not matches:
                    print(f"  EVT name absent from catalog: {family}/{name}", file=sys.stderr)
                for pn in matches:
                    row = {"part_number": pn, "device_id": f"0x{value:08X}",
                           "id_addr": address_of[family], "dont_care_bits": "[7:4]",
                           "id_source": "",
                           "note": V103_NOTE if family == "CH32V103" else "",
                           "confidence": "reference",
                           "basis": f"evt({family}@{commit},{source.relative_to(repo)},"
                                    f"DBGMCU_GetCHIPID:{name}={raw})"}
                    if pn in rows and rows[pn]["device_id"] != row["device_id"]:
                        raise SystemExit(f"{pn}: conflicting EVT IDs")
                    rows[pn] = row
    return sorted(rows.values(), key=lambda r: r["part_number"])


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
        tag = f"device-id:wch-linke({measurement['evidence']})"
        if tag not in row["basis"].split("+"):
            row["basis"] += f"+{tag}"


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    args = ap.parse_args()

    addresses = family_addresses()
    address_of = {r["family"]: r["address"] for r in addresses}

    with paths.table("products").open(newline="", encoding="utf-8") as f:
        family_of = {r["part_number"]: r["family"] for r in csv.DictReader(f)}

    id_rows = evt_ids(family_of, address_of)
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
    print(f"{dest}: {len(id_rows)} 行（EVT + 実測）", file=sys.stderr)
    missing = sorted(set(family_of) - {r["part_number"] for r in id_rows})
    if missing:
        print(f"  IDが資料に無い型番 {len(missing)} 件: {', '.join(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
