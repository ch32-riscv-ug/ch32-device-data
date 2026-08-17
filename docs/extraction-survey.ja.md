# 抽出可能性の事前調査

文書基準日: 2026-08-17

文書状態: 調査記録。実測値を含むが、schemaと取込方式の決定ではない。

## 目的

device recordのどこを一次資料から機械抽出でき、どこが人手判断になるかを、実データで測定します。

すでに人手で作成した3 record（CH32V003F4P6、CH32X035F8U6、CH32M030C8T7）をground truthとして使い、抽出器の出力と照合しました。抽出器は[`tools/extract_selectors.py`](../tools/extract_selectors.py)と[`tools/extract_pins.py`](../tools/extract_pins.py)にあり、いずれも候補を表示するだけでrecordを書き換えません。

## 前提

自動化の向きは「このrepositoryのデータを各family repositoryのpin表へ反映する」方向です。このrepository自身のデータ更新は低頻度で、完全自動化の対象ではありません。

したがって抽出器は常時稼働するpipelineではなく、必要時に一度走らせて人がreviewするためのtoolとして位置づけます。

## 切り分けの原則

調査の結果、資料の種類ではなく**記述の性質**で切るのが妥当だと分かりました。

> コンパイルされて動作に効く値は信頼できる。コメント・文章・表は信頼できない。

マスク値は誤っていればEVT例題が動かないため発覚します。コメントは動作に効かないため静かに腐ります。「EVTは自動、datasheetは手動」という分け方ではありません。

## EVTヘッダからのroute selector抽出

### 使う定義と使わない定義

`GPIO_Remap_*`定数は使いません。`GPIO_PinRemapConfig()`のエンコード方式がfamilyで3系統に分かれ、非連続bitの実体が`.c`の関数本体にベタ書きされているためです。

| 系統 | フラグ | family |
|---|---|---|
| STM32継承 | `0x80000000`/`0x7FFFFFFF` | V003, V103, V407, V307, V20x, L103 |
| 新系 | `0x00FFFFFF`/`0x08000000` | V006, X035, M030, H417 |
| 固有 | V003に`0x10000000`、V20xに`0x40022030`（レジスタアドレス直書き） | — |

代わりに`ch32*.h`の`AFIO_PCFR1_*`／`EXTEN_*`のbit定義を読みます。`#define NAME ((uint32_t)0xMASK)`の素直な形式で、全familyに存在します（H417の23件からV407の105件）。これによりfamily差の問題が消えます。

### 測定結果

| family | record selector | bit位置一致 | valid_values一致 | reset_value | record外の余剰 |
|---|---:|---:|---:|---:|---:|
| CH32V003 | 10 | 10/10 | 10/10 | 0/10 | 6 |
| CH32X035 | 9 | 9/9 | 1/9 | 0/9 | 2 |
| CH32M030 | 8 | 8/8 | 2/8 | 0/8 | 35 |
| 計 | 27 | **27/27** | 13/27 | **0/27** | 43 |

bit位置は取りこぼしも誤りもありません。手作業で発見したと記録されているCH32V003の非連続field（I2C1が`[1,22]`、USART1が`[2,21]`）も、X035とM030の3bit fieldも機械的に得られます。

### ヘッダから得られないもの

- **`reset_value`**: 27件すべて取得不能。RM必須
- **`valid_values`**: 原理的に不能。ヘッダは列挙値とbit index補助定義を区別しません。CH32V003では`AFIO_PCFR1_TIM1_REMAP_1`（bit index）と`AFIO_PCFR1_TIM1_REMAP_PARTIALREMAP_1`（実際の値）がどちらも`0x80`です。X035/M030は単ビットの補助定義しか持たず、CH32M030の`TIM1_REMAP`はrecordが3bit幅に5値（予約値あり）を持つのに対しヘッダからは`[1,2,4]`しか出ません
- **fieldの併合**: `I2C1_REMAP`(bit 1)と`I2C1_HIGH_BIT_REMAP`(bit 22)が同一fieldだという情報はどこにもありません。抽出器は命名規則から推測しており、これは人手規則です
- **非連続fieldのbit順序**: 値のLSBがどの物理bitかはヘッダから決まりません。CH32V003では結果的に昇順一致でしたがRM確認が要ります
- **route selectorか否か**: CH32M030は46件抽出して採用8件、83%が捨て対象です。`EXTEN_UDP_DAC`（6bit DAC値）、`EXTEN_ISINK1_ADJ`のように実在するfieldだがpin routeでないものが多数あります。`EXTEN_KEY_R = 0xFFFFFFFF`のようなunlock keyも混ざるため、field幅の上限で弾いています

