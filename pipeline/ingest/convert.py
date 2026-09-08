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
import sys
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

import jsonschema
import pdfplumber

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "common"))
import logical_tables  # noqa: E402
SCHEMA_VERSION = "0.2"
# 1.1.0: manifestのgeometry_sha256を**非圧縮のJSON**のhashに変更。gzipの圧縮
# バイト列はzlibの版で変わり、GitHub Actions上の再変換がgeometry_sha256だけ
# 全ページ不一致になった（2026-09-01、structured-repro.ymlが検出）。圧縮は
# 保存の都合であって内容ではないので、hashは内容に対して取る。
# 1.7.0: セル内の下付き/上付きの復元を**converterへ移した**（`fix_cell_subscripts`）。
# それまではexporterとparityだけが直していたので、bundleのセルを読む抽出器
# （`operating_conditions`・`option_bytes`・`debug_wiring`）には壊れた綴りのまま
# 届いていた（`V\nSS`・`V power regulation bit:\nIO18`）。14,738セル／61文書。
# 1.7.1: 直す前の綴りを`cells[].text_split`に残す。1.7.0では繋いだ形しか残らず、
# **下付きの境界という情報**が消えて`operating_conditions`の`I_DD`系1,207行が落ちた
# （`build_operating.norm_symbol`が`I\nDD`の改行を`_`にして正規化記号を作るため）。
# 1.8.0: 文字層の正規化（私用領域コードポイント9,291個・重ね描き143件）と、行の中の
# 下付き/上付き復元（805行。`2^20`が`220`に潰れて**値が違って**いた）、表題の全文化
# （27件。exporterとextract_low_powerが同じ修復を各々掛けていた）を**exporterから
# converterへ**移した。それまで直っていたのはMarkdownだけで、bundleを読む抽出器には
# 壊れた字が渡っていた。
# 1.9.0: セル境界の二重取りグリフとreset列の異物も根で落とす（straddling 4,457・
# boundary 2,337・reset列 2,200）。これまでexporterとparityだけが直しており、bundleの
# セルには二重取りが残っていた。
# 1.9.1: 2026-09-06の検証ラウンド（未走査8文書・78ページ）が出した3件を根で直した。
# (a) `reading_order`を`(top,x0)`で並べ直して**2カラム分割を打ち消していた**
#     （全datasheetの1ページ目でFeaturesが左右交互になっていた）。
# (b) 列境界に載ったグリフが右列の行頭に二重取りされる（2カラム16ページ全部で発生）。
# (c) `clean_reset_column`が語彙に無い1〜2字を無条件に消していて、QingKeの`W1`/`R0`が
#     消滅（access列の空セル509個・30文書）。小文字のLatinだけ落とすように変えた。
# 1.9.2: 2026-09-07の検証ラウンド2窓目（16文書・141ページ）が出した2件を根で直した。
# (a) 括弧付きの指数`2^(G+2)`（NAPOTの領域幅）が`2(G+2)`に潰れて**掛け算に読めていた**。
#     前判定・セル単位ゲート・`^`の直後の歯止めの3箇所が括弧を通していなかった。
# (b) `clean_reset_column`が「英数字を含まない値は説明列の残骸」として`…`を消していた。
#     `…`は「行が続く」印であって残骸ではない。
# 1.9.3: 2026-09-07の検証ラウンド3窓目（24文書・228ページ）が出した3件を根で直した。
# (a) **2カラムの2ページ目以降が分割されていなかった**——見出しはページ1にしか刷られない
#     のに、境界検出が見出しを必須にしていた（high 5件）。前ページの列境界xを持ち回り、
#     同じx（±10pt）に再検出できたときだけ続きとして扱う。
# (b) 列の隙間をx0のギャップで測れない版面（右カラムの字下げが何段もある zh datasheet）。
#     語の占有幅をx軸へ投影して空白帯を探す方法をfallbackに足した。
# (c) `clean_reset_column`の1〜2字規則を**1字**に絞った——SDコマンドの`类型`列の`ac`が
#     消えて表32-4/5/6の14行中8行が値を失っていた（1.9.1で入れた規則の穴）。
# 1.9.4: 列境界に**妥当性検査**を入れた。1.9.3で`产品特性`を見出し語に足したところ、
# それまで分割されなかったV205DS0.zh p1が**悪い位置で**分割され、右カラムの語33個が
# 途中で切れて切れ端がページ末尾に落ちた（`crop`は跨いだ語を両側に入れる）。原因は
# x0のギャップ方式が**右カラムの内側**（字下げの段の間）を溝と誤ったこと。2つの候補
# （x0ギャップ・語の占有幅の投影）を出して**跨ぐ語が最小のもの**を採り、それでも3語
# 以上跨ぐなら分割しない。2026-09-07の検証ラウンド4窓目が検出。
# 1.10.0: **表領域の外に落ちた最外列を取り込む**（`recover_outer_column`）。罫線検出が
# 最外列の外枠を拾えないと、その列が表bboxの外に残り、行の中心は表bbox内なので
# `reading_order`からも外れて**Markdownのどこにも出ない**——`位`列（`[31:15]`/`14`）や
# `复位值`/`Reset value`列がそれで消えていた。全corpus49表・約20文書。入れ先が一意に
# 決まるものだけ（本物の罫線表・1列ぶんの幅・縁に接する・全行帯に中身・各24字以内）。
# 2026-09-07の検証ラウンドが「セル格子」familyのhigh 13件として指摘した分の一部。
# 1.10.1: (a) **走査線に刻まれたrasterを1枚に束ねる**——別行立ての数式が高さ0.72ptの
# 帯277枚に割れて`<!-- image -->`コメント277行になり、**内容がMarkdownから消えていた**
# （V205DS0.en p64・L103DS0.zh p49）。(b) **セル文字列をgeometryから組み直す**fallback
# ——脚注の上付きと下付きが同じ基底に付くシンボルで、pdfplumberが脚注を基底の行・
# 下付きを次の行に置くため`V_DD12A(1)`が`'V (1)\nDD12A'`になる。文字は全部あって順序
# だけが違うので挿し込みでは直せない（歯止めが正しく拒否する）。行→xに並べ直すだけなら
# 挿入位置の曖昧さが無い。全corpus419セル・うち338が24字以内で、そこだけ組み直す。
# 1.10.2: **caption を持たない表をページを跨いで繋ぐ**（`chain_uncaptioned`）。
# `continues_from_previous`が「過去にcaption付きの表がある」前提だったため、caption無しの
# 比較表はp3とp4が別の論理表になり、(a)最終セルが`USBHS (USB`で切れ、(b)`'2.0)'`だけの
# 幽霊行が残り、(c)刷り直されたヘッダが列数を狂わせていた。結合表でしか効かない
# `fold_boundary_spills`と`drop_repeated_headers`が届いていなかった。条件は列数と
# **列境界xの±2pt一致**＋上下の位置で、全corpusの候補は18件（既に繋がる表は5,734件）。
# 1.13.0: **折り返した節見出しの続きを見出しへ繋ぐ**（`join_heading_wraps`）。読む側は
# `extract_text()`の行ごとに見出しの正規表現を当てるので、折り返した題は1行目しか
# 取れず、`evidence/features.csv`に`1.4.19 … (USBSS) (Not applicable`と切れて入って
# いた（続きは`to CH32X305)`）。v1.1では`(Not`で切れていて、**新版で切れる位置が
# 動いただけ**。`lines`と`text`の両方で繋ぐ——凍結toolが読むのは`text`。
# 全corpus実測: 節見出し17,400のうち条件を満たすのは**22件**（緩い条件では562件当たり、
# その大半は`● …`の箇条書き）。
# 1.12.0: **最外列の取り込みを3つ緩めた**（`recover_outer_column`）。(a) 隙間の上限8ptを
# 「**縁までの全幅**が1列ぶん」に置き換え——隙間は「列幅−文字幅」で決まるので閾値として
# 筋が悪く、`CH32L103RM.en` p13の`Bit`/`[31:21]`は8.4ptで**0.4pt足りずに落ちていた**。
# (b) 3行→2行（bit説明表は「見出し＋1行」の断片になりやすい）。(c) **左右の両方**を見る
# （以前は片方でreturnし、`Bit`と`Resetvalue`が両方外に出ている表で右が残っていた）。
# 全corpus実測: 49表→107表。増える分は全部`Bit`/`Resetvalue`/`复位值`/`位`/レジスタ名の
# 完全な列で、これらは行の中心が表bbox内のため**reading_orderからも外れて**いた
# （`CH32V003RM.en` p132は`Reset`/`value`/`0xFFF`/`F`と値を分断した本文になっていた）。
# 1.11.0: **グリッドから丸ごと抜けた列を埋める**（`fill_grid_holes`）。罫線が細いと
# pdfplumberはその列のセルを1つも作らず、`WCH-LinkUserManual.zh` p4の機能比較表は
# **14個の行見出しがどのセルにも入っていなかった**。行と列の座標は他のセルから決まるので
# 入れ先は一意。条件は「同じ列に3つ以上の穴があり、その3つ以上に文字が在る」——散発の
# 穴（図の誤検出ページのラベル断片。全corpus90個/50表）を外すとこの1表だけになる。
CONVERTER_VERSION = "1.13.0"

