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
入力の版は `tables/sources.csv` が持つので、差分が出たら原因は「コードを変えた」か
「ミラーが更新された」かに絞れます。

## 総合評価の凡例

- ✅ **固い** — 両言語照合または複数出所で confirmed が大半、機械検査あり、既知の穴なし
- 🟡 **穴が既知** — 使えるが、列挙された穴がある（穴は数か名前で固定してあり、増えたら検査が落ちる）
- 🔵 **単一出所** — EVT ヘッダや RM だけから機械的に写したもの。reference どまりだが、
  写し間違いの余地が小さい（テキストの grep に近い）
- 🔴 **弱い** — 未解決の不定さがある

## 一覧

行数・confidence 分布は 2026-08-25（穴埋め後）時点。検証結果の詳細は下の各節（検証時の行数は当時のもの）。

### 中核（datasheet 両言語照合）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| products | 103 | 列ごと（confirmed大半・packing missing 102） | 結合・比較表と突き合わせ | flash/sram が空の series あり（比較表が書かない） | ✅ |
| product_attributes | 1,721 | confirmed 1,684 / conflict 25 / ref 12 | 結合・CJK漏れ | conflict は本物の版間食い違い（例: H417WEU6 の OPA 数 zh=1/en=2） | ✅ |
| packages | 25 | 列ごと | products と結合・lead数 | — | ✅ |
| pins | 4,558 | confirmed 4,524 / ref 33 / conflict 1 | 結合・**共有lead数を形ごとに固定**・封装lead数 | F-24残り8セルは**zh/en両版とも空欄**と確認（資料側。表に無いのが正しい）。F-31/F-32は**修正済み**（M007/M103のゲートドライバpad 26 leadが入った。lead欠けは資料が`未使用`と書く5型番のみ。`VDD_VIO_1`の綴りも直った）。ref 33の大半は片方の版だけ結合セルが埋まらない7セル由来 | ✅ |
| pin_functions | 28,484 | confirmed 28,235 / ref 237 / conflict 12 | 結合・pins と結合・**alias行の形** | F-6/7（資料側）。F-40/F-41 は**修正済み**（conflict 12 = V103 TIM3 の格子訂正の自己申告）。`route=alias`（30行）はpad名の括弧のGPIO別名で機能ではない（`tables/README`）。**pinout単位**で型番の機能一覧ではない（仕様） | 🟡 |
| operating_conditions | 305 | confirmed 279 / ref 21 / conflict 5 | 結合 | F-36 は**修正済み**（条件欄の添字を戻した。値は検証 12/12 一致） | ✅ |
| features | 397 | confirmed 386 / ref 11 | 結合 | 節番号の振り方が版で違う datasheet あり（数だけ記録） | ✅ |
| memory_configs | 67 | **全行 conflict** | products と往復 | conflict は**意図した記録**: EVT ヘッダの `FLASH_OBR` フィールド幅（2bit）と RM 中文版（3bit）が食い違う。5通りの組合せに3bit要るので中文版が正、と basis に両論併記 | 🟡 |
| errata | 21 | 列ごと | 結合・scan_errata で増分監視 | curated（人手）。両版のページ番号は照合済み | ✅ |

