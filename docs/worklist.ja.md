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

## 利用状況（優先順位の根拠）

| # | 誰 | 最初の問い |
|---|---|---|
| U1 | 買ってしまった人 | このピンは何？どう書き込む？Lチカの最短経路は？ |
| U2 | 選定する人 | 要求を満たす型番は？落とし穴は？ |
| U3 | 開発中の人 | この機能はどのピンに出せる？remap値は？例題は？ |
| U4 | 移植する人 | メモリマップ・割り込み番号・機械可読定義は？ |
| U5 | 原典に到達できない人 | 最新版は？いつ同期した？両言語あるか？ |