# 継ぎ目の区切りを決めるのに使う（CJKは字間が無い）。
CJK_CHAR = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff01-\uff60]")
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


def fix_cell_subscripts(page_chars: list[dict], record: dict) -> None:
    """表セルの中で基底から離れた**下付き/上付き**をgeometryで戻す（1.7.0）。

    pdfplumberはセル内の下付き（小さいフォント・低い基線）を別の視覚行として拾い、
    `VSS`を`V\nSS`、`VDD5*2-1.5`を`V *2-1.5DD5`、`2^20`を`220`にする。判定と組み直しは
    `logical_tables.reattach_cell_subscripts`（geometryで基底と下付きを分け、綴りが
    一致しなければ何もしない安全側）。**行の`merge_subscript_lines`と対**で、あちらは
    ページの行、こちらは表のセルを見る。

    それまではexporterとparityだけが直していたので、bundleのセルを読む抽出器には
    壊れた綴りのまま届いていた。ここで直せばMarkdownにもCSVにも同じ文字が行く。
    判定用の印（`_subscripts_reattached`）はbundleに残さない——schemaに無いキー。

    **直す前の綴りを`text_split`に残す。** pdfplumberの割り方は壊れているのではなく
    **下付きの境界を持っている**——`build_operating.norm_symbol`は`I\nDD`の改行を
    `_`に変えて正規化記号`I_DD`を作る（`KEEP`がその形しか通さない）。繋いだ形だけを
    残すとその境界が消え、`operating_conditions`の`I_DD`系1,207行が丸ごと落ちた
    （2026-09-06に実測）。読み順として正しいのは繋いだ形なので`text`はそれにし、
    **版面がどう割っていたか**を別のキーに置く。`extracted_rows`（pdfplumber互換の
    平坦化行）と同じ考え方で、面を2つ持つ。
    """
    if not logical_tables.has_subscript_shape(record):
        return
    before = [cell["text"] for cell in record["cells"]]
    logical_tables.reattach_cell_subscripts(record, page_chars)
    record.pop("_subscripts_reattached", None)
    for cell, original in zip(record["cells"], before):
        if cell["text"] != original:
            cell["text_split"] = original


def join_split_lines(page: dict) -> int:
    """**同じ視覚行が途中で二つに割れ、境目の1文字が両側に入った**対を繋ぐ（1.9.0）。

    zh版datasheetの本文は全行が x≈241 で `…対外`/`外多组…` のように割れ、1ページに25行も
    「途中で改行して1文字が二重」に見えていた（V002DS0.zh・V006DS0.zh・M030DS2.zh p6。
    全corpus294行）。判定は`logical_tables.split_line_merges`——同じ高さ・左右が接する・
    同じ字送り・左の末尾＝右の先頭、かつ**同じ境界xに3対以上**、と厳しいので、2段組の
    独立した列は当たらない。

    繋いだ結果は**左の行の`text`**に入り、右の行には`merged_into`（左のid）を付けて残す
    ——行を消すと`reading_order`とidの対応が崩れるし、**版面が二つに割っていた事実**も
    消える。読み手（exporter/parity）は`merged_into`のある行を飛ばすだけでよい。
    `page["text"]`は`extract_text()`が別に作る面なので触らない。"""
    merge = logical_tables.split_line_merges(page)
    if not merge:
        return 0
    lines = {line["id"]: line for line in page["lines"]}
    for left_id, (right_id, tail) in merge.items():
        lines[left_id]["text"] = (lines[left_id]["text"] or "").rstrip() + tail
        lines[right_id]["merged_into"] = left_id
    return len(merge)


