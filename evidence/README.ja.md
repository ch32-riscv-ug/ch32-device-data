# 証拠（evidence/）

[English](README.md)

**資料は何と書いているか**を、行ごとに出所（`basis`）と確度（`confidence`）を付けて写した
33 表です（[docs/data-layout.ja.md](../docs/data-layout.ja.md)）。綴りは原典のまま——
`pin_functions.signal` は `TX1` / `UTX` / `USART1_TX` と資料どおりに揺れ、`pad` は
`PA0-WKUP` と装飾ごと持ちます。資料どうしが食い違えば値を直さず `conflict` にして両方を残します。
**引く**ための表（語彙で揃えた名前・結合済み・型番ごとに割ったもの）は
[`index/`](../index/README.ja.md) にあり、鍵の名前は [`catalog/`](../catalog/README.ja.md) にあります。

**テーブルごとの信頼度（どこまで固いか・既知の穴）は
[docs/table-reliability.ja.md](../docs/table-reliability.ja.md)**、用語は
[docs/glossary.ja.md](../docs/glossary.ja.md) にあります。

## 列の種類

| 種類 | 例 | 規則 |
|---|---|---|
| 資料の綴り・値 | `signal`・`pad`・`parameter`・`request`・`define` | そのまま。型だけ揃える（数・hex・単位） |
| **付与識別子** | `remap_fields.selector`・`operating_conditions.symbol`・`product_attributes.attribute`・`pins.kind`・`clock_symbols.role`・`opa_cmp_registers.unit` | 資料が名前を付けていないものに repository が付けた鍵。資料の綴り（`field`・`parameter`・`label_zh/en`・`type`）が同じ行に残る |
| 目録の鍵 | `part_number`・`series`・`family`・`document` | 正規化した名前（結合のため） |
| 出所 | `#` より右の `confidence`・`basis`（`products` は列ごと） | 全行に付く |

語彙で導出した列（`peripheral`・`role`・`port`・`gpio`、pin から数えた `channels`）は
ここには**無く**、索引にあります。

**そのまま読める表（安定）**: EVT ヘッダから写した `interrupts`・`memory_map`・`systick`・
`clock_*`（5表）・`evt_variants`・`clock_enables`・`pin_alternate`と、`memory_configs`・
`flash_geometry`・`adc_internal`・`debug_data` は、名前が最初から機械の語彙なので索引に写していません。
consumer はこれらを直接読んでよく、列は索引と同じ扱いで安定させます。

## 各ファイル

### `pins.csv` / `pin_functions.csv`

**注文型番単位**です。pins.csvは1行1(part_number, pin, pad)で「この型番のlead Nにどのpadが載るか」、pin_functions.csvは1行1(part_number, pad, signal, route)で「この型番のpadが持つ機能」。datasheetのpin表は1つのpinoutを複数型番で共有します（表題が適用範囲を宣言: `CH32V103x8x6`、`CH32V006（除F4U6以外）`、`TSSOP20(F8)`）が、その解決は生成時に済ませてあり、**行はpart_numberでそのままproducts.csvと結合できます**。共有していた事実はメタ側のdatasheet/table列（出典）に残ります。

#### `route`の値の意味（**「デフォルト」が2つの別々のことを指します**）

`route`は**datasheetのpin表の列そのもの**です。全12 familyが同じ4列を持ちます（列見出しを実測して確認）。

| `route` | 出所の列 | 意味 | **電源投入直後に動くか** | 行数 |
|---|---|---|---|---|
| `main` | 主功能（复位后）/ Main function (after reset) | リセット直後にそのpadがやっていること | **動く** | 4,510 |
| `default` | 默认复用功能 / Default alternate function / 引脚功能 | remapレジスタを触らず（値0のまま）**AFモードにしたら**出る機能 | **動かない** | 9,335 |
| `remap-N` | 重映射功能 | AFIOのremapフィールドに N を書く | 動かない | 9,869 |
| `af-N` | 同じ列にAF番号が併記される（`SDA(AF7)`） | そのpadのAF番号に N を書く | 動かない | 4,497 |
| `alias` | pad名の欄の括弧（`LO1\n(PA0)`） | **機能ではない**。そのpadの**GPIOとしての名前**を資料が別名として添えたもの | — | 30 |
| 空 | — | 経路番号が資料になく要確認 | — | 242 |

#### `alias`——pad名にGPIO名が括弧で付くとき（CH32M007 / CH32M103）

CH32M007とCH32M103のゲートドライバ出力は、pin表のpad欄が **`LO1` と `(PA0)` の2行**です。
pad の名前は`LO1`で、括弧はその足が素のCH32V007ではPA0であること（GPIOとしての名前）を
言っています。逆にCH32M030は同じ種類のpadを`PB9`と書いて`HO0`を`default`機能の側に置きます
——**同じ物理を資料が反対向きに書いている**ので、どちらにも寄せずに資料の向きのまま持ちます。

| 資料の書き方 | `pins.pad` | `pin_functions` の行 |
|---|---|---|
| CH32M030: pad `PB9`、既定代替機能 `HO0/TIM1_CH1` | `PB9` | `(PB9, HO0, default)` `(PB9, TIM1_CH1, default)` |
| CH32M007: pad `LO1 (PA0)`、主機能 `LO1` | `LO1` | `(LO1, LO1, main)` **`(LO1, PA0, alias)`** |

**見方**:
- 「M007のPA0はどの足か」→ 索引`index/pinout.csv`で`port=A, gpio=0`を引く（`port`/`gpio`はaliasからも埋める）。証拠だけで辿るなら`pin_functions`の`signal=PA0, route=alias`から`pad`→`pins`の`pin`
- 「M007のLO1はどの足か」→ `pins`で`pad=LO1`
- `alias`の行は**機能の一覧に混ぜないでください**（索引`index/pinout`には機能として載せず、生成READMEでは
  pad名の隣に`LO1 (PA0)`と出す）。PA0としてGPIO出力に使えるかは資料が言っていないので、
  この表も言いません
- `tools/check_tables.py`が、alias行のsignalがGPIO名であること・padがGPIO名でないこと・
  padごとに1つであることを見ます

**`default`は「設定しなくても動く」ではありません。** 「remapを書かなくても届く」です。リセット直後のGPIOはフローティング入力で、**GPIOモードを代替機能にするまで代替機能は出ません**。AF方式のfamilyでも同じで、`GPIOx_AFLR`のリセット値0がAF0を選ぶことと、GPIOモードを代替機能にすることは別の設定です。

具体的には、**UARTは`main`が1行もありません**（TX/RXは全部`default`/`remap-N`/`af-N`）。電源を入れただけではUARTは出ません。`main`に出るのは`SWDIO`/`SWCLK`/`BOOT0`/`BOOT1`と、専用padのリセット機能（`NRST`・`OSC_IN`/`OSC_OUT`・`XI`/`XO`・Ethernetの`MDI*`・USB3.0の`SS*`）だけです。

#### **どちらの列に書くかはfamilyで揃っていません**

同じSWDが、datasheetによって主功能列だったり既定代替功能列だったりします。

```
主功能列に書く:       CH32L103 / CH32V103 / CH32V20x / CH32V307
既定代替功能列に書く:  CH32H417 / CH32M030 / CH32V003 / CH32V006 / CH32V205 / CH32X035 / CH32X315
両方に出る:           CH32V407
```

CH32L103はPA13の主功能を`SWDIO`と書き、CH32X035はPC18の主功能を`PC18`（GPIO）、既定代替功能を`DIO`（＝SWDIO）と書きます。**物理的にはどのfamilyもリセット時にSWDが生きています**（それでデバッガが素で繋がる）。列の違いは資料の書き方の違いです。

**なので「リセット時に生きているか」を引くときは`main`だけを見ないでください。** `main`で引くと7 familyのSWDを落とします。`tools/build_readme.py`が`main`と`default`の両方を見ているのはこのためです。

`route`は資料の列を保つ（綴りと出所が証拠なので変えない）方針なので、この揺れの吸収は読む側の仕事です。

両言語照合で吸収している表記ずれ: 表番号のずれ（X315はzh`表2-1-1`=en`Table 2-1`。表題中のシリーズ名で照合）、列見出しの綴り（`QFN48×7`、`QFN28(6)`、zh`LQFP64M`=en画像`LQFP64`は表内の消去法でペアリング）、1列が複数packageを兼ねる見出し（`LQFP48/QFN48X7`は成分ごとに登録）。

**pin表とRMのremap格子が食い違う行**（CH32V103のTIM3。pin表は`TIM3_CH1_1`をPB4とPC6の両方に書くが、RM格子はPB4=2・PC6=3で値1は定義されていない。F-41）は、**値はpin表のまま**`conflict`にし、basisに`!rm-remap-grid(=remap-2)`と格子の値を並べています。格子の値を採るのは索引`index/pinout.csv`の側です。

### `product_attributes.csv`

比較表の**全属性を縦持ち**で保持します（列に昇格済みのflash/sram/pin数/GPIO/温度/packageは除く）。両言語はラベルの語が違う（`定时器`↔`Timer`）ため、**正規化した値の並びのLCSで行を対応付け**ます——翻訳は表の行順を保つので、同値同順は同じ行です。対応付いて値が違う行はconflictになります（例: CH32H417WEU6のOPA数はzh=1/en=2で本物の食い違い）。`label_zh`/`label_en`に原文ラベルを残しています。

**`order`は資料の行の並び**です。比較表は関連する行を固めて組んでいるので、属性名のアルファベット順に並べ替えると読みにくくなります。ファイルもこの順で並びます。

**`label`は表示用の見出し**です。`value`と同じ作法で、英語版が言っていればそれを、無ければ中文を訳したものを置きます（原文は`label_zh`/`label_en`に残ります）。**中文が混ざらないのはこの列だけ**なので、表示にはこちらを使ってください。

**`group`は見出しの上の段**です。比較表の見出し列は2段組みで、`label`はそれを繋いだ全体（`Communication interfaces CAN`）を持ちます。下の段だけが要るとき（表示するとき）に上の段を剥がせるよう、分けて持ちます。`group`は必ず`label`の接頭辞です。

剥がすかどうかは読む側が決めます。目安は2つ——剥がすと別の行と同じ名前になるとき（`ADC/TKey Unit`と`HSADC Unit`）と、剥がすと普通の英単語しか残らないとき（`Unit`・`Voltage`）は剥がさない。略語か数を含んでいれば（`CAN`・`Basic (16-bit)`）それ自身が何かを名指しているので剥がせます。`attribute`列（結合キー）は**繋いだ全体から作る**ので、剥がしても衝突しません。

### 同じlead番号を複数のpadが持つ行

**`(part_number, pin)`は主キーではありません。** 1本の足に2つのpadが出ていることがあり、datasheetはそれを**番号のセルを縦に結合して2行に掛ける**ことで書きます（`CH32L103F8U6`は結合を使わず`17`を2度書いていて、同じことを別の書き方で言っています）。96箇所あり、意味は4通りです。

| 形 | 件数 | 意味 |
|---|---|---|
| `gpio` + `gpio` | 65 | **チップ内部で短絡されたIOペア**。`PA11`と`PA13`が同じ足 |
| `gpio` + `other` | 15 | `BOOT0`と`PB9`のような、機能padとIOの共用 |
| `power` + `power` | 12 | 小さい封装で基準電圧を電源に寄せたもの（`VREF-`と`VSSA`） |
| `power` ×3 | 2 | `VS1`/`VS2`/`VS3` — 同じ電源節点 |
| `gpio` ×3 | 2 | 8ピン品。3つのIOが1本に出る |

