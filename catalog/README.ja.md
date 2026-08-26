# 目録（catalog/）

**何が存在し、何と呼ぶか**を決める7つの表です（[docs/data-layout.ja.md](../docs/data-layout.ja.md)）。
ほかの全部の表（証拠 `evidence/`・索引 `index/`）はここの名前——family・series・型番・
package・core・文書・mirror の版——を鍵にして結合します。名前の追加や改名は全表に波及するので、
[worklist](../docs/worklist.ja.md) に記録して行います。

`products.csv` は識別（型番・series・family・package・掲載 datasheet）に加えて、比較表と
ordering 表を突き合わせた主要仕様（flash・SRAM・GPIO 数・温度）を**列ごとの確度と根拠つき**で
持ちます。利用者向けの見やすい比較表は索引の [`index/parts.csv`](../index/README.ja.md) です。

`tools/build_tables.py` が products/packages/series/families/cores を、`tools/build_documents.py`
が documents を、`tools/build_sources.py` が sources を生成します。確度・根拠の読み方は
[evidence/README.ja.md](../evidence/README.ja.md) の「確定の基準」「根拠の種類」を参照してください。

### `families.csv` — 最上位

1行1ファミリー。どのシリーズを含み、どのdatasheet・reference manual・EVTが該当するか。文書の対応は日次同期している`manifests/documents.json`から取ります。全体像はまずここを見ます。

### `series.csv`

1行1シリーズ（CH32V006, CH32V203, …）。core・ISAと、配下の全packageが共有する値だけを持ちます。packageで変わる値は`varies-by-package`として空になり、products.csvへ降ります。**シリーズとdatasheetは1対1ではありません**（CH32V203CCT6はCH32V205DS0に掲載）。

### `products.csv`

1行1注文型番。flash・GPIO数・温度など製品固有の値だけを持ち、**寸法系はpackage名でpackages.csvを参照**します。`listed_as`は比較表での略記（`CH32V208CB`→`CH32V208CBU6`、ワイルドカード`C6x6`→C6T6/C6U6）。

`flash_bytes`は**零等待で実行できる領域**（linker scriptの`FLASH`に入る量）です。
CH32V303/305/307のdatasheetは「Code FLASH（字节）480K」と「Flash（字节）256K」を
別の列で持っていて、前者はdie上のprogram flash全体、後者が零等待領域です。
同じフィールドに寄る列が2つあるときは**より具体的な綴りをpromote**し、
負けた側は`product_attributes.csv`へ落とします（480Kも事実なので消しません）。
振り直せるpartは`memory_configs.csv`を参照してください。

**CH32X305/X315の`flash_bytes`は192Kです。** 比較表の列は480Kの1つしかなく、
分割は脚注の散文（「480KB闪存包含192KB的零等待程序运行区域」）にあります。
文が総量と零等待量の両方を書いているので、そこから零等待側を取ります
（480Kは`code_flash_bytes`として`product_attributes.csv`に残ります）。
EVTの`Link.ld`も7本すべて192Kを基準にしています。CH32H41xは当てはまりません——
比較表の列が「非零等待Code FLASH」と名乗っていて、**零等待で走るFLASHが無い**
（零等待のコード領域はSRAM側のITCMにあります）。

`sram_bytes`は逆に**過小でした**。CH32H41xのdatasheetは合計を表に書かず、
ITCM 128K・DTCM 256K・共有領域 512Kの3行に分けて書きます。合計896KBは
本文の「内置総容量896K字節のSRAM」と一致します（F-15）。3行は
`product_attributes.csv`に残してあります。

### `packages.csv`

1行1package名の**マスタ表**。body size・pin pitch・lead数はpackageの属性なのでここに正規化し、productsには持たせません。根拠は全productのordering表記載の集約＋PACKAGE.PDF（封装寸法図面、`WCH-common`にmirror）の両言語目次＋package名の数字です。同名packageが複数ファミリーで違う寸法を主張すればconflictとして現れます（現在0件）。QFN26C3とQSOP24のlead数のみreference（pin定義表と不一致=抽出行落ちの疑い、`?pin-table`）。

### `cores.csv`

1行1 QingKe core。coreのISA仕様（core manual一覧表、両言語確認済み）と、どのmanualに書いてあるかを持ちます。series.csvのISAはchip側datasheetの記述で、coreの任意実装部分（V3Bの[M][B]等）をchipがどう選んだかを表すため、cores.csvのISAとは別の事実です。

