# テーブル別の信頼度

**「このテーブルをどこまで信用してよいか」に1枚で答えるための資料**です。
確度は3層で見ます。どれか1つではなく、3つ揃って初めて「固い」と言えます。

| 層 | 何が分かるか | どこにあるか |
|---|---|---|
| 行の `confidence` | その行を**何個の独立した出所**が言っているか | 各テーブルの `confidence` / `basis` 列 |
| 機械検査 | 参照が結合できるか・数が動いていないか | `tools/check_tables.py` / `tools/check_counts.py`（毎回実行） |
| 原典サンプル検証 | 生成器を通さずに**原典を読み直して**一致するか | この資料の「検証結果」列（2026-08-25 実施） |

`confidence` の意味（[glossary](glossary.ja.md)も参照）:
`confirmed`=2つ以上の独立な出所が一致 / `reference`=1出所のみ（誤りではなく裏取り待ち）/
`conflict`=出所どうしが**本当に食い違っている**（どちらかに寄せず両方残す）/
`varies-by-package`=型番・variantで値が変わる。

**生成は冪等**です（同じ入力・同じコードなら何度回しても差分ゼロ。実測済み）。
入力の版は `catalog/sources.csv` が持つので、差分が出たら原因は「コードを変えた」か
「ミラーが更新された」かに絞れます。

## 総合評価の凡例

- ✅ **固い** — 両言語照合または複数出所で confirmed が大半、機械検査あり、既知の穴なし
- 🟡 **穴が既知** — 使えるが、列挙された穴がある（穴は数か名前で固定してあり、増えたら検査が落ちる）
- 🔵 **単一出所** — EVT ヘッダや RM だけから機械的に写したもの。reference どまりだが、
  写し間違いの余地が小さい（テキストの grep に近い）
- 🔴 **弱い** — 未解決の不定さがある

全表に効く検査（2026-08-28〜29 に追加）:

| 検査 | 何を見るか | 見つけた実例 |
|---|---|---|
| `column_drift` | 表のヘッダが、その列を決めている生成器の定数と合っているか | `remap_routes`・`timers` の導出列（**ツールと生成物が数日ずれていた**。F-54） |
| `regeneration_coverage` | `COLUMN_SOURCES` の生成器が全部 `regenerate.py` の `--full` 順序に載っているか | R-32 で新設した `build_flash_program_method` が**登録漏れ**で `--full` に載っていなかった（原本が改版されても表だけ古いまま残り、列は合っているので `column_drift` にも掛からない。2026-09-06） |
| `routes_backed_by_pins` | `remap_routes` の (pad, signal) が、その series の `pin_functions` にあるか | 別 series の pin 表を読んでいた128行（F-50） |
| `pin_numbering` | 封装の公称 lead 数と番号の連番 | NC の足を落としていた5型番（F-49） |
| `remap_selector_coverage` | `remap-N` 行が selector まで辿れているか | index 側の数を誰も持っていなかった（監査の指摘） |
| `check_baseline` | 凍結台帳（`pipeline/baseline/tables.csv`）の行数・SHA-256が正本の実物と一致するか、**かつ正本を全数覆っているか** | **27表がずれ、5表が台帳に載ってさえいなかった**（2026-09-06。ずれた27表は現行の生成器から27/27 byte一致で再現＝正本は正しく台帳が5日古いだけ。台帳を読むコードが1本も無く、「解凍は明示的に台帳を書き直す」という約束を忘れても何も落ちなかった） |
| CI: 導出物の鮮度 | PDF 不要な生成物がコミット済みの内容と一致するか | カタログ更新が README を置き去りにしていた（D11） |
| `check_docs.py` | **文書が書いている行数と穴の状態**が、表と worklist の台帳と合っているか | 解決済みの F-11 を3つの文書が古いまま説明していた・この資料の pinout 行数が5行古かった（2026-08-29 の監査） |
| `check_viewer.js` | **`pins.html` の表示**が壊れていないか（DOM 無しで関数を評価して出力を見る） | series view の Defaults が先頭型番だけを見ていた（G1。CH32V006 の SWCLK と UART が全部 `-` になっていた） |
| `out_option` | 表を書く生成器が**試験用の出力先 `--out` を受ける**か | `build_operating`（現`operating_rows`） と `build_evt_examples` が argparse を持たず、`--out` を黙って無視して `evidence/` に書いていた（2026-08-29。実際に正本を1つ潰した） |

**中身の鮮度は PDF が要るので CI では見られません。** そこは `catalog/sources.csv`（読んだミラーの commit）と手動のフル実行が担当です。`column_drift` は「中身は見られなくても列なら見られる」という割り切りで、実際に F-54 の2件はこれで捕まりました。

**説明文の鮮度は PDF が無くても見られます。** データが直っても文章が古いままなら、利用者が読むのは古いほうです。`check_docs.py` はその型の腐りだけを見ます——文書が書いている行数を表から数え直し、worklist の F 台帳で ✅ の穴を別の文書が「未解決」と書いていないかを見る。文書側に印は足しません（印は書き忘れるので検査になりません）。どの綴りがどの数かは `check_docs.py` が持ち、綴りが変わって当たらなくなったこと自体を失敗として言います。

## 一覧

行数・confidence 分布は 2026-08-25（穴埋め後）時点。**pins・pin_functions・operating_conditions・remap_* は 2026-08-28 の監査ぶんを反映**（F-49〜F-53）。検証結果の詳細は下の各節（検証時の行数は当時のもの）。

**「検査」欄は機械がやっていることだけを書く。** 2026-08-28 に、pins の欄にあった「封装lead数」が実は `check_tables.py` に無く、F-31 で人が一度数えただけだったことが分かった（そのため5型番の lead 欠けが3日間気付かれなかった）。人が一度確かめたことは「既知の穴」欄に、機械が毎回見ることだけを「検査」欄に書く。