**内部接続であることを別の列や表記では持ちません。** 番号が一致していることがそれそのものなので、`(part_number, pin)`で引けば相手が出ます。`PA13 (PA11)`のような表記を足すと、同じ事実が2箇所に分かれて食い違い得るうえ、検索の邪魔になります。

**「両方を同時に出力にしてはいけない」も列を持ちません。** 同じ`pin`に`kind=gpio`の行が2つ以上あることから導けます——datasheetの注記がそう書いています:

> the PC10 and PC17 pins are short-joined inside the chip, and **both IOs are prohibited from being configured as output functions**（CH32X035DS0 注記4）

電源padの共有（`VS1`/`VS2`/`VS3`、`VREF-`と`VSSA`）は同時使用が当たり前なので、`kind`が自然に両者を分けます。

読み方は資料の別の場所で検算できます。CH32L103の注記8は`F8U6`について`PB1`/`PB10`・`PB6`/`PB13`・`PA12`/`PA14`・`PA11`/`PA13`の**4組を名指し**していて、結合セルから復元した4組と一致します。CH32V407の`VREF-`と`VSSA`が同じ足になるのは、電気特性表の`V_REF- is equal to V_SS`が独立に裏付けます。

#### 資料が「使わない」と書いた足（`kind=nc`）

何も出ていない足にも番号があり、pin表はその行を印刷しています。同じ文書群がその行のpad欄を4通りに綴り——`NC`・`NC.`・`未使用`・`Unused`——型と機能の欄は空です。この行も持ちます。padの綴りは`NC`に揃え、`kind=nc`（露出パッドの番号を`EP`と綴るのと同じ正規化）、`pin_functions`の行は持ちません。5型番の8 lead（CH32V203RBT6の47/48、CH32V205VCT6とCH32V303/307/317VCT6の73）。

**数がそのまま検査になるので落としません。** LQFP100の足は1〜100の100本しかない、と`catalog/packages.pin_count`が言っていて、これはpin表の読みをpin表**以外**の出所で測れる唯一の不変条件です（`tools/check_tables.py`の`pin_numbering`）。落としていたときの実害は「無くなる」だけではありませんでした——pad欄をpad名と見なせないと、CH32V203RBT6のlead 47は**直前の行のpad名を継いで`VDD_2`になり**、LQFP64Mの表がそこに置いていないpadが表に出ていました（worklistのF-49）。

### `timers.csv`

**「このタイマのカウンタは何ビットか」**を機械可読にした表です。比較表は`Timer General-purpose TIM4 (32-bit)`のような**文**をseries粒度で持つだけで、綴りも`ADTM`/`GPTM`/`高级定时器`と揺れます。consumer側が32bitタイマの一覧を手書きすると、そこが間違ったときに周期の計算が静かにずれます。

出所は**RMのregister見出し**です。見出しが種類と対象タイマを、直後のfield表が幅を言います。

```
14.4.10 高级定时器的计数器（TIMx_CNT）（x=1/8）      [15:0] CNT[15:0]  → advanced 16bit
15.4.11 通用定时器的计数器（TIMx_CNT）（x=9/10/11/12） [31:0] CNT[31:0]  → 32bit
```

チャネル数（`channels`・`complementary`）はこの表には無く、pinに出ている機能から数えた導出として索引の[`index/timers.csv`](../index/README.ja.md)が持ちます。`update_vector`は`interrupts.csv`から引きます。高級タイマはベクタが4本に割れるので（`BRK`/`UP`/`TRG_COM`/`CC`）、**更新割り込みの`TIMn_UP`を名前で選びます**。

**幅がvariantで変わるものがあります。** CH32V20xのTIM5がそれで、RMの注が

> 注：32位的TIM5_CNT仅适用于型号为CH32F20x_D8W、CH32V20x_D8、CH32V20x_D8W系列的产品，其他系列芯片的TIM5_CNT为16位。

と書きます。名指しされたmacroを`condition`に置き（`interrupts.csv`と同じ持ち方）、`confidence`は`varies-by-package`。**同じRMを共有する別familyがそのvariantを持たない場合は`conflict`**にします——CH32V307はCH32V20xとRMを共有しますが注のvariantを持たないので、32bitと言い切れません。

### `flash_geometry.csv`

**低レベルflash APIの前提**です。`products.csv`は容量しか持たず、消去単位と書き込み粒度はfamilyごとに違います。

| 列 | 意味 |
|---|---|
| `page_erase_bytes` | 標準ページ消去の単位（1K/2K/4K） |
| `fast_erase_bytes` | 快速ページ消去の単位（64B/128B/256B）。V407/X315/H417は**per-pageの快速消去を持たず**ブロック消去のみ（空） |
| `fast_program_bytes` | 快速ページ書き込みの単位 |
| `block_erase_bytes` | 快速ブロック消去の単位（32K。V205は64K） |
| `program_word` | `FLASH_ProgramWord`/`ProgramHalfWord`がdriverにあるか。**空＝快速ページ経由のみ**（L103/M030/V006/V205/X035） |
| `zero_wait_note` | `flash_bytes`（零等待領域）と総容量の関係。option byteで動くfamilyは`memory_configs.csv`、総容量は`product_attributes`の`code_flash_bytes`を指す |
| `note` | モード依存。CH32H417は`FLASH_CFGR0` bit28（dual flash mode）でページ8K・ブロック64Kになる。列の値はsingle mode |

出所は**EVTのflash driverの`@brief`**（`page size 4KB`・`1page = 256Byte`）と**RMの闪存章の本文**（`标准页（1K字节）`・`快速编程按页（128字节）`）の2つで、突き合わせて確度を決めます。**実際に食い違いが1件**あります——CH32V103のdriverは`ProgramPage_Fast ... 256Byte`と書きますが、RMは`快速编程按页（128字节）`、同じdriverの消去側も128B、`ROM_ERASE`の引数条件も`StartAddr%128 == 0`。EVTコメントの写し間違いと判断して値は128、`conflict`で両論を`basis`に残しています。

### `opa_cmp_registers.csv`

**コンパレータ/OPAクラスの前提**です。baseは`memory_map.csv`、入力padは`index/pinout.csv`が持つので、足りないのは**フィールドの配置**——enable・入力select・出力・gain。

**blockの置き方がfamilyごとに違い、それがこの表の要る理由です。**

| family | 置き場所 |
|---|---|
| X035 / L103 / V006 | OPA block。`CTLR1`がOPA、`CTLR2`がCMP（同じblock） |
| M030 | OPA blockの中に`CMP_CTLR`/`CMP_STATR`（QII/ISPと同居） |
| V205 / H417 | OPA blockに`OPA_CFGR1`/`CMP_CTLR`…と名前を全部書く |
| V30x / V407 | OPA blockは`CR` 1本 |
| V003 | OPAは**`EXTEN_CTR`のbit16-18**（blockを持たない） |

`unit`列が**そのレジスタがOPAのものかCMPのものか**を言います。RMの見出しは`OPA控制寄存器 2（OPA_CTLR2）`としか書かず（blockを言うだけ）、フィールドの説明文（「CMP3正端输入通道选择」対「OPA2正向输入端选择」）の多数決で決めています。RMがそのblockのfieldを1つも書かないfamily（V30x/V407の`CR`、H417）は名前で分かる`CMP_*`以外をOPAとします。

出所はEVTヘッダの構造体（配置）とbit define（`OPA_CTLR2_EN1 ((uint32_t)0x00000001)`）で、**RMのレジスタ表と突き合わせ**ます。bit位置が一致すればconfirmed（293行中199）。**食い違いが5件**あり、両論を`basis`に残しています（F-44/F-45）——CH32X035の`OPA_CTLR2_CMP_LOCK`は`0x2000`（bit13＝`PSEL3`と同じ）と書かれていますがRMはbit31で、**ヘッダの値で書くとCMP3の正入力選択を壊します**。L103の`ITRIMN`/`ITRIMP`はヘッダ5bit・RM6bit、V205の`HYS1_H`/`HYS2_H`はヘッダbit29/30・RMbit19/29。

`purpose`はfield名の綴りから機械的に付けます（`EN`→enable、`PSEL`→positive input select…）。名乗っていないものは空です。多bit fieldの値の列挙（`BKIN_CFG_0`/`_1`）はfieldではないので載せません。OPA/CMPのbit defineを持たないfamily（V20x・V103・X315）は行がありません。

### `clock_enables.csv`

**family × peripheral → どのRCCレジスタの何bitか。** consumer側が`CH32_RCC_APB1_TIM4`のようなdefineをfamilyごとに手書きしていたものを、全peripheral分揃えたものです。

出所はEVTの`ch32*_rcc.h`——`RCC_<bus>PeriphClockCmd()`に渡す定数がperipheralごとのbitで、**busの名前がレジスタを言います**（`RCC_AHBPeriph_USBPD`→`RCC->AHBPCENR`）。busの呼び名はfamilyで違います（AHB/APB1/APB2、HB/PB1/PB2、HB/HB1/HB2）。`RCC_<bus>PeriphClockCmd`が`RCC-><bus>PCENR`へ書くことは8 familyのrcc.cで確かめ、例外はありません。

RMのレジスタ表（`RCC_HBPCENR`の`USBPDEN`）と突き合わせ、**429行中370行がconfirmed、conflict 0**。referenceの59行はRM側のfield名がEVTと綴りで一致しなかったもの（`ETH_MAC_Rx`など）で、bitの誤りではありません。GPIOはEVT`GPIOA`/RM`IOPAEN`と綴りが違うので別名として引いています。

### `adc_internal.csv`

**`temperatureRead()`相当のAPIの前提**です。温度センサと内部参考電圧が**ADCのどのチャネルか**はfamilyで違い、温度センサを持たないfamilyもあります（V003/V006/M030/X035/X315は`vrefint`行のみ）。

| 列 | 意味 |
|---|---|
| `source` | `temperature_sensor` / `vrefint` / `vdd_half` |
| `channel` | ADC_INの番号 |
| `sample_time` / `sample_time_unit` | 読むときに必要なサンプル時間。**単位がfamilyで違う**（`us`または`adc_cycles`=ADCクロック周期数）ので揃えず両方持つ。`sample_clock_mhz`は`us`のときの条件 |
| `v25_mv`（min/max） | 25℃での温度センサ出力 |
| `avg_slope_uv_c`（min/max） | 平均傾き（負温度係数。datasheetはmV/℃、ここはuV/℃） |
| `vrefint_mv`（min/max） | 内部参考電圧 |
| `temp_range_c` / `temp_error_c` | 測定範囲・誤差 |

出所はdatasheetの散文（「温度传感器在内部被连接到IN16输入通道上」）と電気的特性の表（`温度传感器特性`・`内置参考电压`）。英語版に同じ表があるので数値が一致すればconfirmed。**V003とX035はdatasheetがチャネル番号を書かず、RMのADC章が書く**（`连接ADC_IN8通道`/`ADC_IN15`）ので、そこはRMから取って`basis`に書いています。

**conflictはzh/enの食い違いそのもの**です。CH32V20x/V307のAvg_Slope最大値はzh 4.8 / en 4.7 mV/℃。

### `usbpd_plumbing.csv`

**X035以外のseriesへPDを広げる前提**です。足りなかったのは**RCCのenable bit**（`clock_enables.csv`のUSBPD行）と**PHY設定bitの所在**で、後者はfamilyで置き場所が違います。

