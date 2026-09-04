# 人向けMarkdown QA巡回ログ（D18の100%詰め）

`check_markdown_parity`（PDF→bundle→Markdownの取りこぼし・順序ゼロ）を通ったうえで残る
**読みにくさ**を、`pipeline/review/audit_pages.py`で機械的に洗い出し、安価なサブエージェント
巡回と実地調査でつぶしていく作業の台帳。**やり方**: 安全に直せるものは直し、canonicalの
byte一致や既存の描画を崩しそうなら撤退し、その経緯をここに残す（消さない）。

判定はしない（原典の誤りは原典のまま）。canonical（凍結CSV）に触れる変更は`--full`の
frozen parityで検証し、driftが良性（説明文の改善のみ）であることを確かめてからにする。

## 原本の追加（コーパスの変化）

- **2026-09-04: CH32V407 の en 版 RM が mirror に追加**（`datasheet_en/CH32V407RM.PDF`・609ページ）。
  コーパスは **67→68文書**。取り込みは handoff の「原本にPDFが追加・更新されたとき」の手順どおり
  （convert_all 増分 → build_sources → `regenerate --full --verify --human`）。
  - 検証: **parity 68/68 clean**、凍結tool **6/6 byte一致**（canonical不変）、エラッタ NEW 0、
    cross_engine（pypdfium2 突合）で新文書も**取りこぼし0**（extra 27 は回転ラベル等）、
    check_tables/check_counts/check_docs 合格。図は 3,829 asset・図caption 3,023 の全部に実画像。
  - **効果**: `dma_requests` の V407 73行が reference → **confirmed**（zh/en 一致）。ただし
    en 版が DMA 周辺映射表の題を `Figure 11-2/11-3 … peripheral mapping table` と誤植していて
    （zh は `表11-2`/`表11-3`）、そのままでは両表が既定の DMA1 に落ちて対にならなかった——
    `build_dma_requests.CAPTION` に `图|Figure` を追加（図の題は既存の「mapping table」判定で弾く。
    全RM走査でこの綴りは V407 en の2件だけ・他familyの出力は byte 不変）。worklist **F-59**。
  - **副作用（記録のみ）**: `FSMC_NADV` の remap 格子を zh は `remap 1→PB7`、en は `remap 0→PB7` と
    読み、`remap_routes` 2行が落ちて `pin_functions` の PB7 6型番が confirmed → **conflict**。
    資料は両版とも同じことを言っており（表10-40 は FSMCEN=0/1 とも PB7）、en 版で表がページ跨ぎの
    見出し無し断片になるのを凍結 `build_all` が片方ずつ読んでいるのが原因。worklist **F-60**。

## PDF↔MD突合（新文書 CH32V407RM.en・2026-09-04）から直した3件

新しく入ったen版RMの、監査信号が付いた15ページをopusサブエージェントにPDFと突き合わせさせた。
**どれも1文書の話ではなく全文書に効く欠陥**だった（この切り口が最も収穫が大きい、の再確認）。

- **図として畳まれていた本物の罫線表**（229表・48文書）— ✅ 直した。`render_assets`の図領域は
  graphicsの縦クラスタで決まるが**罫線表の罫線もgraphics**なので、原本が表題を`Figure`と
  名乗ると表そのものが図領域になり、exporterが図領域内の表を平文へ潰していた。実例:
  V407RM.en p475 `Figure 26-19 Mode D FSMC_BCR1 bit field`（zh版は`表26-19`、同章の
  Mode 1/A/B/C は en でも`Table …`）——18行のbit域表が画像＋折りたたみの平文に。
  修正: 共有`logical_tables.looks_ruled`（行3以上・列2以上・非空6以上・2行以上が2セル以上）で
  **本物の罫線表なら折りたたみの中にHTML表として描く**。図のboxやラベル（4,917件）は平文のまま。
  parity 68/68 clean。※`Figure`と名乗る表題は原本の誤植なので綴りは直さない（表題は本文に残る）。
- **`=`を含むヘッダ断片に英単語が地続きで繋がる**（162セル・8文書）— ✅ 直した。
  `SPI3_RM=1`＋`Remapping`が`SPI3_RM=1Remapping`、`CAN1_RM=10Remapping`では**設定値10が
  読めない**。`cell_html`の識別子連結（`USAR`+`T1`=`USART1`）が、代入を書き切った断片にも
  効いていた。修正: 断片が`=`を含み、続きが独立した英単語（`[A-Z][a-z]{2,}`）なら`<br>`。
  `FSMCEN=1&USBHS2EN=1`＋`&RB_U…`のような式の続きは英単語でないので今までどおり連結。
  parity 68/68 clean。
- **bit図のフィールド名の末尾が二重になる**（44セル・6文書）— ✅ 直した。`HSYNCSCS`/`VSYNCSCS`/
  `COLKENLKEN`/`VBRR`/`TSCOO`/`WWDG_STOPTOP`/`TIM1_STOPP`/`Reservederved`/`BURST_ENDRST_END`/
  `PA1PA2_RMM`。**bundleのセルは`HSYNCS`と正しい**——`apply_bitfield`が縦割れ名を繋ぐとき、
  隣セルに二重取りされた末尾断片も足していた。結果、bit図と**直下の説明表が食い違う**。
  修正: 共有`logical_tables.fix_doubled_names`が、同ページの記述表の**Name列**を正解表として
  「末尾ブロックの二重を外すと名称列と一致する」ときだけ直す（`description_names`）。
  2点つまずいた: (1)判定を**描画後の形**で行う必要があった——`apply_bitfield`の連結は改行を
  残すことがあり（`HSYNCS⏎CS`）、`cell_html`が識別子として繋いで初めて`HSYNCSCS`になる。
  (2)証拠を**ページ跨ぎの結合表**からも集める必要があった——説明表が前ページから続いていると
  このページの断片にヘッダ行が無く名称列が見つからない（FV2x_V3xRM.en p622の`TIM1_STOP`等12件が
  これで直らず、`description_names(page, chains)`にした）。証拠は「このページに出ている表とその
  続き」に限る——文書全体から集めると`PB11`の正解として別章の`PB1`を拾う。
  結果: **残0**（44→0）、`PB11`169・`ODR11`18・`DMA2_CH11`8・`R16_BKP_DATAR11`4等の正当な
  数字末尾は件数まで不変、parity 68/68 clean。
  **`PB11`・`ODR11`・`DMA2_CH11`・`R16_BKP_DATAR11`のような正当な数字末尾は名称列に在るので
  触らない**——重複ブロックに英字を要求し、名称列の裏付けを必須にしたのはこのため
  （素朴な「末尾重複」規則だけだと508件当たり、その大半が正当な名前だった）。

**続けて、この突合が示した「読み順から外れた行」を追った**（2026-09-04）:

