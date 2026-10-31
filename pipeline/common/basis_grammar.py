"""`basis` 列の文法（公開面の全表で同じ）。

    basis   := term ("+" term)*                  項は括弧の外の `+` で区切る
    term    := [mark] source [dissent]
    mark    := "!"   採った値と食い違う出所（dissent が必ず付く）
             | "?"   当てはめきれなかった照合（食い違いではない）
    source  := [kind ":"] document [":" lang] ["(" locator ")"]
             | kind [":" label] ["(" detail ")"]
    document:= 資料の名前（`catalog/documents.csv` の `document`。`.PDF` で終わる）に、過去の版を指すなら `@V<版>`
    lang    := "zh" | "en"
    locator := "p." <PDF の通しページ番号> [";" detail]   （preview の `<文書>.<言語>/pages/<NNNN>.md` と同じ数）
             | detail
    dissent := "(" column "=" value ("," column "=" value)* ")"
               その出所が言う値を、食い違う列の名前つきで（`!CH32V007DS0.PDF:zh(max=115)`）
    kind    := 出所の種類（`KINDS`）。小文字とハイフン

括弧は対になっていること。`detail` と `value` には括弧を含めてよい（対になっていれば）。

>>> parse("CH32V407DS0.PDF:zh(p.59)+!CH32V407DS0.PDF:en(max=115)")[1]["dissent"]
{'max': '115'}
>>> parse("rm:CH32FV2x_V3xRM.PDF:en(p.608)")[0]["page"]
608
>>> parse("candidates(datasheet-pin-table+rm-remap-grid:en+zh)")[0]["detail"]
'datasheet-pin-table+rm-remap-grid:en+zh'
>>> problems("rm(CH32H417RM.PDF)")
['文書は kind(...) の中ではなく kind:文書 で書く: rm(CH32H417RM.PDF)']
>>> problems("!CH32H417RM.PDF:en(=RW1)")
['! の項に (列=値) が無い: !CH32H417RM.PDF:en(=RW1)']
"""

from __future__ import annotations

import re

# 出所の種類。新しい種類を使う生成器はここに足す（検査が知らない種類で落ちる）。
KINDS = {
    # 資料の読み方（文書を伴う）
    "rm": "a reference manual's text or tables",
    "ds": "a datasheet's notes",
    "rm-address": "the absolute-address table at the head of a reference-manual chapter",
    "rm-remap-grid": "a reference manual's remap grid",
    "rm-enable": "the enable bit a reference manual names",
    "rm-register": "a reference manual's register table",
    "rm-dbmode": "a reference manual's DBMODE-dependent sector size",
    "rm-en": "the English reference manual only",
    "rm-pgerr": "the programming-error value a reference manual states",
    "unit": "the unit a document states",
    "features": "a datasheet's feature section headings",
    "resource-scope": "a datasheet's statement of which resources a part lacks",
    # 表や章の名前で言う出所（言語つき）
    "pin-table": "a datasheet pin table", "products": "a datasheet comparison table",
    "ordering": "a datasheet ordering-information table", "package-pdf": "WCH's package drawing PDF",
    "memorymap": "a datasheet memory map", "manual": "a QingKe processor manual or a named section",
    # EVT
    "evt": "WCH's EVT package (headers, sources)", "evt-api": "an EVT flash API source file",
    "evt-iap": "an EVT IAP example", "evt-bufload": "the EVT buffer-load width",
    "evt-erase": "the EVT erase routine", "evt-comment": "an EVT source comment",
    "device-header": "the EVT device header",
    # 機械の組み立て・規則
    "candidates": "the per-part candidate extraction (which sources agreed)",
    "attributes": "comparison-table attributes", "rule": "a stated derivation rule",
    "searched": "the documents searched without finding the fact",
    # 実測・配布物
    "measured": "a dated measurement record", "silicon": "read from silicon",
    "hartinfo": "the debug module's hartinfo read from silicon", "device-id": "a chip ID read from silicon",
    "flash": "an erase/program/readback on silicon", "obr-readback": "option bytes read back from silicon",
    "wch": "a file WCH distributes", "inferred": "inferred from a stated structure (the row is reference)",
    # 目録の運用の表（公開しない）
    "git": "a mirror repository's commit", "api": "an upstream download API", "head": "an HTTP HEAD of the file",
}
LANGS = {"zh", "en"}
MARK = re.compile(r"^[!?]")
KIND = re.compile(r"^[a-z][a-z0-9-]*$")
DOCUMENT = re.compile(r"^(?P<document>[A-Za-z0-9_.-]+\.PDF)(?:@V(?P<version>[0-9.]+))?$")
LOCATOR_PAGE = re.compile(r"^p\.(?P<page>\d+)(?:;(?P<detail>.*))?$", re.S)
PAIR = re.compile(r"^(?P<column>[a-z][a-z0-9_]*)=(?P<value>.*)$", re.S)