| family | PHY設定bit |
|---|---|
| X035 | `AFIO->CTLR` の `USBPD_PHY_V33`(bit8) / `USBPD_IN_HVT`(bit9) |
| L103 / V205 | `AFIO->CR` の `USBPD_IN_HVT`(bit9) |
| X315 | `AFIO->CR` の `USBPDHVT`(bit0) / `USBPDRISE`(bit2:1) |
| H417 | `AFIO->PCFR1` の `USBPD_CC_HVT`(bit20) |
| M030 | `EXTEN->EXTEN_CTLR0` の `USBPD0/1_CC_REF` / `CC_HVT` / `LVE_T`（PDが2つ） |

**PDのfieldだけ**を載せます。X035の`AFIO_CTLR`やM030の`EXTEN_CTLR1`にある`UDP_*`/`UDM_*`（USBのD+/D-パッド制御）はUSBの配管でPDではないので入れていません。1行が1つのPHY fieldで、RCC側の列は行ごとに繰り返します。出所はEVTヘッダ（define名がレジスタを名乗るか、名乗らないものは直前のbanner「Bit definition for EXTEN_CTLR0 register」）で、RMのレジスタ表とbit位置を突き合わせています。

### `register_blocks.csv` / `registers.csv` / `register_fields.csv`

**レジスタマップの、機械的に集められる部分**です（consumerのR-20。2026-08-25）。出所は12 family
すべてを覆う唯一の機械可読ソースであるEVTのdevice header（`ch32*.h`）で、reference manual（zh）の
レジスタ表でbit位置を突き合わせています。**EVTは参照するだけで複製しない**という作法どおり、
headerの定義をそのまま写すのではなく、構造（block→型→register→field）に分解した事実だけを持ちます。

| 表 | 1行 | 何が分かるか |
|---|---|---|
| `register_blocks` | family × block（`USART1`）676行 | 型（`USART`）・base address・layout key。`#define USART1 ((USART_TypeDef *) USART1_BASE)`から。**RM zh版の絶対アドレス表と1つ以上のregisterの番地が一致したblockはconfirmed（548）**。型の構造体がdevice headerに無いblockが1つ（H417の`UHSIF`）あり、layoutは空 |
| `registers` | family × 型 × register 4,995行 | 構造体内のoffset・幅（8/16/32/64）・配列数。入れ子の構造体（CANの`sTxMailBox[0].TXMIR`）は親からのoffsetで平坦化。unionで重なるregister（H417 TIMの`CNT`と`CNT_32`）は同じoffsetの2行。`rm_address_check`はRMの絶対アドレス表との照合（`ok:N`=一致したinstance数、`mismatch:N`）、`rm_reset`はその表の復位値（`0x0000xx83`のように`x`を含むことがある） |
| `register_fields` | family × register × bit define 33,365行（field 24,792・value 8,573） | bit位置（`hi:lo`）・mask・種類（`field`か、fieldの中の`value`か）・EVTの1行説明・RMのaccess/reset。**`define`はEVTの綴りそのまま**（`RCC_APB2PCENR_USART1EN`）、`field`は型・registerの接頭辞を落とした読みやすい名前。fieldの27.5%（6,829）がRMとbit位置一致、38がconflict |

導出の **layout key**（family × 型 → 構造体の形のハッシュ。同じkeyのfamilyは同じレジスタ定義を共有できる）は索引の[`index/register_layouts.csv`](../index/README.ja.md)にあります。register×fieldを結合して絶対番地を付けた引き口も索引（`index/registers.csv`・`index/register_map.csv`）です。

**見方**:
- **絶対アドレス** = `register_blocks.base_address` + `registers.offset`（同じfamilyの`type`で結合）。
  `USART1->STATR`なら blocks(USART1)=0x40013800 + registers(USART, STATR)=0x000
- **`register_fields.register`はheaderのbanner（`Bit definition for RCC_APB2PCENR register`）の綴り**で、
  RMのレジスタ表と同じ形（`RCC_APB2PCENR`）。構造体のメンバーへの対応は`member`列
  （`RCC.APB2PCENR`）に**付くものだけ付けます**。bannerがinstance番号を含むもの（`DMA_CNTR7`→
  `DMA_Channel.CNTR`）は付きますが、CANのメールボックス/フィルタ（`CAN_TXMI0R`・`CAN_F30R2`）や
  構造体を持たないdefine群（H417の`SERDES_*`・`TKEY_*`、M030の`UART_*`・`CMP_*`）は`member`が空です（1,591行＝4.8%）。**空でも行は消していません**
  ——bit位置とmaskはheaderが言っているとおりです
- **`kind=value`はfieldの中の値**。`RCC_PLLMULL_3`は`PLLMULL`の値。`of_field`が親、`value`がその値
  （`mask >> lo`）。`kind=field`だけを数えればfieldの数になります
- **`bits`が空の`field`**はmaskが連続していないもの（少数）。maskを見てください
- **D-5（型のversion）は`index/register_layouts.layout`**。「I2Cは4型」のような分け方は、`type`ごとに
  `layout`でgroup byすれば出ます。keyはハッシュなので**意味は持たず、同じか違うかだけ**を言います。
  header側の定義が1つでも変われば変わる（版が上がると同じsiliconでも変わり得る）
- **RMとの突き合わせは綴りが一致したものだけ**。RMの`GPIOx_CFGLR`・`IDRy`の`x`/`y`は数字を落として
  比べます。一致してbit位置が同じ→`confirmed`、違う→`conflict`（`basis`に`!rm(...)(=hi:lo)`）、
  RMに同名が無い→`reference`。**`reference`は誤りではなく裏取り待ち**で、`value`行は照合対象外
  なので常に`reference`です
- `conflict`は本物の食い違いです（例: CH32V003の`GPIO_LCKR.LCKK`はEVT bit8 / RM bit16、
  `ADC_RDATAR.DATA`はEVT 32bit / RM 16bit）。どちらかに寄せていません
- **絶対アドレスの裏取り**: RM zh版の各章冒頭の表（`R32_PWR_CTLR | 0x40007000 | 説明 | 復位値`）
  8,369行のうち**5,110行がEVTのblock base＋offsetと一致、不一致4行**（`registers`のconflict 4＝
  H417のCAN2の`FMCFGR`/`FSCFGR`/`FAFIFOR`/`FWR`がRMでは+4。CAN1は一致）。残り2,937行は名前が
  headerの構造体に結べないもの（`BMC_*`・`ESIG_*`・`PFIC_*`・V20xの`CAN1_TTCNT`など、device header
  以外の型やheaderに無いregister）。RMが`R32_USBPD_STATUS`のように32bitの名で書くregisterは、
  EVTがunionで重ねた32bit側のメンバー（`USBPD_STATUS`@0x08）と照合する（8bitの`STATUS`@0x09ではない）

**持っていないもの**: RMのfield説明文（中国語。行が多いので入れていない。`extract_registers.py`で取れる）。
D-7（DMA channel→周辺）は`dma_requests.csv`。

### `dma_requests.csv`

**どの周辺の要求がどのDMA channelに繋がるか**（consumerのR-20 D-7）。EVT headerには無く、
reference manualのDMA章の「DMAx各通道外设映射表」だけが持つ情報です。zh版とen版を別々に読んで
(family, variant, dma, channel, request)で突き合わせ、両版一致で`confirmed`、片方だけなら`reference`。
650行のうち577がconfirmed、73のreferenceは全部CH32V407（RMがzh版しかない）。
**綴りは資料のまま**（`request`。zh版の綴りで、`TIM1_UP*`の`*`やX315の`_0`/`_1`も残す。en版の綴りが違えば`request_en`）。印の読み（`remap`）と語彙で揃えた`peripheral`は索引の[`index/dma.csv`](../index/README.ja.md)が持ちます。

| 列 | 意味 |
|---|---|
| `variant` | 同じRMの中でDMAの構成が違う組（CH32V20x/V30x）。EVTのmacro名（`CH32V20x_D6`など、`|`区切り）。それ以外は空 |
| `dma` / `channel` | `DMA1`/`DMA2`と1始まりのchannel番号。**H417は空**（下記） |
| `request_id` | **H417だけ**。DMAMUXの要求入力番号（1〜123。`CHANNELx_MUX`に書く値は番号−1）。channelは固定でなく、どのchannelにもこの要求を割り当てられる |
| `request` / `request_en` | 資料の綴り。`*`印（V205/V20x/V30x。`EXTEN_CTLR1`で経路を選ぶ要求。同じ要求がDMA1とDMA2の両方に出る）は zh版だけが付けることがあり、そのとき`request_en`に en版の綴りが入る。X315の`_0`/`_1`は`EXTEN_CTR`で選ぶ既定/remap側 |
| `note` | 脚注の印（V006の`（1）（2）`＝CH32M007とV006/V007でTIM3の割り当てが違う）、資料の誤植の注記（V407の`13C`、H417の`I3X_RX`は綴りを保ったまま「as printed」） |

**見方**:
- 「USART1_TXはどのchannelか」→ 索引`index/dma.csv`の`request=USART1_TX`（またはperipheral=USART1）で引く。この表で引くなら`request`に印が付くことに注意。1つの要求が複数channelに出ることがある（V205の`*`付き、X315の`_0`/`_1`）
- 1つのセルに複数の要求（`TIM1_CH4`と`TIM1_TRIG`）が書かれているものは行を分けてある。**同じchannelに複数の要求が来る＝同時には使えない**という資料の含意はそのまま
- CH32V20x/V30xは`variant`で絞ってください。V20x_D6は1 DMA・8ch、V20x_D8/D8Wは1 DMA・8ch、V30x_D8/D8Cは DMA1 7ch＋DMA2 11ch
- H417はDMAMUX方式で、この表は「要求の番号表」です。channelへの割り当ては実行時に`DMAMUX`へ書く

表の形が5通りある（1ページ格子／次ページに見出し無しで続く／channel 8以降が別の表／2 DMA＋`*`印＋セルの
ページ跨ぎ／DMAMUX番号表）のを1つの読み方で読んでいます。読み方の規則と資料側の癖は
`tools/build_dma_requests.py`の冒頭に書きました。

### `pin_functions.csv`は**pinout単位**で、型番の機能一覧ではありません

datasheetのpin表がそう書いています（`CH32V20x_30xDS0`は表の直前に断っています）:

> 注意，下表中的引脚功能描述针对的是**所有功能，不涉及具体型号产品**。不同型号之间外设资源有差异

同じpinoutを共有する型番は同じpad行を読むので、`pin_functions.csv`（と`index/pinout.csv`）は**そのsiliconが出せる機能の和**になります。CH32V303CBT6はUSARTを3つしか持ちませんが、pin表には`UART8_TX`まで並びます。**どの型番が実際に持つかは比較表**（`product_attributes.csv`）が型番単位で数えます。個別の例外は脚注が名指しします（注17「CH32V303CBT6和CH32V303RBT6芯片均不支持TIM8」）。

consumerが型番ごとの機能一覧を作るなら、**この2つを掛け合わせてください**。`tools/check_counts.py`が両者を突き合わせて数を出します:

```
pairs cross-checked 391  agree 352  more on the pin side (superset from a shared pinout) 30  fewer on the pin side 9
  - counted by the comparison table but on no pin at all: 0 pairs
```

`pin側が多い`が共有pinoutの分、`pin側が少ない`はその封装に出ていないinstance（`CMP2`・`LPTIM1`で、入力が内部だけの可能性がある）。**`pin に1つも出ない`が0であること**が、比較表が数える周辺は必ずpinから引けるという保証です。

### `remap_fields.csv` / `remap_routes.csv`

