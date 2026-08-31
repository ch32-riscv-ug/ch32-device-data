# PDF構造化 PoC・実現可能性・移行計画

作成: 2026-08-31。対象は電気特性だけではなく、**データシート全体と
リファレンスマニュアル（RM）全体**。抽出器ごとにPDFを直接読む現行方式を、次へ
全面的に置き換えられるかをPoCで確認し、移行手順を決める。**この検討の作業範囲は
PoCと文書化まで**であり、全資料の実変換、既存抽出器の切替、性能最適化は行わない。

```text
原本PDF
  ↓ 変換（文書の意味はまだ決めない）
構造化bundle ─→ JSON/Markdown/HTMLを人が確認・翻訳
  ↓ 構造検査 + review sidecar
領域別抽出（型番、pin、電気特性、register、DMA、図…）
  ↓ 原文ID・ページへjoin
evidence CSV
  ↓
人向けREADME / viewer
```

## 目的――なぜPDF直読みを続けないか

現行は、`tools/`にある領域別toolがそれぞれPDFを開き、ページ選択・表認識・文字の
補正・意味抽出を一度に行う。同じPDFでもtoolごとに読んだページや表の境界が違い、
最終CSVに誤りが見つかったとき、原因が次のどこにあるか切り分けにくい。

1. PDFから文字・表・図を取り出す変換の失敗
2. 改ページ、結合セル、読み順など文書構造の復元失敗
3. 構造化済みの原文から値や関係を読む意味抽出の失敗
4. zh/enの対応付け、正規化、CSVへの統合の失敗

領域別のPDF直読みを追加し続けても、個々のtoolの局所的な例外が増え、検証範囲と精度が
本当に改善したかを測りにくい。A11で起きた18件の偽 conflict も、PDF表の読取と電気特性の
対応付けが同じ工程にあったため、最終結果を見るまで原因を区別できなかった。

そこで、PDFを一度だけ中間形式へ変換し、検証を二つの独立したゲートに分ける。

- **変換検証**: PDFと中間形式を比較し、ページ、原文、表、cell、span、bbox、読み順を確認
- **抽出検証**: 承認済み中間形式だけを入力にし、期待する値・関係・CSV行を確認

変換器を変更した影響と、領域別抽出規則を変更した影響を別々の差分として確認できる。
一つの変換結果を複数の抽出器、テスト、人のレビューで共有できるため、同じPDF解釈を
toolごとに再実装する必要もなくなる。

## 人間向け表示とリンク可能性（分割仕様は未定）

中間形式を置く主目的は検証の分離だが、副作用として人が読みやすいMarkdown/HTMLを
同じ原文から生成できる。原文自体は変更せず、見出し、段落、表、画像、注記、翻訳などを
block/cell IDへ結び付ける。

各要素は少なくとも`document ID / source SHA-256 / language / source page / block ID / bbox`を持つ。
固定するのはこの識別子までで、人間向け表示を1文書1ページにするか、章単位、PDFページ
単位にするかは今後決める。中間bundleの`pages/*.json`は原本座標と差分を扱うための内部
分割であり、画面やMarkdownの分割単位を規定しない。

どの表示単位を選んでも、HTML生成時にblock IDをanchorへ割り当てれば、概念上は次のように
該当表をURLで指示できる。URLのpath部分はviewer仕様決定後に定める。

```text
.../<viewer-defined-route>#p18-table-002
```

元PDFの`#page=18`へのリンクも生成可能で、viewer側では該当blockを強調表示できる。将来の
semantic tag、翻訳、レビュー判断、抽出されたCSV行のprovenanceは、原文JSONへ直接
書き込まず、安定IDをkeyにしたsidecarへ保存する。これにより「このCSV値は原文のどこか」
をURLで共有でき、翻訳や注釈を追加しても原文hashを変えずに済む。

## 対象と境界

`catalog/documents.csv`で現在assignedの主対象は、datasheet 34版（zh 18 / en 16）と
reference-manual 21版（zh 11 / en 10）の計55版。将来の生成対象には依存元であるcore manual
8版とPACKAGE.PDF 2版も含めるが、最初の移行完了条件はdatasheet＋RMの55版とする。

文書種別で後段ロジックは分ける。datasheetは型番比較・pin・ordering・電気特性・
特徴・図を、RMは章・register/field・remap・DMA・timer・memoryを読む。ただし原本、
座標、表、改ページ、review、原文への参照方法は共通にする。画像のpixel cropだけは
意味データではないため、原本hashを確認する別のasset rendererに残す。

## 中間形式案 0.2（PoC）

PoCの置き場所は `.cache/structured-documents/<document-stem>.<lang>/`。1文書を巨大JSONに
せず、差分確認と遅延読み込みができるbundleにする。

```text
manifest.json                 文書種別、言語、原本hash、変換器、全pageのhash
pages/0001.json               読める基本層: 行、語、役割、表、読み順、画像参照
geometry/0001.json.gz         精密層: 全文字と全描画命令のbbox
review.json                   人の承認・却下。再変換では上書きしない
```