### 中核（datasheet 両言語照合）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| products | 103 | 列ごと（confirmed大半・packing missing 102） | 結合・比較表と突き合わせ | flash/sram が空の series あり（比較表が書かない） | ✅ |
| product_attributes | 1,714 | confirmed 1,687 / conflict 25 / ref 2 | 結合・CJK漏れ | conflict は本物の版間食い違い（例: H417WEU6 の OPA 数 zh=1/en=2）。**ref は 12 → 2 になった**（2026-08-29、F-57/F-58）——残る2行は CH32V317 の2型番の `code_flash_bytes`（480K）で、中文版にしか行が無い | ✅ |
| packages | 25 | 列ごと | products と結合・lead数 | — | ✅ |
| pins | 4,563 | **confirmed 4,556 / ref 7（conflict 0）** | 結合・**共有lead数を形ごとに固定**・**封装の公称lead数と番号の連番**（`pin_numbering`。2026-08-28 に実装） | F-24残り8セルは**zh/en両版とも空欄**と確認（資料側。表に無いのが正しい）。F-31/F-32は**修正済み**（M007/M103のゲートドライバpad 26 leadが入った。`VDD_VIO_1`の綴りも直った）。~~lead欠けは資料が`未使用`と書く5型番のみ~~→ **その5型番も資料は行を印刷していた**（F-49。2026-08-28）。`NC`／`未使用`／`Unused` を pad と見ておらず、CH32V203RBT6 の lead 47 は**直前の pad 名 `VDD_2` に化けていた**。**封装lead数の照合はこの欄に書いてありながら機械では見ていなかった**——F-31 で人が一度数えただけだったので、`check_tables.pin_numbering` にした。いま欠け0・範囲外0。**ref は 33 → 7 になり、conflict は 0 になった**——F-53（見出しがページ境界で割れた塊を落とし、CH32X305RCT6 の lead 1〜25 が中文版だけになっていた 26行）と F-56（`PC14-`。資料の食い違いではなく片方の版の読み落としで、同じ版の他の表の綴りで補えた 1行）を直した。**残る7行は F-4 の残り**（片方の版だけ結合セルが埋まらない。H417 PB10・M103 PB5/PA13・V203 PB8×2・V205 PD0×2）で、**未確定が記録済みの資料側の穴だけになった** | ✅ |
| pin_functions | 28,483 | confirmed 28,319 / ref 146 / conflict 18 | 結合・pins と結合・**alias行の形** | F-6/7・F-51（資料側）。F-40/F-41 は**修正済み**（conflict 18 のうち12 = V103 TIM3 の格子訂正の自己申告）。残る6行は CH32V407/V467 の `FSMC_NADV` で、pin表が `remap-1`・RM 格子が `remap-0` と言う——2026-09-04 に en 版 RM が加わって出た穴で、F-60 に記録している。`route=alias`（30行）はpad名の括弧のGPIO別名で機能ではない（`tables/README`）。**pinout単位**で型番の機能一覧ではない（仕様） | 🟡 |
| operating_conditions | 3,209 | confirmed 3,061 / ref 127 / conflict 21 | 結合・**完全同一行が無いこと**・**記号の頭字が名乗る物理量に単位が合っていること**（`UNIT_FOR`） | 2026-08-29 に 304 → 1,588 行（電圧・時間・クロック・電流・ADC・Flash寿命ほか。既存304行は不変の純追加）。**2026-09-01、A11の受入で 1,588 → 2,796 行**——消費電流とウェイクアップ時間（I_DD 1,054・I_HV 52・t_wu系 51 ほか）。**正本生成元は`pipeline/extract/datasheet/build_operating_conditions.py`**（凍結した`build_operating`のロジックをbundle入力で走らせた基礎行＋A11抽出。表の選択はページ割りでなくcaption、断片はx/位置で結合、zh/en照合は表番号スコープの2段階）。<br>**取れていないもの**: (0) **表全体に掛かる条件**（`条件：V_DD = 5V`／`Condition: V_DD = 5V` とヘッダに書く形。全corpusで4表＝`CH32X035DS0` の OPA/CMP 特性表だけ）。表全体の条件を置く列が無く、行の条件欄に混ぜると `V_DD 供电电压 建议不低于2.5V` が `V_DD = 5V, Recommended not less than 2.5V` と自己矛盾するので写していない。**その表の行は V_DD = 5V での値**（2026-09-09）、(1) 添字が文字層で `*` に化けた式（`0.45*V+*0.41`。`V_DD` だと推測できるが埋めない。`LOST_SUBSCRIPT` で落とす。2026-09-02にこれを**PDFのToUnicodeの破損**と記録したが、**2026-09-10に原本を描画して確かめたら誤りで、PDFの版面そのものが小さなアスタリスクを刷っている**——`CH32H417DS0.en` p.104 と `CH32V205DS0.en` p.56 の該当セルを pypdfium2 で切り出して目視。資料側の組版の欠落なので engine を変えても OCR でも復元できない。人向けMarkdownは該当ページに警告を出す＝`pipeline/common/lost_subscripts.py`。806 glyph／14文書）、(2) 2記号が1行に畳まれた行（`t_/t_r(SCK)_f(SCK)`）、(3) zh単独版datasheet（M030DS2・V006DS2）の行——ただし2026-09-02の調査で**どちらも比較表にまだ無いSKUの文書**（CH32M006のdatasheetとM030 K9U7/C9U7の補遺）と判明し、対象SKUがproductsに現れるまで行の置き場が無い（取りこぼしではなくcatalog範囲外）。<br>~~**conflict 40 のうち 8 は綴りの差**（`mS`/`ms`、`0.8VDD`/`0.8*VDD`、`VI/O`/`VIO`）で資料の食い違いではない。~~→ **2026-09-09に外した**（7件が confirmed に。対応付けのときだけ単位を「先頭の `M` だけ大小を保って残りを小文字」に正規化し、値の `*` と `I/O` の綴りを無視する。`m`/`M` だけが大小で意味を持つので、`mΩ`/`MΩ`・`mV`/`MV` は揃わない＝単純な大小無視を入れなかった理由を保つ。**公開する綴りは変えない**）。A11受入で足した10件は**全て原文裁定済みの資料側齟齬**——H417のstop電流3件・L103のt_wustop（7/13us）・V006の待機電流（10.6/10.7uA）・V407のt_WUSTDBYの**単位差（en us/zh ms）**・X315 zh改版によるFlash時間max欠落2件とI_DD改定2件。F-36・F-52は修正済み。<br>**2026-09-09、OPA/CMP の特性表を読めるようにして 2,876 → 3,140 行**（増えた270行は confirmed 261・reference 7・conflict 2。`V_OHSAT`/`V_OLSAT`/`V_hys`/`V_IOFFSET`/`I_DDOPAMP`/`C_LOAD`/`t_WAKUP`/`I_LOAD`/`R_LOAD`/`t_D`/`V_CMIR` ほか）。穴は5つあった——表題で表を選ぶ（`OPA`/`CMP`＋`特性`。78表のうち68が特性表で全部当たり、`引脚功能` 10表は全部落ちる。zh/en の表数は全文書で対称）／条件ヘッダに限定が入った表を読む（`条件：V_DD = 5V`。全corpusで4表）／表題の無い断片は直前の表題を継ぐ／**食い違いの相手を同じ表に限る**（表題の大文字略語の集合で範囲を作る。記号は同じ文書の複数の表に出るので、記号だけで突き合わせると偽の食い違いが5件出た）／同じ主張の重複を確度の良い方に畳む（重複 6 → 0）。併せて記号と値の綴りも3つ直した——`attach_value_subscript` に `DD33A`（`VDD33-16A0` という壊れた数が消え、H417 の `V_OHSAT` の偽 conflict 3件が confirmed に）、**添字を挟んで割れた脚注**（`V (2⏎OHSAT⏎)` → `V_(2_OHSAT_)` になっていた4行）、**添字自体が2行に割れた** `I_LOAD_PG_A`。この5行はどれも正しい綴りの confirmed 行と重複していたので畳まれた。**既存行は10件動いて全部改善**（reference → confirmed 9・conflict → confirmed 1）で、**新しい conflict 2件はどちらも原文で確かめた資料側の誤り**（`CH32V007DS0` の en が `t_D` に `2.0/5/5.5 ns` と同じ表の `V_DD` の値を印刷している／`CH32M030DS0` の en が `V_IOFFSET` の非対称な範囲 `-8/+12` を `8` に落としている）。<br>**2026-09-09、CH32X035DS0 中文版 V2.3 の受入で 2,864 → 2,876 行**（X035 が 98 → 110。中文版だけが持つ「出力電圧特性」表のピン群ごとの12行を `reference` で採った——ピン群を `condition` に書き、表の選択をページ割りではなく caption にし、zh/en の照合を**ピン群の一致と条件欄の有無**で守った。`pipeline/extract/datasheet/operating_rows.py`）。**同時に動いた既存11行は全部この文書の行で、原文で裁定済み**: 一般I/Oの `V_OH`/`V_OL` 4行の confirmed → reference は正しい（zh V2.3 が一般I/O行をポート群ごとの行に置き換え、en V2.2 の一般I/O行が裏を失った）／ X035 `I_DD`（zh V2.3 の typ 560µA と en V2.2 の 290/480µA）は**資料の本物の食い違い**なので conflict が正しい／`V_DD Performance may be reduced` は conflict → confirmed の改善／`V_DD Recommended not less than 2.5V` の conflict は**残る1件の誤り**で、原因は照合ではなく**到達**——正しい相手（zh p.34 OPA 表／p.35 CMP 表の `建议不低于2.5V 2/5/5.5`）が窓の外で、代わりに p.32 ADC 表の `额定性能` と当たった。OPA/CMP の表題を `TABLE_CAPTION` に足すのが直し方で、**同日に別commitで直した**（下記。confirmed に上がった）。min/typ/max のどれかの一致を conflict の条件にするガードは、上の X035 `I_DD` という本物も消すので入れない／`I_DD Standby/Stop` 4行は V2.3 の表番号振り直しで zh 側の裏が取れなくなり confirmed → reference（同じ表の Run/Sleep 行は confirmed のまま） | ✅ |
| absolute_maximum_ratings | 250 | **全行 confirmed**（ref 0 / conflict 0） | 結合・**記号の頭字が名乗る物理量に単位が合っていること**（`UNIT_FOR`） | **2026-09-10 に新設**。データシートの絶対最大定格表（`表3-1 绝对最大值参数表` / `Table 3-1 Absolute maximum ratings`）だけを読む。全corpus実測: **33表・33版で1文書1表**、表題は4綴りだけ、両版ある16文書はすべて 1/1 の対称。**`operating_conditions` と別の表にした**——どちらも `symbol` が `V_DD` で `min`/`max` を持つのに意味が正反対（推奨動作範囲 vs 超えると壊れる限界）で、混ぜると区別できない。実際に一度混ぜたところ `index/parts.csv` の供給電圧が `CH32L103` で `1.8..3.6V` から `-0.3..4.0V` に化けた（`build_index` は `symbol == "V_DD"` の min/max を取る）。表の形も違う（`条件` の見出しも `典型值` の列も無く、条件は無名の欄に書かれる。続きの断片は列の対応を**x座標で**組む＝`align_cols`）。**受入は250行を1件ずつ原本と照合**——列の対応づけを使わない別実装（末尾3列が min/max/unit、記号と単位は空欄なら直前の行から継ぐ）で読み直し、**250行すべてが zh と en の両版に在る**ことを確かめた。<br>**取れていないもの**: en版310行のうち**60行**は記号が物理量を名乗らないので落としている（`∑I_INJ(PIN)` 11・`|△V_DD_x|` 系 32・`△` が別の行に落ちた綴りの崩れ 12 ほか）。zhだけが行を持つ12行も出していない（表示テキストは英語版から取る設計） | ✅ |
| features | 397 | confirmed 386 / ref 11 | 結合 | 節番号の振り方が版で違う datasheet あり（数だけ記録） | ✅ |
| memory_configs | 67 | **全行 conflict** | products と往復 | conflict は**意図した記録**: EVT ヘッダの `FLASH_OBR` フィールド幅（2bit）と RM 中文版（3bit）が食い違う。5通りの組合せに3bit要るので中文版が正、と basis に両論併記 | 🟡 |
| errata | 21 | 列ごと | 結合・scan_errata で増分監視 | curated（人手）。両版のページ番号は照合済み | ✅ |