AFIO route selectorの定義と、値→経路の対応です。pin_functions.csvの`remap-N`は、remap_routes（selector×値→signal/pad）→remap_fields（どのregisterの何bitか）と辿って解決します。出所はcandidates/（EVTヘッダ+RM register表+RM remap格子+datasheet pin表の結合）ですが、**根拠ごとの一致記録がファイルに残っていないため全行reference**です。EVTとRMの突き合わせを記録付きで再実行して確定へ昇格するのが次の課題です。H41x/X315系はremapではなくAF番号方式なので対象外（pin_functionsの`af-N`が持つ）。

読み方に注意が要る列が3つあります。

**`bits`はbitごとにregister名を持ちます**——`PCFR1:2;PCFR2:19;PCFR2:20`のように、値のLSBから順に`<register>:<bit>`を`;`で並べます。ほとんどのselectorは1つのregisterに収まりますが、CH32L103 / CH32M103 / CH32V20x / CH32V30x / CH32V4x7では**selectorがPCFR1とPCFR2にまたがります**。PCFR1だけを書くとエラーにならずに別の経路が選ばれるので、上位半分を落とさないための修飾です。`register`列は同じことを`PCFR1|PCFR2`と要約します。

**`signal`は原典の表記のまま**で、同じ役割が資料により`USART1_TX` / `UART_TX` / `TX1` / `UTX`と書かれます。語彙で揃えた`peripheral`/`role`は索引の[`index/routes.csv`](../index/README.ja.md)が持ちます（規則が当たらない行はそちらで両方空）。

**`UART`と`USART`は同じものへ畳みます。** WCHは同じseriesの中でも呼び分けが揺れていて、CH32V307はpin表が`UART5_TX`なのにAFIOのfieldは`USART5_REMAP`、CH32M030はpin表が`UART_TX`でfieldは`UART1_REMAP`です。畳まないとsignalが自分のselectorを見つけられません（実際にCH32V303/V307/V317のUSART5〜8が丸ごと落ちました）。12 familyのEVTヘッダを確認して**UARTnとUSARTnのAFIO fieldを両方持つfamilyは無い**ので、同じsiliconで別のペリフェラルを指すことはありません。索引の`peripheral`列は正規化後の`USART5`になりますが、`remap_fields.csv`の`field`列と`selector`のid（付与識別子）は原典の綴り（`UART1_REMAP` / `afio-uart1-remap`）を保ちます。

**`value=0`の行は既定経路です**。datasheet pin表の`default`列を値0として展開したもので、`basis`が`candidates(datasheet-pin-table-default:en)`になります。remap後の経路と同じ表に並ぶので、既定位置を知るためにpin_functions.csvを引き直す必要はありません。

**`valid_values`は下限です**。3つの資料の和を採っています——RMのremap格子が挙げる値、datasheet pin表が実際に経路を持つと示した値、EVTヘッダが定数として列挙している値。格子は「どちらでもよい」桁を`x`で書くので過大に出ることがあり（CH32X035の`USART4_RM=1xx`が4通りに展開される）、逆にどの資料も触れていない値は落ちます。**列挙されていない値が使えないとは限りません**が、列挙されている値はいずれかの資料が実証しています。`remap_routes.csv`に出る経路はすべてここに含まれます。

`tools/check_tables.py`が表だけを読んで検査する内容: `bits`が`register:bit`形式であること・重複がないこと・`register`列と一致すること、`valid_values`が`bits`の幅に収まること、`reset_value`が`valid_values`に含まれること、**`remap_routes.value`がすべて`remap_fields.valid_values`に含まれること**。

### `clock_configs.csv` / `clock_prescalers.csv` / `clock_sources.csv` / `clock_symbols.csv` / `clock_init.csv` / `evt_variants.csv`

EVTが`system_ch32*.c`に用意しているクロック設定です。1関数=1設定で、本体はレジスタ書き込みの列そのものなので、そこから発振器・各クロックドメインの周波数・バス分周・PLL設定・flash latency・RCC外のレジスタを読み出しています（`tools/extract_clock_tree.py`→`tools/build_clock.py`）。**PDFもコンパイラも要らず、静的に読むだけ**です。

読み方に注意が要る列が4つあります。

**`domains`は`名前=Hz`を`;`で並べます**——`SYSCLK=400000000;CoreCLK[V5F]=400000000;CoreCLK[V3F]=100000000`。ほとんどのfamilyは`SYSCLK`だけですが、**CH32V407はSYSCLKとHCLKが別**、**CH32X315はSYSCLK/CoreCLK/HCLKの3段**、**CH32H417は双核なのでCoreCLKがコアごと**です。`SYSCLK = HCLK`という1段のモデルではこの3 familyを表せません。名前が周波数を言っていない設定（`SetSysClockToHSE`＝水晶に直結）は**空**にしてあります。水晶の周波数は基板の属性でchipの属性ではないためです。

**`condition`はコンパイル時分岐です**。CH32V307の144MHzは`#ifdef CH32V30x_D8`で`RCC_PLLMULL18`、`#else`で`RCC_PLLMULL18_EXTEN`を書きます。**1つの関数が2つの事実**なので、分岐ごとに行を分け、どちらかを`condition`が言います。

**`outside_rcc`はRCC以外に触るレジスタです**。CH32L103/V103/V205/V20x/V30xはHSIからPLLを回すとき`EXTEN`を触ります（`EXTEN->EXTEN_CTR |= EXTEN_PLL_HSI_PRE`）。**CH32V205だけはこのregisterを`CTLR0`と呼びます**。「RCCだけ見ればよい」というモデルでは組めません。

**`evt_copies`は「何個のコピーがこの設定を書いているか」です**。EVTは`system_ch32*.c`を例題ごとに配っていて、**コピーは同一ではありません**（CH32H417は390個中に12種類）。`162/168`なら主流、`4/168`なら特定の例題専用です。捨てずに全部載せて、判断はconsumerに委ねています。

`ppre1`に注意してください。CH32V20x/V30xはHSI由来のどの周波数でも`ppre1=2`で、**`PCLK1 = HCLK/2`**です。USART(BRR)・I2C(FREQ/CKCFGR)・SPI(BR)を`PCLK1 = F_CPU`前提で書くと、PLLを使った瞬間に壊れます。

`flash_latency`が空の行は**その設定がlatencyを書かない**ことを意味します。書くfamilyの範囲も違います: V003は0〜1、V006/V103/L103/X035は0〜2、M030は0〜3、V205は0〜4。

**`flash_sck_div`は待ちサイクルではなくフラッシュクロックの分周比です。** CH32X315とCH32H417のFLASH_ACTLRは`LATENCY[n:0]`を持たず、`SCK_CFG[1:0]`で**HCLKを何分周するか**を選びます。記号名が`FLASH_ACTLR_LATENCY_HCLK_DIV4`なので`flash_latency`に入れると「4待ち」と読まれてしまい、単位が違うので列を分けました（`check_tables.py`が両方を持つ行を弾きます）。**CH32X315はHCLK/1・/2・/4・/8、CH32H417はHCLK/2**です。240MHzへ上げるのに既定のままだと落ちるので、落としたままにはできない事実です。

この2 familyは**書き方も違います**——レジスタを直接触らず、ローカル変数へ写して直してから書き戻します（`FLASH_Temp = FLASH->ACTLR; FLASH_Temp &= ~FLASH_ACTLR_SCK_CFG; ...`）。`BLOCK->REGISTER op= value`しか見ていないと中身が丸ごと見えず、これが「X315はlatencyを書かない」という誤りの原因でした。

**この3表だけはseriesではなくfamilyで引きます。** クロックツリーはsiliconの性質で、EVTのcloneは1 silicon分だからです（`families.csv`がどのseriesを覆うかを持っています）。seriesで引くとCH32V20xの19設定がV203とV208へ複製されるうえ、2つのfamily dirが同じseriesに触れている場合（V203はCH32V20xとCH32V205の両方から作られたSKUがある）に**別のsiliconのツリーを拾います**。

`clock_sources.csv`はUSB・RTC・ADC・I2S・RNG・ETH等を「どのクロックから取れるか」で、`<fam>_rcc.h`の`RCC_*CLKSource_*`定数と、それがどのregister fieldへ行くか（`<fam>_rcc.c`の`RCC_*CLKConfig`）の組です。ここも`condition`が要ります——CH32V20xは`RCC_RTCCLKSource_*`の**値0x300が、D8/D8Wでは`HSE/512`、それ以外では`HSE/128`**です。同じ値が別の意味になるので、分岐を落とすとRTCが4倍ずれます。USBの`PLLCLK_Div5`もD8/D8W限定です。CH32X035は選択肢が1つも無く、USB PHYがクロック選択を必要としないことと整合します。

**`clock_symbols.csv`は`pll`と`outside_rcc`の記号を数値に落とします。** この2列だけは値ではなく**記号名**が入っています（`RCC_PLLMULL18`、`EXTEN_PLL_HSI_PRE`）。名前から値は導けません——CH32V307の`RCC_PLLMULL18`は`0x003C0000`、`RCC_PLLMULL18_EXTEN`は`0x00000000`で、**同じ「×18」が別の値**です（`RCC_PLLMULL15`は`0x00340000`、`_EXTEN`版は`0x00380000`で、ずれ方も一定ではありません）。1行が(family, symbol)で、`value`は**シフト済みの10進**（`clock_prescalers.value`と同じ規約）、`register`は書き込み先を`BLOCK->REGISTER`で、`address`はそのregisterの**絶対アドレス**です。

アドレスを載せているのは、レジスタ名から場所が決まらないからです。EVTは`#define EXTEN_BASE (HBPERIPH_BASE + 0x3800)`のように**base定数の連鎖**で書き、綴りもfamilyで違います（`HBPERIPH_BASE`と`AHBPERIPH_BASE`）。**CH32V205だけがEXTENのregisterを`CTLR0`と呼び、CH32X315はEXTENを`0x400220C0`に置きます**（他は`BASE+0x3800`）。`tools/extract_addresses.py`がbase連鎖とstructのメンバーオフセット（reserved配列も数える）を解いています。

**`evt_variants.csv`は型番→コンパイル時macroです。** `condition`列が`CH32V20x_D8W`や`CH32V30x_D8`といったmacroを参照しますが、どの型番がどれに該当するかはEVTのdevice headerの**コメントにしか書かれていません**。該当するfamilyは3つで、既定値（headerが最初から有効にしているもの）は`default`列が言います:

| family | macro | 該当型番 |
|---|---|---|
| CH32V20x | `CH32V20x_D6`（既定） | CH32V203 の F6/F8/G6/G8/K8/C6/C8（11型番） |
| CH32V20x | `CH32V20x_D8` | CH32V203RBT6 のみ |
| CH32V20x | `CH32V20x_D8W` | CH32V208 の4型番 |
| CH32V307 | `CH32V30x_D8` | CH32V303 の5型番 |
| CH32V307 | `CH32V30x_D8C`（既定） | CH32V305/V307/V317 の9型番 |
| CH32V006 | `CH32V002` / `CH32V004` / `CH32V005` / `CH32V006`（既定） / `CH32V007_M007` | 型番の先頭一致で26型番 |

**macroを設定しないプロジェクトは既定のvariantで黙って通ります。** CH32V203RBT6にD6のまま組めば、HSE_VALUEが24MHzのまま（正しくは32MHz）、周辺の集合も違う、という形で表に出ません。

**`clock_symbols.csv`の`role`列は、その記号が何なのかを言います。** 観測から決めています——`&= ~X`なら`mask`、`|= X`なら`value`、`while(REG & X)`なら`poll`。429行の内訳は value 222 / mask 173 / poll 34 です。

