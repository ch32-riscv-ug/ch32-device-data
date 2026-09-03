# 人向けMarkdown QA巡回ログ（D18の100%詰め）

`check_markdown_parity`（PDF→bundle→Markdownの取りこぼし・順序ゼロ）を通ったうえで残る
**読みにくさ**を、`pipeline/review/audit_pages.py`で機械的に洗い出し、安価なサブエージェント
巡回と実地調査でつぶしていく作業の台帳。**やり方**: 安全に直せるものは直し、canonicalの
byte一致や既存の描画を崩しそうなら撤退し、その経緯をここに残す（消さない）。

判定はしない（原典の誤りは原典のまま）。canonical（凍結CSV）に触れる変更は`--full`の
frozen parityで検証し、driftが良性（説明文の改善のみ）であることを確かめてからにする。

## 監査信号（`audit_pages.py`）と現況

| 信号 | 直近数 | 意味 | 状態 |
|---|---|---|---|
| `subscript_orphan` | 304→**96** | `V`と下付き`DD`/`BAT`等が別行 | 🔎 本文/図ラベルは1.6.1/1.6.2で解消。残96は基底Vが表セル内(56)か図中(no-base)——前者はbundleセル変更でcanonical注意、後者はcaption無し図の撤退に含む |
| `table_issue` | 1068→**73** | 変換器が記録した重なり（⚠警告付き） | 🔎 図をtable抽出したもの。221は図の<details>に畳まれ済み・本文で崩れて見えるのは73。監査を図領域外だけ数えるよう精緻化 |
| `bitnum_leftover` | 299 | bit番号行が素のテキスト（bit図未組み直し） | ⬜ 大半ページ境界split |
| `nonstd_bitdiagram` | 136 | 降順でない番号列 | ✅ 全て正しく対象外と確認（下記）。見落としパターン無し |
| `long_line` | 17 | 300字超の本文行 | ⬜ 未着手 |
| PUA / cid | 0 / 0 | 非表示文字 | ✅ 解消済み |

## 試行の記録

### ✅ 完了

- **下付き孤立（図ラベル）** — converter 1.6.1（2026-09-03）。原因: 図中の電圧ラベル
  `V_BAT`の下付きが8.2pt（body 10.6の77%）でグローバル閾値0.72を超え「本文行」扱いに
  なり基底`V`とマージされなかった。修正: **隣接する基底との相対サイズ**（`小 < 基底×0.82`）で
  下付き判定。結果: 全67本で304→112、L103DS0 p36は18→0、CH32xRM.en 10→1。過剰マージ
  なし・parity 67/67・**canonical drift 0**（frozen parity合格。1.6.1が拾うのは図中なので
  電気表に波及せず）。サブエージェント巡回（haiku×3・17ページ）が最頻の高深刻度として発見。
- **サブエージェント指摘の誤検出の検証** — `APB1_DIV&amp;gt;`（二重エスケープ）は実際は
  `&gt;`で正しい単一エスケープ。`Overivew`はPDF原文の誤植（当方バグでない）。haikuは
  false positiveを出すので、指摘は必ず実地確認してから着手する。

### ✅ 完了（続き）

- **bit図セルの境界重複＋折り返し**（`EReserved`/`URese rved`）— export側apply_bitfield
  （2026-09-03、ユーザー報告）。セル境界に載った1文字がpdfplumberで**隣のセルにも二重
  取り**され、`LP_REG`の`E`が右隣に入り`E\nReserved`→`EReserved`（X035RM p11）、`USART`の
  `U`が左隣に入り`U\nRese\nrved`→`URese rved`（X035RM p19。`Rese`+`rved`はcell_htmlが英単語と
  みて空白挿入）。geometryのcharに`E`/`U`は無く重複と確定。修正: データセルを列順に見て、
  先頭「1文字＋改行」がその文字が**左隣末尾2文字か右隣先頭2文字**に重複するなら落とし、残りの
  折り返し行は空白なしで繋ぐ（bit名は識別子）。全67本parity 0・`Port E Reserved`等の正当な
  文は誤検出せず。**表セルの中身がCSVに効く可能性**があるが、これはbit図ダイアグラム専用で
  凍結canonical（説明表由来）には非依存。

