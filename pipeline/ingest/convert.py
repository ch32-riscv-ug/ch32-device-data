#!/usr/bin/env python3
"""PDF全ページ → 構造化bundle（本番converter。D18工程1）。

PoCの`tools/document_converter.py`を出発点に、D17の調査
（docs/structured-migration-survey.ja.md）が特定した2つの欠陥を直したもの。

1. **決定性**——pdfminerはinline imageに`id()`（メモリアドレス）由来の名前を
   付けるので、そのまま写すと同一入力でもbundleが毎回変わる（D17実測:
   1,042ページ中14ページ）。数字だけの長い名前は**捨てる**——converter自身の
   安定ID（`p66-draw-image-00002`）が既に識別子で、実在するXObject名
   （`Im1`等）だけを`name`に残す。
2. **header/footerの検出**——PoCのy閾値（上6%・下94%）はzh版のfooter
   （下端比93.8%）を系統的に取りこぼした。本文はページ高90%の位置まで来るので
   閾値は緩めず、**反復ベース**を足す: 全ページを先に1回歩き、上下12%の帯で
   「数字を`#`に畳んだ同じ綴りが同じ高さに、全ページの25%以上（最低3ページ）
   繰り返し現れる」行を集め、その行だけ帯を12%まで広げて判定する。

出力は2系統:
- **bundle**（`.cache/structured-bundles/<stem>.<lang>/`）——非保存の導出物。
  同一原本＋同一engine＋同一converterでbyte一致に再生成できる
- **manifest**（`structured/<stem>.<lang>/manifest.json`）——コミットする正本。
  原本SHA-256と全page/geometryのSHA-256を持ち、再生成bundleとの突き合わせで
  「どのpageがいつからズレたか」をpage単位で言える

review sidecar（人の判断）は`structured/<stem>.<lang>/review.json`が正本で、
再変換はそれを上書きしない（bundle内のreview.jsonはcacheへの写し）。

実行:
    uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import statistics
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

import jsonschema
import pdfplumber

REPO = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "0.2"
# 1.1.0: manifestのgeometry_sha256を**非圧縮のJSON**のhashに変更。gzipの圧縮
# バイト列はzlibの版で変わり、GitHub Actions上の再変換がgeometry_sha256だけ
# 全ページ不一致になった（2026-09-01、structured-repro.ymlが検出）。圧縮は
# 保存の都合であって内容ではないので、hashは内容に対して取る。
CONVERTER_VERSION = "1.6.1"
DEFAULT_BUNDLES = REPO / ".cache" / "structured-bundles"
DEFAULT_STRUCTURED = REPO / "structured"
MANIFEST_SCHEMA = REPO / "schemas" / "structured-document-manifest.schema.json"
PAGE_SCHEMA = REPO / "schemas" / "structured-document-page.schema.json"
REVIEW_SCHEMA = REPO / "schemas" / "structured-document-review.schema.json"

HEADING_NUMBER = re.compile(r"^(?P<number>\d+(?:\.\d+)+)\s+\S")
CHAPTER_HEADING = re.compile(r"^(?:第\s*\d+\s*章|Chapter\s+\d+)", re.I)
LIST_ITEM = re.compile(r"^(?:[•●▪◆◇*-]|\(\d+\)|[a-z]\))\s*")
# 行頭にanchorする（1.3.0）——「注：表21-4的配置选择…」のような**参照文が
# captionに化けていた**（FV2x RM等で6件実測）。本物のcaptionは表/Tableで始まる。
TABLE_NUMBER = {
    "en": re.compile(r"^\s*Table\s+(\d+(?:-\d+)+)", re.I),
    "zh": re.compile(r"^\s*表\s*(\d+(?:-\d+)+)"),
}

# 反復ベースのheader/footer判定の帯と敷居。厳格帯（6%/94%）はPoCと同じで、
# 拡張帯（12%/88%）は反復が裏付ける行だけに適用する。
STRICT_BAND = 0.06
REPEAT_BAND = 0.12
REPEAT_FLOOR = 3
REPEAT_RATIO = 0.25


def dump_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


_VALIDATORS: dict[Path, jsonschema.Draft202012Validator] = {}


def validate(value: dict, schema_path: Path) -> None:
    validator = _VALIDATORS.get(schema_path)
    if validator is None:
        validator = jsonschema.Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8")))
        _VALIDATORS[schema_path] = validator
    validator.validate(value)


def validate_geometry(value: dict) -> None:
    """精密層の封筒だけを見る（全文字のDraft-2020検査は大型RMで1時間を超える）。"""
    if set(value) != {"schema_version", "source_sha256", "number", "chars", "drawings"}:
        raise ValueError("precision geometry has unexpected or missing keys")
    if value["schema_version"] != SCHEMA_VERSION or len(value["source_sha256"]) != 64:
        raise ValueError("precision geometry has invalid identity")
    if not isinstance(value["number"], int) or value["number"] < 1:
        raise ValueError("precision geometry has invalid page number")
    if not isinstance(value["chars"], list) or not isinstance(value["drawings"], list):
        raise ValueError("precision geometry arrays are invalid")


def rounded_box(box) -> list[float]:
    return [round(float(value), 3) for value in box]


def margin_key(text: str, edge_distance: float) -> tuple[str, float]:
    """反復判定の鍵。数字を畳む（ページ番号・版番号が変わっても同じ行）＋
    **ページの縁からの距離**（絶対yではなく。横向きページでも running footer は
    下端から同じ距離に印字される）。"""
    return (re.sub(r"\s+", " ", re.sub(r"\d+", "#", text)).strip(),
            round(edge_distance, 1))


def margin_repeats(pdf) -> tuple[set, set, set, set]:
    """第1パス: 上下の帯で繰り返す行を集める（1.2.0で規則を3つに）。

    (a) 同綴り・同縁距離が全ページの25%以上（従来の規則）
    (b) 同綴り・同縁距離が**厳格帯（6%）の中で3ページ以上**——章ごとに変わる
        headerの変種（V20x DS enの3ページだけの别綴り）や、途中でfooterの
        位置が変わった文書（V00X RM zhはp198以降の32ページ＝14%が別距離）
    (c) (a)(b)で合格した**綴りは距離が違っても余白扱い**（綴りspillover）——
        横向きページのfooterは縁距離まで変わる（V407 DS enのpin表5ページ）

    ページ番号だけの行（畳んで`#`）は(b)(c)から除く——数字だけの本文行を
    巻き込まないため。(a)の完全一致規則だけで扱う。
    """
    top_pages: dict[tuple, set[int]] = defaultdict(set)
    bottom_pages: dict[tuple, set[int]] = defaultdict(set)
    strict_top: dict[tuple, set[int]] = defaultdict(set)
    strict_bottom: dict[tuple, set[int]] = defaultdict(set)
    for page in pdf.pages:
        height = float(page.height)
        for line in page.extract_text_lines(return_chars=False) or []:
            if line["top"] < height * REPEAT_BAND:
                key = margin_key(line["text"], line["top"])
                top_pages[key].add(page.page_number)
                if line["top"] < height * STRICT_BAND:
                    strict_top[key].add(page.page_number)
            if line["bottom"] > height * (1 - REPEAT_BAND):
                key = margin_key(line["text"], height - line["bottom"])
                bottom_pages[key].add(page.page_number)
                if line["bottom"] > height * (1 - STRICT_BAND):
                    strict_bottom[key].add(page.page_number)
        page.flush_cache()
    threshold = max(REPEAT_FLOOR, int(len(pdf.pages) * REPEAT_RATIO))

    def qualify(band: dict, strict: dict) -> tuple[set, set]:
        keys = {key for key, pages in band.items() if len(pages) >= threshold}
        keys |= {key for key, pages in strict.items()
                 if len(pages) >= REPEAT_FLOOR and key[0] != "#"}
        texts = {key[0] for key in keys if key[0] != "#"}
        return keys, texts

    repeated_top, top_texts = qualify(top_pages, strict_top)
    repeated_bottom, bottom_texts = qualify(bottom_pages, strict_bottom)
    return repeated_top, repeated_bottom, top_texts, bottom_texts


def rotated_line_text(chars_list: list[dict]) -> str | None:
    """90°回転の文字が過半の行を、読める順に組み直す（1.3.0）。

    封装図・引脚配置図の縦ラベルは、pdfplumberの行組みだと**鏡順**になり
    （`33DDV`＝VDD33）、さらに**複数の縦ラベルが1行に混ざる**（x0が違う列の
    集まり）。x0で列に分割し、列の中はmatrixの向きで並べ替える——
    matrix b=+1（反時計回り・下から上へ読む）はtop降順、b=-1はtop昇順。
    向きが混在して決められなければNone（元の綴りのまま）。
    """
    named = [c for c in chars_list if str(c.get("text", "")).strip()]
    rotated = [c for c in named if not c.get("upright", True)]
    if len(named) < 2 or len(rotated) <= len(named) / 2:
        return None
    signs = {1 if c["matrix"][1] > 0 else -1 for c in rotated
             if abs(c["matrix"][1]) > 0.1}
    if len(signs) != 1:
        return None
    descending = signs.pop() > 0
    columns: list[list[dict]] = []
    for c in sorted(named, key=lambda c: c["x0"]):
        # 回転charの`size`はグリフ幅寄りで不安定なので、列分割は固定の許容で
        if columns and c["x0"] - columns[-1][-1]["x0"] <= 2.0:
            columns[-1].append(c)
        else:
            columns.append([c])
    labels = []
    for column in columns:
        column.sort(key=lambda c: c["top"], reverse=descending)
        pitches = [abs(b["top"] - a["top"])
                   for a, b in zip(column, column[1:])]
        positive = sorted(p for p in pitches if p > 0.1)
        median = positive[len(positive) // 2] if positive else 0.0
        parts = []
        for prev, c in zip([None] + column, column):
            if prev is not None and median:
                # 語の切れ目は「文字ピッチの中央値を大きく超える隙間」で見る
                if abs(c["top"] - prev["top"]) > median * 1.9:
                    parts.append(" ")
            parts.append(c["text"])
        labels.append("".join(parts))
    return " ".join(labels)


def fix_rotated_cells(page, record: dict) -> None:
    """回転文字が過半の**表セル**の文字を読める順に置き換える（1.3.1）。

    引脚定义表の型番ヘッダ等は縦書きで、`table.extract()`のセル文字は行と同じく
    鏡順になる（`6UEW714H`＝H417WEU6。322表／43文書で実測）。行（1.3.0）と同じ
    組み直しをセルにも適用する——`cells[].text`と`extracted_rows`の両方。
    旧toolも同じ鏡順を読んで正規化していたので正本CSVは無事だが、人向け出力の
    表セルには裸で出ていた。
    """
    rotated_centers = [((c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2)
                       for c in page.chars
                       if str(c.get("text", "")).strip() and not c.get("upright", True)]
    if not rotated_centers:
        return

    def rebuild(bbox) -> str | None:
        x0, top, x1, bottom = bbox
        if sum(1 for cx, cy in rotated_centers
               if x0 <= cx <= x1 and top <= cy <= bottom) < 2:
            return None
        inside = [c for c in page.chars
                  if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                  and top <= (c["top"] + c["bottom"]) / 2 <= bottom]
        return rotated_line_text(inside)

    for cell in record["cells"]:
        fixed = rebuild(cell["bbox"])
        if fixed is not None:
            cell["text"] = fixed
    for row_texts, row_boxes in zip(record["extracted_rows"], record["row_cells"]):
        for index, bbox in enumerate(row_boxes):
            if bbox is None or index >= len(row_texts) or row_texts[index] is None:
                continue
            fixed = rebuild(bbox)
            if fixed is not None:
                row_texts[index] = fixed


# 2カラムが始まる見出し。**Overview/概述は含めない**——overviewの散文は全幅1行で
# （`…microcontroller based on the QingKe RISC-V core`が1行・実測）、これを境界で
# 割ると`ba`と`d`に裂ける。2カラムなのはFeatures（箇条書き）以降。
COLUMN_START_HEADINGS = ("Features", "主要特性", "功能概述")


def column_boundary(page, lines: list[dict]):
    """2カラム（datasheetのfeaturesリスト）なら(列境界x, 開始y)、なければNone。

    pdfplumberの行抽出は左カラムと右カラムを同じy行として1行に結合してしまう
    （`- QingKe…core ● 3-group…`のように左右が混ざる）。Features見出しのある
    datasheetページに限り、**見出しの下**の表外wordのx0を見て、中央域（幅の
    35〜60%）で最大のx0ギャップ（左カラム右端と右カラム左端の間）を列境界に。
    見出しで絞るので製品比較表・register bit図・pin表・overview散文は対象外。
    """
    starts = [line for line in lines if line.get("role") == "heading"
              and any(k in line["text"] for k in COLUMN_START_HEADINGS)]
    if not starts:
        return None
    y_start = min(starts, key=lambda l: l["bbox"][1])["bbox"][3]
    width = float(page.width)
    tables = [t.bbox for t in page.find_tables()]

    def in_table(word) -> bool:
        cx, cy = (word["x0"] + word["x1"]) / 2, (word["top"] + word["bottom"]) / 2
        return any(t[0] <= cx <= t[2] and t[1] <= cy <= t[3] for t in tables)

    x0s = sorted(w["x0"] for w in (page.extract_words() or [])
                 if not in_table(w) and w["top"] >= y_start)
    x0s = [x for x in x0s if width * 0.35 <= x <= width * 0.60]
    if len(x0s) < 3:
        return None
    best_gap, best_x = 0.0, None
    for a, b in zip(x0s, x0s[1:]):
        if b - a > best_gap:
            # ギャップの中点を境界に——右カラム語の x0 ちょうどにすると、その語
            # （bullet等）が左cropにも intersect して左行末に紛れ込む。
            best_gap, best_x = b - a, (a + b) / 2
    if best_gap < 15:
        return None
    return (best_x, y_start)


def _line_median_size(line: dict) -> float:
    sizes = [c["size"] for c in line.get("chars", []) if str(c.get("text") or "").strip()]
    return statistics.median(sizes) if sizes else 0.0


def _subscript_clusters(chars: list[dict]) -> list[list[dict]]:
    """小フォント行のcharを内部のx空白で束ねる。

    `V_DD ... V_PVD`のように離れた複数の下付き語がtopで同じ行にまとまることが
    あり、その場合は`DD`と`PVD`を別クラスタに割って、それぞれ対応する`V`へ入れる。
    連続する綴り（`POR/PDR`）は空白が詰まっているので1クラスタのまま。
    """
    sc = sorted(chars, key=lambda c: c["x0"])
    groups: list[list[dict]] = [[sc[0]]]
    for prev, cur in zip(sc, sc[1:]):
        if cur["x0"] - prev["x1"] > 8:
            groups.append([])
        groups[-1].append(cur)
    return groups


def _insert_subscript(base_text: str, base_chars: list[dict],
                      sub_chars: list[dict]) -> str:
    """下付き/上付きの文字列を、ベース行のtextの該当位置へ挿入する。

    ベースのtext（正しい単語間空白入り）はそのまま保ち、下付きを`V`の直後へ
    差し込む——下付きが別行へ抜けた跡の空白（`(V )`の` `）は消す。char再構成に
    すると本文の単語空白が壊れる（charに空白が無く、gap判定では再現できない）。
    複数クラスタは右（x0大）から入れるので、左側のtext位置はずれない。
    """
    sub_text = "".join(c["text"] for c in sorted(sub_chars, key=lambda c: c["x0"]))
    sub_x0 = min(c["x0"] for c in sub_chars)
    k = sum(1 for c in base_chars if c["x0"] < sub_x0)   # 下付きより前のbase char数
    if k == 0:
        return base_text
    count, pos = 0, len(base_text)
    for idx, ch in enumerate(base_text):
        if not ch.isspace():
            count += 1
            if count == k:
                pos = idx + 1
                break
    rest = base_text[pos:]
    # 下付きの後の空白は、次が記号（`)`,`,`等）なら下付きが抜けた跡なので消し、
    # 英数字なら`VDD is`のような正規の単語間空白なので残す。
    if rest.startswith(" ") and (len(rest) < 2 or not rest[1].isalnum()):
        rest = rest[1:]
    return base_text[:pos] + sub_text + rest


def merge_subscript_lines(lines: list[dict]) -> list[dict]:
    """下付き・上付きが独立行に分かれたものを、ベースラインが揃う本文行へ統合する。

    pdfplumberの行抽出はtopでグループ化するので、`V`（top=102）の下付き`DD`
    （top=106・**bottomはVと揃う**）が別行になり、`V`と`DD`が離れて`V_DD`が読めなく
    なる（全datasheetで数千件）。本文より小さい行をクラスタに割り、各クラスタを
    bottom（ベースライン）±2.5pt揃い・x的に隣接する行のうち、**その基底より一回り
    小さい**（相対サイズ<0.82）ものへ差し込む。下付き判定はページ全体の中央値でなく
    **隣接する基底との相対**で見る——図中の電圧ラベル`V_BAT`の下付きは8.2pt（body
    10.6の77%）とグローバル閾値には収まらないが、基底`V`11.9に対しては明確に小さい。
    右のクラスタから入れるので左の位置はずれない。基底の無い極小ラベルは残る。
    """
    if not lines:
        return lines
    sizes = [s for s in (_line_median_size(l) for l in lines) if s > 0]
    if not sizes:
        return lines
    body = statistics.median(sizes)

    def baseline(chars: list[dict]) -> float:
        return statistics.median([c["bottom"] for c in chars
                                  if str(c.get("text") or "").strip()])

    bases = [j for j, b in enumerate(lines)
             if _line_median_size(b) > body * 0.72 and b.get("chars")]
    base_size = {j: _line_median_size(lines[j]) for j in bases}
    consumed = [False] * len(lines)
    subs_for: dict[int, list[list[dict]]] = {}
    for i, small in enumerate(lines):
        size = _line_median_size(small)
        if size == 0 or size >= body * 0.90 or not small.get("chars"):
            continue
        sb = baseline(small["chars"])
        matches = []
        for cl in _subscript_clusters(small["chars"]):
            cx = min(c["x0"] for c in cl)
            hit = next((j for j in bases
                        if size < base_size[j] * 0.82
                        and abs(sb - baseline(lines[j]["chars"])) <= 2.5
                        and lines[j]["x0"] - 5 <= cx <= lines[j]["x1"] + 5), None)
            matches.append((cl, hit))
        # 全クラスタが本文行に着地したときだけ小行を統合する。1つでも外れたら
        # 一部挿入でglyphを落とすことになるので小行は丸ごと残す（欠落回避）。
        if matches and all(j is not None for _, j in matches):
            for cl, j in matches:
                subs_for.setdefault(j, []).append(cl)
            consumed[i] = True

    out = []
    for i, line in enumerate(lines):
        if consumed[i]:
            continue
        if i in subs_for:
            line = dict(line)
            text = line["text"]
            for cl in sorted(subs_for[i], key=lambda c: -min(ch["x0"] for ch in c)):
                text = _insert_subscript(text, line["chars"], cl)
            line["text"] = text
        out.append(line)
    return out


def text_items(page, kind: str, boundary=None) -> list[dict]:
    if kind == "line" and boundary:
        # 2カラム: タイトル帯（y_start より上）は全幅、その下を左カラム→右カラム
        x_split, y_start = boundary
        source = ((page.crop((0, 0, page.width, y_start))
                   .extract_text_lines(return_chars=True) or [])
                  + (page.crop((0, y_start, x_split, page.height))
                     .extract_text_lines(return_chars=True) or [])
                  + (page.crop((x_split, y_start, page.width, page.height))
                     .extract_text_lines(return_chars=True) or []))
    else:
        source = (page.extract_text_lines(return_chars=True) if kind == "line"
                  else page.extract_words())
    if kind == "line":
        source = merge_subscript_lines(list(source or []))
    out = []
    for index, item in enumerate(source or [], 1):
        entry = {
            "id": f"p{page.page_number}-{kind}-{index:05d}",
            "text": item["text"],
            "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
        }
        if kind == "line":
            fixed = rotated_line_text(item.get("chars") or [])
            if fixed is not None:
                entry["text"] = fixed
                entry["_rotated"] = True   # 内部flag。書き出す前に落とす
        out.append(entry)
    return out


def chars(page) -> list[dict]:
    out = []
    for index, item in enumerate(page.chars, 1):
        out.append({
            "id": f"p{page.page_number}-char-{index:06d}",
            "text": item.get("text", ""),
            "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
            "font": str(item.get("fontname") or ""),
            "size": round(float(item.get("size") or 0), 3),
            "upright": bool(item.get("upright", True)),
        })
    return out


def classify_lines(lines: list[dict], page_chars: list[dict], height: float,
                   repeated_top: set, repeated_bottom: set,
                   top_texts: set = frozenset(), bottom_texts: set = frozenset()) -> None:
    sizes = [item["size"] for item in page_chars
             if item["text"].strip() and item["size"] > 0]
    body_size = statistics.median(sizes) if sizes else 0
    for line in lines:
        rotated = line.pop("_rotated", False)   # どの分岐でもJSONへは残さない
        x0, top, x1, bottom = line["bbox"]
        members = [item for item in page_chars
                   if item["bbox"][2] >= x0 and item["bbox"][0] <= x1
                   and item["bbox"][3] >= top and item["bbox"][1] <= bottom]
        line_sizes = [item["size"] for item in members if item["text"].strip()]
        line["font_size"] = round(statistics.median(line_sizes), 3) if line_sizes else 0
        named = [item for item in members if item["text"].strip()]
        line["bold"], line["italic"] = emphasis(named)
        text = line["text"].strip()
        numbered = HEADING_NUMBER.match(text)
        # 反復する余白行はheading判定より先に決める——TOC等の小さい本文フォントの
        # ページでは、footerの9ptが「本文中央値の1.25倍」を満たしてheadingに
        # 化けることがある（D18実装時にV003 zhの3ページで実測）。全ページの
        # 25%以上で同じ縁距離に繰り返す行が見出しであることはない。
        if (top < height * REPEAT_BAND
                and (margin_key(line["text"], top) in repeated_top
                     or margin_key(line["text"], top)[0] in top_texts)):
            line["role"] = "header"
        elif (bottom > height * (1 - REPEAT_BAND)
                and (margin_key(line["text"], height - bottom) in repeated_bottom
                     or margin_key(line["text"], height - bottom)[0] in bottom_texts)):
            line["role"] = "footer"
        elif rotated:
            # 90°回転の縦ラベル（封装図のpin名等）。図の部品であって見出しでは
            # ない——大きめのフォントだとheading判定に化けていた（H417 DS p26の
            # 「@VDD33 power」がlevel-1見出しになった実測）。
            line["role"] = "paragraph"
        elif CHAPTER_HEADING.match(text) or numbered or (
                len(text) <= 120 and body_size and line["font_size"] >= body_size * 1.25):
            line["role"] = "heading"
            line["level"] = (min(6, numbered.group("number").count(".") + 1)
                             if numbered else 1)
        elif top < height * STRICT_BAND:
            line["role"] = "header"
        elif bottom > height * (1 - STRICT_BAND):
            line["role"] = "footer"
        elif LIST_ITEM.match(text):
            line["role"] = "list-item"
        else:
            line["role"] = "paragraph"


def drawings(page) -> list[dict]:
    out = []
    for kind in ("line", "rect", "curve", "image"):
        for index, item in enumerate(getattr(page, f"{kind}s"), 1):
            record = {
                "id": f"p{page.page_number}-draw-{kind}-{index:05d}",
                "type": kind,
                "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
            }
            if kind == "image":
                name = str(item.get("name") or "")
                # pdfminerはinline imageへid()由来の数字名を付ける（process毎に
                # 変わる）。実在するresource名だけを残す——安定IDは`id`が持つ。
                if name and not (name.isdigit() and len(name) >= 10):
                    record["name"] = name
                size = item.get("srcsize")
                if size and len(size) == 2:
                    record["source_size"] = [int(size[0]), int(size[1])]
            out.append(record)
    return out


def overlap_issues(cells: list[dict]) -> list[str]:
    occupied: dict[tuple[int, int], str] = {}
    overlaps = []
    for cell in cells:
        for row in range(cell["row_start"], cell["row_end"]):
            for column in range(cell["column_start"], cell["column_end"]):
                previous = occupied.get((row, column))
                if previous:
                    overlaps.append(f"{cell['id']} overlaps {previous} at {row},{column}")
                occupied[(row, column)] = cell["id"]
    return overlaps


def cell_text(page, bbox) -> str:
    # `Table.extract()`は結合セルを矩形行列に平坦化する。物理セルの矩形で
    # cropし、rowspan/colspanを持つセルに文字を残す。
    return (page.crop(bbox).extract_text(x_tolerance=3, y_tolerance=3) or "").strip()


def emphasis(chars_list) -> tuple[bool, bool]:
    """(太字, 斜体)。過半の文字のfontnameが bold / italic(oblique)なら真。

    lineのchar（`font`キー）とpage.chars（`fontname`キー）の両方を受ける。
    見た目の強調（太字＝BoldMT・斜体＝ItalicMT。全コーパスで各3%）は本文の
    テキストには出ないので、これを拾わないと原本の強調が消える。"""
    named = [c for c in chars_list
             if str(c.get("text") or "").strip()]
    if not named:
        return False, False
    def font(c):
        return str(c.get("font") or c.get("fontname") or "").lower()
    n = len(named)
    bold = sum("bold" in font(c) for c in named) >= n / 2
    italic = sum(("italic" in font(c) or "oblique" in font(c))
                 for c in named) >= n / 2
    return bold, italic


def physical_cells(page, table, table_id: str) -> tuple[list[dict], int, int]:
    xs = sorted({round(value, 6) for cell in table.cells for value in (cell[0], cell[2])})
    ys = sorted({round(value, 6) for cell in table.cells for value in (cell[1], cell[3])})
    x_index = {value: index for index, value in enumerate(xs)}
    y_index = {value: index for index, value in enumerate(ys)}
    tb = table.bbox
    table_chars = [c for c in page.chars
                   if str(c.get("text") or "").strip()
                   and tb[0] <= (c["x0"] + c["x1"]) / 2 <= tb[2]
                   and tb[1] <= (c["top"] + c["bottom"]) / 2 <= tb[3]]
    cells = []
    for index, bbox in enumerate(sorted(table.cells, key=lambda box: (box[1], box[0])), 1):
        x0, top, x1, bottom = (round(value, 6) for value in bbox)
        in_cell = [c for c in table_chars
                   if x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                   and top <= (c["top"] + c["bottom"]) / 2 <= bottom]
        bold, italic = emphasis(in_cell)
        cells.append({
            "id": f"{table_id}-cell-{index:04d}",
            "row_start": y_index[top],
            "row_end": y_index[bottom],
            "column_start": x_index[x0],
            "column_end": x_index[x1],
            "bbox": rounded_box(bbox),
            "text": cell_text(page, bbox),
            "bold": bold,
            "italic": italic,
        })
    return cells, len(ys) - 1, len(xs) - 1


def captions(lines: list[dict], lang: str) -> list[dict]:
    found = []
    for line in lines:
        match = TABLE_NUMBER[lang].search(line["text"])
        if match:
            found.append({
                "line_id": line["id"],
                "source_number": match.group(1),
                "text": line["text"],
                "top": line["bbox"][1],
            })
    return found


def page_record(page, lang: str, source_sha256: str,
                previous_logical_id: str | None,
                previous_page: int | None,
                number_occurrences: dict[str, int],
                repeated_top: set, repeated_bottom: set,
                top_texts: set, bottom_texts: set,
                document_type: str = "") -> tuple[dict, dict, str | None]:
    page_chars = chars(page)
    lines = text_items(page, "line")
    classify_lines(lines, page_chars, float(page.height), repeated_top, repeated_bottom,
                   top_texts, bottom_texts)
    # datasheetのoverview/featuresページは2カラム——pdfplumberが左右を1行に
    # 結合するので、列境界が見つかれば左右別々に行を組み直す（左カラム全行→
    # 右カラム全行の読み順）。見出しで絞るので他ページは触らない。
    if document_type == "datasheet":
        boundary = column_boundary(page, lines)
        if boundary:
            lines = text_items(page, "line", boundary=boundary)
            classify_lines(lines, page_chars, float(page.height),
                           repeated_top, repeated_bottom, top_texts, bottom_texts)
    words = text_items(page, "word")
    page_drawings = drawings(page)
    page_captions = captions(lines, lang)
    detected = sorted(page.find_tables(), key=lambda item: (item.bbox[1], item.bbox[0]))
    tables = []
    previous_bottom = 0.0
    for table_index, table in enumerate(detected, 1):
        candidates = [item for item in page_captions
                      if previous_bottom <= item["top"] < table.bbox[1]]
        caption = candidates[-1] if candidates else None
        if caption:
            number = caption["source_number"]
            occurrence = number_occurrences.get(number, 0) + 1
            number_occurrences[number] = occurrence
            logical_id = f"table-{number}@{occurrence}"
            previous_logical_id = logical_id
            caption_record = {key: caption[key]
                              for key in ("line_id", "source_number", "text")}
            continues = False
        else:
            consecutive = previous_page is not None and page.page_number == previous_page + 1
            logical_id = (previous_logical_id if consecutive and previous_logical_id
                          else f"unlabelled-p{page.page_number}-{table_index}")
            caption_record = None
            continues = bool(consecutive and previous_logical_id)
        table_id = f"p{page.page_number}-table-{table_index:03d}"
        cells, row_count, column_count = physical_cells(page, table, table_id)
        tables.append({
            "id": table_id,
            "logical_id": logical_id,
            "bbox": rounded_box(table.bbox),
            "caption": caption_record,
            "continues_from_previous": continues,
            "row_count": row_count,
            "column_count": column_count,
            # 平坦化行（pdfplumber互換）と物理セルの両方を保つ——結合セルの
            # 表で答える問いが違い、既存抽出器の無損失移行に両方要る。
            "extracted_rows": table.extract(),
            "row_cells": [[rounded_box(cell) if cell is not None else None
                           for cell in row.cells] for row in table.rows],
            "cells": cells,
            "issues": overlap_issues(cells),
        })
        fix_rotated_cells(page, tables[-1])
        previous_bottom = table.bbox[3]

    def outside_tables(line: dict) -> bool:
        x0, top, x1, bottom = line["bbox"]
        center_x, center_y = (x0 + x1) / 2, (top + bottom) / 2
        return not any(table["bbox"][0] <= center_x <= table["bbox"][2]
                       and table["bbox"][1] <= center_y <= table["bbox"][3]
                       for table in tables)

    order = ([{"id": line["id"], "type": "line", "bbox": line["bbox"]}
              for line in lines if outside_tables(line)]
             + [{"id": table["id"], "type": "table", "bbox": table["bbox"]}
                for table in tables]
             + [{"id": item["id"], "type": "image", "bbox": item["bbox"]}
                for item in page_drawings if item["type"] == "image"])
    order.sort(key=lambda item: (item["bbox"][1], item["bbox"][0], item["type"]))
    record = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "number": page.page_number,
        "width": round(float(page.width), 3),
        "height": round(float(page.height), 3),
        "rotation": int(getattr(page, "rotation", 0) or 0),
        "text": page.extract_text() or "",
        "lines": lines,
        "words": words,
        "images": [item for item in page_drawings if item["type"] == "image"],
        "tables": tables,
        "reading_order": order,
    }
    geometry = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "number": page.page_number,
        "chars": page_chars,
        "drawings": page_drawings,
    }
    return record, geometry, previous_logical_id


def convert(pdf_path: Path, lang: str, document_type: str,
            bundles: Path = DEFAULT_BUNDLES,
            structured: Path = DEFAULT_STRUCTURED) -> Path:
    source_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    name = f"{pdf_path.stem}.{lang}"
    bundle = bundles / name
    committed = structured / name

    # review の正本はコミット側。原本が変わっていたら流用せず止まる
    # （D16「原本更新時に古いreviewを自動流用しない」）。
    committed_review = committed / "review.json"
    if committed_review.exists():
        review = json.loads(committed_review.read_text(encoding="utf-8"))
        validate(review, REVIEW_SCHEMA)
        if review["source_sha256"] != source_sha256:
            raise ValueError(f"{committed_review}: source hash differs; "
                             "review it against the new original before reconversion")
    else:
        review = {
            "schema_version": SCHEMA_VERSION,
            "source_sha256": source_sha256,
            "status": "unreviewed",
            "decisions": {},
        }
        validate(review, REVIEW_SCHEMA)

    page_dir = bundle / "pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir = bundle / "geometry"
    geometry_dir.mkdir(parents=True, exist_ok=True)

    page_entries = []
    number_occurrences: dict[str, int] = {}
    previous_logical_id = None
    previous_page = None
    with pdfplumber.open(pdf_path) as pdf:
        repeated_top, repeated_bottom, top_texts, bottom_texts = margin_repeats(pdf)
        for page in pdf.pages:
            record, geometry, previous_logical_id = page_record(
                page, lang, source_sha256, previous_logical_id,
                previous_page, number_occurrences, repeated_top, repeated_bottom,
                top_texts, bottom_texts, document_type)
            validate(record, PAGE_SCHEMA)
            validate_geometry(geometry)
            payload = dump_bytes(record)
            geometry_raw = dump_bytes(geometry)
            geometry_payload = gzip.compress(geometry_raw, compresslevel=9, mtime=0)
            relative = Path("pages") / f"{page.page_number:04d}.json"
            geometry_relative = Path("geometry") / f"{page.page_number:04d}.json.gz"
            (bundle / relative).write_bytes(payload)
            (bundle / geometry_relative).write_bytes(geometry_payload)
            page_entries.append({
                "number": page.page_number,
                "file": relative.as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "geometry_file": geometry_relative.as_posix(),
                # 非圧縮のJSONに対するhash。gzipのバイト列はzlibの版で変わる
                "geometry_sha256": hashlib.sha256(geometry_raw).hexdigest(),
                "width": record["width"],
                "height": record["height"],
            })
            previous_page = page.page_number
            page.flush_cache()
        page_count = len(pdf.pages)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "document": pdf_path.name,
            "document_type": document_type,
            "language": lang,
            "sha256": source_sha256,
            "page_count": page_count,
        },
        "conversion": {
            "engine": "pdfplumber",
            "engine_version": version("pdfplumber"),
            "converter_version": CONVERTER_VERSION,
            "coordinates": "PDF points, origin at top-left",
            "scope": "all-pages",
            "table_settings": {},
        },
        "pages": page_entries,
    }
    validate(manifest, MANIFEST_SCHEMA)
    payload = dump_bytes(manifest)
    (bundle / "manifest.json").write_bytes(payload)
    committed.mkdir(parents=True, exist_ok=True)
    (committed / "manifest.json").write_bytes(payload)
    # bundle側のreview.jsonは正本（structured/）の写し。検査toolが読む。
    (bundle / "review.json").write_bytes(dump_bytes(review))
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--lang", choices=("zh", "en"), required=True)
    parser.add_argument(
        "--document-type",
        choices=("datasheet", "reference-manual", "core-manual",
                 "package-drawing", "other", "unknown"),
        default="unknown")
    parser.add_argument("--out", type=Path, default=DEFAULT_BUNDLES,
                        help="bundleの出力先の上書き（試験用）")
    parser.add_argument("--structured", type=Path, default=DEFAULT_STRUCTURED,
                        help="コミットするmanifest/reviewの置き場の上書き（試験用）")
    args = parser.parse_args()
    bundle = convert(args.pdf, args.lang, args.document_type, args.out, args.structured)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    print(f"{bundle}: {len(manifest['pages'])}/{manifest['source']['page_count']} pages "
          f"(converter {CONVERTER_VERSION})")


if __name__ == "__main__":
    main()
