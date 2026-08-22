#!/usr/bin/env python3
"""WCH-Link 系デバッガの最新ファームウェア一覧 → tables/link_firmware.csv

「手元のLinkが古いから更新する」の判断材料。WCHが配る`WCH-LinkUtility.ZIP`の
`Firmware_Link/`を読んで、デバイスごとにファイル・サイズ・sha256・WCHの版番号を
出す。**バイナリ自体はこのrepositoryに置かない**（再配布になる）。置くのは
「いま配られているものの指紋」だけで、取得元URLは`basis`が持つ。

同じ一式がMounRiver Studioにも入っている。Linux版MRSの
`.../components/WCH/Others/Firmware_Link/default/`にある10本は
**Windows版ZIPのものとsha256まで完全に一致する**（2026-08-22時点で実測）。
つまりLinuxでも同じファームウェアが手に入り、MRS本体がIAP更新を実行できる。
`--zip`にローカルのZIPかMRSの`Firmware_Link`ディレクトリを渡せばオフラインでも走る。

**版番号の読み方に未解決がある。** この一式には版を名乗るものが3つあり、意味が違う:

    firmware_version.txt   ZIPは v40、MRSは v43。**中身が同一なのに違う**ので、
                           これは配布パッケージの版であってファームウェアの版ではない
    sub_manifest.json      MRSのみ。パッケージ v43 / 既定セット v41
    wchlink.wcfg           デバイスごとの数（CH549Ver_RV=32 等）。**両配布で一致**するので
                           これがファームウェア側の版と考えられる

一方、Linkが**USBで申告する版は`major.minor`**（`81 0d 01 01`への応答のbyte3・4。
`ch32fun/minichlink/pgm-wch-linke.c`が`%d.%d`で表示し、WCH-Link User Manual p.19も
「v2.8 and above」と書く）。`wchlink.wcfg`の32や42がこの`major.minor`のどれに当たるかは
**配布物からは決められなかった**。`CH549Ver_RV=32`は`major*10+minor`と読めば2.12、
`CH549Ver_ARM=31`なら2.11で辻褄が合うが、`CH32V307Ver=42`は同じ読みだと2.22になる。
ファームウェアのバイナリにも応答テンプレート（`82 0d 04 ...`）は入っておらず、
実行時に組み立てている。**実機で読んだ版と突き合わせるまでは`wcfg_version`を
「WCH独自の番号」として載せるに留める。**

実行:
    uv run tools/build_link_firmware.py [--zip <path|dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = "https://file.wch.cn/download/file?id=418"
PAGE = "https://www.wch.cn/downloads/wch-linkutility_zip.html"

COLUMNS = ["device", "mcu", "mode", "role", "file", "size", "sha256",
           "wcfg_version", "set_version", "#", "confidence", "basis"]
# 単一資料（WCHの配布物そのもの）なので全行reference。sha256は事実だが、
# 「これが最新か」はWCHが差し替えれば変わる。
CONFIDENCE = "reference"

# ファイル名 → (デバイス, MCU, モード, 役割)。
#
# MCUは推測ではなくバイナリの先頭命令で判る——8051は`02`(LJMP)、RISC-Vは`6f`(jal)。
# 役割はWCH-Link User Manual第6章の対応で、p.20が①〜⑩として同じ10本を挙げている:
# `*APP_IAP*`がIAPモード経由の更新用、`FIRMWARE_*`がBOOTモード（オフライン）用。
CATALOG = {
    "FIRMWARE_CH549.bin":        ("WCH-Link", "CH549", "RISC-V", "offline"),
    "WCH-Link_APP_IAP_RV.bin":   ("WCH-Link", "CH549", "RISC-V", "iap"),
    "FIRMWARE_DAP_CH549.bin":    ("WCH-Link", "CH549", "ARM", "offline"),
    "WCH-Link_APP_IAP_ARM.bin":  ("WCH-Link", "CH549", "ARM", "iap"),
    "FIRMWARE_CH32V305.bin":     ("WCH-LinkE", "CH32V305", "", "offline"),
    "WCH-LinkE-APP-IAP.bin":     ("WCH-LinkE", "CH32V305", "", "iap"),
    "FIRMWARE_CH32V208.bin":     ("WCH-LinkW", "CH32V208", "", "offline"),
    "WCH-LinkW-APP-IAP.bin":     ("WCH-LinkW", "CH32V208", "", "iap"),
    "FIRMWARE_CH32V203.bin":     ("WCH-DAPLink", "CH32V203", "", "offline"),
    "WCH-DAPLink_APP_IAP.bin":   ("WCH-DAPLink", "CH32V203", "", "iap"),
}
# wchlink.wcfg のキー → どのデバイスの版か。
WCFG_KEY = {
    ("WCH-Link", "RISC-V"): "CH549Ver_RV",
    ("WCH-Link", "ARM"): "CH549Ver_ARM",
    ("WCH-LinkE", ""): "CH32V307Ver",
    ("WCH-LinkW", ""): "CH32V208Ver",
    ("WCH-DAPLink", ""): "CH32V203Ver",
}
# 先頭バイト → 命令セット。MCUの申告が正しいかの検算に使う。
ISA = {0x02: "8051", 0x6f: "RISC-V"}
EXPECT_ISA = {"CH549": "8051", "CH32V305": "RISC-V",
              "CH32V208": "RISC-V", "CH32V203": "RISC-V"}


def read_source(where: str | None) -> tuple[dict[str, bytes], str]:
    """{ファイル名: 中身} と、どこから読んだかの記述。"""
    if where and Path(where).is_dir():
        found = {p.name: p.read_bytes() for p in Path(where).iterdir() if p.is_file()}
        return found, f"local-dir({Path(where).name})"
    if where:
        blob = Path(where).read_bytes()
        origin = f"local-zip({Path(where).name})"
    else:
        with urllib.request.urlopen(SOURCE, timeout=180) as response:
            blob = response.read()
        origin = SOURCE
    found = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            if info.is_dir() or "/Firmware_Link/" not in info.filename:
                continue
            found[Path(info.filename).name] = archive.read(info)
    return found, origin


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--zip", help="ローカルのZIP、または展開済み Firmware_Link ディレクトリ")
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    try:
        blobs, origin = read_source(args.zip)
    except Exception as exc:  # noqa: BLE001
        print(f"取得できない: {exc}", file=sys.stderr)
        return 1
    if not blobs:
        print("Firmware_Link/ が見つからない", file=sys.stderr)
        return 1

    wcfg = {}
    for line in blobs.get("wchlink.wcfg", b"").decode("utf-8", "replace").splitlines():
        m = re.match(r"^\s*(\w+)\s*=\s*(\S+)\s*$", line)
        if m:
            wcfg[m.group(1)] = m.group(2)
    set_version = blobs.get("firmware_version.txt", b"").decode("utf-8", "replace").strip()

    rows: list[dict] = []
    notes: list[str] = []
    for name, blob in sorted(blobs.items()):
        entry = CATALOG.get(name)
        if entry is None:
            if name not in ("wchlink.wcfg", "firmware_version.txt", "sub_manifest.json"):
                notes.append(f"未知のファイル（CATALOG に無い）: {name}")
            continue
        device, mcu, mode, role = entry
        isa = ISA.get(blob[0] if blob else -1, f"不明({blob[:1].hex()})")
        if isa != EXPECT_ISA[mcu]:
            notes.append(f"{name}: 先頭命令が {isa} で {mcu} と噛み合わない")
        rows.append({
            "device": device, "mcu": mcu, "mode": mode, "role": role,
            "file": name, "size": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "wcfg_version": wcfg.get(WCFG_KEY.get((device, mode), ""), ""),
            "set_version": set_version,
            "confidence": CONFIDENCE,
            "basis": f"wch({origin})",
        })

    missing = sorted(set(CATALOG) - {r["file"] for r in rows})
    for name in missing:
        notes.append(f"配布物に無い: {name}")

    rows.sort(key=lambda r: (r["device"], r["mode"], r["role"]))
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / "link_firmware.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    print(f"{dest}: {len(rows)} 行  取得元 {origin}", file=sys.stderr)
    print(f"  配布パッケージ版: {set_version}", file=sys.stderr)
    for (device, mode), key in sorted(WCFG_KEY.items()):
        label = f"{device}{'/' + mode if mode else ''}"
        print(f"  {label:20} wchlink.wcfg {key}={wcfg.get(key, '?')}", file=sys.stderr)
    for note in notes:
        print(f"  - {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
