# 索引（index/）

[English](README.md)

**利用者が引くための表**です。[証拠 `evidence/`](../evidence/README.ja.md)（資料の綴りのまま）と
[目録 `catalog/`](../catalog/README.ja.md)（名前）**だけ**から `tools/build_index.py` が組み直したもので、
新しい事実は足していません——`tools/check_tables.py` が「索引の行は証拠に戻せる」ことを毎回見ます。
区分の定義は [docs/data-layout.ja.md](../docs/data-layout.ja.md)。

## 何がどこにあるか

| 知りたいこと | 表 |
|---|---|
| 要求を満たす型番は（U2） | [`parts.csv`](parts.csv) |
| 能力（と、その数）から型番を絞る | [`capabilities.csv`](capabilities.csv) |
| 資料どうしが食い違っている箇所を全部見る | [`conflicts.csv`](conflicts.csv) |
| 機能から series を探す | [`features.csv`](features.csv) |
| この型番のこの足は何か・この機能はどの足に出るか（U1/U3） | [`pinout.csv`](pinout.csv) |
| remap の値をどれにするか（U3） | [`routes.csv`](routes.csv) |
| レジスタとビット（ヘッダ生成。U4） | [`registers.csv`](registers.csv) |
| レジスタの絶対番地 | [`register_map.csv`](register_map.csv) |
| DMA 要求 → channel | [`dma.csv`](dma.csv) |
| タイマの素性（チャネル数つき） | [`timers.csv`](timers.csv) |
| family をまたいで同じレジスタ配置か | [`register_layouts.csv`](register_layouts.csv) |
| 全ファイルの sha256 | [`manifest.csv`](manifest.csv) |

どの表も**結合した1ファイル**（全型番・全family）で、generator はこれを読みます。
CSV は機械が読むもので、人が型番や機能で絞り込んで見るのは viewer（[`pins.html`](../pins.html)。
GitHub Pages で配る）の仕事です。型番ごとに切ったコピーは持ちません（正本と重複するだけなので）。

## viewer

`pins.html` が読むのは `catalog/products`・`index/pinout`・`index/capabilities` と、証拠2表
（`product_attributes`・`remap_fields`）です。raw 3.5MB・転送 218KB・解析 0.25秒ほど。
**series 別の表示用キャッシュは意図的に置きません**——索引の複製をもう1つ抱えることになるためです。

| パラメータ | 中身 |
|---|---|
| `?chip=CH32V307` | series view: pad × 機能の格子と比較表 |
| `?chip=CH32V307VCT6` | product view: lead 番号・その series の remap selector・**比較表がその型番に与えていない instance は薄表示** |
| `&features=ADC,TIM` | その機能の列だけ（`UART` は `USART` として受ける） |
| `&routes=default,remap,af,unstated` | その経路だけ |
| `&q=USART1` | 検索。pad・資料の綴り・正規化した peripheral/role のどれでも当たる |
| `&tim=split` | TIM を1列にまとめず instance ごとに出す |

`?chip=` が無ければ series と型番の一覧を出します。セルには証拠の確度が付きます——
`~` は単一出所、`!` は両版の食い違い、remap 値のあとの `?` は selector を決められないもの。
remap 値をクリックするとその selector のレジスタ行へ飛びます。

## 共通の規則

- 名前は `tools/signal_vocabulary.py` の語彙で揃えてあります（`peripheral`・`role`・`port`・`gpio`）。
  **元の綴りは隣の列**（`signal`・`spelled`・`define`）に残るので、証拠へ戻れます
- `confidence` は使った証拠行の確度（複数行を畳んだ表はいちばん弱いもの）。`basis` は証拠行と
  1対1のときに写します。`parts.csv` のような横長の表は `basis` を持たず、下に「この列はどの証拠から」を書きます