def spell_glyphs(glyphs: list[dict]) -> str:
    """グリフ列を読み順（行→x）で綴る。**語の間の空白を隙間から復元する**。

    表の外から取り込む列（`recover_outer_column`・`fill_grid_holes`）は、pdfplumberの
    セル抽出を通らないので区切りが入らず`Resetvalue`・`Filterregister0`になっていた。

    - **視覚行の切れ目は`\n`**にする。狭い列では見出しも値も折り返され、`Reset`/`value`
      は空白で繋ぐべきで`0xFFF`/`F`は繋いではいけない——この判定は既に
      `cell_html`（行末・行頭の文字種で折り返しか意図的な改行かを分ける）が持っている
      ので、そちらへ渡す。改行を入れずに繋いでいたので`Resetvalue`になっていた。
    - **同じ視覚行の語間の空白**は隙間から復元する。隙間が**グリフ幅の中央値の0.35倍**を
      超え、かつ両側がASCIIなら空白（CJKは字間が広く、識別子`R32_ESIG_FLACAP`のような
      連続は隙間が空かない）。全corpus実測: 空白が入るのは35セルで全部`Reset value`型の
      見出し。閾値0.25〜0.50で結果が同じ＝隙間が明確に分かれているので真ん中を採る。
      値のセル（`0xFFFF`・`[31:0]`）は1つも変わらない。
    """
    ordered = sorted(glyphs, key=lambda g: (round(g["bbox"][1], 1), g["bbox"][0]))
    if not ordered:
        return ""
    widths = sorted(g["bbox"][2] - g["bbox"][0] for g in ordered)
    median = widths[len(widths) // 2]
    out: list[str] = []
    for index, glyph in enumerate(ordered):
        if index:
            previous = ordered[index - 1]
            both_ascii = previous["text"].isascii() and glyph["text"].isascii()
            if abs(glyph["bbox"][1] - previous["bbox"][1]) >= 1.0:
                out.append("\n")
            elif (both_ascii
                    and glyph["bbox"][0] - previous["bbox"][2] > median * 0.35):
                out.append(" ")
        out.append(glyph["text"])
    return "".join(out)


def recover_outer_column(page_chars: list[dict], record: dict,
                         siblings: list[dict]) -> str | None:
    """**表領域の外に落ちた最外列**を取り込む（1.10.0）。取り込んだ側を返す
    （`"left"`・`"right"`・`"left,right"`・None）。

    罫線ベースの表検出が最外列の外枠を拾えないと、その列が表bboxの外に残る——
    `CH32M030RM.zh` p7の`位`列（x 78.5-115.2、表bboxは121.8から）がそれで、値
    `[31:15]`/`14`/`[13:12]`は**Markdownのどこにも出ていなかった**（行の中心は表bbox内
    なので`reading_order`からも外れる）。`复位值`/`Reset value`列が右外へ排出される型も
    ある。全corpus49表・約20文書（2026-09-07の検証ラウンドがhigh 13件として指摘した
    「セル格子」familyの中で、**入れ先が一意に決まる**分）。

    入れ先が一意に決まるものだけ触る。**表自身の行境界**でグリフを束ね、1行帯につき
    1セルの列を先頭（または末尾）へ挿す。次の全部を満たすときだけ:

    - 本物の罫線表（2行3列以上・セルの6割以上に中身）——図の誤検出を外す
    - 外側のグリフが**1列ぶんの幅**（表幅の30%以下）で、**表の縁までの全幅も1列ぶん**
      （同30%以下）に収まる。縁に食い込んでいない（隙間≥-2pt）
    - **すべての行帯に中身がある**＝列として完全。1行帯でも欠けたら曖昧なので触らない
    - どの行帯も24字以内。他の表の中にいるグリフは対象外

    緩い条件（幅と行帯の完全性を見ない）では1,000表超が当たり、その大半は図を表と
    誤検出したページの散乱ラベル（`XUSRAMMFS_DPUSBFSFS_DM`）だった。上の条件で107表。
    `extracted_rows`は**触らない**——凍結tool19本がそれを読むので、影響を`cells`側に閉じる。

    **1.12.0で3つ緩めた**（再突合が`CH32L103RM.en` p13の`Bit`列欠落として指摘した分の根）:

    1. 隙間の上限8ptを**縁までの全幅**の条件に置き換えた。隙間は「列幅−文字幅」で決まる
       ので閾値として筋が悪く、`名称`のような左寄せの広い列では大きくなる。L103RM.en p13の
       `Bit`/`[31:21]`は隙間8.4ptで**0.4pt足りずに落ちていた**。全幅で見ると図の断片
       （`['Syst','em','Bus']`。隙間219pt）は落ち、本物の`Bit`/`Resetvalue`列は通る。
    2. 3行→**2行**（行帯3本→2本）。レジスタのbit説明表は「見出し＋1行」の2行断片に
       なることが多く、L103RM.en p13もそれ。緩めて増える64件は全部`Bit`/`Resetvalue`/
       `复位值`/`位`/レジスタ名の列だった。
    3. **左右の両方**を見る（以前は片方を取り込んだ時点でreturnしていた）。`Bit`列と
       `Resetvalue`列が両方外へ出ている表が多数あり、右側が取り残されていた。

    実測: 107表。中身は`['Bit','[31:0]']`・`['Resetvalue','0xFFFF']`・`['复位值','0']`・
    `['过滤寄存器0',…]`のような完全な列ばかり。これらは**行の中心が表bbox内なので
    reading_orderからも外れ**、`CH32V003RM.en` p132では`Reset value 0xFFFF`が表の外に
    `Reset`/`value`/`0xFFF`/`F`と**値を分断された本文**として落ちていた。
    """
    if record["row_count"] < 2 or record["column_count"] < 3:
        return None
    others = [t["bbox"] for t in siblings if t is not record]
    recovered: list[str] = []

    for side in ("left", "right"):
        # 左を取り込むと列番号とbboxが動くので、側ごとに読み直す（行帯は変わらない）。
        cells = record["cells"]
        if not cells or sum(1 for c in cells
                            if (c.get("text") or "").strip()) / len(cells) < 0.6:
            break
        box = record["bbox"]
        width = box[2] - box[0]
        ys = sorted({round(c["bbox"][1], 2) for c in cells}
                    | {round(c["bbox"][3], 2) for c in cells})
        if len(ys) < 3:
            break
        picked = []
        for glyph in page_chars:
            if not (glyph.get("text") or "").strip():
                continue
            gx = (glyph["bbox"][0] + glyph["bbox"][2]) / 2
            gy = (glyph["bbox"][1] + glyph["bbox"][3]) / 2
            if not (box[1] <= gy <= box[3]):
                continue
            if gx < box[0] if side == "right" else gx > box[2]:
                continue
            if side == "left" and gx >= box[0]:
                continue
            if side == "right" and gx <= box[2]:
                continue
            if any(o[0] <= gx <= o[2] and o[1] <= gy <= o[3] for o in others):
                continue
            picked.append(glyph)
        if len(picked) < 3:
            continue
        x0 = min(g["bbox"][0] for g in picked)
        x1 = max(g["bbox"][2] for g in picked)
        if x1 - x0 > width * 0.30:
            continue
        gap = box[0] - x1 if side == "left" else x0 - box[2]
        if gap < -2.0:
            continue     # 縁に食い込んでいる＝表の中のグリフ
        # 縁までの**全幅**が1列ぶんに収まること。隙間の上限では左寄せの広い列を弾いた。
        extent = box[0] - x0 if side == "left" else x1 - box[2]
        if extent > width * 0.30:
            continue
        bands: dict[int, list[dict]] = {}
        for glyph in picked:
            gy = (glyph["bbox"][1] + glyph["bbox"][3]) / 2
            index = max(i for i, y in enumerate(ys[:-1]) if y <= gy) if ys[0] <= gy else -1
            if index < 0 or gy > ys[index + 1]:
                bands = {}
                break
            bands.setdefault(index, []).append(glyph)
        if len(bands) != len(ys) - 1:
            continue
        texts = {i: spell_glyphs(gs) for i, gs in bands.items()}
        if any(len(t) > 24 for t in texts.values()):
            continue

        # 既存セルを1列ずらして、外側に1列足す
        if side == "left":
            for cell in cells:
                cell["column_start"] += 1
                cell["column_end"] += 1
            span = (x0, box[0])
            column = 0
        else:
            span = (box[2], x1)
            column = record["column_count"]
        for index, text in texts.items():
            cells.append({
                "id": f"{record['id']}-outer-{index:04d}",
                "row_start": index, "row_end": index + 1,
                "column_start": column, "column_end": column + 1,
                "bbox": rounded_box((span[0], ys[index], span[1], ys[index + 1])),
                "text": text, "bold": False, "italic": False,
            })
        record["column_count"] += 1
        record["bbox"] = rounded_box((min(box[0], x0), box[1], max(box[2], x1), box[3]))
        cells.sort(key=lambda c: (c["row_start"], c["column_start"]))
        recovered.append(side)
    return ",".join(recovered) or None


def fill_grid_holes(page_chars: list[dict], record: dict) -> int:
    """**グリッドから丸ごと抜けた列**を、行・列の座標とグリフから埋める（1.11.0）。

    罫線が細い/途切れていると、pdfplumberはその列のセルを**1つも作らない**——
    `WCH-LinkUserManual.zh` p4の機能比較表（15行5列）は列0のセルがヘッダ行にしか無く、
    `RISC-V模式`・`ARM-SWD模式-HID设备`…**14個の行見出しがどのセルにも入っていなかった**
    （再突合が「14行すべての1列目が空」として指摘）。列0の座標はヘッダのセルから、行の
    座標は同じ行の他のセルから決まるので、**入れ先は一意**。

    触るのは次を満たすときだけ:

    - 3行以上・2〜12列の表で、単一行/単一列のセルから**全ての行と列の座標が決まる**
    - どのセルにも覆われていない位置（穴）が**同じ列に3つ以上**あり、その3つ以上に文字が在る
    - 穴の矩形（0.5pt内側）に中心が入るグリフだけを取る

    「同じ列に3つ以上」が要——散らばった単発の穴は、図を表と誤検出したページの
    ラベル断片（`ghes`・`tw(NE)`・`SIOX0SIOX1`）で、埋めると意味の無いセルが出来る。
    全corpus実測: 文字が在る穴は90個/50表あるが、**列まるごとの条件を課すとこの1表**
    だけになり、14個の行見出しが完全な形で戻る（誤検出0）。

    `extracted_rows`は触らない——凍結tool19本がそれを読むので影響を`cells`側に閉じる
    （`recover_outer_column`と同じ約束）。
    """
    rows, columns = record["row_count"], record["column_count"]
    cells = record["cells"]
    if rows < 3 or not 2 <= columns <= 12 or not cells:
        return 0
    spans_x: dict[int, list[tuple[float, float]]] = {}
    spans_y: dict[int, list[tuple[float, float]]] = {}
    for cell in cells:
        box = cell.get("bbox")
        if not box:
            continue
        if cell["column_end"] - cell["column_start"] == 1:
            spans_x.setdefault(cell["column_start"], []).append((box[0], box[2]))
        if cell["row_end"] - cell["row_start"] == 1:
            spans_y.setdefault(cell["row_start"], []).append((box[1], box[3]))
    if len(spans_x) < columns or len(spans_y) < rows:
        return 0   # 座標が決まらない列/行があるなら触らない
    xr = {k: (min(a for a, _ in v), max(b for _, b in v)) for k, v in spans_x.items()}
    yr = {k: (min(a for a, _ in v), max(b for _, b in v)) for k, v in spans_y.items()}
    covered = {(row, column)
               for cell in cells
               for row in range(cell["row_start"], cell["row_end"])
               for column in range(cell["column_start"], cell["column_end"])}
    holes: dict[int, list[int]] = {}
    for row in range(rows):
        for column in range(columns):
            if (row, column) not in covered:
                holes.setdefault(column, []).append(row)
    added = 0
    for column, missing in sorted(holes.items()):
        if len(missing) < 3:
            continue
        x0, x1 = xr[column]
        found: list[tuple[int, str]] = []
        for row in missing:
            y0, y1 = yr[row]
            inside = [g for g in page_chars
                      if (g.get("text") or "").strip()
                      and x0 + 0.5 <= (g["bbox"][0] + g["bbox"][2]) / 2 <= x1 - 0.5
                      and y0 + 0.5 <= (g["bbox"][1] + g["bbox"][3]) / 2 <= y1 - 0.5]
            found.append((row, spell_glyphs(inside)))
        if sum(1 for _, text in found if text.strip()) < 3:
            continue
        for row, text in found:
            if not text.strip():
                continue
            y0, y1 = yr[row]
            cells.append({
                "id": f"{record['id']}-hole-{row:04d}-{column:02d}",
                "row_start": row, "row_end": row + 1,
                "column_start": column, "column_end": column + 1,
                "bbox": rounded_box((x0, y0, x1, y1)),
                "text": text, "bold": False, "italic": False,
            })
            added += 1
    if added:
        cells.sort(key=lambda c: (c["row_start"], c["column_start"]))
    return added


def fix_cell_dupes(page_chars: list[dict], record: dict) -> None:
    """セル境界に載った/跨いだグリフの**二重取り**と、reset値の列に降った異物を落とす
    （1.9.0）。`[31:12] R`（右隣`Reserved`の`R`）・`RO R`・`s Description`・reset値の
    `e 0 e`。判定は`logical_tables`の3つで、exporter・parityと同じ関数を通す。

    **下付きの復元より後**に掛ける——`reattach_cell_subscripts`は「組み直した綴りが
    グリフの読み順と完全に一致すること」を歯止めにしているので、先にグリフを落とすと
    その照合が外れて復元が黙って効かなくなる。

    それまではexporterとparityだけが直しており、bundleのセルには二重取りしたグリフが
    残っていた（straddling 4,457・boundary 2,337・reset列 2,200。全corpus実測）。
    `clean_reset_column`は**ヘッダ行を持つ表**でしか列を決められないので、ページ跨ぎの
    継続断片では何もしない（安全側。結合後にexporter側がもう一度掛ける）。"""
    logical_tables.strip_boundary_dupes(record)
    if logical_tables.has_edge_newline(record) or logical_tables.has_short_edge(record):
        logical_tables.strip_straddling_dupes(record, page_chars)
    logical_tables.clean_reset_column(record)
    for key in ("_deduped", "_straddle_stripped", "_reset_cleaned"):
        record.pop(key, None)


# 2カラムが始まる見出し。**Overview/概述は含めない**——overviewの散文は全幅1行で
# （`…microcontroller based on the QingKe RISC-V core`が1行・実測）、これを境界で
# 割ると`ba`と`d`に裂ける。2カラムなのはFeatures（箇条書き）以降。
COLUMN_START_HEADINGS = ("Feature", "主要特性", "功能概述", "产品特性", "產品特性")


def column_boundary(page, lines: list[dict], carried: float | None = None):
    """2カラム（datasheetのfeaturesリスト）なら(列境界x, 開始y)、なければNone。

    pdfplumberの行抽出は左カラムと右カラムを同じy行として1行に結合してしまう
    （`- QingKe…core ● 3-group…`のように左右が混ざる）。Features見出しのある
    datasheetページに限り、**見出しの下**の表外wordのx0を見て、中央域（幅の
    35〜60%）で最大のx0ギャップ（左カラム右端と右カラム左端の間）を列境界に。
    見出しで絞るので製品比較表・register bit図・pin表・overview散文は対象外。

    **見出しはページ1にしか無い**（1.9.3）。箇条書きは次ページへ続くのに見出しは
    刷り直されないので、2ページ目以降が分割されず左右が混ざったまま出ていた
    （H417DS0.en p2・M030DS0.en p2・V007DS0.en p2 ほか。2026-09-07の検証ラウンドが
    high 5件として検出）。`carried`に前ページの列境界xを渡すと、見出しが無くても
    **同じxに±10ptで境界が再検出できたときだけ**続きとして扱う——版面が変わったら
    （表のページ・1カラムに戻ったページ）検出が外れて自然に止まる。
    """
    starts = [line for line in lines if line.get("role") == "heading"
              and any(k in line["text"] for k in COLUMN_START_HEADINGS)]
    if starts:
        y_start = min(starts, key=lambda l: l["bbox"][1])["bbox"][3]
    elif carried is not None:
        # 続きのページ。本文の始まり（header/footer以外の最初の行の上端）から下を見る。
        body = [l["bbox"][1] for l in lines
                if l.get("role") not in ("header", "footer") and (l.get("text") or "").strip()]
        if not body:
            return None
        y_start = min(body) - 1.0
    else:
        return None
    width = float(page.width)
    tables = [t.bbox for t in page.find_tables()]

    def in_table(word) -> bool:
        cx, cy = (word["x0"] + word["x1"]) / 2, (word["top"] + word["bottom"]) / 2
        return any(t[0] <= cx <= t[2] and t[1] <= cy <= t[3] for t in tables)

    words = [w for w in (page.extract_words() or [])
             if not in_table(w) and w["top"] >= y_start]
    def crossings(x: float) -> int:
        """その縦線を跨ぐ語の数。**本物の列境界はほとんど跨がれない**（1.9.4）。

        x0のギャップ方式は、右カラムに字下げの段が複数あると**右カラムの内側**を
        境界に選ぶことがある——V205DS0.zh p1では右カラムがx0≈330から始まるのに、
        段の間の339→353を拾って346.3を境界にし、右カラムの語**33個**を途中で切って
        いた（`crop`は跨いだ語を両側に入れるので、切れ端が二重になって末尾へ落ちる。
        `产品特性`を見出し語に足したことで顕在化した。2026-09-07の検証ラウンド4窓目）。
        左カラムの一番長い語が溝に届くのは普通なので0は要求せず、**少数**で判定する。"""
        return sum(1 for w in words if w["x0"] < x < w["x1"])

    candidates: list[tuple[int, float, float]] = []   # (跨ぐ語, -隙間, x)

    # 候補1: 中央域のx0のギャップ（従来）
    band = [x for x in sorted(w["x0"] for w in words) if width * 0.35 <= x <= width * 0.60]
    if len(band) >= 3:
        gap, mid = 0.0, None
        for a, b in zip(band, band[1:]):
            if b - a > gap:
                # ギャップの中点を境界に——右カラム語の x0 ちょうどにすると、その語
                # （bullet等）が左cropにも intersect して左行末に紛れ込む。
                gap, mid = b - a, (a + b) / 2
        if gap >= 15 and mid is not None:
            candidates.append((crossings(mid), -gap, mid))

    # 候補2: 語の占有幅をx軸へ投影して空白帯を探す。右カラムの字下げが何段もあって
    # x0のギャップでは測れない版面（zh datasheet）を拾う。
    lo, hi = width * 0.30, width * 0.70
    cursor, gap, mid = lo, 0.0, None
    for a, b in sorted((w["x0"], w["x1"]) for w in words):
        if b <= lo or a >= hi:
            continue
        if a > cursor and a - cursor > gap:
            gap, mid = a - cursor, (cursor + a) / 2
        cursor = max(cursor, b)
    if cursor < hi and hi - cursor > gap:
        gap, mid = hi - cursor, (cursor + hi) / 2
    if gap >= 15 and mid is not None:
        candidates.append((crossings(mid), -gap, mid))

    if not candidates:
        return None
    cross, _, best_x = min(candidates)
    if cross > 2:
        return None   # 溝ではなくカラムの内側を割っている
    if carried is not None and not starts and abs(best_x - carried) > 20.0:
        return None   # 前ページと同じ列構造でない——続きとみなさない
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
        # 候補は中央値以下の行だけ（本文どうしの結合を避ける粗い枠）。下付きかどうかの
        # 実判定は下の「隣接する基底との相対サイズ<0.82」が担う——小さいCJKラベルが
        # 多くbody中央値が低いページ（H417DS0 zh p121: body 8.6）で、基底V 11.9に対する
        # 下付きSSA 8.2が中央値比0.95で候補から漏れていた。
        if size == 0 or size > body or not small.get("chars"):
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
            "text": normalize_text(item["text"]),
            "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
        }
        if kind == "line":
            fixed = rotated_line_text(item.get("chars") or [])
            if fixed is not None:
                entry["text"] = normalize_text(fixed)
                entry["_rotated"] = True   # 内部flag。書き出す前に落とす
        out.append(entry)
    return out