### テーブル表示

- **全テーブル同幅**（2026-09-03、ユーザー要望）— レジスタごとに幅が変わっていたのを、
  PAGE_STYLEの`table{width:100%;max-width:960px}`で統一（bit図は`table-layout:fixed`維持）。
  CSSのみ・parity非影響。

## CSVに効く抽出アーティファクト（ユーザー重点）

コミット済みCSVを直接スキャンして、抽出の崩れが正本データに残っているものを探す。人向け
Markdownの`cell_html`は`V`+`DDK`を`VDDK`に結合するが、CSVを作る抽出器は生セルを読むので
別に崩れが残りうる。

- **下付き分離（operating_conditions.csv）** — ✅ **A11の49件を修正**（2026-09-03）。
  セル`In operating\nmode, V\nDDK\n…`の`V\nDDK`が空白繋ぎで`V DDK`に。`norm_text`は凍結
  `build_operating`と共有していて触れないので、A11追加行（extract_low_power）の
  parameter/condition **だけ**を後処理で結合（`_merge_subscripts`。凍結baseは通らない）。
  結果: `V DDK`→`VDDK`・`V DD12A`→`VDD12A`等、diff 49挿入/49削除で**A11行だけ変更**、
  凍結base 1,588行は不変（byte一致保持）。build_conflicts/build_index再生成＋check_tables/
  counts/docs全合格。**凍結canonical（registers/pins/products）は不変**。
  - **凍結base 31件も修正済み**（2026-09-03、ユーザー「良くなることは全部」）。`build_operating`
    （凍結・byte再現の参照実装）は触れず、**合成層`build_operating_conditions`でbase行の
    parameter/conditionに`_clean_text`を後処理**（build_operatingの旧出力byte再現は保ったまま
    正本CSVだけ綺麗にする層）。`V_DDIO < V REFP`→`V_DDIO < VREFP`。残subscriptアーティファクト0。
  - **説明列の全角約物も半角化**（`_clean_text`＝下付き結合＋`～，．：；＜＞（）％＋／＝！`→半角）。
    `V ＜ V REFP DDIO`→`V < VREFP DDIO`。**値列 min/typ/max は触らない**（範囲`6～24`等はそのまま）。
    説明列の全角0に。ただし`V < VREFP DDIO`の`DDIO`は抽出が語順ごと崩したもの（下付き結合では
    直せない・部分改善）。全検証合格（check_tables/counts/docs）・**凍結canonical不変**。
- **日本語（ひらがな/カタカナ）: 全CSVで0件** — ✅ 「日本語禁止」違反なし。
- **中国語（CJK漢字）** — features/product_attributes等の**対訳列**（zh datasheetのfeature名）で、
  英語列と併記の**正当なデータ**。全角`（）`もその中国語文の正しい句読点。ルール「日本語禁止」は
  維持者の作業言語のことで、source言語の中国語は対象外。
- **全角句読点のアーティファクト**（英語列）— ✅ operating_conditionsは`_clean_text`で半角化済み
  （説明列のみ・値列は不変）。**他CSVにも英語列の全角が残る**（CJKを含まないセルで判定）:
  列構造で精査したら大半は**正しい全角**だった: product_attributes 31（`GPHA（5）`）は
  **`label_zh`（中国語ラベル列）**にあり正しい（`label_en`は半角）。ヒューリスティック
  「CJK文字を含まないセル」がLatin名＋全角約物を誤判定していた。真の英語列アーティファクトは
  **evt_examples 6（`description`列の`sleep，shutdown`＝zh作者のEVTコメント由来）・dma_requests 6
  （`note`列の脚注記号`（1）（2）`＝zh RM由来）程度で軽微**。各生成器（build_evt_examples/
  build_dma_requests）の個別修正＋--full検証に見合わないので保留。やるならその2列だけ半角化。
