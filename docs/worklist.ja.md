# 作業リスト

README自動生成の対象は**データシートとEVTを持つ12リポジトリのTOP**と**org TOP（.github）**です。両方とも特殊処理なしの全自動生成を目標にします。根拠は[docs/extraction-survey.ja.md](extraction-survey.ja.md)、データ構造は[tables/README.ja.md](../tables/README.ja.md)。

状態: ✅完了 / 🔜次 / ⬜未着手 / ❓要確認（人の判断待ち）

**解決済みの項目の詳細は [worklist-archive.ja.md](worklist-archive.ja.md) に移した**（2026-08-25 棚卸し）。
この文書に残るのは、索引表と、まだ生きている項目だけ。

## 進捗

テーブルごとの信頼度は [table-reliability.ja.md](table-reliability.ja.md)（どのテーブルがどこまで固いか・既知の穴の所在）。


| 区分 | 完了 | 残り |
|---|---:|---:|
| データ収集 | 9 | 0 |
| README生成 | 3 | 3（B4〜B6。新規） |
| 画像 | 0 | 3（保留） |
| 検査・運用 | 5 | 2（D4・D7。新規） |
| consumerからの依頼 | 7 | 1（R-20。方針が要る） |
| 既知の穴（F系） | 36 | 10 = ツール側 5（F-8・F-21・F-31・F-32・F-24残り）＋ 実機待ち 1（F-11）＋ 資料側の記録 4（F-6/7・F-33・F-43〜46） |

