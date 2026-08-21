# 作業リスト

README自動生成の対象は**データシートとEVTを持つ12リポジトリのTOP**と**org TOP（.github）**です。両方とも特殊処理なしの全自動生成を目標にします。根拠は[docs/extraction-survey.ja.md](extraction-survey.ja.md)、データ構造は[tables/README.ja.md](../tables/README.ja.md)。

状態: ✅完了 / 🔜次 / ⬜未着手 / ❓要確認（人の判断待ち）

## 進捗

| 区分 | 完了 | 残り |
|---|---:|---:|
| データ収集 | 5 | 4 |
| README生成 | 3 | 3 |
| 画像 | 0 | 3（保留） |
| 検査・運用 | 4 | 1 |
| consumerからの依頼 | 2 | 1 |

## 着手順の方針

1. **自動取得できるもの**を先行（原典から機械抽出。腐らない）
2. 次に**自動取得できず更新頻度が低いもの**（一度書けば持つ）
3. **自動取得できず、そこそこ更新するもの**は「検出だけ自動化」して運用でカバーする

| 対象 | 更新の起点 | 頻度 | 検出手段 |
|---|---|---|---|
| エラッタ本文 | datasheet改版 | 年数回 | ✅ `scan_errata.py` |
| 翻訳辞書 | 新シリーズの未知ラベル | 新シリーズごと | ✅ CJK検査（CIが落ちる） |
| 画像 | 新シリーズ・新パッケージ | 新シリーズごと | ⬜ C2 check_images.py |

**載せないもの**: Arduinoコア・ツールチェーンの**チップ別対応状況**は生成物に入れません。自分たちがコントロールできない上流の状態を写すと必ず陳腐化し、しかも検出手段がないためです（サンプルの存在を対応宣言として扱わないルールとも整合）。org TOPからorg内リポジトリへのリンクは、リンク自体が腐らないので維持します。

この方針により、残る全項目が「自動取得」か「人が書くが機械が検出する」のどちらかに収まります。

## A. データ収集

- [x] ✅ **A1 エラッタ** — 21件、全件が中英両版のページ根拠つきconfirmed。`tools/scan_errata.py`で増分検出（NEWがあれば終了コード1）
- [x] ✅ **A2 動作条件** — `tables/operating_conditions.csv` 62行。クロック上限F_*と動作電圧V_DD。全27シリーズ
- [x] ✅ **A3 remap** — `remap_fields`/`remap_routes`（全行reference。根拠記録つき再実行で確定化するのは別課題）。2026-08-20に作り直し: `bits`がbitごとにregister名を持つようになり、PCFR1とPCFR2にまたがるselectorを表せる。`peripheral`/`role`列で`TX1`/`UTX`/`USART1_TX`の綴り差を吸収。value=0の既定経路を同じ表に収録。CH32V407/V467はRM未mirrorでも header+datasheet から生成する。`tools/check_tables.py`が表だけで整合を検査する（bit形式、値の幅、route値がvalid_valuesに含まれること）
- [x] ✅ **A4 公称主周波数** — U2/U1が最初に見る値。**現状は誤解を招く**: CH32V003のMax clockが電気的特性の50MHzで出るが、公称は48MHz（DS1ページ目「48MHz system main frequency」）。product_attributesには8シリーズ分しか無く自由文（`Max: 144MHz`、`40MHz@Zero-wait; Max: 192MHz@Non-zero wait`）。DS第1章の特徴リストから全シリーズ抽出し、`Main clock`列と`Fmax (HCLK)`列を分離する
- [x] ✅ **A5 EVT例題索引** — U1/U3への効果が最大。材料は全12リポジトリの`EVT/<FAMILY>_List_EN.txt`（周辺→例題→1行説明のツリー）に揃っている。パースして`tables/evt_examples.csv`へ
- [ ] ⬜ **A6 機能フラグ（USB/Ethernet/CAN/PD/DVP…）** — org TOPの「機能から探す」に必須。**現データでは作れない**（下記の調査結果）。DS 1.4機能説明からシリーズ単位で抽出する新規作業
- [ ] ⬜ **A7 メモリマップ** — U4向け。Flash/RAM先頭アドレス・サイズ・周辺ベースアドレス。DS 1.2章
- [ ] ⬜ **A8 書き込み方式** — U1の第一関門。1線式SDI（V003系）か2線式SWDか、WCH-Linkのどのモードか。シリーズ属性として`curated/`に記録
- [ ] ⬜ **A9 割り込みベクタ表** — U4向け。RM側。コスト高につき後回し