### RM から（単一出所）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| remap_fields | 288 | 全行 reference | 結合・bits の重複・reset | 一致記録が無く全行 reference。F-34/F-35 は**修正済み**（reset_value 空欄 45→7、残りは RM が復位値を書かない EXTEN CTR 等。valid_values に RM 説明文の列挙を加えた）。F-47 で V407/V467 の `ETHPHY_LED_REMAP` が入った | 🔵 |
| remap_routes | 4,919 | 全行 reference | fields と結合・valid_values | F-27/F-42 修正済み（2レジスタ分割 field の列見出しを合成して読む——V407/V467 USART1 の値が正しくなった）。F-8（V003 の ADC 規則転換トリガ PD3/PC2）と F-47（V407/V467 の LED0/LED1）の経路が入り、`candidates` の未解決は **F-6 の32 function だけ**。X033/X035 の TIM1 値3/4 は **RM に格子が無く** pin 表のみが根拠。F-43（V407 RM の I3C 列見出し誤植）は歯止めで無害化 | 🔵 |
| timers | 67 | ref 65 / varies 1 / conflict 1 | 結合・IRQ名・variant macro | conflict 1 = V307 TIM5（RM の注が名指す variant を V307 が持たない）。V006 TIM3 の kind 空欄は **RM が種類を書いていない** | 🔵 |
| flash_geometry | 12 | confirmed 11 / conflict 1 | 結合・2の冪・fast<page | EVT driver と RM の**両方を読んで突き合わせ**。conflict 1 = V103 の fast_program（EVTコメント256B vs RM 128B。RM＋driverの消去側＋アドレス条件が128で揃うのでRMを採る） | ✅ |
| opa_cmp_registers | 293 | confirmed 199 / ref 89 / conflict 5 | 結合・address=base+offset・bits=mask | EVT ヘッダ×RM レジスタ表。conflict 5 は**EVT ヘッダ側の誤り**と判断できるもの（F-44 X035 CMP_LOCK bit13→RM bit31 / F-45 L103 ITRIM 幅・V205 HYS_H 位置）。V20x/V103/X315 は bit define が無く行なし | 🟡 |
| clock_enables | 429 | confirmed 370 / ref 59 | 結合・address=RCC base+offset | EVT rcc.h×RM。**conflict 0**。ref 59 は RM の field 名綴りが違う（`ETH_MAC_Rx` 等）だけで bit の不一致ではない | ✅ |
| adc_internal | 19 | confirmed 13 / ref 4 / conflict 2 | 結合・channel が数 | datasheet zh/en 照合。conflict 2 = V20x/V307 の Avg_Slope 最大値が **zh 4.8 / en 4.7**（資料側の食い違い、F-46）。V003/X035 のチャネル番号は RM から | ✅ |
| usbpd_plumbing | 13 | confirmed 11 / ref 2 | 結合・clock_enables と一致 | EVT ヘッダ×RM。ref 2 = M030 の LVE_T（RM に field 名が無い） | ✅ |
| dma_requests | 650 | confirmed 577 / ref 73 | 結合・dma+channel か request_id の一方・remap の値・variant が evt_variants の macro | RM の DMA 章の格子を **zh/en 両版で照合**（R-20 D-7、2026-08-26）。ref 73 = CH32V407（RM は zh のみ）。H417 は DMAMUX の番号表（channel 固定でない）。V006 の TIM3 は型番で割り当てが違う（脚注を note に）。資料の誤植 2件（V407 `13C`、H417 `I3X_RX`）は綴りを保って note | ✅ |