### RM から（単一出所）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| remap_fields | 287 | 全行 reference | 結合・bits の重複・reset | 一致記録が無く全行 reference。F-34/F-35 は**修正済み**（reset_value 空欄 45→7、残りは RM が復位値を書かない EXTEN CTR 等。valid_values に RM 説明文の列挙を加えた）。F-47 で V407/V467 の `ETHPHY_LED_REMAP` が入った | 🔵 |
| remap_routes | 4,836 | 全行 reference | fields と結合・valid_values・**pin_functions に (pad, signal) があること**（`routes_backed_by_pins`。2026-08-28 に実装） | F-27/F-42 修正済み（2レジスタ分割 field の列見出しを合成して読む——V407/V467 USART1 の値が正しくなった）。F-8（V003 の ADC 規則転換トリガ PD3/PC2）と F-47（V407/V467 の LED0/LED1）の経路が入り、F-6（V30x の I2S3。2026-08-28）も入って **`candidates` の未解決は 0** になった（**index 側の数は別**——`index/pinout.csv` で selector を決められない `remap-N` 行は **3行**で、F-51 だけ。`KNOWN_SELECTOR_GAPS` が持つ。worklist の「未解決の数は2つあり、単位が違う」）。F-50 は**修正済み**（2026-08-28。CH32X033 の candidate が CH32X035 の pin 表を読んでいた——series CH32X033 の経路が別の pad 由来だった）。X033/X035 の TIM1 値3/4 は **RM に格子が無く** pin 表のみが根拠。F-43（V407 RM の I3C 列見出し誤植）は歯止めで無害化 | 🔵 |
| timers | 67 | ref 65 / varies 1 / conflict 1 | 結合・IRQ名・variant macro | conflict 1 = V307 TIM5（RM の注が名指す variant を V307 が持たない）。V006 TIM3 の kind 空欄は **RM が種類を書いていない** | 🔵 |
| flash_program_method | 12 | confirmed 11 / conflict 1 | 結合・ctlr_bit_names⊆register_fields・幅と方式文字列の一致 | RMの**番号付き手順**（zh一次）とEVT driverの突き合わせ。conflict 1 = H417（RMは起動bitも`FTPG`と書くが、driverは`CR_PG_STRT`・register_fieldsは`PG_STRT` bit21）。V103とM030は**RMに無い必須手順**（`0x40022034`への書き込み）を`undocumented_note`に持つ。`program_buffer_load_bits`はRMに無く**driverの`FLASH_BufLoad`のシグネチャだけが出所**（32/64/128の3通り。M030=64・V103=128） | ✅ |
| flash_geometry | 12 | confirmed 11 / conflict 1 | 結合・2の冪・fast<page・消去後値の幅 | EVT driver と RM の**両方を読んで突き合わせ**。conflict 1 = V103 の fast_program（EVTコメント256B vs RM 128B。RM＋driverの消去側＋アドレス条件が128で揃うのでRMを採る）。`blank_check_word`はEVT IAP由来だが**V103だけRMにもIAPにも無く**、他repoの実測を引用（`basis`に`measured:ch32rv(...)`。RMの`PGERR`の説明が`0xFFFF`前提なのを`rm-pgerr`で裏付け） | ✅ |
| opa_cmp_registers | 293 | confirmed 199 / ref 89 / conflict 5 | 結合・address=base+offset・bits=mask | EVT ヘッダ×RM レジスタ表。conflict 5 は**EVT ヘッダ側の誤り**と判断できるもの（F-44 X035 CMP_LOCK bit13→RM bit31 / F-45 L103 ITRIM 幅・V205 HYS_H 位置）。V20x/V103/X315 は bit define が無く行なし | 🟡 |
| clock_enables | 429 | confirmed 370 / ref 59 | 結合・address=RCC base+offset | EVT rcc.h×RM。**conflict 0**。ref 59 は RM の field 名綴りが違う（`ETH_MAC_Rx` 等）だけで bit の不一致ではない | ✅ |
| adc_internal | 19 | confirmed 13 / ref 4 / conflict 2 | 結合・channel が数 | datasheet zh/en 照合。conflict 2 = V20x/V307 の Avg_Slope 最大値が **zh 4.8 / en 4.7**（資料側の食い違い、F-46）。V003/X035 のチャネル番号は RM から | ✅ |
| usbpd_plumbing | 13 | confirmed 11 / ref 2 | 結合・clock_enables と一致 | EVT ヘッダ×RM。ref 2 = M030 の LVE_T（RM に field 名が無い） | ✅ |
| debug_wiring | 26 | confirmed 26 | 結合・series高々1行・`swdio_pad`がpinoutに実在・`dual_support`の語彙 | WCH-Link manual（zh/en照合）の配線表＋両対応注記（R-29。新経路の抽出器`pipeline/extract/manual/extract_debug_wiring.py`——**新経路による初の新規evidence表**）。manualに載らないM103は行なし。**manualとpin表の齟齬2件**（V002/V004: manualはV00x群を両対応と括るがpin表にSWCLK無し・見出しも1-wire）は証拠を綴りのまま残し、`index/debug_interfaces`が見出し優先＋異議記録で裁定 | ✅ |
| option_bytes | 98 | confirmed 98 | 結合・family×address一意・**baseが`register_blocks`のOB blockと一致**（RM表 vs EVTヘッダの相互検査）・offsetがbaseからの距離・補数は隣（+1） | RMのoption bytes章「用户选择字信息结构」表からfamily×バイトごと1行（R-30。新経路`pipeline/extract/rm/extract_option_bytes.py`。全11 RMが同名captionでこの表を持つ）。zh/en照合は**表内の相対offset**で対にする——**M030はbase番地そのものが版間で食い違う**（zh 0x1FFFF300／en 0x1FFFF800）が、EVTヘッダ（`register_blocks`のOB）がzhを支持＝**2つの独立した根拠の一致でconfirmed**、enの異議は`!…(address=…)`でbasisに残る（2026-09-02裁定・ユーザー委任）。V407（RMがzh単独）の8行はreference。~~V407（RMがzh単独）の8行はreference~~ → **2026-09-04 に V407 の en 版 RM が加わって8行とも confirmed**（両版が同じ番地を言う）。`write_unit`は編程手順が名指す制御bitで分類（OBPG=half-word／FTPG=fast page） | ✅ |
| device_id_addresses | 12 | reference 12 | 結合・**全familyに1行**・memory_mapのCHIPID領域と番地一致（L103/V205）・device_ids全行のid_addrと一致 | device_idの読み出し番地（R-28）。一次資料はEVTの`DBGMCU_GetCHIPID()`（`tools/build_device_ids.py`——即値またはheaderの`CHIPID_BASE`）。**第三者DBに無いgap 4 familyも埋まる**（V205/V407/X315=0x1ffff704、M030=0x1ffff384）。EVT単独なのでreference——実機読みで番地が裏付いたらconfirmed候補 | ✅ |
| device_ids | 71 | reference 71 | 結合・型番がproductsに実在・id_addrがdevice_id_addressesと一致・32bit hexの形・dont_care/id_sourceの語彙 | 型番ごとのdevice_id値（R-28）。**ch32-rs/ch32-data（第三者DB）からの取り込みは全行reference**（basisにcommitとfile）——confirmedは実機読み（`device-id:wch-linke`）との突き合わせでのみ。gap 7 series（V205/V407/V467/X305/X315/M030/M103）は値が無く、ch32rv側の実測待ち。目録に無いch32-data型番12件（CH32系）は対応付けせず落とす——**末尾グレード桁のニアミス**（F8P6 vs F8P7等）を含む | ✅ |
| option_byte_fields | 106 | confirmed 101 / conflict 3 / ref 2 | 結合・family×(byte,bits)一意・全familyにRDPRの行・familyがoption_bytesにも居ること | 構造表直後の無caption「名称/字节」表からbit割当と**RM記載の復位値**（R-30の工場出荷値はこの粒度で提供——生バイト列の合成は導出なのでしない）と、WRPR群の説明文から**`wrpr_bit_protects`＝1bitが保護する範囲**（「N個扇区×サイズ」「4K字节」「DBMODEで扇区サイズが変わる」の3形で全RMを覆う。読めなければ生成が落ちる）。ページ跨ぎはL1結合、ページ跨ぎで割れた識別子・復位値は縫合。復位値の照合は**値トークンの列**（散文の言語差・句読点の漂着を吸収）。版間齟齬は全て原文確認済み。**conflict として残るのは3行**——識別子の綴りが文書ごとに逆転する `IWDG_SW`/`IWDGSW`（V003・V205）と、M030 の `RST_MODE[1:0]`。**残りは confirmed に上がった**が、異議は `basis` の `!…` に残っている——第3の根拠が片方を支持するとき（X315 `USBHSDLEN` は EVT ヘッダ、FV2x の `RAM_CODE_MOD` も EVT ヘッダ、X035 の復位値 `xxxb` は bit 幅の規則）と、V407 のように en 版 RM が加わって両版が揃ったとき。**reference 2** は M030 の WRPR 群のまとめ方が版で違う（zh `WRPR0-WRPR1`／en `WRPR0-WRPR3`）ぶんで、どちらの行も相手を持たない | ✅ |
| debug_data | 12 | confirmed 7 / ref 4 / missing 1 | 結合・番地の書式・data1=data0+4 | EVT debug.c の define × QingKe マニュアル hartinfo 表 × consumer の実測（R-27）。ref 4 は V3 系（マニュアルが値を固定しない）で EVT のみ。missing 1 = H417（EVT に define 無し。実測待ち） | 🟡 |
| dma_requests | 650 | confirmed 650（V407 の 73 行は 2026-09-04 に en 版 RM が加わって ref→confirmed。F-59） | 結合・dma+channel か request_id の一方・variant が evt_variants の macro（印の読み `remap` は `index/dma` 側で検査） | RM の DMA 章の格子を **zh/en 両版で照合**（R-20 D-7、2026-08-26）。ref 73 = CH32V407（RM は zh のみ）。H417 は DMAMUX の番号表（channel 固定でない）。V006 の TIM3 は型番で割り当てが違う（脚注を note に）。資料の誤植 2件（V407 `13C`、H417 `I3X_RX`）は綴りを保って note | ✅ |

