#!/usr/bin/env python3
"""Resolve `BLOCK->REGISTER` to an absolute address from an EVT device header.

The EVT sources reach a register through a struct pointer:

    #define PERIPH_BASE     ((uint32_t)0x40000000)
    #define HBPERIPH_BASE   (PERIPH_BASE + 0x20000)
    #define EXTEN_BASE      (HBPERIPH_BASE + 0x3800)
    #define EXTEN           ((EXTEN_TypeDef *)EXTEN_BASE)
    typedef struct { __IO uint32_t EXTEN_CTR; } EXTEN_TypeDef;

so `EXTEN->EXTEN_CTR` is 0x40023800. Nothing in the name says that, and the
name is not even stable: CH32V205 calls the same register EXTEN->CTLR0, and
CH32X315 puts EXTEN at 0x400220C0 rather than at BASE+0x3800 like the rest. So
the address has to be read, not guessed.

Three things the header does that a naive parser gets wrong:

**The base is a chain.** EXTEN_BASE is written relative to HBPERIPH_BASE, which
is written relative to PERIPH_BASE. Some headers spell the middle one
AHBPERIPH_BASE, and CH32V003 and CH32X315 skip the chain and write the literal.

**Struct members are not all one word.** CH32V205's EXTEN_TypeDef ends in a
uint16_t, and reserved gaps are written as arrays.

**A register's offset is its position, not its index.** Anything before it
counts, including the reserved arrays.

Usage:
    uv run tools/extract_addresses.py <device-header.h> [BLOCK->REGISTER ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# `#define NAME ((uint32_t)0x40000000)` and `#define NAME (OTHER + 0x1000)`.
LITERAL = re.compile(r"^#define\s+(\w+)\s+\(\(u?int32_t\)\s*(0x[0-9A-Fa-f]+|\d+)\s*\)")
RELATIVE = re.compile(r"^#define\s+(\w+)\s+\(\s*(\w+)\s*(?:\+\s*(0x[0-9A-Fa-f]+|\d+)\s*)?\)")
# `#define EXTEN ((EXTEN_TypeDef *)EXTEN_BASE)`
POINTER = re.compile(r"^#define\s+(\w+)\s+\(\(\s*(\w+)\s*\*\s*\)\s*(\w+)\s*\)")
STRUCT_END = re.compile(r"^\}\s*(\w+)\s*;")
MEMBER = re.compile(r"^(?:__I?O?\s+|volatile\s+|const\s+)*"
                    r"u?int(?P<width>8|16|32|64)_t\s+(?P<name>\w+)"
                    r"(?:\s*\[\s*(?P<count>\d+)\s*\])?\s*;")


def number(text: str) -> int:
    return int(text, 16) if text.lower().startswith("0x") else int(text, 10)


def bases(lines: list[str]) -> dict[str, int]:
    """Every `*_BASE`-style constant, following the relative chain to a number."""
    literal: dict[str, int] = {}
    relative: dict[str, tuple[str, int]] = {}
    for line in lines:
        line = line.strip()
        m = LITERAL.match(line)
        if m:
            literal.setdefault(m.group(1), number(m.group(2)))
            continue
        m = RELATIVE.match(line)
        if m and m.group(2) not in ("uint32_t", "int32_t"):
            relative.setdefault(m.group(1),
                                (m.group(2), number(m.group(3) or "0")))

    resolved = dict(literal)

    def value(name: str, seen: frozenset[str] = frozenset()) -> int | None:
        if name in resolved:
            return resolved[name]
        if name in seen or name not in relative:
            return None
        parent, offset = relative[name]
        base = value(parent, seen | {name})
        if base is None:
            return None
        resolved[name] = base + offset
        return resolved[name]

    for name in relative:
        value(name)
    return resolved


def structs(lines: list[str]) -> dict[str, dict[str, int]]:
    """Member byte offsets for each `*_TypeDef`, counting reserved arrays."""
    out: dict[str, dict[str, int]] = {}
    members: dict[str, int] = {}
    offset = 0
    for line in lines:
        line = line.strip()
        end = STRUCT_END.match(line)
        if end:
            if members:
                out[end.group(1)] = members
            members, offset = {}, 0
            continue
        if line.startswith("typedef struct"):
            members, offset = {}, 0
            continue
        m = MEMBER.match(line)
        if m:
            members[m.group("name")] = offset
            offset += int(m.group("width")) // 8 * int(m.group("count") or 1)
    return out


def addresses(header: Path) -> dict[tuple[str, str], int]:
    """{(block, register): absolute address} for every struct pointer define."""
    lines = header.read_text(errors="ignore").splitlines()
    base_of = bases(lines)
    layout = structs(lines)
    out: dict[tuple[str, str], int] = {}
    for line in lines:
        m = POINTER.match(line.strip())
        if not m:
            continue
        block, typedef, base_name = m.groups()
        base = base_of.get(base_name)
        if base is None or typedef not in layout:
            continue
        for member, offset in layout[typedef].items():
            out.setdefault((block, member), base + offset)
    return out


def main() -> int:
    header = Path(sys.argv[1])
    table = addresses(header)
    wanted = sys.argv[2:]
    if wanted:
        for spec in wanted:
            block, _, register = spec.partition("->")
            found = table.get((block, register))
            print(f"{spec:28} {found:#010x}" if found is not None
                  else f"{spec:28} 見つからない")
        return 0
    for (block, register), address in sorted(table.items()):
        print(f"{block}->{register:16} {address:#010x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