def chars(page) -> list[dict]:
    out = []
    for index, item in enumerate(page.chars, 1):
        out.append({
            "id": f"p{page.page_number}-char-{index:06d}",
            # 私用領域だけ直す。重ね描きの畳み込みはしない——glyphは2つ実在する。
            "text": normalize_text(item.get("text", ""), undouble=False),
            "bbox": rounded_box((item["x0"], item["top"], item["x1"], item["bottom"])),
            "font": str(item.get("fontname") or ""),
            "size": round(float(item.get("size") or 0), 3),
            "upright": bool(item.get("upright", True)),
        })
    return out


HEADING_NUMBERED = re.compile(r"^\d+(?:\.\d+){1,3}\s+.*[A-Za-z\u4e00-\u9fff].*$")


def _wrap_joiner(head: str, tail: str) -> str:
    """折り返しの継ぎ目に入れる区切り（`cell_html`の折り返し判定と同じ考え方）。"""
    if CJK_CHAR.search(head[-1]) or CJK_CHAR.search(tail[0]):
        return ""              # CJKは字間が無い
    if head[-1].isalnum() and tail[0].isalnum():
        return " "             # 英単語の折り返し
    if head[-1] in ",;:":
        return " "             # 英文の読点のあとは1字空ける
    return ""                  # 語の途中で折れた（`(y` ＋ `= 1/2)`）