def split_top(text: str, sep: str) -> list[str]:
    """括弧の外の `sep` で切る。"""
    out, depth, start = [], 0, 0
    for i, c in enumerate(text):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == sep and depth == 0:
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return out


def balanced(text: str) -> bool:
    depth = 0
    for c in text:
        depth += (c == "(") - (c == ")")
        if depth < 0:
            return False
    return depth == 0


def groups(text: str) -> tuple[str, list[str]]:
    """`head(g1)(g2)` → (`head`, [`g1`, `g2`])。括弧は対になっている前提。"""
    at = text.find("(")
    if at < 0:
        return text, []
    head, rest, out = text[:at], text[at:], []
    while rest:
        if rest[0] != "(":
            raise ValueError(f"括弧のあとに文字がある: {text}")
        depth = 0
        for i, c in enumerate(rest):
            depth += (c == "(") - (c == ")")
            if depth == 0:
                out.append(rest[1:i])
                rest = rest[i + 1:]
                break
    return head, out


def parse_dissent(group: str) -> dict[str, str] | None:
    """`列=値,列=値`。値に `,` が入ってよい——次の `列=` の前の `,` だけが区切り。

    >>> parse_dissent("value=General purpose, pin-compatible")
    {'value': 'General purpose, pin-compatible'}
    >>> parse_dissent("address=0x1FFFF800,width_bits=32")
    {'address': '0x1FFFF800', 'width_bits': '32'}
    """
    pairs: dict[str, str] = {}
    last = None
    for part in split_top(group, ","):
        m = PAIR.match(part.strip())
        if m and m["column"] not in pairs:
            last = m["column"]
            pairs[last] = m["value"]
        elif last is not None:
            pairs[last] += "," + part
        else:
            return None
    return pairs


def parse_term(term: str) -> dict:
    mark = term[0] if MARK.match(term) else ""
    body = term[len(mark):]
    head, parens = groups(body)
    out = {"term": term, "mark": mark, "kind": "", "label": "", "document": "", "version": "",
           "lang": "", "page": None, "detail": "", "dissent": None}
    if mark == "!" and parens and (pairs := parse_dissent(parens[-1])) is not None:
        out["dissent"] = pairs
        parens = parens[:-1]
    if len(parens) > 1:
        raise ValueError(f"括弧の組が多すぎる: {term}")
    segments = head.split(":")
    if (doc := next((i for i, s in enumerate(segments) if DOCUMENT.match(s)), None)) is not None:
        before, after = segments[:doc], segments[doc + 1:]
        if len(before) > 1 or len(after) > 1:
            raise ValueError(f"文書の前後の区切りが多い: {term}")
        out["kind"] = before[0] if before else ""
        m = DOCUMENT.match(segments[doc])
        out["document"], out["version"] = m["document"], m["version"] or ""
        out["lang"] = after[0] if after else ""
        if parens:
            m = LOCATOR_PAGE.match(parens[0])
            if m:
                out["page"], out["detail"] = int(m["page"]), m["detail"] or ""
            else:
                out["detail"] = parens[0]
        return out
    if len(segments) > 2:
        raise ValueError(f"kind:label の区切りが多い: {term}")
    out["kind"] = segments[0]
    out["label"] = segments[1] if len(segments) > 1 else ""
    out["detail"] = parens[0] if parens else ""
    return out


def parse(basis: str) -> list[dict]:
    return [parse_term(t) for t in split_top(basis, "+")] if basis else []


def problems(basis: str, documents: set[str] | None = None) -> list[str]:
    """文法に外れる所の説明（空なら文法どおり）。`documents` を渡せば文書名も目録と照らす。"""
    if not basis:
        return []
    if not balanced(basis):
        return [f"括弧が対になっていない: {basis}"]
    out = []
    for term in split_top(basis, "+"):
        if not term:
            out.append(f"空の項がある: {basis}")
            continue
        try:
            t = parse_term(term)
        except ValueError as e:
            out.append(str(e))
            continue
        if t["kind"] and not KIND.match(t["kind"]):
            out.append(f"kind の綴りが小文字・ハイフンでない: {term}")
        elif t["kind"] and t["kind"] not in KINDS:
            out.append(f"知らない kind {t['kind']!r}（basis_grammar.KINDS に足す）: {term}")
        if not t["kind"] and not t["document"]:
            out.append(f"kind も文書も無い: {term}")
        if t["document"]:
            if t["lang"] and t["lang"] not in LANGS:
                out.append(f"言語は zh か en: {term}")
            if documents is not None and t["document"] not in documents:
                out.append(f"目録に無い文書 {t['document']}: {term}")
        elif DOCUMENT.match(t["detail"].split(":")[0].split(" ")[0] or "-"):
            out.append(f"文書は kind(...) の中ではなく kind:文書 で書く: {term}")
        if t["mark"] == "!" and not t["dissent"]:
            out.append(f"! の項に (列=値) が無い: {term}")
    return out
