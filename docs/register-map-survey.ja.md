# レジスタマップを持つとしたら: 現状調査

日付: 2026-08-21
状態: **調査のみ。方針は未決定**
発端: ArduinoCore-CH32 の R-20「レジスタマップを持つとしたら何のデータが要るか」
（`docs/research/register-map-data.ja.md`）が D-1〜D-8 を列挙し、
「device-dataへ依頼を出すかどうか」を判断待ちにしている。その判断に要る事実を測った。

R-20の未確認事項3件（ch32-dataの対応範囲・SVDのライセンス条件・上流をどこにするか）に
答えることを目的にしている。**この文書は依頼の受諾でも設計でもない。**

## 結論だけ

1. **12 familyすべてを覆う機械可読ソースはEVTだけ。** base address 614件、peripheral型 353件、
   register 5534件、bit field 33305件が取れる（後述の実測）。
   reference manualも中国語版を含めれば12 family揃うが、PDFなので取り出しの難度が段違いで、
   しかも英語版は途中で切れている箇所がある（後述）。両者は**相互確認の相手**になる
2. **サードパーティ2つは同じ7 seriesで止まる。** ch32-rs/ch32-data も ch32fun も
   **CH32V205 / V407 / V467 / X305 / X315 / M030 / M103** のレジスタ定義を持たない。
   これはこのrepositoryが独自に覆っている範囲とほぼ一致する
3. **D-5（peripheral型のversion key）は手で維持する必要がない。** 構造体のレイアウトと
   bit field名の集合をハッシュすれば familyがグループに分かれる。実測で I2C は4型、
   GPIO は6型、USART/SPI は8型。ArduinoCore側が`CH32_I2C_HAS_RTR`で手当てしている
   I2C の差は、このグループ分けにそのまま現れる
4. **EVTのbit defineはバナーコメントでregisterが決まる。** define名は持っていない
   （`RCC_USART1EN`はどのregisterかを言わない）。ここを読む前提の抽出器が要る

## 対象の12 family

`tools/build_all.py`が処理している family dir と、それが覆う series:

| family dir | series |
|---|---|
| CH32H417 | H415 H416 H417 |
| CH32L103 | L103 M103 |
| CH32M030 | M030 |
| CH32V003 | V003 |
| CH32V006 | V002 V004 V005 V006 V007 M007 |
| CH32V103 | V103 |
| CH32V205 | V205 |
| CH32V20x | V203 V208 |
| CH32V307 | V303 V305 V307 V317 |
| CH32V407 | V407 V467 |
| CH32X035 | X033 X035 |
| CH32X315 | X305 X315 |

## 機械可読ソースの棚卸し

### EVT（mirror済み・参照のみ）

`<family>/EVT/EXAM/SRC/Peripheral/inc/ch32*.h` を実測した数字。

| family | base address | peripheral型 | register | bannerで区切られた節 | bit field |
|---|---:|---:|---:|---:|---:|
| CH32H417 | 101 | 56 | 1000 | 548 | 7180 |
| CH32L103 | 47 | 28 | 384 | 229 | 1971 |
| CH32M030 | 32 | 21 | 317 | 168 | 1768 |
| CH32V003 | 26 | 18 | 169 | 143 | 1270 |
| CH32V006 | 29 | 18 | 188 | 161 | 1425 |
| CH32V103 | 58 | 22 | 303 | 218 | 1783 |
| CH32V205 | 57 | 36 | 566 | 282 | 3498 |
| CH32V20x | 43 | 29 | 456 | 267 | 2877 |
| CH32V307 | 67 | 37 | 747 | 332 | 4178 |
| CH32V407 | 76 | 40 | 673 | 392 | 3686 |
| CH32X035 | 33 | 21 | 299 | 163 | 1731 |
| CH32X315 | 45 | 27 | 432 | 208 | 1938 |
| **合計** | **614** | **353** | **5534** | **3111** | **33305** |

bannerに属さないbit defineは全体で**95件（0.3%）**。つまりバナー方式は例外がほぼ無い。

構造は次のとおりで、**registerを言っているのはコメントだけ**です。

```c
/******************  Bit definition for RCC_APB2PCENR register  *****************/
#define RCC_AFIOEN      ((uint32_t)0x00000001) /* Alternate Function I/O clock enable */
#define RCC_USART1EN    ((uint32_t)0x00004000) /* USART1 clock enable */
```

`RCC_USART1EN`という名前は`APB2PCENR`を含みません。既存の
`tools/extract_selectors.py`が`AFIO_PCFR1_`接頭辞だけで動けているのは、
AFIOがたまたま接頭辞を持っているからで、他のperipheralには使えません。

