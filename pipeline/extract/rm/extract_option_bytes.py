#!/usr/bin/env python3
"""RMのoption bytes章 → evidence/option_bytes.csv・option_byte_fields.csv（R-30）。

ch32rvの依頼0003（`target option get/set`・`recover unbrick`）が要るのは
**書き込みレイアウト**（各バイトの意味・補数バイトの配置・書込単位）と
**工場出荷値**。全11 RMのoption bytes章は同じ2つの材料を持つ（2026-09-01に
全RMで実測）:

1. **「用户选择字信息结构 / User option byte(s) information structure」表**——
   32bit語のアドレス×バイト配置のgrid（`0x1FFFF800: nUSER USER nRDPR RDPR`）。
   ここから1バイト1行のレイアウト（offset・補数の位置）を起こす
2. **直後の無caption表**（`名称/字节 / Name/Byte`）——USER等のbit割当と
   **復位値**（=工場出荷値のRM記載）。ページを跨ぐのでL1結合で読む

工場出荷値はRMが述べる粒度（バイト/ビット単位の復位値）のまま残す——
生バイト列への合成は導出なのでしない（依頼書の表2はconsumer側で合成できる）。
書込単位は編程節の散文（zh「一次写入半字…反码」／en「half word…complement/
inverse」）から`half-word`を確認して全行に書く（見つからなければ落ちる）。

- RM→familyは`catalog/documents.csv`の`repositories`（FV2x_V3xのみ2 family）
- zh/enの両版が一致した行だけconfirmed。片版のみ（V407RMはzh単独）はreference、
  食い違いはconflictで両論をbasisへ
- 識別子・値は空白（改行含む）だけ畳んで資料どおりに残す

実行:
    uv run pipeline/extract/rm/extract_option_bytes.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "pipeline" / "common"))

import logical_tables  # noqa: E402
import paths  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"

BYTE_COLUMNS = ["family", "address", "offset", "byte", "complement_address",
                "write_unit", "#", "confidence", "basis"]
FIELD_COLUMNS = ["family", "byte", "bits", "field", "default",
                 "wrpr_bit_protects", "#", "confidence", "basis"]

STRUCTURE_CAPTION = re.compile(r"用户选择字信息结构|User option bytes? information structure")
FIELDS_HEADER = re.compile(r"^(?:名称/字节|Name/Byte)$", re.IGNORECASE)
BIT_RANGE = re.compile(r"^\[(\d+):(\d+)\]$")
ADDRESS = re.compile(r"^0x[0-9A-Fa-f]+$")

# 「用户选择字编程」節の見出しと、書込方式の分類。方式はfamilyで違う——
# V003系はOBPGで半字書込、L103/M030系はFTPG（快速頁編程・32bitずつ緩存へ）。
# 判定は手順が名指す制御bit（OBPG／FTPG）で行い、節の本文（見出しページ＋
# 次ページ）にちょうど1つ当たらなければ落ちる。「高字节为低字节的反码」の
# 自動補数の文は独立の事実として拾う（M030はFTPG手順と自動補数の文を両方持つ）。
OB_PROGRAM_HEADING = {
    "zh": re.compile(r"用户选择字编程"),
    "en": re.compile(r"User option bytes? programming", re.IGNORECASE),
}
UNIT_PATTERNS: list[tuple[str, re.Pattern]] = [
    # \bは使わない——Pythonの\wはUnicode既定で漢字も語になり「的OBPG位」に効かない
    ("half-word (OBPG)", re.compile(r"OBPG")),
    ("fast page, 32-bit buffer writes (FTPG)", re.compile(r"FTPG")),
]
COMPLEMENT_AUTO = {
    "zh": re.compile(r"自动计算出高字节"),
    "en": re.compile(r"automatically calculates? the high byte", re.IGNORECASE),
}

# WRPRの粒度（1bitが保護する範囲）。WRPR群の説明文（空白を全部除いた形）から
# 取る。書き方は3種で全RMを覆う（2026-09-02実測）——(1) DBMODEで扇区サイズが
# 変わる（H417とX315 en）、(2) N個扇区×サイズ、(3) 扇区を言わずKバイトだけ
# （M030・CH32xRM）。どれにも当たらなければ生成が落ちる。
WRPR_DBMODE = re.compile(
    r"(\d+)(?:个扇区|sectors?)[（(](?:当|When)DBMODE=1[时]?[:：](\d+)K[^;；]*"
    r"[;；](?:当|When)DBMODE=0[时]?[:：](\d+)K", re.IGNORECASE)
WRPR_SECTORS = {
    "zh": re.compile(r"(\d+)个扇区[（(](\d+)K字节/扇区[)）]"),
    "en": re.compile(r"(\d+)sectors?\((\d+)Kbytes?/sector\)", re.IGNORECASE),
}
WRPR_PLAIN = {
    "zh": re.compile(r"(\d+)K字节的写保护状态"),
    "en": re.compile(r"(\d+)Kbytesinthemainmemory", re.IGNORECASE),
}


def wrpr_granularity(desc: str, lang: str) -> str:
    m = WRPR_DBMODE.search(desc)
    if m:
        return (f"{m.group(1)} sector ({m.group(2)}KB/sector when DBMODE=1, "
                f"{m.group(3)}KB/sector when DBMODE=0)")
    m = WRPR_SECTORS[lang].search(desc)
    if m:
        return f"{m.group(1)} sector ({m.group(2)}KB/sector)"
    m = WRPR_PLAIN[lang].search(desc)
    if m:
        return f"{m.group(1)}KB"
    raise SystemExit(f"WRPRの粒度が説明文から読めない（{lang}）: {desc[:120]!r}")


def squeeze(cell) -> str:
    """空白（改行含む）を全部除き、dashを`-`に畳む。識別子の折り返し
    （START_M\\nODE）とzh/enの空白差（WRPR0 - WRPR3）・dash差（Data0–Data1）を
    同じ綴りにする。"""
    if not cell:
        return ""
    return re.sub(r"\s+", "", str(cell)).replace("–", "-").replace("—", "-")


# 復位値の「値のトークン」。セルには説明の句点が漂着したり（`1\n。`・`0xA5）`）、
# chip別の値が散文で書かれたり（zh「CH32V007/CH32M007芯片复位值:11b;其他…10b」
# ／enは同内容の英語）する。**述べている値の列**が一致すれば同じ主張とみなし、
# 食い違いのdissentにも（中国語の散文ではなく）このトークン列を書く。
VALUE_TOKEN = re.compile(r"0x[0-9A-Fa-f]+|\b[0-9A-Fa-f]+h\b|\b[01x]+b\b"
                         r"|\b\d+\b|\b[xX]+\b")


def default_key(value: str) -> str:
    return "/".join(VALUE_TOKEN.findall(value))


def load_pages(name: str) -> list[dict]:
    bundle = BUNDLES / name
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    pages = []
    for entry in manifest["pages"]:
        payload = (bundle / entry["file"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{bundle}/{entry['file']}: page hash differs from manifest")
        pages.append(json.loads(payload))
    return pages


def rm_documents() -> list[dict]:
    out = []
    with (REPO / "catalog" / "documents.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["kind"] != "reference-manual" or row["status"] != "assigned":
                continue
            out.append({"document": row["document"],
                        "families": [r for r in row["repositories"].split(";") if r],
                        "langs": [lang for lang in ("zh", "en")
                                  if row[f"version_{lang}"]]})
    return out


def find_grids(pages: list[dict]) -> tuple[tuple, tuple]:
    """(structure, fields)の(grid, row_pages)。無ければ落ちる。"""
    chains = logical_tables.document_chains(pages)
    structure = fields = None
    for page in pages:
        for t in page["tables"]:
            info = chains[t["id"]]
            if not info["start"]:
                continue
            caption = ((t.get("caption") or {}).get("text") or "")
            merged = info["merged"] or logical_tables.merge_cells([(page["number"], t)])
            grid, row_pages = logical_tables.text_grid(merged)
            if structure is None and STRUCTURE_CAPTION.search(caption):
                structure = (grid, row_pages)
            elif grid and grid[0] and FIELDS_HEADER.match(squeeze(grid[0][0])):
                fields = (grid, row_pages)
    if structure is None or fields is None:
        raise SystemExit("option bytesの表が見つからない（structure="
                         f"{structure is not None}, fields={fields is not None}）")
    return structure, fields


def parse_structure(grid: list[list], row_pages: list[int]) -> list[dict]:
    """アドレス×バイト配置 → 1バイト1行（補数はvalue行の列に畳む）。"""
    header = [squeeze(c) for c in grid[0]]
    col_offset: dict[int, int] = {}
    for ci, h in enumerate(header):
        m = BIT_RANGE.match(h)
        if m:
            col_offset[ci] = int(m.group(2)) // 8
    if sorted(col_offset.values()) != [0, 1, 2, 3]:
        raise SystemExit(f"structure表のbit列が読めない: {header}")

    entries: list[dict] = []
    for cells, page in zip(grid[1:], row_pages[1:]):
        addr_text = squeeze(cells[0])
        if not ADDRESS.match(addr_text):
            raise SystemExit(f"structure表のアドレスが読めない: {cells!r}")
        word = int(addr_text, 16)
        byte_at = {off: squeeze(cells[ci]) for ci, off in col_offset.items()}
        for low in (0, 2):
            value, comp = byte_at.get(low, ""), byte_at.get(low + 1, "")
            if value and comp == f"n{value}":
                entries.append({"address": word + low, "byte": value,
                                "complement_address": word + low + 1, "page": page})
            else:  # 対を成さない（Reserved等）——見えたとおり独立の行に
                for off, name in ((low, value), (low + 1, comp)):
                    if name:
                        entries.append({"address": word + off, "byte": name,
                                        "complement_address": None, "page": page})
    return entries


def parse_fields(grid: list[list], row_pages: list[int]) -> list[dict]:
    """bit割当表 → byte群・bits・field・復位値。説明の折り返し行は読み飛ばす
    （ただし説明の本文は`desc`へ連結して保つ——WRPRの粒度がそこに書いてある）。"""
    if len(grid[0]) != 5:
        raise SystemExit(f"bit割当表の列数が想定外: {len(grid[0])}")
    out: list[dict] = []
    current = None
    for cells, page in zip(grid[1:], row_pages[1:]):
        name, bits, field = squeeze(cells[0]), squeeze(cells[1]), squeeze(cells[2])
        default = squeeze(cells[-1])
        desc = squeeze(cells[3])
        if not name and not bits and out:
            out[-1]["desc"] += desc
            if field and not default and out[-1]["bits"]:
                # ページ跨ぎで識別子が行ごと割れた続き（M030 enの STANDYR + ST）
                out[-1]["field"] += field
                continue
            if default and not field:
                # 復位値がページ跨ぎで割れた続き（V00X zhの
                # CH32V007/CH32M007芯 ＋ 片复位值：11b；…10b）
                out[-1]["default"] += default
                continue
        if name:
            current = name
            if not bits and not field:   # byte群ぐるみの行（RDPR・Data・WRPR）
                out.append({"byte": current, "bits": "", "field": "",
                            "default": default, "desc": desc, "page": page})
                continue
        if not bits and not field:       # 説明の折り返し（descは上で連結済み）
            continue
        if current is None:
            raise SystemExit(f"bit割当表がbyte名より先にbit行を持つ: {cells!r}")
        out.append({"byte": current, "bits": bits, "field": field,
                    "default": default, "desc": desc, "page": page})
    return out


def read_edition(document: str, lang: str) -> dict:
    name = f"{Path(document).stem}.{lang}"
    pages = load_pages(name)
    (s_grid, s_pages), (f_grid, f_pages) = find_grids(pages)
    joined = {p["number"]: " ".join(line["text"] for line in p["lines"])
              for p in pages}
    anchor = s_pages[0]
    heading_page = next((n for n in sorted(joined)
                         if n >= anchor and OB_PROGRAM_HEADING[lang].search(joined[n])),
                        None)
    if heading_page is None:
        raise SystemExit(f"{name}: 用户选择字编程の節が見つからない")
    window = joined[heading_page] + " " + joined.get(heading_page + 1, "")
    units = [unit for unit, pattern in UNIT_PATTERNS if pattern.search(window)]
    if len(units) != 1:
        raise SystemExit(f"{name}: 書込方式を1つに決められない（p.{heading_page}, "
                         f"当たった方式={units!r}）——UNIT_PATTERNSを見直すこと")
    write_unit = units[0]
    if COMPLEMENT_AUTO[lang].search(window):
        write_unit += "; complement auto-computed"
    fields = parse_fields(f_grid, f_pages)
    for row in fields:
        row["wrpr_bit_protects"] = (wrpr_granularity(row["desc"], lang)
                                    if row["byte"].startswith("WRPR") else "")
    entries = parse_structure(s_grid, s_pages)
    # 表内の相対offset。**zh/enの照合はこのoffsetで対にする**——base番地そのものが
    # 版間で食い違うことがある（M030: zh 0x1FFFF300 / en 0x1FFFF800）
    base = min(e["address"] for e in entries)
    for e in entries:
        e["offset"] = e["address"] - base
        e["complement_offset"] = (e["complement_address"] - base
                                  if e["complement_address"] else None)
    return {"bytes": entries, "fields": fields,
            "write_unit": write_unit, "write_page": heading_page}


def merge(document: str, editions: dict[str, dict], kind: str,
          key_of, value_of, extra_pages: dict[str, int] | None = None,
          prefer=None) -> list[dict]:
    """zh/enを突き合わせ、confirmed/reference/conflictの行にする。

    ``extra_pages``は表のページに加えてbasisへ載せるページ（書込方式の節）。
    ``prefer``は食い違ったときにどちらの版を採るか（``(z, e) -> "zh"|"en"``。
    既定はen。もう片方は`!`の異議としてbasisへ）。
    """
    keyed = {lang: {key_of(e): e for e in editions[lang][kind]}
             for lang in editions}
    tail = {lang: (f",p.{extra_pages[lang]}" if extra_pages else "")
            for lang in editions}
    ordered: list = []
    for lang in ("en", "zh"):     # 出力はRMの記載順（en優先、片版のみはzh順）
        for key in keyed.get(lang, {}):
            if key not in ordered:
                ordered.append(key)
    rows = []
    for key in ordered:
        z = keyed.get("zh", {}).get(key)
        e = keyed.get("en", {}).get(key)
        record = e or z
        if z and e and value_of(z) == value_of(e):
            confidence = "confirmed"
            basis = (f"{document}:zh(p.{z['page']}{tail['zh']})"
                     f"+{document}:en(p.{e['page']}{tail['en']})")
        elif z and e:
            confidence = "conflict"
            side = prefer(z, e) if prefer else "en"
            record = e if side == "en" else z
            other, other_lang = ((z, "zh") if side == "en" else (e, "en"))
            diff = ",".join(f"{k}={v}" for k, v in value_of(other).items()
                            if value_of(record).get(k) != v)
            basis = (f"{document}:{side}(p.{record['page']}{tail[side]})"
                     f"+!{document}:{other_lang}({diff})")
        else:
            lang = "zh" if z else "en"
            confidence = "reference"
            basis = f"{document}:{lang}(p.{record['page']}{tail[lang]})"
        rows.append({**record, "confidence": confidence, "basis": basis})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    args = ap.parse_args()

    ob_bases = {r["family"]: int(r["base_address"], 16)
                for r in paths.load("register_blocks") if r["block"] == "OB"}
    byte_rows: list[dict] = []
    field_rows: list[dict] = []
    for rm in rm_documents():
        editions = {lang: read_edition(rm["document"], lang) for lang in rm["langs"]}

        units = {edition["write_unit"] for edition in editions.values()}
        if len(units) != 1:
            raise SystemExit(f"{rm['document']}: zh/enで書込方式が食い違う {units!r}")
        write_unit = units.pop()

        # base番地が版間で食い違ったら、EVTヘッダ（register_blocksのOB block）が
        # 支持する側を採る——第三の証拠による裁定（debug_interfacesのV002/V004と
        # 同じ型）。どちらでもなければ既定（en）。
        evt_bases = {ob_bases[f] for f in rm["families"] if f in ob_bases}
        evt_base = evt_bases.pop() if len(evt_bases) == 1 else None

        def prefer_evt(z: dict, e: dict) -> str:
            zb, eb = (z["address"] - z["offset"]), (e["address"] - e["offset"])
            if evt_base is not None and zb == evt_base and eb != evt_base:
                return "zh"
            return "en"

        merged_bytes = merge(
            rm["document"], editions, "bytes",
            key_of=lambda e: (e["offset"],),
            value_of=lambda e: {"byte": e["byte"],
                                "complement_offset": e["complement_offset"],
                                "address": f"0x{e['address']:08X}"},
            extra_pages={lang: editions[lang]["write_page"] for lang in editions},
            prefer=prefer_evt)
        merged_fields = merge(
            rm["document"], editions, "fields",
            key_of=lambda e: (e["byte"], e["bits"]),
            value_of=lambda e: {"field": e["field"],
                                "default": default_key(e["default"]),
                                "wrpr_bit_protects": e["wrpr_bit_protects"]})

        for family in rm["families"]:
            for e in merged_bytes:
                byte_rows.append({
                    "family": family,
                    "address": f"0x{e['address']:08X}",
                    "offset": f"0x{e['offset']:02X}",
                    "byte": e["byte"],
                    "complement_address": (f"0x{e['complement_address']:08X}"
                                           if e["complement_address"] else ""),
                    "write_unit": write_unit,
                    "confidence": e["confidence"], "basis": e["basis"]})
            for e in merged_fields:
                field_rows.append({
                    "family": family, "byte": e["byte"], "bits": e["bits"],
                    "field": e["field"],
                    # 散文の復位値（zh単独版）は値トークン列に畳む——公開列に
                    # 中国語を入れない。ASCIIならセルの綴りのまま
                    "default": (e["default"] if e["default"].isascii()
                                else default_key(e["default"])),
                    "wrpr_bit_protects": e["wrpr_bit_protects"],
                    "confidence": e["confidence"], "basis": e["basis"]})

    byte_rows.sort(key=lambda r: (r["family"], r["address"]))
    field_rows.sort(key=lambda r: (r["family"],))  # 表の並びはRMの記載順を保つ

    from collections import Counter  # noqa: PLC0415
    for table, columns, rows in (("option_bytes", BYTE_COLUMNS, byte_rows),
                                 ("option_byte_fields", FIELD_COLUMNS, field_rows)):
        dest = paths.table(table, args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columns)
            w.writeheader()
            w.writerows({**{c: r.get(c, "") for c in columns}, "#": "#"}
                        for r in rows)
        print(f"{dest}: {len(rows)} 行 "
              f"{dict(Counter(r['confidence'] for r in rows))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
