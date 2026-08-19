# 抽出可能性の事前調査

文書基準日: 2026-08-17

文書状態: 調査記録。実測値を含むが、schemaと取込方式の決定ではない。

## 目的

device recordのどこを一次資料から機械抽出でき、どこが人手判断になるかを、実データで測定します。

測定は2段階です。まず精度を測るため、すでに人手で作成した3 record（CH32V003F4P6、CH32X035F8U6、CH32M030C8T7）をground truthとして抽出器の出力と照合しました。次に適用範囲を測るため、mirrorしている全datasheetを掃引しました。

抽出器は[`tools/extract_selectors.py`](../tools/extract_selectors.py)、[`tools/extract_pins.py`](../tools/extract_pins.py)、[`tools/extract_remap.py`](../tools/extract_remap.py)、[`tools/extract_registers.py`](../tools/extract_registers.py)の4本で、[`tools/build_candidate.py`](../tools/build_candidate.py)がそれらを1つの候補へ結合します。いずれも候補を表示するだけでrecordを書き換えません。

## 前提

自動化の向きは「このrepositoryのデータを各family repositoryのpin表へ反映する」方向です。このrepository自身のデータ更新は低頻度で、完全自動化の対象ではありません。

したがって抽出器は常時稼働するpipelineではなく、必要時に一度走らせて人がreviewするためのtoolとして位置づけます。

### 方針

- **対象は全SKU・全項目**とする。取れる情報は取れるだけ取る
- schemaは未確定であり、必要に応じて拡張してよい。正規化・分解は公開時に行う
- 自動抽出の限界に達したら、hand researchで確認してcoverageを上げる
- 一つの資料・一つの手法で確定させず、**複数の手法で突き合わせて確度を上げる**

この方針に沿って、資料ごとの抽出結果は元のラベルを保ったまま保持し、schemaへの写像は後段で行います。

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

- **`reset_value`**: 27件すべて取得不能。RMのregister field表から取れる（後述、27/27）
- **`valid_values`**: ヘッダからは原理的に不能。RMのremap格子から取れる（後述、7/7）。ヘッダは列挙値とbit index補助定義を区別しません。CH32V003では`AFIO_PCFR1_TIM1_REMAP_1`（bit index）と`AFIO_PCFR1_TIM1_REMAP_PARTIALREMAP_1`（実際の値）がどちらも`0x80`です。X035/M030は単ビットの補助定義しか持たず、CH32M030の`TIM1_REMAP`はrecordが3bit幅に5値（予約値あり）を持つのに対しヘッダからは`[1,2,4]`しか出ません
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

人手作成の3 recordに対する照合です。

| family | package | pin番号→pad | (pad,signal) | selector値集合 |
|---|---|---:|---:|---:|
| CH32V003 | TSSOP20 | 20/20 | 83/84 | 75/84 |
| CH32X035 | QFN20 | 21/21 | 102/105 | 83/105 |
| CH32M030 | LQFP48 | 46/48 | 151/171 | 144/171 |

### 経路の書き方が2系統ある

同じ「Remapping function」列でも、familyによって書式が異なります。

| 書式 | 例 | 意味 | family |
|---|---|---|---|
| selector値の接尾辞 | `TIM1_CH1_2` | AFIO remap registerの値2 | V003, V006, X035, M030, V103, V20x, V30x, V407 |
| alternate function番号 | `TIM8_CH1(AF0)` | pinごとのAF多重化の番号0 | H415, H416, H417 |

**CH32H41xはAFIO remap方式ではなく、pinごとのalternate function多重化です。** 共有のAFIO fieldではなく各pinのAFR fieldが経路を決めるため、現在の`route_selectors`（controller・register・fieldを一度定義して各functionが参照する構造）では表現できません。schema上の論点として未決定事項に挙げています。

抽出器は両書式を読み分け、前者を`remap-2`、後者を`af-0`として記録します。

### 全datasheetの掃引

15 datasheetの31 pin定義表を掃引しました。

| 指標 | 値 |
|---|---:|
| pin定義表 | 31（うち親見出しで実体なし1） |
| 変種列 | 102（うちpinを得られたもの97） |
| 合計 pin | 4035 |
| 合計 pin function | 21853 |
| 要確認 | 252 |

取得できた製品はCH32V002/V003/V004/V005/V006/V007/M007/M030/M103/L103/V103/V203/V205/V303/V305/V307/V317/V407/V467/X033/X035/H415/H416/H417です。