D-6（割込み番号）もEVTにあります: `IRQn`列挙が V003 27件 / X035 45件 /
M030 38件 / V407 94件 / V307 129件。
D-7（DMA channel）はbase addressだけがEVTにあり（14〜48件）、
peripheral→channelの対応はRM側です。

**registerの絶対アドレスは解けます**（2026-08-21）。R-24追補のA-2で
`EXTEN->EXTEN_CTR`の番地が必要になったので、`tools/extract_addresses.py`を
書きました。base定数の連鎖（`PERIPH_BASE`→`HBPERIPH_BASE`→`EXTEN_BASE`）と
`#define EXTEN ((EXTEN_TypeDef *)EXTEN_BASE)`と`typedef struct`のメンバー
オフセット（reserved配列も数える）を突き合わせて、`BLOCK->REGISTER`を
番地へ落とします。12 familyで**241〜2049 register**ぶん解けました。

| family | 解けたregister |
|---|---:|
| CH32H417 | 2049 |
| CH32V307 | 1492 |
| CH32V407 | 1416 |
| CH32V103 | 1163 |
| CH32V205 | 918 |
| CH32V20x | 819 |
| CH32X315 | 780 |
| CH32L103 | 647 |
| CH32X035 | 503 |
| CH32M030 | 474 |
| CH32V006 | 360 |
| CH32V003 | 241 |

既知の番地で検算しました: `GPIOA->CFGLR`=`0x40010800`、`GPIOD->OUTDR`=`0x4001140C`、
`USART1->STATR`=`0x40013800`、`AFIO->PCFR1`=`0x40010004`、`AFIO->PCFR2`=`0x4001001C`、
`FLASH->ACTLR`=`0x40022000`、`GPIOE->INDR`=`0x40011808`。**すべて一致**。

名前からの推測が効かない例も確認済みです——`AHBPERIPH_BASE`と`HBPERIPH_BASE`の
綴りが揺れ、**CH32X315はEXTENを`0x400220C0`に置き**（他は`BASE+0x3800`）、
**CH32V205はEXTENのregisterを`CTLR0`と呼びます**（他は`EXTEN_CTR`）。

つまりD-1（base address）とD-3（register offset）は**EVT headerから機械的に取れる**
ことが実測できました。残るのはD-2（bit field）で、そこが上の「registerを言っているのは
コメントだけ」という問題です。

### ch32fun（`~/dev_wch/ch32fun`、29MB、MIT）

LICENSEに CNLohr らと並んで **Nanjing Qinheng Microelectronics（WCH）の著作権表示**があります。
`ch32fun/*hw.h`はEVTヘッダを整形した派生物で、独立した出所ではありません。

| ヘッダ | 構造体 | define | 覆うseries |
|---|---:|---:|---|
| ch32v003hw.h | 23 | 2391 | V003 |
| ch32x00xhw.h | 26 | 2713 | V002 V004 V005 V006 V007 M007 |
| ch32x03xhw.h | 32 | 3432 | X033 X035 |
| ch32v10xhw.h | 32 | 3401 | V103 |
| ch32v20xhw.h | 38 | 5045 | V203 V208 |
| ch32v30xhw.h | 48 | 6169 | V303 V305 V307 V317 |
| ch32l103hw.h | 47 | 5396 | L103 |
| ch32h41xhw.h | 61 | 11653 | H415 H416 H417 |
| ch5xxhw.h / ch641hw.h | 10 / 28 | 1814 / 2835 | 対象外 |

**レジスタ定義が無いseries: V205 / V407 / V467 / X305 / X315 / M030 / M103。**
V205・M030・X315は`minichlink`のchip表やREADMEに名前があるだけで、書き込み器の対応であって
レジスタ定義ではありません。

`misc/CH32V003xx.svd` が1件だけあります。`<vendor>WCH Ltd.</vendor>`の
ベンダ製SVDで、peripheral 22件・field 936件。`licenseText`要素は**ありません**。

### ch32-rs/ch32-data（`~/dev_wch/ch32-data` にclone済み）

`data/chips/*.yaml` が78件（SKU単位）、`data/registers/*.yaml` が117件で
**peripheral型×型version**単位。これはR-20のD-3/D-4/D-5がまさに要求している形です
（`i2c_v0.yaml`、`i2c_v3.yaml`、`afio_x0.yaml`、`usart_common.yaml` など）。

SKUから型への解決は `data/chips/<SKU>.yaml` の`include_peripherals`が
`data/family/<F>.yaml`を指し、そこに`registers: {kind: afio, version: x0}`があって
`data/registers/afio_x0.yaml`へ落ちる、という2段です。
`tools/crosscheck_ch32data.py`がこの鎖を辿ります。

