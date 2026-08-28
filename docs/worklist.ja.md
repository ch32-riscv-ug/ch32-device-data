# 作業リスト

README自動生成の対象は**データシートとEVTを持つ12リポジトリのTOP**と**org TOP（.github）**です。両方とも特殊処理なしの全自動生成を目標にします。根拠は[docs/extraction-survey.ja.md](extraction-survey.ja.md)、データ構造は[evidence/README.ja.md](../evidence/README.ja.md)。

状態: ✅完了 / 🔜次 / ⬜未着手 / ❓要確認（人の判断待ち）

**解決済みの項目の詳細は [worklist-archive.ja.md](worklist-archive.ja.md) に移した**（2026-08-25 棚卸し）。
この文書に残るのは、索引表と、まだ生きている項目だけ。

## 進捗

テーブルごとの信頼度は [table-reliability.ja.md](table-reliability.ja.md)（どのテーブルがどこまで固いか・既知の穴の所在）。


| 区分 | 完了 | 残り |
|---|---:|---:|
| データ収集 | 9 | 0 |
| README生成 | 7 | 0 |
| 画像 | 0 | 3（保留） |
| 検査・運用 | 12 | 1（D7） |
| consumerからの依頼 | 9 | 0（R-27 は H417 の実測待ちが1行。R-20は機械収集ぶんまで、残りはconsumerの要否次第） |
| 既知の穴（F系） | 52 | 3 = 資料が決めない 1（F-4残り。実害なし）＋ 実機待ち 1（F-11）＋ 資料側の記録（F-24残り・F-33・F-43〜46・F-51・F-55の誤植2件） |

