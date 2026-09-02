# 作業リスト

README自動生成の対象は**データシートとEVTを持つ12リポジトリのTOP**と**org TOP（.github）**です。両方とも特殊処理なしの全自動生成を目標にします。根拠は[docs/extraction-survey.ja.md](extraction-survey.ja.md)、データ構造は[evidence/README.ja.md](../evidence/README.ja.md)。

状態: ✅完了 / 🔜次 / ⬜未着手 / ❓要確認（人の判断待ち）

**解決済みの項目の詳細は [worklist-archive.ja.md](worklist-archive.ja.md) に移した**（2026-08-25 棚卸し）。
この文書に残るのは、索引表と、まだ生きている項目だけ。

## 進捗

テーブルごとの信頼度は [table-reliability.ja.md](table-reliability.ja.md)（どのテーブルがどこまで固いか・既知の穴の所在）。


| 区分 | 完了 | 残り |
|---|---:|---:|
| データ収集 | 11 | **0**（A11を2026-09-01に受入） |
| README生成 | 7 | 0 |
| 画像 | 0 | 3（保留） |
| 検査・運用 | 16 | 1（D7） |
| PDF構造化PoC・計画 | 2 | 1（D18） |
| consumerからの依頼 | 10 | 2（**R-28〜R-30を2026-09-01にch32rvから受領、翌日までに3件とも資料から取れるぶん完結**。R-29は完全解決（debug_wiring＋全27 series確定）、R-28は**納品受け入れ済**（実測6台と全一致・gap 7はch32rv曰く未発売＝接続でき次第）、R-30はRMから取れるぶん完結（option 2表＋WRPR粒度。残りは実測照合）。R-27 は H417 の実測待ちが1行。R-20は機械収集ぶんまで、残りはconsumerの要否次第） |
| 表示（G系） | 12 | 0 |
| 既知の穴（F系） | 50 | 7（下の F 台帳で ✅ が付いていない行の数。**すべて資料側の記録**で、F-7・F-33・F-43〜46・F-51。F-4 と F-24 は残りだけが資料側で実害なし。**ツール側の穴は0**——F-57・F-58 を 2026-08-29 に解決した） |

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
- [x] ✅ **A11 消費電流とウェイクアップ時間** — **受入完了**（2026-09-01・判定はユーザー委任で実施）。経緯: **一度実装して差し戻した**（2026-08-29）。取れた行そのものは有望だった（`I_DD` 83行・`t_wusleep`/`t_wustop`/`t_WUSTDBY` が全 series・`I_HV`）が、**土台が不健全**だと分かったため入れていない。<br>**分かったこと**: `build_operating.py` の表の探し方は**キャプション駆動**で、`MARKER` が名指ししているのは「一般動作条件・発振器・ADC 特性」だけ。消費電流・Flash・I/O・リセット・低消費モードの表は、**「マーカーが当たったページの次のページも1ページだけ見る」という継続規則で偶然拾えていただけ**で、どの表が読まれるかがページ割りに依存する。その結果**中英で読む表の集合が食い違い**、記号での対応付けがずれて、`I_DD` 83行のうち18行が conflict になった——**資料の食い違いではなく私の抽出の食い違い**。両論を basis に残す規約は資料が食い違ったときのもので、抽出が食い違ったものをそこに流し込むのは規約の悪用になる。<br>**新しい経路のPoC（2026-08-31）**: PDF→構造化JSON→構造検査→値抽出→確認HTMLへ分離した（[実測と形式](structured-extraction-poc.ja.md)）。V003・L103・H417・V007の消費電流/ウェイクアップ対象表で、JSON経由とPDF直読みを比較し、**V003 86行、L103 zh184/en168行、H417 zh109/en110行、V007 zh/en64行が記号・min/typ/max・単位まで全件一致**。V007の英版 `3-9-2` 重複と、タイミング図を表と誤認した候補も値抽出前に検出した。これは今後の**全datasheet＋RM移行の回帰標本**として残す。全体bundle案、review sidecar、Markdown/HTML、移行計画はD16で文書化済み。正本CSVは未変更。<br>**新経路でのcandidate生成が完了**（2026-09-01・D18工程4）: `pipeline/extract/datasheet/extract_low_power.py`が**caption選定**（ページ割りに依存しない——旧実装の根因を除去）・**断片の結合**（列数が同じなら位置、違えばx座標の和集合。続き断片の繰り返しheader行はstateに触れず飛ばす）・**表番号スコープの2段階zh/en照合**で**1,208行**を生成（confirmed 1,200・conflict 6・reference 2。I_DD 1,054・I_HV 52・t_wu系51ほか）。**全16 datasheetでzh/enの行数が完全対称・偽conflictゼロ**（旧実装は18件）。conflict 6件は原文突き合わせで**全て資料側の齟齬と裁定**——H417のstop電流3件（en 2.4/1.4/1.3 vs zh 4.4/1.8/1.7 mA）・L103のt_wustop（en 7us/zh 13us）・V006の待機電流（10.6/10.7uA）・V407のt_WUSTDBY（en us/zh **ms**の単位差）——受入時に資料側の問題台帳へ。reference 2件はL103の`I_DD_VBAT`（en版だけが行を持つ・単位欄なし）。candidateは`.cache/pipeline-candidates/operating_conditions_with_a11.csv`で、**凍結1,588行は不変**（unchanged 1588/missing 0を`compare_csv`で機械確認）。**受入と正本切替**（2026-09-01）: `evidence/operating_conditions.csv`は**2,796行**（confirmed 2,575／reference 181／conflict 40）になり、正本生成元は[`pipeline/extract/datasheet/build_operating_conditions.py`](../pipeline/extract/datasheet/build_operating_conditions.py)（凍結ロジックの基礎行＋A11行。再実行同一を確認）。受入の最中にmirror自動更新で**CH32X315DS0のzh版が改版**され、基礎行2行がconfirmed→conflictへ（新zh版はFlash時間`t_prog_page`/`t_erase_sec`のmaxを書かない）、A11側にX315のI_DD典型値改定2件が加わった——**計10件のconflictは全て原文裁定済みの資料側齟齬**で両論をbasisに記録（原本が動けば合意が崩れてconflictに降格する、という設計どおりの挙動）。**zh単独版の扱いは決着**（2026-09-02調査）: どちらも**WCHの比較表にまだ無いSKUの文書**だった——`CH32V006DS2.zh`は実は**CH32M006（A8U7）のdatasheet**（35ページ・電気特性フル装備）、`CH32M030DS2.zh`は**M030の新variant K9U7/C9U7**の引脚定義補遺。catalogは比較表の写しなので行の置き場が無く、**抽出しないのが正しい**。比較表にSKUが載れば日次update経由でproductsに現れ、通常経路が拾う（文書は変換済み・preview可読）。<br>**将来の順番**（本番移行の事前調査は **D17**。`operating_conditions.csv` を最初の移行CSVにすると決めた——2026-09-01): (1) PDF直読みを構造化bundleへ置き換える、(2) 承認済み表だけから中英を照合、(3) 既存1,588行を不変に保ったまま追加する。表パーサ規則は、結合セルの引き継ぎを**記号が変わったら捨てる**、値の列を割るのは**同じ名前が2箇所以上にある表だけ**——普通の min/typ/max 表を3行に割る回帰を試験で固定する。
- [x] ✅ **A2 電気的特性** — `evidence/operating_conditions.csv` 全27 series（2026-08-29 に 304 → 1,588 へ拡張。当初は62行でクロック上限F_*と動作電圧V_DDだけだった。**2026-09-01、A11の受入で2,796行に**——正本生成元はD18の`pipeline/extract/datasheet/build_operating_conditions.py`へ移行）。クロック・電源電圧・発振器・ADC・Flash・I/O レベル・リセットのタイミングまで。**採る行は記号の一覧ではなく「頭字が名乗る物理量に単位が合っているか」で決める**（`UNIT_FOR`）
- [x] ✅ **A3 remap** — `remap_fields`/`remap_routes`（全行reference。根拠記録つき再実行で確定化するのは別課題）。2026-08-20に作り直し: `bits`がbitごとにregister名を持つようになり、PCFR1とPCFR2にまたがるselectorを表せる。`peripheral`/`role`列で`TX1`/`UTX`/`USART1_TX`の綴り差を吸収。value=0の既定経路を同じ表に収録。CH32V407/V467はRM未mirrorでも header+datasheet から生成する。`tools/check_tables.py`が表だけで整合を検査する（bit形式、値の幅、route値がvalid_valuesに含まれること）
- [x] ✅ **A4 公称主周波数** — U2/U1が最初に見る値。**現状は誤解を招く**: CH32V003のMax clockが電気的特性の50MHzで出るが、公称は48MHz（DS1ページ目「48MHz system main frequency」）。product_attributesには8シリーズ分しか無く自由文（`Max: 144MHz`、`40MHz@Zero-wait; Max: 192MHz@Non-zero wait`）。DS第1章の特徴リストから全シリーズ抽出し、`Main clock`列と`Fmax (HCLK)`列を分離する
- [x] ✅ **A5 EVT例題索引** — U1/U3への効果が最大。材料は全12リポジトリの`EVT/<FAMILY>_List_EN.txt`（周辺→例題→1行説明のツリー）に揃っている。パースして`evidence/evt_examples.csv`へ
- [x] ✅ **A6 機能フラグ（USB/Ethernet/CAN/PD/DVP…）** — `evidence/features.csv`新設（2026-08-23）。比較表からは作れない（[調査結果はarchive](worklist-archive.ja.md)）ので、**機能説明章の節見出し**を採った。節番号は言語に依らないので中英が厳密に対応する
- [x] ✅ **A7 メモリマップ** — `evidence/memory_map.csv`新設（2026-08-23）。**DS 1.2章ではなくEVTヘッダーの`*_BASE`から**。相対の連鎖を解く処理は`extract_addresses`が既に持っていた
- [x] ✅ **A8 書き込み方式** — **A6の副産物**（2026-08-23）。`1-wire Serial Debug Interface (SDI)`／`2-wire SDI Serial Debug Interface`が節見出しとして立っているので、`curated/`への手書きは不要だった
- [x] ✅ **A10 型番×能力の縦持ち索引** — `index/capabilities.csv`新設（2026-08-29。1,707行）。`evidence/product_attributes.csv`（154種類の綴り・1,714行）**だけ**から作る。`index/parts.csv`は横長なので比較表の属性を13列しか持てず、残りは綴りを知っている人しか引けなかった。属性→能力の対応は**総当たりの辞書**（`tools/build_capabilities.py`の`CAPABILITIES`）で、regex で畳まないのは`adc`（チャネル数）と`adc_unit`（ユニット数）のように**似た綴りで意味が違う**ものが混ざるため。辞書に無い属性が現れたら生成が落ちる。`stated`列が資料の言い方（`count`＝素の整数1,182行／`marker`＝`√`160行／`text`＝`8+2`等365行）を言い、`count`が入るのは`stated=count`のときだけで**数える規則は当てない**。**新しい PDF は読んでいない**（既存の証拠の並べ替え）
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