def join_heading_wraps(lines: list[dict]) -> list[tuple[str, str, str]]:
    """**折り返した節見出しの続きを見出しへ繋ぐ**（1.13.0）。繋いだ組を返す。

    節見出しが版面幅を超えると次の行へ折り返すが、**続きは独立した行**になる。
    読む側は行ごとに見出しの正規表現を当てるので、`build_features.py`は
    `1.4.19 … (USBSS) (Not applicable`で切れた題を`evidence/features.csv`に入れて
    いた（続きは`to CH32X305)`。CH32X315DS0.en v1.2。ユーザー指摘）。v1.1では
    `(Not`で切れていて、**新版で切れる位置が動いただけ**で直っていなかった。

    繋ぐのは次の全部を満たすときだけ:

    - 直前が節番号を持つ見出し（`role == "heading"`）
    - 続きが**同じ左マージン**（±1pt）で**すぐ下**（隙間が行高の0.6倍以内）
    - **boldが見出しと同じ**
    - 続きが**それ自身節見出しでない**
    - 見出しの**括弧が閉じていない**、または続きが**小文字で始まる**

    最後の条件が要——これが無いと562件当たり、その大半は
    `9.1.1 NVIC 控制器`＋`● 88个可屏蔽的中断通道`のような**箇条書きの1項目**で、
    繋ぐと壊れる（節見出しと同じ左マージン・同じboldで直下に来る）。全corpus実測:
    節見出し17,400のうち候補744、次も見出し160を除いて584、**この条件で22**。
    22件は全部本物の折り返し（DMAレジスタの`(x=…,`＋`y=1/2)`が大半）。うち3件は
    本文が節番号に見えて見出しと誤判定されたものだが、**繋ぐと正しい文になる**ので
    害は無い。

    続きの行には`merged_into`（見出しのid）を付けて残す——`join_split_lines`と同じ
    約束で、読み手はそれを飛ばすだけでよい。
    """
    joined: list[tuple[str, str, str]] = []
    ordered = sorted((line for line in lines if (line.get("text") or "").strip()),
                     key=lambda line: (round(line["bbox"][1], 1), line["bbox"][0]))
    for index, line in enumerate(ordered[:-1]):
        head = (line.get("text") or "").strip()
        if line.get("role") != "heading" or not HEADING_NUMBERED.match(head):
            continue
        follow = ordered[index + 1]
        tail = (follow.get("text") or "").strip()
        if not tail or follow.get("merged_into") or HEADING_NUMBERED.match(tail):
            continue
        if abs(follow["bbox"][0] - line["bbox"][0]) > 1.0:
            continue
        height = line["bbox"][3] - line["bbox"][1]
        if not 0 <= follow["bbox"][1] - line["bbox"][3] <= height * 0.6:
            continue
        if bool(follow.get("bold")) != bool(line.get("bold")):
            continue
        unbalanced = (head.count("(") != head.count(")")
                      or head.count("\uff08") != head.count("\uff09"))
        if not (unbalanced or tail[:1].islower()):
            continue
        separator = _wrap_joiner(head, tail)
        line["text"] = head + separator + tail
        follow["merged_into"] = line["id"]
        joined.append((head, separator, tail))
    return joined


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


