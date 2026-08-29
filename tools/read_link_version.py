#!/usr/bin/env python3
"""繋がっている WCH-Link がいま載せているファームウェアの版を読む。

`evidence/link_firmware.csv` の `reported_version` は **WCH がいま配っている**版で、
これは **手元の実機がいる**版。2つを並べれば「更新できるか」が分かる（worklist の F-11）。

    uv run tools/read_link_version.py              # 繋がっているものを全部
    uv run tools/read_link_version.py /dev/bus/usb/001/116

デバッガに問い合わせるだけで、**デバッグ対象の MCU には一切触れない**。
`81 0d 01 01` を書いて `82 0d 04 <major> <minor> <type> <mode>` を読む
（`ch32fun/minichlink/pgm-wch-linke.c` と `libmcuupdate.so` が使うのと同じもの）。
RV モードは EP 0x01/0x81、DAP モードは 0x02/0x83 で、**問い合わせも応答も同じ形**。

usbfs の ioctl を直に叩くので pyusb も libusb も要らない。
"""

from __future__ import annotations

import csv
import ctypes
import fcntl
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

# <linux/usbdevice_fs.h>
USBDEVFS_CLAIMINTERFACE = 0x8004550F
USBDEVFS_RELEASEINTERFACE = 0x80045510
USBDEVFS_BULK = 0xC0185502

ENDPOINTS = {"RV": (0x01, 0x81), "DAP": (0x02, 0x83)}
QUERY = bytes([0x81, 0x0D, 0x01, 0x01])
SYSFS = Path("/sys/bus/usb/devices")
# RV モード / ARM(DAP) モード / IAP 中。IAP は更新の途中なので版は聞けない。
PRODUCT_IDS = {"8010": "RV", "8011": "RV", "8012": "DAP"}

# 応答6バイト目の device 型。`minichlink` の分岐とも MounRiver Studio の
# `extension.js` の `g()` とも一致する。値は `link_firmware.csv` の `device` 列。
VARIANT = {1: "WCH-Link", 2: "WCH-LinkE", 3: "WCH-LinkS", 4: "WCH-DAPLink",
           5: "WCH-LinkW", 18: "WCH-LinkE", 133: "WCH-LinkW"}
# 応答7バイト目。CH549 だけが RV/ARM で別ファームを持ち、配布の版番号も分かれる。
MODE = {0: "RISC-V", 1: "ARM"}


class Bulk(ctypes.Structure):
    _fields_ = [("ep", ctypes.c_uint), ("len", ctypes.c_uint),
                ("timeout", ctypes.c_uint), ("data", ctypes.c_void_p)]


def bulk(fd: int, ep: int, payload: bytes | None, size: int = 0,
         timeout: int = 1000) -> bytes:
    buf = ctypes.create_string_buffer(payload if payload is not None else size)
    transfer = Bulk(ep=ep, len=len(payload) if payload is not None else size,
                    timeout=timeout, data=ctypes.cast(buf, ctypes.c_void_p).value)
    n = fcntl.ioctl(fd, USBDEVFS_BULK, transfer)
    return buf.raw[:n]


def ask(node: str, mode: str) -> bytes:
    """1往復。インタフェース0を claim して bulk を投げ、応答を返す。"""
    ep_out, ep_in = ENDPOINTS[mode]
    fd = os.open(node, os.O_RDWR)
    try:
        fcntl.ioctl(fd, USBDEVFS_CLAIMINTERFACE, struct.pack("I", 0))
        try:
            bulk(fd, ep_out, QUERY)
            return bulk(fd, ep_in, None, 64)
        finally:
            fcntl.ioctl(fd, USBDEVFS_RELEASEINTERFACE, struct.pack("I", 0))
    finally:
        os.close(fd)


def read_version(node: str, prefer: str | None = None) -> tuple[bytes, str] | None:
    """(応答, 使えた端点の種類)。どちらの端点でも応答が無ければ None。"""
    order = [prefer] + [m for m in ENDPOINTS if m != prefer] if prefer else list(ENDPOINTS)
    for mode in order:
        try:
            reply = ask(node, mode)
        except OSError:
            continue
        if len(reply) >= 7 and reply[0] == 0x82 and reply[1] == 0x0D:
            return reply, mode
    return None


def connected() -> list[tuple[str, str, str]]:
    """(デバイスノード, シリアル, 端点の種類) を、繋がっている分だけ。"""
    found = []
    for entry in sorted(SYSFS.glob("*")):
        try:
            if (entry / "idVendor").read_text().strip() != "1a86":
                continue
            product = (entry / "idProduct").read_text().strip()
        except OSError:
            continue
        if product not in PRODUCT_IDS:
            continue
        bus = int((entry / "busnum").read_text())
        dev = int((entry / "devnum").read_text())
        serial = (entry / "serial").read_text().strip() if (entry / "serial").exists() else ""
        found.append((f"/dev/bus/usb/{bus:03d}/{dev:03d}", serial, PRODUCT_IDS[product]))
    return found


def distributed() -> dict[tuple[str, str], str]:
    """(device, mode) → WCH がいま配っている版。`link_firmware.csv` から。"""
    out = {}
    with paths.table("link_firmware").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["reported_version"]:
                out[(row["device"], row["mode"])] = row["reported_version"]
    return out


def describe(reply: bytes, latest: dict[tuple[str, str], str]) -> str:
    major, minor, kind, mode = reply[3], reply[4], reply[5], reply[6]
    device = VARIANT.get(kind, f"不明(type {kind})")
    here = f"{major}.{minor}"
    # CH549 だけが RV/ARM で別ファーム。ほかは mode を問わず1つ。
    want = latest.get((device, MODE.get(mode, "")), latest.get((device, ""), ""))
    if not want:
        verdict = "（配布版が分からない）"
    elif want == here:
        verdict = "最新"
    else:
        verdict = f"**更新できる → {want}**"
    return (f"{device} / {MODE.get(mode, f'mode {mode}')}  "
            f"firmware {here}   配布版 {want or '—'}  {verdict}")


def main() -> int:
    latest = distributed()
    targets = [(n, "", None) for n in sys.argv[1:]] or connected()
    if not targets:
        print("WCH-Link が見つからない（1a86:8010 / 8011 / 8012）", file=sys.stderr)
        return 1
    bad = 0
    for node, serial, prefer in targets:
        got = read_version(node, prefer)
        if got is None:
            print(f"{node}{f' [{serial}]' if serial else ''}: 応答なし"
                  "（IAP モード中か、権限が無いか）", file=sys.stderr)
            bad = 1
            continue
        reply, _ = got
        print(f"{node}{f' [{serial}]' if serial else ''}: {reply.hex(' ')}")
        print(f"    {describe(reply, latest)}")
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