- **変換器が`reading_order`から外し、表のセルにも入らなかった行を拾い直す**（1,110行・57文書）
  — ✅ 直した。converterは表領域に重なる行を`reading_order`から外す（セルが同じ文字を持つ、
  という前提）。ところが図（クロックツリー・メモリマップ・プロトコル図）のラベルは「図をtableと
  誤検出した箱」の**外側**に落ちることがあり、セルにも読み順にも無い——exporterもparityも
  reading_orderだけを歩くので**黙って消えていた**（`USBHS OSC32_OUT`・`PLLXTPRE USBCLK`・
  `ADC_IN15 DMA`・`1HCLK external memory`）。図は画像で見えるが、この文書の方針は「図から読めた
  文字も検索・コピーのために残す」なので拾う。修正: 共有`logical_tables.recovered_lines`＋
  `reading_stream`が、**語（2文字以上）が1つも他所に無い行だけ**を縦位置で読み順へ差し込み、
  exporterとparityが同じ流れを歩く（図領域内なら`<details>`の中に入る）。
  **parityの盲点をひとつ塞いだ**——「reading_orderに無い行」は今後も検査対象外だが、
  拾った行は同じ位置で検査される。
- **skipした行（bit番号行・吸収したフィールド行）の欠落: 0件**（14,694行を検査）— 🔎 確認だけ。
  同じ盲点を疑って全文書で数えたが、skip行の中身は全て出力に在った（表題の続き行はすでに
  専用検査あり）。
- **⛔撤退: 部分的にセルへ入っている行の見出しだけの欠落**（7,139行・64文書）。`RDes2 Buffer 1
  address, timestamp low`のように**行頭の語（枠の外の行見出し）だけ**が消えるもの。行ごと出すと
  `Buffer 1 address…`が表のセルと二重になり（メモリマップ図では`0xFFFF FFFFF 0x4001 0800`の
  ように大半が重複）、消えた語だけを出すのは原文に無い行を作ることになる。**表の外にある
  テキストを行/列見出しとして表構造へ取り込む**のが本筋なので、それができるまで記録に留める。
  再挑戦の条件: 表の外の行見出しを`row_header`として持てるようにL1を拡張したとき。

- **表の箱の中にある見出しを段落へ落とす**（243行・16文書）— ✅ 直した。DMA映射表の
  `SPI1 SPI1_RX SPI1_TX`・`Peripheral Channel 1 …`のように、表の中身が太字/大フォントで
  組まれているとconverterがheadingにする。文書の見出しが表の中に在ることはないので、
  `demoted_heading_lines`に「中心が表のbbox内なら段落」を追加（番号/章見出しは除外）。
  `#`が本文の目次を壊していた。**図領域内のラベルは以前から段落**として出ていたので、
  残っていたのは「図が画像化されなかったページ」——PDF↔MD突合が指摘した`# RSTACT (I3C
  broadcast CCC`（V407RM.en p309）がその口。結果: 残0、corpus全体のH1は1,452行、
  parity 68/68 clean（roleはparityの検査対象外なので本文の文字は不変）。
- **縦割れ名の断片が別の行としても出る「幽霊行」を落とす**（64行・26文書）— ✅ 直した。
  重なった結合セルの副産物で、`BU⏎RS⏎T_E⏎ND`（=BURST_END）を持つ縦長セルの下に`RS`・`T_E`・
  `ND`だけの1セル行が並ぶ（H417RM.en p226/p461/p976/p988ほか）。縦長セルが全文を持っているので
  断片行は二重表示。共有`logical_tables.drop_phantom_fragment_rows`が**同じ列で、その行を覆う
  行span2以上のセルの物理行と完全一致する**セルだけ落とす。緩い部分一致で測ると754行当たり、
  その大半は比較表の正当な値（`2*DAC`が別の行の値として在る等）だった——**完全一致＋同一列＋
  被覆**の3条件で64行に絞り込んだのが判断の分かれ目。
- **重なりセルの残骸だけの1列表を描かない**（559表・41文書）— ✅ 直した。
  `<table><tr><th>AL</th></tr><tr><td>LA</td></tr></table>`（V407RM.en p340の`STALLA`の破片）、
  `USART1_RM1=0(2)`＋`Default Mapping`（FV2x_V3xRM.en p138）、`signal`＋`level`。共有
  `logical_tables.fragment_tables`が、1列・2行以下で**すべてのセルの文字が、面積の6割以上を
  重ねる別の表のセルの物理行と完全一致**するものだけを対象にする——中身は必ずその表に出るので
  文字は失われない。箱の重なりを条件にしなかった版では`Reserved`だけの表が848件当たり、
  「同ページのどこかに同じ語がある」だけで消してしまう危険があった。
  結果: 出力に残る極小1列表は10件（正当なもの）、parity 68/68 clean。
  **落とした文字が本当に残っているかを機械的に確認**（parityは落としたセル・表を検査しないので、
  この2件の変換には専用の検算を対にした）: 落とした1,178セルすべてについて`cell_html`の綴りが
  出力に在ることを照合し、**欠落0**。最初は同一ページだけを探して17件が「無い」と出たが、
  全て**ページ跨ぎ結合表の継続断片**（そのページは「Table continued — rendered in full at
  page N」で、中身は開始ページに在る）で、chainの開始ページも探すと0件になった——検算の側の
  誤りだった。
- **⛔保留: セル内で下付きが行末へ飛ぶ**（5,761セル・63文書の疑い。`t = STALL × t SCLL_STALL
  HCLK`）。converter側の`merge_subscript_lines`は行しか見ないので届かない（既に撤退済み）。
  export側だけで直す道はあるが、**セル内の物理行ごとにgeometryのフォントサイズを見て、
  複数の基底へx座標で下付きを割り当てる**必要があり（1行に`t_SCLL_STALL`と`t_HCLK`の2つが
  混在する）、素朴な正規表現では正当な2行セルを壊す。再挑戦の条件: bit図の`bit_number_centers`
  と同じやり方でセル内geometryを扱う部品を作ったとき。

## 2巡目の意味検証（PDF↔MD突合・2026-09-04）と、そこで直した/絞ったもの

今日入れた5つのexport変換を、**別々のモデル・別々の文書**で突き合わせさせた（プロジェクトの規則
「export側の変換には意味検証を対にする」の実施）。zh版RM＝sonnet、en版RM＝opus。

**確認できたもの**（両方がCORRECT判定）: 幽霊行の削除、断片だけの1列表、bit図名の修復、
図領域内の罫線表（en版で6表を値まで照合）。en版はさらに「落とした543表のすべての語が同じ
Markdownページに残っている」ことを機械的に確かめており、**文字の欠落0**を独立に裏づけた。

**指摘を受けて絞った/直したもの**:

