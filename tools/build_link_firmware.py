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
「v2.8 and above」と書く）。

**`wchlink.wcfg`の数と申告版の対応は WCH 自身のコードにある**（2026-08-29 に判明）。
MounRiver Studio の `mrs-vscode/out/extension.js` が、更新を促すダイアログで
**実機の申告値と wcfg の数を同じ関数で復号している**:

    "{0} in RISC-V mode, version v{1}\nLocal firmware version is v{2}. Whether to upgrade?"
        w(n)          n = 実機の申告値
        w(y(i,!1))    y() = wchlink.wcfg の数
    function w(e){ let t=Number(12+e).toString(16);
                   return `${parseInt(t.charAt(0),16)}.${parseInt(t.charAt(1),16)}` }

つまり **12を足して16進で書き、上の桁が major・下の桁が minor**。逆に言えば

    wcfg_version = major*16 + minor - 12

`major*10+minor` という読みが合わなかったのは、10進だと思っていたからでした。
これで全5件が矛盾なく解けます（`31`→2.11、`32`→2.12、`34`→2.14、`42`→**3.6**）。

同じ `extension.js` が **LinkE の CH32V305 を `CH32V307Ver` で引く**ことも明示していて
（`"CH32V305Ver"===n&&(n="CH32V307Ver")`）、`WCFG_KEY` の対応づけはこれで裏が取れました。

**実機2台で確かめました**（2026-08-29）。`81 0d 01 01` への応答は

    WCH-Link  (CH549, RVモード)  82 0d 04 02 0c 01 00 → 2.12、型1  = wcfg 32 と一致
    WCH-LinkE (CH32V305)         82 0d 04 02 0c 12 00 → 2.12、型18 = wcfg 42（3.6）より古い

型番号は `minichlink` の分岐（1=CH549 / 18=LinkE）とも `extension.js` の `g()` とも一致。
ArduinoCore-CH32 の `docs/todo.ja.md` が記録する「CH549 のファーム 2.11 → 2.12 で
probe-rs の不具合が解消」も、2.11=31・2.12=32 として同じ式に載ります。

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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402
SOURCE = "https://file.wch.cn/download/file?id=418"
PAGE = "https://www.wch.cn/downloads/wch-linkutility_zip.html"

COLUMNS = ["device", "mcu", "mode", "role", "file", "size", "sha256",
           "wcfg_version", "reported_version", "measured_version", "set_version",
           "#", "confidence", "basis"]


# 実機で読んだ申告版（`tools/read_link_version.py`）。**表に載せる前に、
# wcfg からの復号と突き合わせるためのもの**で、合わない行は conflict にする。
#
# 2026-08-29 実測（3個体）。**LinkE は2個体とも 2.12**——1台目は RV モード、
# 2台目は DAP モードで、しかも WCH-LinkUtility で「最新に更新」した後の値。
# CH549 のようにモードごとに別ファームを持つ device ではない（配布ファームも
# `FIRMWARE_CH32V305.bin` の1本だけ）。
#
#   434A124C5596  CH549     RV   82 0d 04 02 0c 01 00   2.12
#   F90E8F067DFD  LinkE #1  RV   82 0d 04 02 0c 12 00   2.12（古い個体）
#   FC928F068181  LinkE #2  DAP  82 0d 04 02 0c 12 01   2.12  ← 7バイト目が mode
#   FC928F068181  LinkE #2  RV   82 0d 04 02 0c 12 00   2.12  ← 同一個体。版は不変
#   0A388F068F0B  LinkE #3  RV   82 0d 04 02 16 12 00   2.22  ← 最新版で強制更新した個体
#
# **モードを変えても版は変わらない**（同一個体の #2 で両モードを確認）。変わるのは
# PID（8010↔8012）・EP（0x01/0x81↔0x02/0x83）・応答7バイト目だけ。シリアルも不変。
#
# LinkE #3 が決め手。WCH-LinkUtility 3.00（6月付のファームを同梱）で**強制更新**した
# 純正 LinkE が `minor=0x16`=22 を名乗り、ライブラリの式に入れると
# `2*16+22-12 = 42` = `CH32V307Ver`。**LinkE の対応づけは正しかった**——#1/#2 が
# 2.12 だったのは単に古かっただけ。
MEASURED = {
    ("WCH-Link", "RISC-V"): "2.12",   # 434A124C5596
    ("WCH-LinkE", ""): "2.22",        # 0A388F068F0B（最新版で強制更新した個体）
}