基本層は整形前の原文とbboxを保持し、行に`heading / paragraph / list-item / header /
footer`を付ける。表は次の両表現を同時に持つ。

- 物理セルのbboxとrowspan/colspan: 原本構造を確認するため
- pdfplumber互換の平坦化行とrow座標: 既存抽出器を無損失で移行するため

全文字座標を基本層からgzip精密層へ分けたところ、V003英版datasheet全37ページは
16MBから3.6MBになった。V003英版RMは188ページを全ページ変換できている。スキーマは
`schemas/structured-document-{manifest,page,geometry,review}.schema.json`。

## 検証ゲート

PoCの`tools/check_document_bundle.py`はschema、原本・page・geometryのSHA-256、全ページ性、
ID、bbox、表のspan、読み順、review参照を検査する。本実装では、抽出時に原本hashと
bundleを照合し、欠落・古いbundleでは停止する入口を1つ設ける。PDFへのsilent fallbackは
置かない。

V003英版datasheetでは、従来のPDF直接読取と構造化bundle経由を全37ページ比較し、
本文、行、語、文字数、line/rect/curve/image数、表の平坦化内容、結合セルを含む
row座標がすべて一致した。`extract_products.py`の最終結果も4型番・notesを含め完全一致。
V003英版RM（188ページ）では`extract_registers.py`の結果が旧経路と新経路で
310 fields・notes 16件まで一致した。
電気特性4文書での値一致は[先行PoC](structured-extraction-poc.ja.md)を回帰試験として
残す。

## 実現可能性の判定

**条件付きで実現可能**と判断する。構造化層を挟んでもdatasheetの型番表、電気特性表、
RMのregister field表を失わず、原本の誤記と抽出失敗を別々に確認できた。中間JSONから
Markdown/HTMLを生成できるため、検索・翻訳・人のレビューもPDF直読より行いやすい。

ただし、次はPoCで未確定のため本実装開始時のゲートにする。

- 大型RMの全ページ変換時間と総容量。V003 RMは27MBだったが文書間の振れ幅が大きい
- 全文字への完全なJSON Schema検査は大型RMで高コスト。基本層は完全検査し、精密層は
  hash＋envelope＋必要箇所の検査に分ける案をベンチマークする
- 表でない罫線図を表と誤認する候補。自動修正せずreviewで承認・却下する
- zh/enで表番号や章構成自体が違う場合。位置ではなくcanonical IDをreview sidecarに持つ
- pixel cropは構造化JSONだけでは再現しない。原本hashを固定したasset工程として分離する

### 精度は上がるか

全体的なデータ精度が上がる、という期待は妥当。ただし、中間形式そのものがPDF認識を
自動的に正しくするわけではない。精度向上の主因は次の運用上の変化にある。

| 効果 | 精度への寄与 |
|---|---|
| PDF変換を全抽出器で共有 | toolごとのページ・表認識の不一致をなくす |
| 原文ID・bbox・hashを保存 | 誤った値を原文まで機械的に追跡できる |
| 変換と意味抽出を別々に回帰試験 | 変更が壊した工程を限定できる |
| JSONからHTML/Markdownを生成 | 人がPDFと構造を比較しやすくなる |
| review sidecar | 原典の誤記、変換誤り、抽出判断を混ぜずに記録できる |
| 同じ中間形式へ複数の抽出器を適用 | 領域間で共通する事実を相互検査できる |

逆に、変換器の系統的な誤りを全抽出器が共有する危険もある。そのため原本との標本比較、
文書ごとの変換状態、別engineによる難所比較、未承認blockを正本へ流さないゲートが必要。
目標は「常に正しくなる」ことではなく、誤りを早く発見し、原因と影響範囲を説明できる
状態にすることである。

## 既存tool・CSVとの関係

本実装を開始するときは、現行経路を動かしながら逐次改造せず、**legacy baselineとして
凍結**する。

- 現在の`tools/`は既存CSVを再現する参照実装として更新を止める
- `catalog/`、`evidence/`、`index/`のCSVもbaselineとして凍結し、行数とSHA-256を記録する
- 新toolは凍結CSVへ直接書かず、別のcandidate出力先へ書く
- 旧toolと新toolの出力差分を`unchanged / added / changed / missing`に分ける
- 既存値と違うこと自体を誤りとはしない。原文リンクを確認し、旧側の誤りも修正対象にする
- 移行判定が終わるまでconsumerが読む正本CSVを切り替えず、旧新のdual-writeもしない

通常の機能追加や精度修正は新経路だけで行う。凍結後に旧toolへ修正が必要になった場合は、
baselineを暗黙に動かさず、明示的に凍結を解除して版とhashを更新する。

今回追加した`tools/convert_*`等は形式を評価する**使い捨て可能なPoC**であり、そのまま
本番tool群へ増築しない。本実装は既存の`tools/`から分離し、例えば次のように工程単位で
配置する。