pinを得られなかった5列は、テキスト層で見出しが失われた列です（CH32V208で1列、CH32V317で`LQFP100`が`LQFP10`と`0`に分断、CH32X033で1列）。placeholderとして`col3`のように残し、同じ表の他の列は正常に取得できています。

### 表の構造はfamilyごとに違う

掃引で分かった差です。いずれも固定値を仮定すると壊れます。

- **変種列の数**: CH32V203 Table 3-1-4は1列、CH32V003は4列、CH32X035とCH32V307は7列
- **変種列の見出し**: パッケージ名（`TSSOP20`）のfamilyと、型番（`V006K8U7`、`CH32V407RET6`）のfamilyがある。**後者はrecordのexact SKU単位と直接対応します**
- **見出しの向き**: 複数列では縦書きのためテキスト層に逆順で入りますが、1列だけの表は横書きで入ります
- **列の並び**: CH32V407は`I/O structure`列が挟まります。列位置は見出しラベルから引く必要があります
- **default alternate function列**: CH32H417は"Pin function(2)"という名前で、CH32H415は列自体がありません
- **表番号**: `Table 2-1`、`Table 2-1-1`、`Table 3-1-1`と形式が異なり、`Table 3-1`のように配下の`3-1-1`〜`3-1-4`を束ねるだけで実体のない親見出しもあります

### 表の境界

1ページに前表の末尾・当表の見出し・次表の見出しが同居します。ページ単位で切ると、CH32X035で8 pinが脱落し、CH32V006F4U6の表が別製品の列見出しを拾うといった誤りが出ます。両端をキャプションのy座標で切る必要があります。

キャプション照合は前方一致では不十分です。`Table 3-1`が`Table 3-1-1`の内側にマッチします。また継続ページでキャプションが再掲されるため（CH32V103 Table 2-2）、停止見出しを選ぶ際に同名を読み飛ばさないと直後で切れてしまいます。

### セルの崩れ

- **pad名に脚注が付く**（`PA7(7)`、`PC16(4)(9)`）。`VDD`が`V\nDD`と改行で分断されることもあります。折返しが脚注の内側に入る例もあり（CH32M030の`PA13(7\n)`）、空白除去を脚注除去より先に行わないと1 pin落とします
- **セルがトークン途中で折り返す**（`T2C1N_`/`6`、`C1P`/`0`、`A3(`/`3)`、`USART1_TX`/`_8`）。信号名は数字で始まらないため、「次行が数字始まり、または前行が`_`か`(`で終わる、または次行が`_`か`)`で始まるなら継続」で判別できます

### pad名の列挙は破綻する

電源・特殊padの名前はfamily固有です。CH32M030だけでVS0-3、VB0-3、VHV、VDD8、VDD33、ISP1があります。既知のpad名を列挙する方式ではCH32M030で11 pinを取りこぼしました。

pin type列（`P`、`A`、`O`、`I/O`、`I/O/A`、`I/O/FT`）を行の判別に使う方式に変えて解消しています。ただしdatasheetは電源padをすべて`P`と表記するため、**groundとpowerの区別は人手判断のまま残ります**。

### pin番号 `0` はexposed pad

WCHはQFN等の露出パッドをpin番号`0`で表します。schemaの`EP`表記へ変換したところ、CH32V006K8U7が33件（32 lead + EP）、GPIO 31本となり、**recordに人手で書かれていた`pin_count: 32`と`gpio_count: 31`に独立して一致しました。**

### 解決できない崩れ

- **datasheetの記述そのものが不完全**。CH32X035のPA6行はセル実体が`MISO/T3C1/O1N0/A`、remap列が`T1BK_1`です。当初これをテキスト層の欠落と判断しましたが、**ページを画像化して確認したところ紙面も同じ**でした。`A`は`A6`の、`T1BK`は`T1BKIN`の省略で、recordの値は人が補ったものです。パーサでは復元できません
- **テキスト層の欠落**。変種列の見出しで起きます。CH32V208 Table 3-1は4列目`QFN68`が消えて5列目を誤検出し、CH32V317 Table 3-2は`LQFP100`の末尾`0`が段落ちして`LQFP10`と`0`の2列に割れます。いずれも画像化で正しい見出しを確認しました
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

## Datasheetからの製品比較表抽出