- data 列は英語。`#` 列より右が出所
- 証拠と違う値を持つのは1箇所だけ: **pin 表の remap 値が RM の格子と食い違う行**は格子の値を採ります
  （`pinout.route`。CH32V103 の TIM3 12行。証拠 `pin_functions` は pin 表の値のまま `conflict` で、
  basis に `!rm-remap-grid(=remap-N)` があります。格子はその値の定義そのもので、pin 表は写しだからです）

## consumer の契約

読んでよいもの: `catalog/` の全表、`index/` の正本、`evidence/` のうち README で「安定」と印の
ある表（EVT ヘッダ由来）。それ以外の証拠の表は形を変えることがあります。固定は
commit と読む表の sha256（`manifest.csv` の sha256 を1つ固定してもよい）。列を変えたら
[worklist](../docs/worklist.ja.md) に記録し、この README の列表を更新します。

## 各表

### `parts.csv` — 型番の比較表

1行1型番。`catalog/products.csv` の仕様列と、`evidence/product_attributes.csv` の比較表の値、
`evidence/operating_conditions.csv` のクロック上限・電圧範囲を横に並べたもの。

| 列 | 中身 | どの証拠から |
|---|---|---|
| `part_number` `series` `family` `package` | 識別 | `catalog/products` |
| `pins` | lead 数 | `catalog/packages.pin_count` |
| `flash_bytes` `sram_bytes` `gpio_count` `temperature` | 主要仕様（バイト数・個数・温度範囲） | `catalog/products`（列ごとの根拠はそちらに） |
| `clock_max` | 系統主頻（`F_MAIN`。無ければ `F_HCLK`→`F_SYSCLK`→`F_CORE` の上限）。条件違いは `/` 併記 | `evidence/operating_conditions` |
| `vdd_min` `vdd_max` | `V_DD` の包絡（V） | 同上 |
| `usart` `spi` `i2c` `can` `usb` `adc` `dac` `opa` `cmp` `timers_advanced` `timers_general` `rtc` `ethernet` | 比較表の値**そのまま**（`4`・`1/10`・`√`）。属性の綴りが family で違うので `build_index.py` の `ATTRIBUTE_COLUMNS` で列に寄せる。同じ列に2属性が当たれば `;` | `evidence/product_attributes`（`label_zh/en` に資料の見出し） |
| `confidence` | 仕様列の確度のうちいちばん弱いもの | — |

数え方の規則は持ちません（`OPA/CMP = 4` を OPA 4 と読まない）。数を突き合わせるのは
`tools/check_counts.py` の仕事です。

### `pinout.csv` — 型番 × lead × 機能

1行1（型番, lead, 機能）。**機能の無い lead（電源・NC・GPIO だけの足）も1行**持つので、
`port`+`gpio` → lead が1表で引けます。

| 列 | 中身 |
|---|---|
| `pin` | lead 番号。露出パッドは `EP` |
| `pad` | 資料の綴り（`PA0-WKUP`・`LO1`・`VDD_VIO_1`） |
| `port` `gpio` | GPIO としての読み（`A`・`0`）。装飾を落とし、括弧の別名（`LO1 (PA0)`）からも埋める。GPIO でなければ空 |
| `kind` | `gpio` / `power` / `analog` / `other` / `nc`（`evidence/pins` の付与列）。`nc` は資料が「使わない」と書いた足で、番号だけがあり pad 名も型も機能も無い |
| `peripheral` `role` | 語彙で揃えた機能（`USART1`・`TX`）。周辺名の特殊な綴りは下の表 |
| `signal` | 資料の綴り（`USART1_TX` / `TX1` / `UTX`） |
| `route` | `main`（主功能。リセット直後に生きている）／`default`（默认复用功能。AF モードにすれば remap 無しで届く）／`remap-N`／`af-N`。**`main` と `default` は別のこと**で、どちらに書くかは family で違う（[evidence/README](../evidence/README.ja.md) の「`route` の値の意味」） |
| `selector` `value` | その経路を選ぶ AFIO selector（`afio-tim2-remap`）と値。`routes.csv` の鍵。`default`/`main` は値 `0`。selector を持たない経路は空 |
| `af` | `af-N` の N（AF 方式の family: V205・X315・H41x）。書き込み先は `evidence/pin_alternate` |