- **拾い直す行は「描画済みの図の領域の中」だけに限定**（1,110行→288行）。図の外で拾った分は
  「bit図の破片が本文へ重複して出る」（`INTENINTENINTENINTEN`・`A15 A14 A13`＝`STA15`等の
  再切り出し・表の行をそのまま重ねた`B1[7:0] R0[7:0] …`）で、`# TDes0`のように**本文の見出し**に
  なる例もあった。判定は突合と完全に一致した——**OKと言われた2ページは全行が図の中、WRONGと
  言われた4ページは図の中0行**。図の中なら`<details>🖼 Text parsed from the figure above`に入り
  「図から読めた文字」として意味が通る。
- **図領域内の罫線表の判定を厳しく**（229表→108表）。図のラベル格子（タイミング図の`CH0 CH1 …`・
  波形の数字列・流れ図の枠）が罫線表として描かれ、空セルばかりの格子になっていた。追加条件は
  **埋まり6割以上・1行目が全部埋まっている・1文字セルが6割未満・同じ語が2回並ぶセルを含まない**。
  結果、突合がWRONGと言った p594/p711/p712/p807/p207/p208 は全て除外され、CORRECTと言った
  p275/p912/p837/p912 と V407RM.en p475 は残った（残る誤判定は p979 の`Laye FI`型1件）。
- **表の枠の外にある短い識別子の見出しを段落へ**（27行・13文書）。`# TDes0`・`# SRAM`・`# CK`が
  表の途中でH1になり目次を壊していた。表の縦帯に入り、横は枠の外・60pt以内にある短い識別子を
  段落にする（文字は残す）。
- **bit図の名前修復を「末尾の二重」から「Name列が部分列」へ一般化**。en版の突合が
  **1文書で107件**の破損を洗い出した——`ATACAMTADCMD`＝`ATACMD`・`CTBXBEF`＝`CTXBEF`・
  `RCRONTT`＝`RCONT`・`DBCDKEBNCKDEN`＝`DBCKEND`・`Reser Cved`＝`Reserved`のように、縦割れの
  断片が**交錯して混ざる**壊れ方は末尾重複の規則では届かない。正しい名前は記述表のName列に在り、
  **その文字が順番どおり含まれる**という関係が成り立つので、候補が1つに決まるときだけ差し替える
  （長さは名前の2倍+2までに制限し、`Reserved bits must be 0`のような説明文を名前へ潰さない）。
  単体試験14件（修復7・保持7）。**ここで一度踏み外して戻した**——部分列の条件だけでは
  `INTEN12`→`INTEN`・`PENDSTA15`→`PENDSTA`・`HSICAL[7:0]`→`HSICAL`のように、**Name列が索引や
  bit範囲を書かないだけで図が正しい**セルを短縮してしまい、監査で905件（全1,774件の半分）が
  該当した。歯止め: **落ちる文字が全て採用する名前自身に在ること**（`_only_duplicate_glyphs`）
  ——交錯した重複は名前のグリフが二度出る形なので落ちるのは名前の文字だけ、索引の`1`/`2`や
  `[7:0]`は名前に無いので弾ける。結果 **943件・20文書を修復し、危険な短縮0**、parity 68/68 clean。
  この歯止めで`Reser Cved`→`Reserved`（別セルの`C`が混入した例）のような**異物混入型は保守的に
  見送る**ことになったが、索引を失うより良いと判断した。
- **断片だけの1列表を3行まで**に拡張（559表→739表）。`MA`/`XC`/`H`（=`EXMAXCH`）のような3行の
  残骸が30表残っていた（en版突合の指摘）。中身が本体表に在ることは変わらず条件。

**まだ直していない（記録）**: p979の`Laye FI`型の誤判定1件、p594の`32-bit filter`/`16-bit filter`の
枠ラベル欠落、p807の`SPI FLASH2`欠落、p711/p712の`SDIO_CMD`/`SDIO_D`行見出し欠落——いずれも
**表の外の行/列見出しを表構造へ取り込む**という同じ根（下の⛔撤退と同じ）。p461の一部bitのreset値が
空・p226の`Description`列見出し欠落は今日の変換とは無関係の既存の穴として別項に立てる。

**未着手として記録**（同じ突合が出した、まだ直していないもの）:

- **枠の外に描かれた行/列の見出しが落ちる**（V407RM.en p529 Table 29-9の`RDes0`〜`RDes3`。
  `RDes1`だけが表の後ろに孤立し、どの語がどの記述子かが読めない）。Ethernet/USB/DMA章の
  記述子・メモリマップ表に同じ形がある。表の外にあるテキストを行見出しとして取り込む話で、
  表構造の再構成が要る。
- **図が画像化されず表抽出に流れるページ**（p307・p309のI3Cプロトコル図。`assets/`に画像が無く、
  隣接boxのグリフが交錯した長い塊になる。p309では図中の注記が`# `見出しに昇格して文書の
  アウトラインを壊す）。図のクラスタ判定が効かないページの扱いで、⛔撤退中の「caption無し図」と
  同根。
- **セル内の下付きが行末へ飛ぶ**（`t = STALL × t SCLL_STALL HCLK`。本文行では正しく統合される）。
  タイミング表全般に効く。converter側の`merge_subscript_lines`が表セルを見ないため。
- 原本の誤植（記録のみ）: p528 表29-8のbit18が`20`（zh版も同じ）、p504のAccess列`R0`/`RO`混在、
  p309 `(RSTACT, 0x2A) )`の閉じ括弧重複。

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
- **層化巡回3本（sonnet・cross/bitfield/caption各12±ページ、2026-09-03）** — 中国語=正当・
  原典誤植=対象外を明示。成果: (1)通常表の境界二重取りを多数発見→strip_boundary_dupesで
  1,902文字修正、(2)caption二重描画fixを別レーンが「across sample solid」と検証、(3)既知の
  未解決を再確認（bit図フィールド名の**文字交錯** `SMBALERT→SMBSAMLEBARLTE`/`ENDUAL→ENDUENADL U`
  ＝下記⛔撤退の再確認、bit図内境界bleed＝上記保留）。新規で記録した2件: **FV2x_V3xRM p166
  「Table 11-2 DMA2 request mapping」がtable抽出に失敗し見出し＋バラけた本文に**（表番号11-2が
  直後の別表と衝突）＝抽出失敗系で複雑・保留。**V205RM.zh p110のbit図ヘッダ`D5 D4 D4 D2`**
  （D3欠落・D4重複）＝near衝突でD3がdedup後勝ちに上書きされた残り（cross/図の中心数<列数系）。
  bit-range微修正（`[31:29]`→`[30:29]`, `WAVE2[2:0]`→`[1:0]`）は説明表権威付け＝⛔撤退のため対象外。