各datasheetの冒頭には、注文可能な全modelをmemory・pin数・周辺機器数とともに並べた比較表があります。**SKUの母集合そのものと、recordのidentity・memory・package・peripheralsの出所**です。

[`tools/extract_products.py`](../tools/extract_products.py)がこれを読みます。値はschemaへ写さず、資料が使っているラベルのまま保持します。

### 2つのレイアウト

| レイアウト | 例 | family |
|---|---|---|
| 1 model 1行 | `Model \| Flash memory \| SRAM \| Pin No. \| ...` | V003, V002, V004, V006, V007 |
| 1 model 1列（転置） | `Model/Resource \| \| C8U3 \| C8T7 \| ...` | M030, L103, H417, V103, V20x, V30x, V407, X035 |

転置形はさらに2種類あります。CH32L103・CH32V407・CH32H417は上段にfamily名（`CH32V407` / `CH32V467`）、下段に接尾辞（`VET6` / `WEU6`）を置いて結合します。CH32M030はfamily行を持たず、文書題名から補います。

接尾辞の形も一定ではありません。`C8T6`のように英数交互のもの、`VET6`・`RDU6`のようにそうでないもの、CH32V303/V208の`CB`・`RB`・`VC`のように2文字だけのものがあります。狭いパターンを仮定すると、V407・H417・V20x/V30xがまとめて落ちます。

### 結果

16 datasheetすべてから取得でき、**ユニーク型番92件**になりました。

| datasheet | SKU | datasheet | SKU |
|---|---:|---|---:|
| CH32V003DS0 | 4 | CH32V103DS0 | 4 |
| CH32V002DS0 | 5 | CH32V203DS0 | 6 |
| CH32V004DS0 | 2 | CH32V205DS0 | 4 |
| CH32V006DS0 | 11 | CH32V208DS0 | 4 |
| CH32V007DS0 | 8 | CH32V20x_30xDS0 | 13 |
| CH32M030DS0 | 5 | CH32V407DS0 | 6 |
| CH32L103DS0 | 7 | CH32X035DS0 | 8 |
| CH32H417DS0 | 5 | | |

CH32V007の表にはCH32M007のSKUが、CH32L103の表にはCH32M103が、CH32V407の表にはCH32V467が、CH32H417の表にはCH32H416/H415が入ります。**datasheetのfamily名とSKUのfamily名は一致しません。**

CH32V303/V305/V208の比較表は`CH32V303CB`のように接尾辞を省略しています。完全な注文型番はordering information側にあり、突き合わせが必要です。

## Reference manualからのremap経路抽出

datasheetのpin表は、その package にbond-outされた経路しか書きません。またremap selectorの`valid_values`とdefault経路（値0）も持ちません。RMはこれらを格子で持っています。

```
Alternate function | TIM1_RM=000 Default | TIM1_RM=001 Partial | ...
TIM1_ETR           | PC1                 | PC1                 | ...
TIM1_CH1           | PB9                 | PB9                 | ...
```

[`tools/extract_remap.py`](../tools/extract_remap.py)がこの格子を`(field, value, signal, pad)`へ読み込みます。datasheet側の抽出と突き合わせる相互確認の材料になります。

### 測定結果

| 対象 | 抽出経路 | selector field | recordとの一致 |
|---|---:|---:|---|
| CH32M030 RM | 149 | 7 | 116/124 |
| CH32H417 RM | 102 | 3 | record未採取のため未照合 |

CH32M030の残差8件の内訳は、ADC trigger 2件（後述の資料矛盾）、`PB5PB6_RM` 2件（RMの格子にない）、`TIM3_ETR` 4件（recordが`TIM3_CH1_ETR`を`TIM3_CH1`と`TIM3_ETR`へ分割保持している）です。いずれも既知の構造差で、抽出誤りではありません。

RM側にのみある経路のうち30件は`value=0`のdefault経路です。recordはdefaultにselector値を持たないため、未決定事項「default routeでもselector値0を明示すべきか」がそのまま差分として現れます。

### 資料矛盾が自動的に浮上する

CH32M030の照合で次が出ます。

```
RMが文章で書いている経路 (2件):
  ADC1_ETRGIN=0 -> PB6    (ADC External triggerconversion)
  ADC1_ETRGIN=1 -> PA14
record のみ:
  ADC1_ETRGIN=0   ADC1_ETR   PA14
  ADC1_ETRGIN=1   ADC1_ETR   PB6
```