載せないもの: pad 自身の GPIO 名（`PA9` の主機能が `PA9`）と電源の主機能（`VSS` の `VSS`）。
ただし **`NRST`・`OSC_IN`・`BOOT0` のように自分の名前が機能そのもの**である pad は載せます
（設定しなくても動く機能として引くため）。語彙で覆えない綴りは載せず、その数は
`tools/check_tables.py` の `KNOWN_ROLE_GAPS`（いま 0）で固定してあります。

**語彙の周辺名のうち、資料の見出しと同じ綴りでないもの**（`tools/signal_vocabulary.py` の `SYSTEM` に根拠）:

| `peripheral` | 何か | 資料の呼び方 |
|---|---|---|
| `PREDRV` | CH32M030/M007 のゲートドライバ出力 `HO0`〜`HO3`／`LO0`〜`LO3` | 「预驱 / pre-drive」 |
| `ISP1`/`ISP2` | 差分入力電流サンプリング。役割 `P`/`N`、`QDET`（Q 値検出） | RM §17.2.6 |
| `QII1`/`QII2` | 交流小信号増幅デコーダ。役割 `IN` | RM §17.2.5 |
| `ISINK1`/`ISINK2`・`ISOURCE1`/`ISOURCE2` | 可編程シンク/ソース電流モジュール。役割 `OUT` | RM EXTEN 章 |
| `PWR` の `V_DET` | PB4 の VHV 分圧監視／過電圧リセット | RM 電源制御 |
| `SDI` の `SWDIO` ← `SWIM` | CH32M030 PA3 の `SWIM` は 1-wire SDI の綴り違い | DS §1.4.22 |
| `ADC1` の `RETR`/`IETR` ← `AETR`/`AETR2` | CH32V003 の略記。規則/注入転換の外部トリガ | RM 表7-13/7-14 |
| `TIM1` の `ETR` ← `TIETR` | CH32V003 pin 表の誤植（`I` と `1`） | 表2-3 では `T1ETR` |
| `BLE` の `ANT` | CH32V208 の専用 pad | 凡例「射频信号输入输出（天线）」 |

### `routes.csv` — remap selector の値 → 信号と pad

1行1（series, selector, 値, 信号）。`evidence/remap_fields`（selector の register・bit）と
`evidence/remap_routes`（値ごとの信号と pad）を結び、`peripheral`/`role`/`port`/`gpio` を付けたもの。
`register` が `PCFR1|PCFR2` のように2つあるときは field が2レジスタにまたがる（`bits` に register 名つき）。
`peripheral`/`role` が空の行は語彙で読めない綴り（GPIO 名を信号に書く X315 の `PD0` 1行）。

### `registers.csv` — family × 型 × register × field

1行1（register, bit define）。`evidence/registers`（構造体の offset）に `evidence/register_fields`
（bit define）を並べたもの。field を持たない register も1行（`field` 空）。

| 列 | 中身 |
|---|---|
| `type` | EVT の `*_TypeDef` の名前（`USART`・`DMA_Channel`）。同じ型は family で共有できる（`register_layouts.csv`） |
| `register` | 構造体メンバー。配列は要素ごと（`EXTICR[1]`。offset は先頭＋添字×幅）、入れ子は `sTxMailBox[0].TXMIR` |
| `offset` `width_bits` `count` | 構造体内 offset・幅・配列数。**offset が空の行**は banner の register 名を構造体のメンバーに結べなかった define（1,591 行。bit 位置と define 名は事実なので落とさない） |
| `field` | 読むための名前（型・register の接頭辞を落とした） |
| `define` | EVT の綴りそのまま（`RCC_APB2PCENR_USART1EN`）。証拠へ戻る鍵 |
| `kind` `of_field` `value` | `field`＝ビット領域、`value`＝その領域の列挙値（`of_field` がどの領域か、`value` がその値） |
| `bits` `mask` | ビット位置（`7:0`）と mask |
| `description` | EVT のコメント |
| `access` `reset` | RM のレジスタ表から（bit 位置が一致した行は `confirmed`） |