### EVT から（単一出所・テキスト写し）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| interrupts | 791 | 全行 reference | 結合・condition の macro・境界不変量 | F-37 は**修正済み**（OR条件を`\|`区切りで全部持つ） | 🔵 |
| memory_map | 797 | 全行 reference | 結合 | F-38 は**修正済み**（基準リンカを式評価で読む。H417 はコア別2行）。ヘッダ由来の行は検証で全一致 | 🔵 |
| systick | 53 | 全行 reference | 結合 | — | 🔵 |
| evt_variants | 56 | 全行 reference | products と結合 | — | 🔵 |
| pin_alternate | 240 | 全行 reference | pin_functions(af-N) と結合 | — | 🔵 |
| clock_configs 他 clock_* 5表 | 1,070 | reference（symbols に conflict 5） | 相互結合・macro | V003 の trim 未出力（既知）。F-39 は**修正済み**（V307 の #if 分岐を condition へ・V006 の RMW 手順を採取） | 🔵 |
| evt_examples | 1,608 | confirmed 1,573 / ref 35 | 結合 | — | ✅ |
| eval_boards | 117 | 全行 confirmed | products と結合・重複禁止 | 型番を決められない board 3枚（`parts` 空・意図的） | ✅ |
| register_blocks | 676 | confirmed 548 / ref 128 | 結合・layout と一致・address 書式 | R-20 の機械収集ぶん（2026-08-25）。confirmed = RM zh 版の絶対アドレス表と1つ以上の register の番地が一致（2026-08-26）。ref は RM の表に名前が無い block（別 header の USB/BLE 型・PFIC・ESIG 等）。H417 `UHSIF` は型の構造体が header に無く layout 空 | ✅ |
| registers | 4,936 | confirmed 2,762 / ref 2,170 / conflict 4 | layouts と結合・offset/幅の書式 | confirmed = RM の絶対アドレス表で base+offset が一致（8,369行中 5,110行照合）またはレジスタ表に同名。**conflict 4 = H417 CAN2 のフィルタ設定 register が RM では +4**（CAN1 は一致。原典側の記録）。union で重なる register は同 offset の2行 | ✅ |
| register_fields | 33,365 | field 24,792（confirmed 6,831 / conflict 38）・value 8,573（全 reference） | 結合・bits/mask/kind 書式 | **`member` が空な行は 1,591 → 911**（2026-08-28〜29。R-20。banner が型を名乗らないだけの343行と、**名前では引けないが RM の絶対番地なら引ける**337行を結んだ——FMC/FSMC は BCR と BTR が1つの配列に交互に入り、`OPA_KEY` は header が `OPAKEY` と綴る。残り911行は header に構造体が無く、`member` は header の概念なので埋めようがない）。RM と綴りが一致した field だけ照合。**conflict 38 は本物の食い違い**（M030 `ADC_STATR` の `MULT_CMP1`/`MULT_CMP3` が EVT と RM で bit 入れ替わり、V407 `RCC_CFGR2` の `UTMI1ON`/`UTMI2ON` も入れ替わり、V003/V006 `GPIO_LCKR.LCKK` bit8 vs 16、L103 `CAN_BTIMR` の幅、X035 TIM `CCR3/4` 16 vs 32bit、ほか F-44/F-45 と `FLASH_OBR.USER` の RM 側の行の切り方） | 🟡 |
| register_layouts（`index/`） | 353 | 全行 reference | (family, type) 一意 | ハッシュなので同じか違うかだけを言う。header の版が変われば変わる | 🔵 |