recordがdatasheet Table 2-1・RM register説明・EVT実装の3資料に従って採用した`0=PA14`と、RM Table 6-15の記述が逆であることが、そのまま差分に出ます。**この矛盾を毎回再提起させないために、裁定を機械可読で保持する必要がある**という論点の具体例です。

### siliconとpackageの差も現れる

CH32M030でRM側にのみある非default経路は`TIM1_RM=3 → TIM1_CH4 → PC5`の1件だけで、PC5はLQFP48にbond-outされていません。照合はこれを「このpackageにない」と注記します。**RMはsiliconを、recordはpackageを記述している**という区別が、そのまま観測できます。

### RM側で見つかった崩れ

- **don't-care表記**。CH32H417は`SDMMC_RM=1x`と書きます。`1`として読むと値1に誤って割り当てられ、値2と3が失われます。**静かに間違える種類の崩れ**なので、`x`を展開して複数値にする必要があります
- **表題と中身の不一致**。CH32H417 Table 9-29は"ADC2 external trigger injection"と題しながら、中身はADC1の表の複製です。Table 9-31も"TIM1 alternate function remapping"と題しながら`TIM2ITR1_RM`の内部経路を記述しています
- **pad対応が文章で書かれる行**。CH32M030 Table 6-15とCH32H417のADC系はpad名ではなく"connected to PB6"のような文章です。抽出器は文章からpadを拾い、`_pad_from_prose`として区別します
- **peripheral名のinstance番号が資料間で揺れる**。RMは`SPI_RM`・`I2C1_SCL`、recordは`SPI1_REMAP`・`I2C_SCL`です。「番号がなければinstance 1」と読む正規化を入れないと照合が0件になります
- **pad名を持たない内部経路**。CH32H417の`TIM2ITR1_RM`はTIM2_ITR1を内部接続へ切り替えるだけでpadがありません。CH32V003の`TIM1_1_RM`と同じ分類です

## Reference manualからのregister field抽出

RMは各registerの節にfield表を持ちます。

```
6.3.2.1 Remap Register 1 (AFIO_PCFR1)
Bit      | Name          | Access | Description | Reset value
[26:24]  | SWCFG[2:0]    | RW     | ...         | 0
15       | ADC_ETRGIN_RM | RW     | ...         | 0
```

[`tools/extract_registers.py`](../tools/extract_registers.py)がこれを読みます。**EVTヘッダから取れなかった`reset_value`の出所であり、bit位置の第二の独立な出所でもあります。**

| family | RMに存在 | bit一致 | reset一致 |
|---|---:|---:|---:|
| CH32V003 | 10/10 | 8/10 | 10/10 |
| CH32X035 | 9/9 | 9/9 | 9/9 |
| CH32M030 | 8/8 | 8/8 | 8/8 |
| 計 | 27/27 | 25/27 | **27/27** |

bitの不一致2件は、CH32V003の非連続fieldをRMも別fieldとして記述しているためです（`I2C1_RM`(bit 1)と`I2C1REMAP1`(bit 22)、`USART1_RM`(bit 2)と`USART1_RM1`(bit 21)）。EVTヘッダと同じく、併合は人手規則です。

同じ概念に3資料で3通りの綴りが使われます。

| 概念 | EVTヘッダ | RM field表 | record |
|---|---|---|---|
| I2C1 remapの上位bit | `I2C1_HIGH_BIT_REMAP` | `I2C1REMAP1` | `I2C1_REMAP`に併合 |
| USART1 remapの上位bit | `USART1_HIGH_BIT_REMAP` | `USART1_RM1` | `USART1_REMAP`に併合 |
| TIM1内部LSI経路 | `TIM1_1_RM` | `TIM1_IREMAP` | 未収録 |

### valid_valuesはremap格子から取れる

EVTヘッダから原理的に取れなかった`valid_values`は、RMのremap格子の列見出しが値を列挙しています。CH32M030で照合しました。

| selector | RM列挙 | record | |
|---|---|---|---|
| afio-i2c1-remap | [0,1,2,3] | [0,1,2,3] | ○ |
| afio-uart1-remap | [0,1,2,3,4,5] | [0,1,2,3,4,5] | ○ |
| afio-spi1-remap | [0,1,2,3] | [0,1,2,3] | ○ |
| afio-tim1-remap | [0,1,2,3,4] | [0,1,2,3,4] | ○ |
| afio-tim2-remap | [0,1,2,3] | [0,1,2,3] | ○ |
| afio-tim3-remap | [0,1,2,3,4] | [0,1,2,3,4] | ○ |
| afio-adc-etrgin-remap | [0,1] | [0,1] | ○ |