（2026-08-25 棚卸し＋2026-08-28 の監査ぶん。次にやる順は [次の作業](#次の作業優先順) にある）

## 着手順の方針

1. **自動取得できるもの**を先行（原典から機械抽出。腐らない）
2. 次に**自動取得できず更新頻度が低いもの**（一度書けば持つ）
3. **自動取得できず、そこそこ更新するもの**は「検出だけ自動化」して運用でカバーする

| 対象 | 更新の起点 | 頻度 | 検出手段 |
|---|---|---|---|
| エラッタ本文 | datasheet改版 | 年数回 | ✅ `scan_errata.py` |
| 翻訳辞書 | 新シリーズの未知ラベル | 新シリーズごと | ✅ CJK検査（CIが落ちる） |
| 画像 | 新シリーズ・新パッケージ | 新シリーズごと | ⬜ C2 check_images.py |
| 上流ツールの版 | MounRiverのリリース | 年数回 | ✅ `toolchains.yml`（週次・API取得） |

**載せないもの**: Arduinoコア・ツールチェーンの**チップ別対応状況**は生成物に入れません。自分たちがコントロールできない上流の状態を写すと必ず陳腐化し、しかも検出手段がないためです（サンプルの存在を対応宣言として扱わないルールとも整合）。org TOPからorg内リポジトリへのリンクは、リンク自体が腐らないので維持します。

**上流ツールの「版」は別**（2026-08-27）: どの `MRS_Toolchain_*` が最新か、は上流が公開しているJSON APIから機械で取れるので `catalog/toolchains.csv` に持ちます。上の表でいう1（自動取得できる）で、腐れば差分か赤いrunとして出ます。載せないのは**チップ別の対応状況**——人が書き写すしかなく、検出手段がないもの——だけです。

この方針により、残る全項目が「自動取得」か「人が書くが機械が検出する」のどちらかに収まります。

## A. データ収集

- [x] ✅ **A1 エラッタ** — 21件、全件が中英両版のページ根拠つきconfirmed。`tools/scan_errata.py`で増分検出（NEWがあれば終了コード1）
- [x] ✅ **A2 動作条件** — `evidence/operating_conditions.csv` 62行。クロック上限F_*と動作電圧V_DD。全27シリーズ
- [x] ✅ **A3 remap** — `remap_fields`/`remap_routes`（全行reference。根拠記録つき再実行で確定化するのは別課題）。2026-08-20に作り直し: `bits`がbitごとにregister名を持つようになり、PCFR1とPCFR2にまたがるselectorを表せる。`peripheral`/`role`列で`TX1`/`UTX`/`USART1_TX`の綴り差を吸収。value=0の既定経路を同じ表に収録。CH32V407/V467はRM未mirrorでも header+datasheet から生成する。`tools/check_tables.py`が表だけで整合を検査する（bit形式、値の幅、route値がvalid_valuesに含まれること）
- [x] ✅ **A4 公称主周波数** — U2/U1が最初に見る値。**現状は誤解を招く**: CH32V003のMax clockが電気的特性の50MHzで出るが、公称は48MHz（DS1ページ目「48MHz system main frequency」）。product_attributesには8シリーズ分しか無く自由文（`Max: 144MHz`、`40MHz@Zero-wait; Max: 192MHz@Non-zero wait`）。DS第1章の特徴リストから全シリーズ抽出し、`Main clock`列と`Fmax (HCLK)`列を分離する
- [x] ✅ **A5 EVT例題索引** — U1/U3への効果が最大。材料は全12リポジトリの`EVT/<FAMILY>_List_EN.txt`（周辺→例題→1行説明のツリー）に揃っている。パースして`evidence/evt_examples.csv`へ
- [x] ✅ **A6 機能フラグ（USB/Ethernet/CAN/PD/DVP…）** — `evidence/features.csv`新設（2026-08-23）。比較表からは作れない（[調査結果はarchive](worklist-archive.ja.md)）ので、**機能説明章の節見出し**を採った。節番号は言語に依らないので中英が厳密に対応する
- [x] ✅ **A7 メモリマップ** — `evidence/memory_map.csv`新設（2026-08-23）。**DS 1.2章ではなくEVTヘッダーの`*_BASE`から**。相対の連鎖を解く処理は`extract_addresses`が既に持っていた
- [x] ✅ **A8 書き込み方式** — **A6の副産物**（2026-08-23）。`1-wire Serial Debug Interface (SDI)`／`2-wire SDI Serial Debug Interface`が節見出しとして立っているので、`curated/`への手書きは不要だった
- [x] ✅ **A9 割り込みベクタ表** — `evidence/interrupts.csv`新設（2026-08-23）。**RM側と書いたのは材料の見落とし**で、EVTヘッダーの`IRQn_Type`列挙が番号・名前・説明を全部持っている。variantで番号が入れ替わるので`#if`の条件を`condition`列に持つ

## B. README生成

- [x] ✅ **B1 12リポジトリのTOP生成** — Series/Documents/比較表/ピン表/remap/Errata/Diagrams。日次でミラーが取得
- [x] ✅ **B2 org TOPの生成** — 現行はリポジトリ一覧＋横断文書＋toolchain
- [x] ✅ **B3 org TOP「型番から探す」** — **今あるデータだけで作れる**（series.csv: series→family、products.csv: part_number→family）。CH32M007がCH32V006に、CH32M103がCH32L103に、CH32V317がCH32V307に入っている件が検索者に見えるようになる。～~これができれば`curated/readme-extras/CH32V20x.md`（V205分離の手書きNotes）を削除して**特殊処理ゼロ**にできる~～ → **この見通しは誤りだった**（2026-08-24に確認。手書きNotesは消さない。[記録](worklist-archive.ja.md)）
- [x] ✅ **B4 節構成の組み替え** — `build_readme.render`がU1→U2→U3順（Quick start → Series → Product comparison → Pinout reference → Pin definitions → remap → Block diagrams → Errata → EVT examples → Documents → Evaluation boards → Reference）。棚卸しで確認（2026-08-26）
- [x] ✅ **B5 org TOP「機能から探す」** — `feature_tags.csv`（tag→series）から`## Find by feature`表をorg TOPに生成（2026-08-26）。datasheet粒度のタグ（`precision=datasheet`）はその旨を注記
- [x] ✅ **B6 評価ボード情報** — `eval_boards.csv`（117行）から`### Evaluation boards`節を生成済み（`eval_board_lines`）。棚卸しで確認（2026-08-26）
- [x] ✅ **B7 Series表の`varies-by-package`を空欄にしない** — 利用者の指摘（2026-08-27）。CH32V303/V305のFlash・SRAMが`-`だったのは「資料に無い」ではなく「型番で違う」。`series_bytes`が型番側の実値を全部並べる（`128K/256K`）。**空欄だと不明との区別が読む側に付かない**のが理由。複数値になる族のREADMEには読み方の1行を添える。影響: V006・V103・V20x・V307の4リポジトリ

## C. 画像（保留）

**現時点では生成READMEに画像を使いません。** 切り出しの品質が実用水準に達していないためです。ピン配置図は「パッケージ→型番→データシート」の対応表で代替しています。

- [ ] ⬜ **C1 切り出し品質** — `tools/extract_images.py`は134枚を生成できるが、図の縁の判定・ファイル名と図中型番の一致（82枚中6枚が不一致）に課題が残る
- [ ] ⬜ **C2 ページ番号リンク** — `#page=N`はGitHub Pages配信のPDFで機能する（`content-type: application/pdf`を確認済み）。抽出時にページは分かるので`tables/figures.csv`として持てば、対応表からページ直リンクにできる
- [ ] ❓ **C3 シリーズ構成図** — 原典のデータシートには無く、WCH製品ページ由来。手作りは27シリーズ中10枚のみで17枚不足。`tools/build_system_figures.py`でtables/から生成もできるが見た目が別物。**採用は保留**

### 不足している手作りsystem図（17シリーズ）

CH32H415, CH32H416, **CH32H417**, CH32M007, **CH32M030**, CH32M103, CH32V002, CH32V004, CH32V005, CH32V007, CH32V305, CH32V317, **CH32V407**, CH32V467, CH32X033, **CH32X305**, **CH32X315**

太字はファミリーの主力シリーズ。CH32M030・CH32V407・CH32X315・CH32H417は図が1枚もない状態です。

## D. 検査・運用

- [x] ✅ **D1 参照結合検査** — `tools/check_tables.py`が全50テーブル（目録8・証拠33・索引9）の参照結合・書式・数の不変量を検査（`check_counts.py`が比較表の数とpin側の数を突き合わせる）
- [x] ✅ **D2 中国語混入検査** — `#`より左のデータ列にCJKがあればCIが落ちる
- [x] ✅ **D3 エラッタ増分検査** — `tools/scan_errata.py`（ミラーPDFが要るのでCIではなく手動運用）
- [x] ✅ **D5 画像の検査** — 寸法異常と同一切り出しの共有を機械検出（目視の前段。実際に4件の欠損を捕捉）
- [x] ✅ **D6 読んだ原典の版を記録** — `catalog/sources.csv`新設（2026-08-23）。mirror 12本のcommitとその日付。**生成時刻は入れない**（毎回書き換わると「差分が出たら異常」の判定が使えなくなる）。生成物の差分の原因を「入力が変わった」と「再生成を忘れた」に切り分けるため
- [ ] ⬜ **D7 生成のGitHub Actions化** — 日次起動・datasheetかEVTが変わっていたら全生成。**計画のみ**（下記）。抽出の作り込みが落ち着くまでは手動
- [x] ✅ **D8 上流ツールの版の定期取得** — `catalog/toolchains.csv`新設（2026-08-27）。MounRiverのIDE・`MRS_Toolchain_*`・ベンダのチップ対応パックの**最新版15件**を、ダウンロードページの裏にある公開JSON APIから取る（`tools/build_toolchains.py`）。`.github/workflows/toolchains.yml`が毎週月曜13:20 UTCに取り直してcommit（update.ymlと同じconcurrency群なのでpushがぶつからない）。行ごとに**配信側をHEADして掲載と突き合わせ**（サイズ一致でconfirmed）。ダウンロードURLは署名つきで要求元IPに紐付くため表には入れず、URLを返すAPIを`download_api`に持つ
- [x] ✅ **D10 カタログの写しを担当ぶんだけにする** — 各 mirror が `documents.json` に**全76文書を丸ごと**持っていた（13 mirror すべて md5 一致。担当は3〜7件）。無関係な文書の download id が1つ変わっただけで13 mirror 全部に `update (automated)` の空身のコミットが立ち（実例: `CH32V003` の `28d2fc8` は `documents.json` だけの変更）、`catalog/sources.csv` が持つ mirror の HEAD が動くので**「入力が動いた」と「再生成を忘れた」の切り分け（D6 の目的）が効かなくなっていた**。`templates/update.sh` が担当ぶんだけ書くようにした（40,862 → 2.2〜4.9 KB）。取得失敗時の写しとしての役目は変わらず（`plan()` はこの行だけを読む）、**空スライスは既存の写しを上書きしない**という歯止めも追加。全13 mirror でオフライン検証済み。⚠ **13の mirror repository への反映は別作業**（このrepoはテンプレだけ持つ）
- [x] ✅ **D12 表のヘッダと生成器の列定義を突き合わせる** — 「ツールを書き換えたのに表を作り直していない」を機械で見つける（`check_tables.column_drift`）。D10 の鮮度検査は **PDF 不要な導出物しか見られない**ので、`evidence/` のずれは射程外だった。**中身の鮮度は無理でも、列の食い違いなら CSV の1行目とソースの定数を読むだけで分かる**。`tools/build_*.py` の `*COLUMNS` を **`ast` で読む**ので、pdfplumber を要する生成器も import せずに対象にできる。50表すべてに「どの生成器のどの定数か」の対応を持ち（`COLUMN_SOURCES`。`paths.py` が場所を1箇所で決めているのと対）、対応の無い表があれば落ちる。`build_tables.py` の6表は**データ列だけを定数に持ち出所列は書き出し時に足す**設計なので、「定数がヘッダの接頭辞で余りが出所列」なら通す。**書く前の測定段階で F-54 の2件目（`timers`）を見つけた**
- [x] ✅ **D11 カタログ更新が導出物を置き去りにしないようにする** — `update.yml` は `documents.csv` だけ再生成して commit していたが、**生成READMEは各文書の版番号を引用している**ので置き去りになっていた（実例: `88f7a7a update catalogue (automated)` の直後、README は EVT v1.4 のまま documents.csv は v1.5）。D10 で入れた鮮度検査があると**日次 job が自分の変更で翌 run を赤くする**ので、同じコミットで4本回すようにした（stdlib のみ・数秒。順は依存順）。実測で緑を確認
- [x] ✅ **D9 語彙のdoctestをCIで回す** — `tools/signal_vocabulary.py` の doctest は**規則そのものの説明**だが、`__main__` でしか走らないので誰も回しておらず、F-8 で `AETR2` を語彙へ入れたあとも「未解決のはず」と主張し続けていた（2026-08-28 の監査が手で回して発見）。`check.yml` に1行足した。他の tools に doctest は無い（実測）
- [x] ✅ **D4 同期日時の表示** — 各READMEの冒頭に`sources.csv`のmirror commit（リンク）と日付を出す（`synced_line`。2026-08-26）。生成時刻は出さない（冪等性）


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
| 読んだ版の記録 | **`catalog/sources.csv`**（2026-08-23）。mirror 12本のcommitとその日付 |

手作業として残るのは**ローカルcloneの`git pull`**と**重い抽出**の2つだけ。

#### やること

**日次で起動し、datasheetかEVTが変わっていたら全生成する。**

```
1. mirror 12本を clone/pull（shallow で可。EVTとdatasheetだけあればよい）
2. catalog/sources.csv が記録する commit と、いまの mirror の HEAD を比べる
3. どれも同じなら **何もせず終わる**（生成物は最新のはず）
4. 変わっていたら全生成 → 検査 → 差分を報告
```

3が要点で、**入力が動いていないのに差分が出たら「再生成モレ」**、動いていれば
「入力が変わった」。`sources.csv`を入れたのはこの切り分けのため。

#### 全生成の中身と時間

`evidence/README.ja.md`の生成順そのまま。実測で`build_all`が**2並列16.6分**、
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
| R-20 | レジスタマップ（D-1〜D-8） | 🔧 **機械的に集められる部分を実装**（2026-08-25、`tools/build_registers.py`）。`register_blocks` 676行（D-1）・`registers` 4,995行（D-3）・`register_fields` 33,365行（D-4。field 24,792のうちRM一致6,829・conflict 38）・`register_layouts` 353行（D-5。型数は調査どおりI2C 4/GPIO 6/USART 8…）。D-6は`interrupts.csv`。**RM zh版の絶対アドレス表でD-1/D-3を裏取り済み**（2026-08-26: 8,369行のうち5,110行が一致・不一致4、blocks 548 confirmed、registers 2,762 confirmed）。**D-7 も実装**（2026-08-26: `dma_requests.csv` 650行。RMのDMA章の格子をzh/en両版で照合、577 confirmed。H417はDMAMUXの番号表）。**未着手**: 構造体を持たないdefine群（M030 `UART_*`等1,591行）のmember対応。見方は`tables/README`。[register-map-survey.ja.md](register-map-survey.ja.md) |
| R-24 | クロック関連データ（C-1〜C-8） | ✅ **C-1〜C-8を実装**（2026-08-21）。`clock_configs.csv`・`clock_prescalers.csv`・`clock_sources.csv`＋`operating_conditions.csv`拡張 |
| R-24追補 | クロック表の追補（A-1〜A-4）とremapの要確認（B） | ✅ **実装済み**（2026-08-21）。`clock_symbols.csv`・`evt_variants.csv`新設、`operating_conditions.csv`に`typ`列、remapの誤帰属を修正 |
| R-24追補2 | クロック切替に要るレジスタ/ビットとflash latencyの取りこぼし（D-1〜D-4） | ✅ **実装済み**（2026-08-21）。`clock_symbols.csv`を77→429行に拡張、`clock_init.csv`新設、`clock_configs`に`flash_sck_div`列 |
| R-24追補3 | CH32V103のSTKレジスタほか（E-1〜E-5） | ✅ **全件クローズ**（2026-08-22）。E-1は探されたレジスタが存在せず`systick.csv`で回答、E-2はRMに記述なし、E-3は`memory_configs.csv`新設、E-4/E-5は`clock_symbols`の集め方を直した |
| R-25 | 表の追加依頼3件（timers・port/pin・preferred印） | ✅ **2件実装・1件は回答**（2026-08-25）。`timers.csv`新設、`pin_roles`に`port`/`pin`。preferred印は「電源投入時の状態」なら資料が既に持つ（`route`の`main`/`default`）ので列を足さず`tables/README`に区別を書いた |
| R-26 | 追加テーブル4件＋参考1件 | ✅ **全5件実装**（2026-08-25）。`flash_geometry`・`opa_cmp_registers`・`adc_internal`・`usbpd_plumbing`・`clock_enables` |
| R-27 | debug module の DATA0/DATA1 レジスタの hart 側アドレス（family別） | ✅ **実装**（2026-08-26）。`evidence/debug_data.csv` 12 family（confirmed 7・reference 4・missing 1=H417）。`tools/build_debug_data.py`。下の「R-27」参照 |

### R-27 debug module の DATA0/DATA1 レジスタの hart 側アドレス（2026-08-26 受領・同日実装）

**結果**: `evidence/debug_data.csv`（family × data0/data1。[evidence/README](../evidence/README.ja.md) の節）。値は3群——V2 系 `0xE00000F4`、V4 系 `0xE0000380`、V3 系の多く `0xE0000340`（M030・V205・V407・X315）、**ただし V3A の V103 は `0xE0000380`**。core 世代では決まらないので family 単位。EVT debug.c の define（全 debug.c で一致）× QingKe マニュアル hartinfo 表（V2/V4 は固定値、V3/V5 は「読め」）× 実測5件。**H417 は EVT に define が無く missing**——hartinfo の実測があれば `curated/debug-data-measured.json` に足して埋まる。

Arduino コア側で SDI print（DMDATA0/1 mailbox 経由の printf）を実装したところ、**書き込み先
アドレスが core 世代で違う**ことが実測で分かった。現状は V4 系の `0xE0000380` を既定にして
V003 だけビルド時に上書きしている状態なので、生成で正しくするために family（または core）別の
値を表に。

consumer の実測（WCH-LinkE 経由で RISC-V DM の `hartinfo.dataaddr` を読んだもの）:

| family | core | DATA0 / DATA1 |
|---|---|---|
| CH32V003 | QingKe V2A | `0xE00000F4` / `0xE00000F8` |
| CH32V103 | V3A | `0xE0000380` / `0xE0000384` |
| CH32V203 | V4B | `0xE0000380` / `0xE0000384` |
| CH32X035 | V4C | `0xE0000380` / `0xE0000384` |
| CH32L103 | V4C | `0xE0000380` / `0xE0000384` |

V003 の値は EVT の SDI_Printf 例（`DEBUG_DATA0_ADDRESS = 0xE00000F4`）と一致、V4 系は
SDI_Printf 例が `0xE0000380` を使っていて実測とも一致。

- **欲しいもの**: 残りの family——V00x（V002/004/005/006/007）・M 系・X033・V20x/V30x の各 die・
  X305/X315・H41x
- **出所の候補**: QingKe プロセッサマニュアル（V2/V3/V4/V5）の debug 章、各 EVT の SDI_Printf 例の
  `#define`（機械抽出できる。EVT 全ツリーの grep）、hartinfo の実測
- **列の案**（置き場所・形式は任せる。`cores.csv` があるので core 単位でもよい）:
  `family`（または `core`）, `dm_data0_addr`, `dm_data1_addr`, `confidence`, `basis`
- **方針メモ**: まず EVT の SDI_Printf 例の define を全 family で機械抽出して証拠の表にし
  （`evidence/debug_data.csv` 案。出所 `evt(<file>)`）、QingKe マニュアルの debug 章の記述と
  突き合わせて confirmed へ。core 世代で決まるなら `catalog/cores.csv` に列を足す形も検討。
  V003 の実測値と EVT define の一致は consumer 側で確認済み

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
| F-6 | CH32V30xのRM格子がI2S3のremap経路を書いていない | 32 function・4 series | ~~資料~~ ツール | ✅ **修理済み**（2026-08-28）。**F-8・F-47 と同じで、資料側ではなくツール側だった。** I2S3 は I2S モードの SPI3 で専用の remap フィールドを持たず、`SPI3_REMAP` が両方を動かす——`build_candidate` のコメント自身がそう書いていたのに、周辺名からは selector に当たらず、pad ベースで決めると PC7 の `I2S3_MCK` が pad を共有する TIM8 に化けるため**意図的に未決定**にしていた。F-47 と同じ**名前ベース**の段（`FIELD_OF_PERIPHERAL = {"I2S3": "SPI3"}` → `how=shared-field`）にすればその危険は起きない。根拠は資料そのもの: **CH32V407/V467 の RM 格子が `SPI3_REMAP` の値0/値1の下に `I2S3_CK`/`I2S3_SD`/`I2S3_WS` を SPI3 と同じ pad で名指ししている**。V30x に当てた結果はV407 の格子と完全一致（値0=PB3/PB5/PA15/PC7、値1=PC10/PC12/PA4）。`candidates` の `unresolved` は **32 → 0**、`pinout` の selector 未決定は remap-N 35行＋default 67行が埋まった |
| F-7 | CH32V30xのheaderに`DVP_REMAP`が無い | ~~2 function~~ **0**（下記） | 資料 | 記録のみ。**2026-08-28 に見直したら穴ではなかった。** V30x の pin 表は DVP を**既定機能としてしか書かない**（`pin_functions` 184行すべて `route=default`。V407/V467 は `remap-N` を90行持つ）ので、解決すべき `remap-N` の行がそもそも無い。header に DVP の field が無いことも datasheet と整合していて、3つの出所が食い違っていない。`default` 行に selector が付かないのは remap フィールドを持たない周辺の通常の姿（全体で4,128行ある。`check_tables.remap_selector_coverage` の註）。「V30x の silicon に DVP_REMAP ビットが本当は在るのか」は資料から答えられず、**表に現れる違いも無い**ので、V407 の header から借りることはしない |
| F-8 | CH32V003の`AETR`がADC 2 fieldのどちらか決まらない | 4 function・4 part | ~~資料~~ ツール | ✅ **修理済み**（2026-08-25）。`AETR`→(ADC1, RETR)、`AETR2`→(ADC1, IETR)を語彙に、`RETR`↔`ETRGREG`・`IETR`↔`ETRGINJ`の対応（`ROLE_FIELD`）でselectorを名前から決める。V003の4型番は未解決0、`remap_routes`に`ETRGREG`の経路（PD3/PC2）が入った。[記録](worklist-archive.ja.md) |
| F-9 | USBが48MHzを要求する根拠が散文 | 22行 | ツール | ✅ **実装済み**（2026-08-22）。48MHzは全familyの話ではなかった。[記録](worklist-archive.ja.md) |
| F-10 | CH32V205・CH32X315のRMから経路が0件 | V203CCT6のUSART5-8 | 資料/ツール | ✅ **原因判明**（2026-08-22）。**AFIO remapを持たない世代**だった。[記録](worklist-archive.ja.md) |
| F-11 | WCH-Link系ファームウェアの版番号が確定しない | — | 資料 | 🔜 実機で1回突き合わせる |
| F-12 | AF番号で多重化するfamilyの選択レジスタが未収録 | 240行 | ツール | ✅ **実装済み**（2026-08-22）。`evidence/pin_alternate.csv`新設。[記録](worklist-archive.ja.md) |
| F-13 | pin表のslashが改行で落ちてsignalが連結する | 32種・17 part | ツール | ✅ **修理済み**（2026-08-22）。F-1の副作用。[記録](worklist-archive.ja.md) |
| F-14 | `flash_bytes`が零等待領域ではなく総容量を指すfamilyがある | 18 part | ツール | ✅ **修理済み**（V30xは2026-08-22、X305/X315は2026-08-23）。[記録](worklist-archive.ja.md) |
| F-15 | 比較表の**行グループ**（左セルが複数行にまたがる）が1行に潰れる | H41x 5 part・480行 | ツール | ✅ **修理済み**（2026-08-22）。`sram_bytes`が896KBのうち128KBだった。[記録](worklist-archive.ja.md) |
| F-16 | 脚注の**全角括弧**を剥がしていない | 38 pad・364行 | ツール | ✅ **修理済み**（2026-08-22）。pin表の行が丸ごと落ちていた。[記録](worklist-archive.ja.md) |
| F-17 | **ページ境界で切れた行**が丸ごと落ちる | V407/X035 27行 | ツール | ✅ **修理済み**（2026-08-22）。[記録](worklist-archive.ja.md) |
| F-18 | lead番号に脚注が付いたまま出る（`int`にできない） | 16行 | ツール | ✅ **修理済み**（2026-08-22）。[記録](worklist-archive.ja.md) |
| F-19 | 比較表が**ページ境界**をまたぐと継続ページを読めない | en 141行が欠落・H417 4ラベル | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-20 | 行グループ見出しが属性名に混ざる（`Communication interface CAN`） | 全family | ツール | ✅ **実装済み**（2026-08-24）。`group`/`label`を新設。[記録](worklist-archive.ja.md) |
| F-21 | `pin_roles`が語彙で覆えない signal 110種 | 1046行（4.4%）→**0行（100%）** | ツール | ✅ **修理済み**（2026-08-25）。最後の26種（M030の22種→`PREDRV`/`ISP1,2`/`QII1,2`/`ISINK`/`ISOURCE`/`PWR`/`SDI`、V003の`AETR`/`AETR2`/`TIETR`、V208の`ANT`→`BLE`）を原典で所属確認して語彙へ。`KNOWN_ROLE_GAPS`は空。[記録](worklist-archive.ja.md) |
| F-22 | セル内の折り返しで**空白が落ちる**（`Communicationinterfaces`） | 全family | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-23 | READMEの比較表の**行の並びが資料の並びでない** | 全family | ツール | ✅ **修理済み**（2026-08-24）。`order`列を新設。[記録](worklist-archive.ja.md) |
| F-24 | **lead番号のセルが縦結合された行**を落としている（同じ足に2つのpad） | 42行 → 8行 | ツール→資料 | ✅ **修理済み**（2026-08-25）。残り8行は**zh/en両版とも空欄**と確認（2026-08-26: M007K8U7 `VSS`、V203 LQFP48/QFN48X7 `VSS`、V208 QFN68 `VSS_4`、V20x TSSOP20/QFN28 `PA8`、V20x QFN68 `VDD_IO_3`、X035 TSSOP20 `PB19`、X315 WCU6 `VDD`）。資料が空欄なので表にも無い——記録のみ。片方の版だけ空欄の7セル（H417 PB10、M103 PA13/PB5、V203 PB8×2、V205 PD0×2）は他方の版から復元され`reference`行になっている（F-4の残りと同じもの）。[記録](worklist-archive.ja.md) |
| F-25 | pad名が**8文字を超えると落ちる**（`PC13-TAMPER-RTC`） | 103型番中99がPC13を持たなかった | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-26 | 同じpadの**封装別の行**を「ページの続き」と誤認 | CH32X035 PC3 | ツール | ✅ **修理済み**（2026-08-24）。[記録](worklist-archive.ja.md) |
| F-27 | CH32V103のTIM3 remap値が**RMと食い違う**（pin表の接尾辞が誤り） | 18行 | 資料/ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-28 | **CH32L103のremap格子を1行も読めていない** | 0 → 195経路 | ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-29 | pin type欄が`USB3.0`だと落ちる | H417のUSB3.0差動4 pad×4型番 | ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-30 | 語彙が**1文字の周辺**を作る（`Q_DET1`→周辺`Q`） | 12行 | ツール | ✅ **修理済み**（2026-08-25）。[記録](worklist-archive.ja.md) |
| F-31 | **封装のlead数とpins.csvが合わない型番が10** | 26 lead | ツール/資料 | ✅ **修理済み**（2026-08-25）。pad欄の`LO1\n(PA0)`（GPIO別名の括弧）を読めるようにし、`pins`に26行・`pin_functions`に主機能26行＋**`route=alias`30行**（別名の持ち方は`tables/README`）。~~残る5型番（V203RBT6の48・LQFP100の73）は資料が`未使用`と書く足で、表に無いのが正しい~~→ **この結論は誤りだった**（2026-08-28 の監査で発覚）。資料はその行を印刷していて、落としていたのはこちら。**F-49** で修理。[記録](worklist-archive.ja.md) |
| F-32 | 添字が2組あるpad名を**基準文字→添字の順に詰めて**`VVDD_IO_1`にしている（資料は`VDD_VIO_1`） | CH32V205DS0 の 3 pad・5行 | ツール | ✅ **修理済み**（2026-08-25）。上下の行の語数が同じなら列ごとに組む（`interleave`）。`VDD_VIO_1`〜`_3`に。[記録](worklist-archive.ja.md) |
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
| F-47 | CH32V407/V467の**Ethernet LED（`LED0`/`LED1`、remap-1）のselectorが決まらない** | 8 function・4 part | ツール | ✅ **修理済み**（2026-08-25）。headerは`AFIO_PCFR1_ETHPHY_LED_REMAP`とPHYの名で綴り、語彙の(ETH, LED0)からは名前でも接頭辞でも当たらなかった。`FIELD_OF_SIGNAL`で結び、`remap_fields`に`afio-ethphy-led-remap`（V407/V467）、`remap_routes`に4経路（値0=PE8/PE9、値1=PD14/PD15）。`unresolved`は**32＝F-6だけ** |
| F-49 | 資料が「使わない」と書いた足（`NC`・`NC.`・`未使用`・`Unused`）を pad と見ておらず、**落ちるだけでなく直前の行の pad 名を継いで別の pad に化けていた** | 6行（うち1行は誤った pad 名） | ツール | ✅ **修理済み**（2026-08-28）。`extract_pins.NO_CONNECT` を pad の形の判定より先に見て、綴りを `NC`・`kind=nc` に正規化（露出パッドを `EP` と綴るのと同じ）。CH32V203RBT6 の lead 47 は `VDD_2`→`NC`、48 が復活。CH32V205VCT6・CH32V303/307/317VCT6 の lead 73 も。**封装のlead数との照合を検査に入れた**（`check_tables.pin_numbering`）——F-31 で「表に無いのが正しい」と閉じてしまったのは、この不変条件を機械が見ていなかったから |
| F-50 | candidate が**別の series・別の封装の pin 表の列**を読んでいた（1つの datasheet に同じ封装の列を持つ表が複数あり、先に当たった方を採っていた） | `remap_routes` 128行（**CH32V317 117・CH32X033 11**）＋ CH32M030C8U3 の pinout 全48 lead | ツール | ✅ **修理済み**（2026-08-28）。監査は「X033 の17行が routes に無い」という症状だけを報告したが、原因を追うと**同じ欠陥がもっと大きく出ていた**:<br>・**CH32V317** が `CH32V303/305/307引脚定义`（表3-1）を読み、V307 の `ETH_*`54 経路・`FSMC_*`34 経路が**そのまま CH32V317 の経路として**入っていた。88 経路が V307 と1つ違わず一致していたのが証拠。CH32V317 自身の表（表3-2）に `ETH_`/`FSMC_` は1つも無い（表3-4 `引脚复用和重映射功能` は RGMII を含み V307 固有対81件を持つので**V307側の表**。V317 の裏づけにはならない）<br>・**CH32X033** が `CH32X035引脚定义` を読み、series 全体の経路が別の pad 由来<br>・**CH32M030C8U3** が `QFN48X7_A` ではなく `QFN48` の番号列を読み、pinout が2 lead ずれていた（`want.startswith(got)` の前方一致が**より短い別の封装**に当たる）<br>直し方は2つ。(1) ordering 表の封装名は**完全一致を全列で先に探す**（綴り違いの前方一致はその後）。(2) 表の見出しは封装しか名乗らないので、**caption の scope** で決着させる（`build_all.choose_table`。`build_pins` が既にやっていた `extract_pins.scope_allows` と同じ梯子）。ただし **caption は同じ強さの一致どうしの決着にしか使わない**——`TSSOP20(F8)` の `(F8)` は容量グループの名前で、CH32V203F8U6 は「F8 だが QFN20」なので caption を先に見ると別の表に行く（実装中に1度踏んだ）。`COLUMN_METHODS` で規則の強さを先に順位づける<br>**気付けなかった理由**: `pin_functions`（PDF直読み）と `remap_routes`（candidate 経由）は同じ pin 表の2つの読みなのに、突き合わせる検査が無かった。`check_tables.routes_backed_by_pins` を足した（旧データで128行を検出、いま0行） |
| F-51 | CH32H417 の PF12/PF13/PE7 の remap 欄に**中文版だけ**が `UHSIF_PORT0_1`〜`_2` と書く（英語版は空欄）。RM の格子はその3 padを値0（既定）に当て、値1は PC1→`PORT3` のようにずらす | 3行 | 資料 | 記録のみ（2026-08-28）。`pin_functions` では `reference`／`pin-table:zh` として残り、`pinout` の selector は空。台帳（下）にも記録 |
| F-52 | `operating_conditions.csv` に**完全同一行の重複**（CH32V303/305/307/317 の `F_PLL_IN`） | 1行 | ツール | ✅ **修理済み**（2026-08-28）。1ページに PLL の表が変種ごとに3つあり（`F_PLL_OUT` が 144／75／100MHz）、`F_PLL_IN` は2つの表が同じ 3〜25MHz を書く。この表はどの表から来たかを持たないので同一行になっていた。値・確度・根拠まで同じ行は1行にする |
| F-53 | pin 表の**見出し行がページ境界で割れている**と、その塊を丸ごと読み落とす（見出しは2行——列の語と縦書きの封装名——で、どちらのページも単独では layout を言えない） | CH32X305RCT6 の lead 1〜25（英語版のみ）＝ `pins` 26行・`pin_functions` 89行が `reference` どまり | ツール | ✅ **修理済み**（2026-08-28）。当初は「データは欠けていないので見送り」と判断したが、試作して差分を測ったら**期待した回復だけ**だったので採用した。`find_pin_tables` を**塊を先に集め、layout が決まってから読む**形にする（読む順は変えないので、ページ境界で切れた行 `continues` と封装別の行 `variant_row` の判定はそのまま）。<br>実測: 行数は 4,563／28,483 で不変、lead の増減0、pad の綴りの変化0、**確度は上がるだけ**（pins 26行・pin_functions 89行が `reference`→`confirmed`、降格0）。回復したのは全て CH32X305RCT6 で、`pins` の `reference` は **33 → 7** になり、残る7行は F-4 の残り（H417 PB10・M103 PB5/PA13・V203 PB8×2・V205 PD0×2）と完全一致した——**`pins` の未確定が記録済みの資料側の穴だけになった** |
| F-54 | **2026-08-26 の「導出列外し」が CSV に反映されていなかった** （`evidence/remap_routes.csv` の `peripheral`/`role`、`evidence/timers.csv` の `channels`/`complementary`） | 2表・4列 | 運用 | ✅ **解消**（2026-08-28〜29）。どちらも生成器の定数からは外れていたのに CSV を作り直しておらず、**ツールと生成物が数日ずれたまま**どの検査にも掛からずにいた。`remap_routes` は F-50 の再生成で、`timers` は `column_drift` を書く途中の測定で発覚して再生成した。語彙で導出した読みは索引が持つ（[data-layout](data-layout.ja.md) の「証拠に語彙導出列は不可」）——`index/routes.csv` と `index/timers.csv` が `pinout` から独立に導出する。**consumer には列が減る変更**なので単独の差分として見えるようにここに記録する。同じことが起きないよう **D12** を入れた |
| F-55 | `表3-4 引脚复用和重映射功能`（V30x datasheet）を**どの抽出も読んでいない** | — | ツール | ✅ **調べて穴でないと確認**（2026-08-28）。読む価値が無い。pad × 周辺群の相互参照表で、(GPIO名, signal) 414対のうち **410対が既に `pin_functions` にある**——表3-1 の既定/重映射列の言い換えだった。最初に「217対が無い」と見えたのは切り出しが粗かったせいで、内訳は remap 接尾辞つきの綴り（`TIM2_CH1_2` は `signal=TIM2_CH1`＋`route=remap-2`）202対と、複合 pad 名（`PA0` ↔ `PA0-WKUP`・`PC14` ↔ `PC14-OSC32_IN`）。残る4対も穴ではない: **誤植2件**（`ADC_1N1`←`ADC_IN1` の `I`→`1`、`ETH_RMII_RXDO`←`ETH_RMII_RXD0` の `0`→`O`。台帳へ）と、`PD0`→`OSC_IN`・`PD1`→`OSC_OUT` の2件（小さい封装で lead を共有する事実を、封装の文脈を持たないこの表が「多重化機能」として書いたもの。`pins` の共有 lead が既に持っている） |
| F-56 | pad 欄の**折り返しの2行目を落とす表があり、片方の版だけ不完全な綴りになる**（`PC14-`） | 1 pad・1型番（`pins.csv` 唯一の conflict） | ツール | ✅ **修理済み**（2026-08-28）。**資料が食い違っていたのではない**——同じ中文版が 表3-1-1 では `PC14-\nOSC32_IN(2)` と両方取れるのに、表3-1-4（LQFP64M）では `PC14-` だけになっていた。英語版だけが完全な綴りを持つので `conflict` が立ち、確度が `reference` に落ちていた。**同じ版の別の表の綴り**を根拠に補う（`extract_pins.complete_truncated_pads`。`datasheet_names` が signal に対してやっているのと同じ考え方）。`^P[A-H]\\d{1,2}-$` で判定するので `VREF-` のような本物の `-` 終わりには当たらない（全 datasheet で実測）。**`pins.csv` の conflict が 1 → 0** になった |
| R-25 | consumerからの表の追加依頼3件（2026-08-25受領） | — | 依頼 | ✅ 2件実装・1件は回答（`route`の`main`/`default`を文書化）。[記録](worklist-archive.ja.md) |
| R-26 | consumerからの追加テーブル依頼4件＋参考1件（2026-08-25受領） | — | 依頼 | ✅ **全5件実装**（2026-08-25）。[記録](worklist-archive.ja.md) |

### F-11 WCH-Link系ファームウェアの版番号（[link-firmware-survey](link-firmware-survey.ja.md)）

`evidence/link_firmware.csv`（10行）と`tools/build_link_firmware.py`を作り、
ファイルの同定・sha256・取得の自動化まではできた。**版番号だけが確定していない。**

配布物が名乗る版（`wchlink.wcfg`の`CH32V307Ver=42`等）と、実機がUSBで申告する版
（`2.12`のような`major.minor`）の対応が取れない。バイナリに応答テンプレートは
入っておらず、配布ページはJS生成で版情報を持たない。**この対応が付くまで
「あなたのは古い」を言う表としては使えない。**

次に試すのは実機での1回の突き合わせ（更新前後で`minichlink`の表示を控える）。
詳細と他の案は調査ドキュメントに書いた。

### F-6〜F-8 資料側で決まらないもの（記録のみ）

- ~~**CH32V30xの`I2S3_*` remap-1**~~ → **F-6 は修理済み**（2026-08-28。資料側ではなくツール側だった。
  V407/V467 の格子が同じ `SPI3_REMAP` の下に I2S3 を名指ししているので、周辺の対応
  （I2S3 = I2S モードの SPI3）を語彙に入れて決めた）
- **CH32V30xの`DVP_*`**。CH32V407にはある`DVP_REMAP`がV30xのheaderに無い
- ~~**CH32V003の`AETR`**~~ → **F-8 は修理済み**（2026-08-25。資料側ではなくツール側だった。
  [記録](worklist-archive.ja.md)）

**「資料側」と書いた3件のうち2件がツール側だった**（F-8・F-6）。残る F-7 も同じ疑いで
見直したが、あちらは**穴ではなかった**——V30x の pin 表は DVP を既定機能としてしか書かず、
解決すべき `remap-N` の行が無い。header に field が無いことも datasheet と整合している（F-7 の行）。

**教訓**: 「資料が書いていない」と記録する前に、**同じ事実を別の族の資料が書いていないか**を
見る価値がある。F-6 は V407/V467 の格子が同じフィールドの下に I2S3 を名指ししていたので決まった。

#### 未解決の数は2つあり、**単位が違う**

「未解決は32件だけ」と書いていたのが `index` に対する主張として読めてしまい、
2026-08-28 の監査で「index には52行ある」と指摘された。数え方を分けて書く。

| どこ | 何を数えるか | いま | 何が入るか |
|---|---|---:|---|
| `.cache/candidates/_report.json` の `unresolved` | candidate 1件ごとの function 数（102件の合計） | **0** | F-6 の32が 2026-08-28 に解消して空になった。F-8 の4と F-47 の8も既に解消 |
| `index/pinout.csv` の `remap-N` 行で `selector` が空 | 103型番へ展開したあとの**行数** | **3** | F-51 だけ（CH32H417 の `UHSIF_PORT0`〜`2`。中文版のみの主張で RM 格子が裏づけない） |

**candidate を通らない事実があるので、前者は後者の部分集合ではありません。** F-51
（CH32H417 の `UHSIF_PORT*_1`）は datasheet の**中文版だけ**が書いた経路で、
candidate は RM 格子と英語版の pin 表から作るので `_report.json` には現れず、
`pin_functions`（両版を別々に読んで突き合わせる）と `index` にだけ出ます。

index 側の数は `KNOWN_SELECTOR_GAPS`（`tools/check_tables.py`）が `(series, signal)`
ごとに持ち、増減どちらでも検査が落ちます。**監査の指摘の本体はこれが無かったこと**で、
数が合わないこと自体ではありませんでした。

`--family`だけで回すと`_report.json`が上書きされてこの数が見えなくなる問題は
2026-08-24に直しました（触ったSKUだけ差し替える。D6の項）。

## 次の作業（優先順）

**方針: 完全新規より過去の穴を埋めるほうが先**（2026-08-25 確認）。上から順に。

### 1. 穴を埋める

~~**ツール側で直せる穴は2026-08-25に全部埋めた**~~（F-8・F-21・F-31・F-32・F-47）
→ **2026-08-28 の監査でツール側の穴が3つ出た**（F-49 NC の足・F-50 X033 が別 series の
pin 表・F-52 完全同一行）。**いずれも「気付く手段が無かった」たぐい**で、直したのと同時に
検査を足した（`pin_numbering`・`KNOWN_SELECTOR_GAPS`・doctest の CI 化）。

**教訓**: F-31 は封装の lead 数を人が一度数えて閉じ、その数え方を機械に移していなかった。
「一度確かめた」と「これからも確かめる」は別のことで、[table-reliability](table-reliability.ja.md)
の「検査」欄に書いてあることは**機械が本当にやっているか**を疑う値がある。

残っているのは資料が決めないものと実機が要るものだけ:

| 項目 | 状態 | できること |
|---|---|---|
| ~~F-24 残り8行~~ | **閉じた**（2026-08-26）。8セルとも zh/en 両版で空欄＝資料側 | — |
| F-51 CH32H417 の `UHSIF_PORT*_1` | 中文版だけが書き、RM 格子が裏づけない | 台帳に記録。WCH へ報告する材料 |
| F-4 残り（片方の言語版だけの`reference`行） | 結合セルの版面が版で違い、片方の`fill_merged`だけ埋まる7セル（H417/M103/V203/V205）。値は他方の版で取れている | 実害なし。記録のみ |
| F-11 WCH-Linkの版番号 | **実機が要る**（更新前後で`minichlink`の表示を控える） | ユーザー作業 |
| F-6/F-7、資料側の記録 | 原典に無い | 台帳（下）に記録。WCHへ報告する材料 |
| `remap_fields`のreset_value空欄7行 | RMが復位値を書かない | 推測で埋めない（仕様） |

### 2. 過去情報の整理（決着）

- **JSON schema草案（`schemas/`・`devices/`8 sample・`tools/validate.py`・`docs/schema-notes.ja.md`・
  `.github/workflows/validate.yml`）は2026-08-25に削除した。** `tables/`が正本。記録はgitの履歴
- **R-20（レジスタマップ）**は機械収集ぶんを実装した（2026-08-25。E表参照）。残りの手作業ぶん（D-7・RMの絶対アドレス表）は consumer側の要否を見て
- **`tables/` は 2026-08-26 に `catalog/`・`evidence/`・`index/` へ分けた**（[data-layout.ja.md](data-layout.ja.md)）。表の置き場所は `tools/paths.py` が1箇所で決める

### 3. 新規

2026-08-26に D4（同期日時）・B5（機能から探す）・B6（評価ボード）・B4（節構成）を済ませた。2026-08-27 に D8（上流ツールの版の定期取得）も。
R-20 の機械収集ぶん（4表＋RMアドレス表での裏取り）も同日。残り:

| 順 | 項目 | 状態 |
|---|---|---|
| 0 | ~~**データの区分・形式・置き場所のやり直し**~~ | ✅ **実施**（2026-08-26）→ [data-layout.ja.md](data-layout.ja.md)。`tables/`→`catalog/`（目録7）・`evidence/`（証拠32）・`index/`（索引10表）。`pin_roles`→`index/pinout.csv`、`feature_tags`→`index/features.csv`、証拠の訂正（F-41）を索引側へ、`register_fields.define`・`dma_requests.request`原綴り・`remap_routes`/`timers`の導出列外し、`candidates/`→`.cache/`。**残り: consumer（ArduinoCore-CH32）の lock 付け替え（別 repository）**。確認の記録は [worklist-archive](worklist-archive.ja.md)「表の役割の確認」 |
| 1 | ~~**R-20 D-7** DMA channel→周辺の対応~~ | ✅ `dma_requests.csv`（2026-08-26）。表の形は5通りあったが1つの読み方で全12 family |
| 2 | ~~**R-27** debug module の DATA0/DATA1 アドレス~~ | ✅ `evidence/debug_data.csv`（2026-08-26）。H417 だけ実測待ち |
| 3 | **R-20** 構造体を持たないdefine群の`member`対応 | **1,591 → 911 行**（2026-08-28〜29。680行を解決）。原因は3種類だった:<br>・**banner が型を名乗らない**だけで構造体には居る 343行 → ✅ **解決**。header の banner は `CMP_CTLR` とだけ書き、型は define 側にしかない（`OPA_CMP_CTLR_PSEL_0` の `OPA_`）。register 名そのものをメンバーに持つ構造体が1つに決まるときだけ採る（`member_named`。衝突0件）<br>・**名前では引けないが RM の絶対番地なら引ける** 337行 → ✅ **解決**。CH32H417/V205 の FMC/FSMC は **BCR と BTR が1つの配列に交互**に入っていて（`FMC_Bank1.BTCR[8]`）、RM の `FMC_BCR1`/`FMC_BTR1` はどのメンバー名とも一致しない。V006/X035 の `OPA_KEY` は header が `OPAKEY` と綴る。**RM の各章冒頭の絶対アドレス表**（12 family 全部にある）が番地を書いているので、block の base を引いて offset にすれば実体が決まる（`member_at_address`。0x40025400→`BTCR[0]`、0x40025404→`BTCR[1]` と RM の番地で検算済み）。**スキーマ変更も出所の変更も要らなかった**——アドレス表はもともと base+offset の裏取りに読んであり、それを名前の代わりの鍵に使うだけ<br>・**置き場所がそもそも無い** 911行 → ⬜ 残り。うち62行は RM が番地を書くのに **header に構造体が無い**（V20x の `DVP_*` 0x50050000。F-7 と同じ事実）。残る849行は header にも RM のアドレス表にも無く、`member` は header の概念なので**埋めようがない**。bit 位置と define 名は事実なので offset 無しで載せている |
| 4 | **D7** GitHub Actions化 | 抽出の作り込みが落ち着いてから（計画は上記） |
| 5 | C1〜C3 画像 | 保留のまま |

## 資料側の問題台帳（原典の誤り・記録のみ）

ツールでは直せない、**原典（datasheet / RM / EVT / WCHのAPI）側の問題**を1か所に集めた。
表の中では `conflict`＋両論の `basis`、または脚注として現れる。WCHへ報告する材料でもある。
「どちらが正しいか」の判断根拠も添える。

| # | 資料 | 何が | こちらの扱い |
|---|---|---|---|
| F-6 | CH32V30x RM | I2S3のremap経路（`SPI3_REMAP`）を格子が書かない | ~~32 functionが`unresolved`のまま~~ → **2026-08-28 に解消**。V407/V467 の格子が同じフィールドの下に I2S3 を名指ししているので、周辺の対応（I2S3=SPI3）を語彙に入れて決めた。台帳に残すのは**同じ周辺を族によって書いたり書かなかったりする**という資料側の事実の記録として |
| F-7 | CH32V30x EVT header | `DVP_REMAP`の定義が無い（V407にはある） | 2 function unresolved |
| F-8 | CH32V003 RM **en版** | `AFIO_PCFR1` bit17（`ADC_ETRGINJ_RM`）の説明が規則転換の文（PC2）を誤って繰り返す。zh版と表7-13は正しい（PD1/PA2） | zh版で決める（F-8はツール側で解消可能） |
| F-33 | WCH 検索API | `CH32V20x_30xDS0.PDF`の版がAPI 3.5 / 表紙V3.9（メタデータがファイルより遅れる） | `documents.csv`は上書きしない。他75文書は一致 |
| F-48 | WCH 検索API | `CH32V003EVT.ZIP` が id 409（版2.1）から id 412（版**1.0**）へ差し替わり、**掲載の版番号が下がった**（旧idは404）。`scope` も `CH32V003` から4型番の列挙になり、DS/RMと同じ体裁に揃った | **中身は同一**（2026-08-28に新idからDLして比較。686ファイルのsha256が全一致、ミラーのEVTは2026-05-09から不変）。EVT自身は版を名乗らない（`CH32V00x_List_EN.txt` は 2025.01、内部の最新ファイル日付は2025-03-11）ので、版番号はWCHの掲載メタデータでしかない。カタログは掲載の写しなので新id・新版をそのまま持つ |
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
| F-51 | CH32H417 datasheet zh | pin表2-1-1 の PF12/PF13/PE7 の重映射欄に `UHSIF_PORT0_1`／`_1`／`_2`。**英語版の同じ欄は空**で、RM の格子はその3 pad を `UHSIF_PORT_REMAP=0`（既定）に当て、値1は PC1→`PORT3`・PC2→`PORT4`・PC3→`PORT5` とずらして書く | `pin_functions` に `reference`／`pin-table:zh` として残す（既定側は両版一致で `confirmed`）。格子に裏づけが無いので `pinout` の `selector` は空。`KNOWN_SELECTOR_GAPS` に3行として記録 |
| F-31 | CH32M103 datasheet en | pin説明でHO*を「N型」（p31）と「P型」（p32）の両方で書く | 表には影響なし（記録のみ） |
| F-21 | CH32M030 EVT header | `ISP_CTLR_ISP2_QDET1_*`と綴る（RMは`QDET2`） | 語彙には使わない（記録のみ） |
| F-21 | CH32V003 datasheet | pin表2-1のPD4が`TIETR_2`（同じ行が表2-3では`T1ETR_2`。`I`と`1`） | 語彙で`T1ETR`へ寄せる。層1の綴りは残す |
| F-55 | CH32V20x_30x RM/DS 表3-4 | `ADC_1N1`（`I`→`1`）と `ETH_RMII_RXDO`（`0`→`O`）。同じ pad を表3-1 は `ADC_IN1`・`ETH_RMII_RXD0` と正しく綴る | 表3-4 は読まないので表に影響なし（記録のみ）。**`I`↔`1`・`0`↔`O` の誤植が繰り返し出る**ことの記録でもある |
| R-20 | CH32V407 RM / CH32H417 RM（DMA章） | V407 表11-2 の `I3C_TC` 行の周辺名が `13C`（`I`→`1`）、H417 表10-2 の要求84が `I3X_RX`（`I3C_RX`） | `dma_requests`は綴りを保ち note に「as printed」。`peripheral`は正しい方 |
| R-20 | CH32H417 RM vs EVT header（`registers`の conflict 4） | CAN2 の `FMCFGR`/`FSCFGR`/`FAFIFOR`/`FWR` の番地が RM のアドレス表では EVT の構造体より +4（CAN1 は一致） | conflict＋両論。**実機未確認** |
| R-20 | EVT header vs RM（`register_fields`の conflict 38） | bit位置がEVTとRMで**入れ替わっている**もの: M030 `ADC_STATR` `MULT_CMP1`(EVT bit9/RM bit7)⇄`MULT_CMP3`(bit7/bit9)、V407 `RCC_CFGR2` `UTMI1ON`(bit31/bit30)⇄`UTMI2ON`(bit30/bit31)。**幅が違う**: V003/V006 `GPIO_LCKR.LCKK` EVT bit8/RM bit16、L103 `CAN_BTIMR.TS2` 3bit/4bit・`SJW` 2bit/4bit、V103 `FLASH_ACTLR.LATENCY` 2bit/3bit・`ADC_CTLR1.DUALMOD` 4bit/6bit、V20x/V307 `RCC_CFGR0.USBPRE` 1bit/2bit、X035 `ADC_CTLR3.CLK_DIV` 4bit/9bit・TIM `CCR3/4` 16/32bit、V003 `ADC_RDATAR.DATA` 32/16bit。`FLASH_OBR.USER`（8 family）はRM側が行を別の切り方で書くため | 全部 conflict＋両論。**実機未確認**。どちらが正しいかは決めていない |

いずれも**実機では未確認**。「正しい側」はもう一方の資料が複数一致することで決めている。

## 利用状況（優先順位の根拠）

| # | 誰 | 最初の問い |
|---|---|---|
| U1 | 買ってしまった人 | このピンは何？どう書き込む？Lチカの最短経路は？ |
| U2 | 選定する人 | 要求を満たす型番は？落とし穴は？ |
| U3 | 開発中の人 | この機能はどのピンに出せる？remap値は？例題は？ |
| U4 | 移植する人 | メモリマップ・割り込み番号・機械可読定義は？ |
| U5 | 原典に到達できない人 | 最新版は？いつ同期した？両言語あるか？ |
