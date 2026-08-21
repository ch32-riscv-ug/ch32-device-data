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
| R-24追補 | クロック表の追補（A-1〜A-4）とremapの要確認（B） | ✅ **実装済み**（2026-08-21）。`clock_symbols.csv`・`evt_variants.csv`新設、`operating_conditions.csv`に`typ`列、remapの誤帰属を修正。下記 |

| R-24追補2 | クロック切替に要るレジスタ/ビットとflash latencyの取りこぼし（D-1〜D-4） | ✅ **実装済み**（2026-08-21）。`clock_symbols.csv`を77→429行に拡張、`clock_init.csv`新設、`clock_configs`に`flash_sck_div`列。下記 |

この過程で見つけて手を付けなかった穴は [F. 既知の穴](#f-既知の穴埋める順) に一覧にした。

### R-24追補2（2026-08-21受領・実装済み）

依頼は「PLLの設定値は揃ったので、その設定を**適用する**ために触るレジスタが要る」。
順序は方針なので表に入れない、という境界も依頼書側から示されていた。

| # | 依頼 | 実装 |
|---|---|---|
| D-1 | enable/ready/切替ビットとfieldマスク | `clock_symbols.csv` 77→**429行**（value 222 / mask 173 / poll 34） |
| D-2 | flash latencyの場所（マスク） | 同表に`role=mask`で。**矛盾は4 family**で`confidence=conflict` |
| D-3 | CH32X315のlatencyが落ちている | `flash_sck_div`列を新設。**CH32H417も同じ**だった |
| D-4 | 記号にならないもの（SystemInitのhex、工場トリム） | `clock_init.csv`（101行）新設 |

**D-3で分かったこと**: 原因は正規表現だけではなかった。CH32X315とCH32H417は
**レジスタを直接書かず、ローカル変数へ写して直してから書き戻す**
（`FLASH_Temp = FLASH->ACTLR; FLASH_Temp &= ~FLASH_ACTLR_SCK_CFG; ...`）。
`BLOCK->REGISTER op= value`しか見ていなかったので**中の2行が丸ごと見えていなかった**。
別名を追跡するようにした。そして意味も違う——`SCK_CFG[1:0]`は待ちサイクルではなく
**HCLKの分周比**なので、`flash_latency`に0〜3を入れると「0〜3待ち」と読まれる。
列を分け、`check_tables.py`が両方を持つ行を弾くようにした。
**CH32H417も書いている**（HCLK/2）ので、`tables/README.ja.md`の
「H417は一度も書かない」も誤りだった。

**D-2で分かったこと**: 矛盾はCH32V003だけでなく**V003・V006・V103・X035の4 family**。
いずれも`0x03`（2bit幅）に対しコメントが`LATENCY[2:0]`（3bit幅）。
最初は位置で比べたら`RCC_SWS[1:0]`対マスク`0xC`が全familyで矛盾判定になったが、
これは誤検出——コメントは*フィールド内*のbit番号を書く慣行なので、比べるべきは**幅**。
幅で比べると矛盾はちょうど5件（上の4件＋CH32V407の`RCC_PLLMULL[3:0]`）に落ちた。

**D-1で分かったこと**: 観測だけでは依頼書のリストが埋まらない。`SetSysClockTo*`は
`RCC->CFGR0 |= RCC_HPRE_DIV1`を**クリアせずにOR**している（リセット値に依存）ので、
`RCC_HPRE`/`RCC_PPRE1`/`RCC_PPRE2`/`RCC_ADCPRE`のマスクがソースに現れない。
ヘッダの形から認定する規則（「`_`境界で他の2つ以上の記号の接頭辞、かつ値が連続した
1本のビット列」）を足し、レジスタの位置はbannerコメントから引いた。
出所は`basis`で分かれる（コードが書いた303行 / 定義だけの126行）。

**D-4で分かったこと**: 依頼書の`CFG0_PLL_TRIM`は**CH32V003だけの名前**で、
CH32L103とCH32V205は`HSI_LP_TRIM_BASE`（`0x1FFFF72A`）。3 familyという数は合っている。
CH32V003は`SystemInit`で`0x10`を無条件に書き、工場値が`0xFF`でなければ上書きする——
つまり**未書き込み品では既定値のまま**。L103/V205は低消費HSIの設定関数の中だけで、
常時ではない。`clock_init.csv`は**この repository で唯一 order 列を持つ表**で、
それは`SystemInit`が分岐の無い一直線で順序が転記だから。切替の順序は入れていない。

### R-24追補（2026-08-21受領・実装済み）

依頼は「PLLを実際に書くのに足りない4件（A-1〜A-4）」と「selectorとperipheralの番号
不一致4組（B）」。

| # | 依頼 | 実装 |
|---|---|---|
| A-1 | PLL定数の数値符号化（32記号） | `clock_symbols.csv`（77行）。値・書き込み先register・**絶対アドレス**まで |
| A-2 | `outside_rcc`のアドレスとビット値 | 同表。`EXTEN_PLL_HSI_PRE=16`（bit 4）、V205だけregister名が`CTLR0` |
| A-3 | HSIの公称周波数 | `operating_conditions.csv`に**`typ`列**を追加。指摘のとおり列が無くて落ちていた |
| A-4 | 型番→`CH32V20x_D8`等の対応 | `evt_variants.csv`（56行）。型番×macroで直に結合できる |
| B | selectorとperipheralの番号不一致 | 原因3つ。下記。`check_tables.py`に不変条件を追加 |

**A-1で分かったこと**: 記号名から値は導けないという指摘は、想像より強く成立している。
`RCC_PLLMULL18`=`0x003C0000`と`RCC_PLLMULL18_EXTEN`=`0`だけでなく、
**`RCC_PLLMULL15`=`0x00340000`に対し`_EXTEN`版は`0x00380000`**で、`_EXTEN`の付き方に
一貫した規則がない（×3/×6/×7/×9/×12は同値、×15は別値、×18は0）。

**A-2で分かったこと**: アドレスもfamilyごとに読むしかない。base定数の綴りが
`AHBPERIPH_BASE`と`HBPERIPH_BASE`で揺れ、**CH32X315はEXTENを`0x400220C0`に置く**
（他は`BASE+0x3800`）。`tools/extract_addresses.py`がbase連鎖とstructのメンバー
オフセットを解く。これはR-20（レジスタマップ）の下地にもなる。

**A-3で分かったこと**: 指摘（「typ値＋確度で規定されていて、typ列が無いために基準値が
落ちている」）はそのとおりだった。`HEADER_MAP`は`典型值`/`typ`を既に認識していて、
CSVの列に無いので捨てていた。拾ってみると**HSIは8MHzではなく5通りある**:
8MHz（L103/M103・V103・V20x・V30x）、20MHz（V407/V467・X305/X315）、
24MHz（V00x）、25MHz（H41x）、48MHz（X033/X035）。8MHz決め打ちは5群のうち4群で外す。
低消費モードのHSIも別行（L103/M103とV203/V205は1MHz、V00xは`HSI_LP=1`で30〜58kHz）。
副産物として`F_LSI`もmin/typ/maxが揃い、**CH32V203は`applied for V203RBT6`だけ
25/32/45kHz**（他は25/39/60kHz）——A-4で`CH32V20x_D8`に割り当てた唯一の型番と一致する。
確度の典型値は`±500`のように符号が`±`で書かれるので、数値判定に`±`を足した。

**A-4で分かったこと**: 依頼書の想定（V20xにD8/D8C/D8W）と実際が違う。
**`_D8C`はCH32V30xのmacroで、CH32V20xは`_D6`/`_D8`/`_D8W`**。しかも
`_D8`に該当するのは**CH32V203RBT6の1型番だけ**。`_D6`が既定なので、RBT6に
macroを設定せず組むとHSE_VALUEが24MHzのまま（正しくは32MHz）通ってしまう。
CH32V00x（CH32V002/V004/V005/V006/V007_M007）にも同じ仕組みがあり、こちらは
`condition`列には出てこないが周辺の集合を動かすので同じ表に入れた。

**Bの原因は4つに分かれた**（依頼書は4組を挙げていたが、実際には5クラス24行）:

1. **reference manualのグリッドがページを跨いだところで別の表と合体していた。**
   CH32V407のp108にTIM3の表、p109にTIM4の表がある。TIM4の表はヘッダが2行に
   割れていて空セルを1つ含む（`["復用功能","TIM4_RM=0默認映射","","TIM4_RM=1重映射"]`）。
   `read_header`がその空セルでヘッダ行を却下し、列数が一致したので「前ページの表の続き」
   と判定した。結果TIM4の経路が`TIM3_RM`に、しかも**値1が値3として**入った。
   V103のTIM3、V30xのFSMC_NADV/DVPも同型。空セルを列位置を保ったまま許し、
   ヘッダらしい行は続きと見なさないようにして解決
2. **(pad,値)一致が信号名を上書きしていた。** padは「誰の経路か」を言えないので、
   名前が読めるときは名前に反せない、という制約を入れた。CH32V002の`ADC_IETR`は
   PA2をTIM1と共有しており、V002にADCのselectorが無いためTIM1に付いていた
   （いまは未解決として記録される — 正直な状態）
3. **経路の出所を区別していなかった。** RMのregister説明文は散文を正規表現で読むので、
   field表の行が次のfieldへ流れ込むと関係ないpadを吸い込む。CH32V00xの
   `ADC_ETRGREG_RM`は説明文から**値1で35 pad**（PA0〜PD7のほぼ全部）として出てくるが、
   格子（表7-15）は`PC2`1つだけ。この汚染で`(PA2, 1)`が2候補になり`ADC_IETR`が
   決まらなかった。段3は**格子由来の経路だけで先に引く**ようにした
4. **語彙の穴。** CH32L103のpin表は`LPT_OUT`と書き、AFIOのフィールドは`LPTIM_RM`。
   `LPT`→`LPTIM`を`SAME_PERIPHERAL`に追加。ついでにCH32H417の`UHSIF_PORT33`が
   `UHSIF_CLK_RM`と`UHSIF_PORT_RM`のどちらかを決められず`SDMMC_RM`に落ちていたのを、
   「selector名＋数字」で選べるようにした

**#2の直し方を2回やり直した**（記録として）。最初は「名前が読めるときはpadは名前に
反せない」だけを入れたが、既定経路でも格子の値0を使えるようにしたところ、
**pad一致が名前ベースの段4より先に来て CH32M030の`ISINK1`が`afio-tim2-remap`に
なった**（PA6をTIM2と共有している）。次に条件を「反証されないこと」に緩めたら、
今度は**自分のfieldを持たない周辺で破れた**——CH32V30xの`I2S3_MCK`が
`afio-tim8-remap`になった（`I2S3`という名前のselectorが無いので反証できない）。
結論は「フィルタは積極的一致、順序は名前が読めるかで入れ替える」で、
条件と順序は別の問題だった。

**依頼書が挙げていなかった分**: `UHSIF_PORT33`〜`PORT41`（H417、18行）と
`FSMC_NADV`（V303/V307/V317）。依頼書の検出（selector末尾の番号とperipheral列の番号の
比較）では名前が違うだけの組を拾えない。`check_tables.py`の検査は
「その周辺が自分のselectorを持っているか」または「名前が同じで番号だけ違うか」で
判定するので、両方拾う。**SPI/I2Sの共有は例外指定なしで通る**（CH32V407の`I2S3_WS`は
本当に`SPI3_REMAP`が経路を決めており、`I2S3`という名前のselectorは存在しない）。

**未解決として残るもの**（誤った帰属をやめた結果、正直に穴になった分）:

- **CH32V203の`USART4_*`**。datasheetのpin表は両言語でUSART4のdefaultとremap-1を
  載せているが、**CH32V20xのEVT headerには`AFIO_PCFR2_`の定義が1つも無い**。
  RMがPCFR2を記述しているのでbitは補完できるが、selector自体がheaderに無いので
  生成されない。R-19のF-18と同型の穴で、**PCFR1だけ書いても何も起きない**
- **CH32V30xの`DVP_*`**。V407にはある`DVP_REMAP`がV30xのheaderに無い


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

## F. 既知の穴（埋める順）

R-19・R-24とその追補を実装する過程で見つかったが、依頼の範囲外として手を付けなかったもの。
**資料側の穴**（上流にデータが無い）と**ツール側の穴**（資料にはあるが取れていない）を
分けている。前者は直せないので記録が成果物、後者は直せる。

| # | 穴 | 規模 | 側 | 判断 |
|---|---|---:|---|---|
| F-1 | pin表の電源pin名が添字で分断される | 約850行 | ツール | ✅ **修理済み**（2026-08-21）。F-4も同じ修正で片付いた |
| F-2 | CH32V20xのEVT headerに`AFIO_PCFR2_`が無い | 7 function | 資料 | **方針決定が必要**（下記） |
| F-3 | 中国語版の文章中のpadを拾えない | 未計測 | ツール | 直す。影響範囲を測ってから |
| F-4 | pin表のsignal名が縦書きセルで切れる | 約100行 | ツール | ✅ **ほぼ修理済み**（F-1と同一原因）。残り6行 |
| F-5 | `extract_registers`の見出しrun-on | 未計測 | ツール | R-20のD-2と同時 |
| F-6 | CH32V30xのRM格子がI2S3のremap経路を書いていない | 12 function | 資料 | 記録のみ |
| F-7 | CH32V30xのheaderに`DVP_REMAP`が無い | 2 function | 資料 | 記録のみ |
| F-8 | CH32V003の`AETR`がADC 2 fieldのどちらか決まらない | 1 function | 資料 | 記録のみ |
| F-9 | USBが48MHzを要求する根拠が散文 | — | ツール | R-24のC-7残り |

### F-1 / F-4 pin表のsignal名が改行で分断される（修理済み）

datasheetは電源ピンを`V`＋添字`DD33`のように組んでいて、PDFのテキスト層では
**2つのセルに割れます**。`pad`列は正しいのに`signal`列が壊れます。

```
CH32H415REU6  pad=VDD33   functions = ['DD33', 'DD33', 'DD33', 'Main V', 'V']
CH32H415REU6  pad=VSS     functions = ['SS', 'V']
CH32H416RDU6  pad=VDD12A  functions = ['DD12A', 'V']
```

規模は`signal='V'`が**569行**、断片（`DD`/`SS`/`DDA`/`SSA`/`DDK`/`BAT`/`DD8`…）が
**283行**で、`pin_functions.csv` 29493行の約2.9%。271 padで`V`と断片が同居し、
298 padでは`V`だけが残っている（断片側が別の壊れ方をしている）。

remap経路には影響しません（電源ピンにroute selectorは無い）。**consumerが
「このpadは電源か」を判定するときに効きます。**

**原因は`unwrap`が改行ごとに判断していたことでした。** 実際は**データシートごとに
規約が2種類**あり、セル全体を見ないと決まりません。

| 規約 | family | 改行の意味 |
|---|---|---|
| `/`で区切る | H417・V407・X035・V003・M030など | 改行は**名前の途中**（列幅が尽きた位置で折り返す） |
| 改行で区切る | **V20x・V30x** | 改行が**区切り**そのもの（`/`を一切使わない） |

4 familyで`/`を挿入していた458箇所を全部見たところ、**3箇所を除いて全部が名前の
途中**でした（`V`+`SS`、`SD`+`RAM_D20(AF12)`、`LT`+`DC_G5(AF14)`、`I2`+`C4_SMBA(AF4)`、
`OSC_OU`+`T`、`D`+`VP_VSYNC(AF15)`）。旧既定はV20x/V30xのためのもので、
**改行ごとに判断すると必ず片方の規約を外します**。

各規約の中の例外は根拠を絞りました:

- `/`規約で改行が区切りになるのは、**前の行がAF番号の括弧を閉じているとき**だけ
  （`TIM11_CH3(AF13)` ⏎ `QSPI1_SIO0(AF10)`）
- 改行規約で改行が名前の途中になるのは、**次の行が2文字以下の切れ端のとき**だけ
  （`ETH_MII_PPS_OU` ⏎ `T`）
- **添字は独立した行**なので、末尾が単独の大文字なら常に連結。pin表に1文字のsignalは
  存在しない

あわせて`signals()`も2点直しました。**内部に空白を含むトークンは散文として落とす**
（`Main VDD33`は説明で、隣の列に`VDD33`がある）。先頭の空白は落とさずtrim。
**行を跨いだfootnoteの除去**（`A3(` ⏎ `3)`が`A3(3)`として残っていた13行）。

**結果**（4検査すべて通過、EVTデコーダ261/0とch32-data 203/1は変化なし）:

| 表 | 前 | 後 |
|---|---:|---:|
| `pin_functions.csv` | 29493 | **27850** |
| `remap_fields.csv` | 280 | 277 |
| `remap_routes.csv` | 4635 | 4620 |

`DD`/`SS`/`DDA`/`BAT`/`LTD`/`Main V`/`A3(3)`/`ART10_RTS_3LED0`はすべて0行になり、
`VSS` 69・`OSC_OUT` 44・`VDDK` 17・`VREF+` 16・`VDD33` 10として組み立て直されました。
remapのbit解釈には影響していません（デコーダの一致数が動かなかった）。

**残り6行**（どちらも片方の言語版だけに出る `reference` 行）:

```
CH32H417{M,Q,W}EU6  pad=VDDK  signal=DDK  default   pin-table:zh のみ
CH32V30{3,7}xx      pad=PD8   signal=V    remap-1   pin-table:en のみ
```

### F-2 CH32V20xのEVT headerに`AFIO_PCFR2_`が無い（**方針決定が必要**）

datasheetのpin表は両言語でCH32V203/V208のUSART4を載せており、reference manualも
`AFIO_PCFR2`を記述しています。ところが**`ch32v20x.h`に`AFIO_PCFR2_`の定義が1つも
ありません**（`grep -c` = 0）。route selectorはEVT headerから作る方針なので、
USART4のselectorが生成されず、7 functionが未解決のまま残ります。

- `CH32V203` `USART4_TX`(PA5) `USART4_CK`(PA6) `USART4_CTS`(PA7) `USART4_RTS`(PA15) `USART4_RX`(PB5)
- `CH32V203`/`CH32V208` `UART4_TX`(PB0) `UART4_RX`(PB1)

**PCFR1だけ書いても何も起きない**ので、R-19のF-18と同型の穴です。埋めるには
「selectorはEVT headerから作る」という方針を変える必要があります:

| 選択肢 | 得るもの | 失うもの |
|---|---|---|
| headerのみ（現状） | selectorの存在がSDKのAPIと一致する | datasheetがpinを載せている経路が落ちる |
| header ∪ RM | V203のUSART4が埋まる | RMのfield表の読み取り誤りがselectorを生む（F-5と相互作用） |
| header ∪ RM（`basis`で区別） | 同上＋consumerが選べる | 表の意味が2種類になる |

**これは決めていません。** 3番目が repository の慣行（`confidence`/`basis`で
判断材料を渡す）に最も沿いますが、F-5を先に直さないとRM側の誤りが混入します。

### F-3 中国語版の文章中のpadを拾えない

文章からpadを拾う正規表現が`\bP[A-H]\d{1,2}\b`で、Pythonの`\w`はCJKを含むため
`与PD1相连`の`PD1`の前に語境界が立ちません。中国語版のADC触发表
（`ADC外部触发注入转换与PD1相连`）が0件になります。

いまは英語版が同じ表を"connected to PD1"と書いているので和で埋まっていますが、
**英語版RMが無いCH32V407/V467では埋まりません**（あちらの格子はpadを裸で書くので
現状は影響なし）。前後をASCIIだけで見る形
（`(?<![A-Za-z0-9])P[A-H]\d{1,2}(?![0-9])`）にすれば直りますが、
中国語版の文章由来経路が全familyで増えるので、**増えた分を数えてから**入れる。

### F-4 pin表のsignal名が縦書きセルで切れる

F-1と同じ機構だが電源ピン以外。確認できているもの:

| signal | pad | 本来 | series |
|---|---|---|---|
| `ART10_RTS_3LED0` | PD14 | `USART10_RTS` と `LED0` の混線 | V407/V467 |
| `LTD`（44行） | 各所 | `LTDC_*` | V407/V467 |
| `UHSIF_PORT42_` | — | `UHSIF_PORT42` | H417 |
| `DVP_`, `DV` | — | `DVP_*` | V407/V467 |
| `I2S3_W`, `I2S3_C`, `TIM3_C` | — | `I2S3_WS`, `I2S3_CK`, `TIM3_CH3` | V30x/V407 |
| `MC`+`O`, `T`+`L`, `UT`, `N`, `K`, `S` | — | `MCO`, `TL?`, `UTX`? | V00x/V30x |

`tools/signal_vocabulary.py --tables tables`が語彙規則の当たらないsignalを
series別に出すので、そこが検出器になります（いま最大でV407/V467の7種）。
**短い名前が全部壊れているわけではありません**——`MCO`・`SCL`・`SDA`・`SCK`・`NSS`・
`CS`・`TX1`・`UTX`・`A0`〜`A13`・`HO0`〜`HO3`・`XI`/`XO`・`CC1`/`CC2`は原典どおりです。

### F-6〜F-8 資料側で決まらないもの（記録のみ）

- **CH32V30xの`I2S3_*` remap-1**（`I2S3_WS`/PA4、`I2S3_CK`/PC10、`I2S3_SD`/PC12、
  4 series）。`SPI3_REMAP`が経路を決めるが、V30xのRM格子がその経路を書いていない。
  **CH32V407/V467は書いているので決まる**——同じ周辺が資料の書き方次第で決まったり
  決まらなかったりする
- **CH32V30xの`DVP_*`**。CH32V407にはある`DVP_REMAP`がV30xのheaderに無い
- **CH32V003の`AETR`**（PC2, remap-1）。datasheet独自の略記で、
  `ADC_ETRGINJ`と`ADC_ETRGREG`のどちらか決められない（`AETR2`はpadで決まる）

## 利用状況（優先順位の根拠）

| # | 誰 | 最初の問い |
|---|---|---|
| U1 | 買ってしまった人 | このピンは何？どう書き込む？Lチカの最短経路は？ |
| U2 | 選定する人 | 要求を満たす型番は？落とし穴は？ |
| U3 | 開発中の人 | この機能はどのピンに出せる？remap値は？例題は？ |
| U4 | 移植する人 | メモリマップ・割り込み番号・機械可読定義は？ |
| U5 | 原典に到達できない人 | 最新版は？いつ同期した？両言語あるか？ |