### EVT から（単一出所・テキスト写し）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| interrupts | 791 | 全行 reference | 結合・condition の macro・境界不変量 | F-37 は**修正済み**（OR条件を`\|`区切りで全部持つ） | 🔵 |
| memory_map | 799 | 全行 reference | 結合 | F-38 は**修正済み**（基準リンカを式評価で読む。H417 はコア別2行）。ヘッダ由来の行は検証で全一致 | 🔵 |
| systick | 53 | 全行 reference | 結合 | — | 🔵 |
| evt_variants | 56 | 全行 reference | products と結合 | — | 🔵 |
| pin_alternate | 240 | 全行 reference | pin_functions(af-N) と結合 | — | 🔵 |
| clock_configs 他 clock_* 5表 | 1,066 | reference（symbols に conflict 5） | 相互結合・macro | V003 の trim 未出力（既知）。F-39 は**修正済み**（V307 の #if 分岐を condition へ・V006 の RMW 手順を採取） | 🔵 |
| evt_examples | 1,593 | confirmed 1,556 / ref 37 | 結合 | — | ✅ |
| eval_boards | 117 | 全行 confirmed | products と結合・重複禁止 | 型番を決められない board 3枚（`parts` 空・意図的） | ✅ |
| register_blocks | 676 | confirmed 548 / ref 128 | 結合・layout と一致・address 書式 | R-20 の機械収集ぶん（2026-08-25）。confirmed = RM zh 版の絶対アドレス表と1つ以上の register の番地が一致（2026-08-26）。ref は RM の表に名前が無い block（別 header の USB/BLE 型・PFIC・ESIG 等）。H417 `UHSIF` は型の構造体が header に無く layout 空 | ✅ |
| registers | 4,995 | confirmed 2,762 / ref 2,229 / conflict 4 | layouts と結合・offset/幅の書式 | confirmed = RM の絶対アドレス表で base+offset が一致（8,369行中 5,110行照合）またはレジスタ表に同名。**conflict 4 = H417 CAN2 のフィルタ設定 register が RM では +4**（CAN1 は一致。原典側の記録）。union で重なる register は同 offset の2行 | ✅ |
| register_fields | 33,365 | field 24,792（confirmed 6,829 / conflict 38）・value 8,573（全 reference） | 結合・bits/mask/kind 書式 | RM と綴りが一致した field だけ照合。**conflict 38 は本物の食い違い**（M030 `ADC_STATR` の `MULT_CMP1`/`MULT_CMP3` が EVT と RM で bit 入れ替わり、V407 `RCC_CFGR2` の `UTMI1ON`/`UTMI2ON` も入れ替わり、V003/V006 `GPIO_LCKR.LCKK` bit8 vs 16、L103 `CAN_BTIMR` の幅、X035 TIM `CCR3/4` 16 vs 32bit、ほか F-44/F-45 と `FLASH_OBR.USER` の RM 側の行の切り方）。`member` 空 1,591 行（CAN 以外の入れ子・構造体の無い define 群） | 🟡 |
| register_layouts | 353 | 全行 reference | (family, type) 一意 | ハッシュなので同じか違うかだけを言う。header の版が変われば変わる | 🔵 |

### 導出（他テーブルから機械生成。原典を新たに読まない）

| テーブル | 行数 | confidence | 検査 | 既知の穴 | 総合 |
|---|---:|---|---|---|---|
| pin_roles | 24,266 | 元の行を引き継ぐ | **pin_functions に無い行が入れば失敗**・語彙の穴は**0であることを検査** | **覆い100%**（2026-08-25。最後の26種を原典で所属確認して語彙へ）。pin_functions の conflict 12 を引き継ぐ。`port`/`pin` は alias からも埋まる | ✅ |
| feature_tags | 696 | confirmed 687 / ref 9 | 結合 | 節見出し由来の18タグは datasheet 粒度（precision 列が明示） | ✅ |
| sources | 12 | confirmed | 結合 | 生成時刻は持たない（冪等性のため。仕様） | ✅ |
| series / families / cores / documents | 128 | 列ごと | 相互結合 | — | ✅ |

### 未解決

| テーブル | 行数 | 状態 |
|---|---:|---|
| link_firmware | 10 | 🔴 **版番号が未確定**（F-11）。sha256 と取得元は事実だが、`wcfg_version`/`set_version` の解釈に実機の突き合わせが要る |

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

- 穴の台帳: [worklist.ja.md](worklist.ja.md) の F 番号（未解決: 実機待ち F-11、資料側の記録 F-6/7/24残り/33/43〜46、F-4残りは実害なし。**ツール側の穴は0**）。解決済みの記録は [worklist-archive.ja.md](worklist-archive.ja.md)
- 語彙の穴: `tools/check_tables.py` の `KNOWN_ROLE_GAPS`（綴りと行数で固定）
- 数の不変量: `tools/check_tables.py` の `KNOWN_SHARED_LEADS`、`tools/check_counts.py` の `KNOWN`

**穴は閾値ではなく名前と数で固定**してあるので、どれかが動けば検査が落ちて分かります。
「静かに増える」「静かに直る」のどちらも起きません。
