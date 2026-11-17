#!/usr/bin/env python3
"""EXTI の線（番号 → 起こす元 → 割り込みのベクタ）→ index/exti_lines.csv

EXTI の線は GPIO の端子（`EXTI0`〜`EXTI15` を AFIO_EXTICRx で port に振る）のほかに、
PVD・RTC アラーム・USB の起床・ETH・LPTIM などの内部の事象を受ける。どの線が何かは family で
違う（V003 は PVD が線8、H417 は線16 が USBHS の起床）。consumer（ch32rv のコア）は RM と EVT から
手で書いていた（2026-11-17 の依頼）。

**出所は2つ。**

    RM の表「EXTI中断映射」/「EXTI interrupt mapping」  `EXTI16 | PVD事件：超出电压监控阈值`
    EVT の `*_exti.h`  `#define EXTI_Line16 ((uint32_t)0x10000) /* … Connected to the PVD Output */`

起こす元は `PVD`・`RTC_ALARM`・`AWU`（自動起床）・`<周辺>_WAKEUP`・`GPIO`（端子の線）・
端子名（X035 の `PC18`。SDI が有効なとき）に揃える。RM と EVT が同じ元を言えば confirmed、
片方だけなら reference、違えば conflict。**食い違うときはその family に割り込みのベクタがある
ほうを採る**（V205 の線21 は RM が LPTIM、EVT が USBHS——V205 に LPTIM は無く、ベクタは USBHS の
起床にしか無い）。どちらにもあれば RM を採る。異論は basis に `!evt(...)(source=…)` /
`!rm(...)(source=…)` で残す。

`vector`・`irq` は `index/interrupts.csv` の名前と番号。GPIO の線は `EXTIn` か、まとめた
`EXTI9_5`・`EXTI15_10`・`EXTI7_0` に当てる。内部の元は名前を揃えて当てる（`USBHS1_WAKEUP` →
`USBHS1Wakeup`、`ETH_WAKEUP` → `ETH_WKUP`）。当たらなければ空——線は事象（イベント）としてだけ
使う元もある。

実行:
    uv run pipeline/extract/rm/extract_exti_lines.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MIRRORS = REPO.parent
sys.path.insert(0, str(REPO / "pipeline" / "common"))
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402
import paths  # noqa: E402

COLUMNS = ["family", "line", "source", "vector", "irq", "evt_define", "confidence", "basis"]
LINE_DEFINE = re.compile(r"^\s*#define\s+(?P<name>EXTI_Line(?P<n>\d+))\s+\(\s*\(\s*uint32_t\s*\)\s*"
                         r"0x[0-9A-Fa-f]+\s*\)\s*(?:/\*\s*(?P<comment>.*?)\s*\*/)?")
RANGE = re.compile(r"EXTI\s*(\d+)\s*[～~\-–—至]+\s*EXTI\s*(\d+)")
SINGLE = re.compile(r"^EXTI\s*(\d+)$")


def source_of(text: str) -> str:
    """RM（zh・en）と EVT のコメントの言い方を1つの名前に揃える。読めなければ空。

    >>> [source_of(t) for t in ("PVD事件：超出电压监控阈值", "RTC闹钟事件", "USBHS1唤醒事件",
    ...                         "自动唤醒事件。", "Connected to the PVD Output",
    ...                         "Connected to the the USB PD Wake-up event",
    ...                         "Connected to the Ethernet Wakeup event", "Connected to the PC19(SDI on)",
    ...                         "Connected to the PWR Auto Wake-up event", "USBHS1 wakeup event",
    ...                         "RTC alarm event", "Connected to the AWU", "ETH唤醒事件")]
    ['PVD', 'RTC_ALARM', 'USBHS1_WAKEUP', 'AWU', 'PVD', 'USBPD_WAKEUP', 'ETH_WAKEUP', 'PC19', 'AWU', 'USBHS1_WAKEUP', 'RTC_ALARM', 'AWU', 'ETH_WAKEUP']
    """
    t = re.sub(r"^.*?Connected to (?:the )+", "", text.strip())
    if re.search(r"PVD", t):
        return "PVD"
    if re.search(r"RTC\s*(?:闹钟|alarm)", t, re.IGNORECASE):
        return "RTC_ALARM"
    if re.search(r"自动唤醒|Auto(?:matic)?[- ]?wake|^AWU\b", t, re.IGNORECASE):
        return "AWU"
    # 内部 32K の校準（V20x/V30x の線21。en「Internal 32K calibration wakeup」、EVT「OSCCAL」）。
    if re.search(r"校准|calibration|OSCCAL", t, re.IGNORECASE):
        return "OSCCAL_WAKEUP"
    m = re.match(r"(P[A-F]\d+)\b", t)
    if m:
        return m.group(1)
    m = re.match(r"([A-Za-z][A-Za-z0-9 ]*?)\s*(?:唤醒事件|wake[- ]?up event)", t, re.IGNORECASE)
    if m:
        name = re.sub(r"\s+", "", m.group(1)).upper()
        name = {"ETHERNET": "ETH"}.get(name, name)
        return f"{name}_WAKEUP"
    return ""


def norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper()).replace("WKUP", "WAKEUP")


def rm_lines(family: str) -> dict[str, dict[int, str]]:
    """lang → {線: 元}。表題に EXTI と「映射」/「map」を含む表から。"""
    out: dict[str, dict[int, str]] = {}
    for lang, (bundle, _document) in bundle_pages.rm_bundles(family).items():
        found: dict[int, str] = {}
        for page in bundle_pages.pages(bundle.name):
            for caption, rows in bundle_pages.captioned_tables(page):
                if "EXTI" not in caption or not re.search(r"映射|mapping|map", caption, re.IGNORECASE):
                    continue
                for row in rows[1:]:
                    if len(row) < 2 or not row[0]:
                        continue
                    head = re.sub(r"\s+", "", row[0])
                    desc = (row[1] or "").replace("\n", "")
                    span = RANGE.search(head)
                    if span:
                        lo, hi = sorted((int(span.group(1)), int(span.group(2))))
                        for n in range(lo, hi + 1):
                            found.setdefault(n, "GPIO")
                        continue
                    one = SINGLE.match(head)
                    if one:
                        found.setdefault(int(one.group(1)), source_of(desc) if desc.strip() else "")
        if found:
            out[lang] = found
    return out


def evt_lines(family: str, gpio: set[int]) -> tuple[dict[int, tuple[str, str]], str]:
    """{線: (define, 元)} と header の名前。

    コメントの無い線は、RM が端子の線と言う範囲（`gpio`。RM が無ければ 0〜15）なら `GPIO`、
    そうでなければ元を言っていない（空）——V103/V20x/V307 の `EXTI_Line18` はコメントが無い。
    """
    headers = sorted((MIRRORS / family / "EVT/EXAM/SRC/Peripheral/inc").glob("*_exti.h"))
    if not headers:
        return {}, ""
    found = {}
    for line in headers[0].read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE_DEFINE.match(line)
        if not m:
            continue
        comment = m.group("comment") or ""
        n = int(m.group("n"))
        source = (source_of(comment) if "Connected" in comment
                  else "GPIO" if n in (gpio or set(range(16))) else "")
        found[n] = (m.group("name"), source)
    return found, headers[0].name


def vectors(family: str, interrupts: list[dict]) -> tuple[dict[str, tuple[str, str]], list]:
    """揃えた名前 → (ベクタ名, 番号) と、`EXTIa_b` のまとめたベクタ。"""
    named, ranges = {}, []
    for r in interrupts:
        if r["family"] != family or r["kind"] != "irq":
            continue
        named.setdefault(norm(r["name"]), (r["name"], r["number"]))
        m = re.fullmatch(r"EXTI(\d+)_(\d+)", r["name"])
        if m:
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            ranges.append((lo, hi, r["name"], r["number"]))
    return named, ranges


def vector_for(line: int, source: str, named: dict, ranges: list) -> tuple[str, str]:
    if source == "GPIO" or re.fullmatch(r"P[A-F]\d+", source or ""):
        if norm(f"EXTI{line}") in named:
            return named[norm(f"EXTI{line}")]
        for lo, hi, name, number in ranges:
            if lo <= line <= hi:
                return name, number
        return "", ""
    if not source:
        return "", ""
    for name in (source, *ALIASES.get(source, ())):
        if norm(name) in named:
            return named[norm(name)]
    return "", ""


# 元の名前とベクタの名前の綴りが違うもの（資料はそれぞれの綴りのまま、当てるときだけ読み替える）。
ALIASES = {
    "USBD_WAKEUP": ("USBWakeUp",),          # V103: RM「USBD唤醒」、ベクタ USBWakeUp
    "COMP_WAKEUP": ("CMPWakeUp",),          # L103/V205
    "USBFSOTG_WAKEUP": ("USBFSWakeUp",),    # H417
    "OSCCAL_WAKEUP": ("OSCWakeUp",),        # V20x
    "USB_WAKEUP": ("USBFSWakeUp", "USBWakeUp"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先のディレクトリ（試験用）")
    args = ap.parse_args()

    with paths.index("interrupts").open(newline="", encoding="utf-8") as f:
        interrupts = list(csv.DictReader(f))
    families = sorted({r["family"] for r in interrupts})
    rows = []
    for family in families:
        rm = rm_lines(family)
        gpio = {n for found in rm.values() for n, source in found.items() if source == "GPIO"}
        evt, header = evt_lines(family, gpio)
        named, ranges = vectors(family, interrupts)
        documents = {lang: bundle.name.rsplit(".", 1)[0]
                     for lang, (bundle, _) in bundle_pages.rm_bundles(family).items()}
        for line in sorted(set(evt) | {n for found in rm.values() for n in found}):
            rm_said = {lang: found[line] for lang, found in rm.items() if found.get(line)}
            evt_said = evt.get(line, ("", ""))[1]
            claims = collections.OrderedDict()   # 元 → 言った出所
            for lang, source in sorted(rm_said.items(), key=lambda kv: kv[0] != "zh"):
                claims.setdefault(source, []).append(f"rm({documents[lang]}:{lang})")
            if evt_said:
                claims.setdefault(evt_said, []).append(f"evt({header})")
            if not claims:
                continue
            candidates = list(claims)
            if len(candidates) == 1:
                kept = candidates[0]
            else:
                with_vector = [c for c in candidates if vector_for(line, c, named, ranges)[0]]
                kept = with_vector[0] if len(with_vector) == 1 else candidates[0]
            vector, irq = vector_for(line, kept, named, ranges)
            basis = "+".join(claims[kept])
            for other in candidates:
                if other != kept:
                    for who in claims[other]:
                        basis += f"+!{who}(source={other})"
            confidence = ("conflict" if len(candidates) > 1
                          else "confirmed" if len(claims[kept]) >= 2 else "reference")
            rows.append({"family": family, "line": line, "source": kept, "vector": vector,
                         "irq": irq, "evt_define": evt.get(line, ("", ""))[0],
                         "confidence": confidence, "basis": basis})
    dest = paths.table("exti_lines", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    shown = dest.relative_to(REPO) if dest.is_relative_to(REPO) else dest
    print(f"{shown}: {len(rows)} 行", dict(collections.Counter(r["confidence"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