### A6の調査結果（2026-08-19）

product_attributesからは機能フラグを作れません。datasheetの比較表は**シリーズ内で差がある列しか持たない**ため、シリーズ共通の周辺は列ごと存在しません。

- CH32V307の属性は`adc_tkey / communicationinterfaces / dac_unit / opa_cmp / rng / timer`の6種のみ。USBHSもEthernetも行が無い（実際には両方ある）
- 複数周辺が1セルに同居する（`communicationinterfaces`の値が`4`など、意味が列名に依存）
- **「属性が無い＝その機能が無い」と推論するのは誤り**

## B. README生成

- [x] ✅ **B1 12リポジトリのTOP生成** — Series/Documents/比較表/ピン表/remap/Errata/Diagrams。日次でミラーが取得
- [x] ✅ **B2 org TOPの生成** — 現行はリポジトリ一覧＋横断文書＋toolchain
- [x] ✅ **B3 org TOP「型番から探す」** — **今あるデータだけで作れる**（series.csv: series→family、products.csv: part_number→family）。CH32M007がCH32V006に、CH32M103がCH32L103に、CH32V317がCH32V307に入っている件が検索者に見えるようになる。これができれば`curated/readme-extras/CH32V20x.md`（V205分離の手書きNotes）を削除して**特殊処理ゼロ**にできる
- [ ] ⬜ **B4 節構成の組み替え** — 現状はU3（開発中の人）向けの順序。U1→U2→U3順へ:
  `Quick start`(A8) → `Products` → `Pinout`(画像+表) → `Block diagram` → `Errata` → `EVT examples`(A5) → `Documents`(+同期日時・評価ボードPDF) → `Reference`(A7)
- [ ] ⬜ **B5 org TOP「機能から探す」** — A6待ち
- [ ] ⬜ **B6 評価ボード情報** — `EVT/PUB/`の回路図PDF・ボード説明書へのリンク（全リポジトリに存在）

## C. 画像（保留）

**現時点では生成READMEに画像を使いません。** 切り出しの品質が実用水準に達していないためです。ピン配置図は「パッケージ→型番→データシート」の対応表で代替しています。

- [ ] ⬜ **C1 切り出し品質** — `tools/extract_images.py`は134枚を生成できるが、図の縁の判定・ファイル名と図中型番の一致（82枚中6枚が不一致）に課題が残る
- [ ] ⬜ **C2 ページ番号リンク** — `#page=N`はGitHub Pages配信のPDFで機能する（`content-type: application/pdf`を確認済み）。抽出時にページは分かるので`tables/figures.csv`として持てば、対応表からページ直リンクにできる
- [ ] ❓ **C3 シリーズ構成図** — 原典のデータシートには無く、WCH製品ページ由来。手作りは27シリーズ中10枚のみで17枚不足。`tools/build_system_figures.py`でtables/から生成もできるが見た目が別物。**採用は保留**

### 不足している手作りsystem図（17シリーズ）

CH32H415, CH32H416, **CH32H417**, CH32M007, **CH32M030**, CH32M103, CH32V002, CH32V004, CH32V005, CH32V007, CH32V305, CH32V317, **CH32V407**, CH32V467, CH32X033, **CH32X305**, **CH32X315**

太字はファミリーの主力シリーズ。CH32M030・CH32V407・CH32X315・CH32H417は図が1枚もない状態です。

## D. 検査・運用