### 導出＝索引 `index/`（証拠から機械生成。原典を新たに読まない。2026-08-26 に `pin_roles`→`pinout`・`feature_tags`→`features` へ移った）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| pinout（旧 pin_roles） | 24,982（機能行 24,266＋機能の無い lead 716） | 元の行を引き継ぐ | **pin_functions に無い行が入れば失敗**・語彙の穴は**0であることを検査** | **覆い100%**（2026-08-25。最後の26種を原典で所属確認して語彙へ）。pin_functions の conflict 12 を引き継ぐ。`port`/`pin` は alias からも埋まる | ✅ |
| capabilities（`index/`） | 1,707 | 元の行を引き継ぐ | **product_attributes に (型番, 属性, 値) で戻せること**・`count` が値そのままであること・属性が能力の語彙にあること（無ければ生成が落ちる） | 資料の値のうち素の整数だけが `count` に入る（1,182行。`8+2`・`3/2`・`10@2` は `value` のまま）。**行が無い＝持っていない、と読めるのは family の中だけ**——比較表の `-` は証拠の時点で落ちていて、「その family の比較表にその行が無い」と区別が付かない | ✅ |
| conflicts（`index/`） | 191 | 元の行を引き継ぐ（全行が `conflict`） | **証拠の `conflict` 行の数と一致すること**・`field` がその表に実在する列であること | 資料が食い違っている箇所を1表に集めたもの。`basis` の DSL から「どの出所が異を唱えるか」（`!<source>`）と「その出所は何と言うか」（`(=<value>)`。新経路の抽出器は`(address=…)`・`(field=…)`のように列名を名指し、値は`alternative`へそのまま写る）を取り出す。**114行に相手の値が入り、76行は空**——`memory_configs` の67行と `timers` の1行は食い違いを散文で記録していて DSL に持たないため（空欄自体が「evidence/README を読め」の意味）、残りは**相手が値を書かない型**（新しいX315 zh版がFlash時間のmaxを載せない等）。`product_attributes` の25行は**言い回しの差が混じる**（`Typical: 72MHz` と `Typ. 72MHz`）ので、仕様の食い違いと同一視しないこと | ✅ |
| debug_interfaces（`index/`） | 27 | confirmed 27 | series ごと1行・`debug_if` の語彙・features の節見出しに戻せること・pads が pinout の SWDIO/SWCLK と一致すること | **全27 seriesが確定**（swio 3・rvswd 11・**both 13**）——datasheetの節見出しと`debug_wiring`（WCH-Link manual）の突き合わせ（2026-09-01にR-29完全解決。未記載だった11 seriesはmanualが埋め、V208もmanualでconfirmed化）。V002/V004はmanualが両対応（SWCLK=PB3）と括るが**pin表にSWCLKが無く見出しも1-wire**——見出しを採り、manualの異議を`!WCH-LinkUserManual.PDF(...)`としてbasisへ（資料側の問題台帳にも記録） | ✅ |
| features（旧 feature_tags） | 696 | confirmed 687 / ref 9 | 結合 | 節見出し由来の18タグは datasheet 粒度（precision 列が明示） | ✅ |
| sources | 12 | confirmed | 結合 | 生成時刻は持たない（冪等性のため。仕様） | ✅ |
| series / families / cores / documents | 128 | 列ごと | 相互結合 | — | ✅ |
| toolchains | 15 | confirmed 15 | 語彙・重複・日付・URLの宛先・件数の下限 | 上流（MounRiver）のAPIが「いま最新」と言う配布物の写し。**行ごとに配信側を HEAD して**掲載と突き合わせている（サイズ一致で confirmed）。旧版は持たない（IDE の旧版は `--history`、ツールチェーンの旧版は上流APIに無い） | ✅ |