- **ランダム探索巡回（sonnet・16ページ、2026-09-03）** — 層化とは別パターン。孤立した
  converterアーティファクト3件を記録（いずれも単発・表示のみ・canonicalはEVT基準で無関係）:
  (1)`0x000000000`（X315RM.zh p183・R32_TIM3_CH1CVRのreset値。0が9個、隣行TIM2は8個）＝
  register一覧表セルのglyph重複だが**空白区切りが無い**ためstrip_boundary_dupes対象外、単発。
  (2)`0次`（V205RM.zh p224・I2C reset値に説明文末の`次`が混入）＝bit図/interleave系。
  (3)H417RM.en p224のburst転送タイミング図が画像/`<details>🖼`無しでラベルがバラけて本文に
  （caption無し図＝⛔撤退中の既知の根）。無空白の単発glyph重複を安全に直すにはgeometry判定が要り
  費用対効果薄のため記録に留める。

- **PDF原本↔Markdown直接突合（opus・10ページ×2本、2026-09-03）** — **最も収穫の大きい切り口**。
  サブエージェントにPDFページをReadさせ（`pages=`指定）、生成Markdownと突き合わせる。markdownだけ
  を見る巡回では見えない「原本にあるのに無い/違う」を拾う。成果: (1)**CSVに効く**下付き移動
  （`R_S<70kΩ`→`R <70kΩ S`、operating_conditions 19行）、(2)**図が丸ごと白紙**（11枚、下記）、
  (3)zh reset値へのCJK汚染622セル、(4)図ラベルの全グリフ二重化（`OOSSCC__IINN`）、(5)結合表の
  rowspanが継続行に届かない（保留）。加えて**register意味監査**（bit範囲の連続性・行のセル数・
  Access/Reset値の妥当性・図↔表の名前一致）が「Reset value」ヘッダ折り返し由来の3系統
  （文字降下127セル・偽`value`行104ページ・列ごと排出）を精密に切り出した。

### ✅ 完了（続き）

- **図が白紙で出力される**（M030RM p103 図9-1のブロック図＋Noteが丸ごと消失。全corpus 5-11枚。
  PDF↔MD突合が発見）— render_assets（2026-09-03）。暗号化PDFの埋め込みraster（DCTDecode JPEG、
  およびFlateDecodeのIndexedパレット生サンプル）をpdfiumが描けず、150dpiの切り出しが真っ白に。
  修正: 描いたPNGの暗い画素が0.05%未満なら白紙とみて、領域内の埋め込み画像をpdfminerの
  `stream.get_data()`（復号済み）で取り、JPEGはPILで、Indexedは`srcsize`×1byte indexに
  colorspaceのlookupを当てて復元し、座標を150dpiに合わせて貼る。単体テスト: M030RM p16
  978B白紙→18KB、V103DS0 p38→594×457、WCH-Link p11→653×148。M030RM.en/.zhは再描画済み、
  V103DS0.en/WCH-Link.zhはparity確認後に再描画。canonical無関係。

- **bit図セルの境界重複＋折り返し**（`EReserved`/`URese rved`）— export側apply_bitfield
  （2026-09-03、ユーザー報告）。セル境界に載った1文字がpdfplumberで**隣のセルにも二重
  取り**され、`LP_REG`の`E`が右隣に入り`E\nReserved`→`EReserved`（X035RM p11）、`USART`の
  `U`が左隣に入り`U\nRese\nrved`→`URese rved`（X035RM p19。`Rese`+`rved`はcell_htmlが英単語と
  みて空白挿入）。geometryのcharに`E`/`U`は無く重複と確定。修正: データセルを列順に見て、
  先頭「1文字＋改行」がその文字が**左隣末尾2文字か右隣先頭2文字**に重複するなら落とし、残りの
  折り返し行は空白なしで繋ぐ（bit名は識別子）。全67本parity 0・`Port E Reserved`等の正当な
  文は誤検出せず。**表セルの中身がCSVに効く可能性**があるが、これはbit図ダイアグラム専用で
  凍結canonical（説明表由来）には非依存。

- **cross-page bit図のグリッド衝突→parity退行**（H417RM.en p620ほか）— apply_bitfield
  （2026-09-03）。番号中心が実列数より少ないページ跨ぎ図（例: 27..16の**12中心**に16列の
  `FBM`フィールドと番号行を詰める）で、`bit_span`のnearフォールバックが複数セルを端の1列へ
  束ね、**同じ(row,column)に複数セルが落ちる**。`table_html`のgridは`grid[r][c]=…`で後勝ちに
  上書きし可視は12セルだが、**parityはrecordの全16セルを読む**ため、はみ出た4つの`FBM`が
  後方の`FBMx`（説明表）へ食い込んで「順序外」——H417で146件のparity失敗。以前は縦連結
  （has_span導入前）が`FBM`+番号を1セルに畳んで衝突を偶然隠していた（`FBM15`等の誤ラベルだが
  parity的には一意で通過）。**根治**: apply_bitfield最後で`(row_start,column_start)`衝突セルを
  gridと同じ後勝ちで1つに畳み、**描画とparityが必ず同じセル列を見る**ことを保証。has_span
  ガード（L103のPRIO誤連結対策）には非依存で両立、全67本parity 0復帰。※図そのものの再構成は
  ページ跨ぎで中心数<列数のとき依然不完全（別項の調査保留）だが、少なくとも整合は保証。

- **箇条書きの二重bullet**（`- - Dual-core…`。プログラム走査で発見）— export側
  strip_leading_bullet（2026-09-03）。原本のlist-item行が既に`- `始まりで、exporterが更に
  `- `を足して`- - `に。**全corpusで1,224件/121ページ**。修正: 行頭の`bullet+空白`（`- `/`● `等）を
  落としてから`- `を足す。**`-0.5`/`-40℃`等のマイナス符号（空白が続かない）は剥がさない**（値を
  壊さないため`bullet+空白`限定）。export/parity共有関数で処理。全67本parity 0・二重bullet 0。

