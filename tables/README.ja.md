# 正規化テーブル

`tools/build_tables.py` が生成します。用語（ファミリー/シリーズ/確度…）の定義は [docs/glossary.ja.md](../docs/glossary.ja.md) にあります。**上から下に降りる階層**で、すべての値が「何を根拠にしているか」（`*_basis`列）を持ちます。

```
families.csv        12行   ファミリー一覧（mirror repository = 文書の単位）
  └ series.csv        27行   シリーズ（die）。core・ISA・共通スペック
      └ products.csv    103行   注文型番
          └ pins.csv          注文型番ごとのlead↔pad対応（キー: part_number）
          └ pin_functions.csv 注文型番ごとのpad→signal/route（キー: part_number）

マスタ表（各表から名前で参照される）
  packages.csv    25行  package。寸法・pitch・lead数
  cores.csv       13行  QingKe core。ISAとcore manualへの参照
  documents.csv   76行  文書カタログ。**両言語のページURL・DL URL・mirror URL**

付属表
  product_attributes.csv  995行  比較表の全属性（縦持ち。列に昇格していない残り全部）
  remap_fields.csv        284行  route selector定義（series×field: register/bit/reset/valid値）
  remap_routes.csv       4643行  selector値→(signal, pad)。pin_functionsのremap-Nを解決する
  errata.csv               21行  ロット依存の挙動・ハードウェア注意事項（curated/errata.csvから）
  operating_conditions.csv 283行  クロック上限（F_*）・動作電圧（V_DD）・発振器（HSI/LSI/HSE/LSE）・PLL入出力・ADCクロック上限
  evt_examples.csv       1593行  EVT同梱の例題一覧（周辺グループ→例題→説明）
  clock_configs.csv       152行  EVTが用意しているクロック設定（発振器・各ドメイン周波数・分周・PLL・latency）
  clock_prescalers.csv    263行  AHB/APB/ADC分周器の符号化（分周比→field値）
  clock_sources.csv       116行  USB/RTC/ADC/I2S等をどのクロックから取れるか（選択肢→register field）
  clock_symbols.csv       433行  設定に出てくる記号の数値・書き込み先register・絶対アドレス・役割
  clock_init.csv          101行  SystemInitの手順（ベタhexなので記号では見えない）＋HSI工場トリム
  evt_variants.csv         56行  型番→EVTのコンパイル時variant macro（CH32V20x_D8W等）
  systick.csv              53行  SysTickのregister配置（family×block。CH32V103だけ形が違う）
  link_firmware.csv        10行  WCH-Link系デバッガのファームウェア一覧（sha256・取得元）
```

結合キーの対応（`tools/check_tables.py` が全参照の結合可能性を機械検査します）:

```
series.family / products.family / packages.families   → families.family
products.series                                        → series.series
products.package                                       → packages.package
series.core / families.cores                           → cores.core
pins.part_number / pin_functions.part_number           → products.part_number
product_attributes.part_number                          → products.part_number
remap_fields.series                                     → series.series
remap_routes.(series, selector)                         → remap_fields
clock_configs.family / clock_prescalers.family / clock_sources.family → families.family
clock_symbols.family / clock_init.family / evt_variants.family → families.family
clock_configs.(family, hpre|ppre1|ppre2)                → clock_prescalers.(family, field, divider)
clock_configs.(family, pll|outside_rccの各記号)          → clock_symbols.(family, symbol)
clock_configs.condition / clock_sources.condition の macro → evt_variants.(family, macro)
evt_variants.part_number                                → products.part_number
errata.series / operating_conditions.series             → series.series
evt_examples.family                                     → families.family
*.datasheet(s) / families.reference_manuals・evt / cores.manual → documents.document
```

pins系は`tools/build_pins.py`、remap系は`tools/build_remap.py`、clock系は`tools/build_clock.py`、operating_conditions.csvは`tools/build_operating.py`、evt_variants.csvは`tools/build_evt_variants.py`、それ以外は`tools/build_tables.py`が生成します。

## 各ファイル

### `families.csv` — 最上位

1行1ファミリー。どのシリーズを含み、どのdatasheet・reference manual・EVTが該当するか。文書の対応は日次同期している`manifests/documents.json`から取ります。全体像はまずここを見ます。

### `series.csv`

1行1シリーズ（CH32V006, CH32V203, …）。core・ISAと、配下の全packageが共有する値だけを持ちます。packageで変わる値は`varies-by-package`として空になり、products.csvへ降ります。**シリーズとdatasheetは1対1ではありません**（CH32V203CCT6はCH32V205DS0に掲載）。