- [x] ✅ **D1 参照結合検査** — `tools/check_tables.py`が全51テーブル（目録8・証拠33・索引10）の参照結合・書式・数の不変量を検査（`check_counts.py`が比較表の数とpin側の数を突き合わせる）
- [x] ✅ **D2 中国語混入検査** — `#`より左のデータ列にCJKがあればCIが落ちる
- [x] ✅ **D3 エラッタ増分検査** — `tools/scan_errata.py`（ミラーPDFが要るのでCIではなく手動運用）
- [x] ✅ **D5 画像の検査** — 寸法異常と同一切り出しの共有を機械検出（目視の前段。実際に4件の欠損を捕捉）
- [x] ✅ **D6 読んだ原典の版を記録** — `catalog/sources.csv`新設（2026-08-23）。mirror 12本のcommitとその日付。**生成時刻は入れない**（毎回書き換わると「差分が出たら異常」の判定が使えなくなる）。生成物の差分の原因を「入力が変わった」と「再生成を忘れた」に切り分けるため
- [ ] ⬜ **D7 生成のGitHub Actions化** — 日次起動・datasheetかEVTが変わっていたら全生成。**計画のみ**（下記）。抽出の作り込みが落ち着くまでは手動
- [x] ✅ **D16 PDF構造化ワークフローのPoC・実現可能性・移行計画** — 対象を電気特性に限定せず、**datasheet全34版＋RM全21版**と定義。原本PDF→ページ物理層（L0）→ページを跨ぐ文書論理層（L1）→review・注釈層（L2）→領域別抽出という候補を[PoC最終報告](structured-document-workflow.ja.md)にした。V003英版datasheet 37ページは本文・語・図形・表・結合セル座標が旧経路と全件一致し、`extract_products`の4型番も一致。V003英版RM 188ページを変換し、`extract_registers`も310 fields・notes 16件まで一致した。既存`tools/`とCSVはbaselineとして凍結し、新実装は工程別の`pipeline/`で並走、入力bundleが揃ったCSVから旧新比較後に置き換える方針。原文block IDは表示分割と独立させ、将来HTML anchorとしてCSVからURLで指せる。人向け表示を文書・章・原本ページのどの単位にするかは未決定。**このlayer・schema・IDは本番仕様ではない**。実作業開始時に文書inventory、既存tool、変換engine、難所fixture、性能、結合規則を再調査し、architecture decisionと本番schemaを決めてから実装する。**今回の範囲はここまで**。正本CSVと本番経路は変更しない。**その再調査を D17 として起こした**（2026-09-01）
- [x] ✅ **D17 PDF構造化の本番移行・事前調査** — **完了**（2026-09-01。同日着手・同日完了）。調査報告は[structured-migration-survey.ja.md](structured-migration-survey.ja.md)——項目1（inventory再棚卸し）✅: 55版＋将来10版の所在・SHA-256・ページ数を確定、欠落0・複数mirror写し全一致、**zh/enで版番号がずれる文書3件を発見**（M030DS0・X315DS0・X315RM）。項目3（fixture）は11難所×7文書で確定、項目4（engine選定）は**決着**——ゼロベースの候補一次調査と予備実測の上で**現行pdfplumberを本線、限界が出たら候補から追加**（pypdfium2は非空白文字完全一致・約23倍速の高速L0控え、PyMuPDFはAGPLで除外、Docling等ML系は表構造の監査用。トリガー3種を調査報告に明文化）。pdfplumber基準線を実測（変換0.31s/p・bundle 125KB/p→55版で約1.3GB・検査50ms/p）、**変換の唯一の非決定性を特定**（pdfminerがinline imageへ付けるid()由来name。1,042頁中14頁のみ、正規化で潰せる——「bundle非保存＋manifestコミット」案の成立を裏付け）。項目2（baseline走査）は方法確定・台帳は凍結時。項目5（標本監査）は第一回済み——fixture 7文書をbundle化して既知難所8種を検査、**全難所がL0に材料を残す**ことを確認。RMは表の85%がページ継続で**L1の表結合が主戦場**、zh/en対応は**caption番号だけでV003 30/30・H417 104/104の1:1（衝突0）**。header/footer roleの精度も実測（2026-09-01）——**擬陽性0**（本文の誤カットなし）だが**zh版footerを系統的に取りこぼす**（V003 zh 30/31頁等）。本番converterは反復ベースのheader/footer検出を要件にする（項目8の第一歩の成立条件。PoC exporterは該当role行をHTMLコメント化済みで仕組み自体はある）。項目8（表示用途）は確認済み（2026-09-01）——**PDFと同じ内容をMarkdown/HTMLでそのまま読む。第一歩はheader/footer除去だけ、図の扱いが主課題、分割は後**。**項目6の設計案と項目7の受入条件は同日ユーザーが「いまの方針のまま」で暫定承認**——実装で前提が崩れたら調査報告へ戻る。残余（環境差のCI検証・凍結hash台帳）と`WCH-LinkUserManual.PDF`の対象追加（同日ユーザー判断。zh 24p/en 29p・mirror済み・R-29/R-28の一次資料）は**D18**へ引き継ぐ
- [ ] 🔜 **D18 PDF構造化の本実装（`pipeline/`）** — D17完了・設計暫定承認（2026-09-01）を受けた実装フェーズ。仕様は[調査報告](structured-migration-survey.ja.md)の設計案（bundle非保存＋manifestコミット・L2 sidecar正本・stable ID・無効化規則）と[D16報告](structured-document-workflow.ja.md)の移行順どおり。対象は55版＋将来12版（core-manual 8・PACKAGE 2・**WCH-LinkUserManual 2**）。<br>**工程**: (0) **baseline凍結**——CSV 53表のhash台帳と凍結commitを記録し、旧`tools/`のPDF直読み19本と正本CSVを参照実装として更新停止（解除は明示的に） → (1) `pipeline/ingest`——本番converter（決定性の正規化＝pdfminerのid()由来name等、**反復ベースのheader/footer検出**、manifestだけコミット、review sidecarは正本）、67版の一括変換、CIでの環境差検証 → (2) L1結合（列構造一致。継続flagだけでは不足＝D17実測） → (3) L2 sidecar（承認・canonical ID・zh/en対応。DSはcaption番号で候補生成＝的中率100%実測） → (4) `extract`——**`operating_conditions.csv`の1,588行を新経路で再現一致→A11行を追加**（最初の移行CSV） → (5) 旧新比較→CSV単位切替（受入5条件: schema互換・説明できない欠落0・追加変更行の原文リンク・consumer検査合格・再実行同一）。<br>**早期の抽出対象**: WCH-Link manual（R-29の未記載11 series・R-28手順）とRMのdebug章・option bytes章（R-30）。完了条件はD16の5点。<br>**着手**（2026-09-01）——工程(1)のingestを実装: [`pipeline/ingest/convert.py`](../pipeline/ingest/convert.py)（D17の2欠陥を修正。決定性の正規化＝id()由来の画像名を捨てる、header/footerは**反復ベース**＝数字を畳んだ同綴りが縁から同距離に25%以上のページで繰り返す行。V003 zh/enで本文・語・表・文字は旧PoC bundleと**完全一致**、version+page footerの取りこぼしは**en 35/35・zh 30/30でゼロ**になり、TOCページでfooter/headerがheadingに化けていた12行も直った——反復判定をheading判定より先に置いたため）、[`convert_all.py`](../pipeline/ingest/convert_all.py)（catalogの67版・incremental・並列）。**manifest正本の置き場は`structured/<stem>.<lang>/`に決定**（review sidecarも同じ場所。`manifests/`はWCH APIの写しなので使わない）。環境差検証は[`pipeline/checks/compare_manifest.py`](../pipeline/checks/compare_manifest.py)＋`.github/workflows/structured-repro.yml`（週次・原本変更と環境非再現を別の出口で報告）。**凍結台帳`pipeline/baseline/tables.csv`生成済み**（54表・165,646行）——**凍結の宣言はこの台帳を含むcommitで行う**（ユーザーのcommit操作）。<br>**一括変換の実測**（2026-09-01）: **67版・11,016ページを32分（4並列）で全変換**、bundle総量1.2GB（`.cache/`・非コミット）、コミットする`structured/`のmanifest正本は**4.0MB**。2回目の起動は全67版をup-to-dateとして跳ばす（incremental確認済み）。**決定性の最終証明**: H417 RM（1,042ページ・最大文書）が本番converterの2回の独立変換で**byte一致**——PoCの14ページ非決定は正規化で消えた。**独立検証ゲート（`check_document_bundle`: schema・原本/page/geometryのhash・全ページ性・ID・bbox・表span・読み順）も全67版合格・失敗0**。<br>**(0) baseline凍結成立**（2026-09-01）: 台帳を含むcommit `8d706cd` をユーザーがpush。以後、旧`tools/`のPDF直読み19本は参照実装として更新停止。<br>**(4) 最初の移行CSVの第一関門を通過**（2026-09-01）: `pipeline/extract/pdfcompat.py`（bundle互換層＋**原本hashの入口ゲート**。bundle欠落・hash不一致は停止、PDFへのsilent fallbackなし）で凍結した`build_operating`ロジックをbundle入力で走らせ、**`operating_conditions.csv`の1,588行がbyte一致で再現**（confirmed 1,379/ref 179/conflict 30・診断メモまで同一。実行15.6秒——表検出が変換時に済んでいるためPDF直読みの数分から短縮）。candidateは`.cache/pipeline-candidates/`（正本には書かない・dual-writeなし）。比較道具は`pipeline/reconcile/compare_csv.py`（unchanged/added/changed/missingを列名まで特定。正負両テスト済み）。<br>**A11のcandidate生成も完了**（同日）: `extract_low_power.py`——caption選定・断片結合（L1「列構造一致」の最初の実装）・表番号スコープの2段階zh/en照合で**1,208行・全16 datasheetでzh/en完全対称・偽conflictゼロ**（詳細はA11の項）。<br>**最初のCSV切替が完了**（2026-09-01）: A11受入（ユーザー委任）により`operating_conditions.csv`の正本生成元が`pipeline/extract/datasheet/build_operating_conditions.py`へ移行（詳細はA11の項）。**進め方の更新**（同日ユーザー）: 途中の受入儀式は最小化し、**まず全CSV群で「新経路が従来データ以上」を達成**してからまとめて切替。カバレッジ100%へ向けブラッシュアップ継続。**CI環境差検証もクローズ**（`structured-repro.yml`緑をユーザー確認——bundle非保存・manifestのみコミット設計の最後の前提が実証された）。**残り**: 他CSV群の旧新パリティ（datasheet表群・RM本文/表群・core/package）、L1結合の一般化、L2 sidecar、zh単独版の扱い。<br>**旧新パリティのスコアボード**（2026-09-01開始。[`pipeline/extract/run_frozen.py`](../pipeline/extract/run_frozen.py)——凍結toolのコードを変えず`pdfplumber`属性だけ互換層へ差し替え、`--out`のcandidateを凍結CSVとbyte比較）: **operating_conditions＝切替完了（正本）**／**features・adc_internal・flash_geometry・debug_data＝byte一致**／**timers・memory_configs＝値一致**（差はbasisのページ番号のみ——X315RM・V407RM zhの改版でページが1枚ずれた。現行原本への追随として採用済み）。**datasheet表群も完了**（2026-09-01）: `build_all`はbundle入力・直列（`--jobs 1`で子プロセス不要）41分で102 SKU・未解決0。下流の`build_pins`/`build_tables`/`build_remap`で**12表中9表がbyte一致**——pins 4,563行・pin_functions 28,483行・product_attributes・products・errata・series・families・cores・documents。**差分3表は全て新X315 zh版由来の改善で採用**——packages（LQFP64の`?pin-table`不一致印が解消＝新版のpin表が64 leadに一致）、remap_fields/remap_routes（CH32X305の`PD0_1_REMAP`経路が各+1行＝新版で取れるようになった事実。287/4,838行）。**RM表群・EVT系も完了**（2026-09-01）: `build_registers`は**register_fields（33,365行・最大）がbyte一致**、register_blocks/registers/register_layoutsは**新X315 EVTヘッダ＋新RMへの追随**として採用（USBSSD構造体の再定義で registers 4,995→4,932行。ARGB base移動0x40023400→0x40025000は新RMのアドレス表がconfirmed）。残る全生成器の一括パリティ: **opa_cmp_registers・interrupts・systick・clock_init・clock_prescalers・clock_enables・evt_variants・pin_alternate・usbpd_plumbing＝byte一致**、**dma_requests（zhページずれのみ）・memory_map・clock_configs/sources/symbols・evt_examples・eval_boards・link_firmware・sources＝現行mirrorへの追随として採用**（実は12 mirror全部が2026-08-29に更新されていた——sourcesの記録がそれ）。<br>**凍結の明示的な例外を1件**: `build_usbpd_plumbing.py`はmain内のローカル変数が`import paths`をshadowして**単体でも常にUnboundLocalErrorで落ちる潜在バグ**（CSVを再生成しない限り誰も踏まないF-54型。パリティ実行が発見）——改名のみ修理し、修理後**byte一致**。<br>**別型CLIの2本も解決**（2026-09-01）: `extract_package_dims`は`extract()`を`build_tables`が呼ぶのでpackages.csvのパリティで実証済みのうえ、単体でもzh/en各105 entryがPDF直読みとbundleで完全一致。`scan_errata`は[`run_scan_errata.py`](../pipeline/extract/run_scan_errata.py)（同じ属性差し替え・対象選定は凍結toolのまま——bundleが無いPDFは黙って跳ばず「読み取り失敗」で見える）で走らせ、`--rm`の全57 PDFで旧（PDF直読み・十数分）と新（bundle・23秒）の**出力と終了コードがbyte一致**（KNOWN 21確認・NEW 235も同一）。`extract_images`はasset rendererが後継。**これで凍結PDF tool 19本の全部が「新経路で従来以上」を達成——PDFを直接読む工程は実行経路から消えた**。<br>**R-29完全解決＋新経路初の新規evidence表**（2026-09-01）: `evidence/debug_wiring.csv`（WCH-Link manualの配線表＋両対応注記。zh版のページ跨ぎ表はL1結合で読む）を新設し、`debug_interfaces`が全27 series確定（詳細はR-29の項）。<br>**一括再生成entry point＝実行経路の整理**（2026-09-01）: [`pipeline/publish/regenerate.py`](../pipeline/publish/regenerate.py)——bundle再変換（incremental）→切替済みevidence（operating_conditions・debug_wiring）→下流index（debug_interfaces・conflicts・build_index）→検査3本、を1コマンドで順に呼ぶ（失敗した段で停止）。`--verify`で凍結パリティ一式＋エラッタ増分検査、`--human`で図描画→人向けMarkdown→差ゼロ検査。**全段成功23秒・実行後の`git status`差分ゼロ＝再生成の冪等を実測**。あわせてCIの赤を修理——`build_conflicts.py`のKEYSに`debug_wiring`が未登録でupdate.ymlの4連鎖が落ちていた（R-29の登録儀式の見落とし。`series`を鍵に追加、conflicts.csvは200行のまま無変化）。evidence/README両言語の生成手順とoperating_conditions節に残っていた旧tool参照（`build_operating.py`）も正本生成器へ更新。<br>**converter 1.2.0——header/footer反復検出の規則を2つ追加**（2026-09-02）: R-30の抽出が「**V00X RM zhのp198以降のfooter 32ページ（14%）が未分類**→本文行扱いになり、直前の表が『ページ末で終わっていない』と判定されてbit割当表のL1結合が切れ、復位値が欠ける」を発見。全コーパス実測で同型の取りこぼしを確認——横向きpin表ページのfooter（V407 DS enの5ページ＝縁距離が変わる）、章ごとに綴りが変わるheaderの変種（V20x DS enの3ページ）、footer位置の途中変更。原因は(綴り×縁距離)キーの25%閾値で部分群が割れること。1.2.0で**厳格帯(6%)は同綴り同距離3ページ以上で合格**・**合格した綴りは帯内なら距離が違っても余白扱い**を追加（ページ番号だけの`#`は新規則から除外——数字だけの本文を巻き込まない）。V00X zhで先行検証（role変更33行ちょうど・巻き添え0）→67版を再変換（11,017ページ・22分）→**全コーパスのrole差分72行を全件目視して全部がheader/footerと確認**（paragraph→footer 45・heading→footer 15・heading→header 7・paragraph→header 5。V20x DS enでfooterがheadingに化けていた4ページも直った）。正本CSVは不変（operating_conditions再生成もbyte一致・scan_errataのbundle出力も旧経路baselineとbyte一致のまま）。**表結合は3,759→3,770**（footer分類の修正で11本の連鎖が新たに繋がった——V00X zhのbit割当表もその1つ）、図caption 100%・警告0・67文書parity全合格を維持。<br>**工程(5) CSV群の一括切替が成立**（2026-09-02）: [`run_patched.py`](../pipeline/extract/run_patched.py)（凍結toolをコード不変・引数そのままでbundle入力実行し**正本へ書かせる**正規実行形）＋`regenerate.py --full`（build_all直列→datasheet/RM表群→EVT系→新経路evidence→索引→family README→検査、を生成手順の依存順で）。**初回実行（約1.5時間）で全正本CSV・family READMEがbyte一致**——唯一の差分（registers 9行が偽conflict化）は原本でも新経路でもなく、**`--rm-cache`が原本更新後も無検証で再利用される罠**だった（08-26製のcacheがX315 RM改版前のARGB番地0x40023400を返した。`check_docs`が捕捉→revert→**cache無しの`build_registers`をbundleで再実行して19分・差分ゼロを確認**）。対処: `--full`と生成手順からcacheを外し、READMEに実績つきで警告。**生成手順の正本もbundle入力形へ書き換え**（evidence/README両言語——PDF読みtoolは`run_patched`経由、正面玄関は`regenerate.py --full`。素の`tools/<name>.py`でのPDF直読みは実行経路の外）。<br>**人向け出力の精度向上——回転文字と偽caption**（2026-09-02、ユーザー指摘「PDFから取り込んだ表示外の文字が残っている気がする」を受けた精査）: まず**隠しテキストの疑いを棚卸し**——render_mode=3（不可視）・白文字・ページ外・1pt未満は全PDFで**ゼロ**（健全）。正体は**封装図・引脚配置図の90°回転ラベル**だった: 図がcaptionを持たない（節見出しで導入される）ためasset化されず、pin番号・pad名が**鏡順の文字**（`33DDV`＝VDD33、`3OSIM/3DDS/11CP`＝PC11/SDD3/MISO3の逆）として本文に流出——**3,515行／全datasheet**（RMは0）。大フォントのラベルがlevel-1見出しに化ける実例も（H417 DS p26「@VDD33 power」）。対策2段: (1) **renderer/exporter**——回転文字10個以上を含むcaption無しgraphicsクラスタを**独立asset**として描画し（asset 3,337→3,676）、exporterは領域に入った時点で画像を埋め込み→領域内の行は折りたたみへ（引脚配置図が完全なPNGになることを目視確認）。(2) **converter 1.3.0**——回転行をx0で列に分割しglyph matrixの向きで組み直す（`PA14 PA13 PA12/OTG_DP…`と読める形に。5,858行を再構成。回転charの`size`はグリフ幅寄りで不安定なので語間はピッチ中央値×1.9で判定）、回転行をheading判定から除外、**表caption番号regexを行頭にanchor**（「注：表21-4的…」型の参照文caption **14件を根治**）。`page["text"]`は不変なので凍結toolのbyte一致は崩れない。**検証**: role変化はlist-item→paragraphの8行のみ・caption変化は除去14件のみ・凍結パリティ6/6 byte一致・scan_errata byte一致・regenerate全緑・Markdown差ゼロ67文書・**流出3,515→76行**（残りはクラスタ外の散在ラベルで、文字自体は読める形になった）。偽caption根治で不要になった暫定decision 6件を削除し、caption除去で露出した本物の対7組（enはcaption行を印刷せず参照文のみ——15-2 GTPM×4等）＋行頭Table型参照文1件を追記録（**残差0を維持**）。<br>**左右ビュアーの偶奇バグ修正＋ページ境界のセル結合**（2026-09-02、ユーザー報告）: (1) viewer.htmlで**PDFが偶数ページだけ表示されない**——`about:blank`を挟む二段src設定がナビゲーション競合を起こし、前ページの偶奇に依存して交互に失敗していた。iframe要素ごと作り直す方式に変更（`replaceChildren`。必ず新規ナビゲーションになる）。(2) **ページ境界でセルの中身が割れた行の結合**（X035RM 3-1のMCO[2:0]説明の続き`Other: No clock output.`が独立行になっていた——ユーザー指摘）。`logical_tables.fold_boundary_spills`——結合表で「1列だけ非空・他は全部空」かつ**ページ境界（row_pagesが変わる）**の行を、直前の同列セルへ改行連結。**境界限定が肝**——全コーパス実測で境界限定1,937件は全て本物のセル続き、境界を外すと9,527件になり製品比較表の縦並びセル（`2*ADC`/`2*DAC`）を誤結合する。exporterとparityが共通で呼び、**切替済み抽出器の凍結CSVは呼ばない**（人向け出力専用・冪等）。1,937セル／50文書を結合、67文書parity緑。**継続セルはグリッドから削除**して空行を残さない（rowspanに覆われていない`_folded_rows`だけ落とす安全策——跨ぐrowspanがあれば残す）。(3) **セル内の段落復活**（ユーザー指摘「4行が1行になっている」）——`<td>`は`\n`を空白に潰すので、PDFの物理行の切れ目を`<br>`で残す（`cell_html`。MCO説明が`control:`／`100:…`／`101:…`／`Other:…`の4行に戻る）。折り返しか意図的な改行かの区別はpdfminerに情報が無く原理的に不可能だが、**原本も同じ位置で折り返している**ので物理行そのままが「差ゼロ」に最も近い。parityも同じ`<br>`変換で検査。(4) **caption無し表の偽caption除去**（ユーザー指摘「`table-3-1@1`が6つある」）——captionを持たない表（レジスタのビット図・説明表。原本でも表番号が無い）が、continuation継承で前ページの表番号（logical_id）を借りて`<caption>`に出していた。**captionを持つ表だけが`<caption>`を出す**よう変更、内部IDは追跡用にコメントへ。偽caption 22,356個が消え、残る4,225個は全て`Table`/`表`で始まる本物（67文書parity緑）。<br>**人向け出力の仕上げ——強調・ヘッダ・折り返し（converter 1.4.0）**（2026-09-02、ユーザー「表の1行目は見た目変えられる？ボールドやイタリックは取れない？」＋「セルが3行に分割」）: (1) **太字/斜体は取れる**——fontnameで判定（BoldMT/ItalicMT。全コーパスで太字3%・斜体3.5%）。converterがline/cellに`bold`/`italic`を持ち（textは不変＝正本CSV無傷。schemaに追加）、exporterが`<strong>`/`<em>`で再現（見出しは`#`で済むのでparagraph/list-item/cellのみ）。(2) **表の1行目を`<th>`**（原本の見出し行Bit/Name/Access…がそのままヘッダ。continuation断片はrow>0なので`<td>`）。(3) **セル内の折り返しと意図的改行を文字種で出し分け**（前回`<br>`一律だったのを改良）——句読点終わりは`<br>`（MCO説明の項目リスト）、識別子途中`USAR`+`T1`は直結、英単語は空白。parityはexporterの`cell_html`と揃える。<br>**PUA記号（Wingdings/Symbol）を正規化**（2026-09-02、ユーザー「大きな黒丸みたい」＝`U+F06C`）: datasheetの箇条書き等がWingdings/Symbolフォントの記号をPUA（私用領域）のまま持つ（fontで●等に見えるが文字コードは意味不明）。全コーパスで5種を実測——`U+F06C`（●・8824個）・`U+F06E`（■）・`U+F0B7`（•）・`U+F0B4`（×）・`U+F0B1`（±）。exporterの`pua_normalize`で対応記号へ（**exporterだけ**＝bundle/正本CSVは不変・再変換不要）。parityも同じ正規化で検査。<br>**二段組を分離（converter 1.5.0）**（ユーザー「二段組が段組みになっていないで左右に連結」「1ページ目のFeaturesは確定で2段組・あきらめないで」）: datasheetのoverview/featuresページは散文が2カラムで、pdfplumberの行抽出が左カラムと右カラムを**同一行に結合**する（`- QingKe…core ● 3-group analog vol`のように左右が混ざり読めない）。**見出しで限定**して安全に分離——(1) `document_type==datasheet`かつ本文に`Overview/Features/概述/主要特性/功能概述`見出し（この限定で製品比較表・bit図・pin表を除外。全51対象ページが全部overview系＝誤検出0）、(2) 列境界は表外wordのx0の中央域（幅35〜60%）最大ギャップ（X035DS0.en p1で295）、(3) 分離は見出しbottom以降を左カラム全行→右カラム全行でcrop抽出（**タイトルは全幅帯に残す**——境界で`CH`と`H32…`に裂けるのを防ぐ。見出しの重複も回避）。境界が出ないページ（左右カラムが隣接して谷が無い版）は分離せず現状維持（安全側・誤爆なし）。**試行錯誤の記録**: 中央帯密度→overview逃す、行内ギャップ→表1012件誤爆、word行頭ピーク→閾値がp1を僅かに逃す、を経て見出し限定＋最大ギャップに到達。<br>**bit図の縦分割ビット名の結合は断念**（ユーザー「USART1RSTが3行に分割」）: X035RM p18で`USART1RST`が狭いセルに入りきらず`USAR`(行1)/`T1`(行2)/`RST`(行4)と**3つの別セル**（find_tablesが行ごとに分割・回転文字ではない横書き）。同列の縦連続セルを連結する汎用ロジックを試作したが、**全コーパス6009件中ほぼ半分が壊れた**（FV2x/H417の複雑なbit図で列境界の丸め・複数ビット混在により`RAMLRAVM L`・`PLL3POLNL3`と文字が交互になる）。X035の単純ケースは直るが他を壊すので撤回。**PDF自体も同じ狭いセルで縦3行に表示**しているので差ゼロの観点では現状が忠実——まさに「register系はつらい」領域。<br>**残タスクの総ざらい**（2026-09-02、ユーザー「できることは全部やって」）: (1) **回転ラベルの本文漏れは実は0**——1.3.1後に「asset外かつ表外の回転ラベル行」を精査すると**真の漏れ0**。以前の「76行」は計測が表内の行（`<td rowspan="3">H416RDU6</td>`等の縦書き型番ヘッダ・表セルとして正しく描画）を漏れと数えた偽陽性だった。回転文字は行・表セルの両方で組み直され、asset化か表セル描画のどちらかに収まり、本文への裸漏れはゼロ。(2) **最後のPDF直読み`extract_images`も入口ゲート経由に**——`pipeline/extract/images/run_extract_images.py`が`pdfplumber.open`だけを原本hashゲートに差し替える（pixelのcropは原本PDFが要りpdfcompatでは差し替え不可なので、openでhash照合だけ挟む。render_assetsと同じ考え）。欠落・hash不一致で停止するのをnegative test（manifest一時改変→復元）で確認。これで**PDFを直接読む全工程が「原本とbundleのずれを検出できる」実行経路の要件を満たす**。(3) cross_engineのregenerate統合は見送り——pypdfium2依存を本体（uv.lock）に持ち込まない方が良く、scan_errataと同じ手動検査のまま。<br>**取り込み正しさの独立検証（cross_engine）**（2026-09-02、ユーザー「取り込みが正しいのかを検証したい」への答え）: bundleの文字取り込みを**別実装のPDFエンジンpypdfium2**と突き合わせる`pipeline/checks/cross_engine.py`。converter(pdfplumber=pdfminer)とpypdfium2は独立実装なので、両者が取る文字マルチセットが一致すれば「片方のエンジンの癖で化けた・落ちた」が排除できる。読み順・header/footer分離は両エンジンで違うので**順序でなく文字集合**を比較。pypdfium2の**ハイフン誤読**（`-`をU+0002で読む・全コーパスで実測）は正規化。**全67版で新種取りこぼし0**——bundleは独立エンジンが取る文字を一文字残らず取り、546文字はむしろbundleが多く取る（回転ラベル等でbundleが完全）。唯一の差14文字（H417RM.zh 11・V103DS0.en 3）は**数式・単位記号のToUnicode化け**（`fxxx freq(max) !`の`!`、`RAIN R !" < Ts f #$ %`の`#$%`——元フォントが壊れ両エンジンとも読めない。lost_subscriptsと同類）で、`KNOWN_MISSED`に名前と数で固定（増えたら落ちる。KNOWNを減らすとNEWが出て赤になるのをnegative testで確認）。手動運用（mirror PDFとpypdfium2が要る・CIには入れない）。<br>**回転文字は表セルの中にも居た（converter 1.3.1）**（2026-09-02、「あとできるものある？」の棚卸しで着手）: 1.3.0が直したのは**行**だけで、表セルの文字（`table.extract()`由来）は鏡順のまま——**322表／43文書**、実例は引脚定义表の縦書き型番ヘッダ`6UEW714H`＝H417WEU6。セルにも同じ組み直しを適用（`cells[].text`と`extracted_rows`の両方。回転文字2個以上のセルだけ再構成）。**正本CSVは旧toolも同じ鏡順を読んで正規化していたため無事**だったが、人向け出力の表には裸で出ていた。検証は再変換後に`--full`のbyte比較で（旧toolが読む入力が変わるため、差分が出れば改善として個別裁定）。<br>**L2の初回review実施——対応付け残差とconflictの裁定**（2026-09-02、**ユーザー委任**「精査して判定できそうなのはそのまま承認でいい」）: (1) **対応付け残差83番号→0**。全残差を両版のcaption原文（ADC2は表の中身のR32_ADC2_*）で照合し、**151 decisionsを30 sidecarへ記録**（対45組・単独24件。canonicalは章内で自己整合な側の番号、食い違いはnoteに英語で）。過程で**「番号一致＝自動対応」が偽対を作る章**を発見——H417RM en版のch31は番号が系統的にずれ（zh 31-7=帧格式 vs en 31-7=MACFFR。multisetでは数が釣り合い残差に出ない）、ch22は番号系列が二重（en独自のCCC群7表が22-2..22-8を使い、後半のFIFO/エラー/寄存器群が再び22-2..22-6）、EthernetのTDes表3枚は**27-xと章違いの誤植**。表の形（列数差≥2）の検査で炙り出し、テキストで全対を裁定した。他にもen版の番号重複・±1ずれ・章digit誤り（V205 DS「4-2」、V205 RM「22-2」×2、X035 RM「14-4」×2、V103 DS「2-2」×2、V007 DS「3-9-2」×2、L103 RM 4件、M030 zh「7-17」、H417 zh「10-35/36」「38-1」等）と、**片版にしか無い表**（en欠落: FV2xの主机接收缓冲区・模式D FSMC_BCR1（V205 RMも）・M030のDMA映射表・M103G8R6専有引脚等。zh欠落: X315 RM 12-18）を全て記録。`propose_pairs.py`はsidecarのdecisionを尊重して残差から外すようにした（**現在の残差0**）。converterの「参照文をcaption誤認」（`注：表21-4的…`等6件）はnoteで無害化し、修正は次のconverter版へ持ち越し。<br>**conflictの裁定（第三の証拠があるものだけ）**: option系14件のうち**10件をconfirmedへ**——M030のOB base 6行（zh＋EVTヘッダの2根拠一致）、X315の`USBHSDLEN`（EVT `ch32x3x5_flash.h`）、FV2xの`RAM_CODE_MOD`×2（OBR読み出し側）、X035の`xxxb`（`rule:bit-width`＝[7:5]は3bit）。いずれも異議をbasisの`!`に保持（`adjudicate`callbackと`FIELD_VERDICTS`表として実装＝根拠がコードに残る）。**残る4件は証拠が無く裁定不能のままconflict**（IWDG_SW/IWDGSWの綴り——OBR読み出し側は第三の綴り`WDG_SW`で決め手にならない、M030のRST_MODE表記、X315のWRPR粒度——EVTにDBMODEの痕跡なし）。**operating_conditionsの40件も再精査したが不変**——8件は綴りの差（記録済み）、残りは値そのものの食い違い（H417のstop電流2.4vs4.4mA等）で**実測かWCHの確認でしか決められない**。conflicts索引は214→204行。<br>**zh/en対応付けreviewの工程を確定**（2026-09-02）: 全32文書ペアで表caption番号の対称性を実測——**16ペアは完全一致（自動対応）、非対称の残差は全コーパスで83番号**（大半は±1ずれ: L103 DS 2-2/2-3、X315 RM 23-4/23-5等。最大はH417 RMのzh 11/en 16番号）。工程は「**番号一致は自動、残差だけ人がreview**」で閉じる——[`propose_pairs.py`](../pipeline/review/propose_pairs.py)が残差を両版のcaption原文・同章のen候補つきで並べ（X315の3対は一目で決まる。en単独表=zhに無い表も可視化——X315 RM enの12-18等）、人が決めたら`record_decision.py --canonical`で両blockへ同じcanonical番号を記録する（reviewスキーマの`canonical_table_number`が最初から持っていた欄）。<br>**L2 sidecarの実行部を実装**（2026-09-02——D16完了条件(3)「未承認blockを正本生成に使わない」・(5)「原本更新時に古いreviewを自動流用しない」の機械化）: 器は最初からあった（schema `structured-document-review.schema.json`・converterの「原本が変われば再変換を止める」ゲート）が、**読む側が無かった**。`pipeline/common/review_sidecar.py`（rejectedのblock集合を返す。sidecarの`source_sha256`がmanifestと違えば読む側でも停止）を新経路の抽出器3本（extract_low_power・extract_option_bytes・extract_debug_wiring）に配線——**rejectedの表は正本生成から外れ、必須の表が拒否されたら黙って劣化せず停止する**（X035RM.zhの構造表をrejectして生成が止まることをnegative testで確認・試験後sidecarは削除）。判断の記録は`pipeline/review/record_decision.py`（実在しないblock IDを拒否・schema検証・文書statusの遷移）。classifier群のdoctest（figure_captions・lost_subscripts・review_sidecar）を`check.yml`に追加。<br>**追加toolトリガーの初発火——添字が`*`に化けるglyph**（2026-09-02）: operating_conditionsの既知の穴(1)「`0.45*V+*0.41`」の正体を特定——**PDFのToUnicodeが添字glyph（V_DDのDD等）を`*`に写している**（本文10.6ptに対し7pt、`0.45*V*+0.41`の2つ目の`*`が添字）。調査報告が明文化した「欠落→追加tool」トリガーの初の実例だが、**控えのpypdfium2でも出力が同一**＝文字層のengine追加では解決しない（候補は描画+OCRかfont形状解析——保留）。判定規則「直前の実文字よりサイズ≤0.85の`*`」を`pipeline/common/lost_subscripts.py`に一本化（脚注の`*`や図中ラベルの乗算記号`USART*8`は同サイズなので除外——H417 RMで確認）。**806 glyph／14文書を実測**（H417 DS 462・V205 DS 136…。zh/enで非対称の文書もある——FV2x RMはzhだけ破損）。**人向け出力の該当ページ冒頭に警告を出し、parity検査で印を必須化**（negative test済み・67文書全緑）。<br>**R-30: option bytesの2表を新設**（2026-09-02）: `evidence/option_bytes.csv`（98行）＋`evidence/option_byte_fields.csv`（106行）——詳細はR-30の項と[信頼度表](table-reliability.ja.md)。抽出中に**M030のOB base番地がzh/enで食い違う**のを発見（en 0x1FFFF800はコピペ疑い・EVTヘッダはzhの0x1FFFF300を支持）——**第三の証拠による裁定**を`prefer`として実装（debug_interfacesのV002/V004と同じ型。zh/en照合のキーは番地でなく**表内の相対offset**）。`build_conflicts`のSTATEDを`(列名=値)`形へ拡張（alternativeに写る行 125→138）。<br>**previewリポジトリ**（2026-09-01、ユーザー発案）: `structured-markdown`（11kファイル・95MB）の確認用に、**使い捨てのpreviewリポジトリ**（推奨名 `ch32-device-data-preview`）へ1コミット公開してGitHub Pagesで見る。`export_markdown.py --all`がトップindexを生成し、[`publish_preview.sh`](../pipeline/review/publish_preview.sh)が**毎回orphan branchを作り直してforce push**（履歴は常に1コミット・repoが育たない）。PagesのJekyll既定（相対.mdリンク変換・README index化）で成立、Liquid危険文字ゼロを確認済み。ビルド時間切れ時はgithub.comのファイルビューが代替。**左右同期ビュアー**（2026-09-02、ユーザー要望「PDFとhtmlを左右に同じページで開いて同時にページ移動」）: `export_markdown.py --all`がpreviewのトップに`viewer.html`を生成——左に原本PDF（ブラウザ内蔵viewer・`#page=N`頭出し）、右にJekyllが描画した同ページ。文書選択・ページ入力・←→キーで両側が同時に動き、状態はURL hashに残る（ページをそのまま共有できる）。PDFとpreviewが同一origin（ch32-riscv-ug.github.io）なのでiframeで成立。素のHTML（front matter無し）なのでLiquidは素通し。<br>**preview初公開のフィードバック反映**（2026-09-01）: (1) **図中のパース文字が図の下に重複表示**されていた→消さずに（検索・コピーに有用——ユーザー）`<details><summary>🖼 Text parsed from the figure above</summary>`の折りたたみに**全体をくくって**出す。図領域がページ下端に届くとfooterコメントが順序を追い越すregressionをparity検査が捕捉→同修正（67文書全合格に復帰）。(2) Pagesにはファイル一覧が無くページ移動できない→**各ページ冒頭に`← p.N / index / PDF p.N / p.N+1 →`のナビ**を追加<br>**最終ゴールの確定と人向けMarkdownの実装**（2026-09-01、ユーザー）: このpipelineの最終ゴールは**「PDFと、人が読むMarkdownの差がなくなること」**で、CSV抽出はその上の消費者。あわせて**「既知の取りこぼしは、人向け出力の中で取りこぼしていると見えるようにする」**を要件化。`pipeline/review/export_markdown.py`が全67文書を書き出し（15秒・非コミットの`.cache/structured-markdown/`）、`pipeline/checks/check_markdown_parity.py`が**差ゼロを機械検査して67文書全合格**——本文行と表の全セルが読み順どおりに現れ、header/footerはコメントで監査に残り、**図caption 2,943箇所すべての直後に「図は再現していない」の警告＋原本PDFページへのリンク**、大きい画像（封装図等）は個別の占位、表のissuesは表の直前に警告、`(cid:N)`化けの警告も装備（現状の発火は0——全67文書でglyph復号漏れなしを確認）。zh/enの正否は自動判定しない（**zh版の方が正しいことが多いがデータだけでは判断できない**——ユーザー。conflictは従来どおり両論で、reviewの事前確率としてのみ使う）。<br>**人向け出力のマージ層（L1）を実装**（2026-09-01、ユーザー要望「ページ単位だと表が分割される。もう一段マージした中間層から出力を」）: `pipeline/common/logical_tables.py`が断片の連鎖を**構造で判定**（変換器の継続flagに依存しない——無caption・ページ先頭・前ページ末尾が表・**縦位置の連続**・列構造互換。縦位置条件が無いとRMの背中合わせの同型無caption表を誤結合する）し、rowspan/colspan込みで結合。exporterは**開始ページに表全体を描き、続きページには可視ポインタ**（ファイルの分割単位はページのまま＝分割仕様は据え置き）。**67文書で跨ぎ表3,759個を結合**——D17で「継続推定が結ばない」と実証したH417 DS比較表（p3+p4）も結合された。parity検査も同じL1層で**67文書全合格**。抽出器の結合部品も共通化（A11のcandidate出力はbyte一致の回帰を確認）。<br>**図のasset renderer実装**（2026-09-01・D16が分離を予告した工程）: `pipeline/review/render_assets.py`——原本hash照合後、図領域を150dpi PNGに描き`assets.json`（bbox・PNG SHA-256）へ記録。**図領域は文字ではなくgraphicsの縦クラスタで決める**（図中ラベルがparagraph行として写るため。V003系統図で実測して方式決定）。**67文書3,307 asset（95MB・非コミット）を約3分で描画、図caption 2,884のうち2,837へ実画像を埋め込み（98.4%）**、残り47は可視の警告のまま（極小領域でskipされたもの。取りこぼしを隠さない）。独立raster画像470も埋め込み、二重警告は0。**未描画218件の分析から3つの修正**（2026-09-01）: (1) 「图19-2是…」「Figure 22-17 illustrates…」のような**本文の参照文をcaptionから除外**（判定は`pipeline/common/figure_captions.py`に一本化——句点を含む行・参照言い回しの後続。renderer/exporter/parityが共有）、(2) **波形図の箱がmicro-table誤認**（2×2・24×23pt等）でgraphicsから除外されていた——無caption・面積15,000pt²未満の「表」は図の部品としてクラスタへ算入、(3) ページ末尾のcaptionは**次ページ先頭のクラスタへfallback**。exporterとparity検査（caption直後は実画像＋実ファイル存在か警告のどちらか必須）は**67文書全合格**を維持。<br>**図カバレッジ100%到達**（2026-09-01）: 残り47件を分析、原因は3つ——(a) **図全体が1つの無caption表として誤検出**され「実表」扱いでgraphicsから除外（过滤器编号の示例は2セルで97,759pt²、DMA示意図は2セルで166,621pt²、Sinc3応答グラフは35セル）→**caption直下（NEAR以内）の無caption表は面積によらず図の部品**にする（本物の継続断片はページ先頭が定位置なのでcaptionの下には来ない）、(b) **折り返しで行頭に残った参照の尻尾**（「figure 21-1.」「Figure 6-1, the block diagram … watchdog.」「Figure 38-2: SWP Bus States.」）が偽captionになり本物のcaptionからクラスタを横取り→**半角ピリオドで終わる行は文章**（67版の全行で実測——該当13行は全部が参照文、ピリオドで終わる本物のcaptionは0）、(c) 「图40-15**和**图40-16显示了…」「Figure 40-3 **~** Figure 40-15)」の範囲・列挙参照→尻尾が`和`／`~`で始まる行も文章。結果: **図caption 2,871（参照文17行を除外後）の全部に実画像・「図は再現していない」警告0・asset 3,337**、67文書parity全合格を維持。新規領域はPNG目視でも確認（CAN过滤器編号・master/slave timer・PCM波形——いずれも完全な図）。<br>**CIが環境差を初検出→修正**（2026-09-01）: push後の`structured-repro.yml`が全ページの`geometry_sha256`不一致で赤——**gzipの圧縮バイト列はzlibの版で変わる**のに圧縮後をhashしていた設計ミス。converter 1.1.0で**非圧縮のgeometry JSONをhashする仕様に変更**（圧縮は保存の都合であって内容ではない）、独立ゲートは凍結尊重で`pipeline/checks/check_bundle.py`にfork、67版を再変換して全ゲート合格。**workflowは設計どおりの仕事をした**（原本変更とtool版違いは別の出口で報告することも実地で確認——mirror自動更新でX315/V407のzh版PDFが途中で新しくなったのも吸収）<br>[D16の最終報告](structured-document-workflow.ja.md)を出発点に、本番実装の前提を再調査してarchitecture decisionと本番schema案を決める。**converter・`pipeline/`の実装はこの項目に含めない**（報告の「PoCで選んだ方式を前提に実装を開始しない」に従う）。調査項目は報告の8項目——文書inventory再棚卸し、凍結baselineのcommit・CSV hash確定、難易度別fixture選定、変換engine比較、難所の標本監査、L0/L1/L2と無効化規則の設計、受入条件・移行単位の合意、人間向け表示の用途確認。<br>**方針として決めたこと（2026-09-01の検討）**:<br>・**最初の移行CSVは`operating_conditions.csv`**。既存1,588行を新経路で再現一致させてからA11の行を追加する。A11の「既存行を不変に保ったまま追加」は、報告の「1つのCSVで旧直読みと中間形式を混在させない」ルールとこの順で両立する。回帰標本は[先行PoC](structured-extraction-poc.ja.md)の4文書全件一致<br>・**bundleの保存方針は未決のまま、成立条件を調査項目にする**。方向は「再生成できる中間物は保存しない」。成立条件は (a) **再現性**——同一原本＋同一変換器＋固定した依存で同一出力になるか（byte一致が無理なら正規化一致で足りるか）、(b) **ズレ検出**——`manifest.json`（原本hash・全page hash・変換器版）**だけ**をコミットし、再生成bundleと突き合わせて「どのpageがいつからズレたか」を言えるか。この2つを実測してから保存の要否を決める。**review sidecar（人の判断）は再生成不能なので、原本SHA-256＋block IDをkeyに正本としてコミットする前提**<br>・**engine選定は決着**（2026-09-01。「監査用に縮小」→「白紙から全面比較」→「現行を本線に、限界が出たらtoolを追加」の順に同日で確定。いずれもユーザー判断）。ゼロベースの候補一次調査と予備実測を行った上で、**L0は現行pdfplumberを本線**とし、追加のトリガー（欠落・速度・表構造の3種）と追加候補を調査報告に明文化した。追加toolは監査・候補生成の補助に限り、L0の正本は差し替えない<br>・**zh/en対応付けを独立の調査項目に格上げ**。A11の18件偽conflictの根因であり、「canonical IDをsidecarに持つ」だけでは55版分の人手工数が見積れない。対応付け候補の自動生成→review承認の工程を設計し、標本で自動候補の的中率を実測する<br>**成果物**: 調査報告、代表fixtureと期待値、architecture decision、本番schema案、性能・容量見積り、移行計画。これらのreview後にbaselineを凍結し、実装（`pipeline/`）に入る
- [x] ✅ **D19 表の登録儀式の機械化** — 表を足すときの儀式のうち`build_conflicts`のKEYSと信頼度表の行は、**忘れても足した当日のローカル検査が通ってしまう**（KEYSはbuild_conflictsを回したときにしか落ちない）——R-29の新表でKEYS漏れが翌日のupdate.yml（CI）まで気づかれなかった実例。`check_tables.conflict_keys`（正本の全表⊆KEYS・KEYS⊆正本の両向き）と、`check_docs`のROW_COUNTS被覆検査（catalog＋evidenceの全表がtable-reliabilityのどれかの行に覆われている）を追加（2026-09-02）。**入れる前に外して落ちることを確認**（KEYSから`device_id_addresses`を消す／ROW_COUNTSから`device_ids`を消す——どちらも名指しで落ちた）
- [x] ✅ **D8 上流ツールの版の定期取得** — `catalog/toolchains.csv`新設（2026-08-27）。MounRiverのIDE・`MRS_Toolchain_*`・ベンダのチップ対応パックの**最新版15件**を、ダウンロードページの裏にある公開JSON APIから取る（`tools/build_toolchains.py`）。`.github/workflows/toolchains.yml`が毎週月曜13:20 UTCに取り直してcommit（update.ymlと同じconcurrency群なのでpushがぶつからない）。行ごとに**配信側をHEADして掲載と突き合わせ**（サイズ一致でconfirmed）。ダウンロードURLは署名つきで要求元IPに紐付くため表には入れず、URLを返すAPIを`download_api`に持つ
- [x] ✅ **D10 カタログの写しを担当ぶんだけにする** — 各 mirror が `documents.json` に**全76文書を丸ごと**持っていた（13 mirror すべて md5 一致。担当は3〜7件）。無関係な文書の download id が1つ変わっただけで13 mirror 全部に `update (automated)` の空身のコミットが立ち（実例: `CH32V003` の `28d2fc8` は `documents.json` だけの変更）、`catalog/sources.csv` が持つ mirror の HEAD が動くので**「入力が動いた」と「再生成を忘れた」の切り分け（D6 の目的）が効かなくなっていた**。`templates/update.sh` が担当ぶんだけ書くようにした（40,862 → 2.2〜4.9 KB）。取得失敗時の写しとしての役目は変わらず（`plan()` はこの行だけを読む）、**空スライスは既存の写しを上書きしない**という歯止めも追加。全13 mirror でオフライン検証済み。⚠ **13の mirror repository への反映は別作業**（このrepoはテンプレだけ持つ）
- [x] ✅ **D12 表のヘッダと生成器の列定義を突き合わせる** — 「ツールを書き換えたのに表を作り直していない」を機械で見つける（`check_tables.column_drift`）。D10 の鮮度検査は **PDF 不要な導出物しか見られない**ので、`evidence/` のずれは射程外だった。**中身の鮮度は無理でも、列の食い違いなら CSV の1行目とソースの定数を読むだけで分かる**。`tools/build_*.py` の `*COLUMNS` を **`ast` で読む**ので、pdfplumber を要する生成器も import せずに対象にできる。50表すべてに「どの生成器のどの定数か」の対応を持ち（`COLUMN_SOURCES`。`paths.py` が場所を1箇所で決めているのと対）、対応の無い表があれば落ちる。`build_tables.py` の6表は**データ列だけを定数に持ち出所列は書き出し時に足す**設計なので、「定数がヘッダの接頭辞で余りが出所列」なら通す。**書く前の測定段階で F-54 の2件目（`timers`）を見つけた**
- [x] ✅ **D11 カタログ更新が導出物を置き去りにしないようにする** — `update.yml` は `documents.csv` だけ再生成して commit していたが、**生成READMEは各文書の版番号を引用している**ので置き去りになっていた（実例: `88f7a7a update catalogue (automated)` の直後、README は EVT v1.4 のまま documents.csv は v1.5）。D10 で入れた鮮度検査があると**日次 job が自分の変更で翌 run を赤くする**ので、同じコミットで4本回すようにした（stdlib のみ・数秒。順は依存順）。実測で緑を確認
- [x] ✅ **D9 語彙のdoctestをCIで回す** — `tools/signal_vocabulary.py` の doctest は**規則そのものの説明**だが、`__main__` でしか走らないので誰も回しておらず、F-8 で `AETR2` を語彙へ入れたあとも「未解決のはず」と主張し続けていた（2026-08-28 の監査が手で回して発見）。`check.yml` に1行足した。他の tools に doctest は無い（実測）
- [x] ✅ **D15 生成器が安全に試せること** — `check_tables.out_option`（2026-08-29）。`evidence/README` は「出力先は各ツールが `tools/paths.py` で決めます（`--out <dir>` は試験用の上書き）」と**全 tool について**書いていたが、`build_operating.py` と `build_evt_examples.py` は **argparse 自体を持たず**、`--out` を渡しても黙って無視して `evidence/` に書いていた。**文書のほうが正しく、tool が追いついていなかった**——そして「安全に試す方法が無い」ことに気付かないまま長時間の実験を回して、`evidence/operating_conditions.csv` を1度潰した（コミット済みの中身から復元・byte 一致を確認）。両方に `--out` を足し、**どちらもフル実行してコミット済みと byte 一致する**ことを確かめたうえで、`paths.write`／`paths.table`・`paths.index` の戻りを書き出し先として持つ生成器に `--out` があることを `ast` で毎回見るようにした（読むだけの `build_system_figures` は対象外）。**入れる前に、外して落ちることを確認**
- [x] ✅ **D14 viewer の検査** — `tools/check_viewer.js`新設（2026-08-29）。**表には `check_tables`、文書には `check_docs` があるのに、表示だけが検査の外だった。** その結果 G1（series view の Defaults が先頭型番だけを見る）は、CH32V006 の series view で SWCLK と UART が全部 `-` になるという目に見える誤りのまま残っていた。`pins.html` の `<script>` を **DOM 無しで評価して関数を取り出し**、正本の CSV を食わせて出力を見る（ブラウザも DOM 実装も要らず、CI の node で動く）。固定するのは**壊れたら分かる少数の事実**で見た目ではない——(1) Defaults が series の全型番の和になっていること、(2) 列順が `COLUMN_ORDER` どおりで TIM が既定1列、(3) 正規化名（`SWDIO`）での検索が資料の綴り（`SWIO`）に当たること、(4) 型番に無い instance が薄表示され**持っている instance は薄くならない**こと、(5) `?chip=` 未指定で選択画面になること、(6) 比較表の見出しから資料の崩れが消えていること。**入れる前に、壊して落ちることを確認**（G1 を戻すと3件落ちる）
- [x] ✅ **D13 文書の主張の検査** — `tools/check_docs.py`新設（2026-08-29）。**データが正しくても説明が古ければ、利用者が読むのは古いほう。** 監査が実例を3件挙げた——F-11 が解決して CSV も直っているのに**7つの文書と `build_link_firmware.py` の説明**がまだ古い状態を説明していて（`README.ja.md`・`evidence/README` 両言語・`docs/README.ja.md`・`table-reliability`・`worklist-archive`・`link-firmware-survey`）、`table-reliability` の pinout 行数は5行、clock 5表の合計は1行ずれていた。見るのは3つ: (1) `table-reliability` の「行数」列を表から数え直す、(2) README 両言語の family・series・型番・表の数、(3) **worklist の F 台帳で ✅ の穴を、別の文書が「未解決」と書いていないか**（節単位で見る。1行に複数の穴が並ぶので行全体を窓にすると隣の状態を拾う）。**文書側に印は足さない**——印は書き忘れるので検査にならない。どの綴りがどの数かは tool が持ち、**綴りが変わって当たらなくなったこと自体を失敗**として言う。CI に入れ、`docs/**` と `README*.md` の変更でも走るようにした
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
受けるかどうかもここで決める。**2026-09-01からは`ch32rv`（Rust製CH32書き込みツール）も
`docs/data-requests/`で依頼を出す**（1依頼1ファイル・self-contained。R-28〜R-30が最初の3件）。

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
| R-28 | chip ID（device_id）のevidence表新設（ch32rv 0001・優先度高） | ✅ **納品受け入れ済**（2026-09-02、ch32rv側が依頼書に記載——**実測6台（V003/V103/V203/V307/L103/X035）と突き合わせ、rev bits [7:4] don't-careで全一致**。`xtask db-gen`→`target info`のchip_id→SKU解決が全5接続台で実機動作）。gap 7 seriesはch32rv曰く**未発売**（接続でき次第measured追記——届いたら`device-id:wch-linke`のbasisでconfirmed化する）。経緯: 表2枚を新設（同日、`tools/build_device_ids.py`）: [`evidence/device_id_addresses.csv`](../evidence/device_id_addresses.csv)（12行——**全familyの読み出し番地**をEVTの`DBGMCU_GetCHIPID()`から。第三者DBに無いgap familyも埋まった: V205/V407/X315=0x1ffff704、**M030=0x1ffff384**。memory_mapのCHIPID行と相互検査）＋[`evidence/device_ids.csv`](../evidence/device_ids.csv)（71行——ch32-data取込・**全行reference**。第三者DBは一次資料ではないので、confirmedは実機読み`device-id:wch-linke`との突き合わせのみ）。`id_source`（memory/attach）・`dont_care_bits [7:4]`・V103のSTM32互換note込み＝依頼書の列仕様どおり。**残り＝gap 7 seriesの値**（V205/V407/V467/X305/X315/M030/M103）——**実機が揃わないため実測は当面不可**（2026-09-02ユーザー判断）。読み出し番地は全family提供済みなので、将来実機が入手できた時点で`wlink status`等で埋められる状態にして保留。実測が届いたら行のconfirmed化・memory/attach同値性の記録を行う。なおch32-dataには目録と**末尾グレード桁だけ違う**型番が複数ある（CH32V006F8P6 vs F8P7等——対応付けせず落として見えるまま） |
| R-29 | debug interface種別（1線SWIO/2線RVSWD）の明示列（ch32rv 0002・優先度中） | ✅ **既存データぶんを実装**（2026-09-01。**新しいPDFは読んでいない**）。`index/debug_interfaces.csv`新設（27 series・swio 5／rvswd 11／未記載11）。`tools/build_debug_interfaces.py`が`evidence/features.csv`の**datasheet節見出しの綴り**（`1-wire`/`单线`→swio、`2-wire`/`2线`→rvswd）と`index/pinout.csv`のSWDIO/SWCLK padから作る。**見出しがwire数を言わないseriesは`debug_if`を空にして推測しない**——V005/V006/V205/M030/H41x/V407/V467/X305/X315（gap 7のうちM103以外が該当。**確定にはRM debug章かWCH-Link manualの読取りが要り、それがこの依頼の残り**。両対応系V00X/M030の切替条件も同様）。V208はzh版のみの見出し=reference。V007(+M007)は見出しが1-wireだがpin表はSWDIO+SWCLK両方を持つ（V00X両対応の示唆。見出しの綴りを`wording`に保つ）。見方は[index/README](../index/README.ja.md)。<br>**WCH-Link manual（zh 2.8/en 2.7・WCH-commonにmirror済み）の注記が未記載11 seriesを全て解決する見込み**（2026-09-01に構造化変換で実在を確認。正式な証拠行はD18の新経路で採る——調査メモとしてここに残す）: **1線/2線の両対応と明記**＝M030・V205（と203CC）・H415/416/417・V002/004/005/006/007・M007・V407/467・X305/315（zh/en両版が同じ注記。zhだけCH587_586を追加で挙げる）。対応表のpad（V003=PD1のみ・V00x=PD1+PB3・M030=PA3/PA2・H41x=PB9/PB8・X03x=PC18/PC19・他=PA13/PA14）は**`index/pinout`と全series一致**、V003はSWCLK欄が「-」で1線のみの裏付け。<br>**残りも完全解決**（2026-09-01・D18）: 新経路の抽出器`pipeline/extract/manual/extract_debug_wiring.py`が`evidence/debug_wiring.csv`を新設（26行・全confirmed・両対応15——**新経路による初の新規evidence表**）。`index/debug_interfaces`は2証拠の突き合わせで**全27 seriesが確定**（swio 3・rvswd 11・**both 13**・confirmed 27）。**資料間齟齬2件を発見**: manualはV002/V004を両対応（SWCLK=PB3）と括るが、両者のpin表にSWCLKが無くDS見出しも1-wire——見出しを採りmanualの異議をbasisに記録（下の台帳にも） |
| R-30 | option bytesの書き込みレイアウトと工場出荷値（ch32rv 0003・優先度中） | 🔶 **表2枚を新設**（2026-09-02、新経路のRM章抽出`pipeline/extract/rm/extract_option_bytes.py`）: [`evidence/option_bytes.csv`](../evidence/option_bytes.csv)（98行——family×バイトの配置・補数位置・書込方式。書込方式は編程手順が名指す制御bitで分類＝V003系`half-word (OBPG)`／L103・M030系`fast page, 32-bit buffer writes (FTPG)`、RMが自動反码を明記すれば`; complement auto-computed`）＋[`evidence/option_byte_fields.csv`](../evidence/option_byte_fields.csv)（106行——bit割当とRM記載の復位値）。依頼の表1に相当。**工場出荷値（依頼の表2）はRMが述べる粒度（バイト/bitの復位値）で提供**——生16バイト列の合成は導出なのでせず、新品実測との突き合わせはch32rv側の測定と依頼書どおり照合する。**WRPRの粒度も抽出済み**（2026-09-02追記）: `option_byte_fields`の`wrpr_bit_protects`列——WRPR群の説明文から「1bitが保護する範囲」（V003=1扇区1KB・V00X/X035=2扇区1KB・V205=4扇区2KB・FV2x/V407=1扇区4KB・L103=2扇区2KB・M030/V103=4KB・H417=DBMODE条件つき8K/4K）。**発見した資料側齟齬は台帳へ**（M030 en版のOB base 0x1FFFF800コピペ、X315のWRPR粒度zh/en差等）。残り: 実測ダンプとの照合（ch32rv側の測定待ち） |

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
| F-11 | WCH-Link系ファームウェアの版番号が確定しない | 5件 | ~~資料~~ ツール | ✅ **解決**（2026-08-29）。**`wcfg = major*10 + minor`**（major は全個体で 2）。調査時のこの読みは最初から正しく、否定した理由（「42=2.22 だが手元の LinkE は 2.12」）は**その個体が古かっただけ**だった。WCH-LinkUtility 3.00 で強制更新した純正 LinkE が **2.22** を名乗り、`CH32V307Ver=42` と一致。`libmcuupdate.so` の逆アセンブルでも`major=2` なら `20+minor` に落ちることを確認（MRS の表示関数 `w()` は minor≥16 で壊れ、42 を「3.6」と表示する——表に載せる値としては使えない）。実機5通りで検証し、`link_firmware.csv` に `reported_version`＋`measured_version` を追加（全一致） |
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
| F-57 | 比較表の zh/en が**同じ値を違う綴りで書くと対にならず、同じ属性が2行になる** | 1組（CH32H416RDU6 の SRAM 共有領域。zh `512KB` / en `512K`） | ツール | ✅ **解決**（2026-08-29）。`crosscheck_languages.canonical_value` に容量単位の同一視を入れた（`SIZE_UNIT`。`512KB` ≡ `512K`。`512kbytes` のように語が続くものは触らない。doctest つき）。**直したのは1組ではなかった**——CH32H416RDU6 の SRAM は **zh 3行と en 3行が丸ごと対にならず、同じ3つの事実が6行の `reference` として並んでいた**。`512KB`/`512K` の不一致で LCS の対応付けが外れ、前後の HS ITCM/DTCM 行まで道連れになっていた（`PUNCTUATION` の註が予告していた壊れ方そのもの）。**3行の `confirmed` になった**。全 family を再生成して差分を確認: 変わったのは `product_attributes`（1,721→1,714行）と `products`（CH32V003 の4行だけ）で、**値は1つも変わっていない**（変わったのは確度と出所、そして資料の並び順を写す `order`）。`product_attributes` の `reference` は **12 → 2**、`conflict` は 25 のまま |
| F-58 | 比較表の **GPIO 数の英語見出しが同義語表に無く**、中文版だけが昇格する | 4型番（CH32V003）＋同じ見出しを持つ family | ツール | ✅ **解決**（2026-08-29）。`build_tables.CANONICAL["gpio_count"]` に英語版の綴り `generalpurposeio` を足した。中文版の `通用IO` だけが列に昇格して英語版の `General- purpose I/O` が属性に残る、という非対称が消えた。結果、CH32V003 の4型番で `gpio_count` の出所が `products:zh(+pin-table)` → **両版**になり、CH32V003J4M6 は `reference` → `confirmed`（pin 表と合わない `?pin-table` の記録はそのまま残る）。`General-purpose timer` などに誤爆しないことを確認済み。**比較表の見た目は変わらなかった**——G5 の `RESTATES` が表示側で既に重複行を畳んでいたため。その歯止めは再発用に残してある |
| R-25 | consumerからの表の追加依頼3件（2026-08-25受領） | — | 依頼 | ✅ 2件実装・1件は回答（`route`の`main`/`default`を文書化）。[記録](worklist-archive.ja.md) |
| R-26 | consumerからの追加テーブル依頼4件＋参考1件（2026-08-25受領） | — | 依頼 | ✅ **全5件実装**（2026-08-25）。[記録](worklist-archive.ja.md) |