### `register_map.csv` — 絶対番地

1行1（family, block, register）。`evidence/register_blocks`（`USART1` の base address）×
`registers` で `address = base + offset`。型の構造体が無い block（V407/X315 の `USBHSH`）は
register 空・address＝base の1行。

### `dma.csv` — DMA 要求 → channel

`evidence/dma_requests` の綴り（`spelled`。`TIM1_UP*`・`USART1_TX_1`）を読んだもの:
`request` は印を落とした要求名、`remap` は印の読み（`selectable`＝`*`、X315 の `_0`/`_1`＝`default`/`remap`）、
`peripheral` は語彙で揃えた周辺名（`SPI/I2S2_RX` → `SPI2`）。`request_id` を持つ行（H417 の DMAMUX）は
channel 固定でなく、`note` にそう書く。variant・channel の意味は [evidence/README](../evidence/README.ja.md) の `dma_requests`。

### `timers.csv`

`evidence/timers`（RM の種類・カウンタ幅・更新割り込み）に、`pinout.csv` から数えた
`channels`（pin に出ている最大チャネル番号。silicon の上限ではない）と
`complementary`（`CHxN` が pin に出ていれば `1`）を足したもの。

### `capabilities.csv` — 型番 × 能力（縦持ち）

`tools/build_capabilities.py` が `evidence/product_attributes` **だけ**から作ります。
1行1（型番, 能力, qualifier, 元の属性）。

`parts.csv` は比較表を横に並べたもので、158種類ある属性の綴りのうち列に持てるのは13種類だけです。
この表は残りも含めて全部を行に落とし、**能力の名前を揃えて**あるので、
「SPI が何本か」を family ごとに `spi`・`communication_interfaces_spi` と綴り分けている事情を
引く側が知らなくて済みます。

| 列 | 中身 |
|---|---|
| `capability` | 揃えた名前（`usart`・`can-fd`・`usb-hs`・`timer-general`・`adc`・`adc-channel` …） |
| `qualifier` | **資料自身がその能力の中で付けている区別**（`32bit`・`tim1`・`include-phy`・`adc1`・`with-tkey`）。綴りの違いは区別ではないので `attribute` 列に残ります |
| `stated` | 資料の言い方。`count`＝素の整数／`marker`＝`√`・`Supported`（数を言わずに有ると言っている）／`text`＝それ以外（`8+2`・`3/2`・`10@2`・`MAC+10M/100M PHY`） |
| `count` | その整数。`stated=count` のときだけ入ります。**数える規則は当てません**——`8+2` を 10 とは読みません |
| `value` | 資料の値そのまま |
| `attribute` | 元になった `evidence/product_attributes` の鍵（戻り道） |

**行があること自体が「持っている」の主張**です。比較表が `-` と書いたセルは
`product_attributes` の時点で落ちているので、ここにも現れません。ただし
**その読みが効くのは family の中だけ**——行が無いのは「その型番が持っていない」か
「その family の比較表にその行が無い」かのどちらかで、表からは区別できません。
family をまたいで「X を持たない型番」を数えないこと。

`adc` は**ユニット数**、`adc-channel` は**チャネル数**です。資料はどちらも「ADC」と書くことがあり
（`adc`＝`8+2` はチャネル、`adc_unit`＝`2` はユニット）、規則で畳むと静かに間違えるので、
属性→能力の対応は**総当たりの辞書**にしてあります（`tools/build_capabilities.py`。
辞書に無い属性が現れたら生成が落ちます）。