### `products.csv`

1行1注文型番。flash・GPIO数・温度など製品固有の値だけを持ち、**寸法系はpackage名でpackages.csvを参照**します。`listed_as`は比較表での略記（`CH32V208CB`→`CH32V208CBU6`、ワイルドカード`C6x6`→C6T6/C6U6）。

### `packages.csv`

1行1package名の**マスタ表**。body size・pin pitch・lead数はpackageの属性なのでここに正規化し、productsには持たせません。根拠は全productのordering表記載の集約＋PACKAGE.PDF（封装寸法図面、`WCH-common`にmirror）の両言語目次＋package名の数字です。同名packageが複数ファミリーで違う寸法を主張すればconflictとして現れます（現在0件）。QFN26C3とQSOP24のlead数のみreference（pin定義表と不一致=抽出行落ちの疑い、`?pin-table`）。

### `pins.csv` / `pin_functions.csv`

**注文型番単位**です。pins.csvは1行1(part_number, pin, pad)で「この型番のlead Nにどのpadが載るか」、pin_functions.csvは1行1(part_number, pad, signal, route)で「この型番のpadが持つ機能」。datasheetのpin表は1つのpinoutを複数型番で共有します（表題が適用範囲を宣言: `CH32V103x8x6`、`CH32V006（除F4U6以外）`、`TSSOP20(F8)`）が、その解決は生成時に済ませてあり、**行はpart_numberでそのままproducts.csvと結合できます**。共有していた事実はメタ側のdatasheet/table列（出典）に残ります。

`route`の値: `main`（リセット後の主機能）/ `default`（既定の代替機能）/ `remap-N`（remap値N）/ `af-N`（H41x・X315系のalternate function番号）/ 空（経路番号が資料になく要確認）。

両言語照合で吸収している表記ずれ: 表番号のずれ（X315はzh`表2-1-1`=en`Table 2-1`。表題中のシリーズ名で照合）、列見出しの綴り（`QFN48×7`、`QFN28(6)`、zh`LQFP64M`=en画像`LQFP64`は表内の消去法でペアリング）、1列が複数packageを兼ねる見出し（`LQFP48/QFN48X7`は成分ごとに登録）。

### `product_attributes.csv`

比較表の**全属性を縦持ち**で保持します（列に昇格済みのflash/sram/pin数/GPIO/温度/packageは除く）。両言語はラベルの語が違う（`定时器`↔`Timer`）ため、**正規化した値の並びのLCSで行を対応付け**ます——翻訳は表の行順を保つので、同値同順は同じ行です。対応付いて値が違う行はconflictになります（例: CH32H417WEU6のOPA数はzh=1/en=2で本物の食い違い）。`label_zh`/`label_en`に原文ラベルを残しています。

### `remap_fields.csv` / `remap_routes.csv`

AFIO route selectorの定義と、値→経路の対応です。pin_functions.csvの`remap-N`は、remap_routes（selector×値→signal/pad）→remap_fields（どのregisterの何bitか）と辿って解決します。出所はcandidates/（EVTヘッダ+RM register表+RM remap格子+datasheet pin表の結合）ですが、**根拠ごとの一致記録がファイルに残っていないため全行reference**です。EVTとRMの突き合わせを記録付きで再実行して確定へ昇格するのが次の課題です。H41x/X315系はremapではなくAF番号方式なので対象外（pin_functionsの`af-N`が持つ）。

読み方に注意が要る列が3つあります。

**`bits`はbitごとにregister名を持ちます**——`PCFR1:2;PCFR2:19;PCFR2:20`のように、値のLSBから順に`<register>:<bit>`を`;`で並べます。ほとんどのselectorは1つのregisterに収まりますが、CH32L103 / CH32M103 / CH32V20x / CH32V30x / CH32V4x7では**selectorがPCFR1とPCFR2にまたがります**。PCFR1だけを書くとエラーにならずに別の経路が選ばれるので、上位半分を落とさないための修飾です。`register`列は同じことを`PCFR1|PCFR2`と要約します。