### 副産物

CH32X035で`AFIO_PCFR1_SPI1_REMAP`（bits `[0,1]`）が抽出されましたが、recordに対応selectorがありません。recordはPA4-PA7にCS/SCK/MISO/MOSIを`route: "default"`・`selection`なしで持っています。QFN20でremap先がbond-outされていない可能性もありますが、未決定事項「default routeでもselector値0を明示すべきか」に該当する箇所です。

抽出器は転記toolとしてだけでなく網羅性チェッカとしても働きます。

## EVTコメントからpad対応は取れない

`AFIO_*`定義のコメントにpad参照があるかを全familyで数えました。

| 状態 | family |
|---|---|
| pad参照があり、存在しないportを参照している | V003（PB 9件・PE 9件）、V20x（PE 9件） |
| pad参照はあるが未検証の継承テキスト | V103、V407、V307（各16件） |
| pad参照が0件 | V006、X035、M030、H417、L103 |

CH32V003はPA1/PA2/PC0-7/PD0-7しか持ちませんが、コメントは`ETR/PA12, CH1/PA8, ... BKIN/PB12`や`Full remap (ETR/PE7, CH1/PE9, ...)`と書いています。CH32V103系からの継承です。`AFIO_PCFR1_PA12_REMAP`というsymbol名とそのコメント「Port D0/Port D1 mapping on OSC_IN/OSC_OUT」も同様で、実際はPA1/PA2の話です。

古い系は誤っており、新しい系は何も書いていません。**pad対応はdatasheet/RMに100%依存し、EVTは相互確認の相手にもなりません。**

## Linker scriptからのmemory情報

`EXAM/SRC/Ld/Link.ld`のみが代表値です。IAPやVectorInRAMなど例題別の`.ld`は意図的に別レイアウトを持ちます。

CH32V006の代表`Link.ld`は3 SKU分を同居させ、2つをコメントアウトしています。

```
/* CH32V002 */              FLASH 16K / RAM 4K   コメントアウト
/* CH32V004_CH32V005 */     FLASH 32K / RAM 6K   コメントアウト
/* CH32V006_CH32V007_CH32M007 */ FLASH 62K / RAM 8K   有効
```

素朴な`grep LENGTH`は6値を拾って壊れます。一方でSKUグループ名が併記されており、`CH32M007`の存在とV006/V007と同siliconであることはここ以外で得にくい情報です。既存recordのCH32V003（16K/2K）とCH32V006K8U7（62K/8K）は有効ブロックと一致します。

CH32V407は`LENGTH = 136K-1K`、CH32H417は`ORIGIN = (0x200C0000+512+256)`と式評価が必要です。

## DatasheetからのPin抽出

### 環境

`pdftotext`・`pdfplumber`・`pip`のいずれも環境にありません。uvで`pdfplumber`を導入しました。`pdfplumber`の表認識はテキストdumpより大幅に良く、列が正しく分離されます。ghostscript（`gs -sDEVICE=txtwrite`）でもテキストは取れますが、表の列構造は失われます。

### 測定結果

| family | package | pin番号→pad | function数 | (pad,signal) | selector値集合 | 抽出器の自己申告 |
|---|---|---:|---:|---:|---:|---:|
| CH32V003 | TSSOP20 | 20/20 | 110/110 | 83/84 | 75/84 | 2 |
| CH32X035 | QFN20 | 20/21 | 122 / 116 | 102/105 | 83/105 | 0 |
| CH32M030 | LQFP48 | 34/48 | 136 / 188 | 88/171 | 70/171 | 102 |

CH32X035で欠けた1 pinはexposed pad（`EP`/`GND`）で、表がleadとして番号を振っていないためです。

**CH32M030には現在の抽出器の前提が成立しません。** この表は`_N`形式の経路番号を使わず、remap情報はRM側にあります。抽出器は102件を「経路番号なし・要確認」として報告しており、黙って誤った値を出してはいません。

### パーサで解決した崩れ