### 実機観測を伴うもの

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| link_firmware | 10 | 全行 reference | 結合を持たない（配布物の写し）・`reported_version` が `wcfg_version` の復号と一致すること | **版番号は解決済み**（F-11。2026-08-29）。`wcfg_version` は `major*10 + minor`（major は観測した全個体で 2）で、`reported_version` が復号値、`measured_version` が実機の申告値。LinkE と CH549 の2機種は実測で一致（`tools/read_link_version.py`）。残る8行は実機を持っていないぶんで `measured_version` が空 | 🟡 |

この表だけは**資料ではなく配布物と実機**を出所にするので、他の表の「両言語照合」に
あたる裏取りが `measured_version`（実機が USB で申告する版）になる。

## 原典サンプル検証（2026-08-25）

生成器を通さず、原典（datasheet PDF / RM PDF / EVT ヘッダ）を独立に読み直して
サンプル行と照合した結果。実施の分担と結果はこの節に記録する。

### 導出テーブル（pin_roles / feature_tags / sources / series / families / cores）— 違反 0

導出規則そのものを全行検証した（サンプルではなく全数）。

| 検証 | 規模 | 結果 |
|---|---|---|
| pin_roles ⊆ pin_functions（新しい事実を足さない約束） | 24,120行 | **違反 0** |
| pin_roles を独立に再導出して多重集合比較 | 24,120行 | **差分 0**（`TAMPER-RTC`→2役割の展開も一致） |
| 除外4,334行の内訳が規則と一致するか | GPIO名3,609 / 電源602 / 語彙の穴122 / NC 1 | 一致 |
| port/pin の分解・ソート順 | 24,120行 | 違反 0 |
| peripheral/role = 語彙規則の適用結果 | 24,120行 | 違反 0 |
| feature_tags の全行再導出 | 696行・全列 | **差分 0**（precision=part の裏付け289行も完備） |
| sources.csv とミラー実HEAD・dirty | 12行 | 一致（全ミラー clean） |
| series/families/cores の参照・カウント整合 | 全行 | 違反 0 |

