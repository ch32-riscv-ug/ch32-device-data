#!/usr/bin/env python3
"""Read the AFIO remap field definitions by running EVT's own decoder.

Every other extractor here reads a document. This one reads *behaviour*. Each
family's ``GPIO_PinRemapConfig()`` knows exactly which register bits a named
remap constant touches, and the twelve families ship twelve unrelated
implementations, so re-deriving that from the constants by hand is twelve
chances to get it wrong. Instead the vendor function is compiled for the host
against a two-word stub of AFIO and watched:

    set   = the registers after calling with ENABLE from an all-zero state
    clear = the bits the DISABLE path forces to zero from an all-ones state

``clear`` is the field. ``set`` read over that field, least-significant bit
first, is the value the constant selects. Nothing is transcribed, so nothing can
be mistranscribed.

What this adds over tools/extract_selectors.py, which reads the same fields out
of the device header's ``AFIO_PCFR*`` defines: the header enumerates *bits*, and
only sometimes enumerates *values*. The gpio header names one constant per real
route, so this is the only mechanical source for which encodings the silicon
actually accepts -- CH32V407 has no mirrored reference manual at all, and
CH32X035 states its routes only in prose that the PDF text layer truncates.

The two sources are kept separate on purpose. extract_selectors.py stays the
build path's definition of a field's bits, because it needs no compiler and
covers families that ship no GPIO_Remap constant at all. This tool's bits are
the independent check on it: --compare reports every disagreement.

Requires a host C compiler (``cc``). EVT is read in place and never copied.

Usage:
    uv run tools/extract_remap_fields.py --mirrors <dir holding the CH32* clones>
        [--family CH32L103] [--json out.json] [--compare tables] [--raw]
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import paths  # noqa: E402
import signal_vocabulary  # noqa: E402

FN = re.compile(r"void GPIO_PinRemapConfig\(.*?\n\}", re.S)
LOCAL_DEFINE = re.compile(r"\s*#define\s+(LSB_MASK|DBGAFR_\w+|REMAP_\w+)\b")
CONST = re.compile(r"#define\s+(GPIO_(?:Remap|PartialRemap\d*|FullRemap)_(\w+))"
                   r"\s+\(\(uint32_t\)(0x[0-9A-Fa-f]+)\)")
ABS_DEREF = re.compile(r"\*\s*\(\s*(?:volatile\s+)?uint32_t\s*\*\s*\)\s*(0x[0-9A-Fa-f]+)")

# A second constant for the same field, not a peripheral of its own: on
# CH32V20x/V30x, GPIO_Remap_USART1_HighBit is PCFR2:26 and belongs to USART1.
SECOND_HALF = re.compile(r"^(?P<field>\w+?)_(?:HighBit|HIGHBIT|High_Bit)$")

# The registers the shim exposes, in the order a value's bits run.
REGISTERS = ("PCFR1", "PCFR2")

SHIM = """#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
typedef enum { DISABLE = 0, ENABLE = 1 } FunctionalState;
typedef struct { volatile uint32_t PCFR1, PCFR2; } AFIO_TypeDef;
static AFIO_TypeDef afio_inst;
#define AFIO (&afio_inst)
"""

# CH32V20x's decoder reads 0x40022030 -- past the end of the documented FLASH
# block -- and re-packs PCFR1 when it reads zero. Give it a page so it can, and
# probe both ways: a layout that depends on the silicon is a fact the tables
# have to carry, not a detail to average over. The default is all-ones, the
# plain documented layout.
DRIVER = """
static void map_probe_pages(void);
int main(int argc, char **argv) {
    map_probe_pages();
    uint32_t probe_val = argc > 1 ? (uint32_t)strtoul(argv[1], 0, 0) : 0xFFFFFFFFu;
    for (int i = 0; probe_addrs[i]; i++)
        *(volatile uint32_t *)probe_addrs[i] = probe_val;
    char line[64];
    while (fgets(line, sizeof line, stdin)) {
        uint32_t w = (uint32_t)strtoul(line, 0, 0);
        afio_inst.PCFR1 = 0; afio_inst.PCFR2 = 0;
        GPIO_PinRemapConfig(w, ENABLE);
        uint32_t s1 = afio_inst.PCFR1, s2 = afio_inst.PCFR2;
        afio_inst.PCFR1 = 0xFFFFFFFFu; afio_inst.PCFR2 = 0xFFFFFFFFu;
        GPIO_PinRemapConfig(w, DISABLE);
        printf("%08x %08x %08x %08x\\n", s1, s2,
               (uint32_t)~afio_inst.PCFR1, (uint32_t)~afio_inst.PCFR2);
    }
    return 0;
}
static void map_probe_pages(void) {
    for (int i = 0; probe_addrs[i]; i++) {
        uintptr_t page = probe_addrs[i] & ~(uintptr_t)0xFFF;
        mmap((void *)page, 0x1000, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    }
}
"""


def gpio_sources(mirrors: Path, only: str | None = None):
    """(family, <fam>_gpio.c, <fam>_gpio.h) for every EVT clone under mirrors."""
    for csrc in sorted(mirrors.glob("CH32*/EVT/**/*_gpio.c")):
        family = csrc.parts[len(mirrors.parts)]
        if only and family != only:
            continue
        header = csrc.parent.parent / "inc" / (csrc.stem + ".h")
        if header.exists():
            yield family, csrc, header


def observe(csrc: Path, words: list[int], work: Path, probe_val: int = 0xFFFFFFFF):
    """Run the vendor decoder once per constant.

    Returns ([(set1, set2, clear1, clear2), ...], addresses it reads), or
    (an {"error": ...} dict, addresses) when it cannot be built or run.
    """
    text = csrc.read_text(errors="ignore")
    found = FN.search(text)
    if not found:
        return {"error": "GPIO_PinRemapConfig が見つからない"}, []
    defines = "\n".join(l for l in text.splitlines() if LOCAL_DEFINE.match(l))
    addrs = sorted({int(a, 16) for a in ABS_DEREF.findall(found.group(0))})
    table = ("static const uintptr_t probe_addrs[] = {"
             + "".join(f"0x{a:x}u," for a in addrs) + "0};\n")
    program = work / f"{csrc.stem}.c"
    program.write_text(SHIM + table + defines + "\n" + found.group(0) + DRIVER)
    exe = work / csrc.stem
    built = subprocess.run(["cc", "-w", "-o", str(exe), str(program)],
                           capture_output=True, text=True)
    if built.returncode:
        tail = built.stderr.strip().splitlines()[-1:] or ["(no output)"]
        return {"error": f"compile: {tail[0]}"}, addrs
    run = subprocess.run([str(exe), hex(probe_val)],
                         input="\n".join(hex(w) for w in words),
                         capture_output=True, text=True)
    if run.returncode:
        return {"error": f"run: exit {run.returncode}"}, addrs
    rows = [tuple(int(x, 16) for x in line.split())
            for line in run.stdout.splitlines()]
    if len(rows) != len(words):
        return {"error": f"{len(words)} 定数に対し出力 {len(rows)} 行"}, addrs
    return rows, addrs


def bit_list(masks: dict[str, int]) -> list[tuple[str, int]]:
    """A field's bits, least-significant first: PCFR1 ascending, then PCFR2."""
    return [(register, bit)
            for register in REGISTERS
            for bit in range(32) if masks.get(register, 0) >> bit & 1]


def value_of(bits: list[tuple[str, int]], sets: dict[str, int]) -> int:
    return sum(1 << i for i, (register, bit) in enumerate(bits)
               if sets.get(register, 0) >> bit & 1)


def extract_family(csrc: Path, header: Path | None = None,
                   raw: bool = False) -> tuple[dict, list[str]]:
    """Observe one family's decoder. `csrc` is its <fam>_gpio.c."""
    if header is None:
        header = csrc.parent.parent / "inc" / (csrc.stem + ".h")
    label = csrc.stem
    notes: list[str] = []
    fields: dict = {}
    if not header.exists():
        return fields, [f"{label}: {header.name} が無い"]
    consts = CONST.findall(header.read_text(errors="ignore"))
    if not consts:
        return fields, [f"{label}: GPIO_Remap 定数が無いので対象外"]

    words = [int(word, 16) for _, _, word in consts]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        observed, addrs = observe(csrc, words, work)
        if isinstance(observed, dict):
            return fields, [f"{label}: {observed['error']}"]
        varies = False
        if addrs:
            alternate, _ = observe(csrc, words, work, 0)
            varies = not isinstance(alternate, dict) and alternate != observed

    # Group the constants by the field they belong to, folding a _HighBit
    # constant onto the field whose upper bits it carries.
    grouped: dict[str, list] = collections.defaultdict(list)
    for (symbol, name, _), row in zip(consts, observed):
        m = SECOND_HALF.match(name)
        grouped[m.group("field") if m else name].append((symbol, row))

    for name, entries in sorted(grouped.items()):
        # The field is everything its constants clear. Usually they all clear
        # the same bits, but where WCH split a field over two registers each
        # constant clears only the half it writes.
        clear = {"PCFR1": 0, "PCFR2": 0}
        for _, (_, _, c1, c2) in entries:
            clear["PCFR1"] |= c1
            clear["PCFR2"] |= c2
        bits = bit_list(clear)
        if not bits:
            notes.append(f"{label} {name}: DISABLE 経路が何も落とさない")
            continue
        # The value is read from the bits inside the field, which discards the
        # decoder's side writes: CH32V30x and CH32V407 re-assert the SWJ_CFG
        # bits on every call, so a raw `set` carries PCFR1:24..27 whatever route
        # was asked for.
        values = {
            symbol: value_of(bits, {"PCFR1": s1 & c1, "PCFR2": s2 & c2})
            for symbol, (s1, s2, c1, c2) in entries
        }
        # Every one of these constants names a real route, so their values must
        # be distinct and none may be 0, which means "not remapped". Where that
        # fails, the ENABLE and DISABLE paths disagree about where the field is
        # and the observation is unusable. CH32V407 is the case: for USART1 the
        # decoder clears PCFR2 bit 26 but sets `(GPIO_Remap & 0x2) << 26`, which
        # is bit 27, so two of its three constants read back as the same route.
        # The device header and the manual both say bit 26, so the vendor
        # function is the thing that is wrong -- which is why its bits are a
        # cross-check here and never the build's source of truth.
        counts = collections.Counter(values.values())
        broken = sorted(k for k, v in values.items() if v == 0 or counts[v] > 1)
        entry = {
            "bits": [f"{register}:{bit}" for register, bit in bits],
            "registers": sorted({register for register, _ in bits},
                                key=REGISTERS.index),
            "values": {} if broken else values,
        }
        if raw:
            entry["_observed"] = {
                symbol: {"set": [f"{s1:08x}", f"{s2:08x}"],
                         "clear": [f"{c1:08x}", f"{c2:08x}"]}
                for symbol, (s1, s2, c1, c2) in entries
            }
        if broken:
            entry["_unusable"] = {"values_observed": values,
                                  "reason": "値が0または重複"}
            notes.append(
                f"{label} {name}: 定数が一意な非0の値にならないため値を採らない {values}"
            )
        fields[name] = entry

    fields["_probe"] = {"reads_hardware": [hex(a) for a in addrs],
                        "layout_depends_on_it": bool(varies)}
    return fields, notes


def extract(mirrors: Path, only: str | None = None,
            raw: bool = False) -> tuple[dict, list[str]]:
    result: dict = {}
    notes: list[str] = []
    for family, csrc, header in gpio_sources(mirrors, only):
        fields, family_notes = extract_family(csrc, header, raw)
        notes += family_notes
        if len(fields) > 1:
            result[family] = fields
    return result, notes


def summarise(result: dict, out=sys.stderr) -> None:
    for family, fields in result.items():
        spans = sum(1 for k, v in fields.items()
                    if k != "_probe" and "PCFR2" in v["registers"])
        probe = fields["_probe"]
        note = ""
        if probe["reads_hardware"]:
            note = ("  reads " + ",".join(probe["reads_hardware"])
                    + ("; 配置が読み値で変わる" if probe["layout_depends_on_it"] else ""))
        print(f"{family:9} {len(fields) - 1:3} selector, うち PCFR2 に跨る {spans:2}{note}",
              file=out)


def family_series(candidates: Path) -> dict[str, set[str]]:
    """Which series each EVT family's silicon covers.

    Read from candidates/, whose _provenance names the header every SKU was
    built from, so the mapping stays true as SKUs are added rather than being a
    table to keep in step. CH32M007 and CH32V002 come from the CH32V006 clone,
    not from the ones named after them.
    """
    out: dict[str, set[str]] = collections.defaultdict(set)
    for path in sorted(candidates.glob("ch32*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        header = (data.get("_provenance") or {}).get("header")
        m = re.match(r"^(CH32[A-Z0-9]+)", data.get("part_number", ""))
        if header and m:
            out[header.split("/")[0]].add(m.group(1)[:8])
    return out


def compare(result: dict, tables: Path, candidates: Path, out=sys.stderr) -> int:
    """Diff the observed fields against remap_fields.csv, which is header-derived."""
    rows = {}
    with (tables / "remap_fields.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[(r["series"], signal_vocabulary.canonical_field(r["field"]))] = r
    covers = family_series(candidates)

    agree, differ, absent = 0, [], []
    for family, fields in result.items():
        for name, d in sorted(fields.items()):
            if name == "_probe":
                continue
            key = signal_vocabulary.canonical_field(name)
            series_list = sorted(covers.get(family, ()))
            if not series_list:
                continue
            hit = False
            for series in series_list:
                row = rows.get((series, key))
                if row is None:
                    continue
                hit = True
                if row["bits"].split(";") == d["bits"]:
                    agree += 1
                else:
                    differ.append((series, key, d["bits"], row["bits"].split(";")))
            if not hit:
                absent.append((family, key, d["bits"]))
    print(f"\n表と一致 {agree} / 不一致 {len(differ)} / 表にpin経路が無い {len(absent)}",
          file=out)
    for series, key, evt, table in differ:
        print(f"  {series:9} {key:16} EVT={','.join(evt):28} 表={','.join(table)}", file=out)
    return 1 if differ else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, required=True,
                    help="CH32* の EVT clone を並べたディレクトリ")
    ap.add_argument("--family", help="この family だけ処理する")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--compare", type=Path, help="突き合わせる remap_fields.csv のあるディレクトリ（evidence/）")
    ap.add_argument("--candidates", type=Path, default=paths.CANDIDATES,
                    help="family と series の対応を読む candidates ディレクトリ（既定 .cache/candidates）")
    ap.add_argument("--raw", action="store_true",
                    help="観測した set/clear をそのまま出す（デバッグ用）")
    args = ap.parse_args()

    result, notes = extract(args.mirrors, args.family, args.raw)
    summarise(result)
    for note in notes:
        print(f"  - {note}", file=sys.stderr)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print(f"wrote {args.json}", file=sys.stderr)
    if args.compare:
        return compare(result, args.compare, args.candidates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