**7/7一致**です。3bit幅に5値しかない`tim1`・`tim3`の予約値も正しく出ます。`afio-pb5-pb6-remap`だけは格子を持たないため、RMのfield説明文（`1: 水晶発振子ピン / 0: GPIO`）を人が読む必要があります。

### route_selectorの必須項目はすべて機械由来にできる

| 項目 | 出所 | 実測 |
|---|---|---|
| controller / register / field | EVTヘッダ、RM field表 | 27/27 |
| bit位置 | EVTヘッダ（27/27）とRM field表（25/27）の2系統 | 相互確認可能 |
| `valid_values` | RM remap格子 | 7/7 |
| `reset_value` | RM field表 | 27/27 |
| `evidence` | — | 人手 |
| route selectorか否かの採否 | — | 人手（CH32M030で83%が捨て） |

## 4資料の統合

[`tools/build_candidate.py`](../tools/build_candidate.py)が上記4抽出器の出力を1つの候補へ結合します。

| 資料 | 与えるもの |
|---|---|
| EVTヘッダ | selectorのbit位置 |
| RM register field表 | `reset_value`、bit位置の第二の出所 |
| RM remap格子 | `valid_values`、値ごとのpad |
| datasheet pin表 | packageにbond-outされたpin |

**selectorの採否が自動化できます。** pinから参照されたselectorだけを残すと、CH32M030でヘッダ由来46候補が7件に絞られました。人手で83%を捨てていた作業がここで消えます。

### 未採取SKUで動かす

`devices/ch32v006k8u7.json`は`pins`が空のままです。CH32V006K8U7で走らせると次が得られました。

| 項目 | 生成 |
|---|---|
| route_selectors | 6（すべてbit位置・`valid_values`・`reset_value`つき） |
| pins | 33（32 lead + exposed pad） |
| pin function | 244（うちselection解決済み180、未解決6） |

CH32V006は`CH32V00XRM.PDF`をV002/V004/V005/V007と共有しますが、そのまま扱えます。

### 測定結果

3 recordに対する照合です。

| family | route_selector | selection付き経路 | selector未解決 |
|---|---|---|---:|
| CH32M030 LQFP48 | record 8 / 候補 7（7/7 全項目一致） | 107/124 | 0 |
| CH32V003 TSSOP20 | record 10 / 候補 5 | 51/74 | 14 |
| CH32X035 QFN20 | record 9 / 候補 6 | 45/87 | 18 |

CH32M030では候補に入った7 selectorすべてが、bit位置・`valid_values`・`reset_value`のすべてでrecordと一致します。**完全なselector定義が資料から自動生成できています。**

### CH32V003で止まる理由: 同一製品内での語彙の不一致

CH32V003は同じ製品のdatasheetとRMが別の名前を使います。

| 資料 | signal名 |
|---|---|
| datasheet Table 2-1 | `T1CH1`、`SCL`、`UCK`、`MOSI` |
| RM remap格子 | `TIM1_CH1`、`I2C1_SCL`、`USART1_CK`、`SPI1_MOSI` |

signal名だけで突き合わせると**0/74**になります。未決定事項として挙げられていた「canonical signal IDとvendor表記の分離」が、ここで具体的なコストとして現れます。CH32M030が107/124まで届くのは、そのdatasheetとRMがどちらも長い形を使っているからにすぎません。

### 対応表は資料から導出できる

signal名を使わず「padと selector値」で突き合わせれば、経路は名前なしで同定できます。そこから逆に名前の対応表が得られます。

```
datasheet T1CH1  = RM TIM1_CH1
datasheet T1BKIN = RM TIM1_BKIN
datasheet SCL    = RM I2C1_SCL
datasheet UCK    = RM USART1_CK
datasheet TIETR  = RM TIM1_ETR
```

導出した対応を二巡目で全体に適用すると、CH32V003は0/74から**51/74**まで上がります。最後の行が示すとおり、**datasheetの誤植`TIETR`も`T1ETR`と同じ経路に落ちるため正しい対応が付きます。**

ただし、pad+値が複数の経路を指す箇所からは何も学べません。同じpadを別のperipheralが同じ値で使う場合で、そこは対応付けを見送っています。導出結果は対応表の**素案**であって確定ではありません。