（2026-08-25 棚卸し時点。次にやる順は [次の作業](#次の作業優先順) にある）

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
- [x] ✅ **A6 機能フラグ（USB/Ethernet/CAN/PD/DVP…）** — `tables/features.csv`新設（2026-08-23）。比較表からは作れない（[調査結果はarchive](worklist-archive.ja.md)）ので、**機能説明章の節見出し**を採った。節番号は言語に依らないので中英が厳密に対応する
- [x] ✅ **A7 メモリマップ** — `tables/memory_map.csv`新設（2026-08-23）。**DS 1.2章ではなくEVTヘッダーの`*_BASE`から**。相対の連鎖を解く処理は`extract_addresses`が既に持っていた
- [x] ✅ **A8 書き込み方式** — **A6の副産物**（2026-08-23）。`1-wire Serial Debug Interface (SDI)`／`2-wire SDI Serial Debug Interface`が節見出しとして立っているので、`curated/`への手書きは不要だった
- [x] ✅ **A9 割り込みベクタ表** — `tables/interrupts.csv`新設（2026-08-23）。**RM側と書いたのは材料の見落とし**で、EVTヘッダーの`IRQn_Type`列挙が番号・名前・説明を全部持っている。variantで番号が入れ替わるので`#if`の条件を`condition`列に持つ

## B. README生成

- [x] ✅ **B1 12リポジトリのTOP生成** — Series/Documents/比較表/ピン表/remap/Errata/Diagrams。日次でミラーが取得
- [x] ✅ **B2 org TOPの生成** — 現行はリポジトリ一覧＋横断文書＋toolchain
- [x] ✅ **B3 org TOP「型番から探す」** — **今あるデータだけで作れる**（series.csv: series→family、products.csv: part_number→family）。CH32M007がCH32V006に、CH32M103がCH32L103に、CH32V317がCH32V307に入っている件が検索者に見えるようになる。～~これができれば`curated/readme-extras/CH32V20x.md`（V205分離の手書きNotes）を削除して**特殊処理ゼロ**にできる~～ → **この見通しは誤りだった**（2026-08-24に確認。手書きNotesは消さない。[記録](worklist-archive.ja.md)）
## C. 画像（保留）

**現時点では生成READMEに画像を使いません。** 切り出しの品質が実用水準に達していないためです。ピン配置図は「パッケージ→型番→データシート」の対応表で代替しています。

- [ ] ⬜ **C1 切り出し品質** — `tools/extract_images.py`は134枚を生成できるが、図の縁の判定・ファイル名と図中型番の一致（82枚中6枚が不一致）に課題が残る
- [ ] ⬜ **C2 ページ番号リンク** — `#page=N`はGitHub Pages配信のPDFで機能する（`content-type: application/pdf`を確認済み）。抽出時にページは分かるので`tables/figures.csv`として持てば、対応表からページ直リンクにできる
- [ ] ❓ **C3 シリーズ構成図** — 原典のデータシートには無く、WCH製品ページ由来。手作りは27シリーズ中10枚のみで17枚不足。`tools/build_system_figures.py`でtables/から生成もできるが見た目が別物。**採用は保留**

### 不足している手作りsystem図（17シリーズ）

CH32H415, CH32H416, **CH32H417**, CH32M007, **CH32M030**, CH32M103, CH32V002, CH32V004, CH32V005, CH32V007, CH32V305, CH32V317, **CH32V407**, CH32V467, CH32X033, **CH32X305**, **CH32X315**

太字はファミリーの主力シリーズ。CH32M030・CH32V407・CH32X315・CH32H417は図が1枚もない状態です。

## D. 検査・運用

- [x] ✅ **D1 参照結合検査** — `tools/check_tables.py`が全36テーブルの参照結合・書式・数の不変量を検査（`check_counts.py`が比較表の数とpin側の数を突き合わせる）
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
| R-20 | レジスタマップ（D-1〜D-8） | ❓ **調査済み・方針未決**。[register-map-survey.ja.md](register-map-survey.ja.md)。consumer側の要否確認から |
| R-24 | クロック関連データ（C-1〜C-8） | ✅ **C-1〜C-8を実装**（2026-08-21）。`clock_configs.csv`・`clock_prescalers.csv`・`clock_sources.csv`＋`operating_conditions.csv`拡張 |
| R-24追補 | クロック表の追補（A-1〜A-4）とremapの要確認（B） | ✅ **実装済み**（2026-08-21）。`clock_symbols.csv`・`evt_variants.csv`新設、`operating_conditions.csv`に`typ`列、remapの誤帰属を修正 |
| R-24追補2 | クロック切替に要るレジスタ/ビットとflash latencyの取りこぼし（D-1〜D-4） | ✅ **実装済み**（2026-08-21）。`clock_symbols.csv`を77→429行に拡張、`clock_init.csv`新設、`clock_configs`に`flash_sck_div`列 |
| R-24追補3 | CH32V103のSTKレジスタほか（E-1〜E-5） | ✅ **全件クローズ**（2026-08-22）。E-1は探されたレジスタが存在せず`systick.csv`で回答、E-2はRMに記述なし、E-3は`memory_configs.csv`新設、E-4/E-5は`clock_symbols`の集め方を直した |
| R-25 | 表の追加依頼3件（timers・port/pin・preferred印） | ✅ **2件実装・1件は回答**（2026-08-25）。`timers.csv`新設、`pin_roles`に`port`/`pin`。preferred印は「電源投入時の状態」なら資料が既に持つ（`route`の`main`/`default`）ので列を足さず`tables/README`に区別を書いた |
| R-26 | 追加テーブル4件＋参考1件 | ✅ **全5件実装**（2026-08-25）。`flash_geometry`・`opa_cmp_registers`・`adc_internal`・`usbpd_plumbing`・`clock_enables` |

R-24系・R-25・R-26の実装記録は [archive](worklist-archive.ja.md)。この過程で見つけて手を付けなかった穴は [F. 既知の穴](#f-既知の穴埋める順) に一覧にした。

## F. 既知の穴（埋める順）

R-19・R-24とその追補を実装する過程で見つかったが、依頼の範囲外として手を付けなかったもの。
**資料側の穴**（上流にデータが無い）と**ツール側の穴**（資料にはあるが取れていない）を
分けている。前者は直せないので記録が成果物、後者は直せる。

| # | 穴 | 規模 | 側 | 判断 |
|---|---|---:|---|---|
| F-1 | pin表の電源pin名が添字で分断される | 約850行 | ツール | ✅ **修理済み**（2026-08-21）。F-4も同じ修正で片付いた |
| F-2 | CH32V20xのEVT headerに`AFIO_PCFR2_`が無い | 7 function | 資料 | ✅ **実装済み**（2026-08-22）。3案目（`basis`で区別）。[記録](worklist-archive.ja.md) |
| F-3 | 中国語版の文章中のpadを拾えない | **増分0** | ツール | ✅ **修理済み**（2026-08-22）。今の資料では表は動かない。[記録](worklist-archive.ja.md) |
| F-4 | pin表のsignal名が縦書きセルで切れる | 約100行 | ツール | ✅ **ほぼ修理済み**（F-1と同一原因）。残り6行 |
| F-5 | `extract_registers`の見出しrun-on | 見出し432・field多数 | ツール | ✅ **修理済み**（2026-08-22）。[記録](worklist-archive.ja.md) |
| F-6 | CH32V30xのRM格子がI2S3のremap経路を書いていない | 32 function・4 series | 資料 | 記録のみ（実測 2026-08-24） |
| F-7 | CH32V30xのheaderに`DVP_REMAP`が無い | 2 function | 資料 | 記録のみ |
| F-8 | CH32V003の`AETR`がADC 2 fieldのどちらか決まらない | 4 function・4 part | ~~資料~~ **ツール** | 🔜 **再調査で決まった**（2026-08-25）。zh版RMの表7-13/7-14が`ETRGREG`=PD3/PC2、`ETRGINJ`=PD1/PA2と書き、`AETR`(PD3/PC2)・`AETR2`(PD1/PA2)のpadと一致する。決まらなかったのは**en版RMのbit17説明が誤植**（ETRGINJの説明にETRGREGの文を繰り返しPC2と書く）で両fieldにPC2が出るため。下記 |
| F-9 | USBが48MHzを要求する根拠が散文 | 22行 | ツール | ✅ **実装済み**（2026-08-22）。48MHzは全familyの話ではなかった。[記録](worklist-archive.ja.md) |
| F-10 | CH32V205・CH32X315のRMから経路が0件 | V203CCT6のUSART5-8 | 資料/ツール | ✅ **原因判明**（2026-08-22）。**AFIO remapを持たない世代**だった。[記録](worklist-archive.ja.md) |
| F-11 | WCH-Link系ファームウェアの版番号が確定しない | — | 資料 | 🔜 実機で1回突き合わせる |
| F-12 | AF番号で多重化するfamilyの選択レジスタが未収録 | 240行 | ツール | ✅ **実装済み**（2026-08-22）。`tables/pin_alternate.csv`新設。[記録](worklist-archive.ja.md) |
| F-13 | pin表のslashが改行で落ちてsignalが連結する | 32種・17 part | ツール | ✅ **修理済み**（2026-08-22）。F-1の副作用。[記録](worklist-archive.ja.md) |
| F-14 | `flash_bytes`が零等待領域ではなく総容量を指すfamilyがある | 18 part | ツール | ✅ **修理済み**（V30xは2026-08-22、X305/X315は2026-08-23）。[記録](worklist-archive.ja.md) |
| F-15 | 比較表の**行グループ**（左セルが複数行にまたがる）が1行に潰れる | H41x 5 part・480行 | ツール | ✅ **修理済み**（2026-08-22）。`sram_bytes`が896KBのうち128KBだった。[記録](worklist-archive.ja.md) |
| F-16 | 脚注の**全角括弧**を剥がしていない | 38 pad・364行 | ツール | ✅ **修理済み**（2026-08-22）。pin表の行が丸ごと落ちていた。[記録](worklist-archive.ja.md) |
| F-17 | **ページ境界で切れた行**が丸ごと落ちる | V407/X035 27行 | ツール | ✅ **修理済み**（2026-08-22）。[記録](worklist-archive.ja.md) |
| F-18 | lead番号に脚注が付いたまま出る（`int`にできない） | 16行 | ツール | ✅ **修理済み**（2026-08-22）。[記録](worklist-archive.ja.md) |
| F-19 | 比較表が**ページ境界**をまたぐと継続ページを読めない | en 141行が欠落・H417 4ラベル | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-20 | 行グループ見出しが属性名に混ざる（`Communication interface CAN`） | 全family | ツール | ✅ **実装済み**（2026-08-24）。`group`/`label`を新設。[記録](worklist-archive.ja.md) |
| F-21 | `pin_roles`が語彙で覆えない signal 110種 | 1046行（4.4%）→**26種122行（0.5%）** | ツール/資料 | 🔜 大半を解消（2026-08-24）。残りはM030の22種・V003の3種・V208の`ANT`。下記 |
| F-22 | セル内の折り返しで**空白が落ちる**（`Communicationinterfaces`） | 全family | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-23 | READMEの比較表の**行の並びが資料の並びでない** | 全family | ツール | ✅ **修理済み**（2026-08-24）。`order`列を新設。[記録](worklist-archive.ja.md) |
| F-24 | **lead番号のセルが縦結合された行**を落としている（同じ足に2つのpad） | 42行 → 8行 | ツール | ✅ **修理済み**（2026-08-25）。残り8行は結合でもない空欄（資料が`-`を書き忘れたか別の意味か決まらない。`build_pins`のnotesに出る）。[記録](worklist-archive.ja.md) |
| F-25 | pad名が**8文字を超えると落ちる**（`PC13-TAMPER-RTC`） | 103型番中99がPC13を持たなかった | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-26 | 同じpadの**封装別の行**を「ページの続き」と誤認 | CH32X035 PC3 | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-27 | CH32V103のTIM3 remap値が**RMと食い違う**（pin表の接尾辞が誤り） | 18行 | 資料/ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-28 | **CH32L103のremap格子を1行も読めていない** | 0 → 195経路 | ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-29 | pin type欄が`USB3.0`だと落ちる | H417のUSB3.0差動4 pad×4型番 | ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-30 | 語彙が**1文字の周辺**を作る（`Q_DET1`→周辺`Q`） | 12行 | ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-31 | **封装のlead数とpins.csvが合わない型番が10** | 26 lead | ツール/資料 | 🔜 **原因判明**（2026-08-25）: M007×4・M103の26 leadは全部ゲートドライバ出力pad `LO1\n(PA0)`で、GPIO別名の括弧を`PAD_TOKEN`が通さず黙って落ちる。V203RBT6/LQFP100の`未使用`は資料どおり。下記 |
| F-32 | 添字が2組あるpad名を**基準文字→添字の順に詰めて**`VVDD_IO_1`にしている（資料は`VDD_VIO_1`） | CH32V205DS0 の 3 pad・5行 | ツール | 🔜 下記 |
| F-33 | `documents.csv`の版番号が**WCH APIのメタデータ**で、PDF表紙より遅れることがある | CH32V20x_30xDS0（3.5 vs V3.9） | 資料 | 記録のみ（2026-08-25）。全PDFの表紙スキャンで他は一致 |
| F-34 | `remap_fields.csv`の**reset_value空欄が45行**（RMでは0と確定できる） | 45行→**7行** | ツール | ✅ **修理済み**（2026-08-25）。RMの復位値`00b`/`000b`（2進）を読めていなかった。残り7行はRMが復位値を書かないもの（EXTEN `CTR`のM030 `ISINK*_ADJ`・V20x `ETH_10M_EN`、V103 `TIM4_REMAP`/`USART2_REMAP`、X315 `PD0_1_REMAP`）。推測で0と埋めない |
| F-35 | `TIM5CH4_RM`の**valid_valuesに値1（LSI）が無い** | V20x/V30x系6行 | ツール | ✅ **修理済み**（2026-08-25）。RM説明文が列挙する値（`0：…；1：…`）をvalid_valuesの出所に足した |
| F-36 | `operating_conditions`の条件文字列に**下付き文字のずれ**（`f > 1MHz S`） | 13行 | ツール | ✅ **修理済み**（2026-08-25）。孤立した添字を手前の裸の記号へ戻す（`f_S > 1MHz`・`T_A = …`）。残り0 |
| F-37 | `interrupts.csv`の**OR結合variant条件が先頭マクロに切り詰め** | V006の2ベクタ | ツール | ✅ **修理済み**（2026-08-25）。`\|`区切り（memory_mapと同じ規約） |
| F-38 | `memory_map.csv`の**link-origin 2行が誤値**（ORIGINの算術未評価・H417の2コア別リンカ） | V407 RAM・H417 RAM | ツール | ✅ **修理済み**（2026-08-25）。多数決をやめ基準リンカ（EXAM/SRC/Ld）を式評価で読む。H417はコア別2行（condition=V3F/V5F） |
| F-39 | `clock_init.csv`の**V307分岐条件の欠落とV006のRMW手順の丸ごと欠落** | 2 family | ツール | ✅ **修理済み**（2026-08-25）。#if分岐をconditionへ、ローカル変数経由のRMWを手順として採る |
| F-40 | `pin_functions`が**封装別の既定機能をunionで潰す**（X035 PC3のRSTが全封装に付く） | 余分2行 | ツール | ✅ **修理済み**（2026-08-25）。機能を(表,封装,pad)単位に。[記録](worklist-archive.ja.md) |
| F-41 | **F-27の格子優先修正がpin_functions/pin_rolesに未反映**（build_pinsはPDF直読み） | V103 TIM3 12行 | ツール | ✅ **修理済み**（2026-08-25）。candidatesの`_value_from_grid`をbuild_pinsが適用（conflict+両論のbasis）。[記録](worklist-archive.ja.md) |
| F-42 | **2レジスタに割れたfieldの格子列見出しを低位ビットだけで読んでいた** | V407/V467のUSART1等 | ツール | ✅ **修理済み**（2026-08-25）。F-41の適用で発覚。[記録](worklist-archive.ja.md) |
| F-43 | CH32V407 RMの**I3C格子の列見出しが両列とも`I3C_RM=0`**（原典の誤植） | 2列 | 資料 | 記録のみ。pin表の`I3C_SCL_1`が正。誤植への歯止めを実装 |
| F-44 | CH32X035 EVTヘッダの**`OPA_CTLR2_CMP_LOCK`のmaskが`0x2000`（bit13=PSEL3と同じ）**。RMはbit31 | 1 define | 資料 | 記録のみ（2026-08-25）。opa_cmp_registersでconflict表示。使うとCMP3の正入力選択を壊す |
| F-45 | EVTヘッダとRMで**OPA/CMPのbit位置が食い違う**（L103 ITRIMN/ITRIMP 5bit vs 6bit、V205 HYS1_H/HYS2_H bit29/30 vs 19/29） | 4 define | 資料 | 記録のみ。opa_cmp_registersでconflict＋両論 |
| F-46 | datasheet zh/en で**温度センサのAvg_Slope最大値が違う**（V20x/V307: 4.8 vs 4.7 mV/℃） | 2 family | 資料 | 記録のみ。adc_internalでconflict＋両論 |
| R-25 | consumerからの表の追加依頼3件（2026-08-25受領） | — | 依頼 | ✅ 2件実装・1件は回答（`route`の`main`/`default`を文書化）。[記録](worklist-archive.ja.md) |
| R-26 | consumerからの追加テーブル依頼4件＋参考1件（2026-08-25受領） | — | 依頼 | ✅ **全5件実装**（2026-08-25）。[記録](worklist-archive.ja.md) |

### F-11 WCH-Link系ファームウェアの版番号（[link-firmware-survey](link-firmware-survey.ja.md)）

`tables/link_firmware.csv`（10行）と`tools/build_link_firmware.py`を作り、
ファイルの同定・sha256・取得の自動化まではできた。**版番号だけが確定していない。**

配布物が名乗る版（`wchlink.wcfg`の`CH32V307Ver=42`等）と、実機がUSBで申告する版
（`2.12`のような`major.minor`）の対応が取れない。バイナリに応答テンプレートは
入っておらず、配布ページはJS生成で版情報を持たない。**この対応が付くまで
「あなたのは古い」を言う表としては使えない。**

次に試すのは実機での1回の突き合わせ（更新前後で`minichlink`の表示を控える）。
詳細と他の案は調査ドキュメントに書いた。

### F-6〜F-8 資料側で決まらないもの（記録のみ）

- **CH32V30xの`I2S3_*` remap-1**（`I2S3_WS`/PA4、`I2S3_CK`/PC10、`I2S3_SD`/PC12、
  4 series）。`SPI3_REMAP`が経路を決めるが、V30xのRM格子がその経路を書いていない。
  **CH32V407/V467は書いているので決まる**——同じ周辺が資料の書き方次第で決まったり
  決まらなかったりする
- **CH32V30xの`DVP_*`**。CH32V407にはある`DVP_REMAP`がV30xのheaderに無い
- ~~**CH32V003の`AETR`**（PC2, remap-1）。datasheet独自の略記で、
  `ADC_ETRGINJ`と`ADC_ETRGREG`のどちらか決められない~~ → **決まる**（2026-08-25 再調査）。
  datasheetの凡例は`AETR(ADC_ETR)`、RM zh 表7-14は`ADC_ETRGREG_RM` 0=PD3 / 1=PC2、
  表7-13は`ADC_ETRGINJ_RM` 0=PD1 / 1=PA2。`AETR`のpad（PD3→PC2）は`ETRGREG`の、
  `AETR2`（PD1→PA2）は`ETRGINJ`のpadと一致する。tool側が決められなかったのは
  **en版RMのbit17（ETRGINJ）の説明文が規則転換（PC2）の文を誤って繰り返す**ためで、
  英語版を読むと両fieldがPC2を名乗る。zh版だけで決める（zh散文のpadはF-3で読める）。
  語彙は`AETR`→(ADC1, RETR)、`AETR2`→(ADC1, IETR)（V00xの`ADC_RETR`/`ADC_IETR`の既存規則と同じ綴り）

**`candidates/_report.json`の`unresolved`はこの2件だけ**です（2026-08-24の全体生成で
**36 function・13型番**）。内訳はF-6が32（V303/V305/V307/V317の`I2S3_CK`/`I2S3_SD`/
`I2S3_WS`）、F-8が4（V003の4型番の`AETR`）。**これ以外の未解決はありません**。
F-8を直すと**32**になる。

`--family`だけで回すと`_report.json`が上書きされてこの数が見えなくなる問題は
2026-08-24に直しました（触ったSKUだけ差し替える。D6の項）。逆に言えば、
**この36という数から動いたら、それは資料側が変わったか抽出が壊れたかのどちらか**です。

### F-21 `pin_roles`が語彙で覆えない signal

`tables/pin_roles.csv`は`signal_vocabulary.split()`を通せた行だけを載せ、覆えなかった
綴りは`tools/check_tables.py`の`KNOWN_ROLE_GAPS`に**名前と行数で固定**してある
（増減はどちらも検査で落ちる）。110種1046行（4.4%）から始めて、2026-08-25時点で
**26種122行（0.5%）**。内訳と行き先:

| 内訳 | signal（行数） | 行き先 |
|---|---|---|
| CH32M030 のモータ/アナログ専用機能（22種・99行） | `HO0`〜`HO3`／`LO0`〜`LO3`（PB8〜PB15の`default`。`HO3`はM007の専用padにも）、`ISP1`（専用pad）`ISP2` `ISN1` `ISN2`、`ISINK1/2`、`ISOURCE1/2`、`QII1/2`、`Q_DET1/2`、`V_DET`、`SWIM`（PA3） | **語彙を足す**。所属は下表（2026-08-25 原典で確認） |
| CH32V003 の略記（3種・18行） | `AETR`(PD3/PC2)・`AETR2`(PD1/PA2)・`TIETR`(PD4, remap-2) | `AETR`→(ADC1, RETR)、`AETR2`→(ADC1, IETR)（F-8。padでRMの表7-13/7-14と一致）。`TIETR`は`T1ETR`の誤植（`I`と`1`。同じ行が表2-3では`T1ETR_2`、RM表7-8で`TIM1_RM=10`のETRがPD4）→(TIM1, ETR) |
| CH32V208 の専用pad（1種・4行） | `ANT`（凡例「射频信号输入输出（天线）」。`main`） | (BLE, ANT)。die上のRFブロックはBLE5.3だけ（header `BB_IRQn`「BLE BB」） |

**全26種が語彙で覆える見込み**（F-8も含めて）。M030の22種はF-31のM007/M103の`HO*`/`LO*`と
同じpad群なので、F-31と同時に語彙を入れると一度で済む。

**CH32M030の22種の所属**（datasheet zh/en・RM・`ch32m030.h`で確認。WCHの呼び方に揃える）:

| signal | 資料の説明 | WCHの呼び方 | 提案 (peripheral, role) |
|---|---|---|---|
| `HO0`〜`HO3` / `LO0`〜`LO3` | DS 表2-2「内部高侧/低侧栅极驱动器的输出，控制N型MOSFETの栅极」。§1.4.20 栅极驱动器 / Gate Driver「4个独立半桥驱动器」 | RMは独立章を持たず§6.2.10「MVのGPIO構造」で説明。headerは`AFIO_PCFR1_HO_DIO_EN0..3_REMAP`のみ。比較表は「半桥栅极驱动器 / Half-bridge gate driver」「预驱动I/O（MV I/O）/ Pre-drive I/O」。M007は「三相预驱 / three-phase pre-driver」 | **(PREDRV, HO0)…(PREDRV, LO3)**。M030/M007の両datasheetと比較表が共通に使う語が「预驱/pre-drive」。代案の`HB`はRMで「HB时钟」（AHB）を意味するので避ける。**要判断** |
| `ISP1`（専用pad）`ISP2`(PA10) / `ISN1`(PA8) `ISN2`(PA11) | DS §1.4.18.2「差分输入电流采样（ISP）」。「ISP1和ISN1/PA8为一对差分输入，ISP2/PA10和ISN2/PA11为另一对」 | RM §17.2.6（OPA/CMP章）。header `OPA_TypeDef.ISP_CTLR`、`ISP_CTLR_ISP1_EN/GAIN/NSEL` | **(ISP1, P) (ISP1, N) (ISP2, P) (ISP2, N)**（CMPの`C3N0`→(CMP3, N0)と同じ流儀） |
| `QII1`(PA12) `QII2`(PA13) | DS §1.4.18.1「交流小信号放大解码器（QII）」。QII1=OPA1+CMP1+デジタルフィルタ | RM §17.2.5。header `OPA_TypeDef.QII_CFGR`、`QII_CFGR_QII1_AE` | **(QII1, IN) (QII2, IN)**（役割語は資料に無いのでこちらで置く） |
| `Q_DET1`(PA14) `Q_DET2`(PA15) | pin表のみ。RM `ISP_CTLR`の`QDET1_EN`「ISP1模块Q值检测使能」、ADC章「ADC_IN9/IN10を使うには`QDET1_EN`/`QDET2_EN`を1に」 | ISPモジュールのQ値検出経路。header `ISP_CTLR_ISP1_QDET1_EN`（**`ISP2_QDET1_*`はheaderの誤記**。RMはQDET2） | **(ISP1, QDET) (ISP2, QDET)** |
| `V_DET`(PB4) | DS「PB4引脚支持ADC和OVP过压复位。VHVを外部抵抗で分圧してPB4へ」 | RM 電源制御（PWR）§2.2.2 过压复位 / §2.2.3 分压监测。`PWR_CTLR[13:12] SEL_IO_VHV`「PB4端口功能选择」。header `PWR_CTLR_SEL_IO_VHV` | **(PWR, V_DET)** |
| `ISINK1`(PA6) `ISINK2`(PA7) | DS §1.4.19「可编程灌电流模块ISINK」10bit | RM EXTEN章§20.1 `R16_ISINK1_CFGR`/`R32_ISINK_ADJ`。header `EXTEN_TypeDef.ISINK1_CFGR` | **(ISINK1, OUT) (ISINK2, OUT)** |
| `ISOURCE1`(PA4) `ISOURCE2`(PA5) | 同§1.4.19「源电流模块ISOURCE」（NTC用）。pin図の凡例「ISRC:ISOURCE」 | RM EXTEN_CTLR0 `ISRC1_EN/ISRC1_SEL` | **(ISOURCE1, OUT) (ISOURCE2, OUT)** |
| `SWIM`(PA3) | pin表の`default`列だけに出る（`SWDIO/SWIM/CC4/…`）。RMにもEVTにも無い | DS §1.4.22 SDI「单线调试…对应**SWIO**引脚，双线…SWDIO和SWCLK」。**STM8のSWIMではなく1-wire SDIのデータ線**を`SWIO`と綴り違えたもの | 既存規則`SWIO`→(SDI, SWDIO)に揃えると PA3 が (SDI, SWDIO) を2回持つ。**要判断**: 1-wire/2-wireを区別するなら`SWIO`と`SWIM`を (SDI, SWIO) に |

比較表との整合: `half_bridge_gate_driver`（4/4/4/2/3）・`pre_drive_i_o_mv_i_0`（8/8/8/6/6＝HO/LOのpad数）・
`current_sampling_isp_isn`・`signal_decoding_qii`（2）・`programmable_current_injection_module_isink`（2）・
`source_current_module_isource`（2）が`product_attributes`に既にあり、数が合う。

### F-31 封装のlead数とpins.csvが合わない型番が10

`packages.csv` の `pin_count` と `pins.csv` の lead 番号の数を突き合わせると、
103型番中10で足りません（F-29で16→12、`PAD_TOKEN`の拡張で12→10。2026-08-25実測）。

| 型番 | 封装 | 欠け |
|---|---|---|
| CH32M007E8R6 / E8U7 / G8R6 / K8U7 | QSOP24 / QFN26C3 / QSOP28 / QFN32 | 各5 |
| CH32M103G8R6 | QSOP28 | 6 |
| ~~CH32V203CCT6~~ | LQFP48 | ~~3（24・36・48）~~ 解消（`PAD_TOKEN`を12文字に。綴りはF-32） |
| ~~CH32V103C6T6~~ | LQFP48 | ~~1（6）~~ 解消（`OSC8M_OUT`が9文字だった） |
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

**CH32M007 / CH32M103 の欠け 26 lead は原因が1つです（2026-08-25 原典で確認）。**
どれもゲートドライバ出力の pad で、datasheet は pad 欄を **pad 名＋括弧の GPIO 別名**の
2行で書きます:

```
['14', '17', '9', '10', 'LO1\n(PA0)', 'O', 'LO1', '', '']     ← M007 表2-2（zh p21 / en p28）
['15', 'HO1\n(PA8)', 'O', 'FT', 'HO1', '', '']                  ← M103 表2-1-2（zh p23 / en p29）
```

`normalise_pad` は数字の脚注 `(7)` しか剥がさないので `LO1(PA0)` が残り、
`PAD_TOKEN`（`^[A-Z][A-Z0-9_+-]{0,11}$`）が括弧を通さない。`variant_row` も
`continues` も当たらないので**notes も出さず黙って落ちる**。M007 の `HO3` だけが
残っているのは en 版が別名なしで `HO3` と書くから（zh は `HO3\n(PB1)`）——それで
`reference` になっている。

| 型番 | 落ちている pad（別名） |
|---|---|
| CH32M007 ×4 | `LO1(PA0)` `LO2(PA2)` `LO3(PD0)` `HO1(PA3)` `HO2(PB0)`、＋zh側の `HO3(PB1)` |
| CH32M103G8R6 | `HO1(PA8)` `LO1(PB13)` `HO2(PA9)` `LO2(PB14)` `HO3(PA10)` `LO3(PB15)` |

同じ足は素の CH32V007 では普通の GPIO（E8R6 の lead 18〜23 = PA0/PA2/PD0/PA3/PB0/PB1）で、
M007 はそれをドライバ出力に振り替えて別名で GPIO 名を残している。CH32M030 は逆に
pad を `PB9` と書いて `HO0` を default 機能の側に置く（F-21 の M030 の22種と同じ pad 群）。

**直し方**: 括弧の GPIO 別名を `normalise_pad` で分離して pad 名を通す。
**要判断**: 別名 `(PA0)` をどう持つか。案は (a) 捨てる（GPIO として使えるかは資料が
言っていない）、(b) `pin_functions` に `signal=PA0` の行を足す——ただし `route` の値が
要る（`main`/`default` ではない。新しい値 `alias` を定義するか）、(c) `PA0-WKUP` と同じ
複合 pad 名 `LO1-PA0` にする——ただし既存の形は GPIO が先で順序が逆になる。
**推奨は (b)**: 資料が書いていることを落とさず、`port`/`pin` から引く consumer に
M007 の PA0 が lead 14 にあると見える。値の意味は `tables/README` に書く。

### F-32 添字が2組あるpad名の詰め方が誤り（`VVDD_IO_1`）

CH32V205DS0 の pin 表は `VDD_VIO_1`〜`_3` という pad を、**基準サイズの `V` と添字の
組を2つ並べて**書きます（図中の回転ラベルも `VDD_VIO_1` と綴る）:

```
V(基準 x=163)  D D _(添字 x=169-174)  V(基準 x=177)  I O _ 1(添字 x=182-190)
```

**当初「2つの pad 名が1セルに入っている」と読んだのは誤り**で、資料の綴りが
`VDD_VIO_1` という1つの名前です（同じ足を CH32V203DS0 は `VDD_IO_1` と書く——
版の違い）。いまの詰め方は**基準文字を先に、添字を後に**並べるので `V`+`V`+`DD_`+`IO_1`
＝`VVDD_IO_1` になります。x 順に並べれば `VDD_VIO_1` になり、pdfplumber の
`extract_text` もそう読みます。

- 該当: CH32V203CCT6 の lead 24/36/48、CH32V205CCT6 の lead 25/48（5行。zh/en とも同じ誤り）
- **直し方**: 添字を戻すとき、基準文字の並びの中に添字を x 順で差し込む（F-1 の
  `dewrap` の並べ方の問題。`build_pins` 側）。判断は要らない——**資料の綴りをそのまま採る**
  （layer-1 の綴りは証拠。`VDD_IO_1` へ寄せない）

## 次の作業（優先順）

**方針: 完全新規より過去の穴を埋めるほうが先**（2026-08-25 確認）。上から順に。

### 1. 穴を埋める（ツール側で直せるもの）

| 順 | 項目 | 何が直るか | 判断の要否 |
|---|---|---|---|
| 1 | **F-31** M007×4・M103のゲートドライバpad 26 lead | `pins`に26行、`pin_functions`に主機能26行が入り、lead欠けは資料が`未使用`と書く5型番だけになる。**黙って落ちていた**ので検出も足す（pad欄が空でないのに採らなかった行はnotesへ） | **要**: 括弧のGPIO別名`(PA0)`の持ち方（F-31節の(a)(b)(c)。推奨(b)） |
| 2 | **F-32** `VVDD_IO_1`→`VDD_VIO_1` | 5行の綴り。x順に詰めるだけ | 不要（資料の綴りをそのまま） |
| 3 | **F-21＋F-8** 語彙の穴 26種122行 | `pin_roles`の覆いが99.5%→**100%**、`candidates`の`unresolved`が36→32 function。所属は全部原典で確認済み（F-21節の表） | **要（2件）**: ゲートドライバの周辺名 `PREDRV`（推奨）か `HB` か／`SWIM`を`SWDIO`に畳むか`SWIO`として分けるか |
| 4 | F-24 残り8行（結合でもない空欄） | 資料の意図が決まらない。**zh/en両版で空欄が一致するか**だけ確かめて、一致なら「資料が空欄」として記録で閉じる | — |
| 5 | F-4 残り6行（片方の言語版だけの`reference`行） | 実害は小。F-31/F-32の修正で動くか見てから | — |

残る穴のうち**触らないもの**: `remap_fields`のreset_value空欄7行（RMが書かない。推測しない）、
F-6/F-7（資料側）、F-11（実機が要る。ユーザー作業）。

### 2. 過去情報の整理で残った判断（ユーザー）

- **`schemas/`・`devices/`（8 sample）・`tools/validate.py`・`docs/schema-notes.ja.md`を消すか。**
  2026-08-17のJSON schema草案で、`tables/`が正本になってから触っていない。
  READMEの「構成」冒頭がまだこれを主役として書いている（今回は文書一覧だけ直した）
- **R-20（レジスタマップ）**を受けるか。consumer側の要否から

### 3. 新規（穴が尽きてから）

| 順 | 項目 | なぜこの順 |
|---|---|---|
| 1 | **D4** 同期日時の表示 | `sources.csv`が既にあるので小さい。U5（原典に届かない人）が最初に見る |
| 2 | **B6** 評価ボード情報 | `eval_boards.csv`（117行）が既にあり、READMEに節を足すだけ |
| 3 | **B5** org TOP「機能から探す」 | A6（`features`/`feature_tags`）が済んで着手できる |
| 4 | **B4** 節構成の組み替え | U1→U2→U3順。B5/B6の節が揃ってから並べ替えるほうが1回で済む |
| 5 | **D7** GitHub Actions化 | 抽出の作り込みが落ち着いてから（計画は上記） |
| 6 | C1〜C3 画像 | 保留のまま |

## 資料側の問題台帳（原典の誤り・記録のみ）

ツールでは直せない、**原典（datasheet / RM / EVT / WCHのAPI）側の問題**を1か所に集めた。
表の中では `conflict`＋両論の `basis`、または脚注として現れる。WCHへ報告する材料でもある。
「どちらが正しいか」の判断根拠も添える。

| # | 資料 | 何が | こちらの扱い |
|---|---|---|---|
| F-6 | CH32V30x RM | I2S3のremap経路（`SPI3_REMAP`）を格子が書かない | 32 functionが`unresolved`のまま。V407/V467は書いているので決まる |
| F-7 | CH32V30x EVT header | `DVP_REMAP`の定義が無い（V407にはある） | 2 function unresolved |
| F-8 | CH32V003 RM **en版** | `AFIO_PCFR1` bit17（`ADC_ETRGINJ_RM`）の説明が規則転換の文（PC2）を誤って繰り返す。zh版と表7-13は正しい（PD1/PA2） | zh版で決める（F-8はツール側で解消可能） |
| F-33 | WCH 検索API | `CH32V20x_30xDS0.PDF`の版がAPI 3.5 / 表紙V3.9（メタデータがファイルより遅れる） | `documents.csv`は上書きしない。他75文書は一致 |
| F-43 | CH32V407 RM | I3C格子の列見出しが両列とも`I3C_RM=0`（誤植） | pin表の`I3C_SCL_1`が正。`build_candidate`に「同じ値に別padが居たら訂正しない」歯止め |
| F-44 | CH32X035 EVT header | `OPA_CTLR2_CMP_LOCK`のmaskが`0x2000`（bit13＝`PSEL3`と衝突）。RMはbit31 | `opa_cmp_registers`でconflict。使うとCMP3の正入力選択を壊す |
| F-45 | CH32L103 / CH32V205 EVT header | `ITRIMN`/`ITRIMP`が5bit（RMは6bit）、`HYS1_H`/`HYS2_H`がbit29/30（RMは19/29） | conflict＋両論 |
| F-46 | CH32V20x / V30x datasheet | 温度センサ`Avg_Slope`の最大値がzh 4.8 / en 4.7 mV/℃ | `adc_internal`でconflict＋両論 |
| E-3 | CH32V30x RM en版 / EVT header | `RAM_CODE_MOD`をen版は`[9:8]`（2bit）、zh版は`[9:7]`（3bit）。5通りの組合せに3bit要るのでzh版が正。`ch32v30x.h`/`ch32v4x7.h`の`FLASH_OBR_RAM_CODE_MOD`も2bit | `memory_configs`は全行conflict＋両論 |
| E-3 | CH32X315 EVT `Link.ld` | コメントが`CH32V4x7RM.PDF Table 32-3`を指して576K/136Kを挙げるが、X315のheaderにその構成は無い | 読まない（`build_memory`のnotes） |
| R-26-1 | CH32V103 EVT driver | `FLASH_ProgramPage_Fast`の`@brief`が256Bと書く。RMは128B、消去側と番地条件も128 | `flash_geometry`でconflict、RMを採る |
| R-25-1 | CH32V307 RM | TIM5=32bitの注が`CH32V20x_D8`/`D8W`を名指すが、V307はそのvariantを持たない | `timers`でconflict |
| R-24 | CH32V205 datasheet | ADCクロック上限がzh 96MHz / en 64MHz | `operating_conditions`でconflict |
| A6 | CH32H417 datasheet | 1.4.26節の見出しがzh/enで別の機能 | `features`は両方をそのまま転記 |
| 比較表 | CH32H417 datasheet | `CH32H417WEU6`のOPA数がzh=1 / en=2 | `product_attributes`でconflict |
| 2026-08-17 | CH32V407 EVT `ch32v4x7_gpio.c` | `GPIO_PinRemapConfig()`のUSART1上位bitがclear=PCFR2 bit26、set=`(GPIO_Remap & 0x2) << 26`＝bit27で1つずれる。headerとRMはbit26 | `extract_remap_fields`が観測値の一意性検査で自動検出し、この1 fieldの値は採らない |
| 2026-08-17 | CH32M030 RM | Table 6-15の`ADC_ETRGIN_RM`のpad対応が、datasheet Table 2-1・RMのregister説明/reset・EVT実装の3根拠と逆 | `0=PA14`、`1=PB6`（3根拠側）を採る。`extract_remap`が照合時に矛盾を提示 |
| 2026-08-17 | CH32V003 RM | `ADC_ETRGINJ_RM`のregister説明がregular trigger（PD3/PC2）の文を誤って繰り返す | datasheet Table 2-2とRM Table 7-13が一致する`0=PD1`、`1=PA2`を採る |
| F-31 | CH32M103 datasheet en | pin説明でHO*を「N型」（p31）と「P型」（p32）の両方で書く | 表には影響なし（記録のみ） |
| F-21 | CH32M030 EVT header | `ISP_CTLR_ISP2_QDET1_*`と綴る（RMは`QDET2`） | 語彙には使わない（記録のみ） |
| F-21 | CH32V003 datasheet | pin表2-1のPD4が`TIETR_2`（同じ行が表2-3では`T1ETR_2`。`I`と`1`） | 語彙で`T1ETR`へ寄せる。層1の綴りは残す |

いずれも**実機では未確認**。「正しい側」はもう一方の資料が複数一致することで決めている。

## 利用状況（優先順位の根拠）

| # | 誰 | 最初の問い |
|---|---|---|
| U1 | 買ってしまった人 | このピンは何？どう書き込む？Lチカの最短経路は？ |
| U2 | 選定する人 | 要求を満たす型番は？落とし穴は？ |
| U3 | 開発中の人 | この機能はどのピンに出せる？remap値は？例題は？ |
| U4 | 移植する人 | メモリマップ・割り込み番号・機械可読定義は？ |
| U5 | 原典に到達できない人 | 最新版は？いつ同期した？両言語あるか？ |