- [x] ✅ **D1 参照結合検査** — `tools/check_tables.py`が13テーブルの全FKを検査
- [x] ✅ **D2 中国語混入検査** — `#`より左のデータ列にCJKがあればCIが落ちる
- [x] ✅ **D3 エラッタ増分検査** — `tools/scan_errata.py`（ミラーPDFが要るのでCIではなく手動運用）
- [x] ✅ **D5 画像の検査** — 寸法異常と同一切り出しの共有を機械検出（目視の前段。実際に4件の欠損を捕捉）
- [ ] ⬜ **D4 同期日時の表示** — 各READMEに「いつ原典と同期したか」。U5（原典に到達できない人）が最初に確認する情報

## E. consumerからの依頼

`ArduinoCore-CH32`が`docs/research/`で出している依頼。上流はこのrepositoryなので、
受けるかどうかもここで決める。

| # | 依頼 | 状態 |
|---|---|---|
| R-19 | signal名の正規化と分割remap field | ✅ **実装済み**（2026-08-20〜21）。D-0〜D-4すべて。[extraction-survey](extraction-survey.ja.md)参照 |
| R-20 | レジスタマップ（D-1〜D-8） | 🔜 **調査済み・方針未決**。[register-map-survey.ja.md](register-map-survey.ja.md) |
| R-24 | クロック関連データ（C-1〜C-8） | ✅ **C-1〜C-8を実装**（2026-08-21）。`clock_configs.csv`・`clock_prescalers.csv`・`clock_sources.csv`＋`operating_conditions.csv`拡張。下記 |

### R-24 クロック関連データ（2026-08-21受領・一部実装）

**実装した分**: `tools/extract_clock_tree.py`がEVTの`system_ch32*.c`を静的に読み、
`tools/build_clock.py`が2表へ落とす。PDFもコンパイラも要らない。

| 列 | 対応するC-n | 中身 |
|---|---|---|
| `domains` | C-1 | `SYSCLK=400000000;CoreCLK[V5F]=400000000;...`。多段・双核も表せる |
| `pll` + `condition` | C-3 | PLL関連の記号列と、それがどの`#if`分岐か |
| `outside_rcc` | C-4 | `EXTEN->EXTEN_CTR EXTEN_PLL_HSI_PRE` など |
| `hpre`/`ppre1`/`ppre2` + `clock_prescalers.csv` | C-5 | 選ばれる分周比と、分周比→field値の符号化 |
| `flash_latency` | C-6 | その設定が書くlatency。空欄は「書かない」 |
| `clock_sources.csv` | C-7 | USB/RTC/ADC/I2S/RNG/ETH等の源の選択肢と、選ぶregister field |
| `confidence`/`basis` | C-8 | 既存の慣行どおり。単一資料なので全行reference |

152行 / 263行 / 116行。**seriesではなくfamilyで引く**——クロックツリーはsiliconの性質で
EVTのcloneが1 silicon分だから。seriesで引くとV203がCH32V20xとCH32V205の両方から
別のツリーを拾う。`tools/check_tables.py`がfamilyの結合・分周比の存在・`domains`の書式・
value/shiftが数であることを検査する。

**C-2も実装**（2026-08-21）。`tools/build_operating.py`を発振器の表まで読むよう広げた。
`operating_conditions.csv`は76行→**241行**になり、`ACC_HSI`（確度・温度範囲ごと）、
`F_HSE_ext`/`F_LSE_ext`（外部クロックの許容範囲）、`F_HSI`/`F_LSI`、`DuCy_*` が入った。
**C-3の上下限も同時に取れた**——`F_PLL_IN`/`F_PLL_OUT`/`F_VCO`（例: L103は入力3〜25MHz・
出力18〜96MHz、H41xは出力100〜600MHz）。C-5のバス上限も`F_PCLK1`の`max`が`F_HCLK`という
記号のまま入っている。

抽出上の注意（吸収済み）: 発振器の表は本体と別ページにあり5表に分かれるので、
**1つ見つけて打ち切ってはいけない**。記号セルの添字は改行にも空白にもなる
（`F HSE_ext`→`F_HSE_ext`）。脚注を落とした跡が空白として残る（`V (6)\nDD`→`V_DD`）。
記号セルが空の続き行は別パラメータのことがあり、単位で弾ける（`F_*`に`%`が付く行）。