対象SKUのうち**存在するもの**: H415 H416 H417 / L103 / M007 / V002 V003 V004 V005 V006 V007 /
V103 / V203 V208 / V303 V305 V307 V317 / X033 X035。

**無いもの: V205 / V407 / V467 / X305 / X315 / M030 / M103。**
R-20の推測（M007も無いだろう）は外れで、M007はあります。残り7つは推測どおり無い。

逆にこちらに無くて向こうにあるものもあります: **CH32X034**、および旧CH32F103系。

### 突き合わせた結果（AFIO remap field）

`tools/crosscheck_ch32data.py`で`tables/remap_fields.csv`と照合しました。
19 seriesが照合可能で、**185一致・不一致1**。

不一致の1件はこちらが正しく、**ch32-data側の過度な一般化**でした。

```
CH32V103  USART1   ch32-data=PCFR1:2,PCFR2:26   うち=PCFR1:2
```

ch32-dataの`data/family/CH32V1.yaml`は`version: v3 # compatible with v1`と書いて
CH32V30xのAFIO定義をV103へ流用しています。しかしEVTの`ch32v10x.h`は
`AFIO_PCFR2_`定義を**1つも持たず**、`ch32v10x_gpio.h`も`GPIO_Remap_USART1`だけで
`_HighBit`がありません。V103のUSART1はPCFR1 bit2の1bit fieldです。

「まず独自に取得し、既存のものとは突き合わせる」という方針が、この1件で機能しました。
逆向きの差もあります: こちらにあって向こうに無いのが
`CH32V003 ADC1_ETRGINJ`と`CH32V203 TIM1_CAP`の2件。

なお「うちが持たない field」が172件出ますが、これは方針の差です。ch32-dataはAFIOの
全fieldを載せ、こちらは**pin経路が参照するfieldだけ**を載せます（`SW_CFG`、ADCトリガ、
HSLVのI/O設定などはpin remapではないため対象外）。

ライセンスはREADMEが明言しています。「SVD files are provided by MounRiver Studio」を
ch32-rs側が後処理し、「most of the chip definitions are manually written」。
プロジェクト自体はMIT/Apache-2.0。**元SVDの条件は書かれていません。**
R-20の未確認事項#2はこの状態のままで、ch32-dataがMIT/Apacheで配っていることは
元SVDの条件を解決しません。

### Reference manual（PDF、mirror済み）

`tools/extract_registers.py`が既にregister表を読み、
register名・field名・bit offset・幅・access・reset値を返します。remap系の
`reset_value`はこれが出所です。ただし2点あります。

- **中国語版のほうが新しく、内容も多い。** 実測: CH32X035のregister fieldは
  英語版876件に対し中国語版895件。CH32X035の`TIM1_RM`の経路一覧は英語版が値1の途中で
  切れているのに対し中国語版は値2まで読めます。また英語版だけが1行を小文字で書く
  （`010: mapping (rx/pc17, ...)`）のに対し中国語版は全行が同じ書式です。
  `tools/build_all.py`は現在**両版を読んで和を取り**、scalarが食い違ったときは
  後に読んだ中国語版を採ります
- **CH32V407/V467のRMは`datasheet_zh/`にあります**（`datasheet_en/`にはDS0だけ）。
  中国語版の`CH32V407RM.PDF`から格子経路434件・21 selectorが取れ、
  しかも分割fieldを明記しています——
  「USART1_RM为AFIO_PCFR1寄存器bit2」「USART1_RM1为AFIO_PCFR2寄存器bit26」。
  これはEVTの関数がbit 27を書く（＝EVT側のバグ）ことの裏付けになりました
- **registerの見出し判定が走り過ぎます。** CH32FV2x_V3xRMを読ませると
  DMAのfield（`MEM2MEM`・`PL`・`NDT`・`PA`・`MA`など）が`AFIO_PCFR2`の下に付きます。
  見出しが更新されないまま次のregister表へ入るためです。remap系では
  「幅8bit超は除外」で実害を避けていますが、D-3/D-4の材料にするなら
  ここを直すのが前提になります
- **中国語版にはregisterの絶対アドレス表があります。** 例（CH32X035 表8-13）:
  `R32_AFIO_PCFR1 / 0x40010004 / 重映射寄存器 / 0x00000000`。
  D-1（base address）とD-3（offset）の裏取りに使える形で、まだ抽出していません

## D-5は計算できる

EVTの`<PERIPH>_TypeDef`のメンバ列と`<PERIPH>_*` bit define名の集合を
ハッシュして family をグループ分けした結果です。`reg`はメンバ数、`field`はdefine数。