### F-11 WCH-Link系ファームウェアの版番号 ✅ 解決（2026-08-29）

**`wchlink.wcfg` の数は `major*10 + minor`**（major はこれまで観測した全個体で 2）。
`CH549Ver_RV=32`→2.12、`CH32V307Ver=42`→**2.22**。

調査時に立てた `major*10+minor` という読みは**最初から正しかった**。当時これを
否定したのは「42 は 2.22 になるが手元の LinkE は 2.12」という理由だったが、
**その LinkE が古かっただけ**だった。最新版で強制更新した個体は 2.22 を名乗る。

#### 裏づけ1: WCH のライブラリ

`libmcuupdate.so` の `McuCompiler_GetDeviceVersion` は、応答
`82 0d 04 <major> <minor> <type> <mode>` から数を作る:

```
eax = major<<4 + minor ; cmp eax,0x2f ; jg 枝B
枝A:  major*10 + minor          （10進）
枝B:  major*16 + minor - 12     （16進-12）
```

**major=2 では2つの式が一致する**（枝A=20+minor、枝B=32+minor-12=20+minor）ので、
実質 `20+minor`。2.22 → 54>0x2f なので枝B → `54-12=42` = `CH32V307Ver`。

**MounRiver Studio の表示関数は当てにならない。** `extension.js` の
`w(e)`（`12+e` を16進2桁にして上下の桁を major/minor と読む）は
**minor が16以上だと壊れ**、42 を「3.6」と表示する。比較の両辺が同じ関数を通るので
WCH の UI 上は破綻しないが、表に載せる値としては使えない。