マスクが要るのは**setterが全部read-modify-writeだから**です。値だけでは書けません。ところが**ベンダのコード自身がフィールドをクリアせずにORしている**ことがあり（CH32V20xは`RCC->CFGR0 |= RCC_HPRE_DIV1`をリセット値に依存して書く）、ソースの観測だけではマスクが揃いません。足りない分はヘッダの形から認定しています——「名前が`_`境界で他の2つ以上の記号の接頭辞になっていて、値が連続した1本のビット列である」。これがちょうど`RCC_HPRE`（対`RCC_HPRE_DIV1..DIV512`）・`RCC_SW`（対`RCC_SW_HSI/HSE/PLL`）・`FLASH_ACTLR_LATENCY`に当たり、`RCC_HSEON`のような単一ビットには当たりません。レジスタの位置はヘッダのbannerコメント（`/*** Bit definition for RCC_CFGR0 register ***/`）から引きます——名前は`RCC_ADCPRE`がCFGR0のものだと言わないので。

出所は`basis`で分かれます: **`evt(device-header+system_ch32*.c)`は設定コードが実際に書いたもの（303行）、`evt(device-header)`はヘッダに定義があるだけ（126行）**です。

**`confidence=conflict`はヘッダが1行の中で自分と食い違っている記号です。** 5件あります。代表は`FLASH_ACTLR_LATENCY`で、CH32V003/V006/V103/X035が値`0x03`（2bit幅）に対しコメントは`LATENCY[2:0]`（3bit幅）と書きます。名前を信じるか数を信じるかで書けるマスクが変わり、狭い方ではlatency 4が書けません。`basis`に両方の読みを残しています（`+!evt(device-header-comment:FLASH_ACTLR_LATENCY[2:0])`）。**マスクの幅自体もfamilyで違います**: V003/V006/V103/L103/X035が`0x03`、V20x/V307/M030が`0x07`、V205が`0x0F`。

比較は位置ではなく**幅**でしています。コメントは*フィールド内*のbit番号を書く慣行なので、`RCC_SWS[1:0]`はマスク`0xC`（3:2に置いた2bit）と矛盾しません。位置で比べると全familyが矛盾判定になります。

**`clock_init.csv`は`SystemInit`の手順です。** ここだけ順序（`step`列）を持ちます。順序が方針ではなく**転記**だからです——`SystemInit`は分岐の無い一直線で、`RCC->CTLR |= 1`はSWをクリアする前に来なければ動かすクロックが無くなります。一方**クロック切替の順序（latencyを上げ下げする位置、enable→ready→切替→SWS待ち、タイムアウト方針）は入れていません**。あれは方針で、方針はdevice factではありません。

この表が必要なのは、`SystemInit`が**記号ではなくベタのhexで書かれている**からです（`RCC->CFGR0 &= 0xF8FF0000`）。記号ベースの抽出には何も見えません。`action`は`set`(`|=`)・`clear`(`&=`)・`write`(`=`)・`poll`(`while`)・`trim`の5種で、**`clear`の`value`は原典どおりのANDマスク**（残すビット。落とすビットではない）です。反転すると解釈になるので、そのまま載せています。

**HSIの工場トリム**も`action=trim`の行で入っています。3 familyが工場値を固定アドレスから読んで校正します。飛ばすとHSIが規格外のままです。

| family | 読む場所 | アドレス | マスク | 条件 | 書き込み先 | 出てくる関数 |
|---|---|---|---|---|---|---|
| CH32V003 | `CFG0_PLL_TRIM` | `0x1FFFF7D4` | `0x1F` | `!= 0xFF` | `RCC->CTLR` | `SetSysClockTo_48MHZ_HSI` |
| CH32L103 | `HSI_LP_TRIM_BASE` | `0x1FFFF72A` | `0x1F` | — | `RCC->CTLR` | `SetSysClockToHSI_LP` |
| CH32V205 | `HSI_LP_TRIM_BASE` | `0x1FFFF72A` | `0x1F` | — | `RCC->CTLR` | `SetSysClockToHSI_LP` |

**記号名がfamilyで違います**（`CFG0_PLL_TRIM`と`HSI_LP_TRIM_BASE`）。CH32V003は`SystemInit`でも`0x10`という既定値を無条件に書き、あとで工場値が`0xFF`でなければ上書きします——つまり**未書き込み品では既定値のまま**です。CH32L103とCH32V205は低消費HSIの設定関数の中だけで、常時ではありません。

出典は`evt(system_ch32*.c)`・`evt(rcc-header+rcc-driver)`・`evt(device-header+system_ch32*.c)`・`evt(device-header)`・`evt(system_ch32*.c+device-header)`・`evt(device-header-comment)`で単一資料のため**conflictを除いて全行reference**です。reference manualが同じfieldを記述しているので、そちらを second reading にするのが確定化の道筋です。

### `debug_data.csv`

**debug module の data0/data1 レジスタの hart 側アドレス**（consumer の R-27。SDI print＝DMDATA0/1 の
mailbox 経由の printf が書く番地）。1行1 family。**番地は die で違う**——V2 系（V003/V00x）は
`0xE00000F4`、V4 系（L103/M103・V20x・V30x・X035）は `0xE0000380`、V3 系の多く（M030・V205・V407・X315）
は `0xE0000340`、ただし V3A の V103 は `0xE0000380`。core 世代では決まらないので family 単位。

出所は3つで、揃ったものが `confirmed`:

| basis | 中身 |
|---|---|
| `evt(<debug.c>)` | 各 EVT の debug.c の `#define DEBUG_DATA0_ADDRESS ((volatile uint32_t*)0x…)`（SDI_Printf の実装）。family 内の全 debug.c で同じ値であることを見る（`+N more`） |
| `manual:qingke-vN(dataaddr=0x380)` | QingKe プロセッサマニュアル debug 章の hartinfo 表。**V2（`0x0f4`）と V4（`0x380`）は固定値**、V3 と V5 は `0xXXX`＝「以具体读出为准」（実装ごとに hartinfo を読め）なので `dataaddr=read hartinfo` と書き、根拠には数えない |
| `hartinfo:wch-linke(consumer 2026-08-26)` | consumer が WCH-LinkE で hartinfo.dataaddr を読んだ実測（`curated/debug-data-measured.json`。V003・V103・V203・X035・L103） |

CH32H417 は EVT に define が無く（SDI_Printf 例が無い）、V5/V3 のマニュアルは値を固定しないので、
行は残して番地は空・`missing`。埋めるには hartinfo の実測が要る。`dm_data1_addr` は常に `dm_data0_addr + 4`
（`check_tables` が見る）。生成は `tools/build_debug_data.py`。

### `debug_wiring.csv`

**debug配線（1線SWIO／2線SWDIO+SWCLK）のWCH-Link manual側の証拠**（consumerのR-29）。
1行1 series（26行——manualに載らないM103は行なし。M103のwire数はdatasheetの節見出しが持つ）。
出所は`WCH-LinkUserManual.PDF`（zh 2.8／en 2.7、WCH-commonにmirror）の2箇所で、zh/enが
一致した行がconfirmed:

- **配線表**（常用芯片型号／SWDIO／SWCLK）→ `swdio_pad`・`swclk_pad`。SWCLK欄が`-`の
  chip（V003・CH641）は`swclk_pad`空＝1線のみ
- **両対応の注記**（「…支持单线（SWDIO）和两线（SWDIO-SWCLK）调试接口」）→ `dual_support=yes`

抽出は新経路（`pipeline/extract/manual/extract_debug_wiring.py`。構造化bundle入力で、
zh版のページを跨ぐ配線表はL1結合層で結合してから読む）。chip群のtoken→seriesは
総当たりの辞書で、辞書に無いCH32系tokenが現れたら生成が落ちる。**manualの主張を
pin表が裏付けない箇所が2つ**（V002/V004——manualはV00x群を両対応と括るが、両者の
pin表にSWCLKが無くdatasheetの見出しも1-wire）——証拠はmanualの綴りのまま残し、
裁定は`index/debug_interfaces`側（見出しを採り、manualの異議をbasisに記録）。

### `option_bytes.csv`

**ユーザー選択字（option bytes）領域の書き込みレイアウト**（consumer依頼R-30——
構造化した`target option get/set`と工場値書き戻しには、各バイトの意味・補数
バイトの配置・書込単位が要る）。RMのoption bytes章「用户选择字信息结构」表から
family×バイトごとに1行。全11 RMが同じcaptionでこの表を持つ（2026-09-01実測）。
新経路の抽出（`pipeline/extract/rm/extract_option_bytes.py`・bundle入力・
ページ跨ぎ断片はL1で結合）。

- `address`／`offset`: バイトの絶対番地と、OB base（領域の最小番地）からの
  距離。baseは`register_blocks.csv`の`OB` blockと`check_tables`が突き合わせる
  ——RMの表とEVTヘッダという独立な2ソースの相互検査
- `byte`: 記載どおりのバイト名（RDPR／USER／Data0／WRPR0／Reserved…）
- `complement_address`: 補数バイト（`nRDPR`…）の位置。表が対にしていない
  バイト（Reservedの語）は空
- `write_unit`: 領域の書込方式。「用户选择字编程」手順が名指す制御bitで分類
  ——`half-word (OBPG)`（V003系）か`fast page, 32-bit buffer writes (FTPG)`
  （L103/M030系）。RMが「高バイトはFPECが自動で反码を計算する」と書いていれば
  `; complement auto-computed`を足す。ちょうど1方式に当たらなければ生成が落ちる

zh/enの両版が一致した行がconfirmed。CH32V407（RMがzh単独）はreference。

### `option_byte_fields.csv`

**option bytesのbit割当とRM記載の復位値**（構造表の直後にある無captionの
「名称/字节」表から）。記載されたfieldまたはbyte群ごとに1行: `byte`（RDPR／
USER／Data0-Data1／WRPR0-WRPR3）・`bits`・`field`・`default`、WRPR群の行には
`wrpr_bit_protects`——**1bitが保護する範囲**をWRPR群の説明文から（「N個扇区×
サイズ」・「4K字节」・DBMODE条件つき、の3形。どれにも当たらなければ生成が
落ちる）。復位値は**RMが述べる粒度のまま**残す——工場出荷の生バイト列への合成は導出なのでしない
（consumer側が新品実測との突き合わせに使う）。両版の比較は復位値セルの
**値トークンの列**で行う（周りの散文は言語で違い、文字層では句読点がセルに
漂着する）。識別子・値は空白とdashだけ畳んで資料どおり。**第三の証拠があるzh/en齟齬は
裁定済み**（2026-09-02）——X315のbitは`USBHSDLEN`（EVTの`ch32x3x5_flash.h`が
zhを支持）、FV2x/V3xのSRAM分割fieldは`RAM_CODE_MOD`（OBR読み出し側が支持。
en版は無名のまま）、X035の復位値は`xxxb`（`rule:bit-width`——[7:5]は3bit）——
いずれもconfirmedで、もう片方の版の異議はbasisに残る。証拠の無い齟齬は
conflictのまま（文書ごとに逆転するIWDG_SW/IWDGSWの綴り、X315のWRPR粒度）。

### `device_id_addresses.csv`