### 経路の書かれ方は3系統ある

CH32X035のRMにはremap格子がありません。経路はregister field表のDescription列に文章で書かれています。

```
[4:2] I2C1_RM[2:0] RW  001: Mapping (SCL/PA13, SDA/PA14)  0
```

ここから219経路を読み取れます。信号名はfield名から補完できるので（`I2C1_RM` + `SCL` → `I2C1_SCL`）、格子と同じ形に揃います。これを併用してCH32X035は0/87から**45/87**になりました。

まとめると経路の出所は次の3つで、familyごとにどれがあるかが違います。

| 出所 | 例 |
|---|---|
| datasheetのremap列の接尾辞・AF番号 | 全family |
| RMのremap格子 | V003, M030, H417 |
| RMのregister説明文 | X035, M030, V003 |

## 全SKUへの適用

[`tools/build_all.py`](../tools/build_all.py)が、比較表が挙げる全SKUに対して候補を生成します。reference manualの読み取りが支配的なので、familyごとに1回解析して各SKUで使い回します。

生成結果は[`candidates/`](../candidates/)に置いています。**人のreviewを経ていない機械出力**で、`devices/`とは別物です。

| family | SKU | pin取得 | pin | function | 解決経路 | selector |
|---|---:|---:|---:|---:|---:|---:|
| CH32H417 | 5 | 5 | 391 | 3644 | 241 | 10 |
| CH32L103 | 7 | 7 | 209 | 1421 | 799 | 65 |
| CH32M030 | 5 | 5 | 213 | 926 | 485 | 35 |
| CH32V003 | 4 | 4 | 68 | 359 | 162 | 18 |
| CH32V006 | 26 | 26 | 564 | 4430 | 3145 | 148 |
| CH32V103 | 4 | 4 | 196 | 366 | 83 | 22 |
| CH32V20x | 20 | 20 | 879 | 2750 | 568 | 99 |
| CH32V307 | 13 | 13 | 784 | 4190 | 1038 | 136 |
| CH32V407 | 6 | 6 | 440 | 2800 | 0 | 0 |
| CH32X035 | 8 | 8 | 245 | 1300 | 587 | 52 |
| **合計** | **98** | **98** | **3989** | **22186** | **7108** | **585** |

同一の`CH32V20x_30xDS0`を2つのfamily dirが持つため、処理は111 SKU・重複を除いたファイルは98件です。**pinを取得できなかったSKUはありません。**

### SKUとpin表の列を対応付ける

比較表のSKUと、pin表の列は直接はつながりません。CH32V003だけが`Package Form=TSSOP20`という属性を持ち、他familyは持たないためです。

3段階で決めています。

1. 列見出しが型番そのもの（CH32V006、CH32V407）ならそれを使う
2. 比較表にpackage属性があればそれで引く
3. なければ比較表の**pin数**で候補を絞り、型番の**末尾から2文字目**でpackage種別を決める

3の規則（`M`=SOP、`P`=TSSOP、`U`=QFN、`T`=LQFP、`R`=QSOP）は、人手作成の8 recordすべてと例外なく一致します。

### hand researchで解消した限界

当初13 SKUでpin表の列を特定できませんでした。原因は3系統に分かれ、いずれも別資料か画像確認で解けています。

| 原因 | 該当 | 解決手段 |
|---|---|---|
| `QFN48`と`QFN48X7_A`のようにpin数だけでは決まらない | M030 C8U3/C8U7、L103 K8U6/K8U7 | ordering表がpackageを明示 |
| 列見出しが末尾の変種数字を落としている（`V006E8R`） | V006/V007の6 SKU | 数字を除いた前方一致 |
| 比較表の接尾辞が省略形 | V208、V303、V305 | ordering表の完全型番、または列に埋まった型番との一致 |
| テキスト層が列見出しを落とす・誤分割する | V208、V317、V203 | ページ画像で確認し`curated/`へ記録 |

**CH32V407にはreference manualがmirrorされていません。** datasheetのみのため、440 pin・2800 functionは取れていますが経路が0件です。資料側の欠落であり、抽出器の問題ではありません。mirror追加が要ります。

## 画像化による確認

テキスト層と紙面が食い違う箇所は、`pypdfium2`でページを描画して目視確認します。同じPDFに対する第2の手法として機能し、実際に判定を覆した例があります。