# 実機が名乗る版のうち、これまでに観測した major は**すべて 2**。下の decode は
# それを前提にする（`wcfg - 20` を minor と読む）。前提を置く理由は decode 側の
# 曖昧さで、`libmcuupdate.so` の encode は
#
#     major*16 + minor <= 0x2f  →  major*10 + minor      （枝A）
#     それ以外                  →  major*16 + minor - 12 （枝B）
#
# の2通りあり、**major=2 ではどちらも 20+minor に一致する**（枝Aは 20+minor、
# 枝Bは 32+minor-12 = 20+minor）。数だけを見ると 42 は「2.22」とも「3.6」とも
# 読めるが、**実機が 2.22 だと言っている**のでこちらを採る。
BASE_MAJOR = 2


def reported_version(wcfg: str) -> str:
    """`wchlink.wcfg` の数 → その版が実機で名乗る `major.minor`。

    `82 0d 04 <major> <minor> <type> <mode>` の major/minor に戻す。

    **MounRiver Studio の表示関数は当てにしない。** `extension.js` の
    `w(e)` は `12+e` を16進2桁にして上下の桁を major/minor と読むので、
    **minor が16以上だと壊れる**——`CH32V307Ver=42` を「3.6」と表示するが、
    実機は `minor=0x16`=22、つまり **2.22** と名乗る（2026-08-29 実測。
    WCH-LinkUtility 3.00 で強制更新した純正 LinkE）。比較の両辺が同じ関数を
    通るので WCH の UI 上は破綻しないが、**表に載せる値としては使えない**。
    """
    if not wcfg.isdigit():
        return ""
    minor = int(wcfg) - BASE_MAJOR * 10
    return f"{BASE_MAJOR}.{minor}" if minor >= 0 else ""
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
    ap.add_argument("--out", type=Path, default=None, help="override the output directory (tests)")
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
            "wcfg_version": (version := wcfg.get(WCFG_KEY.get((device, mode), ""), "")),
            "reported_version": (decoded := reported_version(version)),
            "measured_version": (seen := MEASURED.get((device, mode), "")),
            "set_version": set_version,
            # **実機と合わない行は conflict。** `wchlink.wcfg` の数を WCH 自身の式で
            # 復号した版と、実機が名乗る版が食い違うことがある。CH32V307Ver=42 は
            # 3.6 と読めるが、WCH-LinkE は WCH-LinkUtility で更新しても RV/DAP
            # どちらのモードでも 2.12 のままだった（2026-08-29 実測）。どちらかに
            # 寄せず両論を残す——`CH32V307Ver` を LinkE に結びつけているのは
            # MounRiver Studio の `"CH32V305Ver"===n&&(n="CH32V307Ver")` で、
            # **その読み替えのほうが実態と合っていない**疑いが濃い。
            "confidence": "conflict" if seen and decoded and seen != decoded else CONFIDENCE,
            "basis": (f"wch({origin})" if not (seen and decoded and seen != decoded)
                      else f"wch({origin})+!device(={seen})"),
        })

    missing = sorted(set(CATALOG) - {r["file"] for r in rows})
    for name in missing:
        notes.append(f"配布物に無い: {name}")

    rows.sort(key=lambda r: (r["device"], r["mode"], r["role"]))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    dest = paths.table("link_firmware", args.out)
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