**32bit chip識別子（device_id）の読み出し番地をfamilyごとに**（consumer依頼
R-28——chip IDによるtarget自動判定）。一次資料はEVTの`DBGMCU_GetCHIPID()`——
`*_dbgmcu.c`の即値、またはdevice headerの`CHIPID_BASE`で解決する`CHIPID`
マクロ（L103/V205）。全12 familyに行がある——**第三者DBに無いfamilyも含む**
（V205/V407/X315は`0x1ffff704`、M030だけ独自の`0x1ffff384`）。`check_tables`が
`memory_map.csv`のCHIPID領域（ある家系）と、`device_ids.csv`全行の`id_addr`と
突き合わせる。

### `device_ids.csv`

**型番ごとの32bit device_id**（packageの違いはbit[19:16]に出る）。
**ch32-rs/ch32-data**（`data/chips/*.yaml`。cloneのcommitとfileをbasisに記録）
から取り込んだ値は`reference`——第三者の機械可読DBは一次資料ではない。
confirmedへ上がるのは実機読み（WCH-LinkE。basisは`device-id:wch-linke`——
`debug_data`の`hartinfo:wch-linke`と同じ流儀）と突き合わせた行だけ。
`id_source`は測定経路（`memory`＝番地読み／`attach`＝probe応答）で、取り込み
行は空。`dont_care_bits`は`[7:4]`（silicon revision。ch32-dataのbit割り文書と
probe-rsの照合maskが根拠）。目録に無いch32-dataの型番は**対応付けせずに見える
形で落とす**——末尾のグレード桁だけ違うニアミスが複数ある
（ch32-dataの`CH32V006F8P6` vs 目録の`CH32V006F8P7`等）。

### `link_firmware.csv`

WCHが配るデバッガ用ファームウェアの一覧。生成は`tools/build_link_firmware.py`で、
`WCH-LinkUtility.ZIP`（またはMounRiver Studio同梱の同じディレクトリ）を読む。
**`.bin`自体はこのrepositoryに置いていない**——再配布になるため、載せるのは
sha256・サイズ・取得元URLだけ。

**「あなたのLinkは古い」を言える**（2026-08-29、F-11 解決）。`wcfg_version`列はWCH独自の
番号（`wchlink.wcfg`の`CH32V307Ver=42`等）で、実機がUSBで申告する`major.minor`との
対応は **`wcfg = major*10 + minor`**（majorは観測した全個体で2）。復号した値が
`reported_version`列で、`tools/read_link_version.py`が実機から読んだ値が
`measured_version`列。**両者が食い違う行はconflictにする**規則で、いまは全一致
（実機を持っている2機種ぶんだけ埋まり、残り8行は空）。導出と実測の記録は
[docs/link-firmware-survey.ja.md](../docs/link-firmware-survey.ja.md)。
「手元のファイルが今配られているものと同じか」は**sha256**で判る。

MCUの割り当ては推測ではなく先頭命令から出している（`02`=8051の`LJMP`、
`6f`=RISC-Vの`jal`）。WindowsのZIPとLinux版MounRiver Studioの10本は
**sha256まで完全に一致する**ので、更新にWindowsは要らない。

### `systick.csv`