- **セル境界を跨いだグリフの二重取り（通常表・結合表・bit図を統一）**（zhのreset値`0对`/`，\n0`/
  `0通<br>，`622セル超・`Reserved L`・`BIDI\nC\nOE`・`e 0`。PDF↔MD突合とregister意味監査が発見）—
  logical_tables.strip_straddling_dupes 全面改修（2026-09-03）。判定を「グリフ中心がセル外＋改行
  分離」から次の3段へ: (1)**値セル前処理**（短いASCII値の端の非ASCII文字は、隣セルの**行端**に
  同じ文字があれば落とす——全角文字のグリフ箱は広く面積では決まらない）、(2)`own`＝**面積の半分
  以上がセル内**のグリフの綴り（中心判定は端の実グリフを漏らし`Reserved`→`eserved`を生んだ）、
  (3)余剰の**具体的なグリフ**が自セルに半分未満・別セルに半分以上入り・そのセルの行端に同じ文字が
  あるときだけ落とす。さらに2つの過剰除去を単体テストで潰した: 相手が1文字だけの人工セルなら
  除去しない（`PB14`の`4`が幅17ptからあふれ、隣は`4`のみ）、**自セルで語に融合・相手で空白分離
  なら融合側が本物**（`INTEN1`｜`1 INTE`）。さらに値セル前処理で**datasheet製品比較表の単位/助数詞
  （`8路`・`105℃`・`2组`）を落とす過剰除去**を除去サンプルの目視で発見——同列の兄弟セルが皆`…路`
  で終わるため「隣の行端に同じ文字」が単位でも満たされる。真のbleedは値と別行/空白で切れ
  （`0\n对`・`，\n0`・`00b 次`）、単位は値と地続きなので、**地続きなら本物**として触らない。
  加えて、説明文の行末句読点が**単独で隣の空セルに降りた**もの（reset列が`。`だけ。V003RM.zh p16
  の名称空行）は、隣の行端に同じ文字があれば空にする（全corpus 136セル、全てzhの`、，；。`）。
  ページ跨ぎ結合表は`merge_cells`がセルに`src_bbox`と
  `page`を持たせ、export/parityが**ページ番号でgeometryを引く関数**を渡す（結合セルにbboxが
  無くて素通りしていた——zh説明表はほぼ結合表）。geometryは候補セル（`has_edge_newline`／
  `has_short_edge`）があるページだけ遅延ロード（export 1m26→約4m）。**単体テスト14/14**
  （除去: `Reserved L`/`BIDI\nC\nOE`/`Reserve\nd\nR`/`，\n0`/`0\n；`/`15:0]`←隣`ddr[1`と両取り/
  `TIM7 T`/`Reserved C`、保持: `INTEN1`/`Reserved`/`CC1P`/`PB14`/`R 22`/`DATAL`）。**全corpusで
  2,823グリフ除去**（bit図668・通常表683・結合表1,472、うち値セルのCJK端1,758。単位融合ガード前は
  3,602で、差の約780が`8路`型の誤除去だった）・ヘッダ畳み278。
  全67本parity 0。**過剰除去のサブエージェント検証（sonnet・除去上位14ページ/58表）: 実文字の損失
  ゼロ**（zh USBHS一覧の`0x0`→`0x`はbit定義`[16:0]=X`＝8桁と整合し正しい除去と裏取り）。未除去の
  残り3件（`HTIF4 T`、`0 x`/`00b x`＝説明文中`CH32V31x`の`x`で行端でない）は幾何が半々の端例。

- **表題の折り返し2行目が別の段落に**（`<caption>…SRAM (RISC-V5F</caption>`の後に`+ RISC-V3F)`が
  本文段落として漏れる。H417DS0.en p99等、括弧未閉じの表題11件＋接続詞終わり）— 共有
  `logical_tables.caption_full`（2026-09-03）。bundleの`caption.text`は1行目だけ。**括弧が閉じて
  いない／接続詞・前置詞・読点で終わる**間、後続のparagraph行を最大3行繋いで全文とし、
  exporterは`<caption>`に全文を出して続き行を`plan["skip"]`で本文から消す（parityも同じskip）。
  同じ全文をoperating_conditionsの抽出器（`caption_context`）も使う——CSVの条件prefixが
  `…(RISC-`で切れていた原因の半分がこれ（下記CSV項参照）。
  - **落とし穴（2026-09-04、自前の検証で発見）**: 全文は`bitfield_plan`が**ページ表dict**に付けるが、
    ページ跨ぎの結合表は`record = info["merged"]`の別dictなので載らず、**続き行はskipで本文から消えた
    うえ表題も1行目だけ**——`+ RISC-V3F)`が文書から消えていた（まさにH417DS0.en p99）。parityは
    skip行を見ないので**67/67 cleanのまま検出できず**（parityの盲点、記憶済み）。修正: render_pageで
    結合recordへ`_caption_full`を載せ替え＋**parityに「続き行のテキストが`<caption>`の中に在ること」
    の存在検査**を追加（`plan["caption_cont"]`。順序は問わない）。
  - **誤連結1件を撤退的にガード**: V407RM.zh p106 `表10-4 串行外设接口（（SPI1/2/3）模块`は原本の
    `（（`重複で括弧が永久に閉じず、後続の**表10-5〜10-7の表題3行を飲み込んだ**。`_looks_like_caption`
    （`Table`/`Figure`/`表`/`图`＋数字で始まる行）で止める。連結26→25件（他25件は不変）。
  - 結果: 連結25件（括弧11・接続詞/読点14。14文書）、corpusの不対応`<caption>` 6→1（残1はその`（（`＝
    資料側）。**PDF直接突合サブエージェント（opus）: 25件全てEXACT**（過剰連結0・不足0。どの続き行の
    直後も表のヘッダ行で、3行上限に達した例も無し）。指摘2点: (A) CJKの折り返し（H417RM.zh p795
    `…数据值），`＋`基于某些IOSR值…`）で区切りのASCII空白が1文字余分——両側CJK/全角なら区切り無しに
    修正（`_cjk`）。(B) `SRAM (VDD= 3.3V)`の空白位置（V003DS0.en p19/20）はconverterの下付き統合
    （`V`＋`DD`）由来で連結とは無関係——既知の下付き課題として残置。

- **空スロットの`<td>`省略で列がずれる**（FV2x_V3xRM.zh p63 CRC一覧: 継続ページで名称列を
  pdfplumberが取り漏らし、`0x40023004`が名称列に見えた。PDF↔MD突合/register監査が発見）—
  table_html（2026-09-03）。gridのNoneを「span被覆」と「本当に空」で区別せず両方とも省略して
  いたため、後続セルが左へ詰まっていた。**結合表650件**（61本）に幅へ届かない行があった。修正:
  スロット単位の被覆行列を持ち、**中身のある行**の被覆されていない空スロットだけ`<td></td>`
  （row 0は`<th></th>`）で埋める（全行空の行は従来どおり空`<tr>`）。parityはtext無しのtdを
  見ないので不変。※取り漏らした名称そのもの（`R8_CRC_IDATAR`）はbundle段階で表外の行に
  なっており未回収（converter側の表領域検出、保留）。

- **章題の折り返し2行目が別見出し**（`# Chapter 20 …Transceiver`＋`# (SerDes)`。#6）— export側
  title_continuations（2026-09-03）。**章見出し（第N章/Chapter N）の直後・同フォントサイズ・
  40字以下・番号/章見出しでも図表captionでもない・文末句読点で終わらない**行を1行目へ空白で
  繋ぎ、本文から消す。全corpus実測: 該当5件（`Transmitter (USART)`×3・`(SerDes)`・
  `(USBFS/OTG_FS)`）は全て題の折り返し、番号見出し直後の`图22-3 …`caption等23件は条件で除外。
  parityは1行目→2行目のtextを順に探すので繋いだ1行で通る。