### `documents.csv`

1行1文書。`CH32L103DS0.PDF`という名前だけでは場所が分からないため、**中国語/英語それぞれのオリジナルページ（.html）・ダウンロードURL・mirror（GitHub raw）URL**と版数を持ちます。除外文書も`status`付きで載る完全なカタログです。EVT（ZIP）はarchive自体をmirrorに置かないため、mirror URLは展開済みツリーを指します。

### `sources.csv`

**どの版の原典を読んで生成したか。** 1行1 family。

このリポジトリは原典を自分の中に持たず、`/home/mt/dev_wch/<FAMILY>/`にある
**別々のgitリポジトリ（mirror）**のPDFとEVTを読みます。mirrorはGitHub Actionsが
毎日15:07 UTCにWCHから取り直してcommit/pushするので、**入力が勝手に動きます**。
版を控えておかないと、生成物の差分の原因が

1. 抽出のコードを変えた
2. mirrorが更新された
3. 誰かが再生成を忘れた

のどれなのか区別できません。`tools/build_all.py`は入力とコードが同じなら何度
回しても差分が出ない（実測済み）ので、**版さえ控えれば差分は1か3に絞れます**。

**生成時刻は入れていません。** 入れると回すたびに行が変わり、「差分が出たら異常」
という判定そのものが使えなくなります。控えるのはcommit hashと、そのcommit自身が
持つ日付だけ——どちらも再実行で動きません。

`dirty`はmirrorに未コミットの変更があったという印で、立っている行は
**commit hashが読んだ中身を説明しません**。`tools/check_tables.py`が落とします。

この表は`evidence/`を作り直す一連の実行の中で回します。mirrorを同期した後・生成の
前後どちらでもよいですが、**生成の途中で同期しないこと**。


## 全表の結合キー

`tools/check_tables.py` が全参照の結合可能性を機械検査します:

```
series.family / products.family / packages.families   → families.family
products.series                                        → series.series
products.package                                       → packages.package
series.core / families.cores                           → cores.core
pins.part_number / pin_functions.part_number           → products.part_number
product_attributes.part_number                          → products.part_number
index/pinout.(part_number, pad, pin)                    → pins.(part_number, pad, pin)
index/pinout.(part_number, pad, route, signal)          → pin_functions.（同じ4つ組。route だけ RM 格子の値を採る行がある）
remap_fields.series                                     → series.series
remap_routes.(series, selector)                         → remap_fields
clock_configs.family / clock_prescalers.family / clock_sources.family → families.family
clock_symbols.family / clock_init.family / evt_variants.family → families.family
clock_configs.(family, hpre|ppre1|ppre2)                → clock_prescalers.(family, field, divider)
clock_configs.(family, pll|outside_rccの各記号)          → clock_symbols.(family, symbol)
clock_configs.condition / clock_sources.condition の macro → evt_variants.(family, macro)
evt_variants.part_number                                → products.part_number
memory_configs.part_number                              → products.part_number
pin_alternate.family                                    → families.family
interrupts.family / memory_map.family / features.family / sources.family → families.family
eval_boards.family / feature_tags.family                → families.family
eval_boards.parts                                       → products.part_number
feature_tags.series                                     → series.series
features.series                                         → series.series
interrupts.condition の macro                            → evt_variants.(family, macro)
pin_functions(route=af-N).part_number+pad               → pin_alternate.family+pad
errata.series / operating_conditions.series             → series.series
evt_examples.family                                     → families.family
*.datasheet(s) / families.reference_manuals・evt / cores.manual → documents.document
```

pins系は`tools/build_pins.py`、remap系は`tools/build_remap.py`、clock系は`tools/build_clock.py`、operating_conditions.csvは`tools/build_operating.py`、evt_variants.csvは`tools/build_evt_variants.py`、systick.csvは`tools/build_systick.py`、pin_alternate.csvは`tools/build_pin_alternate.py`、eval_boards.csvは`tools/build_eval_boards.py`、feature_tags.csvは`tools/build_feature_tags.py`、sources.csvは`tools/build_sources.py`、interrupts.csvは`tools/build_interrupts.py`、memory_map.csvは`tools/build_memory_map.py`、features.csvは`tools/build_features.py`、memory_configs.csvは`tools/build_memory.py`、link_firmware.csvは`tools/build_link_firmware.py`、それ以外は`tools/build_tables.py`が生成します。

