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
DEFINE = re.compile(r"^#define\s+(?P<name>\w+)\s+\(\(u?int(?:8|16|32)_t\)"
                    r"(?P<value>0x[0-9A-Fa-f]+|\d+)\)\s*(?:/\*(?P<comment>.*?)\*/)?")
# ヘッダのコメントが宣言するbit範囲。値と食い違うことがある（CH32V003の
# FLASH_ACTLR_LATENCY は 0x03 = 2bit なのにコメントは LATENCY[2:0] = 3bit）。
BIT_RANGE = re.compile(r"\[(?P<high>\d+):(?P<low>\d+)\]")

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
# CH32X315とCH32H417のFLASH_ACTLRは待ちサイクル数ではなく**フラッシュクロックの
# 分周比**を持つ（SCK_CFG[1:0]）。名前が LATENCY_HCLK_DIVn なので LATENCY と
# 同じ列に入れると「n待ち」と読まれる。単位が違うので列を分ける。
FLASH_SCK = re.compile(r"^FLASH_ACTLR_LATENCY_HCLK_DIV(?P<divider>\d+)$")
# 設定を「適用する」ために触るもの。enable/ready ビットと、read-modify-write の
# ために要る field マスクがここに入る。値だけでは書けないので、名前が出てくる
# 記号は分類できたものも含めて全部 clock_symbols.csv に落とす。
CLOCK_SYMBOL = re.compile(r"^(?:RCC_\w+|FLASH_ACTLR\w*|EXTEN_\w+)$")
# Anything the configuration writes that is not RCC or FLASH. This is the fact
# R-24 calls C-4: CH32V20x cannot run its PLL from HSI without EXTEN_CTR.
NON_RCC_BLOCKS = ("RCC", "FLASH")

# CH32X315とCH32H417はレジスタを直接読み書きせず、ローカル変数へ写して直す。
#   FLASH_Temp = FLASH->ACTLR;
#   FLASH_Temp &= ~FLASH_ACTLR_SCK_CFG;
#   FLASH_Temp |= FLASH_ACTLR_LATENCY_HCLK_DIV1;
#   FLASH->ACTLR = FLASH_Temp;
# `BLOCK->REGISTER op= value` しか見ていないと、この2行が丸ごと見えない。それが
# 「CH32X315はflash latencyを一度も書かない」という誤りの原因だった。
ALIAS = re.compile(r"^\s*(?P<name>\w+)\s*=\s*(?P<block>\w+)\s*->\s*(?P<register>\w+)\s*;")
LOCAL_WRITE = re.compile(r"^\s*(?P<name>\w+)\s*(?P<op>\|=|&=)\s*(?P<value>[^;]*);")
# ready待ちの条件。書き込みではないので WRITE では拾えないが、どのビットを見て
# 待つのかは設定を適用するのに要る事実。
POLL = re.compile(r"while\s*\(.*?(?P<block>\w+)\s*->\s*(?P<register>\w+)")


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
            raw = m.group("value")
            out.setdefault(m.group("name"),
                           int(raw, 16) if raw.lower().startswith("0x") else int(raw, 10))
    return out


def comments(header: Path | None) -> dict[str, str]:
    """The trailing comment of each define, which sometimes contradicts the value."""
    if header is None:
        return {}
    out: dict[str, str] = {}
    for line in header.read_text(errors="ignore").splitlines():
        m = DEFINE.match(line.strip())
        if m and m.group("comment"):
            out.setdefault(m.group("name"), " ".join(m.group("comment").split()))
    return out


# SystemInit puts the chip into a known state before any configuration runs, and
# it does so with **literal hex** rather than the symbols the rest of the file
# uses -- `RCC->CFGR0 &= 0xF8FF0000`. Nothing symbol-based can see those, so they
# are read as an ordered list of steps instead.
INIT_FUNCTION = re.compile(
    r"^(?:static\s+)?void\s+SystemInit\s*\(\s*void\s*\)\s*$(?P<body>.*?)^\}",
    re.M | re.S)
