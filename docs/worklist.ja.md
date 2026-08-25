# 作業リスト

README自動生成の対象は**データシートとEVTを持つ12リポジトリのTOP**と**org TOP（.github）**です。両方とも特殊処理なしの全自動生成を目標にします。根拠は[docs/extraction-survey.ja.md](extraction-survey.ja.md)、データ構造は[tables/README.ja.md](../tables/README.ja.md)。

状態: ✅完了 / 🔜次 / ⬜未着手 / ❓要確認（人の判断待ち）

## 進捗

| 区分 | 完了 | 残り |
|---|---:|---:|
| データ収集 | 9 | 0 |
| README生成 | 3 | 3 |
| 画像 | 0 | 3（保留） |
| 検査・運用 | 4 | 1 |
| consumerからの依頼 | 2 | 1 |
| 既知の穴（F系） | 14 | 4（うち3件は資料側で直せない） |

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
- [x] ✅ **A6 機能フラグ（USB/Ethernet/CAN/PD/DVP…）** — `tables/features.csv`新設（2026-08-23）。比較表からは作れない（下記の調査結果）ので、**機能説明章の節見出し**を採った。節番号は言語に依らないので中英が厳密に対応する
- [x] ✅ **A7 メモリマップ** — `tables/memory_map.csv`新設（2026-08-23）。**DS 1.2章ではなくEVTヘッダーの`*_BASE`から**。相対の連鎖を解く処理は`extract_addresses`が既に持っていた
- [x] ✅ **A8 書き込み方式** — **A6の副産物**（2026-08-23）。`1-wire Serial Debug Interface (SDI)`／`2-wire SDI Serial Debug Interface`が節見出しとして立っているので、`curated/`への手書きは不要だった
- [x] ✅ **A9 割り込みベクタ表** — `tables/interrupts.csv`新設（2026-08-23）。**RM側と書いたのは材料の見落とし**で、EVTヘッダーの`IRQn_Type`列挙が番号・名前・説明を全部持っている。variantで番号が入れ替わるので`#if`の条件を`condition`列に持つ

### A6の調査結果（2026-08-19）

product_attributesからは機能フラグを作れません。datasheetの比較表は**シリーズ内で差がある列しか持たない**ため、シリーズ共通の周辺は列ごと存在しません。

- CH32V307の属性は`adc_tkey / communicationinterfaces / dac_unit / opa_cmp / rng / timer`の6種のみ。USBHSもEthernetも行が無い（実際には両方ある）
- 複数周辺が1セルに同居する（`communicationinterfaces`の値が`4`など、意味が列名に依存）
- **「属性が無い＝その機能が無い」と推論するのは誤り**

## B. README生成

- [x] ✅ **B1 12リポジトリのTOP生成** — Series/Documents/比較表/ピン表/remap/Errata/Diagrams。日次でミラーが取得
- [x] ✅ **B2 org TOPの生成** — 現行はリポジトリ一覧＋横断文書＋toolchain
- [x] ✅ **B3 org TOP「型番から探す」** — **今あるデータだけで作れる**（series.csv: series→family、products.csv: part_number→family）。CH32M007がCH32V006に、CH32M103がCH32L103に、CH32V317がCH32V307に入っている件が検索者に見えるようになる。～~これができれば`curated/readme-extras/CH32V20x.md`（V205分離の手書きNotes）を削除して**特殊処理ゼロ**にできる~～ → **この見通しは誤りだった**（2026-08-24に確認）。詳細は下記
#### B3の後始末は実施しない（2026-08-24に確認）

B3の項に「`curated/readme-extras/CH32V20x.md`を削除して特殊処理ゼロにできる」と
書いていたが、**削除できない**。Notesの2項目はどちらもB3では置き換わらない:

| Notes | B3で置き換わるか |
|---|---|
| CH32V205が独立リポジトリへ移った | **✗** org TOPの型番検索は**org全体を探す人**を助けるが、**すでにCH32V20xのページにいる読者**には届かない |
| 生成前の型番別ページへのリンク | **✗** `README_CH32V203.md`/`README_CH32V208.md`はミラーに**現存**していてリンクが生きている。データからは導けない履歴 |

`extras_section`の仕組みも「表が言えないこと（エラッタ・リポジトリの注記）」の
**正当な逃げ道**で、消すべき欠陥ではない。古いTODOを根拠に手書きの注記を消さない。

**導けるものは1つある。** CH32V20xの`CH32V203CCT6`は`CH32V205DS0.PDF`に載っていて
（`products.csv`の`datasheet`列）、その文書はfamily CH32V205のもの。つまり
**2つのリポジトリの間にデータで見えるリンクがある**ので、「関連リポジトリ」節を
生成することはできる——しかも「なぜ関連するのか」まで言える。ただしこれは
「移った」という履歴の代わりにはならないので、手書きNotesと**併存**する。
節構成の話なのでB4で扱う。

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
- [x] ✅ **D6 読んだ原典の版を記録** — `tables/sources.csv`新設（2026-08-23）。mirror 12本のcommitとその日付。**生成時刻は入れない**（毎回書き換わると「差分が出たら異常」の判定が使えなくなる）。生成物の差分の原因を「入力が変わった」と「再生成を忘れた」に切り分けるため
- [ ] ⬜ **D7 生成のGitHub Actions化** — 日次起動・datasheetかEVTが変わっていたら全生成。**計画のみ**（下記）。抽出の作り込みが落ち着くまでは手動
- [ ] ⬜ **D4 同期日時の表示** — 各READMEに「いつ原典と同期したか」。U5（原典に到達できない人）が最初に確認する情報


### D7 生成のGitHub Actions化（計画のみ・2026-08-23）

**いまは手動のみ。** 抽出の作り込みが続いている間は、生成の主導権を手元に置く。
`candidates/`は**未reviewの機械出力**という位置づけなので、CIが書き戻す形にすると
レビュー前のものが正になってしまう。**落ち着いてから**下記に移す。

#### 前提として済んでいること

| | |
|---|---|
| mirror の更新 | **すでにActions**（各mirrorの`update.yml`が毎日15:07 UTC、WCHから取り直してcommit/push） |
| 目録の更新 | **すでにActions**（`ch32-device-data/update.yml`が毎日13:07 UTC。mirrorより2時間早く回して同じ日の目録を使わせる） |
| `build_all`の冪等性 | **実測済み**。入力とコードが同じなら何度回しても差分ゼロ |
| 読んだ版の記録 | **`tables/sources.csv`**（2026-08-23）。mirror 12本のcommitとその日付 |

手作業として残るのは**ローカルcloneの`git pull`**と**重い抽出**の2つだけ。

#### やること

**日次で起動し、datasheetかEVTが変わっていたら全生成する。**

```
1. mirror 12本を clone/pull（shallow で可。EVTとdatasheetだけあればよい）
2. tables/sources.csv が記録する commit と、いまの mirror の HEAD を比べる
3. どれも同じなら **何もせず終わる**（生成物は最新のはず）
4. 変わっていたら全生成 → 検査 → 差分を報告
```

3が要点で、**入力が動いていないのに差分が出たら「再生成モレ」**、動いていれば
「入力が変わった」。`sources.csv`を入れたのはこの切り分けのため。

#### 全生成の中身と時間

`tables/README.ja.md`の生成順そのまま。実測で`build_all`が**2並列16.6分**、
6並列ならもっと速い（pdfplumberのtext-map LRUを落として1 worker 360MiBになった）。
`build_pins`と`build_operating`と`build_features`がそれぞれ数分。
**全部で30分前後**を見込む。GitHub Actionsの標準runnerで収まる。

#### 決めていない点（着手時に決める）

- **成果物をどう扱うか。** 案は3つ。
  - (a) **差分を報告して落とすだけ**（書き戻さない）。いちばん安全で、
    「再生成モレ」と「入力が変わった」の検出はこれで足りる。**推奨**
  - (b) PRを立てる。人がレビューしてmerge。(a)の次にやるならこれ
  - (c) mainに直接commit。`candidates/`が未reviewである以上、いまは採らない
- **cloneの量。** mirror 12本で**1.8GB**（うち`.git`が約半分。CH32V307単体で
  `.git` 153MB・EVT 103MB）。`--depth 1`かつ`--filter=blob:none`で削れるが、
  PDFとEVTは実体が要るので**1GB弱は落ちる**。runnerのディスクには収まるが、
  毎日1GBを落とす価値があるかは 2 の比較で早期に打ち切れるかによる。
  **比較だけなら`git ls-remote`でHEADが取れるので、変化が無い日はcloneしない**
- **起動時刻。** mirrorの更新が15:07 UTCなので、**16:00 UTC以降**。
  GitHub側の遅延が数時間出ることがあるので、前日ぶんを拾う前提にする
- **手動起動を残すか。** `workflow_dispatch`は残す（変化が無くても回したいときがある）

#### やらないこと

- **`build_all`に自動pullを入れない。** 作業中に入力が変わるのは危険で、
  「いま何を読んでいるか」が分からなくなる。同期は明示的な操作として分ける
- **CIを生成の主導権にしない。** 上記(c)を採らない理由と同じ

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

| R-24追補3 | CH32V103のSTKレジスタほか（E-1〜E-5） | 🔜 **受領**（2026-08-21）。E-4/E-5は実装済み、E-1が最優先。下記 |