所見: CH32V203CCT6 の family=CH32V205 は意図的なクロス掲載（glossary に明記）で整合。
cores.csv の V3C/V4A/V4J は未参照（語彙の余剰・害なし）。

### 文書カタログ系（documents / eval_boards / evt_examples / features / memory_configs / errata）

| テーブル | 検証 | 結果 |
|---|---|---|
| documents | mirror_url の実在（**全80件**） | 一致 100% |
| documents | 版番号 vs PDF表紙（全PDFスキャン） | **不一致 1文書**: `CH32V20x_30xDS0.PDF` がカタログ3.5 / 表紙V3.9（下記） |
| eval_boards | path実在・parts参照（**全117行**） | 不一致 0 |
| evt_examples | basis の主張と実在の整合（**全1,593行**） | 完全整合（`evt:tree`あり1,337行=全実在、なし256行=全不在） |
| features | 3 datasheet×10節×両言語=60比較 | **60/60 逐語一致**（H417の1.4.26は原典自体がzh/enで食い違い。忠実に転記） |
| memory_configs | V307VCT6の5行 vs RMのoption byte表 | **5/5一致**。conflict印はen版RMの誤記（[9:8]）を正しく反映 |
| errata | 5行×両言語の引用ページ | 全て実記述を指す（1件のみ文が改ページ跨ぎ・実害なし） |

**documents.csv の版番号のずれ**: 版番号は WCH の検索APIのメタデータ
（`manifests/documents.json`）から来る。ミラーPDFは2026-08-07にV3.9へ更新されたが、
APIは2026-08-20取得でも3.5を返している——**WCH側のメタデータがファイル実体より
遅れている**。こちらで上書きせず、穴として記録（worklist F-33）。この1文書以外は
表紙とカタログが一致（一致64 / 不一致2=同一文書の両言語）。

### 比較表系（products / product_attributes / packages）— 不一致 0

| テーブル | 検証 | 結果 |
|---|---|---|
| products | 12 family×1型番: flash/sram/package/gpio/temperature を原典から独立に読み直し | **12/12 一致** |
| product_attributes | 30行（value・label 両言語・正規化） | **30/30 一致** |
| product_attributes | `order` が資料の行順どおりか（2 family 全属性） | 完全一致 |
| packages | 10 package の pin_count/body_size/pin_pitch を訂貨表と照合 | **10/10 一致** |

特筆:
- 疑わしかった CH32V305FBP6 の ADC/TKey チャネル=1 は、**グリフの x 座標解析**で
  PDF原文（FB列=1、GB列=6）どおりと確認。テキスト抽出の見かけ（「1 6」）に
  引きずられていない。
- `flash_bytes`＝零等待領域という規約が X305（Code FLASH 480K 注記→192K）でも
  一貫していることを原典側から確認。
- 温度が比較表に無い family は型番末尾の命名規則で照合され、products.csv 側も
  `rule:pn-temp-grade` / reference と正しく標識済み。
- 軽微な観察: `label_zh` に縦組みヘッダ由来の空白揺れ（「串 口」vs「串口」）。
  不一致ではないが正規化の余地（結合キーの `attribute` には影響しない）。

### RM系（remap_fields / remap_routes / timers / operating_conditions）

| テーブル | 検証 | 結果 |
|---|---|---|
| remap_routes | 20行（全10 RM×2、value≠0）を格子と照合 | **20/20 一致**（H417の結合セル PORT17-47 の全値展開も罫線位置で確認） |
| remap_fields | 10行の bits/reset を レジスタ表と照合 | **bits 10/10 一致**。指摘3件（下記） |
| timers | 32bit **全9行**＋16bit 5行 | **14/14 一致**。basisのページ番号も全数一致。V307 TIM5 は conflict と自己申告済みで原典（16bit注記）と整合 |
| operating_conditions | 12行を電気的特性表と照合 | **値 12/12 一致**。表現上の注記2件（下記） |

指摘（誤りではなく改善点。worklist F-34〜F-36 に記録）:
1. **reset_value 空欄が45行**（H417全remap・V30x系PCFR2群など）。該当レジスタの
   復位値はいずれも RM 上 0x00000000 なので 0 と確定できる
2. **TIM5CH4_RM の valid_values が 0 のみ**。RM は値1（LSI内部クロックへのremap）も
   定義しており、L103 TIM1_RM では同種の LSI 値(7)を含めている——扱いが不統一
3. operating_conditions の条件文字列に下付き文字のずれ（`f > 1MHz S` ← f_S）。
   また L103 F_HCLK(USB) の typ=96 は原文「48/72/96 のいずれか必須」の要約で情報を落とす