#### 裏づけ2: 実機5通り（`tools/read_link_version.py`）

`81 0d 01 01` を投げるだけでターゲットには触らない。RV は EP 0x01/0x81、
DAP は 0x02/0x83 で**問い合わせも応答も同じ形**。

| 個体 | type | モード | 応答 | 版 | wcfg |
|---|---|---|---|---|---|
| `434A124C5596` | 1（CH549） | RV | `82 0d 04 02 0c 01 00` | 2.12 | `CH549Ver_RV=32` ✓ |
| `F90E8F067DFD` | 18（LinkE #1） | RV | `82 0d 04 02 0c 12 00` | 2.12 | 古い個体 |
| `FC928F068181` | 18（LinkE #2） | DAP | `82 0d 04 02 0c 12 01` | 2.12 | 古い個体 |
| `FC928F068181` | 18（**同一個体**） | RV | `82 0d 04 02 0c 12 00` | 2.12 | モードで変わらない |
| `0A388F068F0B` | 18（LinkE #3） | RV | `82 0d 04 02 **16** 12 00` | **2.22** | `CH32V307Ver=42` ✓ |

#3 が決め手。**WCH-LinkUtility 3.00（6月付のファーム同梱）で強制更新した純正 LinkE**が
2.22 を名乗った。`CH32V307Ver` を LinkE に結びつける MRS の読み替え
（`"CH32V305Ver"===n&&(n="CH32V307Ver")`）は**正しかった**。