- **`Reset value`ヘッダの折り返しが偽データ行に**（`<th>Reset</th></tr><tr><td>value</td>`。
  全corpus 104ページ。register意味監査が発見）— logical_tables.fold_header_wrap（2026-09-03）。
  row 1に中身が**ちょうど1つ**・短い小文字1語・同列のrow 0が短いヘッダなら、ヘッダへ繋いで
  行を詰める（export/parity共有）。**⚠ 踏んだ穴**: 行を繰り上げた際に`fold_boundary_spills`が
  記録した`_folded_rows`（table_htmlが落とす継続行の番号）と`row_pages`を繰り上げ忘れ、
  **1つ下の実データ行（V003RM.en p17 PLLON行）を捨てた**。parityはセルを個別にexpectするので
  「missing」で気づけたが、列ずれ等は原理的に見えない（[[parity-blind-spots]]をmemoryに記録）。
  行数を変える変換では行番号を持つ付帯情報を必ず一緒に更新する。約280表を畳んで全67本parity 0。

- **図ラベルの全グリフ二重化**（`OOSSCC__IINN`→`OSC_IN`、`CCPPOOLL==00`→`CPOL=0`。PDF↔MD突合が
  発見）— pua_normalize内`_undouble`（2026-09-03）。太字風の重ね描きをpdfplumberが2回拾う。
  空白なし・6字以上・偶数長・全隣接ペア同一・**hex桁以外を含む**（`0000FF`のような16進値を
  除外）行を畳む。全corpus 143件（本文108・セル35）。export/parity共有。

- **段落・傍注・ピンラベルが見出しに化ける**（Overview本文が複数H1・`注：`が5つのH1・ピン名が
  97個のH1。収束巡回とプログラム走査が発見）— export側 demoted_heading_lines（2026-09-03）。
  converterの見出し判定は「短い(≤120字)＋本文中央値の1.25倍フォント」でheading化するため、
  **やや大きいフォントで組まれた本文・傍注・pinout・mode説明が丸ごと見出しに化ける**（全corpusで
  フォントサイズ由来headingが3つ以上連続するrun=359/272ページ）。**export側だけで降格**できる——
  parityは`#`接頭辞を見ず本文textだけ照合するので、heading↔paragraphの切替に非依存（reconvert不要）。
  降格条件（番号見出し`20.1`・章見出し`第N章`/`Chapter N`は本物なので除外）: (1)フォントサイズ由来
  headingが**3つ以上連続**するrun、(2)runに**注記マーカー**（`注：`/`Note:`/`说明：`等）を含む、
  (3)**50字超**の見出し（本物の節見出しは短い。実測: >50字の非caption見出し645件は全て文/傍注）、
  (4)**CJK文末/節句読点（。，；：、）で終わる**行（節見出しはこれで終わらない。ページ跨ぎ断片
  `除BTF位。`・本文`…実現交互。`。実測536件は全て段落）。図caption（`Figure N-M …`）はcaption_matchが
  先に描くので無影響。**全corpusで2,390見出し行/332ページ**を
  段落へ復帰（連続H1のあるページ 272→52＝残は正当な連番節）・全67本parity 0。**残（#6）**: 章題の
  折り返し（`# Chapter 20 …`＋`# (SerDes)`）はマーカー無し・2行なので据え置き（題の一部か別物か曖昧）。

- **空table・図領域の偽table**（`<details>🖼`内に罫線boxが割り込む。図ブロック巡回が発見）—
  export側render_page（2026-09-03）。converterが**図のbox/ラベルを罫線ありtableと誤抽出**する。
  (1)**全セル空のtable 1,115件/455ページ**——空セルのcell_htmlは""でparityのexpectがno-opなので、
  caption無し・非bitfield/crossの空tableをexportでskip（parity整合維持）。(2)**図領域内（in_figure）の
  非空table 3,758件/1,255ページ**——枠付きboxが図テキストへ割り込むので、セルの中身を**プレーン
  テキスト**で出す（`Text parsed from the figure`の趣旨に沿う）。transformは適用済みでparityは同じ
  変換後セルを同順で読むため整合。結果: X315RM.zh p124が16個のboxから綺麗な図テキスト
  （`1st 3rd 5th 7th`/`Sample`/`ADC1`…）へ。全67本parity 0・`<details>`内のtable 0。canonical無関係。

- **cell_htmlのenum誤連結**（`…AVDD10: …AVDDOther:`。表構造巡回が発見）— export側cell_html
  （2026-09-03）。セル内の物理改行を「折り返し（連結）か項目改行（`<br>`）か」で出し分ける際、
  「前行末＝英大文字/数字 かつ 次行頭＝英大文字/数字」を識別子の折り返し（`USAR`+`T1`=`USART1`）と
  みて地続きに連結していた。だがenumオプション行（`10: Calibration voltage 3/4 AVDD`、前行末`D`＋
  次行頭`1`）も連結され`AVDD10`に。修正: **識別子の継続断片は空白を含まない1トークン**なので、
  `次行に空白を含むなら折り返しでなく項目改行`として`<br>`。**全corpusで2,611セル**が変化（分類:
  enum/ラベル・図ラベル・`TIM1_RM=00`/`Default Mapping`のenum対が大半で全て改善、旧の誤連結より悪化
  するケースは無し）。識別子折り返し（`USART`+`1RST`）は連結維持。全67本parity 0。

- **重複見出しのghost**（`# Feature`が2回。プログラム走査で発見）— export側（2026-09-03）。
  2列見出し検出が**高さ0の退化bbox**を持つ重複heading行を生む。**全corpusで退化行はちょうど28件・
  全て高さ0・全てrole=heading・全て直前の重複**（Feature/Features/功能概述等、datasheet先頭）と確定。
  修正: `bbox高さ<0.5`の行をexport/parity両方でskip。全67本parity 0・連続重複見出し 0。

- **表captionの二重描画**（`Table 4-1 … list`が表の上と表内で2回。X035RM p23、ユーザー報告）—
  bitfield_plan（2026-09-03）。表の`caption.line_id`が`<caption>`として描かれるのに、同じ行が
  reading_orderにも残り本文段落としても出ていた。**コーパス全体で4225件・63本**が該当（全table
  captionが重複）。修正: caption行を`plan["skip"]`（export/parity共有）へ入れて本文から消す。
  継続テーブルが自ページにcaption行を持つ危険ケースは全corpus走査で**0件**と確認。全67本
  parity 0維持。