クロック・電圧・Flash・SRAM・GPIO の行も比較表にあるぶんは載せますが、
**数として引くなら `parts.csv` のほうが出所が良い**です（`evidence/operating_conditions` と
`catalog/products` から来た数で、比較表の自由文 `Max: 144MHz` ではありません）。

### `conflicts.csv` — 資料どうしの食い違い

`tools/build_conflicts.py` が `catalog/`・`evidence/` 全表から `conflict` の印を集めたもの
（165行）。証拠は食い違いを片方に寄せず両論を残す規則ですが、その記録は11の表に散っていて、
「両版で食い違う仕様を全部」に答えるには全表を grep するしかありませんでした。

| 列 | 中身 |
|---|---|
| `table`・`subject` | どの表のどの行か（鍵の列を `col=value` で並べたもの） |
| `field`・`kept` | 争っている列と、表が採った値。列ごとの印のとき／`basis` がその表に実在する列名を名乗るとき／その表が1行につき1つの値を主張するとき（`pin_functions.route`・`product_attributes.value`・`register_fields.bits`）に埋まる。1行で複数の値を主張する表は空で、`basis` の側が欄を名指しする |
| `dissenting` | `basis` で `!` が付いている出所 |
| `alternative` | その出所が言う値（`basis` の `(=…)`） |

**115行に相手の値が入り、68行は空**です。`memory_configs`（67行）と `timers`（1行）は
食い違いを散文で記録していて DSL に持たないので、空欄は「[evidence/README.ja.md](../evidence/README.ja.md)
の該当節を読め」の意味になります。

**`conflict` の印は「事実が食い違っている」と同義ではありません。** `product_attributes` の25行は
**仕様の差**（`2 (OPA1/3)` と `1（OPA1）`）と**言い回しの差**（`Typical: 72MHz` と `Typ. 72MHz`）が
混ざり、`operating_conditions` の30行のうち8行は**綴りの差だけ**です（`mS` と `ms`、`0.8VDD` と
`0.8*VDD`、`VI/O` と `VIO`）。中文版が異を唱えている行の `alternative` は、`basis` が持つ
**訳した読み**であって原文の綴りではありません。

`operating_conditions` は1行で min/typ/max/unit の4つを主張していて、争っているのがどれかは
行ごとに違うので、`field` は空にして `alternative` の側が欄を名指しします（`min=60,typ=82,max=110`）。

### `features.csv` — 機能から series を探す

`tools/build_feature_tags.py` が作ります（比較表を優先し、無ければ datasheet の節見出し）。
1行1（タグ, series）。`precision`＝`part`（比較表が行を持つ。型番単位）／`datasheet`（節見出しに戻る。
datasheet 単位）。`parent` は上位のまとめ（`USBHS` は `USB` にも入る）。節見出しだけだと
`CH32V20x_30xDS0` の Ethernet が V303 にも付く偽陽性が出るので、比較表がある場合はそちらを採ります。

### `register_layouts.csv`

`tools/build_registers.py` が作ります。(family, 型) → 構造体の形のハッシュ `layout`。同じ `layout`
の family はレジスタ定義を共有できます（D-5）。

### `manifest.csv`

`index/` の全 CSV（自分以外）の path・行数・sha256。`build_index.py` の最後に作り、
`check_tables.py` が中身と一致することを見ます。

## 生成と検査

```sh
uv run tools/build_capabilities.py     # capabilities.csv（manifest に入るので build_index より前）
uv run tools/build_conflicts.py        # conflicts.csv（同上）
uv run tools/build_index.py            # 全部（1〜2秒。証拠の表が揃っていること）
uv run tools/build_index.py --only pinout,timers
uv run tools/check_tables.py           # 索引 ⊆ 証拠、manifest 一致
```

証拠の表を作り直したら索引も作り直します（順番は [evidence/README](../evidence/README.ja.md) の「生成」）。