`evidence/link_firmware.csv` に `reported_version`（wcfg からの復号）と
`measured_version`（実測）を持たせ、両者が食い違えば `conflict` にする。いまは全一致。
**これで「あなたのは古い」が言える。**

#### 更新の落とし穴（WCH-LinkUtility）

**繋いだだけでは更新ダイアログが出ない**（ある程度新しいと黙って通る）。
`Synchronize Current WCH-Link Firmware` を選んで強制更新する必要がある。
そして **複数の LinkE を挿していると、選択中のものではなく一覧の一番上が更新される**。
この調査で 2.12 のままだった2個体はこれに当たっていた可能性が高く、
「`CH32V307Ver=42` は LinkE のものではないのでは」と一度誤った結論に傾いた原因でもある。
**更新する個体だけを挿し、`tools/read_link_version.py` で上がったことを確かめる**こと。

#### 分かったついで

- 応答6バイト目は device 型（1=CH549 / 18=LinkE。`minichlink` の分岐とも `extension.js` の `g()` とも一致）
- 応答7バイト目はモード（RV=00 / DAP=01）。`libmcuupdate.so` が `uCurLinkMode` に入れる
- **モードを変えても版もシリアルも変わらない**（同一個体で確認）。変わるのは PID（`8010`↔`8012`）と EP だけ
- CH549 だけが RV/ARM で別ファームを持ち、wcfg も `_RV`/`_ARM` に分かれる

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