**周辺固有の上限も実装**（2026-08-21）。ADCの上限は散文ではなく`ADC characteristics`表に
あった（表題は`ADC characteristics`/`10-bit ADC characteristics`/`10位ADC特性`と揺れる）。
`operating_conditions.csv`は**283行**になり、`f_ADC`が19行入った。

依頼書の「ADCは14MHz以下」は**V103/V203/V208/V30xだけ**の話だった。実測:

| family | ADCクロック上限 |
|---|---|
| V003 | **6 / 12 / 24 MHz**（V_DD 2.8〜 / 3.2〜 / 4.5〜5.5V） |
| **X033・X035** | **6 / 8 MHz**（V_DD < 3.2V / ≥ 3.2V） |
| V103・V203・V208・V303〜V317 | 14 MHz |
| M030 | 18 MHz |
| V407・V467 | 30 MHz |
| L103・M103・M007・V002・V004〜V007 | 48 MHz |
| V205 | 64 MHz（zh版は96 MHzでconflict） |
| H41x・X305・X315 | 80 MHz |

**電源電圧に依存する**のがV003とX033/X035で、依頼書に無い差。X035は主対象なのに
6〜8MHzで他familyより1桁近く厳しい。

抽出上の追加注意: 表はページを跨ぎ、**続きページはヘッダ行を持たない**
（V003のADC上限の行はキャプションの次ページにしかない）。列数が同じなら直前の
列並びを引き継ぐ形で吸収した。

**未実装**: USBが48MHzを要求することの根拠。`RCC_USBCLKSource_*`で分周は選べるが
「48MHzでなければならない」はRMのUSB章の散文で、表になっていない。

**依頼書との差**（実測して分かった分）:

- **flash latencyを一度も書かないfamilyは V20x/V30x だけではない。**
  V407・X315・H417 も書かない。依頼書の指摘#6より範囲が広い
- **EXTENのregister名がfamilyで違う。** L103/V103/V20x/V30xは`EXTEN_CTR`だが
  **V205は`CTLR0`**。C-4を「EXTEN_CTRのbit」と決め打つと V205 で外す
- **1つの設定が2つの事実になる。** V307の144MHzは`#ifdef CH32V30x_D8`で`RCC_PLLMULL18`、
  `#else`で`RCC_PLLMULL18_EXTEN`。同じ×18でも符号化が違う
- **同じ値が分岐で別の意味になる。** CH32V20xの`RCC_RTCCLKSource_*`は
  **値0x300が D8/D8Wでは`HSE/512`、それ以外では`HSE/128`**。分岐を落とすとRTCが4倍ずれる。
  USBの`PLLCLK_Div5`もD8/D8W限定。依頼書のC-7の例（`RCC_USBCLKSource_PLLCLK_Div1/1.5/2/3`）は
  実測では`Div1/Div2/Div3`＋条件付き`Div5`で、`1.5`は定数として存在しない
- **CH32X035はクロック源の選択肢を1つも持たない。** 依頼書の「X035は不要」と整合
- **`system_ch32*.c`のコピーは同一でない。** 例題ごとに配られており、H417は390個中12種類、
  V307は168個中26種類。「最初の1個を読む」と例題固有の設定を主流と誤認する。
  `evt_copies`列（`162/168`など）で区別できるようにした

### R-24 の材料の下見（受領時）

`ArduinoCore-CH32/docs/research/clock-data-request.ja.md`。`SystemInit`をPLL込みに
一般化するために要る事実が全部familyごとに違い、いまはEVTを手で読んで写している、という依頼。
`products.csv`にはflash/sram/GPIO数まであるが、**クロックの表は1つも無い**。

欲しいものはC-1〜C-8: クロックツリーの段構成 / 発振器 / PLL / PLL周辺の非RCCレジスタ /
プリスケーラと各バス上限 / flash latency閾値 / 正確な周波数を要求する周辺の経路 / 出典と確信度。
粒度はfamily。

**材料の下見（実測）**: 依頼が挙げる検証手段——EVTの`system_*.c`の`SetSysClockTo*`は
レジスタ書き込みの列そのもの——は成立する。ただし**関数名の書式が3通り**あり、
段構成は名前そのものが持っている。