ANY_FUNCTION = re.compile(r"^(?:static\s+)?\w[\w\s*]*?\b(?P<name>\w+)\s*\(")
NUMBER = re.compile(r"^(?:0[xX][0-9A-Fa-f]+|\d+)$")
# `(1<<20)` — RMW の set がビット位置で書かれる。
# （`SHIFT` は後方でヘッダ用に別定義があるので名前を分ける）
RMW_SHIFT = re.compile(r"^(?P<base>\d+)\s*<<\s*(?P<by>\d+)$")
# `#if defined(CH32V30x_D8C)` の macro。
MACRO_NAME = re.compile(r"\b(CH32[A-Za-z0-9_]+)\b")
# `while ((RCC->CTLR & RCC_HSIRDY) != RCC_HSIRDY)` -- the mask and the comparison
# the body waits for. Both are needed; the comparison is kept verbatim rather
# than interpreted, because what counts as "ready" is the vendor's statement.
POLL_TEST = re.compile(r"&\s*(?P<mask>[\w]+)\s*\)?\s*(?P<compare>[!=]=\s*[\w]+)")
# The HSI factory trim. CH32V003 reads a byte at CFG0_PLL_TRIM (0x1FFFF7D4) and
# feeds the low 5 bits to the calibration setter; CH32L103 and CH32V205 do the
# same from HSI_LP_TRIM_BASE (0x1FFFF72A). Skipping it leaves HSI out of spec.
TRIM_CALL = re.compile(r"RCC_AdjustHSICalibrationValue\s*\((?P<arg>.*)\)\s*;")
DEREF = re.compile(r"\*\s*\(\s*u?int8_t\s*\*\s*\)\s*(?P<symbol>\w+)")
BYTE_COPY = re.compile(r"^\s*(?:u?int8_t\s+)?(?P<name>\w+)\s*=\s*"
                       r"\*\s*\(\s*u?int8_t\s*\*\s*\)\s*(?P<symbol>\w+)\s*;")
AND_MASK = re.compile(r"&\s*(?P<mask>0[xX][0-9A-Fa-f]+|\d+)")
GUARD = re.compile(r"^\s*if\s*\(\s*(?P<name>\w+)\s*(?P<compare>[!=]=\s*\S+?)\s*\)")

# The banner that opens each register's block of bit defines. It is the only
# thing in the header that says which register a bit define belongs to -- the
# name does not (RCC_ADCPRE says nothing about CFGR0) -- and it covers all but
# 0.3% of them across the twelve headers.
BANNER = re.compile(r"^/\*+\s*Bit definition for (?P<register>\w+) register\s*\**/")


def banner_registers(header: Path | None) -> dict[str, str]:
    """{symbol: "BLOCK->REGISTER"} from the banners, for symbols no write places."""
    if header is None:
        return {}
    out: dict[str, str] = {}
    where: str | None = None
    for line in header.read_text(errors="ignore").splitlines():
        line = line.strip()
        m = BANNER.match(line)
        if m:
            block, _, register = m.group("register").partition("_")
            where = f"{block}->{register}" if register else None
            continue
        m = DEFINE.match(line)
        if m and where:
            out.setdefault(m.group("name"), where)
    return out


