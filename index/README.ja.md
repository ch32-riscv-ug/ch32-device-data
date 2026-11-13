# 索引（index/）

[English](README.md)

**`index/` の下が公開面の全部で、その外は公開面ではありません**（[consumer の契約](#consumer-の契約)）。
表は2種類あります。

- **資料の事実をそのまま公開する表**（[そのまま公開する表](#そのまま公開する表)）: 鍵の表（family・series・
  パッケージ・コア）と、資料や EVT ヘッダから読んだ事実。それぞれの生成器がここに直接書きます。
- **引くための表**（[各表](#各表)）: [証拠 `evidence/`](../evidence/README.ja.md)（資料の綴りのまま）・目録・上の表
  **だけ**から `pipeline/build/build_index.py` が名前を揃えて組み直したもの。新しい事実は足していません——
  `tools/check_tables.py` が「索引の行は証拠に戻せる」ことを毎回見ます。

`index/`・`evidence/`・`catalog/` の区分の定義は [docs/data-layout.ja.md](../docs/data-layout.ja.md)。

## 何がどこにあるか

| 知りたいこと | 表 |
|---|---|
| 要求を満たす型番は。その名前・パッケージ・メモリ・クロック・電源・周辺の数 | [`parts.csv`](parts.csv) |
| 能力（と、その数）から型番を絞る | [`capabilities.csv`](capabilities.csv) |
| 資料どうしが食い違っている箇所を全部見る | [`conflicts.csv`](conflicts.csv) |
| 機能から series を探す | [`features.csv`](features.csv) |
| この型番のこの足は何か・この機能はどの足に出るか | [`pinout.csv`](pinout.csv) |
| debug 配線は1線（SWIO）か2線（SWDIO+SWCLK）か | [`debug_interfaces.csv`](debug_interfaces.csv) |
| remap の値をどれにするか | [`routes.csv`](routes.csv) |
| 有効にした周辺で pad が動く信号（AFIO の remap ではないもの） | [`pin_conditions.csv`](pin_conditions.csv) |
| レジスタとビット（ヘッダ生成） | [`registers.csv`](registers.csv) |
| レジスタの絶対番地 | [`register_map.csv`](register_map.csv) |
| DMA 要求 → channel | [`dma.csv`](dma.csv) |
| タイマの素性（チャネル数つき） | [`timers.csv`](timers.csv) |
| family をまたいで同じレジスタ配置か | [`register_layouts.csv`](register_layouts.csv) |
| series・family・パッケージ・コア | [`series.csv`](series.csv)・[`families.csv`](families.csv)・[`packages.csv`](packages.csv)・[`cores.csv`](cores.csv) |
| chip ID・option bytes・flash の形と書き方 | [`device_ids.csv`](device_ids.csv)・[`option_bytes.csv`](option_bytes.csv)・[`option_byte_fields.csv`](option_byte_fields.csv)・[`flash_geometry.csv`](flash_geometry.csv)・[`flash_program_method.csv`](flash_program_method.csv) |
| 絶対最大定格 | [`absolute_maximum_ratings.csv`](absolute_maximum_ratings.csv) |
| OPA/CMP と USB-PD のレジスタの field | [`opa_cmp_registers.csv`](opa_cmp_registers.csv)・[`usbpd_plumbing.csv`](usbpd_plumbing.csv) |
| option bytes で決まる FLASH/SRAM の配分 | [`memory_configs.csv`](memory_configs.csv) |
| WCH-Link のファームのファイル（過去の版を含む）と、実測で不良と分かった版 | [`link_firmware.csv`](link_firmware.csv)・[`link_firmware_issues.csv`](link_firmware_issues.csv) |
| クロック・割り込み・メモリマップ・動作条件・エラッタ | [そのまま公開する表](#そのまま公開する表) |
| ここの全列の意味・書き方・空欄の意味 | [`columns.csv`](columns.csv) |
| 全ファイルの sha256 | [`manifest.csv`](manifest.csv) |

どの表も**結合した1ファイル**（全型番・全family）で、generator はこれを読みます。
CSV は機械が読むもので、人が型番や機能で絞り込んで見るのは viewer（[`pins.html`](../pins.html)。
GitHub Pages で配る）の仕事です。

## viewer

`pins.html` が読むのは `index/parts`・`index/pinout`・`index/capabilities` と、証拠2表
（`product_attributes`・`remap_fields`）です。series 別の表示用キャッシュは置きません——索引の複製を
もう1つ抱えることになるためです。

| パラメータ | 中身 |
|---|---|
| `?chip=CH32V307` | series view: pad × 機能の格子と比較表 |
| `?chip=CH32V307VCT6` | product view: lead 番号・その series の remap selector・**比較表がその型番に与えていない instance は薄表示** |
| `&features=ADC,TIM` | その機能の列だけ（`UART` は `USART` として受ける） |
| `&routes=default,remap,af,unstated` | その経路だけ |
| `&q=USART1` | 検索。pad・資料の綴り・正規化した peripheral/role のどれでも当たる |
| `&tim=split` | `TIM` を1列にまとめず instance ごとに出す |

`?chip=` が無ければ series と型番の一覧を出します。セルには証拠の確度が付きます——
`~` は単一出所、`!` は両版の食い違い、remap 値のあとの `?` は selector を決められないもの。
remap 値をクリックするとその selector のレジスタ行へ飛びます。

## consumer の契約

- **読むのは `index/` の下だけ。** `catalog/` と `evidence/` はこのリポジトリの作業の層で、形はいつでも
  変わります。ここに無いものが要るときは、外を読まずに公開を依頼してください（データの依頼）
- **固定は commit と `manifest.csv` の sha256。** manifest がここの全 CSV の行数と sha256 を持ちます。
  データの中に版の番号は持ちません——壊す変更は、読み手が固定を進めたときに「読む列が無い」ではっきり止まり、
  リリースの版はタグで表します
- **リリース。** tag `v<major>.<minor>...` を打つと、このディレクトリを1つの zip
  （`ch32-device-data-index-<tag>.zip`。全 CSV・README 2つ）にした GitHub の release が出ます。consumer を
  壊しうる変更——列の削除・改名、列の書き方の変更、鍵や `fixed` の値の改名——はリリースノートに書きます。
  ネットワークなしでビルドするときは zip を取り、中の `manifest.csv` で照合してください
- **列は名前で読む。** 列の並び順は契約に入らず、表と列は断りなく足されます
- **[`columns.csv`](columns.csv) がここの全表・全列を説明します**: `meaning`（意味）、`format`（`text`・`name`・`integer`・
  `decimal`・`hex`・`bits`・`reg-bits`・`list(;)`・`list(,)`・`list(|)`・`url`・`path`・`enum(a|b|...)`）、`empty`
  （空欄の意味）、`role`（`data`＝データの列／`provenance`＝確度と根拠の列。provenance はいつもデータの列のあと）。
  `tools/check_tables.py` が実データと突き合わせます（全列を覆う・enum の値・integer/hex の形・`never empty`・
  provenance が右端）
- **`columns.csv` の `spelling` は、その列の綴りを誰が決めるかを言います**: `fixed` はこの repository が決める
  （鍵、`routes.selector`・`operating_conditions.symbol` のような付けた識別子、`pinout.peripheral`/`role` の
  ような正規化した語彙）——既存の値の改名は壊す変更（リリースノートに書く）なので、照合はこちらで。`as-printed` は
  datasheet・RM・EVT ヘッダの綴りのまま（`pinout.signal`・`memory_map.region`・`clock_symbols.symbol`・
  `operating_conditions.condition`）——資料に合わせるので、改版で変わりえます。
  `prose` は人が読む文で照合に使わない。空は値の列（数・番地）
- **表・列・行を足すのは壊す変更ではありません。** 列は名前で読み、知らないものは無視してください
- **`family` は WCH の EVT パッケージの単位**で、名前は `<family>EVT.ZIP` から取ります。製品の系列でも、
  datasheet や RM の単位でもありません（`CH32V20x_30xDS0` は CH32V20x と CH32V307 にまたがり、CH32V006 は
  CH32V002〜CH32V007 と CH32M007 を含む）。WCH が EVT を組み替えたら family もそれに従い、それは
  壊す変更です
- **`confidence` は `confirmed`・`reference`・`conflict` のどれか**で、空になるのは、それが言う値が空のときだけ
  です（理由はその列の `empty`）。`confirmed`＝独立した根拠が2つ以上一致、または人が中身を確かめて根拠を
  記録した／`reference`＝根拠が1つで、裏付けも食い違いも無い／`conflict`＝根拠が食い違い、表は片方を採って、
  `basis` にもう片方を名指した。複数の行からできた値は、いちばん弱いものを採ります。どの確度をどう扱うかは
  consumer が決めます
- **`basis` は1つの文法に従います**（[下](#basis)）。どの資料のどの版・どのページが値を言っているか、
  どの出所が異を唱えているかを、プログラムが読めます
- 保証するのは形（列・意味・綴りの規則）、全行の出所、`tools/check_tables.py` が見る不変条件、原本が
  変わったときの再生成です。**全行が正しいことは保証しません**——資料が誤っていれば行も誤り、その
  ことを `confidence`/`basis` で言います

## basis

`basis` 列（と `<列>_basis` 列）は、隣の値の出所を並べます。

```
basis    := term ("+" term)*                     項は括弧の外の "+" で区切る
term     := [mark] source [dissent]
mark     := "!"   別のことを言う出所（必ず dissent が付く）
          | "?"   当てはめきれなかった照合（食い違いではない）
source   := [kind ":"] document [":" lang] ["(" locator ")"]
          | kind [":" label] ["(" detail ")"]
document := 目録の文書名（.PDF で終わる）。過去の版を指すなら "@V<版>"
lang     := "zh" | "en"
locator  := "p." <PDF の通しページ番号> [";" detail]  |  detail
dissent  := "(" 列 "=" 値 ("," 列 "=" 値)* ")"
```

- `CH32V407DS0.PDF:zh(p.59)` は、その datasheet の中文版の PDF 59 ページ。ページ番号は PDF 自身の通し番号なので、
  原本を mirror からそのページで開けます:
  `https://ch32-riscv-ug.github.io/<repository>/datasheet_<言語>/<文書>#page=<N>`。`<repository>` は
  `families.csv` の `datasheets`・`reference_manuals` でその文書を持つ family、QingKe のマニュアル・WCH-Link の
  マニュアル・パッケージ図なら `WCH-common` です
- `!CH32V007DS0.PDF:zh(max=115)` は、その出所が `max` を 115 と言い、表はもう一方の値を採ったこと。
  このような項は全部 [`conflicts.csv`](conflicts.csv) に集まります（`field` が列、`kept` が表の値、`alternative` が
  異論の値）
- `kind` はその出所の読み方です: `pin-table:zh`、`products:en`（比較表）、`rm:<manual>`、`rm-address:<manual>`
  （章の冒頭の絶対番地表）、`rm-remap-grid`、`evt(<file>)`、`evt-api(<file>)`、`measured:<日付>(<記録>)`、
  `rule:<名前>` など。全部の一覧と1行の説明は `pipeline/common/basis_grammar.py` の `KINDS` にあり、
  `tools/check_tables.py` は一覧に無い kind で落ちます
- 括弧はいつも対になります。`detail` と `value` は、対になった括弧・`,`・`+` を含めてかまいません

## 共通の規則

- 名前は `pipeline/common/signal_vocabulary.py` の語彙で揃えてあります（`peripheral`・`role`・`port`・`gpio`）。
  **元の綴りは隣の列**（`signal`・`spelled`・`define`）に残るので、証拠へ戻れます
- data 列は英語
- 証拠と違う値を持つのは1箇所だけ: **pin 表の remap 値が RM の格子と食い違う行**は格子の値を採ります
  （`pinout.route`）。証拠 `pin_functions` は pin 表の値のまま `conflict` で、basis に
  `!rm-remap-grid(route=remap-N)` があります。格子はその値の定義そのもので、pin 表は写しだからです

## そのまま公開する表

それぞれの生成器がここに直接書きます（`paths.PUBLISHED`）。1行1事実で、`confidence` と `basis` が付きます。
全列の意味は [`columns.csv`](columns.csv) に、資料からの読み方は同じ名前の表を
[目録の README](../catalog/README.ja.md) と [証拠の README](../evidence/README.ja.md) で引いてください。
鍵: `families`・`series`・`packages`・`cores`。
EVT ヘッダ由来: `interrupts`・`memory_map`・`systick`・`evt_variants`・`clock_configs`・`clock_prescalers`・
`clock_sources`・`clock_symbols`・`clock_init`・`clock_enables`・`pin_alternate`。
RM・datasheet 由来: `flash_geometry`・`flash_program_method`・`adc_internal`・`debug_data`・
`device_ids`・`option_bytes`・`option_byte_fields`・`register_blocks`・`errata`・`operating_conditions`・`esig`・
`absolute_maximum_ratings`・`opa_cmp_registers`・`usbpd_plumbing`・`pin_conditions`・`memory_configs`。
WCH-LinkUtility と MounRiver Studio の配布物由来: `link_firmware`（過去の版を含む）。実測した不良: `link_firmware_issues`。

## 各表

### `parts.csv` — 1行1型番

型番の表です。**値の列ごとに `<列>_confidence` と `<列>_basis` を持ちます。**

| 列 | 中身 | どこから |
|---|---|---|
| `part_number` `series` `family` `package` `flash_bytes` `sram_bytes` `gpio_count` `temperature` `packing` `listed_as` `datasheet` | 識別と主要仕様。比較表と ordering 表を突き合わせたもの | 目録 |
| `pins` | lead 数 | `packages.pin_count` |
| `clock_max` | 系統主頻（`F_MAIN`。無ければ `F_HCLK`→`F_SYSCLK`→`F_CORE` の上限）。条件違いは `/` 併記（`144/192 MHz`） | `operating_conditions`（使った行の確度と根拠） |
| `vdd_min` `vdd_max` | `V_DD` の包絡（V） | 同上 |
| `usart` `spi` `i2c` `can` `usb` `adc` `dac` `opa` `cmp` `timers_advanced` `timers_general` `rtc` `ethernet` | 比較表の値**そのまま**（`4`・`1/10`・`√`）。属性の綴りが family で違うので `build_index.py` の `ATTRIBUTE_COLUMNS` で列に寄せる。同じ列に2属性が当たれば `;` | `evidence/product_attributes` |

`family`・`listed_as`・`datasheet` は目録が付ける名前なので確度を持ちません。数え方の規則は持ちません
（`OPA/CMP = 4` を OPA 4 と読まない）。数を突き合わせるのは `tools/check_counts.py` の仕事です。

### `pinout.csv` — 型番 × lead × 機能

1行1（型番, lead, 機能）。**機能の無い lead（電源・NC・GPIO だけの足）も1行**持つので、
`port`+`gpio` → lead が1表で引けます。

| 列 | 中身 |
|---|---|
| `pin` | lead 番号。露出パッドは `EP` |
| `pad` | 資料の綴り（`PA0-WKUP`・`LO1`・`VDD_VIO_1`） |
| `port` `gpio` | GPIO としての読み（`A`・`0`）。装飾を落とし、括弧の別名（`LO1 (PA0)`）と、機能名の pad に pin 表が route 無しで書く GPIO 名（`OSC_IN` → `PD0`）からも埋める。後者は同じ型番の別の lead がその GPIO を持つとき（100ピン封装で `PD0` が独立した lead）は埋めない。GPIO でなければ空 |
| `kind` | `gpio` / `power` / `analog` / `other` / `nc`。`nc` は資料が「使わない」と書いた足で、番号だけがあり pad 名も型も機能も無い |
| `peripheral` `role` | 語彙で揃えた機能（`USART1`・`TX`）。周辺名の特殊な綴りは下の表 |
| `signal` | 資料の綴り（`USART1_TX` / `TX1` / `UTX`） |
| `route` | `main`（主功能。リセット直後に生きている）／`default`（默认复用功能。AF モードにすれば remap 無しで届く）／`remap-N`／`af-N`。**`main` と `default` は別のこと**で、どちらに書くかは family で違う（[evidence/README](../evidence/README.ja.md) の「`route` の値の意味」） |
| `selector` `value` | その経路を選ぶ AFIO selector（`afio-tim2-remap`）と値。`routes.csv` の鍵。`default`/`main` は値 `0`。selector を持たない経路は空 |
| `af` | `af-N` の N（AF 方式の family: V205・X315・H41x）。書き込み先は `pin_alternate` |

載せないもの: pad 自身の GPIO 名（`PA9` の主機能が `PA9`）と電源の主機能（`VSS` の `VSS`）。
ただし **`NRST`・`OSC_IN`・`BOOT0` のように自分の名前が機能そのもの**である pad は載せます
（設定しなくても動く機能として引くため）。語彙で覆えない綴りは載せず、その数は
`tools/check_tables.py` の `KNOWN_ROLE_GAPS` で 0 に固定してあります。

**語彙の周辺名のうち、資料の見出しと同じ綴りでないもの**（`pipeline/common/signal_vocabulary.py` の `SYSTEM` に根拠）:

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
`controller` は selector の register を持つ block（`afio`、EXTEN block なら `extend`）。`register` が
`PCFR1|PCFR2` のように2つあるときは field が2レジスタにまたがる（`bits` に register 名つき。`PCFR1:1;PCFR2:23`）。
`peripheral`/`role` が空の行は語彙で読めない綴り（GPIO 名を信号に書く X315 の `PD0`）。周辺を有効に
したときだけ成り立つ経路は `pin_conditions.csv` が補います。

### `registers.csv` — family × 型 × register × field

bit define ごとに1行と、bit define の無い register ごとに1行。どちらかは `kind` が言います:
`field`（ビット領域）、`value`（領域の列挙値。`of_field` がどの領域か）、`register`（register だけの行）。
bit define のある register は field と value の行にだけ現れ、各行が register の `offset`・`width_bits`・
`count` を持ちます。

**`register` はヘッダの綴りのままなので、同じレジスタが family で違う綴りになる。** AFIO の EXTI 設定は
多くの family で配列 `EXTICR[0]`〜`EXTICR[3]`（X035 は `EXTICR[0]`/`[1]`）、V003/V006/M030 は1メンバーの
`EXTICR`、H417 は2メンバーの `EXTICR1`/`EXTICR2`。名前は揃えない（ヘッダに無い名前を作ることになる）。
「その register の k 番目の語」は、同じ `type` の行を `offset` で並べて引く。

**header と manual が field の位置を違えて書き、実機の測定で決着したものは、この索引が
測った位置を採ります**（`bits`/`mask`）。行は `confidence=conflict` のままで、`basis` に両方の資料と
実測が並びます——`pinout.csv` が RM の remap 格子の値を採るのと同じ規則です。CH32L103 の
`FLASH_OBR` の `DATA0`/`DATA1` がそれで、header は `[17:10]`/`[25:18]`、manual は `[19:12]`/`[27:20]`。
WCH-LinkE で `FLASH_OBR` を読み返すと manual が正しかった（`basis` の末尾が
`obr-readback:wch-linke(bits=19:12)`）。`evidence/register_fields.csv` は資料の言い分を記録する表なので
header の bits のまま残します。

| 列 | 中身 |
|---|---|
| `type` | EVT の `*_TypeDef` の名前（`USART`・`DMA_Channel`）。同じ型は family で共有できる（`register_layouts.csv`） |
| `register` | 構造体メンバー。配列は要素ごと（`EXTICR[1]`。offset は先頭＋添字×幅）、入れ子は `sTxMailBox[0].TXMIR` |
| `offset` `width_bits` `count` | 構造体内 offset・幅・配列数。**`offset` が空の行**は banner の register 名を構造体のメンバーに結べなかった define（bit 位置と define 名は事実なので落とさない） |
| `field` | 読むための名前（型・register の接頭辞を落とした） |
| `define` | EVT の綴りそのまま（`RCC_APB2PCENR_USART1EN`）。証拠へ戻る鍵 |
| `kind` `of_field` `value` | 上の3種と、`value` の行の親の領域と値 |
| `bits` `mask` | ビット位置（`7:0`）と mask |
| `description` | EVT のコメント |
| `access` `reset` | RM 中文版のレジスタ表から名前で引いたもの。`access_confidence`/`access_basis` は英語版が同じ語を刷っているか |

### `register_map.csv` — 絶対番地

1行1（family, block, register）。`register_blocks`（`USART1` の base address）×
`registers` で `address = base + offset`。型の構造体が無い block（H417 の `UHSIF`・V103 の `USBFS`）は
`register` 空・`address`＝base の1行。

### `dma.csv` — DMA 要求 → channel

`evidence/dma_requests` の綴り（`spelled`。`TIM1_UP*`・`USART1_TX_1`）を読んだもの:
`request` は印を落とした要求名、`remap` は印の読み（`selectable`＝`*`、X315 の `_0`/`_1`＝`default`/`remap`）、
`peripheral` は語彙で揃えた周辺名（`SPI/I2S2_RX` → `SPI2`）。`request_id` を持つ行（H417 の DMAMUX）は
channel 固定でなく、`note` にそう書く。`variant`・`channel` の意味は [evidence/README](../evidence/README.ja.md) の `dma_requests`。

### `timers.csv`

`evidence/timers`（RM の種類・カウンタ幅・更新割り込み）に、`pinout.csv` から数えた
`channels`（pin に出ている最大チャネル番号。silicon の上限ではない）と
`complementary`（`CHxN` が pin に出ていれば `1`）を足したもの。一部の variant にだけあるタイマは
`condition` にその variant を書きます。

### `capabilities.csv` — 型番 × 能力（縦持ち）

`pipeline/build/build_capabilities.py` が `evidence/product_attributes` **だけ**から作ります。
1行1（型番, 能力, qualifier, 元の属性）。

`parts.csv` は比較表を13列に横に並べたものです。この表は全部の属性を行に落とし、**能力の名前を揃えて**
あるので、「SPI が何本か」を family ごとに `spi`・`communication_interfaces_spi` と綴り分けている事情を
引く側が知らなくて済みます。

| 列 | 中身 |
|---|---|
| `capability` | 揃えた名前（`usart`・`can-fd`・`usb-hs`・`timer-general`・`adc`・`adc-channel` …） |
| `qualifier` | **資料自身がその能力の中で付けている区別**（`32bit`・`tim1`・`include-phy`・`adc1`・`with-tkey`）。綴りの違いは区別ではないので `attribute` 列に残ります |
| `stated` | 資料の言い方。`count`＝素の整数／`marker`＝`√`・`Supported`（数を言わずに有ると言っている）／`text`＝それ以外（`8+2`・`3/2`・`10@2`・`MAC+10M/100M PHY`） |
| `count` | その整数。`stated` が `count` のときだけ入ります。**数える規則は当てません**——`8+2` を 10 とは読みません |
| `value` | 資料の値そのまま |
| `attribute` | 元になった `evidence/product_attributes` の鍵（戻り道） |

**行があること自体が「持っている」の主張**です。比較表が `-` と書いたセルは
`product_attributes` の時点で落ちているので、ここにも現れません。ただし
**その読みが効くのは family の中だけ**——行が無いのは「その型番が持っていない」か
「その family の比較表にその行が無い」かのどちらかで、表からは区別できません。
family をまたいで「X を持たない型番」を数えないこと。

`adc` は**ユニット数**、`adc-channel` は**チャネル数**です。資料はどちらも「ADC」と書くことがあり
（`adc`＝`8+2` はチャネル、`adc_unit`＝`2` はユニット）、規則で畳むと静かに間違えるので、
属性→能力の対応は**総当たりの辞書**にしてあります（辞書に無い属性が現れたら生成が落ちます）。
クロック・電圧・Flash・SRAM・GPIO の行も比較表にあるぶんは載せますが、**数として引くなら
`parts.csv` のほうが出所が良い**です（比較表の自由文 `Max: 144MHz` ではありません）。

### `conflicts.csv` — 資料どうしの食い違い

`pipeline/build/build_conflicts.py` が全表から `conflict` の印を集めたもの。表は食い違いを黙って片方に
寄せず、片方の値を採って行を `conflict` にし、`basis` にもう片方を名指します。この表はその印を集めます。

| 列 | 中身 |
|---|---|
| `table`・`subject` | どの表のどの行か（鍵の列を `col=value` で並べたもの） |
| `field` | 争っている列。列ごとの確度ならその列、ほかは異論の項が名指す列。複数なら `;` で並べる |
| `kept` | 表が採った `field` の値 |
| `dissenting` | `basis` で `!` が付いている出所 |
| `alternative` | その出所が言う `field` の値 |

**`conflict` の印は「事実が食い違っている」と同義ではありません。** `product_attributes` には言い回しの差
だけの行（`Typical: 72MHz` と `Typ. 72MHz`）があり、`option_byte_fields` で `field` が `field` の行は、
bit の位置や既定値ではなく field の名前の綴りが違うだけです。見分けるには `field` を読んでください。
中文版が異を唱えている行の `alternative` は、`basis` が持つ**訳した読み**であって原文の綴りではありません。

### `debug_interfaces.csv` — debug 配線は1線か2線か

`pipeline/build/build_debug_interfaces.py` が作ります。1行1 series。2つの証拠の突き合わせで `debug_if` を
決めます——**datasheet の debug 節見出しの綴り**（`evidence/features.csv`。`1-wire`／`单线`→`swio`、
`2-wire`／`2线`→`rvswd`）と、**WCH-Link manual の配線表＋両対応の注記**（`evidence/debug_wiring.csv`）。
manual が両対応と言えば `both`、見出しが wire 数を言う場合は manual と矛盾しないことを確かめます
（`swio` は `both` の部分集合として整合）。manual は V002/V004 を両対応（SWCLK=PB3）と括りますが、両者の
pin 表に SWCLK が無く見出しも 1-wire なので、**見出しを採り manual の異議を basis に記録**しています
（`!WCH-LinkUserManual.PDF(swclk=PB3,dual=yes)`）。

| 列 | 中身 |
|---|---|
| `debug_if` | `swio`（1線）／`rvswd`（2線）／`both`（両対応。manual の注記） |
| `wording` `section` | datasheet 側の節見出しの英語の綴りと節番号（CH32V208 は英語版に見出しが無く空） |
| `swdio_pads` `swclk_pads` | `pinout.csv` の正規化 role（SWDIO/SWCLK）の pad（`;`区切り。manual の pad が実在することも生成が確かめる） |

### `features.csv` — 機能から series を探す

`pipeline/build/build_feature_tags.py` が作ります（比較表を優先し、無ければ datasheet の節見出し）。
1行1（タグ, series）。`precision`＝`part`（比較表が行を持つ。型番単位）／`datasheet`（節見出しに戻る。
datasheet 単位）。`parent` は上位のまとめ（`USBHS` は `USB` にも入る）。節見出しだけだと
`CH32V20x_30xDS0` の Ethernet が V303 にも付く偽陽性が出るので、比較表がある場合はそちらを採ります。
逆に**節見出しが無い機能**（CH32V208 の Ethernet は概要文とブロック図にしか出ない）は、別の datasheet の
見出しで既に在るタグに限り、比較表の属性名の最後のトークンがそのタグなら付けます（`features`・`sections` は空、
`basis` は `attributes(...)`）。

### `register_layouts.csv`

`pipeline/extract/rm/extract_registers.py` が作ります。(family, 型) → 構造体と define 名の集合のハッシュ `layout`。同じ `layout`
の family はレジスタ定義を共有できます。

### `manifest.csv`

`index/` の全 CSV（自分以外）の path・行数・sha256。`build_index.py` の最後に作り、
`check_tables.py` が中身と一致することを見ます。

## 生成と検査

```sh
uv run pipeline/build/build_capabilities.py     # capabilities.csv（manifest に入るので build_index より前）
uv run pipeline/build/build_conflicts.py        # conflicts.csv（同上）
uv run pipeline/build/build_index.py            # 引くための表と manifest（1〜2秒。証拠の表が揃っていること）
uv run pipeline/build/build_index.py --only pinout,timers
uv run tools/check_tables.py           # 索引 ⊆ 証拠、manifest 一致、basis の文法
```

証拠の表を作り直したら索引も作り直します（順番は [evidence/README](../evidence/README.ja.md) の「生成」）。