この過程で見つけて手を付けなかった穴は [F. 既知の穴](#f-既知の穴埋める順) に一覧にした。

### R-24追補3（2026-08-21受領）

consumer側でPLL対応が実装され、**CH32V20x/V307が8→96MHz、CH32V103が8→72MHz**に
なったという報告つき。実機確認済み（V307VCT6・V203C8T6・V103R8T6）。

**渡したデータが実害を防いだ場面が3つ報告された**（表の設計判断の検証になるので記録）:

1. `RCC_PLLMULL18_EXTEN` が **0**。「PLL値が非0ならPLLを使う」判定を書いていたので、
   D8C(V305/V307/V317)でPLLが黙って無効になるところだった。
   → A-1で「名前から値は導けない」と書いた通りの罠が実際に踏まれかけた
2. PLLフィールドのマスクがfamilyごとに違う（V205は5bit、V407は位置違い、
   V307は`PLL2MUL`/`PLL3MUL`が同居）。決め打ちだと巻き込んで壊していた
   → D-1で「setterは全部read-modify-writeなのでマスクが要る」とした通り
3. **`clock_init.csv`のリセット手順はPLL対応の前提条件だった。**
   PLLONが立っている間`PLLSRC`/`PLLMULL`が書き換え不可なので、リセット手順が無いと
   前のファームが残したPLLがそのまま生き残る。CH32V103での実測:

   ```
   手順なし: RCC->CFGR0 = 0x001D000A  PLLSRC=1(HSE)  ← HSIを書いたのに
   手順あり: RCC->CFGR0 = 0x001C000A  PLLSRC=0(HSI)  ← 意図どおり
   ```

   D-4を「記号にならないので別扱い・後回しで構わない」として受けたが、
   **実際には最優先級だった**。順序を`step`列で持つ判断も含めて正解だった。

| # | 依頼 | 状態 |
|---|---|---|
| E-1 | CH32V103のSTKレジスタ定義（**P0**） | ✅ **クローズ**（2026-08-22）。探されていたレジスタは**存在しない**。`tables/systick.csv`新設＋[register-map-survey](register-map-survey.ja.md#先出し1-systickr-24追補3のe-1)。consumer側は実機で解決済み |
| E-2 | EVTがAPB1を`/2`にする理由（RMにAPB1固有の上限はあるか） | ✅ **クローズ**（2026-08-22）。**RMに上限記述は無い**。表の追加は不要。下記 |
| E-3 | CH32V30xのflash/SRAM構成が可変 | ✅ **実装済み**（2026-08-22）。`tables/memory_configs.csv`新設（67行）。**V20xとV407も可変**だった。下記 |
| E-4 | CH32V003の`RCC_HSITRIM`フィールド位置 | ✅ **実装済み** |
| E-5 | CH32X315の`RCC_HSIRDY`が`clock_symbols.csv`に無い | ✅ **実装済み** |

**E-4/E-5の原因は`clock_symbols`の集め方**だった。`sites`を`SetSysClockTo*`からだけ
集めていたので、**`SystemInit`にしか出ない記号が表に届かなかった**（X315の
`RCC_HSIRDY`）。`RCC_HSITRIM`は兄弟定数（`RCC_HSITRIM_0`等）を持たないので
マスク認定規則（兄弟2つ以上）にも当たらなかった。`SystemInit`の記号も集め、
`trim`ステップの書き込み先フィールドを明示的に足した。`clock_symbols`は429→433行。

**`check_tables.py`に検査を追加**: `clock_init.condition`が呼ぶ記号は
`clock_symbols`にあること。E-5と同型の「存在しない行への参照」を今後は弾く。

#### E-3の実装: `memory_configs.csv`（FLASH/SRAMの境界はoption byteで動く）

**依頼はCH32V30xだけだったが、可変なのは3 family・19 partだった。**
CH32V20xの`_D8`/`_D8W`とCH32V407/V467も同じ仕組みを持つ。

| 適用先 | 符号 | 組合せ | datasheet | EVTの例題 |
|---|---|---|---|---|
| **V203RB・V208×4**（`CH32V20x_D8` / `_D8W`） | `00x` | CODE 128K + RAM 64K | ← | ×14 |
| | `01x` | CODE 144K + RAM 48K | | ×1 |
| | `1xx` | CODE 160K + RAM 32K | | |
| **V303RC・V303VC・V307RC/VC/WC・V317VC/WC**（10 part） | `00x` | CODE 192K + RAM 128K | | ×8 |
| | `01x` | CODE 224K + RAM 96K | | |
| | `10x` | CODE 256K + RAM 64K | ← | ×17 |
| | `110` | CODE 128K + RAM 192K（**批号倒数第六位が0でない品のみ**） | | |
| | `111` | CODE 288K + RAM 32K | | ×2 |
| **V407×3・V467×3** | `0` | CODE 512K + RAM 200K | ← | ×1 |
| | `1` | CODE 576K + RAM 136K | | ×7 |

**「出荷時の組」と書ける1組は無い**（当初そう書いていたが誤り）。RM 32.4.6は
`RAM_CODE_MOD`の復位値を`x`とし、「USERとRDPRTはシステムリセット後に用户选择字
領域から読み込む」と注記する——決めるのはoption byteで、RMはその出荷値を書かない。
**EVTも決めていない**: 例題ごとに違う組をlinkしていて（上表の右端。符号表に載る
組だけ数えた。ほかにIAPやBLEが領域を切り分けた、符号表に無い組が20本ある）、
V407では多数派が比較表と食い違う。

いったん`evt_linker`列を足しかけたが、**`EVT/EXAM/SRC/Ld/Link.ld`だけを見て
「EVTの既定」と読んだのが誤り**だった。1組に決まらないものを1列にすると嘘になる
ので、列は`datasheet_value`（比較表が載せる組）1本だけにし、分布は
`build_memory.py`が実行時のnotesに出す。**可変partのlinker scriptを起こす側は、
決め打たずに自分のscriptに合わせてoption byteを書く。**

書き込み先は**用户选择字のUSERバイト**（`0x1FFFF800`）で、`FLASH_OBR`は
リセット時にそこから読み込まれた値を見せるだけ。列を両方持つ:
`option_byte_bits`（書く側）と`obr_bits`（読む側）。

**zhとenでフィールド幅が食い違う。** 中文版は`RAM_CODE_MOD[2:0]`を`[9:7]`、
English版は`SRAM_CODE_MODE`を`[9:8]`と書く。**組合せが5通りある以上3bit要る**
（2bitでは`110`=128K+192Kと`111`=288K+32Kが同じ値になる）ので中文版が正しく、
EVT headerの

```c
#define  FLASH_OBR_RAM_CODE_MOD  ((uint16_t)0x0300)   /* ch32v30x.h -- 2bit しかない */
#define  FLASH_OBR_RAM_CODE_MOD  ((uint16_t)0x0200)   /* ch32v4x7.h -- RM は bit8 と書く */
```

はどちらも間違い。English版が内部矛盾しているのも根拠になる——`USER`は両版とも
`[7:5]`（3bit）で、`FLASH_OBR`の中でUSERバイトは`[9:2]`を占めるのだから、
`USER[7:5]`は`OBR[9:7]`にしか対応しない。全行を`confidence: conflict`にし、
`basis`にRMとEVTの両方を残した。

**出所は3つで、それぞれ別のことを言う**:

| 出所 | 言うこと |
|---|---|
| reference manual | 符号（どの値がどの組合せか）・適用part・条件 |
| EVTの`Link.ld`のコメント | 組合せの一覧（符号は無い）。RMとの照合に使う |
| EVTのheader | `FLASH_OBR`のマスクと`OB_RAM_CODE_MOD`の値 |

`Link.ld`が独立した第2の読みになるのが効いた。**CH32X315の`Link.ld`だけ嘘を書く**——
`CH32V4x7RM.PDF\Table 32-3`を指して576K/136Kを挙げるが、X315のheaderには
`RAM_CODE_MOD`が無く、datasheetは「480KB闪存包含192KB的零等待程序运行区域和
288KB非零等待区域」と固定で書いている。V407からのコピー忘れ。**X315は可変ではない。**

抽出で引っかかった点を3つ記録する（同型の表を読むときに再発する）:

1. **符号行は行頭に来ない。** CH32V407のRMはフィールド名の折り返しを同じ行に
   混ぜて`RAM_CODE_M 1：CODE-576KB + RAM-136KB`と出す。`^`固定では0件になる
2. **`1xx`の必要ビット幅は3ではなく1。** 桁数で数えるとV20xの`00x/01x/1xx`が
   3bit要ると誤判定し、EVTの2bitマスクを冤罪で`conflict`にする。
   **xでない一番下の桁まで**を数える
3. **適用先を書かない組は「限定が無い」の意味。** V407のRMはフィールドの説明に
   適用partを書かない。書いてある場合（`适用于`/`Applied for`）だけ絞り、
   無ければその manual が扱う family 全体に効くと読む。ページの柱
   （`CH32V407应用手册`）を先に落とさないと、柱の型番を適用先と読んでV467が抜ける

**`products.csv`側の実害も見つかった**（F-14）。V30xの`flash_bytes`は
「Code FLASH 480K」を取っていて、零等待領域（128K/256K）ではなかった。
`memory_configs.csv`の`datasheet_value`行と一致するよう直した。

#### E-2の回答: reference manualにAPB1固有の上限は書かれていない

**結論: `/1`でよい。** `operating_conditions.csv`に足す行は無い。

reference manual **23版すべて**（12 family・zh/en）を走査し、`APB1`/`PCLK1`/`PB1`/
`PPRE1`を含む行と、その前後2行に周波数の上限表現（`不能超过`・`最高`・
`shall not exceed`・`maximum`等）が同居する箇所を探した。**1件も無い。**

「書かれていないから無い」を言うには、**書かれるときはどう書かれるか**が要る。
同じ`RCC_CFGR0`の説明表の中で、隣のフィールドには上限が書いてある:

```
[15:14] ADCPRE[1:0]  ...  注：ADC时钟最高不要超过14MHz。
                          Note: ADC clock shall not exceed 14MHz at most.
[13:11] PPRE2[2:0]   ...  （注なし）
[10:8]  PPRE1[2:0]   ...  （注なし）
[7:4]   HPRE[3:0]    ...  注：当HB时钟来源的预分频系数大于1时，必须开启预取缓冲器。
```

WCHは上限があるフィールドには注を書く。PPRE1とPPRE2にだけ注が無いのは、
**そこに制限が無いから**と読める。`operating_conditions.csv`が既に
`F_PCLK1 max == F_PCLK2 max == F_HCLK max`を全familyで持っているのとも一致する。

つまりEVTの`SetSysClockTo*`が`PPRE1 = DIV2`を書くのは資料上の要求ではない。
STM32では APB1 が 36MHz 上限で、そのコードが移植されて残ったものと考えられる
（同じEVTでもCH32V205とCH32V407は一度も分周しない）。

**この過程で見つかった本物の制限**（APB1とは別物なので混同しないこと）:

| 制限 | 出所 | 表の現状 |
|---|---|---|
| FLASH操作中はFLASHアクセスクロックを60MHz以下に。`FLASH_CTLR[25]`(SCKMOD)が既定で`/2` | V20x/V30x RM 32.1注2 | `clock_configs.flash_sck_div`にある |
| FLASH操作時は主频120MHz以下を強く推奨 | 同上 | 未収録（数値ではなく推奨） |
| PLL出力は72MHzを超えられない（V103） | V103 RM `PLLMULL`の注 | `clock_configs`の組合せが結果的に表現 |
| HBの分周比が1より大きいときはprefetch bufferが必須 | V103 RM `HPRE`の注 | 未収録 |
| ADCクロックは14MHz以下 | 全family `ADCPRE`の注 | `clock_prescalers`に符号化はあるが上限は未収録 |

**E-5の`RCC_HSION`について**: これは表のどの行も参照していない（X315の`SystemInit`
step 0は`set RCC->CTLR 0x1`という**リテラル**で、記号名を使っていない）。
つまり宙ぶらりんの参照ではなく、「リテラルが指すビットの名前が引けない」という別の話。
`clock_init`の行はリテラルであることが本質なので、名前を引くには
クロック関連レジスタのビット定義一式（R-20のD-2の部分集合）が要る。規模を測ってから判断する。

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
| F-2 | CH32V20xのEVT headerに`AFIO_PCFR2_`が無い | 7 function | 資料 | ✅ **実装済み**（2026-08-22）。3案目（`basis`で区別）。下記 |
| F-3 | 中国語版の文章中のpadを拾えない | **増分0** | ツール | ✅ **修理済み**（2026-08-22）。今の資料では表は動かない。下記 |
| F-4 | pin表のsignal名が縦書きセルで切れる | 約100行 | ツール | ✅ **ほぼ修理済み**（F-1と同一原因）。残り6行 |
| F-5 | `extract_registers`の見出しrun-on | 見出し432・field多数 | ツール | ✅ **修理済み**（2026-08-22）。下記 |
| F-6 | CH32V30xのRM格子がI2S3のremap経路を書いていない | 32 function・4 series | 資料 | 記録のみ（実測 2026-08-24） |
| F-7 | CH32V30xのheaderに`DVP_REMAP`が無い | 2 function | 資料 | 記録のみ |
| F-8 | CH32V003の`AETR`がADC 2 fieldのどちらか決まらない | 4 function・4 part | 資料 | 記録のみ（実測 2026-08-24） |
| F-9 | USBが48MHzを要求する根拠が散文 | 22行 | ツール | ✅ **実装済み**（2026-08-22）。48MHzは全familyの話ではなかった。下記 |
| F-10 | CH32V205・CH32X315のRMから経路が0件 | V203CCT6のUSART5-8 | 資料/ツール | ✅ **原因判明**（2026-08-22）。**AFIO remapを持たない世代**だった。下記 |
| F-11 | WCH-Link系ファームウェアの版番号が確定しない | — | 資料 | 🔜 実機で1回突き合わせる |
| F-12 | AF番号で多重化するfamilyの選択レジスタが未収録 | 240行 | ツール | ✅ **実装済み**（2026-08-22）。`tables/pin_alternate.csv`新設。下記 |
| F-13 | pin表のslashが改行で落ちてsignalが連結する | 32種・17 part | ツール | ✅ **修理済み**（2026-08-22）。F-1の副作用。下記 |
| F-14 | `flash_bytes`が零等待領域ではなく総容量を指すfamilyがある | 18 part | ツール | ✅ **修理済み**（V30xは2026-08-22、X305/X315は2026-08-23）。下記 |
| F-15 | 比較表の**行グループ**（左セルが複数行にまたがる）が1行に潰れる | H41x 5 part・480行 | ツール | ✅ **修理済み**（2026-08-22）。`sram_bytes`が896KBのうち128KBだった。下記 |
| F-16 | 脚注の**全角括弧**を剥がしていない | 38 pad・364行 | ツール | ✅ **修理済み**（2026-08-22）。pin表の行が丸ごと落ちていた。下記 |
| F-17 | **ページ境界で切れた行**が丸ごと落ちる | V407/X035 27行 | ツール | ✅ **修理済み**（2026-08-22）。下記 |
| F-18 | lead番号に脚注が付いたまま出る（`int`にできない） | 16行 | ツール | ✅ **修理済み**（2026-08-22）。下記 |
| F-19 | 比較表が**ページ境界**をまたぐと継続ページを読めない | en 141行が欠落・H417 4ラベル | ツール | ✅ **修理済み**（2026-08-24）。下記 |
| F-20 | 行グループ見出しが属性名に混ざる（`Communication interface CAN`） | 全family | ツール | ✅ **実装済み**（2026-08-24）。`group`/`label`を新設。下記 |
| F-21 | `pin_roles`が語彙で覆えない signal 110種 | 1046行（4.4%）→**21種97行（0.4%）** | ツール/資料 | 🔧 大半を解消（2026-08-24）。残りは下記 |
| F-22 | セル内の折り返しで**空白が落ちる**（`Communicationinterfaces`） | 全family | ツール | ✅ **修理済み**（2026-08-24）。下記 |
| F-23 | READMEの比較表の**行の並びが資料の並びでない** | 全family | ツール | ✅ **修理済み**（2026-08-24）。`order`列を新設。下記 |
| F-24 | **lead番号のセルが縦結合された行**を落としている（同じ足に2つのpad） | 42行 → 8行 | ツール | ✅ **修理済み**（2026-08-25）。下記 |
| F-25 | pad名が**8文字を超えると落ちる**（`PC13-TAMPER-RTC`） | 103型番中99がPC13を持たなかった | ツール | ✅ **修理済み**（2026-08-24）。下記 |
| F-26 | 同じpadの**封装別の行**を「ページの続き」と誤認 | CH32X035 PC3 | ツール | ✅ **修理済み**（2026-08-24）。下記 |
| F-27 | CH32V103のTIM3 remap値が**RMと食い違う**（pin表の接尾辞が誤り） | 18行 | 資料/ツール | ✅ **修理済み**（2026-08-25）。下記 |
| F-28 | **CH32L103のremap格子を1行も読めていない** | 0 → 195経路 | ツール | ✅ **修理済み**（2026-08-25）。下記 |
| F-29 | pin type欄が`USB3.0`だと落ちる | H417のUSB3.0差動4 pad×4型番 | ツール | ✅ **修理済み**（2026-08-25）。下記 |
| F-30 | 語彙が**1文字の周辺**を作る（`Q_DET1`→周辺`Q`） | 12行 | ツール | ✅ **修理済み**（2026-08-25）。下記 |
| F-31 | **封装のlead数とpins.csvが合わない型番が12** | 最大6 lead | ツール/資料 | 🔜 下記 |
| F-32 | 添字の**2つの名前が1セルに入る**（`V`＋`DD_` と `V`＋`IO_1`） | CH32V205 の 3 pad | ツール | 🔜 下記 |
| R-25 | consumerからの表の追加依頼3件（2026-08-25受領） | — | 依頼 | 🔧 2件実装・1件は設計を返す。下記 |

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

**3番目で実装しました**（consumerからも「`basis`で区別する案が一番ありがたい」との
回答）。ただし**単純な「header ∪ RM」は成立しません**。実測でそれが出ました。

### 実測: RMだけが持つAFIO fieldは294種あり、54種が「参照されるが偽物」

12 familyで、headerに無くRMにあるAFIO/EXTEND fieldを全部数え、
`pin_functions.csv`のsignalと突き合わせた。

| 群 | 件数 | 中身 |
|---|---:|---|
| **A** 参照あり・**経路あり** | 6 | CH32V20xの`USART4`〜`USART8`と`ETH` |
| **B** 参照あり・経路なし | **54** | H417の`TIM1_CH1`〜`TIM9_CH3`（`AFIO_EXTICR2`へ誤帰属したDMAトリガ）41件、`ADC1_SMP_SELx`、X035の`*_FILT_EN`/`UDM_*`、`VDDIO_IO_HSLV`、V003の`TIM1_IREMAP` |
| **C** 参照なし | 234 | DMAのフィールド（`EN`・`TCIE`・`PINC`…） |

**「pin経路から参照されたselectorだけ残す」という既存の篩では足りない。** B群は
fieldの名前が`TIM1_CH1`のように本物のsignal名と一致するので、54種が素通りする。
これはF-5（`extract_registers`の見出しrun-on）が生む誤りで、`AFIO_EXTICR2`は
外部割込み設定レジスタなのにDMAのトリガmultiplexerのフィールドが載る。

### 採った条件は2段

> RM由来selectorを認めるのは、**(a) RMがそのfieldにpad経路を述べていて、
> (b) その経路が名乗るsignalのうち少なくとも1つが、その部品のpin表にもある**とき

(a)だけでB群54種が全滅する（DMAトリガにpadは無い）。(b)が要るのは**`ETH`のため**。
CH32V20xのheaderに`AFIO_PCFR1_ETH_REMAP`は無く、あるのは`EXTEN_ETH_10M_EN`
（既存の`extend-eth-10m-en`）。V203/V208のETH信号は`ETH_RXP`/`RXN`/`TXP`/`TXN`の
4本だけ（固定パッドの10M PHY）なのに、共有RM（`CH32FV2x_V3xRM.PDF`）の`ETH_RM`は
V30xのMII/RMII用で`ETH_MDIO`・`ETH_TXD0`等を名乗る。**共有RMがV3xの記述をV2xへ
持ち込む**という、まさに懸念していた形が実在した。

### 結果: 7 selector

```
CH32V203 afio-tim5ch4-rm   PCFR1:16          CH32V303 afio-tim5ch4-rm  PCFR1:16
CH32V203 afio-usart4-rm    PCFR2:16;PCFR2:17 CH32V305 afio-tim5ch4-rm  PCFR1:16
CH32V208 afio-usart4-rm    PCFR2:16;PCFR2:17 CH32V307 afio-tim5ch4-rm  PCFR1:16
                                             CH32V317 afio-tim5ch4-rm  PCFR1:16
```

狙いの`USART4`に加えて**`TIM5CH4_RM`**（TIM5_CH4をLSIへ切り替えるfield）も出た。
V30xのheaderがこれを定義していない。`basis`で区別する:

```
candidates(rm-register-table+rm-remap-grid:en)              ← headerに定義が無い
candidates(evt-header+rm-register-table+rm-remap-grid:en)   ← 従来
```

`remap_fields` 277→**284**、`remap_routes` 4620→**4643**。4検査すべて通過。

**`USART5`〜`USART8`は入らなかった。** 該当ピンを持つのは`CH32V203CCT6`だけで、
その型番は**CH32V205 familyから作られる**ため——そしてCH32V205のRMからは経路が
1件も取れていない（F-10）。

### F-3 中国語版の文章中のpadを拾えない

文章からpadを拾う正規表現が`\bP[A-H]\d{1,2}\b`で、Pythonの`\w`はCJKを含むため
`与PD1相连`の`PD1`の前に語境界が立ちません。中国語版のADC触发表
（`ADC外部触发注入转换与PD1相连`）が0件になります。

いまは英語版が同じ表を"connected to PD1"と書いているので和で埋まっていますが、
**英語版RMが無いCH32V407/V467では埋まりません**（あちらの格子はpadを裸で書くので
現状は影響なし）。

**直しました**（2026-08-22）。前後をASCIIだけで見る形にすれば、CJKが隣でも取れて、
`PA1`が`PA12`の中で当たらないことは保てます:

```python
PAD_IN_PROSE = re.compile(r"(?<![0-9A-Za-z_])P[A-H]\d{1,2}(?![0-9A-Za-z_])")
```

`\b`はASCIIについては「前後が`\w`でない」と同じなので、**旧の挙動をそのまま含み、
CJKが隣のときだけ増えます**。

**増えた分は0行でした。** 全102 SKUを再生成して候補JSONを1件ずつ比較し、差分なし。
上の予測どおりで、いま持っている資料では

- 英語版があるfamilyは、和を取っているので既に埋まっている
- 英語版が無いCH32V407/V467は、格子がpadを裸で書いていてそもそも散文でない

**表は動きませんが、直しは残します。** 中国語版だけを読んだときに結果が変わる
という言語依存が消えるためで、資料が改版されて散文が増えたときに効きます。

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

### F-10 CH32V205とCH32X315のRMから経路が1件も取れない（原因判明）

`extract_remap`の格子も`extract_registers.routes_in`の説明文も、この2 familyでは
**0件**を返す（他familyは7〜23種）。抽出の不具合ではなく、**この世代はAFIO remapを
持たない**。CH32V205のEVT headerを読むと`AFIO_PCFR1`に残っているのは3つだけで、
代わりに**ピンごとのAF番号レジスタ**が並ぶ:

```c
typedef struct {                     /* ch32v205.h */
    __IO uint32_t ECR;
    __IO uint32_t PCFR1;             /* PD01_RM / SW_CFG / TIM1_CAP_RM の3つだけ */
    __IO uint32_t EXTICR[4];
    __IO uint32_t CR;
    __IO uint32_t RESERVED;
    __IO uint32_t GPIOA_AFLR;        /* ← 経路はこちらで選ぶ */
    __IO uint32_t GPIOA_AFHR;
    ...  GPIOE_AFHR まで
} AFIO_TypeDef;
```

`GPIOx_AFLR`/`AFHR`を持つのは**CH32V205・CH32X315・CH32H417の3 family**で、
これは`remap_routes.csv`が薄い family とちょうど一致する（V205=0行、X315=1行、
H417=151行）。逆に`AFLR`を持たない9 familyはすべて72〜445行ある。
つまり2つの世代が混ざっていて、**同じ「経路」の概念が別のレジスタで実現されている**。

この3 familyの経路は`pin_functions.csv`に`route = af-N`として入っている（4412行）。
消えているのではなく、**`af-N`のNをどこに書くかを表が言っていない**のが穴で、
それを F-12 に分けた。

**consumer側の症状**: CH32V205のPWMが全滅する。`remap-N`しか見ていないと
`af-N`の行が読み飛ばされる。CH32V203CCT6（この型番だけ`USART5`〜`USART8`の
ピンを持ち、CH32V205 familyから作られる）も同じ理由でselectorが付かない。

### F-12 AF番号で多重化するfamilyの選択レジスタ（実装済み）

F-10の続き。`pin_functions.route = af-N`が4412行あるのに、**Nの書き込み先が
どの表にも無かった**。`tables/pin_alternate.csv`（240行 = 3 family × port × 16 pin）
を新設した（`tools/build_pin_alternate.py`）。

`remap_fields.csv`の列に載せることも考えたが分けた。あちらのselectorは
**周辺機器ごと**（`afio-tim2-remap`）で、こちらは**ピンごと**なので、
同じ表に混ぜるとどちらの意味で読むのかが行を見ても決まらない。
`pin_functions.pad`と直接結合できる形（`family` + `pad`）にした。

規則は決め打ちしていない。EVTの`GPIO_PinAFConfig()`が

```c
    if(GPIO_PinSource >= 0x08) tmp = GPIO_PinSource - 0x08; else tmp = GPIO_PinSource;
    AFIO->GPIOA_AFHR &= ~(0xF << (tmp << 2));
```

と書いているので、マスク`0xF`から幅4bit、`<< 2`から刻み4bit、`>= 0x08`から
上下の境界を読む。**ポート分だけ同じ形が並ぶので、全部が同じことを言っている
ことを確かめてから採る**（1つでも違えばポートによって幅が違うという意味になり、
決め打ちでは書けない）。

番地は`extract_addresses`が構造体のメンバーオフセットから解く。**familyごとに
違う**——CH32H417のAFIOは`PCFR1`の直後にAF registerが並ぶので`GPIOA_AFLR`が
`0x40010004`、V205とX315は`ECR`/`EXTICR`/`CR`が前にあるので`0x40010020`から。
**同じ番地がfamilyによって別のregisterを指す**（CH32H417の`GPIOD_AFHR`と
CH32V205の`GPIOA_AFLR`がどちらも`0x40010020`）。

`check_tables.py`に**`af-N`の行すべてについて書き込み先の存在**を見る検査を
足した。経路の情報が行き止まりになるのを弾く。

### F-13 pin表のslashが改行で落ちてsignalが連結する（修理済み）

F-1（改行で分断されたsignal名を繋ぐ）の副作用。**繋ぎすぎた。**

datasheetのセルには2つの区切り方が混ざっていて、CH32V407のPB5はその両方を
1セルの中でやる:

```
USART5_CK/          ← 改行の前に "/" がある = 区切り
I2C_SMBA/SPI3_      ← 改行の前が "_" = 名前の途中
MOSI                ← ここが問題。"/" が無いのに区切り
I2S3_SD/LTDC_V      ← 改行の前が単独の大文字 = 添字（LTDC_VSYNC）
SYNC
```

`MOSI`と`I2S3_SD`の境目には手がかりが**1つも無い**。F-1では「slashのあるセルでは
裸の改行は区切りでない」と決めたので、`SPI3_MOSII2S3_SD`という存在しないsignalが
できた。同型が**32種・17 part**（M030・V007・V208・V407・V467）。

**手がかりは同じ表の他のセルにある。** `/`で囲まれて改行を含まないセグメントは
1つのsignalそのものなので、そこから**その表が使う周辺機器名の語彙**を集められる。
次の行が`I2S3_`で始まるなら`I2S`は語彙にあるから区切り、`RAM_D20(AF12)`で
始まっても`RAM`は語彙に無いから継続（CH32H417の`SDRAM_D20`の後半）。
インスタンス番号は落として比較する——表が`I2S2_CK`を明示していても
`I2S3_SD`は改行の後にしか出ないことがあるため。

1文字の語幹は除く。除かないとCH32V407の`LTDC_R2`が`LTD`/`C_R2`に割れたときに
`C_R2`をsignalと読んでしまう。

**結果**（2026-08-22の再生成）:

| | 前 | 後 |
|---|---:|---:|
| 連結名 | 32種 | **0種** |
| `pin_functions.csv` | 27850 | 27982 |
| `remap_routes.csv` | 4643 | 4672（削除27・追加56） |
| `remap_fields.csv` | 284 | 285（`CH32V208 afio-tim5ch4-rm`が復活） |
| EVTデコーダとの一致 | 261 / 不一致0 | **263 / 不一致0** |
| ch32-dataとの一致 | 203 / 不一致1 | **211 / 不一致1**（既知のCH32V103 USART1のみ） |

`CH32V208 afio-tim5ch4-rm`は`TIM5_CH4`が`TIM5_CH4ADC_IN3`に潰れていて
pin表から消えていたため、F-2の「経路が参照するselectorだけ載せる」条件に
当たらず落ちていた。他5シリーズ（V203/V303/V305/V307/V317）には元からあり、
`AFIO_PCFR1_TIM5CH4_IREMAP`=0x00010000（bit16）と一致する。

**残留を機械的に確認した。** 全27982行のsignal名について「内側に、同じdatasheetが
先頭語幹として使う周辺機器名を含むもの」を数えて**0件**。

**続き（2026-08-22の追い込み）。** 上の「残留0件」は、語幹（`I2S3_`のように
`_`を持つ接頭辞）を含む連結だけを数えていた。数え方を「同じdatasheetが綴る
**名前そのもの**を内側に含むもの」まで広げると、**改行が1つも無いのに2つ以上の
名前が詰まっているセル**が残っていた。

```
CH32V407 PD14 の remap 列（en p.28、生のセル）
    TIM4_CH3_1/
    USART10_RTS_2US        ← 改行が名前の途中に落ちている（繋ぐのが正しい）
    ART10_RTS_3LED0        ← 繋ぐと3つ分の長さになる
    _1/
    FSMC_D0_1
```

datasheetが`/`を打ち忘れていて、**版面には手がかりが1つも残っていない**。
繋いだあとの名前を、表が綴る語彙で切り直す（`extract_pins.resplit`）。
切るのは**左側がすでに完全な名前**（`_`を持ち、切れ目の直前の文字が左側のもの）で、
かつ**右側が語彙にある周辺機器名で始まるか、語彙にある名前そのもの**のときだけ。
左側の条件が、CH32H417の`HSADC_IN0`・CH32V205の`QSPI_SCK`・CH32L103の`LPTIM_CH1`を
割らずに残す（`HS`・`Q`・`LP`は名前ではないので、そこから`ADC_IN0`は始まらない）。

語彙の作り方で3回間違えた。記録しておく:

1. **`/`で囲まれた改行なしのセグメントだけでは足りない。** 列が狭くて
   ほとんどのセルが折り返すので、そこに現れない名前が多い。**1回目のパスの
   出力そのものを語彙にする**（周辺機器名だけで改行を解いた結果は、
   切り直したい名前を既に正しく読めている）
2. **1回目のパスが壊れていると語彙が汚れる。** CH32V30xの`ETH_MII_RX_DV_1`が
   `ETH_MII_RX_D`/`V_1`に割れて語彙に入り、それで`ETH_RMII_CRS_DV_1`を
   `ETH_RMII_CRS_D`/`V_1`に切ってしまった。原因は改行が区切りになる版の
   継続判定が「2文字以下」だったこと——**切れ端は経路の添字を連れてくる**
   （`V_1`）。`^[A-Z0-9]{1,2}(_\d+)?$`に広げて、`V`というsignalも消えた
3. **語彙はdatasheet単位。** 番号表でしか綴られない名前と説明表でしか
   綴られない名前がある。また照合時は**経路の添字を外して**比べる
   （`LED0_1`と語彙の`LED0`）


#### pin抽出のまとめ（F-13続き・F-16・F-17・F-18を通した後）

4つは別の穴だが、**直すと同じところに効く**ので通しの数字を1つ置く。基準は
`git show HEAD:tables/`（この日の作業前）:

| | 前 | 後 |
|---|---:|---:|
| `pins.csv` | 4319 | **4342**（38 pad回復・脚注で壊れていた16行を修正） |
| `pin_functions.csv` | 27850 | **27926** |
| うち`confirmed` | 24572 | **27719** |
| うち`reference` | 3410 | **207** |
| signal名の種類 | 1239 | **1154**（偽名85種が消えた） |
| `remap_routes.csv` | 4643 | **4900** |
| candidates の解決済み経路 | 14382 | **15004** |
| EVTデコーダとの一致 | 261 / 不一致0 | **263 / 不一致0** |
| ch32-dataとの一致 | 203 / 不一致1 | **211 / 不一致1**（既知のCH32V103 USART1のみ） |

**`reference`が3410→207に落ちたのがいちばん効いた。** 全角括弧の脚注（F-16）で
両言語版の綴りが割れていたぶんが揃い、**同じ事実を2つの言語版が裏書きしている**
状態になった行が3000以上ある。行数の増減より、この確度の変化のほうが大きい。

`check_tables.py`は全参照が結合可能。`pins.csv`の`pin`列で数字でない値は
`EP`（露出パッド）45行だけ。

### F-16 脚注の全角括弧を剥がしていなかった（修理済み）

**`extract_pins.py`の脚注regexが半角だけを見ていた。**

```python
FOOTNOTE = re.compile(r"\(\d+\)")      # 旧
FOOTNOTE = re.compile(r"[（(]\d+[)）]")  # 新
```

中文版は全角で`（7）`と打つ。同じ規約を`build_operating.py`は最初から
全角で見ていた（動作条件表の脚注）ので、**知識はあったのに別のツールへ
渡っていなかった**という形の穴。実害は2種類:

1. **pad名が正規化に通らず、行ごと落ちる。** `PA5（4）`は`PAD.match`に当たらないので
   pin表の行として認識されない。**CH32V30xで38 pad**（PA5×12・PC9×10・PB2×4・
   PD15/PD14/PD1/PD0/PB6×2・PD5/PD4×1）が`pins.csv`から丸ごと欠けていた
2. **signal名に括弧が残る。** `SDIO_D0（7）`・`PD0（4）`・`SPI3_MOSI（12）`・
   `I2S3_MCK（11）（12）`など**46種・364行**（`git show HEAD:tables/pin_functions.csv`基準）。
   両言語版で綴りが違うので`confirmed`にも上がらなかった

AF番号の`ALTERNATE`（`TIM8_CH1(AF0)`→`route=af-0`）と、`unwrap`の括弧の
釣り合い判定も同じ理由で半角だけを見ていたので合わせて直した
（`LTDC_HSYNC（AF15）`は経路に化けず名前に残っていた）。

### F-17 ページ境界で切れた行が丸ごと落ちる（修理済み）

pin表の行がページをまたぐと、**pad列とpin type列は上のページに残り、
下のページには幅の広いsignal列だけが来る**。行の判別はpad列でしているので、
この継続行は「padが読めない行」として捨てられていた。

CH32V407のPB7（en版 p.31→p.32）:

```
p.31 の最終行  PB7 | I/O | - | PB7 | TIM4_CH2/I2C_S      | TIM8_CH2_1/
p.32 の先頭行   -  |  -  | - |  -  | DA/USBHS2_DP/FSM    | USART1_RX_1/
                                     C_NADV                USART7_RTS_2/
                                                           FSMC_NADV_1
```

`I2C_SDA`が`I2C_S`になり、`USBHS2_DP`・`FSMC_NADV`・`USART1_RX_1`・
`USART7_RTS_2`・`FSMC_NADV_1`が消える。**pad列とtype列が空で、signal列に
文字がある行**を上の行の続きとして繋ぐようにした。

「pad列が空」は継続行の必要条件でしかなく、**同じ形のものが2つある**。
両方とも実際に踏んで直した:

1. **繋ぐのはsignal列だけ。** 最初は全列を繋いだので、pin番号列に残った数字が
   上の行の番号に積み上がって`5\n17`のような番号ができ、`pins.csv`が15%増えた
2. **ページ頭で刷り直される列見出しも「pad列が空」になる。** `Main function
   (after reset)`が折り返した`function`・`reset)`がsignalとして入った
   （CH32H417で98行）。signal名は**小文字が3つ以上続かず、CJKも含まない**ので、
   それを継続行の条件に足して弾く

`I2C_S`・`USAR`・`DVP_`（CH32V407/V467）と`A`（CH32X035）の27行、および
CH32H417の`UHSIF_PORT42_`が消え、落ちていた経路が入る。

### F-18 lead番号に脚注が付いたまま出る（修理済み）

**`pins.csv`の`pin`列が`int`にできない値を持っていた。** pad列は脚注を剥がして
いたのに（`normalise_pad`）、**番号列は生のまま**だった。

```
CH32V203K8T6  BOOT0  '31(\n6)'     ← 脚注の中に改行が落ちた
CH32V407RET6  PB6    '59(1\n2)'
CH32V407RET6  PB7    '60(1'        ← 閉じ括弧すらページの向こう
CH32V208GBU6  BOOT0  '26(5)'
```

**16行**（CH32V203DS0・CH32V208DS0・CH32V407DS0）。閉じ括弧が残らない形があるので
括弧を剥がすだけでは足りず、**頭の数だけを採る**（`normalise_number`）。
数で始まらないセルはそのまま返す——`EP`（露出パッド）は45行ある本物の値で、
番号ではない。

同じpadに`31(\n6)`と`31(6)`の2行があった型番は1行に畳まれる。

### F-11 WCH-Link系ファームウェアの版番号（[link-firmware-survey](link-firmware-survey.ja.md)）

`tables/link_firmware.csv`（10行）と`tools/build_link_firmware.py`を作り、
ファイルの同定・sha256・取得の自動化まではできた。**版番号だけが確定していない。**

配布物が名乗る版（`wchlink.wcfg`の`CH32V307Ver=42`等）と、実機がUSBで申告する版
（`2.12`のような`major.minor`）の対応が取れない。バイナリに応答テンプレートは
入っておらず、配布ページはJS生成で版情報を持たない。**この対応が付くまで
「あなたのは古い」を言う表としては使えない。**

次に試すのは実機での1回の突き合わせ（更新前後で`minichlink`の表示を控える）。
詳細と他の案は調査ドキュメントに書いた。

### F-14 `flash_bytes`が零等待領域ではなく総容量を指すfamilyがある

E-3を調べる過程で見つけた。**linker scriptを`flash_bytes`から作ると壊れる。**

CH32V303/305/307の datasheet は列を2つ持つ:

```
Code FLASH（字节） 480K     die 上の program flash 全体
Flash（字节）      256K(1)  零等待で実行できる領域 R_0WAIT
```

`flash_bytes`は長い綴りが勝つ規則（`gpioportnumber`が`gpio`に食われないための規則）
のせいで**前者**を取っていた。`FLASH (rx) : ORIGIN = 0x00000000, LENGTH = 480K`を
書くとEVTが256Kと書いている領域を4倍に見積もる。

**修理**: 同じ表に同じフィールドへ寄る列が2つあるときは、**より具体的な綴りを
promote**し、負けた側は`product_attributes.csv`へ落とす（消さない——480Kも事実）。
V303CB/RBは128K、V307VCは256Kになり、datasheetの`Flash（字节）`列と
`memory_configs.csv`の`datasheet_value`に一致する（14 part・`code_flash_bytes`が
`product_attributes.csv`に増える）。

**ただしこれで`flash_bytes`がlinker scriptの正解になったわけではない。**
可変partでは組自体がoption byteで動き、EVTの例題も1組に揃っていない（E-3）。
可変partのlinker scriptは`memory_configs.csv`を見る。

**残っていたCH32X305/X315も直した（2026-08-23）。** 列が1つ（480K）しかなく、
分割は脚注の散文にある:

```
注：1.480KB闪存包含192KB的零等待程序运行区域和288KB非零等待区域。
Note: 1. The 480KB flash memory contains 192KB of zero-wait program execution
      area and 288KB of non-zero-wait area.
```

**脚注番号と値を対応付ける機構は要らなかった。** 文が総量と零等待量の両方を
書いているので、`extract_products`が文を読んで
`零等待Code FLASH（字节） = 192K`という**属性として注ぎ足す**だけでよい。
あとは上の「具体的な綴りをpromoteし、負けた側は属性へ落とす」規則にそのまま乗る
（480Kは`code_flash_bytes`として残る）。

1つ罠がある。**「零等待」は「非零等待」の内側にある**ので、
`CANONICAL_ORDER`が長さ降順に並べる規律に頼って**長い非零等待側を先に当てる**
必要がある。そうしないとCH32H41xの列（`非零等待Code FLASH`）が零等待と読まれる。

**結果**: X305RCT6・X315×3の`flash_bytes`が491520→**196608**（192K）。
EVTの`.ld`は7本すべて192Kを基準にしている（IAP版の172K・32Kもその内訳）ので、
480Kをlinker scriptに書くものは1本も無い。他familyの値と確度は動いていない。

**CH32H41xは当てはまらない**（確認済み）。比較表の列がそもそも
「非零等待Code FLASH 960KB」/「Nonzero wait Code FLASH」と名乗っていて、
**零等待で走るFLASHが無い**——零等待のコード領域はSRAM側にある:

```
内置総容量 896K 字節の SRAM ... 128KBのITCM内核1紧耦合零等待代码区、
256KBのDTCM内核1紧耦合零等待数据区、剩余的512KB共享代码和数据区
```

つまりH41xでは「FLASHに置いてwait付きで走らせる」か「ITCM/共有領域へ写して
零等待で走らせる」かの選択で、`flash_bytes`=960Kという表記自体は正しい。
ただし**`DBMODE`で960K/480Kが切り替わる**という別の可変性があり
（`DBMODE=1`で960K、`0`で480K）、512KB共有領域もコード/データの割り振りが
可変。`memory_configs.csv`に入れるべき候補だが、`DBMODE`の在り処を
まだ調べていないので今回は入れていない。

### F-15 比較表の行グループが1行に潰れる

F-14を確認しているときに見つけた。**CH32H41xの`sram_bytes`が896KBのうち128KBだけ
になっている。**

datasheetの比較表は左端のセルが複数行にまたがる「行グループ」を使う:

```
              内核1高速ITCM        128KB
SRAM          内核1高速DTCM        256KB     ← 合計 896KB
              共享代码和数据区      512KB
定            高级（16位）          2
时            通用（16位）          4         ← Timer は 2/4/4/2/2 の5種
器            通用（32位）          4
```

`extract_products`はグループの見出しと最初の子行だけを読み、**残りの子行を
落とす**。candidatesを見ると`'SRAM': '128KB'`、`'Timer': '2'`しか無い。

影響を受けるのはH41x（`SRAM`・`定时器`・`ADC/TKey`の通道数）。他familyの比較表は
行グループを使っていないので、いまのところこの5 partだけ。

**修理した（2026-08-22）。** 直しは3段になった。

**1. 見出しは1列とは限らない。** `extract_products.read_column_layout`は
`row[0]`だけを見出しと読み、空なら行ごと捨てていた。**型番の列より左は全部
見出し**で、H417の比較表はそこを2段に使う。段ごとに値を持ち越し、
**上の段が変わったら下の段を無効にする**（そうしないと見出しが1段だけの
`GPIO端口数`に前のグループの子見出しが付いて回る）。
`product_attributes.csv`は1009→1513行。

**2. 分割された容量は足す。** H41xのdatasheetは合計を表に書かない。
本文が「内置総容量896K字節のSRAM」と書いていて128+256+512と一致するので、
**足し算は資料に裏書きされている**。足す条件は狭く取った——`*_bytes`の
フィールドに寄るラベルが2つ以上あり、**先頭語が全部同じ**（＝同じグループの子）で、
全部がサイズとして読めるとき。CH32V30xの`Code FLASH`と`Flash`は先頭語から違うので
足されない。`定时器`のような数の group は`看门狗: WWDG+IWDG`がサイズにならないので
当たらない。足して得た値はどの1行のものでもないので、**子行は全部
`product_attributes.csv`に残す**（F-14で480Kを残したのと同じ）。

**3. 子行を出したら、隠れていた誤マッチが表に出た。**

| ラベル | 誤って当たっていた先 | 理由 |
|---|---|---|
| `FMC SDRAM`（コントローラ数=1） | `sram_bytes` | squashが空白を落として`fmc`+`sdram` |
| `programmable current sink module` | `sram_bytes` | `prog`+`ram`+`mable` |

`squash()`が空白を落とすので**単語の途中から別の単語が読み出せる**のが根本。
ASCIIのキーワードは「前が英字でない位置」でしか当たらないようにした
（`spelt_in`）。CJKは空白を使わないので従来どおり部分一致——あちらのキーワードは
ラベル丸ごとなので必要ない。`Code FLASH`→`codeflash`のような**空白をまたぐ
正しい一致は保たれる**。

`programmable current sink`の誤マッチは**以前から存在していた**（列の並び順で
たまたま`sram_bytes`を取られずに済んでいた）。

**結果**: H41x 5 partの`sram_bytes`が131072→**917504**（896KB）。ITCM/DTCM/共有領域の
3行は`product_attributes.csv`に`confirmed`で残る（両言語版が同じ分割を書いている）。
**`products.csv`の確度は1件も動いていない**——`sram_bytes`以外の値も動いていない。

途中で1回、自分で回帰を作った。`spelt_in`の境界を「squash後の文字列で前が英字か」で
見たので、`Non-zero wait Code FLASH`が落ちて11 partの`flash_bytes`が
`confirmed`→`reference`になった。**squashは空白をまたぐ一致を成立させるための
仕組み**なので、境界はsquashする時点で記録しないと壊れる。中文は英字と地続きに
書く（`非零等待Code FLASH`）ので、**字種が変わる位置も語の切れ目**として扱う。
F系の修理では確度の差分も毎回見ること。

翻訳辞書は**部品ごとに引く**ようにした（`通信接口 CAN`→`Communication
interfaces CAN`）。行グループの組合せを全部辞書に書くのは現実的でない。

### F-9 USBが48MHzを要求する根拠（文は特定済み）

`clock_sources.csv`は分周の選択肢（`PLLCLK_Div1`/`Div1_5`/`Div2`…）を持つが、
**どれを選べばよいかを決める「48MHz」がどこにも無い**。他の作業のついでに
根拠の文が2種類見つかったので記録する。

**CH32V103 RM 3.3.4（zh p.17 / en 該当節）** — 一次的な事実:

```
如果需要在应用中使用 USBD 或 USBFS 模块功能，PLL 必须被设置为输出 48MHz 或 72MHz
时钟，用于提供48MHz的USBCLK时钟。因为USBD或USBFS模块的模拟收发时钟基于PLL时钟。
```

**CH32V20x_30x datasheet（zh p.11）** — 上から導かれる形:

```
注：当使用USB功能时，CPU的频率必须是48MHz或96MHz或144MHz。
```

入れ方の候補:

| 案 | 形 | 問題 |
|---|---|---|
| `operating_conditions.csv`に`F_USBCLK` | min=max=48・unit=MHz・`condition`にUSB使用時 | 既存の表の形にそのまま乗る。**推奨** |
| `clock_sources.csv`に`requires`列 | USB行に「48MHz」 | 列が1つの consumer のためだけになる |
| SYSCLKの許容値の列挙 | 48/96/144 | **分周器の一覧から導ける値**なので、表に入れると
  データではなく判断が入る（R-24追補2で切った線と同じ） |

#### 全文書を走査した結果（2026-08-22）: **前提が変わった**

`F_USBCLK`が48MHzでないfamilyがあるかを確認していない、と書いていた点を
潰した。DS・RM の**55文書×言語**を走査して、USBと周波数が同じ文脈に出る箇所を
全部拾った（204件）。

**48MHzは全familyの話ではない。** USBHS/USBSSを持つfamilyは
**48MHzのUSBCLKを一切使わない**。専用PLLを別に持つ:

| family | USBの時钟 |
|---|---|
| V103・V20x・V30x・V205・L103・X035・H41x | **USBD/USBFS = 48MHz**（PLLを分周） |
| V407/V467 | `USBHS_PLL` **320MHz / 480MHz** |
| X305/X315 | `USBHS_PLL` **480MHz**、`USBSS_PLL` **125 / 357 / 625MHz** |

`F_USBCLK = 48MHz`の行を全familyに入れると**V407/V467・X305/X315で嘘になる**。
入れてよいのは上の表の1行目だけ。

（CH32V205は最初「48MHzの記述が1件も無い」と書いたが、**datasheetだけを見ていた
誤り**。`CH32V205RM.PDF`のp.19/p.23が48MHzを書いている。RMも読む理由がこれ。）

**もう1つ、consumerが実際に要るのはCPU側の制約のほうで、これはfamilyで違う。**
しかも**資料が明示的に列挙している**（分周器から導いた値ではない）:

| 出所 | 文 | 許される CPU 周波数 |
|---|---|---|
| CH32V103DS0 | 当使用USB功能时，必须同时使用PLL，CPU的频率必须是48MHz或72MHz | 48 / 72 |
| CH32L103RM | 当使用USB功能时，CPU的频率必须是48MHz、72MHz或96MHz | 48 / 72 / 96 |
| CH32V203DS0・V208DS0・V20x_30xDS0・CH32FV2x_V3xRM | CPU的频率必须是48MHz或96MHz或144MHz | 48 / 96 / 144 |

**当初「分周器の一覧から導ける値なので判断が入る」として切った案は、前提が
間違っていた**——資料が直接書いている。導出ではないので入れてよい。ただし
`min/typ/max`の3列では「48か96か144」という**離散集合を表せない**ので、
許容値1つにつき1行（`typ`に値、`condition`に「USB使用時」）が形として素直。

#### 実装（2026-08-22・完了）

`build_operating.py`に散文を読む2つのreaderを足した。`read_headline_clock`
（1ページ目の系統主頻）と同じ形で、表ではなく本文を読む。

**48MHzは全速側のblock名を必ず伴う形でしか拾わない**
（`USBD|USBFS|USBHD|USBCLK|OTG_FS`）。高速側の文書には48MHzが一度も出てこないので、
これでV407/V467・X305/X315には当たらない。

**reference manualも読む。** CH32L103のCPU周波数とCH32H41xの48MHzは
**datasheetに無くRMにしかない**。CH32V205の48MHzも同じ。

**離散集合はmin/typ/maxで表せない**ので、CPU周波数は許容値1つにつき1行
（`typ`に値、`condition`に`USB in use`）。`F_USBCLK`は要求値が1つなので
min=typ=max=48。

**結果**: `operating_conditions.csv` 283→**305行**。追加22行は**全部`confirmed`**
（両言語版が一致）。

| symbol | series | 値 |
|---|---|---|
| `F_USBCLK` | V103 / V203 / V203;V205 / V208 / V30x / L103;M103 / X033;X035 / H41x | 48 MHz |
| `F_HCLK(USB)` | V103 | 48 / 72 |
| | L103;M103 | 48 / 72 / 96 |
| | V203・V208・V30x | 48 / 96 / 144 |

V407/V467・X305/X315・USBを持たないfamilyには1行も出ない（意図どおり）。

**抽出で1つ踏んだ**: `\b48\s*MHz`が中文版で当たらない。中文は「的48MHz时钟」と
続けて書き、**CJKも語構成文字なので`\b`が境界にならない**。CH32X035の中文版だけ
取り逃していた。`(?<![\d.])48`に変えた。F-16（全角括弧）・F-15（squashの語頭）と
同じ「ASCII前提の書き方が中文版で崩れる」型で、この日3件目
（[抽出可能性の事前調査](extraction-survey.ja.md)に型としてまとめた）。

**残り**: V407/V467・X305/X315のUSBHS/USBSS PLLは別の事実。`clock_symbols.csv`側の
話で、`operating_conditions`には入れない。

### F-5 `extract_registers`の見出しrun-on（修理済み）

**症状**: CH32H417のDMA章の41 fieldが`AFIO_EXTICR2`のfieldとして出る。
名前が`TIM1_CH1`〜`TIM9_CH3`なので**本物のremap selectorと見分けがつかない**
（F-2のB群54種の主因）。

**原因は2つで、どちらも見出しの読み方**:

```
✘ 10.3.1 DMAx 中断状态寄存器（DMAx_INTFR）（x=1/2）
✘ 10.3.3 DMAy 通道 x配置寄存器（DMAy_CFGRx）（x=1/2/3/4/5/6/7/8，y=1/2）
✔ 10.3.8 DMA请求复用器通道 1-4配置寄存器（DMAMUX1_4_CFGR）
```

1. **register名が行末に無い。** 適用範囲をもう1つの括弧で後ろに足す書き方があり、
   旧の`...（NAME）\s*$`は当たらない
2. **placeholderが小文字。** `DMAx_INTFR`・`GPIOx_CFGLR`・`DMAy_CFGRx`は
   `[A-Z][A-Z0-9_]*`に当たらない

当たらないと`register`が**前の値のまま残る**ので、その章の表が全部前の register の
ものになる。CH32H417ではAFIO章の最後の`AFIO_EXTICR2`が残ったまま
DMA章に入っていた。

**直し方は2つ**。名前の読み取りを緩めるのと、**見出しが来たら名前が読めなくても
`register`を必ず入れ替える**（読めなければ`None`にして表を捨てる）こと。後者が本体で、
「前の所有者を留任させる」のをやめれば同型の誤りは全部消える——**無いほうが、
もっともらしい別人の名前が付くよりよい**。

**実測**（節見出しを全部集めて突き合わせ）:

| RM | 見出し | 旧が名前を取れた | 新 | 新しく取れる | 取れなくなる |
|---|---:|---:|---:|---:|---:|
| CH32FV2x_V3xRM（zh） | 964 | 326 | 487 | **161** | **0** |
| CH32H417RM（zh） | 1539 | 592 | 863 | **271** | **0** |

新しく取れるのは`GPIOx_CFGLR`〜`GPIOx_SPEED`・`DMAx_INTFR`・`DMAy_CFGRx`・
`PFIC_IPRIORx`・`BKP_DATARx`・`HSEM_RXy`・`IPC_MSGx`など、**まさに誤帰属の
持ち主だったregister**。失うものは0件。

CH32H417を再抽出すると`AFIO_EXTICR2`のfieldは**59→0**、DMAのfieldは
`DMAy_CFGRx`(14)・`DMAMUX1_4_CFGR`(4)へ移り、`AFIO_PCFR1`の13 fieldは変わらない。
register 737種 / field 3232件。

**R-20（レジスタマップ）の下地でもある。** D-2が要るのはクロック関連レジスタの
ビット定義で、`GPIOx_*`や`RCC_*`が正しい持ち主に付くようになったのはその分の前進。

### F-6〜F-8 資料側で決まらないもの（記録のみ）

- **CH32V30xの`I2S3_*` remap-1**（`I2S3_WS`/PA4、`I2S3_CK`/PC10、`I2S3_SD`/PC12、
  4 series）。`SPI3_REMAP`が経路を決めるが、V30xのRM格子がその経路を書いていない。
  **CH32V407/V467は書いているので決まる**——同じ周辺が資料の書き方次第で決まったり
  決まらなかったりする
- **CH32V30xの`DVP_*`**。CH32V407にはある`DVP_REMAP`がV30xのheaderに無い
- **CH32V003の`AETR`**（PC2, remap-1）。datasheet独自の略記で、
  `ADC_ETRGINJ`と`ADC_ETRGREG`のどちらか決められない（`AETR2`はpadで決まる）

**`candidates/_report.json`の`unresolved`はこの2件だけ**です（2026-08-24の全体生成で
**36 function・13型番**）。内訳はF-6が32（V303/V305/V307/V317の`I2S3_CK`/`I2S3_SD`/
`I2S3_WS`）、F-8が4（V003の4型番の`AETR`）。**これ以外の未解決はありません**。

`--family`だけで回すと`_report.json`が上書きされてこの数が見えなくなる問題は
2026-08-24に直しました（触ったSKUだけ差し替える。D6の項）。逆に言えば、
**この36という数から動いたら、それは資料側が変わったか抽出が壊れたかのどちらか**です。

### F-19 比較表がページ境界をまたぐと継続ページを読めない

`extract_products.read_column_layout`は**表1つを単位に読む**ので、
`pdfplumber`がページごとに別の表として返す継続ページに、前ページの文脈が
何も渡りません。症状は3つ出ますが原因は1つです。

**(a) 継続ページに見出し行が無いと、その表が丸ごと落ちる。** どの列がどの型番か
決められず`read_column_layout`が`None`を返します。CH32L103の英語版がこれで、
比較表の後半13行——`CMP`・`Communication interface`の6行・`CPU main frequency`・
`Rated voltage`・`Package`・`Main applications`——が**英語側に1行も無い**まま
出ていました。

```
zh 29行 / en 16行
 16 CMP                       3   |                    ← en 側が空
 17 通信接口 USART              4   |
 ...
 28 主要应用及特点          通用，引脚兼容  |
```

`build_tables.attribute_rows`は値の並びのLCSで両版を対応付けるので、en側が
無ければ**そのまま「中文にしか無い」と読んで`reference`にします**。表に中国語が
大量に残っていたのはこれで、`label_en`が空の行が**141行**（L103・M030・M103・
H416・V103・V317）。資料は両方書いているので、`reference`は誤りです。

**(b) セル内の折り返しがページ境界で切れると、後半が捨てられる。**
CH32H417の英語版は`USBHS (USB 2.0)`が改行を挟んでページをまたぎ、

```
p3 r40: ['',  'USBHS (USB', '1','1','1','1','1']    ← 値はこちら
p4 r2 : ['',  '2.0)',       '', '', '', '', '' ]    ← 値が無い＝行ではない
```

前ページ側だけが残って`PDUSB USBHS (USB`という属性名になっていました。
**値を1つも持たない行は属性行ではない**（転置レイアウトでは必ず型番の列に値が
入る）ので、これは折り返しの尻尾だと判る。

**(c) 行グループの見出しが継続ページに引き継がれない。** (a)を直しても、
`carried`が表ごとに空から始まるので`PDUSB`が落ち、
`USBSS (USB 3.0)`が親無しで出ます（中文版はページ境界の位置が違うので
`PDUSB USBSS（USB 3.0）`になり、**同じ表なのに両版で親の有無が食い違う**）。

**このほかに、比較表の値が中文しか無い行が残ります。** CH32V317 の英語版は
比較表そのものが `Timer` の行から始まっていて（p.8）、pin数・Code FLASH・
FLASH・SRAM・GPIO の行が中文版にしかありません。**資料側の非対称**なので
`reference` / `products:zh` は正しい。ただし**表示に中文が出てはいけない**ので、
`product_attributes.csv` に表示用の `label` 列を足しました（`value` と同じ作法で、
英語版が言っていればそれを、無ければ `curated/translations.json` で訳したもの）。
訳が無ければ `tools/check_tables.py` の CJK 検査が落とすので、穴は黙って通りません。

**直し方は「前の表の状態を持ち回る」の一点。** 列と型番の対応は
**列のx範囲で引き継ぐ**——継続ページは列番号がずれることがあり
（CH32L103 p3は空列が1つ入って10列になる）、番号では合いません。
x範囲は罫線そのものなので厳密に一致します。

```
p2: (38.6,88.3) (88.3,155.8) (155.8,209.9) (209.9,267.8) ...
p3: (38.5,88.3) (88.3,155.8) None          (155.8,209.9) (209.9,267.8) ...
```

### F-20 行グループ見出しが属性名に混ざる

比較表の見出し列は2段組みで、`extract_products`は段を空白で繋いで
1つのラベルにしています（`通信接口 CAN` / `Communication interface CAN`）。
**READMEに出すと`Communication interface`が全行に付いて読みにくい。**

ただし親を捨てるだけでは駄目で、`三相预驱 电压`（3-phase gate drive Voltage）の
子は`Voltage`だけになり何の電圧か分からなくなります。**親は必要な情報だが、
ラベルに畳み込むのが間違い**なので、階層のまま持って表示側で選ぶ。

### F-21 `pin_roles`が語彙で覆えない signal

`tables/pin_roles.csv`は`signal_vocabulary.split()`を通せた行だけを載せ、
覆えなかった数を毎回出します。現在 110種 / 1046行（4.4%）が覆えていない。
**最終的には100%が目標**で、内訳ごとに行き先が違います。

| 内訳 | 例 | 行き先 |
|---|---|---|
| 抽出の残りかす | `DD33` `DDIO` `DDK` `IO18` `A13RST` | **抽出を直す**（F-1・F-13の残り） |
| pad名がsignal列に出る | `OSC_IN`のsignalが`PD0` | 役割ではないので**載せない**（除外条件を足す） |
| 系列固有の略記 | `O1N0`(OPA) `C1P0`(CMP) `A0`〜`A13`(ADC) | **語彙を足す** |
| システムピン | `MCO` `WKUP` `RST` `OSCI/OSCO` `XI/XO` | **語彙を足す** |
| USB | `USBDM/DP` `USBHDM/DP` `CC1`〜`CC4` | **語彙を足す** |
| CH32M030固有 | `HO0`〜`HO3` `LO0`〜`LO3` `ISINK` `ISOURCE` `QII` | **語彙を足す** |
| 資料側で未確定 | `AETR` `AETR2` | F-8として**記録のみ**。覆えないことを残す |

### F-22 セル内の折り返しで空白が落ちる

`flatten()`はセル内の改行を**空文字で**繋ぐので、欧文が空白で折り返した箇所が
潰れます。

```
Communicationinterfaces   ← Communication interfaces
MAC+10/100MPHY            ← MAC+10/100M PHY（同じ行の隣の型番は空白が残っている）
Low-powertimer(LPTIM)     ← Low-power timer(LPTIM)
3-phasegate drive         ← 3-phase gate drive
```

F-19(b)と同じ話で、**欧文は空白でしか折り返せない**。漢字は任意の位置で
折り返すので詰めて繋ぐのが正しく、両側がASCIIのときだけ空白を入れる。

### F-23 READMEの比較表の行の並びが資料の並びでない

`### CH32V303 product comparison`で`Timer Basic(16-bit)`や
`Communicationinterfaces FSMC`が末尾に来る。`product_attributes.csv`は
`(part_number, attribute)`のアルファベット順で、**資料の行の並びを持っていない**。
比較表は関連する行が固まるように組まれているので、その並びのほうが読みやすい。
行番号を持たせるか、READMEの生成側で並べ替える。

### F-24 lead番号のセルが縦結合された行を落としている（修理済み）

**1本の足に2つのpadが出ていることがあります。** datasheetはそれを、lead番号の
セルを縦に結合して2行に掛けることで書きます。

```
17 17 27 21 32  PA11(8)         ← G8R6 は 27
18 16 28 22 33  PA12(7)(8)      ┐ この 28 のセルが
19 17    23 34  PA13(7)(8)(9)   ┘ 2行に掛かっている
```

`table.extract()` は結合セルの値を**テキストが描かれた側の行にだけ**返し、もう
片方を空にします。空欄を「この封装には無い」（資料は`-`と書く）と同じに扱って
いたので、**CH32M103のPA13/PA14が丸ごと落ち、SWDIO/SWCLKを1つも持たないseries**
としてREADMEに出ていました。

**どちらの行にテキストが載るかは版面次第で、上とも下とも限りません**
——CH32L103のPA13は上のPA12に、CH32M103のPA13は下のPA12に載ります。
「上から継ぐ」ではなく**矩形が覆っている行を持ち主**とします（`fill_merged`）。

42行が該当し、34行が埋まりました。**読み方は資料の別の場所で検算できます**:

- CH32L103の注記8は`F8U6`について`PB1`/`PB10`・`PB6`/`PB13`・`PA12`/`PA14`・
  `PA11`/`PA13`の**4組を名指し**していて、結合セルから復元した4組と一致します。
- `CH32L103F8U6`は結合を使わず`17`を2度書いていて、同じことを別の書き方で
  言っています。
- CH32V407の`VREF-`と`VSSA`が同じ足になるのは、電気特性表の
  `V_REF- is equal to V_SS` が独立に裏付けます。

**内部接続を別の列や表記では持ちません。** 番号が一致していることが「同じ足」
そのもので、`PA13 (PA11)`のような表記を足すと同じ事実が2箇所に分かれて食い違い
得るうえ、検索の邪魔になります。「両方を同時に出力にしてはいけない」も列を
持ちません——**同じ`pin`に`kind=gpio`の行が2つ以上あることから導けます**
（電源padの共有は同時使用が当たり前で、`kind`が自然に両者を分ける）。
`tools/check_tables.py`が組の数を`kind`の形ごとに記録していて、増えれば結合セル
の読み違い、減ればpadの取りこぼしとして落とします。

**残る8行**は結合セルでもない空欄で、資料が`-`を書き忘れたのか別の意味があるのか
この表からは決まりません（CH32V20xのPA8はTSSOP20/QFN28が空欄なのに、同じ表の
隣の行は`-`を書いています）。落としますが`notes`に出します。

### F-25 pad名が8文字を超えると落ちる（修理済み）

`PAD_TOKEN`が`^[A-Z][A-Z0-9_+-]{0,7}$`で、**8文字までしか pad 名として認めて
いませんでした**。datasheet は pad の特別な役割を名前に継ぎ足して書くので、

```
PA0-WKUP           8文字。通っていた
PC13-TAMPER-RTC   15文字。落ちていた
PC14-OSC32_IN     13文字。落ちていた
PC15-OSC32_OUT    14文字。落ちていた
```

となり、**9冊の datasheet でこの3 padが丸ごと消えていました**（103型番のうち
99がPC13を持たない状態）。長さで測るのをやめ、**GPIOの名前で始まり`-`で役割が
続く**という形（`PAD_COMPOUND`）で見るようにしました。この形はsignal名には
現れないので、周辺信号を pad と取り違えません。

pin 4342→4455、pin_function 27926→28238。RTCのTAMPER/OUTが逆引きに載るように
なりました。

### F-26 同じpadの封装別の行を「ページの続き」と誤認（修理済み）

CH32X035のPC3は**封装によって既定の多重化機能が違う**ので、pad欄を縦に結合して
2行に組まれます。

```
11 -  4 -  -  -  -  PC3  I/O/A  PC3  C1N0/C2N1/C3N1/A13
-  -  -  8  -  4  -  （pad欄は空）    RST/C1N0/C2N1/C3N1/A13
```

pad欄が空の行を「ページ境界で切れた続き」として前の行に繋いでいたため、
`A13`＋`RST`が`A13RST`という存在しないsignalになり、**その封装だけが持つRSTが
消えていました**。

見分けは**封装欄が埋まっているか**です。自分の行なら全部の封装欄に何か書いて
ある（番号か「無い」の`-`）。ページ境界の尻尾は書けなかった欄が空のまま残る
——CH32V407のPB7は`60(12)`が切れて`2)`だけが次ページに残ります。

**それだけでは足りませんでした**。pad欄が縦に結合されているなら封装は2行に
分かれているはずなので、**同じ封装の欄を両方の行が埋めているなら別のpad**です。
CH32L103のPC13/PC14/PC15は番号が2/3/4と続くのにpad欄が取れておらず（F-25）、
継ぐと直前のVBATが3つに増えていました。縦書き見出しの繰り返し
（`6TER764V23HC` = `CH32V407RET6`の逆順）も番号欄に入るので、番号の形
（数字＋脚注か`-`）まで見ます。

### F-27 CH32V103のTIM3 remap値がRMと食い違う

consumer（ArduinoCore-CH32）の実験0015から辿って見つけたもの。
`pin_roles.csv`で**同じ (型番, 周辺, 役割, 経路) に複数padがある組**を数えると
984/22453（4.4%）あり、経路の種類で内訳が分かれます。

| 経路 | 組数 | 意味 |
|---|---:|---|
| `af-N` | 860 | **設計どおり**。pinごとにAF番号を選ぶので、同じ機能を出せるpadが複数ある |
| `default` | 101 | `SYS_NRST`が`PA15`と`PC0`（CH32M030）など |
| `remap-N` | 23 | **要調査**。1つのfield値は1組のpadを選ぶはずで、複数padは説明が要る |

`remap-N`の23組を資料に戻して確かめると、**3群それぞれ結論が違いました**。

**(1) CH32V103 TIM3（18行）——こちらの値が間違い。** RMの表10-12:

```
              TIM3_RM=00   TIM3_RM=10   TIM3_RM=11
TIM3_CH1      PA6          PB4          PC6
TIM3_CH3      PB0          PB0          PC8
```

PB4は**2**(10b)、PC6は**3**(11b)。ところがdatasheetのpin表は`TIM3_CH1_1`を
**PB4とPC6の両方に**書いていて（p13・p15・p17の3箇所）、こちらはその接尾辞を
そのまま採っています。**`TIM3_REMAP=1`と書いてもどちらのpadにも出ません**
（RMは01を定義していない）。candidateには既に`"_values_not_in_grid": [1]`と
記録されているのに、使っていません。

**(2) CH32L103 USART2（35行）——こちらの値は正しく、格子が読めていない**（F-28）。
RMの表10-17は`00 / 10 / 11`で`USART2_TX`の`10`列がPA11。pin表の値2(=10b)と一致
します。

**(3) CH32X033/X035 TIM1（42行）——pin表が正しく、格子は元から無い。**
CH32X035のRMには`复用功能重映射`の表が1つもなく、経路はregister fieldの説明文の
中だけにあります（`build_candidate`のコメントが既にそう書いている）。

**「格子を優先」の一律規則にしてはいけません。** 3群が別々の方向を向いていて、
(1)は格子が正しく、(2)は格子が壊れていて、(3)は格子が存在しません。直すなら
**格子が同じ (signal, pad) を別の値で名指ししているときだけ**という狭い条件に
限る必要があり、それでも(2)がF-28で直るまでは誤爆します。**F-28が先です。**

### F-28 CH32L103のremap格子を1行も読めていない

`extract_remap.extract()`が`CH32L103RM.PDF`に対して**0行**を返します。RMには

```
表10-17 USART2复用功能重映射
表10-18 USART3复用功能重映射
表10-19 USART4复用功能重映射
表10-20 SPI1复用功能重映射
```

がp84に並んでいます（実際に読めています）。12 familyの内訳:

| family | 格子経路 | 正しいか |
|---|---:|---|
| CH32V407 | 402 | ○ |
| CH32V20x / CH32V307 | 318 | ○ |
| CH32V006 | 302 | ○ |
| CH32M030 | 125 | ○ |
| CH32H417 | 97 | ○ |
| CH32V003 | 96 | ○ |
| CH32V103 | 80 | ○ |
| CH32V205 / CH32X315 | 0 | ○ AF方式でremap格子を持たない |
| CH32X035 | 0 | ○ RMに格子の表が無い（説明文のみ） |
| **CH32L103** | **0** | **✗ 表があるのに読めていない** |

**効き方**: CH32L103のremap経路は**pin表の接尾辞だけが根拠**で、裏取りが1つも
ありません。他familyでは格子とpin表の突き合わせが効いているのに、L103だけ
片肺です。F-27(2)の「値2が格子に無い」という誤った印もここから出ています。

### F-29 / F-30 逆引きで見つかった2つ（修理済み）

**F-29 pin type欄が`USB3.0`だと落ちる。** 型の欄は電気的な種別の記号（`I/O/A`・
`P`）か、その pad が属する interface の名前です。既に `ETH`・`USB`・`I/O/SDP` が
通っていましたが、CH32H417 の USB 3.0 差動 pad だけ `USB3.0` と版番号付きで
書かれるため外れ、**SSTXA/SSTXB/SSRXA/SSRXB の4 padが QFN128 から丸ごと落ちて
いました**。版番号を許すだけで、他の datasheet の行は1つも増減しません（全
datasheet で narrow/wide を突き合わせて実測）。

**F-30 語彙が1文字の周辺を作る。** `split()` は `_` を含む名前を
`(head, tail)` に割るので、`PERIPHERAL_ROLE` の形をしていない CH32M030 の
`Q_DET1`（電荷検出）が「**Q という周辺の DET1**」になっていました。
`extract_pins.stem()` が既に「1文字は周辺名ではない」を持っているので、語彙側にも
同じ条件を入れました。12行が「覆えない」として見えるようになります——
`memory_map.csv` に `Q` という region が無いことから見つけました。

### F-31 封装のlead数とpins.csvが合わない型番が12

`packages.csv` の `pin_count` と `pins.csv` の lead 番号の数を突き合わせると、
103型番中12で足りません（F-29 を直して16→12）。

| 型番 | 封装 | 欠け |
|---|---|---|
| CH32M007E8R6 / E8U7 / G8R6 / K8U7 | QSOP24 / QFN26C3 / QSOP28 / QFN32 | 各5 |
| CH32M103G8R6 | QSOP28 | 6 |
| CH32V203CCT6 | LQFP48 | 3（24・36・48） |
| CH32V103C6T6 | LQFP48 | 1（6） |（F-32で解消）
| CH32V203RBT6 | LQFP64M | 1（48） |
| CH32V205VCT6 / V303VCT6 / V307VCT6 / V317VCT6 | LQFP100 | 1（73） |

**LQFP100 の 73 番は資料が `未使用` と書いています**（`['-','-','-','-','-','-',
'73','未使用','']`）——pad ではないので機能は無く、落ちているのは正しいとも
言えますが、**封装の lead としては在る**ので、番号で pad を引く consumer には
「データが無い」と区別が付きません。`NC` として持つかどうかは持ち方の判断。

**CH32V103C6T6 の 6 番は解消しました（2026-08-25）。** この datasheet は pin 表を
2つ持ち（x8 品の3封装用と x6 品の2封装用）、x6 側は同じ端子を
`OSC8M_IN`/`OSC8M_OUT` と綴ります。`build_pins` は**両方の表を読んでいる**
（キャプション単位で全部見る。`choose_table` は単体 CLI 用）ので表の選択は
問題ではなく、`OSC8M_OUT` が9文字で `PAD_TOKEN` の8文字に掛かっていたのが原因
でした。**最初の測定で「広げても増えない」と書いたのは誤りで**、その測定が
`choose_table` 経由で表を1つしか見ていませんでした。`build_pins.read_edition`
で測り直すと `OSC8M_OUT` と CH32V203CCT6 の lead 24/36/48 が増えます（F-32）。

CH32M007 / CH32M103 の欠けは未調査です。

### R-25 consumerからの表の追加依頼（2026-08-25受領）

ArduinoCore-CH32 から3件。**2件は実装、1件は持ち方の問題があるので設計を返す。**

**(1) タイマの表 → `tables/timers.csv` を新設（実装済み）。**
妥当な依頼でした。比較表は`Timer General-purpose TIM4 (32-bit)`という**文**を
series粒度で持つだけで、綴りも`ADTM`/`GPTM`/`高级定时器`と揺れます。
**RMのregister見出しが対象タイマを名指ししている**ことを見つけたので、そこから
取れました（`（TIMx_CNT）（x=9/10/11/12）`＋`[31:0] CNT[31:0]`）。
63行／12 family、32bitのタイマは9つ。`counter_width_bits`・`kind`はRM、
`channels`・`complementary`は`pin_roles.csv`、`update_vector`は`interrupts.csv`。

作る過程で2つ気付きがありました。**更新割り込みは名前で選ばないといけません**
——高級タイマはベクタが`BRK`/`UP`/`TRG_COM`/`CC`の4本に割れていて、表の並び順で
最初に当たるのは`BRK`です（中断入力のベクタを更新割り込みとして渡すところでした）。
**幅がvariantで変わるものもあります**——CH32V20xのTIM5は`CH32V20x_D8`/`D8W`だけが
32bitで、同じRMを共有するCH32V307はそのvariantを持たないので`conflict`にしました。

**(2) pad名の正規化列 → `pin_roles.csv`に`port`/`pin`を追加（実装済み）。**
妥当な依頼でした。`pin_alternate.csv`が既に`pad, port, pin`を持っているので、
新概念ではなく揃えるだけ。`PA0-WKUP`→`port=A, pin=0`。GPIOでないpad
（`OSC_IN`・`XI`）は51行で、両方とも空にします。

**(3) 既定padの印（`preferred`列）→ そのままは入れられない。**

依頼の理由（consumerごとに推測すると、consumerごとに違う間違い方をする）は
正しいと思います。ただ**`pin_roles.csv`に入れると表の約束が壊れます**——この表は
「資料が言ったことを語彙で言い換えただけ」で、新しい事実を足さないことを
`check_tables.py`が毎回検査しています。984組のうち860組は`af-N`で、
**AF方式のfamilyに既定は無い**（電源投入時どのpadにも出ていない）ことを
確かめてあります。どれが「普通」かはどの資料も書いていません。

**当初`used_by_evt`（WCHの例題が使っているpad）を提案しましたが、撤回しました。**
依頼者に「デフォルト」の意味を確認したところ、**「電源を入れて何も設定しない
ときの状態」**であって「よく使う」ではないとのこと。例題が使っているpadは
後者なので別物です。

**その意味なら新しい判断は要りません。資料が書いています。** ただし
`route`の`main`と`default`が別のことを指していて、しかも**どちらの列に書くかが
familyで揃っていません**（下記）。必要なのは列を足すことではなく、この区別を
文書化して読む側が取り違えないようにすることでした。`tables/README.ja.md`の
「`route`の値の意味」に書きました。

### `route` の `main` と `default`（2026-08-25 整理）

全12 familyのpin表が同じ4列を持つことを列見出しの実測で確認しました。

| `route` | 出所の列 | 電源投入直後に動くか | 行数 |
|---|---|---|---|
| `main` | 主功能（复位后） | **動く** | 130 |
| `default` | 默认复用功能 / 引脚功能 | **動かない**（AFモードの設定が要る） | 9,261 |
| `remap-N` | 重映射功能 | 動かない | 約10,000 |
| `af-N` | 同じ列にAF番号併記 | 動かない | 約4,100 |

**UARTは`main`が1行もありません。** `main`に出るのは`SWDIO`/`SWCLK`/`BOOT0`/
`BOOT1`と、専用padのリセット機能だけです。

**列の選び方がfamilyで揃っていません。** 同じSWDが4 familyで主功能列、
7 familyで既定代替功能列、CH32V407は両方。物理的にはどのfamilyもリセット時に
SWDが生きている（それでデバッガが素で繋がる）ので、これは資料の書き方の違いです。
`main`だけで引くと**7 familyのSWDを落とします**。`build_readme.py`が両方を
見ているのはそのためで、コメントに理由を書きました。

**あわせて`main`の取りこぼしを直しました。** `signal == pad` の行を一律に
落としていたので、**名前が機能そのものである専用padのリセット機能**が消えて
いました。`kind`で分けます——`power`なら電源（`VSS`の主機能が`VSS`）、そうで
なければ機能（`NRST`の主機能が`NRST`）。`NRST`・`OSC_IN`/`OSC_OUT`・`XI`/`XO`・
`BOOT0`・Ethernetの`MDI*`・USB3.0の`SS*`が戻り、`pin_roles.csv`は
23,852→24,119行。`MDIRP`等と`SSTXA`等の語彙も足しました。

### F-32 添字の2つの名前が1セルに入る

CH32V205 の pin 表は1つのセルに**2つの pad 名**を書きます。文字の位置で分かります:

```
V(基準 x=163)  D D _(添字 x=169-174)  V(基準 x=177)  I O _ 1(添字 x=182-190)
→ V_DD_  と  V_IO_1
```

詰めると `VVDD_IO_1` という存在しない名前になります。`PAD_TOKEN` が8文字だった
ときは丸ごと落ちて、別の行から拾った `VIO_1` が残っていました（部分的には正しい
読み）。12文字に広げたので**lead 24/36/48 が CH32V203CCT6 に戻り**、代わりに
CH32V205 の2型番で綴りが `VIO_1` → `VVDD_IO_1` に悪化します。

**直し方は分かっています**——基準サイズの文字が現れるたびに新しい名前が始まる、
という規則（F-1 と同じ添字の話）。1セルに2つの pad 名が入るとき `pad` 列に
どう持つかの判断が要るので、そこを決めてから直します。

## 利用状況（優先順位の根拠）

| # | 誰 | 最初の問い |
|---|---|---|
| U1 | 買ってしまった人 | このピンは何？どう書き込む？Lチカの最短経路は？ |
| U2 | 選定する人 | 要求を満たす型番は？落とし穴は？ |
| U3 | 開発中の人 | この機能はどのピンに出せる？remap値は？例題は？ |
| U4 | 移植する人 | メモリマップ・割り込み番号・機械可読定義は？ |
| U5 | 原典に到達できない人 | 最新版は？いつ同期した？両言語あるか？ |