## G. 表示（viewer と生成 README）

2026-08-29 の外部レビュー（表示面）を台帳にしたもの。**データではなく「選ぶための見せ方」の問題**で、
指摘は全件をコードとデータで確認した（下の「確認したこと」欄が実測）。
G1〜G3 は表示が事実と違うので穴に近い扱い、G4 以降は導線と可読性。

| # | 項目 | 確認したこと | 状態 |
|---|---|---|---|
| G1 | pins.html の series view の Defaults が**先頭型番だけ**を見ている | `defaultsLine` が `r.part_number !== partNames[0]` で弾く。型番ごとに default set が違う series は **21/27**。CH32V006 の先頭品 `D8U7` は default 27行で **USART1 の TX/RX が1本も出ない**（他6品は47行で PD5/PD6）。**同じ穴を `build_readme.py` は塞いである**——`debug_defaults` のコメントが「**1型番だけ見ない**。CH32V006 の先頭品では USART1 が remap にしか出ない」と名指ししていて、viewer 側に反映されていなかった | ✅ **修理済み**（2026-08-29）。`build_readme.debug_defaults` と同じ読み方に揃えた——選択中の**全型番の和**を出し、全品には無い pad に `*` と `<abbr title>` を付け、AF 方式の family は `-` ではなく *none by default* と言う（`-` だと「その機能が無い」に読める）。CH32V006 の series view は「SWCLK/UART がすべて `-`」から `SWCLK = PB3*`・`UART TX = PD5* (USART1); PA7* (USART2)` になり、README の Debug/serial defaults 表と一致する |
| G2 | pin 表が**その型番の周辺一覧ではない**ことが viewer に出ない | pin 表は同じ pinout を共有する silicon の機能の和（datasheet が「所有功能，不涉及具体型号产品」と断っている。`check_counts.py` の前提）。CH32V303CBT6 は `index/capabilities.csv` で `usart` `count=3` だが pin 表には UART8 まで並ぶ。生成 README 13本と pins.html に断り書き **0件** | ✅ **実装**（2026-08-29）。product view に断り書きを出し、生成 README の `## Pin definitions` にも `> [!NOTE]` で同じことを書いた。**型番ごとの薄表示は G12** |
| G3 | org トップの feature 表の `*` が**tag 名に付いていて series に付いていない** | `mark = "\*" if tag in loose else ""` を **tag 名のセル**（`**{tag}**{mark}`）に置いており、文言は「Series marked \*」。55タグ中 **23** に `*` が付き、うち **7タグ（CLOCK・CMP・I2C・OPA・POWER・RTC・USART）は part 確認済みと datasheet 単位が混在**していて、tag 単位の印はその区別を潰す（(tag, series) 637組のうち datasheet 精度は 384組） | ✅ **修理済み**（2026-08-29）。`loose` を (tag, series) にして series 名のほうに `\*` を付けた。文言も「A series marked \* …」に直した。印は 384 個（datasheet 精度の (tag, series) 組数と一致）。例: I2C の行で `CH32X033\*, CH32X035\*` だけが印になり、他11 family は型番単位で裏付け済みだと読める |
| G4 | org トップに **viewer への導線が無く**、主用途の「型番を探す」が後ろ | `_profile.md` に `pins.html` **0件**（family README には8件ある）。節順は mirrors → Find your part → Find by feature → …。型番例は素のテキスト | ✅ **実装**（2026-08-29）。節順を Find your part → Find by feature → **Pin-function viewer**（新設）→ Device documentation mirrors に変え、型番例を viewer への直リンクにした（4つ目以降は `… all N` で series view へ） |
| G5 | 資料由来の**崩れた見出しが表示まで届く**／GPIO 行が重複 | `CH32V003.md` に `General- purpose I/O`・`Advanced- control timer`・`General- purpose timer`、`CH32V307.md` に `Communication interfaces Ethernet`。しかも `General- purpose I/O` は固定行の **GPIO** と値が同一（14/18/18/6） | ✅ **実装**（2026-08-29）。表示側だけを直した（証拠は資料の綴りのまま）。`tidy_label()` が折り返しで割れたハイフンを畳み（`General- purpose I/O` → `General-purpose I/O`）、群の名前自体が分類語でしかない `Communication interface(s)` は葉が普通の英単語1つでも剥がす（`Communication interfaces Ethernet` → `Ethernet`）。GPIO の重複行は **値が全型番で一致するときだけ**落とす（`RESTATES`）——根本原因は F-58。`pins.html` の `leafOf`/`comparisonHTML` にも同じ規則を入れた |
| G6 | 大きい family の README が**選ぶための表になっていない** | `CH32V307.md` は1,064行で、pin map が 178〜996行＝**818行（77%）**。比較表4つ。V307 の比較表は29行あって**差があるのは3行だけ**（GPIO・DVP・FSMC）。Pin definitions の見出しは既に型番リンクだが、Product comparison は素のテキスト | ✅ **実装**（2026-08-29）。(1) 冒頭に**見出しの一覧から作る**ジャンプ行（Choose a part・Pin viewer・Pin maps・Errata・Examples・Documents・Address map。その README に無い節は出さない）、(2) 比較表は**差のある行だけ先に出し**全仕様は `<details>`、(3) 比較表の型番見出しを viewer への直リンクに、(4) `Pinouts`→`Packages & pinout drawings`／`Pin definitions`→`Pin maps & alternate functions`、(5) series が複数ある family は pin map 本体を `<details>` に。**畳まれていない行数**は CH32V307 が 1,064 → **226**、全 family が 260 行以下になった |
| G7 | feature 55種が**選定に効く項目と共通項目を同列**に並べる | **13タグが27 series 全部に付く**（CLOCK・DMA・EXTI・GPIO・I2C・LDO・LOW-POWER・MEMORY・PFIC・POWER・SDI・SPI・TIM） | ✅ **実装**（2026-08-29）。8分類（Connectivity・Analog・Motor and power drive・Display, audio and camera・Memory and storage・Timers・Security・System）に分け、**全 series が持つ15機能は `<details>` に畳んで `every series` と1語で書く**。分類内は覆う series の少ない順（選定に効く順）。分類に無いタグが現れたら生成が落ちる。**この過程で欠陥を1つ直した**——`USB` は `curated/feature-tags.json` で `parent` が自分自身なので `if r["parent"]: continue` に落ち、**表から丸ごと消えていた**。子タグを親にも足す（註が言うとおりの挙動）ようにして `USB`／`USB / USBHS` の両方が引けるようにした。分類は表示側に持つ（索引に事実を足さない規則） |
| G8 | pins.html の操作性 | 列順は `ADC/DAC → TIM1..n → USART → …→ SWD → SYS`（USART が全 TIM の右、SWD/SYS が最右）。検索は pad と**生の綴りだけ**で正規化済み `peripheral`/`role` に当たらない。URL に `q=` 無し・Clear 無し・confidence 表示無し・remap 信号から selector 表への移動無し。`?chip=` 未指定は `series[0]` = **CH32H415** を勝手に開く。型番選択は103項目の native select | ✅ **実装**（2026-08-29。G9 のあとに実施——正規化検索と confidence 表示が `index/pinout.csv` を前提にするため）。(1) 列順を **SWD → SYS → USART → I2C → SPI/I2S → CAN → USB/PD → ETH → TIM → ADC/DAC → 特殊**に（**当てる順と出す順を分けた**。`GROUPS` は正規表現の当たり順で、表示順は `COLUMN_ORDER`）、(2) TIM は既定で1列・`split TIM` で instance 別、(3) 検索文字列を `q=` で URL に保存、(4) `Clear filters` ボタン、(5) 検索が**正規化済みの `peripheral`/`role` にも当たる**（CH32V003 は `SWIO` と綴るが `SWDIO` で引ける）、(6) `confidence` を `~`（単一出所136行）・`!`（両版が食い違う12行）で、selector を決められない remap 値を `?`（3行）で表示、(7) remap セルが `#sel-<selector>` へのリンクになり Remap selectors 表の該当行が光る、(8) `?chip=` 未指定で **CH32H415 を勝手に開かず**、series と型番の一覧を出す、(9) 型番選択を `<input list>` の combobox に（`V307` と打てば4件に絞れる） |
| G9 | viewer が**同じ事実を2通り読み込む** | 6ファイル計 **6.22MB**。`evidence/pin_functions`(2.66MB)＋`evidence/pins`(0.42MB) と `index/pinout`(3.13MB) の**両方**を読む（matrix は前者、Defaults は後者）。`index/pinout.csv` は pin・pad・signal・route・peripheral・role を持つので1本で足り、**約3.1MB 減と検索の正規化が同時に片付く**。ただし完全な等価ではない——pin_functions だけに314行（`PC13-TAMPER-RTC` の GPIO 名など）、pinout だけに319行（`XI`/`XO`/`SSRXA` など pad 名＝機能）がある | ✅ **実装**（2026-08-29）。読み込みを `catalog/products`・`index/pinout`・`evidence/product_attributes`・`evidence/remap_fields` の4本にし、`evidence/pin_functions`(2.66MB) と `evidence/pins`(0.42MB) をやめた。**6.22MB → 3.45MB（-44%）**。`(pad, pin)` の集合が **103型番すべてで両者一致**することを確認してから外した（`evidence/pins` は lead 番号にしか使っていなかった）。副産物として、matrix の行が正規化済みの `peripheral`/`role` と `confidence`・`selector` を持つようになり、G8 の (5)(6)(7) が素直に書けた |
| G10 | `Flash` と `Code FLASH (bytes)`、`Clock` と `CPU main frequency` が重複に見える | Flash は**本物の重複表示**（`**Flash** 256K` は零等待領域、`Code FLASH (bytes) 480K` は総容量。F-14）。**Clock のほうは既に解決済み**——CH32V003 の Series 表は 48 MHz（電気的最大の 50MHz ではない。A4）で、V003 に `cpu_main_frequency` 行は無い。誤りではなく明確化 | ✅ **実装**（2026-08-29）。**両方が出るときだけ**名前で区別する——比較表が `Code FLASH` を持つ family では固定行を `Flash (zero-wait)`、属性行を `Code FLASH, total (bytes)` にする（持たない family は `Flash` のまま。零等待と総容量が分かれるのはその family だけなので）。Series 表の列は `Clock` → `Main clock` に改め、**F_MAIN を持たない5 series**（CH32X033・X035・H415・H416・H417）の値に `\*` と脚注を付けた——22 series は datasheet の系統主頻、5 series は電気的特性表の上限で、「定格ではなく限界」と書き分けた |
| G11 | 表示専用 JSON キャッシュ（`generated/viewer/<series>.json`） | G9 で 3.1MB 減るので、まずそれを測ってから決める | ✅ **測って、作らないと決めた**（2026-08-29）。G9 後の viewer のペイロードは **raw 3.46MB / gzip 218KB**（G9 前は 6.22MB / 362KB）。GitHub Pages は gzip で配るので転送は 218KB、残るコストは client 側の CSV 解析で **`index/pinout.csv` 24,982行が約 250ms**（desktop 級の V8 で実測）。series 別 JSON を置けば解析は 1/12 になるが、**正本の複製を持つことになり**（`index/README` の「型番ごとに切ったコピーは持たない」）、生成物・CI の鮮度検査・manifest・腐りの経路が増える。**その対価に見合わない**と判断。再検討の目安は「pinout が倍になる」か「解析が 1s を超える」 |
| G12 | `index/capabilities.csv` を使って**その型番に無い instance を薄表示**（G2 の完全版） | `usart` は 101/103 型番、`i2c` 91、`timer-general` 100 で素の整数の `count` が引ける（`spi` 72・`can` 48・`adc` 25 は資料が数を書かない型番があるので「主張なし」を持てること）。**G9 のあとに実装する**——matrix が `index/pinout.csv` の正規化済み `peripheral` を読むようになれば、綴りから instance を割り出す処理が要らなくなる | ✅ **実装**（2026-08-29）。product view で `index/capabilities.csv` を読み、**その型番の比較表が数えていない instance を薄表示**（消さない。tooltip で理由を出す）。規則は保守側に倒した——(1) pin 表の instance 番号と比較表の数が対応する周辺だけ（USART・SPI・I2C・CAN・I2S。`check_counts.py` が突き合わせているのと同じ集合）、(2) 比較表が**素の整数**を書いているときだけ、(3) **pin 表の instance 数が比較表の数より多いときだけ**、小さい番号から数のぶんを残して残りを薄くする。(3) が要るのは V30x の I2S が **2 と 3 しか無い**（I2S1 が存在しない）ためで、「番号 > 数なら無い」と読むと正しい I2S3 を消してしまう。**番号が1から始まらないのに落とす例は 0 件**であることを確認済み。実測 43 instance / 28 (型番, 周辺) 組。例: CH32V303CBT6 は USART4〜8・SPI3・CAN2 が薄くなる（レビューが挙げた例そのもの）。追加ペイロードは gzip 10KB |