| 書式 | family | 例 |
|---|---|---|
| `SetSysClockTo<N>_HSI/HSE` | L103(20) M030(14) V003(6) V006(6) V103(14) V205(24) V20x(26) V307(26) X035(10) | `SetSysClockTo144_HSI` |
| `SetSYSCLK_<sys>MHz_HCLK_<hclk>MHz_HSI/HSE` | V407(10) | `SetSYSCLK_400MHz_HCLK_200MHz_HSE` |
| `SetSYSCLK_<sys>M_CoreCLK_<core>M_HCLK_<hclk>M_HSI/HSE` | X315(8) | `SetSYSCLK_480M_CoreCLK_480M_HCLK_240M_HSI` |
| setter無し | H417 | `SystemAndCoreClockUpdate`だけ。dual-coreで設定箇所が別 |

関数の本体は記号名のまま読める。V20xの144MHz HSIは依頼のC-4/C-5をそのまま裏付ける:

```c
static void SetSysClockTo144_HSI(void) {
    EXTEN->EXTEN_CTR |= EXTEN_PLL_HSI_PRE;   /* C-4: RCC外のPLL制御 */
    RCC->CFGR0 |= (uint32_t)RCC_HPRE_DIV1;   /* C-5: HCLK = SYSCLK */
    RCC->CFGR0 |= (uint32_t)RCC_PPRE2_DIV1;  /* PCLK2 = HCLK */
    RCC->CFGR0 |= (uint32_t)RCC_PPRE1_DIV2;  /* PCLK1 = HCLK/2 -- F_CPUとは違う */
```

つまり**gccは要らず、静的に読むだけ**でC-1/C-3/C-5/C-6の裏取りができる（合計146関数）。
R-19で`extract_remap_fields.py`が果たしたのと同じ「独立検証」の役回りになる。

**未確認**:
- C-2のHSE許容範囲・HSIの確度はEVTには無く、datasheetの電気的特性章側。
  `tables/operating_conditions.csv`が既にクロック上限と動作電圧を持っているので、
  同じ抽出器（`tools/build_operating.py`）の隣に置ける可能性
- ArduinoCore側が「成果物ごと渡せる」と言っているAHBプリスケーラの符号化は、
  EVTヘッダの`RCC_HPRE_DIV*` defineから**機械的に再導出できる（確認済み）**。
  ただし2通りではなく**3通り**だった:

  | 符号化 | 値 | family |
  |---|---|---|
  | linear（全部） | DIV1..8 = 0x00,0x10..0x70 / DIV16,32,64,128,256 = 0xB0..0xF0 | V003 X035 |
  | linear（DIV7止まり） | DIV1..7 = 0x00,0x10..0x60 のみ | **M030** |
  | pow2（DIV32が無い） | DIV1=0x00 / DIV2,4,8,16 = 0x80..0xB0 / DIV64..512 = 0xC0..0xF0 | V103 V20x V307 V407 L103 V205 X315 |

  「`/32`が無い」という依頼側の指摘はpow2群で正しい。M030がDIV8以上を1つも持たないのは
  依頼書に無い差なので、渡す側・受ける側どちらでも要確認
- ch32-dataは`rcc_*.yaml`を9種持っている（`rcc_v003` `rcc_v00x` `rcc_v1` `rcc_v3`
  `rcc_v3_d8c` `rcc_x0` `rcc_l1` `rcc_h4` `rcc_ch641`）。C-3/C-5/C-6のfield符号化は
  ここと突き合わせられる。ただしV205/V407/V467/X305/X315/M030/M103は向こうに無い

## 利用状況（優先順位の根拠）

| # | 誰 | 最初の問い |
|---|---|---|
| U1 | 買ってしまった人 | このピンは何？どう書き込む？Lチカの最短経路は？ |
| U2 | 選定する人 | 要求を満たす型番は？落とし穴は？ |
| U3 | 開発中の人 | この機能はどのピンに出せる？remap値は？例題は？ |
| U4 | 移植する人 | メモリマップ・割り込み番号・機械可読定義は？ |
| U5 | 原典に到達できない人 | 最新版は？いつ同期した？両言語あるか？ |