備考: V103 の RM はレジスタを `AFIO_PCFR`（数字なし）と書き、CSV の `PCFR1` は
EVT ヘッダの綴り。field 名も `*_RM`（RM）と `*_REMAP`（EVT）が出所ごとに混在
——`field` 列は原典の綴りを保つ方針（README記載）どおりだが、読む側は
`canonical_field` で畳むこと。

### EVT系（interrupts / memory_map / systick / evt_variants / pin_alternate / clock_*）

| テーブル | 検証 | 結果 |
|---|---|---|
| interrupts | 36行（condition付き4行含む） | 番号・名前 **36/36 一致**。表現の欠落1件（下記 F-37） |
| memory_map | 15行＋link-origin **全24行** | ヘッダ由来 15/15 一致。**link-origin 2行が誤り**（下記 F-38） |
| systick | 7行 | **7/7 一致**（64bit CNT・2ブロック構成の family 差まで正確） |
| evt_variants | 全56行の構造照合 | 完全整合 |
| pin_alternate | 8行（アドレス再計算・bit割当） | **8/8 一致** |
| clock_configs | 6行 | 6/6 一致（pll列はPLLSRC系のみ採録する粒度。DIV系は載らない） |
| clock_init | 4 family 44ステップ | 数値・アドレスは全一致。**分岐と手順の欠落2件**（下記 F-39） |
| clock_prescalers / sources / symbols | 11サンプル | 全一致 |

検証で見つかった**要修正3件**（worklist F-37〜F-39）:
1. **F-37 interrupts**: OR結合のvariant条件が先頭マクロに切り詰められる。
   CH32V006 の USART2(39)/OPCM(40) は原典が `#if defined(CH32V005) ||
   defined(CH32V006) || defined(CH32V007_M007)` なのに condition=CH32V005 のみ
2. **F-38 memory_map（値の誤り2行）**: link-origin が ORIGIN の算術を評価しない。
   V407 RAM は `0x20000000+1024`=0x20000400 が正（+1024が落ちている）。
   H417 RAM 0x20120000 は一部例題の値で、基準は V3F=0x20110100 / V5F=0x200C0300
   ——**2コア別リンカの H417 は単一行では表現できない**
3. **F-39 clock_init**: V307 の step5-8 の `#ifdef CH32V30x_D8C`/`#else` 分岐が
   condition 列に落ちていない。V006 の RMW 手順（CTLR を 0xFED6FFFB でクリアし
   bit20 をセット）が丸ごと欠落

### pin表系（pins / pin_functions）

| テーブル | 検証 | 結果 |
|---|---|---|
| pins | 8 family×3 pad（封装列・縦結合pad・EP正規化） | **24/24 一致** |
| pin_functions | 40行（main/default/remap-N/af-N まんべんなく） | **40/40 一致**（ページ境界で切れた続きの採取も正確） |
| 境界ケース: PC13-TAMPER-RTC | V103C8T6 | 完全一致（main=PC13 / default=TAMPER-RTC） |
| 境界ケース: X035 PC3（封装別の既定機能） | 4型番 | pins は正しいが **pin_functions に余分な2行**（下記 F-40） |
| 境界ケース: V103 TIM3（RM格子との食い違い） | 12行 | **F-27の修正がこのテーブルに未反映**（下記 F-41） |

検証で見つかった**要修正2件**（worklist F-40〜F-41）:
1. **F-40 pin_functions（余分な2行）**: `build_pins.read_edition()` が機能を
   (表, pad) 単位で union するため、**封装別の行の帰属が潰れる**。X035 の PC3 で
   QSOP28/TSSOP20 の行にしかない `RST` が R8T6/G8U6 にも付いた。candidates は正しい
   （封装別の認識 F-26 は成功していて、その後の union で潰れる）
2. **F-41 pin_functions / pin_roles（12行）**: F-27 の格子優先の修正は
   candidates と remap_routes には入ったが、**build_pins は PDF を直接読むため
   届いていない**。V103 の TIM3 12行が pin 表の誤った `_1` のまま remap-1

軽微: X315 の `table` 列が pins.csv=zh版番号 / pin_functions.csv=en版番号と不統一
（データ誤りではない）。

## 検証のまとめ（全6班・2026-08-25完了）

**独立サンプル検証 約300箇所＋全数検証5種**の結果:

| 判定 | 内訳 |
|---|---|
| **値の誤り** | **2行**（memory_map の link-origin。F-38） |
| **行の過不足** | 余分2行（F-40）・手順欠落1式（F-39 V006）・修正未反映12行（F-41） |
| **表現の欠落** | OR条件の切り詰め（F-37）・分岐条件の欠落（F-39 V307）・reset_value空欄45行（F-34）・valid_values欠け（F-35） |
| **原典側の問題の正しい記録** | memory_configs の conflict（en版RMの誤記）・H417 1.4.26 の zh/en食い違い・documents の版番号（WCH APIの遅れ、F-33） |
| **上記以外** | サンプル・全数とも**全一致** |

**28,425行の pin_functions で値の誤りゼロ、24,120行の pin_roles は導出規則の違反ゼロ**。
見つかった誤りは EVT 由来の少数行に集中しており、いずれも worklist に F 番号で
固定した。修正されるまでは該当行だけを避ければよい。

## 既知の穴の一覧はどこにあるか

- 穴の台帳: [worklist.ja.md](worklist.ja.md) の F 番号（開いているのは資料側の記録だけ: F-7・F-33・F-43〜46・F-51。F-4 と F-24 は残りだけが資料側で実害なし。**ツール側の穴は0**）。解決済みの記録は [worklist-archive.ja.md](worklist-archive.ja.md)。この一覧が台帳とずれていないことは `tools/check_docs.py` が見る
- 語彙の穴: `tools/check_tables.py` の `KNOWN_ROLE_GAPS`（綴りと行数で固定）
- 数の不変量: `tools/check_tables.py` の `KNOWN_SHARED_LEADS`、`tools/check_counts.py` の `KNOWN`

**穴は閾値ではなく名前と数で固定**してあるので、どれかが動けば検査が落ちて分かります。
「静かに増える」「静かに直る」のどちらも起きません。