**`peripheral`/`role`は`signal`を正規化した読みです**。`signal`は原典の表記のまま残してあり、同じ役割が資料により`USART1_TX` / `UART_TX` / `TX1` / `UTX`と書かれます。`tools/signal_vocabulary.py`の語彙規則がこれを1組へ読み、規則が当たらない行は**両方とも空**にします（推測で埋めるより、埋まっていないことが分かるほうが使えるため）。現在空なのは4380行中14行で、`AETR2`（ADCトリガでペリフェラル役割ではない）、`TIETR`（`T1ETR`の誤植に見えるがdatasheet原文未確認）、`ISINK1`/`ISINK2`（ペリフェラル_役割の形をしていない実在の信号）、`X`・`V`・`SW`・`PD0`・`DVP_`（pin表のテキスト層が壊れた断片）です。`uv run tools/signal_vocabulary.py --tables tables`で規則一覧と当たり具合を出せます。

**`UART`と`USART`は同じものへ畳みます。** WCHは同じseriesの中でも呼び分けが揺れていて、CH32V307はpin表が`UART5_TX`なのにAFIOのfieldは`USART5_REMAP`、CH32M030はpin表が`UART_TX`でfieldは`UART1_REMAP`です。畳まないとsignalが自分のselectorを見つけられません（実際にCH32V303/V307/V317のUSART5〜8が丸ごと落ちました）。12 familyのEVTヘッダを確認して**UARTnとUSARTnのAFIO fieldを両方持つfamilyは無い**ので、同じsiliconで別のペリフェラルを指すことはありません。`peripheral`列は正規化後の`USART5`になりますが、`remap_fields.csv`の`field`列と`selector`のidは原典の綴り（`UART1_REMAP` / `afio-uart1-remap`）を保ちます。

**`value=0`の行は既定経路です**。datasheet pin表の`default`列を値0として展開したもので、`basis`が`candidates(datasheet-pin-table-default:en)`になります。remap後の経路と同じ表に並ぶので、既定位置を知るためにpin_functions.csvを引き直す必要はありません。

**`valid_values`は下限です**。3つの資料の和を採っています——RMのremap格子が挙げる値、datasheet pin表が実際に経路を持つと示した値、EVTヘッダが定数として列挙している値。格子は「どちらでもよい」桁を`x`で書くので過大に出ることがあり（CH32X035の`USART4_RM=1xx`が4通りに展開される）、逆にどの資料も触れていない値は落ちます。**列挙されていない値が使えないとは限りません**が、列挙されている値はいずれかの資料が実証しています。`remap_routes.csv`に出る経路はすべてここに含まれます。

`tools/check_tables.py`が表だけを読んで検査する内容: `bits`が`register:bit`形式であること・重複がないこと・`register`列と一致すること、`valid_values`が`bits`の幅に収まること、`reset_value`が`valid_values`に含まれること、**`remap_routes.value`がすべて`remap_fields.valid_values`に含まれること**、`peripheral`と`role`が揃って埋まるか揃って空であること。

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

### `link_firmware.csv`

WCHが配るデバッガ用ファームウェアの一覧。生成は`tools/build_link_firmware.py`で、
`WCH-LinkUtility.ZIP`（またはMounRiver Studio同梱の同じディレクトリ）を読む。
**`.bin`自体はこのrepositoryに置いていない**——再配布になるため、載せるのは
sha256・サイズ・取得元URLだけ。

**この表はまだ「あなたのLinkは古い」を言えない。** `wcfg_version`列はWCH独自の
番号（`wchlink.wcfg`の`CH32V307Ver=42`等）で、**実機がUSBで申告する`2.12`のような
`major.minor`との対応が取れていない**。詳細と再挑戦の手順は
[docs/link-firmware-survey.ja.md](../docs/link-firmware-survey.ja.md)。
いま確実に使えるのは**sha256**で、「手元のファイルが今配られているものと同じか」は
これで判る。

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

### `errata.csv`

1行1エラッタ（ロット依存の挙動・ハードウェア注意事項）。ソースは`curated/errata.csv`（手編集）で、`condition`列がどのロット/型番に該当するかを持ちます。**両言語datasheetの記載ページ（source_zh/source_en）が記録済みの行はconfirmed**、片方のみはreferenceです。

エラッタは今後のdatasheet改版で増えうるため、`tools/scan_errata.py`が全datasheetを走査して既知（curated/errata.csvの`match`列の正規表現で識別）と照合し、未知の記述があれば`NEW`として報告します（終了コード1）。NEWが出たらcurated/errata.csvに行を追加し、再実行でNEW: 0を確認します。

### `operating_conditions.csv`

シリーズごとのクロックと動作電圧です。生成は`tools/build_operating.py`。

