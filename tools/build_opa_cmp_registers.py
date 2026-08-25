#!/usr/bin/env python3
"""OPA / CMP のレジスタとフィールド配置 → tables/opa_cmp_registers.csv

**コンパレータ・OPA クラスの前提**（consumer の依頼 R-26-2）。base は
`memory_map.csv`、入力 pad は `pin_roles.csv` が持っているので、足りないのは
**フィールドの配置だけ**——enable / 入力 select / 出力の読み出し bit / gain。

**block の置き方が family ごとに違い、それがこの表の要る理由です。**

    CH32X035 / L103 / V006   OPA block。CTLR1 が OPA、CTLR2 が CMP（同じ block）
    CH32M030                 OPA block の中に CMP_CTLR / CMP_STATR（QII/ISP と同居）
    CH32V205 / H417          OPA block に OPA_CFGR1 / CMP_CTLR … と名前を全部書く
    CH32V30x / V407          OPA block は CR 1本
    CH32V003                 OPA は **EXTEN_CTR の bit16-18**（block を持たない）

出所は EVT の device header——構造体（レジスタの並びとオフセット）と bit define
（`OPA_CTLR2_EN1 ((uint32_t)0x00000001)`）。**RM のレジスタ表と突き合わせ**、
bit 位置が一致すれば confirmed、RM に無ければ reference、食い違えば conflict で
両方を basis に残します。実際に食い違いがあります——CH32X035 の header は
`OPA_CTLR2_CMP_LOCK` を `0x00002000`（bit13、PSEL3 と同じ）と書きますが、RM は
bit31。header の写し間違いで、書くと **CMP3 の正入力選択を壊します**。

`purpose` は field 名の綴りから機械的に付けます（EN→enable、PSEL→positive input
select、…）。名乗っていないものは空にします——推測で埋めません。

多bit field の値の列挙（`OPA_CFGR1_BKIN_CFG_0` / `_1`）は field ではないので
載せません（親 field の bits に含まれる）。

実行:
    uv run tools/build_opa_cmp_registers.py [--mirrors <dir>] [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_addresses  # noqa: E402
import extract_registers  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MIRRORS = Path("/home/mt/dev_wch")

COLUMNS = ["family", "block", "register", "unit", "offset", "address", "field", "bits",
           "mask", "purpose", "#", "confidence", "basis"]
# RM のレジスタ見出し。`12.4.2 比较器控制寄存器（OPA_CTLR2）` の題が**どの周辺の
# レジスタか**を言う——CH32X035 は OPA block の CTLR1 が OPA、CTLR2 が CMP で、
# 名前からは分からない。
RM_HEADING = re.compile(r"^\s*\d+(?:\.\d+)+\s*(?P<title>[^（(]{2,40}?)\s*[（(]\s*"
                        r"(?P<register>(?:OPA|CMP|OPCM|EXTEN)_\w+)\s*[)）]", re.M)
UNIT_WORDS = (("比较器", "CMP"), ("CMP", "CMP"), ("运放", "OPA"), ("运算放大", "OPA"),
              ("OPA", "OPA"))

BLOCKS = ("OPA", "CMP", "OPCM", "EXTEN")
STRUCT = re.compile(r"typedef\s+struct\s*\{(?P<body>[^{}]*?)\}\s*(?P<name>\w+)_TypeDef\s*;", re.S)
MEMBER = re.compile(r"(?:__I?O?\s+|volatile\s+|const\s+)*"
                    r"u?int(?P<width>8|16|32|64)_t\s+(?P<name>\w+)"
                    r"(?:\s*\[\s*(?P<count>\d+)\s*\])?\s*;")
DEFINE = re.compile(r"^\s*#define\s+(?P<name>(?:OPA|CMP|OPCM|EXTEN)_\w+)\s+"
                    r"\(\s*\(\s*u?int\d+_t\s*\)\s*(?P<mask>0[xX][0-9A-Fa-f]+)\s*\)", re.M)
ENUM_VALUE = re.compile(r"^(?P<parent>.+)_\d+$")

# field 名が役割を名乗る綴り。順に当て、最初に当たったもの。
PURPOSE = [
    (re.compile(r"(^|_)LOCK$"), "lock"),
    (re.compile(r"KEY"), "key"),
    (re.compile(r"^FB_EN|_FB$|^FB\d*$"), "feedback enable"),
    (re.compile(r"^IE_|_IE$"), "interrupt enable"),
    (re.compile(r"^IF_|_IF$"), "interrupt flag"),
    (re.compile(r"POLL"), "polling"),
    (re.compile(r"BKIN|_BK$|^BK"), "break input"),
    (re.compile(r"RST"), "reset"),
    (re.compile(r"NMI"), "nmi"),
    (re.compile(r"PGA|GAIN"), "gain"),
    (re.compile(r"PSEL"), "positive input select"),
    (re.compile(r"NSEL"), "negative input select"),
    (re.compile(r"CHNSEL|SEL\d*$"), "input select"),
    (re.compile(r"(^|_)EN\d*$|^EN_"), "enable"),
    (re.compile(r"^MODE|_MODE"), "output mode"),
    (re.compile(r"^OUT|_OUT\d*$|OUTF|^STATR"), "output"),
    (re.compile(r"HYS"), "hysteresis"),
    (re.compile(r"FILT"), "filter"),
    (re.compile(r"TRIM"), "trim"),
    (re.compile(r"^HS$|_HS$"), "high speed"),
]


def purpose_of(field: str) -> str:
    for pattern, name in PURPOSE:
        if pattern.search(field):
            return name
    return ""


def find_header(family_dir: Path) -> Path | None:
    found = sorted(family_dir.glob("EVT/**/Peripheral/inc/ch32*.h"))
    plain = [p for p in found if re.fullmatch(r"ch32[a-z0-9]+\.h", p.name, re.IGNORECASE)]
    return plain[0] if plain else (found[0] if found else None)


def read_structs(text: str) -> dict[str, list[tuple[str, int, int]]]:
    """{block: [(member, offset, width)]}。RESERVED は飛ばす（オフセットは進める）。

    入れ子の union を持つ構造体（CH32M030 の EXTEN）は `} NAME_TypeDef;` から手前の
    `typedef struct` へ戻って本体を取り、union 以降はオフセットが一意でないので
    採らない。
    """
    out: dict[str, list[tuple[str, int, int]]] = {}
    for end in re.finditer(r"\}\s*(?P<name>" + "|".join(BLOCKS) + r")_TypeDef\s*;", text):
        start = text.rfind("typedef struct", 0, end.start())
        if start < 0:
            continue
        body = text[start:end.start()].split("union", 1)[0]
        members = []
        offset = 0
        for line in body.splitlines():
            member = MEMBER.search(line)
            if not member:
                continue
            width = int(member.group("width"))
            count = int(member.group("count") or 1)
            if not member.group("name").upper().startswith("RESERVED"):
                members.append((member.group("name"), offset, width))
            offset += width // 8 * count
        out[end.group("name")] = members
    return out


def bit_span(mask: int) -> tuple[int, int] | None:
    """連続した mask なら (lo, hi)。飛び飛びなら None。"""
    if mask == 0:
        return None
    lo = (mask & -mask).bit_length() - 1
    hi = mask.bit_length() - 1
    return (lo, hi) if mask == ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1) else None


def resolve(name: str, structs: dict) -> tuple[str, str, str] | None:
    """define 名 → (block, register, field)。決まらなければ None。"""
    # CH32M030 は OPA block の中の `CMP_CTLR` に `CMP_CTLR_EN1` と**メンバー名を
    # 頭にした** define を付ける（block 名の OPA は付かない）。メンバー名で先に当てる。
    for block, members in structs.items():
        for member, _, _ in sorted(members, key=lambda t: -len(t[0])):
            if name.startswith(member + "_") and "_" in member:
                return block, member, name[len(member) + 1:]
    for block, members in structs.items():
        if not name.startswith(block + "_"):
            continue
        rest = name[len(block) + 1:]
        # 長い名前から当てる（CTLR1 と CTLR の取り違えを避ける）。
        for member, _, _ in sorted(members, key=lambda t: -len(t[0])):
            # X035: OPA_CTLR2_EN1 → member CTLR2
            if rest.startswith(member + "_"):
                return block, member, rest[len(member) + 1:]
            # V205: OPA_CFGR1_X で member が OPA_CFGR1 と block 名を含む
            if name.startswith(member + "_"):
                return block, member, name[len(member) + 1:]
        # register が1本だけの block（V30x/V407 の CR、V003 の EXTEN_CTR）。
        # EXTEN は OPA/CMP の field だけがこの表の対象。
        if len(members) == 1 and (block != "EXTEN" or re.search(r"OPA|CMP", rest)):
            return block, members[0][0], rest
    return None


def read_manual_fields(family_dir: Path) -> tuple[dict, dict, str]:
    """RM → ({(register, field): (offset, width)}, {register: unit}, ファイル名)。"""
    paths = sorted(family_dir.glob("datasheet_zh/*RM.PDF"))
    if not paths:
        return {}, {}, ""
    fields, _ = extract_registers.extract(paths[0], None)
    out: dict = {}
    # **レジスタの持ち主は field の説明文が言う。** 見出しは `OPA控制寄存器 2
    # （OPA_CTLR2）` としか書かず、それが CMP のレジスタだと分からない。中の
    # field の説明が「使能比较器CMP1」と書いているので、説明文に出る周辺の名で
    # 数える。
    votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for f in fields:
        if re.search(r"OPA|CMP|OPCM|EXTEN", f["register"]):
            out.setdefault((f["register"], f["field"]), (f["bit_offset"], f["bit_width"]))
            # レジスタ名（OPA_CTLR2）は block を言うだけで持ち主ではないので除いて数える。
            text = re.sub(r"\b(?:OPA|CMP|OPCM)_\w+", "", f.get("description") or "")
            for word, unit in UNIT_WORDS:
                if word in text:
                    votes[f["register"]][unit] += 1
    # **見出しは使わない。** CH32X035 の RM は CMP のレジスタを `OPA控制寄存器 2
    # （OPA_CTLR2）` と呼ぶ——見出しは block を言うだけ。field の説明文の多数決
    # （「CMP3正端输入通道选择」対「OPA2正向输入端选择」）で決め、1票差以下なら決めない。
    units: dict[str, str] = {}
    for register, tally in votes.items():
        ranked = tally.most_common(2)
        if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1] + 1):
            units[register] = ranked[0][0]
    return out, units, paths[0].name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirrors", type=Path, default=MIRRORS)
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    ap.add_argument("--family", help="1 family だけ")
    args = ap.parse_args()

    with (args.out / "families.csv").open(newline="", encoding="utf-8") as f:
        families = [r["family"] for r in csv.DictReader(f)]
    if args.family:
        families = [f for f in families if f == args.family]

    rows: list[dict] = []
    notes: list[str] = []
    for family in families:
        header = find_header(args.mirrors / family)
        if header is None:
            notes.append(f"{family}: device header が無い")
            continue
        text = header.read_text(errors="ignore")
        structs = read_structs(text)
        bases = extract_addresses.bases(text.splitlines())
        defines = {m.group("name"): int(m.group("mask"), 16) for m in DEFINE.finditer(text)}
        # 値の列挙（`X_0`/`X_1` が親 `X` の mask に収まる）は field ではない。
        names = set(defines)
        fields = {}
        for name, mask in defines.items():
            parent = ENUM_VALUE.match(name)
            if parent and parent.group("parent") in names \
                    and defines[parent.group("parent")] & mask == mask \
                    and defines[parent.group("parent")] != mask:
                continue
            resolved = resolve(name, structs)
            if resolved:
                fields[name] = (resolved, mask)
        if not fields:
            notes.append(f"{family}: OPA/CMP の bit define が無い"
                         + ("（構造体はある）" if any(b in structs for b in ("OPA", "CMP")) else ""))
            continue
        manual, units, manual_name = read_manual_fields(args.mirrors / family)
        offsets = {(b, m): (o, w) for b, ms in structs.items() for m, o, w in ms}
        for name, ((block, register, field), mask) in sorted(fields.items(),
                                                             key=lambda kv: (kv[1][0], kv[1][1])):
            offset, _width = offsets[(block, register)]
            base = bases.get(f"{block}_BASE")
            span = bit_span(mask)
            bits = ("" if span is None else
                    f"{span[0]}" if span[0] == span[1] else f"{span[1]}:{span[0]}")
            confidence, basis = "reference", [f"evt({header.name})"]
            # RM 側の名前: レジスタは `OPA_CTLR1` のように block を頭に付ける。
            candidates = [register, f"{block}_{register}"]
            said = next((manual[(r, field)] for r in candidates if (r, field) in manual), None)
            if said and span is not None:
                lo, width = said
                if (lo, lo + width - 1) == span:
                    confidence = "confirmed"
                    basis.append(f"rm({manual_name})")
                else:
                    confidence = "conflict"
                    hi = lo + width - 1
                    basis.append(f"!rm({manual_name})(={hi}:{lo})" if hi != lo
                                 else f"!rm({manual_name})(={lo})")
            # 持ち主: RM の見出し。無ければレジスタ名の綴り（M030 の CMP_CTLR、
            # V205 の OPA_CFGR1）、それも無ければ空——推測しない。
            unit = next((units[r] for r in candidates if r in units), "")
            if not unit:
                unit = "CMP" if register.startswith("CMP") else \
                       "OPA" if register.startswith("OPA") else ""
            if not unit and not any(r in units for r in
                                    (f"{block}_{m}" for m, _, _ in structs.get(block, []))) \
                    and block == "OPA":
                # RM がこの block の field を1つも書いていない（CH32V30x/V407 の CR、
                # CH32H417）。名前で分かる CMP_* 以外は OPA block の OPA レジスタ。
                unit = "OPA"
            rows.append({
                "family": family,
                "block": block,
                "register": register,
                "unit": unit,
                "offset": f"{offset:#04x}",
                "address": f"{base + offset:#010x}" if base is not None else "",
                "field": field,
                "bits": bits,
                "mask": f"{mask:#x}",
                "purpose": purpose_of(field),
                "confidence": confidence,
                "basis": "+".join(basis),
            })

    dest = args.out / "opa_cmp_registers.csv"
    if args.family and dest.exists():
        # 1 family だけ回したときは他 family の行を残す（全 RM を読み直すと長い）。
        with dest.open(newline="", encoding="utf-8") as f:
            kept = [r for r in csv.DictReader(f) if r["family"] != args.family]
        rows = [{k: r.get(k, "") for k in COLUMNS if k != "#"} for r in kept] + rows
        rows.sort(key=lambda r: (r["family"], r["block"], r["register"], r["field"]))
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)
    tally = collections.Counter(r["confidence"] for r in rows)
    print(f"{dest}: {len(rows)} 行  family {len({r['family'] for r in rows})}  {dict(tally)}",
          file=sys.stderr)
    for note in dict.fromkeys(notes):
        print(f"  - {note}", file=sys.stderr)
    conflicts = [r for r in rows if r["confidence"] == "conflict"]
    for r in conflicts[:10]:
        print(f"  ! {r['family']} {r['register']}.{r['field']} header={r['bits']} {r['basis']}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