def merge_scanline_images(items: list[dict]) -> int:
    """**走査線に刻まれたrasterを1枚に束ねる**（1.10.1）。束ねた枚数を返す。

    数式や小さな図を、PDFが高さ1pt未満の帯を何百枚も並べて描くことがある——
    `CH32V205DS0.en` p64の「Formula 1: Maximum R_AIN」は**277枚**（高さ0.72pt）に
    刻まれていた。1枚ずつでは`render_assets`の大きさ条件に届かず描画されないので、
    exporterが`<!-- image: … -->`を277行吐き、**数式の中身がMarkdownから完全に
    消えていた**（`CH32L103DS0.zh` p49も同型。2026-09-07の検証ラウンドがhigh 2件）。

    resource名を持たない（inline）小さな画像を**y方向の帯**でまとめ、帯に10枚以上
    あってその囲いが縦横とも8pt以上なら1枚に置き換える。帯の切れ目は縦の隙間4pt。
    表の罫線代わりに置かれた細い画像を巻き込まないよう、名前つきのresource画像
    （`X49`のような実在名）は対象外。"""
    small = sorted((i for i in items
                    if i["type"] == "image" and not i.get("name")
                    and i["bbox"][3] - i["bbox"][1] <= 12.0),
                   key=lambda i: i["bbox"][1])
    if len(small) < 10:
        return 0
    bands: list[list[dict]] = []
    for item in small:
        if bands and item["bbox"][1] - max(g["bbox"][3] for g in bands[-1]) <= 4.0:
            bands[-1].append(item)
        else:
            bands.append([item])
    merged = 0
    for band in bands:
        if len(band) < 10:
            continue
        x0 = min(g["bbox"][0] for g in band); x1 = max(g["bbox"][2] for g in band)
        y0 = min(g["bbox"][1] for g in band); y1 = max(g["bbox"][3] for g in band)
        if x1 - x0 < 8.0 or y1 - y0 < 8.0:
            continue
        keep = band[0]
        keep["bbox"] = rounded_box((x0, y0, x1, y1))
        keep.pop("source_size", None)
        drop = {id(g) for g in band[1:]}
        items[:] = [i for i in items if id(i) not in drop]
        merged += len(band) - 1
    return merged


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


# PDFが記号フォント（Wingdings/Symbol）のグリフを**私用領域のコードポイント**として
# 文字層に書いているもの。そのまま出すと読めないだけでなく、**文字として壊れている**
# ので、bundleを読む抽出器にも壊れた字が渡る（全corpus 9,291個・65文書。lines/words/
# page.text/cells/charsの全部に入っていた）。実測したコードポイントとフォントの対応:
# 0xf06c=Wingdings-Regular 9,233・NSimSun 1・SimHei 1、0xf0b7=SymbolMT 24・SimHei 5、
# 0xf0b4=SymbolMT 18、0xf06e=Wingdings-Regular 8、0xf0b1=SymbolMT 1。CJKフォントの
# 7件も文脈は同じ（箇条書き記号）なのでフォントで分けない。元のグリフが何だったかは
# geometryの`font`が持ち続けるので、この置換で情報は失われない。
PUA_REPLACEMENTS = {
    "\uf06c": "●",   # Wingdings 0x6C: 箇条書きの■/●
    "\uf06e": "■",   # Wingdings 0x6E
    "\uf0b7": "•",   # Symbol 0xB7
    "\uf0b4": "×",   # Symbol 0xB4
    "\uf0b1": "±",   # Symbol 0xB1
}