- **`√`（チェックマーク）** — product_attributes/capabilitiesのyes標識（source由来）。76件。意図的とみて保持。

### 🔧 調査中 / 進行中

- **cross-page bit図** — export側（2026-09-03）。番号行がページ末尾（y>高さ80%）で箱が
  **次ページ先頭**にある分割237件を回収。`export_markdown.document_bitfields`が文書全体の
  ページを見て、ページN末尾の未ペア番号行→ページN+1先頭のdiagram-like箱を、x重なり>60%を
  条件に対応づけ、番号行のx中心（ページNのgeometry）でページN+1の箱をbit図化する。番号行
  ページには「次ページの図へ」の可視ポインタ。exporter・parity・auditが同じ`document_bitfields`
  を使う（parityは箱のセルを検査、番号行はskipで消費）。**結果: bitnum_leftover 299→80**。
  実例: FV2x.zh p40番号行→p41-table-001（RCC_INTR高位half）が`31..16`ヘッダ＋
  `Reserved`/`CSSC`/`PLL3RDYC`…と正しく再構成（縦割れも連結）。全67本parity 0・canonical
  非依存（凍結toolはdocument_chainsのみ使用、bit図関数は使わない）。落とし穴: `bitfield_plan`の
  早期returnが`cross`/`cross_note`キーを欠きKeyError→export/parityが静かにクラッシュ（出力を
  /dev/nullで隠していて気付きにくかった）。早期returnにキーを追加して解決。
- **下付き孤立の残り（基底あり27）** — converter 1.6.2（2026-09-03、検証中）。1.6.1後も
  残る112を分類: 基底V行あり27・表内56・基底なし104（重複あり）。「基底あり27」は
  小さいCJK/ラベルが多くbody中央値が低いページ（H417DS0 zh p121: body 8.6）で、候補
  フィルタ`size >= body*0.90`が基底V 11.9に対する下付きSSA 8.2（中央値比0.95）を弾いて
  いた。修正: 候補フィルタを`size > body`（中央値以下は全部候補）に緩め、実判定は相対
  サイズ<0.82に委ねる。実測: H417DS0.zh p121で`VSSA`/`VDD33A`がマージ、密なレジスタ
  ページ（X035RM p17/140）は0変化＝回帰なし。全67本の再変換＋`--full`で検証中。
  **残る「表内56・基底なし104」は基底Vが表セル/図中にあり、行しか見ない
  `merge_subscript_lines`では届かない**（表セルの下付き統合はcanonicalに触れるので保留）。

### 🔎 調査済み（性質を確定・当面は現状維持が妥当）

- **table_issue（本文で崩れて見える73）** — 全てclock tree/FSMC/USBの**ダイアグラムを
  table抽出**したもので、本物のデータ表ではない（1-2 issueも clock tree図）。294表中221は
  図領域として描画され`<details>🖼`に畳まれ表示は綺麗、残73は図アセット化されず本文に
  崩れた格子＋⚠警告で出る。**真の解決は図領域の検出改善**（render_assets/converter側・
  実装量大）。当面は⚠警告付きで残すのが「隠さない」方針に合う（断片は検索・コピーに使える）。
  監査は図領域外の崩れた表だけ数えるよう精緻化済み。

- **nonstd_bitdiagram（136）** — `bit_numbers`が弾く番号様の行の内訳を確認（2026-09-03）:
  bit>31（`96…65`等）58・繰り返し値（`11 11 11 11…`＝bit行でない）43・**昇順**
  （`0 1 2…15`＝列index等）18・横並び連結（`8 7 5 3 0 9 8 7`）17。**全て正しく非bit図**で
  見落としパターン無し。bit>31の58は64bit幅レジスタ等だが0..31前提の外で稀。対象外のまま。

### ⬜ 次に着手（調査済み・方針あり）