- **パッケージ列数がfamilyで異なる**（V003は4列、M030は5列、X035は7列）。見出しから動的に検出する必要があります。パッケージ名は縦書きのためテキスト層では逆順に入ります（`02POSST` → `TSSOP20`）
- **表が次表と同じページに跨る**。ページ単位で打ち切るとCH32X035で8 pin脱落します。次表キャプションのy座標で切ります
- **pad名に脚注が付く**（`PA7(7)`、`PC16(4)(9)`）。`VDD`が`V\nDD`と改行で分断されることもあります
- **セルがトークン途中で折り返す**（`T2C1N_`/`6`、`C1P`/`0`、`A3(`/`3)`）。信号名は数字で始まらないため、「次行が数字始まりなら継続」で判別できます

### 解決できない崩れ

- **テキスト層の文字欠落**。CH32X035のPA6行はセル実体が`MISO/T3C1/O1N0/A`で、`A6`の`6`がテキスト層に存在しません。remap列も`T1BK_1`で、正しくは`T1BKIN_1`です。紙面には出るがテキスト層に無く、パーサでは復元できません
- **datasheetの誤植**。CH32V003 Table 2-1のPD4行は`TIETR_2`（正しくは`T1ETR_2`）です。`T1ETR`系13出現のうちこの1件だけ`I`と`1`が入れ替わっています。抽出器は忠実に再現するため、そのまま取り込むと誤りが入ります

### 自己申告できない誤りが残る

CH32V003でrecordと食い違った9件のうち、抽出器が「要確認」と申告できたのは2件だけでした。

| 差分 | 抽出器の主張 | 実際 |
|---|---|---|
| OPN0 / OPP0 / OPN1 / OPP1 | default | `EXTEND_CTR`の`OPA_NSEL`/`OPA_PSEL`制御 |
| OSCI / OSCO | 経路番号なし（申告あり） | AFIO `PA1PA2_REMAP`制御 |
| AETR / AETR2 | default | ADC external trigger remap制御 |
| TIETR | そのまま採用 | datasheetの誤植 |

**datasheetのpin表は、その機能がselector制御されていることを表記しません。** RMを読まないと分からない差が、確定扱いで紛れ込みます。

## 仕組みの方針

以上から、次を提案します。決定ではありません。

- 抽出器は`tools/`に置き、必要時に人が実行する。CIには入れない
- 出力は候補として提示し、人のreviewを経て`devices/`へ人が反映する
- 抽出結果を格納する中間層（`extracted/`等）とmergerは設けない。継続同期しないため不要
- **抽出結果は全件reviewを前提とする。** 抽出器がflagを立てた項目だけを見るのでは足りない
- 資料矛盾の裁定だけは機械可読で残す。抽出器を再実行したとき同じ矛盾が再提起されるのを防ぐため

## 生成先が必要SKU数を決める

`CH32V003/README.md`のGPIO表はA4M6 / F4P6 / F4U6 / J4M6の4列です。この表を生成するにはfamilyの全packageが必要ですが、現在あるのはF4P6のみです。

4 SKUは同一siliconであり、selectorを4回複製することになります。未決定事項「silicon/package/exact SKUの正規化」は、この生成要件から判断できます。

なお各family repositoryのREADMEにある手製GPIO表は、`ch32_riscv_tools/PinAlternateFunctions`と同じく出典・coverageを持ちません。検証根拠や取込元にはしない対象として同列に扱うべきです。

## Toolの使い方

```sh
uv run tools/extract_selectors.py <EVT>/Peripheral/inc/ch32xxx.h --compare devices/<id>.json
uv run tools/extract_pins.py <datasheet>.PDF --package TSSOP20 --compare devices/<id>.json
```

`--compare`を省くと候補の一覧と要確認事項だけを表示します。`--emit`で候補JSONを標準出力へ書きます。どちらもrecordを書き換えません。

`tools/validate.py`は標準libraryだけで動く状態を維持しており、`python3 -S tools/validate.py`のfallback検査も従来どおりです。

## 未決定事項

1. CH32M030系のremap表をRMから読む抽出器を作るか
2. 抽出候補JSONをschema準拠の形にして、未採取SKUの入力に使うか
3. datasheetの誤植とテキスト層欠落を、reviewのどの段階で検出する仕組みにするか
4. 資料矛盾の裁定を保持する構造をschemaへ追加するか
5. family repositoryのREADME手製表を禁止対象として明記するか