| 対象 | テキスト層 | 紙面 | 判定 |
|---|---|---|---|
| CH32V208 Table 3-1の列 | `QFN28,QFN48,LQFP64,col3,col4` | `QFN28,QFN48,LQFP64,QFN68` の4列 | テキスト層の欠落 |
| CH32V317 Table 3-2の列 | `QFN68,LQFP10,col2` | `QFN68,LQFP100` の2列 | テキスト層の欠落 |
| CH32V203 Table 3-1-1の列 | `QFN20,LQFP32,QFN32,LQFP48,QFN48X7` の5列 | `QFN20,LQFP32,QFN32,LQFP48/QFN48X7` の**4列** | 1セルに積んだ見出しを2列に誤分割 |
| CH32X035 PA6行 | `MISO/T3C1/O1N0/A` `T1BK_1` | **同じ** | datasheet側の省略。当初の「テキスト層の欠落」という判断は誤り |

CH32V203の4列目は`LQFP48`と`QFN48X7`を積んだ1セルで、**2つのpackageが同じpin番号を共有する**ことを表します。列としては1つなので、curated値も`LQFP48/QFN48X7`という結合名で保持し、ordering表との照合では`/`で分割して突き合わせます。

確認済みの見出しは[`curated/pin-table-columns.json`](../curated/pin-table-columns.json)に、確認方法とページ番号つきで保持します。抽出器はこれを見出しの正解として優先します。**機械抽出が復元できない箇所を、人が確認した事実で上書きする唯一の経路**です。

見出し名だけでなく**位置**も直す必要がありました。どちらの表もpdfplumberが罫線から空の列を1つ余計に検出しており、紙面の4列がgrid上は5列になっています。curated値は紙面の列名にその空列を`-`として挟んだ並びで保持します。これでCH32V208は4 SKUすべて、CH32V317も取得できるようになりました。

## Ordering情報からのpackage確定

datasheet末尾の「Package and Ordering Information」表は、order modelとpackageの対応を明示します。body sizeとpin pitch、packing typeもここにしかありません。

```
Package Form | Body Size | Pin Pitch | Package Description | Order Model
QFN48X7_A    | 7*7mm     | 0.5mm     | Quad Flat No-lead   | CH32M030C8U3
QFN48        | 5*5mm     | 0.35mm    | Quad Flat No-lead   | CH32M030C8U7
```

[`tools/extract_ordering.py`](../tools/extract_ordering.py)が読みます。16 datasheet中14に存在します（CH32V20x_30xDS0にはありません）。列順と綴りは一定でなく、CH32V103はorder modelが先頭でpacking typeが増え、CH32V208は`Bidy Size`と誤記しています。

**これがSKUとpackageの最も強い根拠**で、`QFN48`と`QFN48X7_A`のようにpin数だけでは決まらない組を確定できます。CH32M030は5 SKU中3 SKUしか列を決められませんでしたが、ordering表を第一根拠にして5/5になりました。

### SKUの母集合は2表の和

2つの表は互いを補います。

- **ordering表は完全な注文型番を持つ**。比較表が`CH32V208CB`と略すところをordering表は`CH32V208CBU6`と書きます。未決定事項に挙げていた省略接尾辞の問題はこれで解けます
- **各表に相手が載せないSKUがある**。CH32V203は比較表6件・ordering表12件、CH32X035は比較表のみに`CH32X035D8U6`があります

そのため候補生成では両表の和を母集合とし、ordering表の型番を優先します。CH32V20xはこの変更でSKUが14件から33件になりました。

### package表記のずれ

同じpackageを2表が違う名前で書きます。ordering表の`LQFP64M`はpin表では`LQFP64`です。前方一致で吸収しています。

## 3系統での突き合わせ

package判定は3つの独立な根拠で検証できます。

| 突き合わせ | 結果 |
|---|---|
| 型番の末尾2文字目（`T`=LQFP等） vs ordering表のpackage | **84/84 一致、不一致0** |
| ordering表のpackageに含まれるpin数 vs 比較表のpin数 | **41/41 一致、不一致0**（比較表にpin数属性がない43件は対象外） |

型番規則は当初、人手作成の8 recordだけで確認したものでしたが、ordering表84件でも例外がありません。

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
uv run tools/extract_remap.py <manual>.PDF --compare devices/<id>.json
uv run tools/extract_registers.py <manual>.PDF --compare devices/<id>.json