```text
pipeline/
  README.ja.md               全工程、入力、出力、承認ゲート
  common/                    ID、hash、座標、schema読込
  ingest/                    PDF → structured bundle
  review/                    検査、annotation、HTML/Markdown
  extract/
    datasheet/               型番、pin、ordering、電気特性、feature
    reference_manual/        register、remap、DMA、timer、memory
    common/                  文書種別をまたぐ抽出
  reconcile/                 zh/en照合、旧CSVとの差分、provenance
  publish/                   candidate CSV → 承認済み正本
  checks/                    unit、fixture、旧新回帰、coverage
```

schema、設定、fixtureも各工程から参照できる決まった場所へ集め、スクリプト名だけでは
入力・出力・責務が分からない現状を繰り返さない。

### 置き換えの単位と時期

置き換えはCSV単位でよい。ただし、そのCSVが参照する全PDFについて中間bundleが揃い、
変換検証を通っていることを前提にする。推奨は次のhybrid方式。

1. datasheetとRMの基本層を広く変換し、文書inventory・ID・review手順を先に固定する
2. 代表的な文書で精密層と難しい表を確認する
3. 依存範囲が小さいCSVから、新toolでbaselineとの比較を開始する
4. CSVごとに同等以上と判定できたら、そのCSVだけ正本生成元を切り替える
5. 共通bundleへ依存するCSVが十分移行した時点で、旧PDF直読みtoolを実行経路から外す

全中間変換の完了を待って一度に置き換える必要はないが、1つのCSVの入力文書が旧PDF直読みと
中間形式に混在する状態は避ける。CSV単位の完了条件は、schema互換、既存行の説明できない
欠落0、追加・変更行の原文リンク、consumer検査合格、再実行で同一結果、の5点とする。

## 人が見る形式のPoC

JSONは正本、MarkdownとHTMLは再生成可能な表示とする。以下は変換可能性を確認するための
PoCであり、最終的な画面構成、分割単位、navigation、URL pathの仕様ではない。

```sh
uv run tools/convert_document.py \
  /home/mt/dev_wch/CH32V003/datasheet_en/CH32V003DS0.PDF \
  --lang en --document-type datasheet

uv run tools/check_document_bundle.py \
  .cache/structured-documents/CH32V003DS0.en \
  --source /home/mt/dev_wch/CH32V003/datasheet_en/CH32V003DS0.PDF

uv run tools/export_document_markdown.py \
  .cache/structured-documents/CH32V003DS0.en

uv run tools/render_document.py \
  .cache/structured-documents/CH32V003DS0.en \
  --source /home/mt/dev_wch/CH32V003/datasheet_en/CH32V003DS0.PDF
```

現在のPoCは実装が単純な1原本ページ1ファイルを採り、見出し・段落・リストと、結合セルを
失わないHTML tableを出す。これは単一の大きな文書、章単位、仮想スクロール等へ後から
変更できる派生層であり、中間JSONや抽出器には影響させない。翻訳も表示ファイルではなく
block/cell IDへ結び付ける。この境界を守れば、分割方式を後で変更する費用は主にrendererと
navigationに閉じ、中間変換・review・意味抽出・CSV生成をやり直す必要はない。

## 本実装する場合の移行順

将来の実装では、まず`catalog/documents.csv`から対象55版を列挙する一括変換器を作り、
1文書ごとに変換と検査を完結させる。移行は、(1) textのみ、(2) table、(3) char/図形、
(4) pixel cropの順に行う。既存抽出器は共通の構造化文書入口へ置き換え、
同じ入力PDF名に対して旧経路と新経路の
候補を比較してから切り替える。datasheet代表は`extract_products`、RM代表は
`extract_registers`。最後に全evidence/index/READMEを再生成し、意図した追加以外の差分が
ないことを完了条件にする。

移行単位は次のとおり。1群ずつ旧経路との多重集合比較を通し、まとめて切り替えない。

| 群 | 主な既存tool | 必要な構造 |
|---|---|---|
| datasheet本文 | `build_features`, `scan_errata`, `build_adc_internal` | page text、heading、原文ID |
| datasheet表 | `extract_products`, `extract_ordering`, `extract_pins`, `build_pins`, `build_operating`, `build_all` | 物理cell、span、平坦化row、改ページ継続 |
| RM本文 | `build_memory`, `build_timers`, `build_flash_geometry` | heading、paragraph、章境界 |
| RM表 | `extract_registers`, `build_registers`, `extract_remap`, `build_dma_requests` | headingとtableの読み順、row geometry |
| core/package | `build_debug_data`, `extract_package_dims` | text、文書種別 |
| 画像 | `extract_images` | word/char/drawing geometry＋別asset renderer |

本実装の完了条件は、(1) 対象55版が全ページbundleでhash検査済み、(2) 各抽出器の旧新比較を
保存、(3) 未承認blockを正本生成に使わない、(4) 正本CSVの意図しない差分0、(5) 原本更新時に
古いreviewを自動流用しない、の5点とする。

次工程（今回の範囲外）は、55版の一括変換、全PDF抽出器の切替、zh/enの対応付けreview、
画像asset rendererのhash連携である。PoCは`.cache/`だけを使い、正本CSVを変更していない。