def _undouble(part: str) -> str:
    """全グリフが2回ずつ拾われた行（`OOSSCC__IINN`→`OSC_IN`、`CCPPOOLL==00`→`CPOL=0`）を
    畳む。PDFが太字風に同じ文字を重ね描きし、pdfplumberが両方を拾ったもの（全corpus143件）。
    条件: 空白なし・6文字以上・偶数長・全ての隣接ペアが同じ・**hex桁以外の文字を含む**
    （`0000FF`のような正当な16進値は偶然ペアになるので除外）。

    畳むのは**文字層だけ**——geometryの`chars`には2つのグリフが実在するので触らない
    （重ね描きだったという事実はそこに残る）。"""
    body = part.strip()
    if (len(body) < 6 or len(body) % 2 or " " in body
            or any(body[i] != body[i + 1] for i in range(0, len(body), 2))
            or len(set(body)) < 2
            or all(ch in "0123456789abcdefABCDEF" for ch in body)):
        return part
    return part.replace(body, body[::2])


def normalize_text(text: str, undouble: bool = True) -> str:
    """文字層の正規化: 私用領域コードポイントの置換と、重ね描きの畳み込み。

    **exporterではなくここで行う**——見た目を整えるためではなく、文字が壊れているから
    （1.8.0でexporterから移した。それまではMarkdownだけが直り、bundleのlines/cells/
    page.textには私用領域の字が残っていた）。"""
    for pua, real in PUA_REPLACEMENTS.items():
        if pua in text:
            text = text.replace(pua, real)
    if not undouble:
        return text
    if "\n" in text:
        return "\n".join(_undouble(part) for part in text.split("\n"))
    return _undouble(text)


def strip_column_boundary_dupes(lines: list[dict], boundary: tuple) -> int:
    """2カラム分割の境界に載ったグリフが**右列の行頭に二重取り**されたぶんを落とす（1.9.0）。

    `column_boundary`でx_splitに沿って左右へ切ると、境界をまたぐ1グリフが両側のcropに入る。
    右列の行は`r ● GPIO port`・`n - Built-in system clock…`・`V - Support TIMx/ADC…`のように
    **左列の末尾文字＋空白**で始まる（2カラム判定される16ページの全部で発生。datasheetの
    表紙なので読者が最初に見る面。2026-09-06の検証ラウンドが`m - Analog input range`で検出）。

    条件は`strip_boundary_dupes`（セル版）と同じ形にする——同じ高さ（±1.5pt）の左列の行の
    末尾非空白文字と一致し、それがASCII英数字1字で、直後が空白であること。"""
    x_split, y_start = boundary
    below = [l for l in lines if l["bbox"][1] >= y_start]
    left = [l for l in below if (l["bbox"][0] + l["bbox"][2]) / 2 < x_split]
    right = [l for l in below if (l["bbox"][0] + l["bbox"][2]) / 2 >= x_split]
    fixed = 0
    for r in right:
        head = (r.get("text") or "").lstrip()
        if len(head) < 2 or head[1] not in " \t" or not (head[0].isascii() and head[0].isalnum()):
            continue
        peer = next((l for l in left if abs(l["bbox"][1] - r["bbox"][1]) <= 1.5), None)
        if peer is None:
            continue
        tail = (peer.get("text") or "").rstrip()
        if tail and tail[-1] == head[0]:
            r["text"] = head[2:].lstrip()
            fixed += 1
    return fixed


def fix_line_subscripts(page_chars: list[dict], lines: list[dict]) -> int:
    """本文行でも、基底から離れた下付き/上付きをgeometryで戻す（1.8.0）。

    `merge_subscript_lines`（1.6.0）は**別の視覚行として拾われた小行**を本文行へ差し込む
    が、同じ行の中で基底から離れたものは残る——`每 2^20 个`が`每220个`に、CRCの
    `x^32+x^26+…`が`x32+x26+…`に潰れていた（全corpus805行・61文書）。**指数が桁に化ける
    ので値が違う**: bundleの行を読む抽出器には`220`が渡る。表セルと同じ
    `logical_tables.reattach_cell_subscripts`に1セルの表として渡すだけで、歯止め
    （グリフ読み順との完全一致）も共通。`page["text"]`は`extract_text()`が別に作るので
    そちらは触らない（凍結toolのbyte一致を保つ。`merge_subscript_lines`と同じ扱い）。"""
    fixed = 0
    for line in lines:
        raw = line.get("text") or ""
        if not raw.strip() or not logical_tables.has_subscript_shape({"cells": [{"text": raw}]}):
            continue
        pseudo = {"cells": [{"text": raw, "bbox": line["bbox"], "row_start": 1, "row_end": 2,
                             "column_start": 0, "column_end": 1}]}
        if logical_tables.reattach_cell_subscripts(pseudo, page_chars):
            line["text"] = pseudo["cells"][0]["text"]
            fixed += 1
    return fixed


def _column_edges(cells: list[dict]) -> list[float]:
    return sorted({round(c["bbox"][0], 1) for c in cells}
                  | {round(c["bbox"][2], 1) for c in cells})


def chain_uncaptioned(table: dict, tail: dict | None, height: float) -> bool:
    """**caption を持たない表を、前ページの最後の表へ繋ぐ**（1.10.2）。繋いだら真。

    `continues_from_previous`は「過去にcaption付きの表がある」ことを前提にしていた
    （`continues = bool(consecutive and previous_logical_id)`）ので、**caption が無い表は
    ページを跨いで繋がらなかった**。`CH32H417DS0.en`の比較表がそれで、p3とp4が別の論理表に
    なり、(a) p3の最終セルが`USBHS (USB`で切れたまま、(b) p4に`'2.0)'`だけの**幽霊行**、
    (c) p4に刷り直されたヘッダが列数を狂わせる——という3つの症状を同時に出していた。
    結合表でしか効かない`fold_boundary_spills`（境界のspillを畳む）と
    `drop_repeated_headers`（刷り直しヘッダを落とす）が、そもそも届いていなかった。

    条件は厳しくする——`logical_id`が変わると`extract_low_power`のフラグメント束ねが
    変わり`operating_conditions`に影響するため。双方caption無し・列数一致・**列境界xが
    ±2ptで一致**（最も強い証拠）・前の表はページ下端近く（75%以降で終わる）・この表は
    上端近く（35%以内に始まる）。全corpusで候補は**18件**（すでに繋がっている表は5,734件）
    で、実物を確認するとどれも本物の継続表（割込ベクタ表・比較表・アクセス属性の凡例）。
    """
    if tail is None or table["caption"] or table["continues_from_previous"]:
        return False
    if tail["captioned"] or tail["column_count"] != table["column_count"]:
        return False
    mine = _column_edges(table["cells"])
    if len(mine) != len(tail["edges"]):
        return False
    if any(abs(a - b) > 2.0 for a, b in zip(mine, tail["edges"])):
        return False
    if tail["bottom"] < tail["height"] * 0.75 or table["bbox"][1] > height * 0.35:
        return False
    table["logical_id"] = tail["logical_id"]
    table["continues_from_previous"] = True
    return True


def cell_text(page, bbox) -> str:
    # `Table.extract()`は結合セルを矩形行列に平坦化する。物理セルの矩形で
    # cropし、rowspan/colspanを持つセルに文字を残す。
    return normalize_text(
        (page.crop(bbox).extract_text(x_tolerance=3, y_tolerance=3) or "").strip())


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