uv run tools/extract_pins.py <datasheet>.PDF --list
uv run tools/extract_pins.py <datasheet>.PDF --package V006K8U7 --compare devices/<id>.json
uv run tools/extract_pins.py <datasheet>.PDF --package V006K8U7 --emit > candidate.json
```

`extract_pins.py`は`--list`でpin定義表の一覧を表示します。`--package`にはパッケージ名と型番のどちらも渡せます。表は既定で自動選択し、`--table`と`--stop`で明示もできます。

`--compare`を省くと候補の一覧と要確認事項だけを表示します。`--emit`は候補JSONを標準出力へ、人向けの報告をstderrへ分けて出します。どちらもrecordを書き換えません。

### 要確認件数は表の作りに比例する

掃引全体で要確認は252件で、うち47件はCH32H415の1製品です。この表にはdefault alternate function列がなく、remap列のみからの採取になるためflagが集中します。**要確認件数は抽出精度ではなく、その表がどれだけRM参照を要求するかの指標**として読むべきです。

4資料をまとめて1候補にするには次を使います。

```sh
uv run tools/build_candidate.py \
  --header <EVT>/Peripheral/inc/ch32xxx.h \
  --manual <manual>.PDF --datasheet <datasheet>.PDF --package LQFP48 \
  --compare devices/<id>.json
```

`tools/validate.py`は標準libraryだけで動く状態を維持しており、`python3 -S tools/validate.py`のfallback検査も従来どおりです。

## 未決定事項

1. `build_candidate.py`が導出するsignal名対応表を、canonical signal辞書としてrepositoryへ持つか
2. `extract_remap.py`が拾う内部経路（padを持たない`TIM2ITR1_RM`等）を同じschemaへ入れるか分離するか
3. CH32H41xのalternate function多重化（pinごとのAFR field）を`route_selectors`でどう表現するか。共有fieldを前提とした現在の構造では表せない
4. datasheetの誤植とテキスト層欠落を、reviewのどの段階で検出する仕組みにするか
5. 資料矛盾の裁定を保持する構造をschemaへ追加するか
6. family repositoryのREADME手製表を禁止対象として明記するか
7. RMのdefault経路（value=0）をrecordへ明示するか
8. CH32V303/V305/V208の省略された接尾辞を、ordering information側と突き合わせて完全な注文型番にする

## 電気的特性章の調査（2026-08-19追記）

全16 datasheetの章構成を掃引した結果、全DS0が共通で「Electrical Characteristics」章（Test Conditions / Absolute Maximum Ratings / Electrical Characteristics）を持ち、ここが未収集情報の最大の塊でした。

### 収集済みにしたもの

- **一般動作条件（General operating conditions / 通用工作条件）表** → `tables/operating_conditions.csv`（`tools/build_operating.py`）。クロック上限（F_HCLK等のF_系）と動作電圧範囲（V_DD、ADC/USB使用条件別）。62行中61行が両言語一致でconfirmed。family READMEの「## Series」表にMax clock・VDD列として反映
- **ロット依存注記（エラッタ）** → `tables/errata.csv` 21行（`tools/scan_errata.py`で走査、`curated/errata.csv`で管理）

抽出上の注意（build_operating.pyが吸収済み）: zh版の表題は「通用工作条件」（「一般」ではない）、絶対最大定格表が同一ページにあり`条件`列の有無で区別する、記号セルの折返しで`F_HCLK or F_SYS`が壊れる、脚注は全角括弧`（2）`、rowspanの単位セルはzh版で空になる。

### 未収集（今後の候補）

- **絶対最大定格**: 入力電圧上限・ESD耐圧・注入電流など。表構造は動作条件表と同型で抽出可能
- **消費電流表**: Run/Sleep/Standby別・周波数別のtyp値。列構造がネストしており（HSI/HSE×周波数×周辺ON/OFF）抽出コストは高め
- **flash耐久**: 擦写次数（例: V007は25℃で300K回）・データ保持期限（同20年）。小さい表で抽出しやすく、選定情報として価値が高い
- **発振器特性・ウェイクアップ時間**: LSI/HSI精度、モード復帰時間

### エラッタの増分監視

エラッタはdatasheet改版で増えるため、`uv run tools/scan_errata.py`を単体実行すると全datasheetを走査して既知（`curated/errata.csv`の`match`列）と照合し、未知の記述をNEWとして報告します（終了コード1）。mirror PDFが必要なためCIではなく手動運用です。datasheet更新を取り込んだら一度回してNEW: 0を確認します。