**決めたこと**（着手前の判断。レビューと違えたものは理由つき）:

- **G1 は「全型番の和＋package 差の印」を採る**（レビューは「Defaults を出さない」を推奨）。理由は
  `build_readme.py` に**和を取る実装がすでにあり**（`debug_defaults` と `usart_choice`）、
  そちらに揃えれば二重実装が1つの読み方に寄るため。出さない案だと README と viewer で
  「同じ問いへの答え」が食い違ったままになる
- **G7 の分類は表示側（`build_readme.py`）に持つ**。分類は device の事実ではなく見せ方なので、
  索引に入れると「索引に事実を足さない」規則（[data-layout](data-layout.ja.md)）の境界が濁る。
  consumer から要求が出たら `index/features.csv` に列を足す
- **13 mirror への反映は別作業**。このリポジトリが持つのは `generated/readme/` までで、
  push は D10 と同じ扱い

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
| 4 | ~~**D17** PDF構造化の本番移行・事前調査~~ | ✅ **完了**（2026-09-01）。後続はD18 |
| 5 | **D18** PDF構造化の本実装 | 🔧 **進行中**（2026-09-01〜02）。ingest（converter 1.2.0）・L1結合（3,770表）・人向けMarkdown（差ゼロ検査67文書合格・図caption 100%・添字破損の警告）・一括再生成entry point（`--full`で全CSVをbundle入力で再生成）済み。**凍結PDF tool 19本すべて新経路で従来以上、工程(5)の一括切替も成立**（`--full`初回実行で全正本byte一致・生成手順もbundle入力形へ）。L2 sidecarの実行部（rejected除外＋record CLI）も実装済み——**D16完了条件5点が全部立った**。新経路の新規evidence: debug_wiring・option_bytes/option_byte_fields（R-30）・device_id_addresses/device_ids（R-28受入済）。<br>**converter 1.6.0（人向けMarkdownの忠実度・2026-09-02）**: 2カラム分離・太字/斜体・PUA記号の正規化・図captionの誤検出抑止・ページ境界セルの折り込み・**下付き/上付きの本文行統合**（`V`+`DD`→`VDD`、単語スペース保持。下流のoperating_conditions説明文も`V`→`VDDK`と改善）・**レジスタbit図の組み直し**（番号行→ヘッダ・16等幅・折り返し復旧・TIMの2段保持・罫線無し単一フィールドの合成。bit番号x中心で列マップ＝抽出の列数差に非依存。全67本parity 0、RMカバレッジ94-98%）・**表セル中央寄せ＋長文左寄せ**。検証中に2バグ修正（bit図の誤チェーン→mergedセルbbox欠落でexport中断／隣接セルのbit中心二重主張→グリッド衝突）。**QA監査ツール** `pipeline/review/audit_pages.py`（残る「変な箇所」をスコア化・viewerリンク付き）。残り: L2の実運用（conflict裁定の記録蓄積）・zh/en対応付けreviewの工程化・**QA巡回での100%詰め**（表セル/図中の下付き孤立304・byte境界bit図187・table_issue 1068の目視。bundleセル変更はcanonical byte一致に触れるので要慎重） |
| 6 | **D7** GitHub Actions化 | 抽出の作り込みが落ち着いてから（計画は上記） |
| 7 | C1〜C3 画像 | 保留のまま |

