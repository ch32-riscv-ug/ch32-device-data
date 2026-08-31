# PDF→構造化文書→抽出 PoC

作成: 2026-08-31。この文書は[全PDF構造化ワークフロー](structured-document-workflow.ja.md)
に先立つ**回帰標本**の記録。対象は [worklist A11](worklist.ja.md) の消費電流と
ウェイクアップ時間。一度目の実装では中英で読む表集合が違うまま値を対応付け、
`I_DD` 83行中18行を偽の conflict にした。PDFの表認識と、電気特性の意味を読む
処理を同時に行う限り、この2種類の失敗を区別しにくいため、工程を分ける。

## このPoCの位置付け

最終範囲は電気特性章ではなくdatasheet全体とRM全体である。ここで作った0.1形式と
抽出器は、難しい表で「PDF変換の成否」と「意味抽出の成否」を分けられるか確認する
ために残す。実運用形式の候補として、全ページbundleの0.2を設計・PoCした。

## 当時の結論

採る工程は次の5段階。

1. PDFを、意味を解釈しない構造化JSONへ変換する
2. JSONの表番号・物理セル・結合・PDF座標を検査する
3. 承認済みJSONだけから電気特性を抽出する
4. 中英の値を照合して `evidence/operating_conditions.csv` にする
5. JSONから人向けの中英横並びHTMLを生成する

Markdownは検索・翻訳用の派生表示には使えるが、結合セルを表現できないため
中間正本にはしない。中間正本はJSON、レビュー表示はHTMLとする。

## 変換器の実測

難しい表を持つ V003・L103・H417・V007 で Docling 2.123.1 と、現在依存している
pdfplumber 0.11.10 を比較した。DoclingはOCRを切り、TableFormer accurateを使った。

| 対象 | Docling | pdfplumberとの比較 |
|---|---:|---|
| V003英版 p.18–22 | 67.54秒、16物理表 | 結合セル・座標は取れた。改ページ表と見出しだけの断片は別表になる |
| V003中文版 p.16–19 | 38.99秒、13物理表 | 中英とも論理表は3-5〜3-15の13表 |
| L103英版 p.44 | 14.09秒 | pdfplumber 25行に対してDocling 24行 |
| H417英版 p.97 | 2.55秒 | pdfplumber 4行に対してDocling 3行 |
| V007英版 p.48 | 6.39秒 | 3表とも行列は一致 |

L103/H417でDocling側に1行ずつ欠落があり、3代表ページの合計はDocling約23秒、
pdfplumber約0.6秒だった。Doclingのモデル・PyTorch一式も一時環境で数GBになる。
この資料群ではDoclingを主経路にはせず、難所の独立比較に使う。主経路は
pdfplumberが返す物理セルを、製品非依存の自前JSONへ写す。

## 中間JSON 0.1

スキーマは `schemas/structured-document.schema.json`。変換器は
`tools/convert_structured.py`。

- 元PDF名、言語、SHA-256、全ページ数、変換対象ページ
- 変換器と版、座標系
- ページごとの行テキストとbbox
- 物理表断片と論理表ID、表番号・キャプション、継続関係
- 物理セルの原文、bbox、row/columnの開始・終了（rowspan/colspan）
- 文書・表ごとの `unreviewed / approved / rejected`

資料側の誤記は変換時に直さない。V007英版の2個目の `3-9-2` も原文どおり残し、
検査で中文版の `3-9-3` と食い違うことを示す。変換結果はまだPoCなので
`.cache/structured/` に置き、正本の `evidence/` には入れない。

```sh
uv run tools/convert_structured.py \
  /home/mt/dev_wch/CH32V003/datasheet_en/CH32V003DS0.PDF \
  --lang en --pages 18-22

uv run tools/check_structured.py \
  .cache/structured/CH32V003DS0.zh.structured.json \
  .cache/structured/CH32V003DS0.en.structured.json
```

V003は中英で表番号列が一致し、検査を通る。V007の電気特性章全体では両版とも
表題は38件だが、英版の `9-2` 重複と、14番目の `en=9-2 / zh=9-3` を抽出前に検出する。
また、タイミング図を表と誤認した小さい候補ではセル重複も検出した。この候補を
承認対象から外す判断は値抽出より前に行える。

## JSONからの抽出結果

PoC抽出器は `tools/extract_operating_structured.py`。PDFを開かず、中間JSONだけを読む。
意味の読み方を変えた影響と混ぜないため、記号・単位・複数Typ列の規則は
`build_operating.py` の作業中実装を再利用している。

4文書の消費電流・ウェイクアップ表について、JSON経由と従来のPDF直読みの
`(表番号, 記号, min, typ, max, unit)` の多重集合を比較した。V007だけは英版の
表番号誤記を既知として値集合で比較した。

| 文書 | zh | en | 主な対象行 |
|---|---:|---:|---|
| V003 | 対象86行すべて一致 | 対象86行すべて一致 | `I_DD` 84行、`t_wusleep=30us`、`t_WUSTDBY=200us` |
| L103 | 184/184行一致 | 168/168行一致 | `I_DD` 169/153行、sleep/stop/standby wake各1行 |
| H417 | 109/109行一致 | 110/110行一致 | `I_DD` 92/93行、sleep wake各1行、stop wake各2行 |
| V007 | 64/64行一致 | 64/64行一致 | `I_DD` 50行ずつ、standby wake各1行 |

全電気特性では、英版だけが持つ行と `DuTy` / `DuCy` のような原典の綴り差は残る。
これは変換失敗と分離して確認できるので、資料差として扱うか正規化するかを後段で
判断できる。

## 人向け表示

`tools/render_structured.py` は中英JSONを、表番号ごとの横並びHTMLへする。セルの
rowspan/colspanを復元し、ページ、断片ID、bbox、レビュー状態を表示する。ページ本文も
折りたたみで読める。翻訳は将来、行ID・セルIDにぶら下げ、原文セルは変更しない。

```sh
uv run tools/render_structured.py \
  .cache/structured/CH32V003DS0.zh.structured.json \
  .cache/structured/CH32V003DS0.en.structured.json \
  --out .cache/structured/CH32V003DS0.review.html
```

## このPoCから全体ワークフローへ移したこと

- レビュー結果を再変換で消さないsidecar形式にした
- datasheet/RM共通の全ページbundle、hash検査、精密幾何層を追加した
- Markdownとページ別HTMLを追加した
- 残りは全55版への展開、全抽出器の切替、承認済みblockだけを読む運用である