- **通常表の境界グリフ二重取り**（`[31:12] R`・`RO R`・`RW A`・`s Description`・reset値の
  `。 0`等。サブエージェント巡回が多数報告）— logical_tables.strip_boundary_dupes
  （2026-09-03）。セル境界に跨るグリフをpdfplumberが**左右両セルへ二重に割当**。geometry実測で
  確定（H417RM p218-005の`[31:12] R`の`R`はx0=112.8/x1=119.9の**1グリフ**が境界113.5を跨ぎ、
  右隣`Reserved`の先頭Rが左セル末尾へ重複）。`register_fields.csv`等のcanonicalは**EVTヘッダ
  基準**なので無関係（bleedは人向けmarkdownの可読性のみ）。修正: 行内で列順に見て、`空白+1文字`の
  末尾がその文字＝右隣の先頭文字／`1文字+空白`の先頭が左隣の末尾文字なら落とす。**短いセル
  （本文≤14字）限定**で長い説明文を守る。誤検出をgeometryで実測: **末尾0/60・先頭は既に文字
  交錯で崩れた図セルのみ**（無害）。export/parity共有ヘルパー・通常表のみ適用（bitfield/crossは
  apply_bitfield側）。**全corpusで1,902文字/1,059表を除去**・全67本parity 0維持。
  bitfield**図内**のbleed（`ReservedR`・`Reserved\nT`等、空白区切りが無く隣接テキストとも
  一致しない版）は下記 strip_straddling_dupes（geometry版）で別途対応。

- **bit図内の境界グリフ二重取り（geometry straddling判定・改行分離のみ）**（`ReservedR`→
  `Reserved`・`Reserved\nT`→`Reserved`。サブエージェント巡回報告）— logical_tables.strip_straddling_dupes
  （2026-09-03）。図セルの端の重複が**テキスト隣接セルの境界文字と一致しない**（別の行/列から
  跨いだグリフ）ためstrip_boundary_dupesでは捕まらない。geometryで確定: CH32xRM.en p29の
  `Reserve\nd\nR`の末尾`R`はグリフ中心100.9で**セル右端99.1の外**（右隣列に属す）。手法: 各セルに
  中心が入るグリフを綴り直し、cell textがそれより端に1-2文字だけ多いぶんを重複とみて落とす。
  bitfield_planで番号中心を得た**pairの図テーブルにだけ**適用（export・parity検査が同じ生セルへ）。
  **⚠ 一度崩して撤退→厳格化して再導入した経緯**: 初版（空白/改行問わず端の余剰を落とす）は
  **全corpus 651グリフ/481図**を除去したが、**strip検証サブエージェントが過剰除去を3件検出**——
  `SWIER22`→`SWIE22`（`SWIE`+`R 22`の`R`）・`USART6RST`→`SART6RST`・`RGUFS`→`RGUF`。原因: **狭い列で
  名前がセル幅を超えてあふれると実文字の中心もセル外**に落ち、dup（隣から跨いだ）と区別がつかない。
  parityはexport=bundle変換で一貫するため**検出できない**（サブエージェント検証の価値）。**厳格化**:
  余剰の端文字が残りと**改行で隔てられているときだけ**落とす（`Reserve\nd\nR`の`R`は別視覚行＝真dup、
  `R 22`の`R`は同行のあふれ実文字＝保持）。ユニットテスト（ReservedR除去・`R 22`/`USART`保持）合格・
  **厳格版で132グリフ/117図**を除去・全67本parity 0・**再検証サブエージェントで過剰除去0**（約42図/14ページ）。
  canonicalはEVTヘッダ基準で無関係。**残り（別の既知問題として記録）**: (1)apply_bitfieldの**既存**leading
  strip（`text[1] in " \n"`で空白も許容）は`R 20`→`20`のように**あふれ実文字を落とす**が、これは
  vertical-interleaveで既に崩れた図セル（`SWIE SR23`等）に限られ、strip無効化しても同一＝当該fix由来でない。
  \n限定に絞ると`E Reserved`（空白区切りの真dup）を取りこぼすので触らず記録に留める。(2)cross/synthの図は
  当該ページcharsの引き回しが要るため未適用。(3)X315RM.en p351の`RSE`/`PGST`（多文字欠落）は別のより重い崩れ。

### テーブル表示

- **全テーブル同幅**（2026-09-03、ユーザー要望）— レジスタごとに幅が変わっていたのを、
  PAGE_STYLEの`table{width:100%;max-width:960px}`で統一（bit図は`table-layout:fixed`維持）。
  - **一部で100%が効かない件を修正**（ユーザー報告・liveのHTML/テーマCSSを取得して原因特定）:
    GitHub Pagesのテーマが`.markdown-body table{display:block;width:100%;overflow:auto}`（詳細度
    0,1,1）を持ち、素の`table{width:100%}`（0,0,1）に勝ってtableを**block化**していた。blockの
    tableは中身の実テーブルが内容幅に縮むため、内容の広い多fieldのbit図は100%に見え、Reserved
    単独や説明表は狭く見えた。修正: `display:table!important;width:100%!important;max-width:960px
    !important`でテーマに勝たせる。全67本parity 0・Liquid非破壊。**反映にはpreview再公開が必要**。

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
- **下付きが値の後ろへ移動（operating_conditions.csv）** — ✅ **19行を修正**（2026-09-03、PDF↔MD突合
  サブエージェント（opus）が発見）。セル内で下付きだけが別の物理行に落ち、`norm_text`の空白連結で
  `R_S < 70kΩ`→`R <70kΩ S`（条件列）、`…impedance R_S`→`…impedance R S`（parameter列）、`V_S`→`V S`に。
  凍結`build_operating`は触らず、合成層`_clean_text`（extract_low_power）に**基底1文字＋既知の下付き
  token**（`R/T/C/V/L`＋`S/A/L/L1/L2/IN/OUT/DD/SS/J`）を基底の直後へ戻す2つの正規表現を追加
  （`_TAIL_SUBSCRIPT`: 値の後ろの孤立token、`_END_SUBSCRIPT`: 末尾の`X YY`）。結果: `RS < 70kΩ`・
  `…impedance RS`・`…ground VS`、diff 19挿入/19削除で**意図した行だけ**、凍結base 1,588行はbyte不変。
  build_conflicts/build_index再生成＋check_tables/check_counts/check_docs**全合格**。