### 4. 2026-08-29 の監査からの残り

外部レビューが挙げた項目の処置。**取り入れたもの2件は上の A10・D13**（型番×能力の縦持ち索引と、
文書の主張の検査）。残りはここに置いて、着手の順と理由を決めてから動く。

| 項目 | 判断 | いま言えること |
|---|---|---|
| **電気特性・低消費電力**（絶対最大定格・動作/待機/スリープ電流・Flash 書換回数と保持期間・各低消費モードのウェイクアップ時間・GPIO 駆動能力と入力閾値・ADC 精度） | ✅ **実装**（2026-08-29） | **抽出器を書く仕事ではなく語彙を広げる仕事だった。** `build_operating.py` は**すでに電気的特性表と絶対最大定格表を歩いていて**、`KEEP` 正規表現で落としているだけだった。**304 → 1,588行**（記号187種・全27 series・confirmed 1,379 / ref 179 / conflict 30）。内訳は 電圧・しきい値 489／時間 393／クロック 195／電流 148／抵抗 70／容量 66／温度 34／ADC 誤差 32／Flash 寿命 21。監査が名指しした項目はほぼ入った——`N_END`（書換 300K回）・`t_RET`（保持 20年）・`I_DDA`・`t_SU(HSI/LSI/HSE)`・`t_STAB`・`V_IH`/`V_IL`/`V_OL`/`V_hys`/`I_lkg`・`t_s`/`t_CONV`/`f_S`/`R_ADC`/`C_ADC`・`ED`/`EL`/`EO`/`ET`・`t_prog_page`/`t_erase_*`・`T_J`。<br>**やり方**: (1) `KEEP` を記号の一覧ではなく**頭字＝物理量**にし、単位で弾く（`UNIT_FOR` を拡張。`T_S_*`・`t_RET`・`N_END` は具体規則を先に置く先勝ち）、(2) 値の判定を `reads_as_value` に書き直して**式**（`0.22*(VDD-2.7)+1.55`）と記号（`VREF-`）と `∞` を採る、(3) 値の欄の**添字修復**`attach_value_subscript`（`V-0.4DD` → `VDD-0.4`）、(4) 見出し行（`Symbol`）と2記号が畳まれた行を落とす。<br>**検証**: 既存 304 行は**1行も欠けず確度も根拠も不変**（純粋な追加）。probe が落とした87通りの値を全部新しい規則に通して45採用・42却下を1件ずつ確認。単位と物理量の不一致 0。データ列の CJK 0。`index/parts.csv` と生成 README は**無変化**（クロック・電圧の読み方に影響なし）。<br>**残り**: (a) ~~消費電流とウェイクアップ時間~~——A11 として切り出し、**2026-09-01に受入済み**、(b) **添字が `*` に化けた式**（19通り。推測になるので埋めない）、(c) conflict 30 のうち**8件は綴りの差**（`mS`/`ms`・`0.8VDD`/`0.8*VDD`・`VI/O`/`VIO`）で、単位の大小を無視する正規化は `MΩ`/`mΩ` を潰すため入れていない |
| **機械可読な列定義**（`meta/columns.csv`。型・単位・主キー・空欄の意味） | ⬜ 保留。**要求は本物だが置き場所が違う** | 空欄の意味が混ざっている（該当しない／資料にない／未解決／variant 依存／0個／索引では意図的に省略）という指摘はそのとおり。ただし51表・約500列の台帳を人が別ファイルに書くと、**それ自体が次に腐るもの**になる。`check_tables.column_drift` がすでに「ヘッダ＝生成器の `*COLUMNS` 定数」を毎回見ているので、足すなら**定数の隣に型と空欄理由を書き、そこから生成する**形にしたい。着手前に consumer がどの列で困っているかを聞く |
| **出所・矛盾の縦持ち索引**（`claim_id, subject, predicate, value, source, ...`） | 🔧 **安い部分を実装**（2026-08-29）→ `index/conflicts.csv` | `basis` が1セル内の DSL なので横断で引けない、というのは事実。まず `confidence=conflict` の行だけを集める索引を作った（**証拠の表の conflict は 204 行**。memory_configs 67・register_fields 38・operating_conditions **40**（A11受入とX315 zh改版で2026-09-01に30→40）・product_attributes 25・pin_functions 12・option_byte_fields 4（R-30の新表。8→4は2026-09-02の裁定）・clock_symbols 5・opa_cmp_registers 5・registers 4・adc_internal 2・flash_geometry 1・timers 1。この数は `check_docs.py` と `check_tables.py` が数え直す）。`basis` から `!<出所>` と `(=<値>)`（新経路の `(address=…)`・`(field=…)` 形も）を取り出すので、**129行は「表が採った値」と「相手が言う値」が横に並ぶ**（例: CH32V407 `RCC_CFGR2.UTMI1ON` は EVT が bit31・RM が bit30）。残る75行は、食い違いを散文で記録している表（memory_configs・timers の68行）と、**相手が「値を書かない」型**（新しいX315 zh版がFlash時間のmaxを載せない等）。**分かったこと**: `product_attributes` の25行は仕様の差と**言い回しの差**（`Typical: 72MHz` / `Typ. 72MHz`）が混ざっていて、conflict の印が「本当の食い違い」と同義ではない表がある。claim 表まで広げるかは、この索引が使われるかを見てから |
| **版間差分のデータ化** | ⬜ 保留 | git 履歴はあり、`catalog/sources.csv` が読んだミラーの commit を持つので材料は揃っている。**D7（生成の Actions 化）と一緒にやるのが自然**——差分を出す主体が定期実行だから |
| **ブート・書込み・保護設定の意味索引**（option byte・BOOT 条件・読み出し保護・IAP・debug 無効化・reset source） | ⬜ 保留。**consumer が現れてから** | register field は `index/registers.csv` に揃っているので、足りないのは目的別の語彙だけ。ただし**いま作ると語彙を推測で決めることになる**（どの粒度で引きたいかは使う側が決める） |
| **パッケージ実装情報**（辺ごとの lead 数・番号方向・exposed pad 寸法・推奨ランド・courtyard） | ⬜ 保留 | PCB や部品ライブラリの生成まで見るなら要るが、consumer からの依頼が無い。画像 C1〜C3 と同じ扱い |

**見つけたこと（監査の指摘ではないが、A10 の過程で分かったもの）**:

- **比較表の `-` は証拠に残っていない。** `build_tables.attribute_rows` が空欄・`-`・`—` のセルを
  落とすので、`product_attributes` にも `index/capabilities.csv` にも現れない。結果として
  「行が無い＝持っていない」と読めるのは **family の中だけ**（family をまたぐと「その family の
  比較表にその行が無い」と区別が付かない）。証拠に `-` の行を持たせれば区別できるが、
  全表の行数が動くので別作業。いまは `index/README` に読み方として書いてある
- **F-57**（zh/en が同じ値を違う綴りで書くと対にならない）はこの過程で見つけた

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
| R-29 | WCH-LinkUserManual vs CH32V002/V004 DS | manualの両対応注記はV00x群を一括で括る（SWCLK=PB3）が、V002/V004のpin表にSWCLKが無く、見出しも1-wire | `debug_interfaces`は見出し（1線）を採り、manualの異議を`!WCH-LinkUserManual.PDF(swclk=PB3,dual=yes)`としてbasisに記録 |
| R-30 | CH32M030 RM **en版** | option bytes章の「User option bytes information structure」表の番地が**0x1FFFF800**（他familyからのコピペ疑い）。zh版は0x1FFFF300で、EVTヘッダ`ch32m030.h`のOB baseも0x1ffff300 | `option_bytes`はzh＋EVTの**2根拠一致でconfirmed**（2026-09-02裁定・ユーザー委任）、enの異議は`!CH32M030RM.PDF:en(address=…)`でbasisに残す。同章のWRPR群名もenは`WRPR0 - WRPR3`とコピペ（M030のWRPRは2バイト。zhは`WRPR0–WRPR1`）——両論をreference 2行で保持 |
| R-30 | RM option bytes章の版間齟齬（識別子・復位値・WRPR粒度） | 文書ごとにzh/enで綴りが逆転（V003: zh `IWDG_SW`/en `IWDGSW`、V205はその逆——OBR読み出し側は第三の綴り`WDG_SW`）。X315はzh `USBHSDLEN`/en `USBFSDLEN`（**FSとHSの違い**）。X035の復位値はzh `xxxb`/en `xxb`。FV2x/V3x enはSRAM分割fieldを無名のまま（zhは`RAM_CODE_MOD`と命名）第3列に復位値`xx1b`を置く。**X315のWRPR粒度**はzh「1扇区（4K字节/扇区）」/en「DBMODE=1: 8K・DBMODE=0: 4K」（enはH417と同文。EVTにDBMODEの痕跡なし） | **第三の証拠がある3種は2026-09-02に裁定済み**（ユーザー委任）: X315のbit名=`USBHSDLEN`（EVT `ch32x3x5_flash.h`が支持）・FV2xのfield名=`RAM_CODE_MOD`（OBR読み出し側が支持）・X035の復位値=`xxxb`（`rule:bit-width`——[7:5]は3bit）——いずれもconfirmed＋enの異議をbasisに保持。**証拠の無い4件はconflictのまま**（IWDG綴り2・M030のRST_MODE表記・X315のWRPR粒度＝実測かWCH確認待ち） |
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