def _text_with_heading_wraps(text: str,
                             joins: list[tuple[str, str, str]]) -> str:
    """ページ本文で「見出し\n続き」を繋いだ形へ置き換える（見付かった分だけ）。"""
    for head, separator, tail in joins:
        text = text.replace(f"{head}\n{tail}", head + separator + tail, 1)
    return text


def page_record(page, lang: str, source_sha256: str,
                previous_logical_id: str | None,
                previous_page: int | None,
                number_occurrences: dict[str, int],
                repeated_top: set, repeated_bottom: set,
                top_texts: set, bottom_texts: set,
                document_type: str = "",
                carried_split: float | None = None,
                table_tail: dict | None = None,
                ) -> tuple[dict, dict, str | None, float | None, dict | None]:
    page_chars = chars(page)
    two_column = None   # (列境界x, 開始y)。読み順のkeyが左列→右列を保つのに使う
    lines = text_items(page, "line")
    classify_lines(lines, page_chars, float(page.height), repeated_top, repeated_bottom,
                   top_texts, bottom_texts)
    # datasheetのoverview/featuresページは2カラム——pdfplumberが左右を1行に
    # 結合するので、列境界が見つかれば左右別々に行を組み直す（左カラム全行→
    # 右カラム全行の読み順）。見出しで絞るので他ページは触らない。
    if document_type == "datasheet":
        boundary = column_boundary(page, lines, carried_split)
        if boundary:
            lines = text_items(page, "line", boundary=boundary)
            classify_lines(lines, page_chars, float(page.height),
                           repeated_top, repeated_bottom, top_texts, bottom_texts)
            strip_column_boundary_dupes(lines, boundary)
            two_column = boundary
    # 行の中で基底から離れた下付き/上付きをgeometryで戻す（`2^20`が`220`に潰れる）。
    # 2カラム再抽出のあとに掛ける——行が組み直されると位置が変わるので。
    fix_line_subscripts(page_chars, lines)
    # 折り返した節見出しの続きを見出しへ繋ぐ（textにも同じ結合を反映する）。
    heading_wraps = join_heading_wraps(lines)
    # 列境界で割れた本文行を繋ぐ。`reading_order`より前でよい——`merged_into`を付けた
    # 行はそのまま残るので順序は変わらない。
    join_split_lines({"lines": lines})
    words = text_items(page, "word")
    page_drawings = drawings(page)
    # 走査線に刻まれたrasterを1枚に束ねる（数式が277枚に割れていた）。
    merge_scanline_images(page_drawings)
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
        # 回転の組み直しの**後**——直った文字に対して下付きを戻す。
        fix_cell_subscripts(page_chars, tables[-1])
        fix_cell_dupes(page_chars, tables[-1])
        # 表領域の外に落ちた最外列を取り込む（入れ先が一意に決まるものだけ）。
        recover_outer_column(page_chars, tables[-1], tables)
        # グリッドから丸ごと抜けた列を、行・列の座標とグリフから埋める。
        fill_grid_holes(page_chars, tables[-1])
        # ページの最初の表なら、caption無しでも前ページの最後の表へ繋ぐか試す。
        if table_index == 1 and chain_uncaptioned(tables[-1], table_tail, float(page.height)):
            previous_logical_id = tables[-1]["logical_id"]
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
    # **2カラムのページは「左列を全部→右列を全部」の順にする。** `text_items`が
    # boundary付きで正しくその順に組んでいたのに、ここで`(top, x0)`で並べ直していたため
    # **分割が打ち消され**、Featuresの箇条書きが左右交互に出ていた（全datasheetの1ページ目。
    # 生成物では`- 2 output channels each…`が`- Core`より先に出ていた。2026-09-06の検証
    # ラウンドが検出）。右列の項目に版面の高さを足して、列の中の上下は保ったまま列の
    # 順を優先させる。表題帯（y_startより上）は影響を受けない。
    height = float(page.height)

    def reading_key(item: dict) -> tuple:
        top, x0, x1 = item["bbox"][1], item["bbox"][0], item["bbox"][2]
        if two_column:
            x_split, y_start = two_column
            if top >= y_start and (x0 + x1) / 2 >= x_split:
                return (top + height, x0, item["type"])
        return (top, x0, item["type"])

    order.sort(key=reading_key)
    # 表題が折り返して途中で切れているものを全文にする（1.8.0）。それまでbundleは
    # **1行目だけ**を持ち、exporterとextract_low_powerが各々`caption_full`を呼んで
    # 繋ぎ直していた——同じ修復を2箇所で掛けていたので、根で1回にする。繋いだ続き行の
    # idを残すので、読み順から外す側（exporter）はそれを見れば済む。
    # `reading_order`が要るのでここで掛ける。
    scope = {"lines": lines, "reading_order": order}
    for table in tables:
        if not table["caption"]:
            continue
        full, used = logical_tables.caption_full(scope, table)
        if used:
            table["caption"]["text"] = full
            table["caption"]["continuation_line_ids"] = used
    record = {
        "schema_version": SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "number": page.page_number,
        "width": round(float(page.width), 3),
        "height": round(float(page.height), 3),
        "rotation": int(getattr(page, "rotation", 0) or 0),
        # `extract_text()`は行の組み直しを通らない別の面（pdfplumber互換。凍結toolが
        # これを読む）。**文字の壊れだけは同じく直す**——PUAの字と重ね描きは互換の
        # ためのものではなく単に壊れているので、この面に残す理由が無い。
        # 折り返した見出しは`text`でも1行にする——読む側（凍結tool含む）は
        # `extract_text()`の行ごとに見出しの正規表現を当てるので、ここが分かれて
        # いると題が切れたまま正本CSVへ入る。見付からなければ何もしない（安全側）。
        "text": _text_with_heading_wraps(
            normalize_text(page.extract_text() or ""), heading_wraps),
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
    tail = None
    if tables:
        last = max(tables, key=lambda t: t["bbox"][3])
        tail = {"logical_id": last["logical_id"], "column_count": last["column_count"],
                "edges": _column_edges(last["cells"]), "bottom": last["bbox"][3],
                "height": float(page.height), "captioned": bool(last["caption"])}
    return (record, geometry, previous_logical_id,
            (two_column[0] if two_column else None), tail)


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
    carried_split = None   # 前ページの列境界x。2カラムの続きページを見分けるのに使う
    table_tail = None      # 前ページ最後の表の形。caption無しの継続を見分けるのに使う
    with pdfplumber.open(pdf_path) as pdf:
        repeated_top, repeated_bottom, top_texts, bottom_texts = margin_repeats(pdf)
        for page in pdf.pages:
            record, geometry, previous_logical_id, carried_split, table_tail = page_record(
                page, lang, source_sha256, previous_logical_id,
                previous_page, number_occurrences, repeated_top, repeated_bottom,
                top_texts, bottom_texts, document_type, carried_split, table_tail)
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