- **`F_MAIN`**: datasheet 1ページ目の特徴リストが謳う**系統主頻**。製品として語られる周波数がこれです
- `F_HCLK`/`F_PCLK*`/`F_CORE*`: 電気的特性章「一般動作条件」表の**上限値**。F_MAINとは別の事実で、値も食い違います（CH32V003は本文48MHz・電気的特性の上限50MHz）。README の Clock 列は F_MAIN を優先し、無いシリーズ（CH32X035・CH32H41x）だけ F_HCLK / F_CORE に落とします
- `V_DD`: 動作電圧。ADC使用時・USB使用時などの条件行があります
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

### `cores.csv`

1行1 QingKe core。coreのISA仕様（core manual一覧表、両言語確認済み）と、どのmanualに書いてあるかを持ちます。series.csvのISAはchip側datasheetの記述で、coreの任意実装部分（V3Bの[M][B]等）をchipがどう選んだかを表すため、cores.csvのISAとは別の事実です。

### `documents.csv`

1行1文書。`CH32L103DS0.PDF`という名前だけでは場所が分からないため、**中国語/英語それぞれのオリジナルページ（.html）・ダウンロードURL・mirror（GitHub raw）URL**と版数を持ちます。除外文書も`status`付きで載る完全なカタログです。EVT（ZIP）はarchive自体をmirrorに置かないため、mirror URLは展開済みツリーを指します。

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

## 現況（2026-08-22生成）

| 表 | 行数 | confirmed | reference | conflict |
|---|---:|---:|---:|---:|
| products.csv | 103 | 643 | 79 | 0 |
| packages.csv | 25 | 73 | 2 | 0 |
| series.csv | 27 | 100 | 4 | 0 |
| cores.csv | 13 | 13 | 0 | 0 |
| product_attributes.csv | 995 | 926 | 68 | 1 |
| remap_fields.csv | 284 | 0 | 284 | 0 |
| remap_routes.csv | 4643 | 0 | 4643 | 0 |
| systick.csv | 53 | 0 | 53 | 0 |
| link_firmware.csv | 10 | 0 | 10 | 0 |
| clock_configs.csv | 152 | 0 | 152 | 0 |
| clock_prescalers.csv | 263 | 0 | 263 | 0 |
| clock_sources.csv | 116 | 0 | 116 | 0 |
| clock_symbols.csv | 433 | 0 | 428 | 5 |
| clock_init.csv | 101 | 0 | 101 | 0 |
| evt_variants.csv | 56 | 0 | 56 | 0 |
| errata.csv | 21 | 21 | 0 | 0 |
| operating_conditions.csv | 283 | 257 | 21 | 5 |
| pins.csv | 4312 | 4022 | 290 | 0 |
| pin_functions.csv | 27850 | 24444 | 3406 | 0 |

pins系は全103型番がpin行を持ちます（型番→pin表列の解決失敗ゼロ）。

series.csvはcore・ISAとも全27シリーズで値が入っています（ISAはdatasheetとQingKe core manual両方で確認。H415/H416のみcore推定に依存するためreference）。temperatureは型番末尾の温度グレード規則で補っており、規則単独の値はreferenceです。

part_number・series・packageは全型番で確定（conflict 0件）。残るconflictはproduct_attributesの1件（CH32H417WEU6のOPA数: zh=1/en=2）です。productsのreference 79件の大半は温度グレード規則単独のtemperatureです。pins系のreferenceはM030・V20x・V30x・H41xに偏っており、片方の版で表の行が抽出できていない箇所です（文書の矛盾ではなく抽出欠落。今後の改善対象）。

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

```sh
uv run tools/build_tables.py --out tables                     # families/series/products/packages/cores/documents
uv run tools/build_pins.py --out tables                       # pins/pin_functions（数分かかる）
uv run tools/build_remap.py --out tables                      # remap_fields/remap_routes（candidates/から）
uv run tools/build_operating.py                               # operating_conditions（数分かかる）
uv run tools/build_evt_examples.py                            # evt_examples（EVTツリーと目録から）
uv run tools/build_clock.py --out tables                      # clock_configs/clock_prescalers/clock_sources（EVTから）
uv run tools/extract_images.py                                # 各repoのimage/（数分かかる）
uv run tools/check_images.py [--missing|--prune]              # 画像の必要一覧と検査
uv run tools/check_tables.py                                  # 全テーブルの参照結合検査
uv run tools/scan_errata.py                                   # エラッタ増分チェック（NEWで終了コード1）
uv run tools/build_tables.py --out tables --family CH32V006   # 1familyだけ
```