SysTickのregister配置。`core_riscv.h`の`SysTick_Type`から機械抽出する
（`tools/build_systick.py`）。**配置が4種類あり、CH32V103だけ`CMP`の位置が違う**
——他11 familyは`CMP@0x10`だが、CH32V103は`0x10`が`CMPHR`（上位32bit）で
比較値の下位は`0x0C`。`write_bits`列が「8bit単位でしか書けない」を言う。
CH32H417は`SysTick`が2本ある（双核なのでコアごと）。bit定義はreference manualに
しか無いので[register-map-survey](../docs/register-map-survey.ja.md#先出し1-systickr-24追補3のe-1)に置いた。

### `pin_alternate.csv`

**AF番号をどこに書くか。** `pin_functions.csv`の`route = af-N`（4,497行）のNの
書き込み先で、1行1（family, pad）。`tools/build_pin_alternate.py`。

CH32V205・CH32X315・CH32H417の3 familyは**AFIO remapを持たない世代**で、
経路をピンごとの4bitのAF番号で選びます。残る9 familyの`remap_fields.csv`と
対になる表です。

| 世代 | 経路の選び方 | 表 |
|---|---|---|
| remap（9 family） | `AFIO->PCFR1`の周辺機器ごとのフィールドに経路番号 | `remap_fields.csv` / `remap_routes.csv` |
| AF（3 family） | `AFIO->GPIOx_AFLR`/`AFHR`のピンごとの4bitにAF番号 | この表 ＋ `pin_functions.route = af-N` |

`pin 0-7`が`AFLR`、`pin 8-15`が`AFHR`で、下から4bitずつ。この規則は決め打ちでは
なくEVTの`GPIO_PinAFConfig()`の`~(0xF << (tmp << 2))`と`GPIO_PinSource >= 0x08`を
読んで確かめています。**番地はfamilyごとに違います**——CH32H417のAFIOは`PCFR1`の
直後にAF registerが並ぶので`GPIOA_AFLR`が`0x40010004`、CH32V205とCH32X315は
`ECR`/`EXTICR`/`CR`が前にあるので`0x40010020`から。同じ番地がfamilyによって
別のregisterを指します（CH32H417の`GPIOD_AFHR`とCH32V205の`GPIOA_AFLR`）。

`check_tables.py`が**`af-N`の行すべてについて書き込み先の存在**を見ます。
経路の情報が行き止まりになるのを防ぐためで、これが無いままV205のPWMが
consumer側で全滅していました（docs/worklist.ja.mdのF-10/F-12）。

### `memory_configs.csv`

**FLASH/SRAMの境界が用户选择字（option byte）で動くpart**の組合せ表。
1行1（型番, 符号）。`products.csv`の`flash_bytes`/`sram_bytes`はdatasheetの比較表が
載せる1組しか言わないので、振り直せること自体がそこから読めません（`tools/build_memory.py`）。

対象は**19 part / 3 family**——CH32V20xの`_D8`/`_D8W`（V203RB・V208）、
CH32V30xのC品（V303RC/VC・V307RC/VC/WC・V317VC/WC）、CH32V407/V467。
CH32X315は`Link.ld`のコメントが可変だと書いていますが**嘘**です
（V407からのコピー忘れ。headerに`RAM_CODE_MOD`が無く、480K=零等待192K＋
非零等待288Kで固定）。

**「出荷時の組」と言えるものはありません。** RM 32.4.6は`RAM_CODE_MOD`の復位値を`x`と
書き、「USERとRDPRTはシステムリセット後に用户选择字領域から読み込む」と注記します——
決めるのはoption byteで、RMはその出荷値を書きません。EVTも決めません。
例題ごとに違う組をlinkしています（符号表に載る組だけ数えて）:

```
CH32V20x   128K+64K ×14  144K+48K ×1
CH32V307   256K+64K ×17  192K+128K ×8  288K+32K ×2
CH32V407   576K+136K ×7  512K+200K ×1
```

そこで列は「既定」と名乗らず、**出所を名前にします**——`datasheet_value`は
**datasheetの比較表が載せる組**（`products.csv`の`sram_bytes`に当たる行）で、
それ以上の意味は持ちません。**可変partのlinker scriptを起こす側は、
どれか1組を決め打つのではなく自分のscriptに合わせてoption byteを書く**必要があります。

`condition`はその符号だけに付く制約（`110`は批号倒数第六位が0でない品のみ）。
書き込み先と読み出し先を別の列で持ちます——`option_byte_bits`が
`0x1FFFF800`のUSERバイトの中の位置（書く側）、`obr_bits`が`FLASH_OBR`の中の
位置（読む側）。

**全行`conflict`です。** 中文版RMは`RAM_CODE_MOD[2:0]`を`[9:7]`、English版は
`SRAM_CODE_MODE`を`[9:8]`と書き、EVT headerは後者と同じ2bitマスクを持ちます。
組合せが5通りある以上3bit要る（2bitでは`110`と`111`が同じ値になる）ので
中文版が正しく、`basis`に両方を残しています。

### `interrupts.csv`

割り込みベクタ表。1行1（family, 番号, condition）。**出所はreference manualではなく
EVTのdevice header**で、`IRQn_Type`列挙が番号・名前・1行説明を全部持っています。
コンパイルされる側の定義そのものなので、RMの表を読むより確かです。

`kind`が`exception`（RISC-Vのプロセッサ例外）と`irq`（PFICの周辺割り込み）を分けます。
**境目の番号はfamilyで違います**——ほとんどは16番からですが、CH32H41xは**32番**から
で、16〜28はIPC（コア間通信）とHSEMです（2コアなのでプロセッサ側の枠が広い）。
番号で決め打つと5本を取り違えるので、ヘッダー自身の横断幕
（`RISC-V Processor Exceptions Numbers` / `RISC-V specific Interrupt Numbers`）を
読んでいます。検査は「例外の番号は全部、割り込みの番号より小さい」という形です。

**同じ番号が別の周辺を指すことがあります。** CH32V20xの61番は`_D6`で`UART4`、
`_D8`/`_D8W`で`ETH`。`condition`列がその条件で、どの型番がそのmacroを立てるかは
`evt_variants.csv`が持ちます（`clock_configs.condition`と同じ辿り方）。

### `memory_map.csv`

アドレス空間の地図。1行1（family, kind, region）。**DS 1.2章の図ではなくEVTの
device headerの`*_BASE`定数から**取ります。相対の連鎖
（`EXTEN_BASE = HBPERIPH_BASE + 0x3800`）の解決は`tools/extract_addresses.py`が
持っています。

`kind`は4種類:

```
memory       FLASH・SRAM・OB（用户选择字）
bus          PERIPH_BASE / APB1PERIPH_BASE / AHBPERIPH_BASE ── 束ねる側
peripheral   TIM2_BASE・GPIOA_BASE … 個々の周辺
link-origin  EVTのlinker scriptが実際に使う先頭番地
```

**FLASHの番地は2つあります。** ヘッダーの`FLASH_BASE`はCH32V307で`0x08000000`、
EVTのlinker scriptは`ORIGIN = 0x00000000`を使います。どちらも実在の窓口で、
**linker scriptを起こす側が要るのは後者**なので両方を別の行で持ちます。
IAPの例題はbootloaderのぶんだけずらしたORIGINを書くので、`link-origin`は
**一番多い値**（＝領域の先頭）を採っています。

`FLASH_R`はFLASHの制御レジスタ（`0x40022000`）で記憶域ではないため`peripheral`です。

### `features.csv`

そのdatasheetが覆うシリーズが持つ周辺の一覧。1行1（series群, 節番号）。

**比較表からは作れません。** 比較表は「シリーズ内で差がある列」しか持たないので、
シリーズ共通の周辺は列ごと存在しません——CH32V307の属性は6種しかなく、USBHSも
Ethernetも行がありません（実際には両方あります）。**「属性が無い＝機能が無い」は
誤り**です。機能説明の章は別物で、その製品が持つ周辺を節見出しとして並べます。

**章番号は決め打ちできません。** CH32L103は`1.4`、CH32V103は`1.5`、CH32V20x/V30xは
`2.5`です。題（`Functional Description` / `功能概述`）で章を探します。

**節番号は言語に依らない**ので中英の対応が推測なしで取れます……が、**保証では
ありません**。CH32V208は23節中18節が対応する一方、英語版が通信系を`2.5.15.1〜6`と
入れ子にし、中文版が同じものを`2.5.19〜`と平らに振るため、残りが噛み合いません
（`reference` 11行）。**その節が片方の版に無いのか、番号の振り方が違うだけなのかは
この表からは決まりません**——題を突き合わせないと分かれないので、生成時は断定せず
一致数・片方のみの数を出します。

**granularityは`series`です。** 1つのfamilyがdatasheetを複数持つことがあり
（CH32V006はV002/V004/V006/V007の4冊）、**節番号は1冊の中でしか一意ではない**ため、
familyを主キーにすると別々の冊子の`1.4.17`が衝突します。

書き込み方式（worklistのA8）もここに出ます——`1-wire Serial Debug Interface (SDI)`
（CH32V002/V003/V004/V006/V007）と`2-wire SDI Serial Debug Interface`
（CH32L103・V103・V203・V30x・X035）が節見出しとして立っています。

### `eval_boards.csv`

評価ボードの資料と回路図。**WCHの配布物ではなくEVT同梱**なので`documents.csv`
（ダウンロードURL付きの文書カタログ）には入りません。`kind`で5種類を分けます:

```
board          型番ごとの板（SCHPCB/<型番>-R<版>/）        78
board-variant  用途違いの派生板（-UHSIF- / -USB）            3
board-manual:en / :zh   family単位の説明書              12 / 12
schematic-pdf  family単位の回路図PDF                      12
```

**`board`が一番効きます**——「自分の型番に評価ボードはあるか、版はどれか」に答えます。

**板の名前は型番と別の綴りで、80枚のうち27枚が素の一致では外れます**（温度グレードの
桁落ち`CH32V203CCT`、CH32F系との共用`CH32F&V208C`、区切りが`_`、`x`のワイルドカード
`CH32V4x7RET`、派生板`-UHSIF-`）。`listed_as`と同型ですが、板は**package単位で作られる**
ので複数の型番に当たるのが正常で、末尾の補完も3文字まで要ります（`CH32V208C`→`CBU6`）。
比較表用の`resolve_full_names`（2文字まで・1つに寄せたい）とは要件が違うので別規則です。

決められない3枚は`parts`が空です——`CH32V006K8U6`・`CH32V203K6T6`はcatalogueに無い型番、
`CH32X035USBPD_CH211`はcompanion chip込みのリファレンス板。近い型番に寄せると嘘になります。

`path`はmirrorの中での位置です。**CJK検査から除外しています**——
`EVT/PUB/CH32V30x评估板说明书.pdf`は中文名で実在するファイルで、翻訳したら指す先が
なくなります。「表示する値」ではなく識別子です。

### `errata.csv`

1行1エラッタ（ロット依存の挙動・ハードウェア注意事項）。ソースは`curated/errata.csv`（手編集）で、`condition`列がどのロット/型番に該当するかを持ちます。**両言語datasheetの記載ページ（source_zh/source_en）が記録済みの行はconfirmed**、片方のみはreferenceです。

エラッタは今後のdatasheet改版で増えうるため、`tools/scan_errata.py`が全datasheetを走査して既知（curated/errata.csvの`match`列の正規表現で識別）と照合し、未知の記述があれば`NEW`として報告します（終了コード1）。NEWが出たらcurated/errata.csvに行を追加し、再実行でNEW: 0を確認します。

### `operating_conditions.csv`

**電気的特性の章を series ごとに**——クロック・電源電圧・発振器・ADC・Flash・I/O レベル・
リセットのタイミング。生成は `pipeline/extract/datasheet/build_operating_conditions.py`
（新経路——凍結した抽出ロジックをbundle入力で走らせた基礎行＋消費電流・ウェイクアップ
時間の行。`tools/build_operating.py` は凍結された参照実装として残る）。

**採る行を記号の一覧では決めません。** 記号は頭字で物理量を名乗る（`V_*` は電圧、`I_*` は電流、
`t_*` は時間）ので、「その量に単位が合っているか」で採ります（`UNIT_FOR`）。資料の記法は決まって
いるので、一覧を持つより新しい family に強くなります。`T_S_*`（温度ではなく ADC のサンプリング
時間）・`t_RET`（年）・`N_END`（回数）は一般の規則より先に置いてあります。

値は数とは限りません。I/O のしきい値は電源に対する式で書かれ（`0.29*VDD-0.07`・
`0.41*(VDD-1.8)+1.3`）、上限が別の記号のこともあります（`F_HCLK`・`VREF+`）。

**取れていないもの**（理由は tool の docstring に）:

- **条件つきの消費電流**——`I_DD` は動作条件（`F_HCLK = 48MHz`・`开启`）が min の欄に
  流れ込む表で書かれていて、値として読めません。表の形の問題で、記号の問題ではありません
- **添字が文字層で `*` に化けた式**（`0.45*V+*0.41`。`0.45*V_DD+0.41` のはず）。兄弟の行を
  見れば人には分かりますが推測なので、埋めずに落とします
- **2つの記号が1行に畳まれた行**（`t_/t_r(SCK)_f(SCK)`）。値をどちらのものとも決められません

シリーズごとのクロックと動作電圧です。

- **`F_MAIN`**: datasheet 1ページ目の特徴リストが謳う**系統主頻**。製品として語られる周波数がこれです
- `F_HCLK`/`F_PCLK*`/`F_CORE*`: 電気的特性章「一般動作条件」表の**上限値**。F_MAINとは別の事実で、値も食い違います（CH32V003は本文48MHz・電気的特性の上限50MHz）。README の Clock 列は F_MAIN を優先し、無いシリーズ（CH32X035・CH32H41x）だけ F_HCLK / F_CORE に落とします
- `V_DD`: 動作電圧。ADC使用時・USB使用時などの条件行があります
- **`F_USBCLK` / `F_HCLK(USB)`**（2026-08-22追加）: USBのクロック要求。表ではなく本文にあるので散文から取ります。
  **48MHzは全familyの話ではありません**——USBHS/USBSSを持つCH32V407/V467とCH32X305/X315は専用PLL
  （`USBHS_PLL` 320/480MHz、`USBSS_PLL` 125/357/625MHz）を持ち、48MHzのUSBCLKを使いません。
  この2 familyには行が出ません。`F_HCLK(USB)`は**USB使用時に許されるCPU周波数の列挙**で、
  資料が直接書いています（V103は48/72、L103は48/72/96、V20x・V30xは48/96/144）。
  **離散集合はmin/maxで表せない**ので、許容値1つにつき1行（`typ`に値）です
- **`typ`列**（2026-08-21追加）: 発振器は「**公称値＋確度**」で規定されていて上下限を持ちません。`F_HSI`のばらつきは`ACC_HSI`の±%側にあり、周波数そのものは`typ`にしか出ません。この列が無いあいだ`F_HSI`はmin/maxが空の行で、**PLL入力が決まらないのでSYSCLKが計算できない**状態でした。中英どちらか一方だけが典型値の列を持つ表があるので、両方が値を持つときだけ突き合わせ、英語版が空なら中国語版で埋めます（数値なので言語に依りません）

  **HSIは8MHzではありません。familyで5通りあります。**

  | HSI公称値 | family |
  |---|---|
  | **8 MHz** | CH32L103・M103、V103、V203・V205・V208、V303〜V317 |
  | **20 MHz** | CH32V407・V467、X305・X315 |
  | **24 MHz** | CH32V002〜V007、M007、V003 |
  | **25 MHz** | CH32H415・H416・H417 |
  | **48 MHz** | CH32X033・X035 |

  低消費モードのHSIも別行です（CH32L103/M103とV203/V205は**1MHz**、CH32V00xは`HSI_LP=1`で30〜58kHz）。`F_LSI`もmin/typ/maxが揃い、**CH32V203は`applied for V203RBT6`だけ25/32/45kHz**で他の型番（25/39/60kHz）と違います——`evt_variants.csv`が`CH32V20x_D8`に割り当てる唯一の型番と一致します
- **発振器**（2026-08-21追加）: `F_HSI`/`F_LSI`と`ACC_HSI`/`ACC_LSI`（**確度**。`condition`列が温度範囲を持ち、範囲ごとに行が分かれます）、`F_HSE_ext`/`F_LSE_ext`（**外部クロックの許容範囲**。例: CH32L103は3〜25MHz、CH32M030は4〜25MHz、CH32V00xは3〜32MHz、CH32H41xは5〜32MHz）、`F_OSC_IN`/`F_XI`（水晶）、`DuCy_*`（デューティ比）
- **PLL**（同）: `F_PLL_IN`/`F_PLL_OUT`/`F_VCO`の上下限。例: CH32L103は入力3〜25MHz・出力18〜96MHz、CH32H41xは出力100〜600MHz
- **`f_ADC`**（同）: ADCのクロック上限。**familyで大きく違い、しかも電源電圧に依存します。** 記号だけ小文字始まりなのは原典の表記どおりです

  | family | ADCクロック上限 |
  |---|---|
  | CH32V003 | **6 / 12 / 24 MHz**（V_DD 2.8〜/3.2〜/4.5〜5.5V） |
  | CH32X033・X035 | **6 / 8 MHz**（V_DD < 3.2V / ≥ 3.2V） |
  | CH32V103・V203・V208・V303〜V317 | 14 MHz |
  | CH32M030 | 18 MHz |
  | CH32V407・V467 | 30 MHz |
  | CH32L103・M103・M007・V002・V004〜V007 | 48 MHz |
  | CH32V205 | 64 MHz（中英で食い違い。zh版は96 MHz → conflict） |
  | CH32H41x・X305・X315 | 80 MHz |

  `SYSCLK`を上げたときADCの分周を選び直す必要があり、その基準がこれです。**X035は6〜8MHzで、他familyより1桁近く厳しい**点に注意してください

上限が別の記号で書かれる行があります——`F_PCLK1`の`max`が`F_HCLK`のように。数値ではありませんが「PCLK1はHCLKを超えない」という事実そのものなので採っています。

表示テキストは英語版、最小/典型/最大/単位は両言語照合で一致すればconfirmedです。シリーズ列はdatasheet→products結合で展開しています（`;`区切り）。

発振器やADCの表は本体と別ページにあり（HSI/LSI/外部高速/外部低速/水晶/ADCで6種）、抽出器は**対象表を1つ見つけて打ち切らず全ページを走ります**。さらに**表はページを跨ぎ、続きページはヘッダ行を持ちません**（CH32V003のADCクロック上限の行はキャプションの次ページにしかない）。列数が同じなら直前の列並びを引き継いで読みます。この副作用で同じページにある他の`F_*`（`F_prog`＝flash書き込みクロック、`F_max(IO)out`＝IOの最大出力周波数）も入りますが、いずれも実在の周波数上限です。表の継承（記号セルが空の続き行）は多条件行には正しいものの、別パラメータが続くと記号を取り違えるので、**記号と単位と値の噛み合い**で弾いています（`F_*`にデューティ比の`%`が付く行など）。弾いた行は実行時に一覧で出ます。

電気特性章の残り（絶対最大定格・消費電流・flash耐久・ウェイクアップ時間）は未収集です（docs/extraction-survey.ja.md参照）。

### `evt_examples.csv`

EVTに同梱される例題の一覧です。生成は`tools/build_evt_examples.py`。EVTの目録（`EVT/<name>_List_EN.txt`と中国語版。中国語版はGBK）を索引の権威とし、**展開済みEVTツリーに実在するか**を突き合わせます。目録2版＋実体の3根拠のうち2つ以上でconfirmed。

referenceは目録と実体の食い違いで、文書側の事実です（目録が触れていないグループ、実体に無い例題名、目録内の綴りゆれ）。目録に無いグループは生成時にstderrへ報告します（現在: CH32V407のUSBHS、CH32X035のSYSTICK、CH32X315のUSBHS/USBSS）。説明は英語版のみを採用し、中国語版にしか説明が無い行は空にします。

## 確定の基準は「根拠の総合判断」

各CSVには名前も値もすべて `#` の区切り列があり、**そこから右はデータ本体ではなくメタデータ**（confidence/basis）です。全行のそのセルに`#`が入るので、ファイルのどこを見ていても「ここまでがデータ」の境界が分かります。読むときは`#`以降の列を落とせば素のデータ表になります。別ファイルに分けないのは、データとメタが構造的にずれないようにするためです。

| `*_confidence` | 判定 |
|---|---|
| `confirmed` | 独立した根拠が2つ以上一致、**または人が内容を確認して根拠を記録した** |
| `reference` | 根拠が1つだけで裏取りも矛盾もない。参考値 |
| `conflict` | 根拠同士が矛盾。**人の判断が要る** |
| `missing` | どの根拠にも記載がない |
| `partial` / `varies-by-package` | （series.csvのみ）配下の確度不揃い / package依存 |

**確定は自動化に限りません。** 使い捨てスクリプトで該当箇所を提示させ、人が両言語を突き合わせて確認できたら確定とし、根拠を`curated/`に記録します。core・ISAはこの方式です（`curated/series-facts.json`、2026-08-18確認）。

## 根拠の種類（basis表記）

| basis | 中身 | 扱い |
|---|---|---|
| `products:zh/en`・`ordering:zh/en` | 比較表・ordering表。zhが原典、enは翻訳 | 通常の根拠 |
| `pin-table` | pin定義表のlead数・GPIO数（candidates/から） | **soft**: 一致すれば確定を押し上げ、不一致は`?pin-table`と記録するだけ（表抽出の行落ちがありうるため） |
| `package-pdf:zh/en` | PACKAGE.PDF（封装寸法図面）目次のbody size・pitch | 通常の根拠。`QFN48X7_A`のような変種suffixは基本名で引く |
| `rule:pn-letter` | 型番末尾2文字目=package種別（T=LQFP等、84+8件無例外） | 照合。矛盾はconflict（`!`表記） |
| `rule:pn-temp-grade` | 型番末尾数字=温度グレード（6=-40〜85℃、7=-40〜105℃。記載のある32件無例外） | temperatureの根拠・照合。比較表が最大値だけ載せる場合は`products:zh(max)`として照合に回る。末尾1・3は対象外 |
| `rule:package-name` | package名の数字=lead数 | pin_countの根拠・照合 |
| `rule:part-number-structure` | seriesは型番構造から決まる | seriesの根拠 |
| `manual:…` | 人が確認して記録した根拠（curated/） | 確定として扱う |

**採用しなかった規則**: 型番の容量コード（8=64K等）。V30x/H41x系は比較表が最大構成を載せるため92件中24件で不一致になり、規則として成立しません。

## 吸収している表記差

単位語（`8-channel`↔`8路`）、全角記号、温度→数値2つ、容量→バイト数（脚注`(2)`除去含む）、packageセルへの寸法同居（`LQFP64M(10*10)`）、ワイルドカード列（`C6x6`）、略記型番の展開。**吸収しないと本物の差が埋もれます。**

## 既知の要確認事項

- **CH32V004F6U1のpackage**: zh `QFN20L` / en `QFN20`のconflictだったが、en版datasheetの改版で`QFN20L`に修正され、再生成で両言語4根拠一致のconfirmedへ自己解消（2026-08-19確認）
- **CH32V203CCT6**: V205DS0掲載の256K品。series=V203に数えているが設計はV205（青稞V3B）系の可能性。内核の個別記述未確認
- **CH32H415/H416のcore**: H417の記述（V5F+V3F双核）からの推定でreference

## 並び順と列順

再生成や途中挿入でdiffが局所に収まるよう、規則を固定しています。

- **行順**: 各表とも行の識別子の単純昇順。families=`family`、series=`series`、products=`(part_number, family, datasheet)`。productsのpart_numberだけでは一意保証がない（同じ型番が複数datasheetに載りうる）ため、識別子の組で並べます
- **列順**: 左から重要な値（識別子 → スペック → package詳細 → 出典）。次に区切りの `#` 列（全行`#`）、その右に`*_confidence`ブロック、`*_basis`ブロックを同じ順で並べます
- **pins系**: 行の識別子は（part_number, pin, pad）/（part_number, pad, signal, route）で、その昇順。出典の`table`・`datasheet`は確認用データとして`#`の右（メタ側）にあります

## 画像（現在は未使用）

生成READMEは画像を参照していません。データシートから図を切り出す仕組みは
用意しましたが（`tools/extract_images.py` / `tools/check_images.py`）、切り出し
品質の調整が済んでいないため、生成物はミラーに置いていません。READMEはピン
配置図の代わりに、パッケージ→型番→データシートの対応表を出します。

切り出しで分かったこと（再開するときの前提）:

- 図の見出しはデータシートごとに置き方も表記も違う。上・下・内側・1行に横並びの4通り、表記は完全型番・伏字（`CH32V103Cx`）・温度グレード省略（`CH32V007K8U`）・スラッシュ連結（`CH32V303RxT6/CH32V303RCT7`）の4通り
- 90度回転した文字はPDF上の座標が実際の描画とずれるため、座標計算だけでは範囲が決まらない。描いた画像の縁を見て広げ直す必要がある
- 同じピン配置でも型番ごとに図が別々にあるため、ファイル名の代表型番と図中の型番が食い違いうる（82枚中6枚）
- CH32V407DS0のようにピン番号がフッタ罫線に重なる版がある

シリーズ構成図（`system_*.png`）は原典のデータシートには無く、WCHの製品ページ由来です。手作りが27シリーズ中10枚あり、17シリーズ分が欠けています。`tools/build_system_figures.py` でtables/から同等の情報をSVGとして生成できますが、見た目が別物になるため採用は保留しています。

## 生成

**正面玄関は `uv run pipeline/publish/regenerate.py --full`**——以下の全部を
依存順に構造化bundle入力で回し、検査まで進む（1時間強。`--full`なしは新経路
だけの速い再生成）。下の一覧は1表ずつ回すときのもの。PDFを読むtoolは
`pipeline/extract/run_patched.py`経由で回す（入力層だけをbundleへ差し替える。
toolのコードは不変）——素の`tools/<name>.py`で回すとPDF直読みになり、切替後は
実行経路の外。出力先は各ツールが `tools/paths.py` で決めます（`--out <dir>` は
試験用の上書き）。上から順に。

```sh
uv run pipeline/extract/run_patched.py build_all --jobs 1  # .cache/candidates/（型番ごとの抽出候補。直列——patchはworker子プロセスに効かない）
uv run pipeline/extract/run_patched.py build_tables                    # catalog: families/series/products/packages/cores/documents  evidence: product_attributes/errata
uv run pipeline/extract/run_patched.py build_pins                      # pins/pin_functions（数分かかる）
uv run pipeline/extract/run_patched.py build_remap                     # remap_fields/remap_routes（candidates から）
uv run pipeline/extract/datasheet/build_operating_conditions.py  # operating_conditions（新経路・bundle入力。凍結ロジックの基礎行＋A11の行）
uv run tools/build_evt_examples.py              # evt_examples（EVTツリーと目録から）
uv run tools/build_clock.py                     # clock_configs/clock_prescalers/clock_sources/clock_symbols/clock_init（EVTから）
uv run tools/build_systick.py                   # systick（EVTのcore_riscv.hから）
uv run tools/build_pin_alternate.py             # pin_alternate（EVTのAFIO構造体とGPIOドライバから）
uv run pipeline/extract/run_patched.py build_memory                    # memory_configs（RMとEVTのLink.ldから・数分かかる）
uv run tools/build_interrupts.py                # interrupts（EVTのIRQn_Type列挙から）
uv run tools/build_memory_map.py                # memory_map（EVTの*_BASEとLink.ldのORIGINから）
uv run pipeline/extract/run_patched.py build_features                  # features（datasheetの機能説明章から・数分かかる）
uv run pipeline/extract/run_patched.py build_timers                    # timers（RMのTIMx_CNT見出しから・数分かかる）
uv run pipeline/extract/run_patched.py build_flash_geometry            # flash_geometry（EVTのflash driver＋RMの闪存章）
uv run pipeline/extract/run_patched.py build_opa_cmp_registers         # opa_cmp_registers（EVTヘッダ＋RMレジスタ表。RM全読みで長い）
uv run pipeline/extract/run_patched.py build_clock_enables             # clock_enables（EVTのrcc.h＋RMレジスタ表。RM全読みで長い）
uv run pipeline/extract/run_patched.py build_adc_internal              # adc_internal（datasheet両言語の散文と電気的特性表）
uv run pipeline/extract/run_patched.py build_usbpd_plumbing            # usbpd_plumbing（clock_enablesの後。EVTヘッダ＋RM）
uv run pipeline/extract/run_patched.py build_registers  # register_blocks/registers/register_fields ＋ index/register_layouts（EVTヘッダ＋RM全読み。bundleで約19分。cacheは使わない——staleな--rm-cacheが正本を改版前の読みへ戻した実績あり）
uv run pipeline/extract/run_patched.py build_dma_requests              # dma_requests（RM zh/en のDMA章の格子。全ページ走査で15分前後）
uv run tools/build_eval_boards.py               # eval_boards（EVTのPUB/から）
uv run tools/build_feature_tags.py              # index/features（features + 比較表から。PDF不要）
uv run tools/build_capabilities.py              # index/capabilities（product_attributes から。PDF不要。manifest が入るので build_index より前）
uv run tools/build_conflicts.py                 # index/conflicts（catalog/・evidence/ の conflict を全部。PDF不要。同じく build_index より前）
uv run tools/build_sources.py                   # catalog/sources（読んだmirrorの版。**生成の一式の中で回す**）
uv run tools/build_evt_variants.py              # evt_variants（EVTのdevice headerから）
uv run tools/build_link_firmware.py             # link_firmware（WCHの配布物から）
uv run pipeline/extract/run_patched.py build_debug_data                # debug_data（EVTのdebug.cのdefine＋QingKeマニュアルのhartinfo表＋実測）
uv run pipeline/extract/manual/extract_debug_wiring.py  # debug_wiring（WCH-Link manualの配線表＋両対応注記。新経路＝構造化bundle入力）
uv run pipeline/extract/rm/extract_option_bytes.py  # option_bytes + option_byte_fields（RMのoption bytes章。新経路＝構造化bundle入力）
uv run tools/build_device_ids.py                # device_id_addresses + device_ids（EVTのDBGMCU_GetCHIPID＋ch32-data取込）
uv run tools/build_index.py                     # **索引**: index/parts, pinout, routes, registers, register_map, dma, timers ＋manifest（秒）
uv run tools/build_readme.py                    # generated/readme/*.md（各 family の README）
uv run pipeline/extract/images/run_extract_images.py  # 各repoのimage/（凍結toolを原本hashゲート経由で。数分かかる）
uv run tools/check_images.py [--missing|--prune] # 画像の必要一覧と検査
uv run tools/check_tables.py                    # 全テーブルの参照結合・索引⊆証拠・manifest
uv run tools/check_counts.py                    # 比較表の周辺数 vs pinのinstance数
uv run tools/check_docs.py                      # 文書が書いている行数・穴の状態 vs 実際の表
node tools/check_viewer.js                      # pins.html の表示（script を DOM 無しで評価）
uv run pipeline/extract/run_scan_errata.py                     # エラッタ増分チェック（NEWで終了コード1）
uv run tools/build_tables.py --family CH32V006  # 1familyだけ
```