- **bit図のnarrow列 縦書き名の文字交錯**（mid-word-space 104・leading-lowercase 70・
  single-letter 24。先回りスキャンで発見・2026-09-03） — 狭い1-bit列で縦に書かれた
  フィールド名がpdfplumberで文字レベルに交錯（`Reser`上段は綺麗だが下段`ved`が
  `Rveesde r`にjumble＝FV2x.en p41）。`pmp3cfg`（先頭Cが落ちてる）・単独`M`等も。
  **bit図ダイアグラム専用の表示崩れで、同ページの説明表（Bit/Name/Access）には正しい
  名前があり、CSV（registers等）は説明表由来なので非影響**。正しい直し方: **説明表の
  (bit範囲→名前)を参照して図のフィールド名を上書き**する（図の列span→bit番号→説明表の
  行を引く）。export側で安全だが、説明表の隣接検出とbit範囲パースが要り中程度の実装量。
  ユーザーのCSV優先方針では後回し。着手時は「図名は常に説明表で置換」か「崩れた時だけ」かを
  決める（前者は一貫するが説明表パース失敗のリスク、後者は崩れ検出が要る）。

- **mid-page 57 / bottom-no-box 5** — 番号行が中央付近にあり近傍に箱が無い（図中埋め込み
  等）。cross-page対応後の残り。調査保留。

### ⛔ 撤退（理由つき）

- **bit図の名前を説明表で権威付け**（`ReserRveesde r`等の縦書き文字交錯104件）— 2026-09-03に
  実装→撤退。狙い: 図のフィールド名を、同レジスタの説明表（Bit/Name/…幅広で正しい）の
  (bit範囲→名前)で上書き。**撤退理由**: 図↔説明表の対応付けが信頼できない——(1)説明表が
  ページを跨ぐ（p41のtable-003はbit31-25だけ、残りは次ページ）、(2)1ページに複数レジスタが
  交錯し「図の直下の最寄り説明表」が別レジスタのものになる、(3)**単一bitフィールドは別
  レジスタの説明表と偶然bit範囲一致して誤置換する**（bit2がreg Aは`X`・reg Bは`Y`）。exact
  bit範囲一致に絞っても(3)が残り、正しい図を壊すリスクがある。**「崩しそうなら撤退」に従い
  全変更をrevert**（apply_bitfieldのnames引数・document_bitfieldsのnames引き当て等）。
  **再挑戦の条件**: reading_orderで「番号行→図→…→説明表」をレジスタ単位に区切り、図と説明表を
  レジスタIDで結ぶ（bit範囲でなく構造で対応づける）ようにできたとき。ページ跨ぎの説明表の
  結合（document_chains）も要る。境界重複修正（`EReserved`）は別物で有効なまま。

- **caption無しの複雑図の検出**（`long_line 17`・`table_issue`の可視73・図中下付きの一部・
  mid-page bit図の一部の**共通の根**） — 2026-09-03に撤退。I3Cタイミング図・比較器/DACの
  ブロック図・clock tree等がcaptionを持たず、回転・鏡像・重なりの文字/セルとして本文に
  散乱する（M030 p219の`esolc ot`＝`to close`の鏡像、H417 p338のI3Cバス図）。**図領域として
  検出できれば`<details>🖼`へ畳めて解決するが、caption・回転文字クラスタ(≥10)・大ラスタ画像の
  いずれも持たない**。ベクター描画の個数（密度）で図と判定する案は、普通の文章ページでも
  描画が数十個あり誤検出するため既に却下済み（D18初期）。散乱テキストを綴りの崩れで検出して
  畳む案も、本物の本文を誤って畳むリスクがある。**「崩しそうなら撤退」に従い見送り**、現状の
  ⚠警告＋各ページのPDFリンク（最後の砦）を緩和策とする。**再挑戦の条件**: caption無し図領域を
  誤検出なく囲える判定（例: 罫線・矢印・小円などdiagram固有の描画種の空間的まとまり）を
  作れたとき。それまでは監査で数を追うだけにする。