| peripheral | 型数 | グループ |
|---|---:|---|
| I2C | **4** | `reg18 field68`: H417 L103 V103 V205 V20x V307 V407 ／ `reg16 field59`: V003 V006 X315 ／ M030 単独 ／ X035 単独 |
| GPIO | 6 | `reg7 field197`: L103 M030 V103 V205 V20x V307 V407 ／ H417 ／ V003 ／ V006 ／ X035 ／ X315 |
| USART | 8 | L103+V003+X035 ／ V103+V20x ／ V307+V407 ／ H417 ／ V006 ／ V205 ／ X315 ／ M030（`USART_*`のdefineが0件） |
| SPI | 8 | H417+V307 ／ L103+V205 ／ M030+V006 ／ V003+V103 ／ V20x ／ V407 ／ X035 ／ X315 |
| TIM | 11 | V307+V407 のみ共有、他は単独 |
| ADC | 11 | V103+V20x のみ共有、他は単独 |
| RCC | 12 | 全て単独 |
| AFIO | 12 | 全て単独 |

読み取れること:

- **I2Cの4型分けは、ArduinoCore側が手で書いている差と一致します。** `reg18`側が
  RTRを持つ群（V20x/V30x系）で、`reg16`側が持たない群（V003/V006）。ただし
  **X035とM030はそれぞれ独立した型**で、V003と同じではありません。
  `CH32_I2C_HAS_RTR`の2値では足りない、という具体的な材料になります
- RCC・AFIOが12型（全部違う）なのは想定どおりで、この2つは型を共有できません。
  D-3/D-4を「型で共有する」効果はGPIO・I2C・USART・SPIに出て、RCC/AFIOには出ません
- M030の`USART_*` bit defineが0件なのは、M030がこのperipheralを **UART** と呼ぶためです。
  `remap_routes.csv`の`peripheral`列が`UART1`になるのと同じ事情
  （`tools/signal_vocabulary.py`）

つまりD-5は「familyごとに人が1個ずつ足す」ものではなく、**D-3/D-4を抽出した副産物として
出てくる**。R-20の表でD-5が「手で足している」とされている箇所は、機械化できます。

## 現状のtables/に無いもの

`tables/`にあるのは products / series / families / packages / pins / pin_functions /
remap_fields / remap_routes / errata / documents / cores / evt_examples /
operating_conditions / product_attributes。**registerの表は1つもありません。**

例外的に`remap_fields.csv`が「AFIOのどのregisterの何bitか」を持っていますが、
これはpin routeのための最小限です。ただしその1件を作る過程で、D-3/D-4に必要な
仕掛けは既に揃っています。

- EVTヘッダのbit define解析（`tools/extract_selectors.py`）
- RM register表の解析（`tools/extract_registers.py`。register/field/offset/幅/access/reset）
- **EVTの関数をホストでコンパイルして挙動を観測する**（`tools/extract_remap_fields.py`）
- 資料間で名前を揃える語彙規則（`tools/signal_vocabulary.py`）
- 出典と確信度を`#`の右に持つ表の作法（D-8はこの形にそのまま乗る）

## 判断に必要な材料（決めていない）

方針は「**まず独自に取得し、既存のものとは突き合わせてチェックする**」で確定
（2026-08-21のユーザ指示）。以下は残っている論点。

- **上流をどこにするか。** EVTだけが12 family全部を覆い、しかも
  「EVTは参照のみ・事実は導出する」はこのrepositoryの既定の作法です。
  一方 ch32-data は D-3/D-4/D-5 の形が完成しており、7 series欠けている以外は先に進んでいます。
  **7 seriesがこのrepositoryの独自価値とほぼ一致する**ので、
  「ch32-dataを上流にする」と欠けた7 seriesだけ別扱いになり二重管理になります。
  方針どおり「独自に持つ」なら、ch32-dataはremapでEVTデコーダが果たしたのと同じ
  **独立した突き合わせ相手**になります。AFIOでは既に185件を照合済みで、
  その形をD-3/D-4へ広げるのが自然な次手
- **元SVDのライセンス条件。** MounRiver Studio由来のSVDの条件は
  ch32-dataも明示していません。EVTと同じ扱い（参照して事実を導出、複製しない）に
  収めるなら追加の論点は増えませんが、SVDを取り込むなら確認が要ります
- **段階の切り方。** R-20が提案する「まずコアが触っている7つ（RCC/GPIO/AFIO/USART/I2C/SPI/TIM）」は
  上の型数と噛み合います。この7つで型は 12+6+12+8+4+8+11 = 61型、
  bit fieldは概算で全体の半分弱
- **検証手段。** D-3（registerとoffset）はEVT構造体とRM register表の**2資料で相互確認できます**。
  D-4（bit field）は EVTのbanner節とRM register表の説明文で同じことができます。
  remapで「EVTデコーダをホスト実行して242 selector全一致」を作れたのと同じ役割を果たせます