def field_masks(symbols: dict[str, int]) -> set[str]:
    """The symbols that are a field's mask rather than one of its values.

    Needed because the vendor's own code does not always clear a field before
    writing it -- CH32V20x's SetSysClockTo* ORs RCC_HPRE_DIV1 in and relies on
    the reset value -- so observing the source finds only some of the masks. A
    consumer writing the field needs all of them, since every setter is
    read-modify-write.

    A mask is recognised by the header's own shape: its name is the prefix, at an
    underscore boundary, of at least two other symbols, and its value is one run
    of set bits. That is exactly RCC_HPRE against RCC_HPRE_DIV1..DIV512, RCC_SW
    against RCC_SW_HSI/HSE/PLL, and FLASH_ACTLR_LATENCY against its numbered
    values. A single enable bit like RCC_HSEON prefixes nothing and is not one.
    """
    contiguous = {}
    for name, value in symbols.items():
        if value and (value | (value - 1)) == (value + (value & -value) - 1):
            contiguous[name] = value
    out = set()
    for name in contiguous:
        if not CLOCK_SYMBOL.match(name):
            continue
        members = sum(1 for other in symbols if other.startswith(name + "_"))
        if members >= 2:
            out.add(name)
    return out


def mask_disagrees(symbol: str, value: int, comment: str) -> str | None:
    """The comment's own bit range, when it is a different width. Else None.

    CH32V003 defines FLASH_ACTLR_LATENCY as 0x03 and calls it LATENCY[2:0] in the
    same line. 0x03 is two bits wide; [2:0] is three. A consumer that reads the
    name writes a different mask than one that reads the number, and the narrow
    one cannot write latency 4. Recording which document said what is the whole
    point of the basis column, so the disagreement is carried, not resolved.

    Only the width is compared. The comment numbers the bits **within the
    field**, not within the register: every family writes RCC_SWS[1:0] for a
    mask of 0xC, which is the same two bits placed at 3:2. Comparing positions
    would call each of those a contradiction.
    """
    m = BIT_RANGE.search(comment)
    if not m or value == 0:
        return None
    declared = int(m.group("high")) - int(m.group("low")) + 1
    return f"{symbol}{m.group(0)}" if declared != bin(value).count("1") else None


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
                 notes: list[str]) -> dict[str, dict]:
    """The configurations one copy of system_ch32*.c states.

    Each entry's `symbols` records, per symbol the body names, the
    `BLOCK->REGISTER` it was written to and the role it played there. The
    clock_configs cells cannot carry any of that: RCC_PLLMULL18 is 0x003C0000
    and RCC_PLLMULL18_EXTEN is 0, so the same "x18" reads two ways and the name
    is not decodable; and a field's mask never reaches a cell at all even though
    every setter is read-modify-write and cannot be written without it.
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
            "flash_sck_div": None,
            "system_clock_source": None,
            "outside_rcc": [],
            "unresolved_symbols": [],
            "symbols": {},
        }
        conditions: list[str] = []
        alias: dict[str, tuple[str, str]] = {}
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
            # A register the body copies into a local before editing it.
            copy = ALIAS.match(line)
            if copy:
                alias[copy.group("name")] = (copy.group("block"),
                                             copy.group("register"))
                continue
            where = " && ".join(conditions)
            write = WRITE.search(line)
            if write:
                block, register = write.group("block"), write.group("register")
                value, op = write.group("value"), write.group("op")
            else:
                local = LOCAL_WRITE.match(line)
                poll = POLL.search(line)
                if local and local.group("name") in alias:
                    block, register = alias[local.group("name")]
                    value, op = local.group("value"), local.group("op")
                elif poll:
                    # Not a write. Which bit the body waits on is still part of
                    # applying the configuration, so it is recorded as a poll.
                    block, register = poll.group("block"), poll.group("register")
                    value, op = line, "poll"
                else:
                    continue
            value = CAST.sub("", value)
            # `&= ~FIELD` names the mask, not a value. Setters are all
            # read-modify-write, so the mask is as necessary as the value and
            # skipping the line lost half of what is needed.
            role = ("poll" if op == "poll"
                    else "mask" if (op == "&=" and "~" in value) else "value")
            for symbol in SYMBOL.findall(value):
                if symbol not in symbols:
                    if symbol not in ("uint32_t", "uint8_t", "uint16_t") and role != "poll":
                        entry["unresolved_symbols"].append(symbol)
                    continue
                if CLOCK_SYMBOL.match(symbol):
                    entry["symbols"].setdefault(symbol, set()).add(
                        (f"{block}->{register}", role))
                if role != "value":
                    continue  # a mask or a polled bit configures nothing by itself
                m = PRESCALER.match(symbol)
                if m:
                    entry["prescalers"][m.group("field")] = m.group("divider").upper()
                    continue
                m = FLASH_SCK.match(symbol)
                if m:
                    entry["flash_sck_div"] = int(m.group("divider"))
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
                    continue
                if block not in NON_RCC_BLOCKS:
                    entry["outside_rcc"].append(f"{block}->{register} {symbol}")
        entry["unresolved_symbols"] = sorted(set(entry["unresolved_symbols"]))
        entry["outside_rcc"] = sorted(set(entry["outside_rcc"]))
        entry["pll"] = list(dict.fromkeys(entry["pll"]))
        entry["symbols"] = {k: sorted(v) for k, v in sorted(entry["symbols"].items())}
        configs[name] = entry
    return configs


def read_init(text: str, symbols: dict[str, int]) -> list[dict]:
    """The ordered steps of SystemInit, plus every HSI trim load in the file.

    This is the one place order is recorded, and it is a transcription rather
    than a decision: `RCC->CTLR |= 1` has to precede clearing SW or the chip has
    no clock to run on. The switching sequence proper is not here, because when
    to raise the flash latency relative to the switch is a policy and this file
    is not one.

    A `clear` step's value is the AND mask exactly as the source writes it --
    the bits to keep, not the bits to drop -- because that is what the vendor
    states and inverting it would be an interpretation.

    **SystemInit は一直線とは限らない**（以前はそう決め打っていた——worklist の
    F-39。原典検証で発覚）:

    - CH32V30x は `#ifdef CH32V30x_D8C` / `#else` で手順が分岐する。落とすと
      D8 系に D8C の3手順を混ぜて再生することになる。分岐は `condition` に
      variant macro で書く（interrupts.csv と同じ。`!` は「定義されていない」）
    - CH32V00X は `tmp = RCC->CTLR; tmp &= …; tmp |= …; RCC->CTLR = tmp;` と
      **ローカル変数経由の read-modify-write** で書く。行ごとの直接代入しか
      見ていなかったので、この4行が丸ごと落ちていた。演算はソースの順に
      clear/set の手順として採り、最後の書き戻しは commit なので採らない
    """
    steps: list[dict] = []

    def number(token: str) -> int | None:
        if NUMBER.match(token):
            return int(token, 16) if token.lower().startswith("0x") else int(token)
        return symbols.get(token)

    found = INIT_FUNCTION.search(text)
    if found:
        branch: list[str] = []      # 開いている #if の variant macro
        seen: list[list[str]] = []  # #else が否定する枝
        alias: dict[str, tuple[str, str]] = {}

        def guarded(extra: str = "") -> str:
            parts = [c for c in branch if c] + ([extra] if extra else [])
            return "+".join(parts)

        for line in found.group("body").splitlines():
            bare = CAST.sub("", line)
            directive = CPP.match(bare)
            if directive:
                kind = directive.group("directive")
                macros = MACRO_NAME.findall(directive.group("condition") or "")
                if kind in ("if", "ifdef", "ifndef"):
                    branch.append("|".join(macros))
                    seen.append(list(macros))
                elif kind == "elif" and branch:
                    branch[-1] = "|".join(macros)
                    seen[-1].extend(macros)
                elif kind == "else" and branch:
                    branch[-1] = "+".join(f"!{m}" for m in (seen[-1] if seen else []))
                elif kind == "endif" and branch:
                    branch.pop()
                    if seen:
                        seen.pop()
                continue
            copy = ALIAS.match(bare)
            if copy:
                alias[copy.group("name")] = (copy.group("block"),
                                             copy.group("register"))
                continue
            write = WRITE.search(bare)
            if write:
                operand = write.group("value").strip().strip("()~ ").strip()
                value = number(operand)
                if value is None:
                    # `RCC->CTLR = tmp;` — RMW の書き戻し。演算は下で採っている。
                    continue
                steps.append({
                    "function": "SystemInit",
                    "action": {"|=": "set", "&=": "clear", "=": "write"}[write.group("op")],
                    "register": f"{write.group('block')}->{write.group('register')}",
                    "value": value, "condition": guarded(), "source": "",
                })
                continue
            local = LOCAL_WRITE.match(bare)
            if local and local.group("name") in alias:
                operand = local.group("value").strip().strip("()~ ").strip()
                value = number(operand)
                if value is None and RMW_SHIFT.match(operand):
                    m = RMW_SHIFT.match(operand)
                    value = int(m.group("base")) << int(m.group("by"))
                if value is None:
                    continue
                block, register = alias[local.group("name")]
                steps.append({
                    "function": "SystemInit",
                    "action": {"|=": "set", "&=": "clear"}[local.group("op")],
                    "register": f"{block}->{register}",
                    "value": value, "condition": guarded(), "source": "",
                })
                continue
            poll = POLL.search(bare)
            test = POLL_TEST.search(bare) if poll else None
            if poll and test:
                value = number(test.group("mask"))
                if value is None:
                    continue
                steps.append({
                    "function": "SystemInit",
                    "action": "poll",
                    "register": f"{poll.group('block')}->{poll.group('register')}",
                    "value": value,
                    "condition": guarded(" ".join(test.group("compare").split())),
                    "source": "",
                })

    # The trim loads, wherever they sit. CH32V003 calls the setter twice -- once
    # in SystemInit with a literal default and once from the factory byte, the
    # second guarded by the byte not being 0xFF (an unprogrammed part).
    where, aliases, guards = "", {}, {}
    for line in text.splitlines():
        head = ANY_FUNCTION.match(line)
        if head and "=" not in line:
            where, aliases, guards = head.group("name"), {}, {}
        copy = BYTE_COPY.match(line)
        if copy:
            aliases[copy.group("name")] = copy.group("symbol")
            continue
        guard = GUARD.match(line)
        if guard:
            guards[guard.group("name")] = " ".join(guard.group("compare").split())
        call = TRIM_CALL.search(line)
        if not call:
            continue
        arg = call.group("arg")
        deref = DEREF.search(arg)
        source = deref.group("symbol") if deref else next(
            (aliases[n] for n in aliases if re.search(rf"\b{n}\b", arg)), "")
        mask = AND_MASK.search(arg)
        condition = next((c for n, c in guards.items()
                          if re.search(rf"\b{n}\b", arg)), "")
        if mask:
            value = int(mask.group("mask"), 0)
        else:
            operand = arg.strip().strip("()")
            value = number(operand)
        if value is None:
            continue
        steps.append({
            "function": where, "action": "trim", "register": "",
            "value": value, "condition": condition,
            "source": source if source in symbols else source,
        })
    return steps


def read_family(family: Path) -> tuple[dict, list[str]]:
    notes: list[str] = []
    variants = system_sources(family)
    if not variants:
        return {}, [f"{family.name}: system_ch32*.c が無い"]
    symbols = defines(find_device_header(family))

    configs: dict[str, dict] = {}
    copies: collections.Counter = collections.Counter()
    disagree: list[str] = []
    total = sum(len(paths) for _, paths in variants.values())
    for digest, (text, paths) in variants.items():
        for name, entry in read_variant(text, symbols, family.name, notes).items():
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
    # Every symbol the retained configurations name, with the register it was
    # written to, the role it played there, and its number. The address comes
    # from the header's own base-and-struct chain, because the name does not give
    # it away -- CH32V205 calls EXTEN's register CTLR0 where everyone else calls
    # it EXTEN_CTR, and CH32X315 puts the block somewhere else entirely.
    #
    # Collected from the configurations rather than across every copy, because a
    # copy this family disagrees about can name a symbol the retained version
    # does not, and a row nothing refers to would claim it is in use.
    header = find_device_header(family)
    where = extract_addresses.addresses(header) if header else {}
    remark = comments(header)
    banners = banner_registers(header)
    declared: set[str] = set()

    init: list[dict] = []
    for _, (text, _) in sorted(variants.items(), key=lambda kv: -len(kv[1][1])):
        init = read_init(text, symbols)
        if init:
            break
    # A trim step's address is where the byte lives, not a register. CH32V003
    # writes CFG0_PLL_TRIM as (VENDOR_CFG0_BASE), so it has to be followed
    # through the same base chain the register addresses use.
    chain = extract_addresses.bases(
        header.read_text(errors="ignore").splitlines()) if header else {}
    trim_field = banners.get("RCC_HSITRIM", "")
    for step in init:
        if step["action"] == "trim":
            found = chain.get(step["source"])
            step["address"] = "" if found is None else f"{found:#010x}"
            # Where the value ends up. The setter is a driver function, but the
            # field it writes is named in the header like any other.
            step["register"] = trim_field
        else:
            block, _, register = step["register"].partition("->")
            found = where.get((block, register))
            step["address"] = "" if found is None else f"{found:#010x}"
    if not init:
        notes.append(f"{family.name}: SystemInit が無い（初期化の場所が別）")

    sites: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    for config in configs.values():
        for symbol, seen in config["symbols"].items():
            sites[symbol].update(tuple(entry) for entry in seen)
    # SystemInit's own symbols. Collecting them only from the configurations left
    # the bit CH32X315 waits on out of the table while clock_init named it in a
    # poll condition -- a reference to a row that does not exist. And where a
    # trim ends up is a field like any other, but the setter is a driver
    # function, so nothing in the sources read here writes its mask.
    for step in init:
        for symbol in SYMBOL.findall(step["condition"]):
            if symbol in symbols and CLOCK_SYMBOL.match(symbol) and step["register"]:
                sites[symbol].add((step["register"], "poll"))
        if step["action"] == "trim" and step["register"]:
            sites["RCC_HSITRIM"].add((step["register"], "mask"))
            declared.add("RCC_HSITRIM")
    # The masks the code never clears. Their register is the one the field's own
    # values are written to, which the observed rows already say; a mask whose
    # field this family never touches has no register to name and is left out.
    register_of: dict[str, str] = {}
    for symbol, seen in sites.items():
        for site, _ in seen:
            register_of.setdefault(symbol, site)
    for mask in sorted(field_masks(symbols)):
        if mask in sites:
            continue
        register = next((register_of[s] for s in sorted(register_of)
                         if s.startswith(mask + "_")), banners.get(mask))
        if register:
            sites[mask].add((register, "mask"))
            declared.add(mask)
    resolved: list[dict] = []
    for symbol in sorted(sites):
        if symbol not in symbols:
            continue
        note = remark.get(symbol, "")
        disagreement = mask_disagrees(symbol, symbols[symbol], note)
        for site, role in sorted(sites[symbol]):
            block, _, register = site.partition("->")
            address = where.get((block, register))
            resolved.append({"symbol": symbol, "register": site, "role": role,
                             "address": "" if address is None else f"{address:#010x}",
                             "value": symbols[symbol],
                             "observed": symbol not in declared,
                             "disagreement": disagreement or ""})
        if disagreement:
            notes.append(f"{family.name}: {symbol} = {symbols[symbol]:#x} だが"
                         f"ヘッダ自身のコメントは {disagreement}")
        registers = {site for site, _ in sites[symbol]}
        if len(registers) > 1:
            notes.append(f"{family.name}: {symbol} が複数のレジスタに書かれる "
                         f"({', '.join(sorted(registers))})")
    return {"copies": total,
            "variants": len(variants),
            "configs": configs,
            "symbols": resolved,
            "init": init,
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
