#!/usr/bin/env python3
"""Read each family's clock configurations out of EVT's system_*.c.

EVT ships one function per clock configuration the vendor supports, and the body
is a plain sequence of register writes by symbol name:

    static void SetSysClockTo144_HSI(void) {
        EXTEN->EXTEN_CTR |= EXTEN_PLL_HSI_PRE;   /* not an RCC register */
        RCC->CFGR0 |= (uint32_t)RCC_HPRE_DIV1;   /* HCLK  = SYSCLK   */
        RCC->CFGR0 |= (uint32_t)RCC_PPRE1_DIV2;  /* PCLK1 = HCLK / 2 */
        RCC->CFGR0 |= (uint32_t)(RCC_PLLSRC_HSI_Div2 | RCC_PLLMULL18);
        ...
    }

So the facts a generalised SystemInit needs -- which domains exist, what divides
what, which PLL multiplier reaches a frequency, what flash latency goes with it,
and which registers outside RCC take part -- are all here, statically. No
compiler is needed, unlike tools/extract_remap_fields.py.

The function *name* carries the clock tree's shape, in four spellings:

    SetSysClockTo144_HSI                              SYSCLK only
    SetSysClockTo_48MHZ_HSI                           SYSCLK only, other spelling
    SetSYSCLK_400MHz_HCLK_200MHz_HSE                  SYSCLK and HCLK differ
    SetSYSCLK_312_5M_CoreCLK_312_5M_HCLK_312_5M_HSI   three domains, 312.5 MHz

CH32H417 has no setter at all -- it is dual-core and configures its clocks
elsewhere -- so it yields nothing and says so.

This emits candidates for review and never writes device records.

Usage:
    uv run tools/extract_clock_tree.py --mirrors <dir holding the CH32* clones>
        [--family CH32V20x] [--json out.json]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import extract_addresses  # noqa: E402

# "static void SetSysClockTo144_HSI(void)" opening a body that ends at column 0.
FUNCTION = re.compile(
    r"^(?:static\s+)?void\s+(?P<name>Set(?:SysClockTo|SYSCLK)\w*)\s*\(\s*void\s*\)\s*$"
    r"(?P<body>.*?)^\}", re.M | re.S)

# "RCC->CFGR0 |= (uint32_t)(A | B);"  ->  register, operator, the symbols in it.
WRITE = re.compile(r"(?P<block>\w+)\s*->\s*(?P<register>\w+)\s*"
                   r"(?P<op>\|=|&=|=)\s*(?P<value>[^;]*);")
SYMBOL = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,})\b")
# A body can configure the PLL two ways behind a compile-time switch: CH32V307's
# SetSysClockTo24 multiplies by 3 under one #if and by 6 under the other, because
# the D8 and D8C variants divide HSI differently. Which branch applies is part of
# the fact, so the condition is carried with each write.
CPP = re.compile(r"^\s*#\s*(?P<directive>if|ifdef|ifndef|elif|else|endif)\b"
                 r"\s*(?P<condition>.*?)\s*$")
CAST = re.compile(r"\(\s*u?int(?:8|16|32)_t\s*\)")
DEFINE = re.compile(r"^#define\s+(\w+)\s+\(\(u?int(?:8|16|32)_t\)(0x[0-9A-Fa-f]+|\d+)\)")

# The domains a configuration names. A run is an optional domain label, an
# optional core name, and a frequency: CH32H417 is dual-core and gives each core
# its own CoreCLK, as "CoreCLK_V5F_400M_V3F_100M".
DOMAIN_RUN = re.compile(r"(?:(?P<domain>SYSCLK|CoreCLK|HCLK)_)?"
                        r"(?:(?P<core>V5F|V3F)_)?"
                        r"(?P<mhz>\d+(?:_\d+)?)M(?:Hz|HZ)?(?=_|$)", re.I)
# "SetSysClockTo144_HSI", "SetSysClockTo_48MHZ_HSE", "SetSysClockTo24" (no
# oscillator named), "SetSysClockToHSE" (run straight off the oscillator, no
# frequency in the name), "SetSysClockToHSI_LP" (the low-power variant).
PLAIN = re.compile(r"^SetSysClockTo_?(?P<mhz>\d+)?(?:MHz|MHZ)?_?"
                   r"(?P<source>HSI|HSE)?(?P<mode>_LP)?$")
STAGED = re.compile(r"^SetSYSCLK_(?P<stages>.*?)_?(?P<source>HSI|HSE)$")

# What each symbol tells us. A prescaler and a PLL multiplier are both just
# defines; only the name says which.
PRESCALER = re.compile(r"^RCC_(?P<field>HPRE|PPRE1|PPRE2|ADCPRE|CoreHCLK_PRE|HBPRE)_"
                       r"(?P<divider>DIV[0-9_]+|Div[0-9_]+)$")
PLL = re.compile(r"^RCC_(?:PLLSRC|PLLMULL|PLLXTPRE|PLL_\w+|CFGR2_\w*PLL\w*)\w*$")
LATENCY = re.compile(r"^FLASH_ACTLR_LATENCY(?:_(?P<wait>\d+))?$")
SOURCE_SELECT = re.compile(r"^RCC_SW_(?P<source>\w+)$")
# Anything the configuration writes that is not RCC or FLASH. This is the fact
# R-24 calls C-4: CH32V20x cannot run its PLL from HSI without EXTEN_CTR.
NON_RCC_BLOCKS = ("RCC", "FLASH")


def system_sources(family: Path) -> dict[str, tuple[str, list[Path]]]:
    """The distinct system_ch32*.c under a family, and which copies hold each.

    EVT ships this file once per example and **the copies are not identical**:
    CH32H417 has 390 of them in 5 distinct versions. Reading only the first one
    silently picks whichever example sorted first, the same trap the linker
    scripts have. So every copy is read and its configurations unioned, with a
    count of how many copies attest each -- a configuration in 185 of 390 files
    is the mainstream one, and one in a single file is example-specific.
    """
    variants: dict[str, tuple[str, list[Path]]] = {}
    for path in sorted(family.glob("EVT/**/system_ch32*.c")):
        text = path.read_text(errors="ignore")
        digest = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]
        if digest in variants:
            variants[digest][1].append(path)
        else:
            variants[digest] = (text, [path])
    return variants


def find_device_header(family: Path) -> Path | None:
    candidates = sorted(family.glob("EVT/**/Peripheral/inc/ch32*.h"))
    plain = [p for p in candidates
             if re.fullmatch(r"ch32[a-z0-9]+\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else None


def defines(header: Path | None) -> dict[str, int]:
    if header is None:
        return {}
    out: dict[str, int] = {}
    for line in header.read_text(errors="ignore").splitlines():
        m = DEFINE.match(line.strip())
        if m:
            # Some defines are decimal with leading zeros, which int(x, 0) rejects.
            raw = m.group(2)
            out.setdefault(m.group(1),
                           int(raw, 16) if raw.lower().startswith("0x") else int(raw, 10))
    return out


def hz(mhz: str) -> int:
    """"312_5" is 312.5 MHz; the vendor writes the decimal point as an underscore."""
    whole, _, fraction = mhz.partition("_")
    return round(float(f"{whole}.{fraction}" if fraction else whole) * 1_000_000)


def domains_of(name: str) -> tuple[dict[str, int], str | None]:
    """The clock domains a configuration's name states, and its oscillator.

    A name need not state a frequency. "SetSysClockToHSE" runs the system
    straight off the oscillator, so the frequency is the board's crystal and not
    a property of the chip; the domains come back empty rather than guessed.
    """
    m = PLAIN.match(name)
    if m:
        mhz = m.group("mhz")
        return ({"SYSCLK": hz(mhz)} if mhz else {}), m.group("source")
    m = STAGED.match(name)
    if m:
        found: dict[str, int] = {}
        # "SetSYSCLK_" has already eaten the first label, so the first frequency
        # in what is left belongs to SYSCLK.
        domain = "SYSCLK"
        for run in DOMAIN_RUN.finditer(m.group("stages")):
            if run.group("domain"):
                domain = {"sysclk": "SYSCLK", "coreclk": "CoreCLK",
                          "hclk": "HCLK"}[run.group("domain").lower()]
            if domain is None:
                continue
            core = run.group("core")
            found[f"{domain}[{core}]" if core else domain] = hz(run.group("mhz"))
        return found, m.group("source")
    return {}, None


def read_variant(text: str, symbols: dict[str, int], family_name: str,
                 notes: list[str],
                 sites: dict[str, set[str]] | None = None) -> dict[str, dict]:
    """The configurations one copy of system_ch32*.c states.

    `sites` collects, for every symbol that ends up in a clock_configs cell by
    name alone, the `BLOCK->REGISTER` it was written to. The cell cannot carry
    the number: RCC_PLLMULL18 is 0x003C0000 and RCC_PLLMULL18_EXTEN is 0, so the
    same "x18" reads two ways and the name is not decodable. Recording the write
    site rather than guessing from the name is what lets the value be resolved
    against the right register.
    """
    configs: dict[str, dict] = {}
    for found in FUNCTION.finditer(text):
        name, body = found.group("name"), found.group("body")
        if not body.strip():
            continue  # a forward declaration, not the definition
        domains, oscillator = domains_of(name)
        if not domains:
            notes.append(f"{family_name}: 関数名から周波数を読めない {name}")

        entry = {
            "source": oscillator,
            "domains": domains,
            "prescalers": {},
            "pll": [],
            "flash_latency": None,
            "system_clock_source": None,
            "outside_rcc": [],
            "unresolved_symbols": [],
        }
        conditions: list[str] = []
        for line in body.splitlines():
            directive = CPP.match(line)
            if directive:
                kind = directive.group("directive")
                condition = directive.group("condition")
                if kind in ("if", "ifdef", "ifndef"):
                    conditions.append(f"{kind} {condition}".strip())
                elif kind in ("elif", "else"):
                    if conditions:
                        conditions[-1] = f"{kind} {condition}".strip()
                elif kind == "endif" and conditions:
                    conditions.pop()
                continue
            write = WRITE.search(line)
            if not write:
                continue
            where = " && ".join(conditions)
            block, register = write.group("block"), write.group("register")
            value = CAST.sub("", write.group("value"))
            if "~" in value:
                continue  # clearing the field before setting it
            for symbol in SYMBOL.findall(value):
                if symbol not in symbols:
                    if symbol not in ("uint32_t", "uint8_t", "uint16_t"):
                        entry["unresolved_symbols"].append(symbol)
                    continue
                m = PRESCALER.match(symbol)
                if m:
                    entry["prescalers"][m.group("field")] = m.group("divider").upper()
                    continue
                m = LATENCY.match(symbol)
                if m and m.group("wait") is not None:
                    entry["flash_latency"] = int(m.group("wait"))
                    continue
                m = SOURCE_SELECT.match(symbol)
                if m:
                    entry["system_clock_source"] = m.group("source")
                    continue
                if PLL.match(symbol):
                    entry["pll"].append(f"{symbol} [{where}]" if where else symbol)
                    if sites is not None:
                        sites.setdefault(symbol, set()).add(f"{block}->{register}")
                    continue
                if block not in NON_RCC_BLOCKS:
                    entry["outside_rcc"].append(f"{block}->{register} {symbol}")
                    if sites is not None:
                        sites.setdefault(symbol, set()).add(f"{block}->{register}")
        entry["unresolved_symbols"] = sorted(set(entry["unresolved_symbols"]))
        entry["outside_rcc"] = sorted(set(entry["outside_rcc"]))
        entry["pll"] = list(dict.fromkeys(entry["pll"]))
        configs[name] = entry
    return configs


def read_family(family: Path) -> tuple[dict, list[str]]:
    notes: list[str] = []
    variants = system_sources(family)
    if not variants:
        return {}, [f"{family.name}: system_ch32*.c が無い"]
    symbols = defines(find_device_header(family))

    configs: dict[str, dict] = {}
    copies: collections.Counter = collections.Counter()
    disagree: list[str] = []
    sites: dict[str, set[str]] = {}
    total = sum(len(paths) for _, paths in variants.values())
    for digest, (text, paths) in variants.items():
        for name, entry in read_variant(text, symbols, family.name, notes,
                                        sites).items():
            copies[name] += len(paths)
            known = configs.get(name)
            if known is None:
                configs[name] = entry
            elif known != entry:
                # Say what differs, not just that something does. CH32V407's
                # 400MHz setting multiplies by 16 in one copy and by 8 in
                # another, which is the kind of difference worth naming.
                only = (set(entry["pll"]) ^ set(known["pll"])) | \
                       (set(entry["outside_rcc"]) ^ set(known["outside_rcc"]))
                # A short difference is the interesting one (x16 against x8);
                # a long one means one copy configures the PLL and another does
                # not, which the count says better than the list.
                disagree.append((name, " ".join(sorted(only)) if len(only) <= 6
                                 else f"{len(only)} 項目"))
    notes[:] = list(dict.fromkeys(notes))
    for name, differing in sorted(set(disagree)):
        detail = f"（{differing} の有無。先に読んだ版を採用）" if differing \
            else "（先に読んだ版を採用）"
        notes.append(f"{family.name}: {name} の中身が例題によって違う{detail}")
    for name, entry in configs.items():
        entry["copies"] = f"{copies[name]}/{total}"

    if not configs:
        notes.append(f"{family.name}: SetSysClockTo*/SetSYSCLK* が無い")

    # C-5's other half: the divider encodings, from the device header. These are
    # a property of the family, not of one configuration.
    encodings: dict[str, dict[str, int]] = collections.defaultdict(dict)
    for symbol, value in symbols.items():
        m = PRESCALER.match(symbol)
        if m:
            encodings[m.group("field")][m.group("divider").upper()] = value
    # A-1 and A-2 of R-24's follow-up: the number behind every symbol a config
    # cell names, and where it is written. The address comes from the header's
    # own base-and-struct chain, because the name does not give it away --
    # CH32V205 calls EXTEN's register CTLR0 where everyone else calls it
    # EXTEN_CTR, and CH32X315 puts the block somewhere else entirely.
    header = find_device_header(family)
    where = extract_addresses.addresses(header) if header else {}
    # Only the symbols the configs that survived the union actually name. A copy
    # this family disagrees about can mention a symbol the retained version does
    # not, and a row nothing refers to would claim it is in use.
    # A pll entry is "SYMBOL" or "SYMBOL [condition]"; an outside_rcc entry is
    # "BLOCK->REGISTER SYMBOL". The symbol is at opposite ends of the two.
    named = {entry.split(" ")[0] for config in configs.values()
             for entry in config["pll"]}
    named |= {entry.split(" ")[-1] for config in configs.values()
              for entry in config["outside_rcc"]}
    resolved: list[dict] = []
    for symbol in sorted(sites):
        if symbol not in symbols or symbol not in named:
            continue
        for site in sorted(sites[symbol]):
            block, _, register = site.partition("->")
            address = where.get((block, register))
            resolved.append({"symbol": symbol, "register": site,
                             "address": "" if address is None else f"{address:#010x}",
                             "value": symbols[symbol]})
        if len(sites[symbol]) > 1:
            notes.append(f"{family.name}: {symbol} が複数のレジスタに書かれる "
                         f"({', '.join(sorted(sites[symbol]))})")
    return {"copies": total,
            "variants": len(variants),
            "configs": configs,
            "symbols": resolved,
            "prescaler_encodings": {k: dict(sorted(v.items(), key=lambda kv: kv[1]))
                                    for k, v in sorted(encodings.items())}}, notes


def summarise(result: dict, out=sys.stderr) -> None:
    for family, data in result.items():
        configs = data["configs"]
        oscillators = collections.Counter(c["source"] or "?" for c in configs.values())
        multi = {name: c["domains"] for name, c in configs.items()
                 if len(c["domains"]) > 1}
        outside = sorted({w for c in configs.values() for w in c["outside_rcc"]})
        latencies = sorted({c["flash_latency"] for c in configs.values()
                            if c["flash_latency"] is not None})
        print(f"{family:10} 設定 {len(configs):3}  "
              f"copy {data['copies']:3}/{data['variants']}種  "
              f"{'/'.join(f'{k}{v}' for k, v in sorted(oscillators.items()))}"
              f"  多段 {len(multi):2}  latency {latencies or '触らない'}", file=out)
        if outside:
            print(f"{'':10}   RCC外: {', '.join(outside)}", file=out)
        for field, table in data["prescaler_encodings"].items():
            shown = " ".join(f"{d}={v:#x}" for d, v in table.items())
            print(f"{'':10}   {field}: {shown}", file=out)


# C-7's half of the clock data lives in <fam>_rcc.h, not the device header, and
# the options are #if-guarded: CH32V20x defines RCC_RTCCLKSource_HSE_Div512 and
# RCC_RTCCLKSource_HSE_Div128 as the *same* value 0x300 under different branches,
# because the variants divide HSE differently for the RTC.
SOURCE_OPTION = re.compile(
    r"^\s*#define\s+RCC_(?P<consumer>[A-Za-z0-9]+?)CLK(?:Source|48MSource)_"
    r"(?P<option>\w+)\s+\(\(u?int(?:8|16|32)_t\)(?P<value>0x[0-9A-Fa-f]+|\d+)\)")
CONFIG_FN = re.compile(r"^void\s+RCC_(?P<consumer>[A-Za-z0-9]+?)CLKConfig\s*\("
                       r".*?\n\}", re.M | re.S)
SHIFT = re.compile(r"<<\s*(?:\(\s*uint32_t\s*\))?\s*(\d+)")
REG_WRITE = re.compile(r"RCC\s*->\s*(\w+)")
# "#ifndef __CH32V20x_RCC_H" is the include guard, not a silicon variant.
INCLUDE_GUARD = re.compile(r"^ifn?def\s+_+\w*_H_?\w*$")


def find_rcc_pair(family: Path) -> tuple[Path | None, Path | None]:
    header = sorted(family.glob("EVT/**/Peripheral/inc/ch32*_rcc.h"))
    source = sorted(family.glob("EVT/**/Peripheral/src/ch32*_rcc.c"))
    return (header[0] if header else None), (source[0] if source else None)


def read_sources(family: Path) -> tuple[dict, list[str]]:
    """Which clock each peripheral can be fed from, and where that is written.

    This is R-24's C-7: the USB 48 MHz path, the RTC's oscillator, the ADC
    divider. The options are named in <fam>_rcc.h; which register field they land
    in is only visible in RCC_<consumer>CLKConfig() in <fam>_rcc.c.
    """
    notes: list[str] = []
    header, source = find_rcc_pair(family)
    if header is None:
        return {}, [f"{family.name}: ch32*_rcc.h が無い"]

    # Where each consumer's value is written, from the setter's body.
    target: dict[str, dict] = {}
    if source is not None:
        for found in CONFIG_FN.finditer(source.read_text(errors="ignore")):
            registers = list(dict.fromkeys(REG_WRITE.findall(found.group(0))))
            shifts = SHIFT.findall(found.group(0))
            target[found.group("consumer")] = {
                "register": "|".join(registers),
                "shift": int(shifts[0]) if shifts else 0,
            }

    options: dict[str, list[dict]] = collections.defaultdict(list)
    conditions: list[str] = []
    for line in header.read_text(errors="ignore").splitlines():
        directive = CPP.match(line)
        if directive:
            kind, condition = directive.group("directive"), directive.group("condition")
            if kind in ("if", "ifdef", "ifndef"):
                conditions.append(f"{kind} {condition}".strip())
            elif kind in ("elif", "else") and conditions:
                conditions[-1] = f"{kind} {condition}".strip()
            elif kind == "endif" and conditions:
                conditions.pop()
            continue
        m = SOURCE_OPTION.match(line)
        if not m:
            continue
        consumer = m.group("consumer")
        where = target.get(consumer, {})
        if not where:
            notes.append(
                f"{family.name}: RCC_{consumer}CLKConfig が無いので書き込み先が不明"
            )
        raw = m.group("value")
        options[consumer].append({
            "option": m.group("option"),
            "value": int(raw, 16) if raw.lower().startswith("0x") else int(raw, 10),
            "register": where.get("register", ""),
            "shift": where.get("shift", 0),
            "condition": " && ".join(c for c in conditions
                                     if not INCLUDE_GUARD.match(c)),
        })
    return dict(options), notes


def extract_all(mirrors: Path, only: str | None = None) -> tuple[dict, list[str]]:
    """Every family's clock configurations, keyed by EVT family directory name."""
    result: dict = {}
    notes: list[str] = []
    for family in sorted(p for p in mirrors.glob("CH32*") if p.is_dir()):
        if only and family.name != only:
            continue
        data, family_notes = read_family(family)
        notes += family_notes
        sources, source_notes = read_sources(family)
        notes += source_notes
        if data:
            data["peripheral_sources"] = sources
            result[family.name] = data
    return result, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, required=True,
                    help="CH32* の EVT clone を並べたディレクトリ")
    ap.add_argument("--family", help="この family だけ処理する")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    result, notes = extract_all(args.mirrors, args.family)
    summarise(result)
    for note in notes:
        print(f"  - {note}", file=sys.stderr)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