- **括弧が閉じない parameter/condition（operating_conditions.csv）** — ✅ **101行→4行**（2026-09-04、
  ユーザー指摘「`(when`とか閉じられていないのでなんかへん」）。原因は3種で、全て**凍結
  `build_operating`に触れず**合成層で直した（凍結base 1,588行はbyte不変、消失value-key 0、行数2,796不変）:
  1. **表題の折り返し**（A11の条件prefix）— bundleの`caption.text`は1行目だけで、`…SRAM (RISC-V5F`の
     続き`+ RISC-V3F)`は次のparagraph行。共有`logical_tables.caption_full`（括弧未閉じ／接続詞・前置詞・
     読点終わりの間、最大3行繋ぐ）を`caption_context`が使う（exporterの`<caption>`と同じ全文）。
  2. **ページ跨ぎで割れたrowspanセル**（A11）— `…in sleep mode (when`（p99）＋`peripherals are powered
     and clock is held)`（p100先頭行）が別セルになりparse_tableのstateを置き換えていた。
     `extract_low_power.fold_page_continuations`: 記号列が空の行で、ページ境界（header繰り返し行を
     跨いで持ち越す）または値の無い行の続きを、上の直近セルへ`_continues`判定で繋ぐ（上が括弧未閉じ
     →続き／文末記号→別物／先頭小文字・`+&/(`→続き／CJK始まりは境界だけ）。値のある行では
     Parameter列に限り、上が括弧未閉じのときだけ繋ぐ。
  3. **凍結baseの行**（`Accuracy of HSI oscillator (after`＋次ページ`calibration)`×3、
     `PLS[2:0] = 100 (falling`＋`edge)`×1）— ページ単位の`extract_text`は次ページ先頭行を拾えない。
     `build_operating_conditions.FoldedCells`/`complete_truncated_cells`: basisのen頁からbundleの
     結合grid（`fold_page_continuations`済み）を引き、「切れた文＋語境界＋括弧が閉じる」候補が
     **1つだけ**のとき全文に差し替える（4欄）。
  - **残4件は資料側**: `I_DD_VBAT` `Backup domain supply current (Remove V and DD V , only powered by
    VDDA BAT`（V203×2/V208/V20x_30x）。原本セル`…only powered by V⏎DDA BAT`にそもそも`)`が無く
    （text layer欠落）、下付きの語順も崩れている。補完元が無いので現状維持。features.csvにも1件
    `(Not`（凍結build_features・別ツール）が残る。
  - 検証: build_conflicts/build_index再生成、check_tables/check_counts/check_docs（下記）、日本語0。
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

- **converter 1.6.3（Feature 2列マージ）— 完了・全reconvert＆canonical byte一致確認済み** —
  `convert.py`の`COLUMN_START_HEADINGS`を`"Features"`→`"Feature"`（単数で"Feature"も"Features"も
  部分一致）に。狙い: H417DS0.en p1でOverview本文とFeature列が2列マージで交錯していたのを分離。
  **全67本を1.6.3へreconvert完了**（VSCode再起動で2回中断したが、`convert_all`は増分方式で
  各docが原子的なので再開で継続・破損なし、最終的に67/67完了）。**検証（2026-09-03）**: (1)export+parity
  **67/67 clean**、(2)`run_frozen --batch`＝**6/6 byte-identical**（build_features/adc_internal/memory/
  timers/flash_geometry/debug_data）——**canonical完全不変を確定**。理由: build_featuresは
  `page.extract_text()`（pdfplumber native・lines[]復元と独立）を使い、1.6.3が変えるのは
  lines[]の2列検出だけなので、text/cell由来のcanonicalは無影響。**効果**: H417DS0.en p1で
  「# Overview」直後にOverview本文が単一列段落で分離（達成）。※Feature**一覧**自体の2列交錯は
  別の細かい課題として残存（1.6.3スコープ外）。export側修正（caption/boundary-dup/grid-dedup/straddling）は
  1.6.3 bundleでもcells/text/geometry不変なのでそのまま動作・parity 0維持。
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

- **表領域の外に落ちたグリフ／列（converter側・保留）** — 2026-09-03の巡回で3系統を確認。
  (1)`LEVEL4`の`4`（H417RM.en p297: グリフ中心x=537.1が表右端532.8の外で、bundle段階で
  どのセルにも入っていない——除去処理の副作用ではない）、(2)ページ跨ぎ継続断片で**先頭列を
  表領域に含めず**（FV2x_V3xRM.zh p64: `R8_CRC_IDATAR …`の行がparagraph行として表外に残り、
  表は3列で始まる。列ずれは`<td></td>`埋めで解消したが名称は未回収）、(3)「Reset value」列が
  ヘッダごと本文へ排出（4列ヘッダ14表・Bit列も失う20ページ）。いずれもpdfplumberの表領域検出
  （罫線ベース）が境界の無い列を取り漏らすもので、export側では復元できない。**再挑戦の条件**:
  converterで、表bboxと同じy帯にある表外の行/グリフを列境界のx位置に合わせて取り込む後処理
  （または該当列だけtext strategy）を作り、`run_frozen --batch`でcanonical byte一致を確かめたとき。

- **通常表へのstraddling除去の拡張** — **→ 同日中に条件を作り直して達成**（✅「セル境界を跨いだ
  グリフの二重取り」の面積・行端・値セル判定を参照。以下は当初撤退した経緯の記録として残す）。
  （reset値へのCJK/句読点bleed `0000b时、`・`0式过`等）— 2026-09-03に調査→撤退。strip_straddling_dupes（bit図で有効）を通常表にも掛ければreset値の
  bled文字を消せるが、除去文字を分類すると**CJK 200・句読点 32は安全だが、Latin英数字 116が危険**。
  内訳に`t\nsu(SI)`→`su(SI)`（`tsu`=setup time）・`t\nd(CLKL_ADIV)`→`d(CLKL_ADIV)`（`td`=delay time）
  のように、**タイミングパラメータの実在する`t`接頭辞を別視覚行から降ってきた重複と誤認して除去**する
  ケースがある。\n制約（bit図側の過剰除去を止めた条件）でもこれは守れない（`t`は別行にあるが実データ）。
  さらに通常表全ページへgeometryを引き回す配線コストも要る。**再挑戦の条件**: 「除去文字がCJK/句読点の
  ときだけ落とす（Latin英数字は触らない）」＋「reset値列と分かる列限定」にできたとき。CJK/句読点限定なら
  232件は安全に消せる見込み。

- **見出し検出のミス**（converter由来・記録のみ）— 2026-09-03の巡回で確認。(1)章題の折り返しが別見出しに
  （H417RM.en p357: `# Chapter 20 …Transceiver`＋`# (SerDes)`）、(2)大フォントの傍注が複数H1に
  （L103RM.zh p16/en p19: 「注：…」が5つのH1に分裂）。bundleのline roleがheadingに化けており、
  export側で「継続っぽい見出し（`(`始まり・小文字始まり・文末が未完）を直前へ統合」する案は誤統合の
  リスクが高い。zh/en両版に同じ崩れが出る＝converterのheading判定heuristicの取りこぼし。要reconvertか
  慎重なheuristic。**保留**。

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
