# pipeline/ — PDF構造化の本番経路（D18）

[English](README.md)

旧`tools/`のPDF直読み抽出器を置き換える本番実装。前提と設計は
[事前調査（D17）](../docs/structured-migration-survey.ja.md)と
[D16最終報告](../docs/structured-document-workflow.ja.md)にあり、設計案は
2026-09-01にユーザーが暫定承認した。**旧`tools/`と正本CSVはbaselineとして凍結**し
（台帳は[`baseline/tables.csv`](baseline/tables.csv)）、この経路の出力は旧経路との
比較を通ってからCSV単位で切り替える。

## 置き場所と保存（D17設計案どおり）

| 何 | どこ | 保存 |
|---|---|---|
| bundle（pages・geometry） | `.cache/structured-bundles/<stem>.<lang>/` | **非保存**（決定的に再生成できる。D17実測） |
| manifest（原本SHA-256・全page/geometryのSHA-256・engine/converter版） | `structured/<stem>.<lang>/manifest.json` | **コミット**（ズレ検出の正本） |
| review sidecar（人の判断） | `structured/<stem>.<lang>/review.json` | **コミット**（再生成不能。再変換は上書きせず、原本が変われば流用せず止まる） |
| baseline凍結台帳 | `pipeline/baseline/tables.csv` | コミット（凍結を宣言するcommitと一緒に） |

## 工程

```text
ingest/    PDF → bundle（L0）。convert.py（1文書）・convert_all.py（catalogの68版）
common/    logical_tables.py（**L1: ページを跨ぐ表の断片を1つの論理表に結合**。
           変換器の継続flagに依存せず構造で判定——無caption・ページ先頭・前ページ
           末尾が表・縦位置の連続・列構造互換。列の対応付けは列数が同じなら位置、
           違えばx座標の和集合。reviewとextractが同じ部品を使う）
extract/   pdfcompat.py（bundle互換層＋原本hashの入口ゲート。PDFへのsilent fallbackなし）
           datasheet/run_operating.py（凍結ロジックをbundle入力で走らせる。
           evidence/operating_conditions.csv の1,588行を**byte一致**で再現——2026-09-01実測）
           datasheet/extract_low_power.py（A11: 消費電流・ウェイクアップ時間。
           caption選定＋断片結合＋表番号スコープの2段階zh/en照合。偽conflict 0）
           datasheet/build_operating_conditions.py（**operating_conditions.csvの正本生成器**。
           基礎行＋A11行。2026-09-01に受入・**最初に切替が完了したCSV**——2,796行）
           manual/extract_debug_wiring.py（**debug_wiring.csvの正本生成器**——新経路が
           初めて正本に足した新規evidence表。WCH-Link manualの配線表＋両対応注記）
           run_frozen.py（凍結toolをコード不変のままbundle入力で走らせ、出力を
           凍結CSVとbyte比較する——旧新パリティの道具。台帳はworklistのD18）
           run_scan_errata.py（エラッタ増分検査（KNOWN/NEW）をbundle入力で。
           対象選定は凍結toolのまま）
           images/run_extract_images.py（family repoのimage/を作る凍結
           `extract_images`を、**`pdfplumber.open`だけ原本hashゲート経由**で走らせる。
           pixelのcropは原本PDFが要りpdfcompatでは差し替えられないので、openで
           hash照合だけ挟む＝**最後のPDF直読みも実行経路の要件（ずれ検出）を満たす**）
reconcile/ compare_csv.py（凍結CSVとcandidateの unchanged/added/changed/missing）。zh/en照合は今後
common/    review_sidecar.py（**L2: 人の判断の読み手**。正本は
           `structured/<stem>.<lang>/review.json`——block IDごとのapproved/rejected、
           原本SHA-256にpin。新経路の抽出器はrejectedのblockを正本生成から外し、
           必須の表が拒否されたら黙って劣化せず停止する。原本が変わった
           sidecarは流用せず止まる——converterの再変換ゲートと同じ判定を
           読む側でも行う。判断の記録は`review/record_decision.py`。
           **zh/enの表対応はcaption番号一致で自動**（2026-09-02実測: 32文書
           ペア中16ペアは完全一致、非対称の残差は**全コーパスで83番号**だけ）
           ——残差は`review/propose_pairs.py`が両版のcaption原文つきで並べ、
           人が対を決めたら両blockへ同じ`canonical_table_number`を記録する）
review/    render_assets.py（**図のpixel描画**。原本hashを照合してから、図領域を
           150dpiのPNGに描いて`assets.json`（領域bbox・PNGのSHA-256）と置く。
           図領域は文字ではなく**graphicsの縦クラスタ**で決める——図中のラベルは
           paragraph行として写るので文字を境界にすると領域が潰れる。68文書で
           3,829 asset・**図caption 3,023の全部に実画像（100%・警告0）**——caption無しでも回転文字入りの大クラスタ（封装図・引脚配置図）は独立assetとして描画——
           図全体が1つの無caption表として誤検出される場合（過滤器編号の示例・
           波形図・応答グラフ）もcaption直下ならクラスタへ算入する。
           本文の参照文（「图19-2是…」「figure 21-1.」等）はcaption扱いしない
           ——判定は`pipeline/common/figure_captions.py`に一本化）
           export_markdown.py（人が読むMarkdown。**最終ゴール「PDFとの差ゼロ」の本体**。
           **変換器が`reading_order`から外し、表のセルにも入らなかった行を拾い直す**
           （`logical_tables.recovered_lines`/`reading_stream`。parityと共有）——図のラベルは
           「図をtableと誤検出した箱」の外側に落ちることがあり、どちらの流れにも無く黙って
           消えていた（`USBHS OSC32_OUT`・`1HCLK external memory`。1,110行・57文書）。
           語が1つも他所に無い行だけを拾うので二重には出ない。
           header/footerはコメント化、表はrowspan/colspan保持のHTML、
           **ページを跨ぐ表はL1で結合して開始ページに全体を描き、続きページには
           可視ポインタ**（68文書で3,914表を結合）、**ページ境界でセルの中身が
           割れた「宙ぶらりん行」は直前セルへ畳む**（`fold_boundary_spills`。
           MCO説明の続き`Other: No clock output.`等——1,937セル／50文書。
           同一ページ内は比較表の縦並びを誤結合するので境界行だけが対象。
           継続セルはグリッドから消して空行を残さない。exporterとparityが
           共通で呼び、抽出器の凍結CSVは触らない）、**セル内の物理行は折り返しか
           意図的な改行かを文字種で出し分ける**（句読点終わりは`<br>`、識別子途中
           （`USAR`+`T1`）は直結、英単語は空白。原本の段落を保つ。**代入を書き切った断片に
           独立した英単語が続くのは折り返しでない**——`SPI3_RM=1`＋`Remapping`は改行のまま。
           連結すると`CAN1_RM=10Remapping`で設定値10が読めなかった。162セル・8文書）、
           **表の1行目は`<th>`・原本の太字/斜体を`<strong>`/`<em>`で再現**
           （fontから。太字3%・斜体3.5%を実測。textは不変なので凍結CSVは無傷）、
           **caption行を持つ表だけが`<caption>`を出す**（無caption表が
           continuation継承で前ページの表番号を借りて名乗るのを止めた。内部IDは
           コメントへ）、
           **レジスタのbit図を組み直す**（`31 30 … 16`のbit番号行を表のヘッダ行へ
           畳み、bitを等幅の折り返し列で描く。各フィールドはbit番号glyphのx中心
           （geometry由来）で列へ割り当てるので、抽出が16列の空箱でも8〜9列に潰れて
           名前入りでも同じように扱える。番号行は「0..31の厳密降順・長さ≥8」を採るので
           byte境界図（`31 24 23 16 15 8 7 0`）や16幅でない図（`11 10 … 0`）も拾い、
           横並びが混ざった非降順（`8 7 5 3 0 9 8 7`）は弾く。罫線の無い図で
           フィールド行が1本だけなら全幅の合成テーブルにする。狭い列で縦に割れた名前
           （`Reser`+`ved`→`Reserved`）は連結し、**隣セルの断片が交錯して壊れた名前は
           同ページの記述表のName列を正解として直す**（`HSYNCSCS`→`HSYNCS`・`PLLRPDLLY`→
           `PLLRDY`・`ATACAMTADCMD`→`ATACMD`。名称列の綴りが描画文字の部分列になっていて、
           かつ**落ちる文字が全てその名前に在る**ときだけ差し替える——交錯重複は名前のグリフが
           二度出る形だが、`HSICAL[7:0]`はbit範囲を失うので触らない）。**索引つきの名前は
           `base+bit番号`で組む**——索引は**そのセル自身の列のbitヘッダ**から、baseは同じ図の
           無傷の兄弟セル・記述表の族名から末尾`x`を外した綴り（`SWIERx`→`SWIER`）・同ページが
           範囲つきで書いた綴り（`PENDSET[31:16]`）のいずれかから取る（`PENPDESNTDAS1T5`→
           `PENDSTA15`・`FBMFB27M`→`FBM27`）。歯止めは4つ: **既に「base+自分の列のbit」の形なら
           触らない**（DMA_INTFCRの`CTCIF1`の`C`はclearの意味）、**図の3セル以上が共有する頭文字は
           落とさない**、**索引は短くしない**（`ODR11`→`ODR1`にしない）、**隣接bleedの除去は行に
           繰り返す頭文字を飛ばす**（`SWIE`+`R 14`の`R`を落として`SWIE14`にしていた）。
           1,208セル・21文書）、TIMのCCMRのような出力名/入力名の
           2段は2行で残す。bit図はページ跨ぎの表結合からも外す（背中合わせの2図が
           誤結合すると組み直しに要るセルのbboxが失われる）。**ページ跨ぎで割れた図**
           （番号行がページ末尾・箱が次ページ先頭）は`document_bitfields`が跨いで対応づけ、
           前ページの番号中心で箱を組み直し、番号行ページには「次ページの図へ」の印を置く。
           変換は`pipeline/common/logical_tables.apply_bitfield`と
           `export_markdown.document_bitfields`に共通化し、exporter・parity検査・auditが
           同じものを呼ぶ）、
           **表セルは既定で中央寄せ・長い/複数行セルは左寄せ**（PDFに寄せる）、
           **セル境界を跨いだグリフの二重取りを落とす**（pdfplumberのcropは境界に載った
           グリフを両セルに入れる——`[31:12] R`・`RO R`・`ReservedR`・zh説明文の行末`，`が
           reset値列へ。テキスト隣接で分かるものは`strip_boundary_dupes`、それ以外は
           `strip_straddling_dupes`がgeometryで「その具体的なグリフが別セルに半分以上入り、
           そのセルの行端に同じ文字がある」ことを確かめて落とす。自セルに半分以上入る
           グリフは触らないので、狭い列からあふれた名前（`PB14`・`SWIER22`）の文字は
           失われない。ページ跨ぎ結合表はセルごとに出自ページを持ち、そのページのグリフで
           判定する）、**`Reset`/`value`に折り返したヘッダがpdfplumberで偽データ行になった
           ものをヘッダへ畳む**（`fold_header_wrap`。`fold_boundary_spills`が持つ行番号も
           一緒に繰り上げる）、**spanに覆われていない空スロットは`<td></td>`で埋める**
           （先頭列を取り漏らした継続断片が左へ詰まらない）、**中身の無い表は出さず、
           図領域内の表はプレーンテキストにする**（さらに**重なりセルの残骸だけの1列表は描かず**——
           全語が重なる本体表のセルの物理行と一致するもの559表——**縦割れ名の断片が別行として
           も出る幽霊行**（`BU/RS/T_E/ND`の下の`RS`）はグリッドから落とす。64行）（どちらも図のboxを表と誤検出したもの。
           全corpusで1,115と3,758）。ただし**図領域の中身が本物の罫線表なら表として描く**
           （行3以上・列2以上・非空6以上。`logical_tables.looks_ruled`。原本が表題を
           `Figure`と名乗ると罫線が図クラスタになる——V407RM.en p475
           `Figure 26-19 Mode D FSMC_BCR1 bit field`はzh版では`表26-19`。106表・37文書。図の箱のラベル格子は除く——穴が多い/1行目が揃わない/1文字セルばかり/同じ語の反復、
           および5行以下で空行を含むもの（`Laye FI|er IFO|1`＝`Layer 1 FIFO`の箱）は表と見なさない）、**大フォントの本文がheadingに化けたものを段落へ戻す**
           （フォントサイズ由来のheadingが3連続以上・`注：`/`Note:`始まり・50字超・CJK文末
           句読点終わり——2,390行。番号/章見出しは触らない）、**表の箱の中にある見出しは
           表の中身なので段落へ**（DMA映射表の太字行が`#`になり目次を壊していた。243行・16文書）、**章題の折り返し2行目を1行目へ
           繋ぐ**（`(SerDes)`。括弧が開いたまま／読点で終わる番号見出しも短い次行を繋ぐ——`y=1/2）`）、
           **pinout図の題として刷られた封装名は見出しにしない**（`CH32V003F4P6`×4）、**密なpin表は
           回転文字が多くても「captionの無い図」にしない**（`render_assets`: 8行×4列以上・6割以上非空の
           表がクラスタの6割以上を覆う）、**セルの中で新しい選択肢が始まる行は改行を保つ**
           （`0：`・`11:`・`0x1F:`・`[5:0]：`・`注：`・`Note:`。`中断指示域`＋`0：异常`＋`1：中断`が
           一続きに潰れていた。1,740箇所・29文書。英単語の折り返し`mode:`は値でないので繋ぐ）、
           **狭いセルで途中折り返した英単語は、そのページの語彙が裏づけるときだけ繋ぐ**
           （`Rese`+`t`→`Reset`・`channe`+`l`。既定は空白のまま——`source is`+`greater`）、
           **本文の`*`をエスケープ**（`2*ADC(TKey) … 4*OPA`が斜体化して`*`が消えていた。817行・
           58文書。表のセルはHTMLブロックの中なので触らない）、**pin表・remap表のセルは1行1機能で`<br>`**（`MCO`/`TIM1_CH1`/
           `USART1_CK`が地続きになっていた。`0x…`の転送一覧・`R32_…`の別名も同様）、**セル内で基底から
           離れた下付き/上付きをグリフ寸法と位置で戻す**（`V *2-1.5DD5`→`VDD5*2-1.5`・`f = 2.4MHz S`→
           `fS = 2.4MHz`・`232`→`2^32`。`logical_tables.reattach_cell_subscripts`。文字集合が変わる変更は
           しない）、**reset値/Access列に降りた説明列の行端グリフを落とす**（`e 0 e`→`0`・`L<br>RO 10`→`RO`。
           折り返した16進1桁`0xFFFFFFF`+`F`は繋ぐ）、**数字は境界の二重取りとして落とさない**
           （`HSRXEN = 1`・`Page 0`の値が消えていた）、**ページ跨ぎの結合表では続きページ先頭に刷り直された
           列見出しを落とし、複数行に折り返した見出しを1行へ畳む**（`Pin`/`name`・`Main`/`function`/
           `(after`/`reset)`）、**境界で二つに割れ境目の文字が両側に入った本文行を繋ぐ**（zh版DS:
           `…対外`/`外多组…`。同じxで3対以上割れているページだけ）、**重なりセルの残骸（1列断片）は
           ページ跨ぎ連鎖の起点にしない**（V407RM.en p145の残骸が続き11行を引き取って出力から消えていた）、**2行に折り返した表題は`<caption>`に全文を出し、続き行を本文から
           消す**（括弧が閉じていない／`or`・`with`・読点で終わる表題。`logical_tables.caption_full`
           をoperating_conditionsの抽出器と共有し、CSVの条件prefixも全文になる。
           `…SRAM (RISC-V5F`＋`+ RISC-V3F)`）、**箇条書きのbulletを二重にしない**、**太字風の重ね描きで
           2回拾われたグリフを畳む**（`OOSSCC__IINN`→`OSC_IN`。16進値は除外）、
           **pdfiumが白紙にした図**（暗号化PDFの埋め込みJPEG/パレットraster）**は
           render_assetsが画像streamを直接復号して貼る**（11枚が白紙だった）、
           **既知の取りこぼしはその場所に見える印**——図caption直後の警告＋原本
           ページへのリンク、大きい画像の占位、表issuesの警告、(cid:N)化けの警告、
           **添字が`*`に化けたglyphの警告**（壊れたToUnicode。pdfplumberでも
           pypdfium2でも同一＝文字層では復元不能——806 glyph／14文書を実測。
           判定は`pipeline/common/lost_subscripts.py`に一本化し、parity検査が
           印を必須にする））
checks/    compare_manifest.py（環境差の検証）
           check_markdown_parity.py（bundle→Markdownで本文行・表セルが読み順どおり
           全部現れること＋取りこぼしの印があることの機械検査。**68文書全合格**。exporterが
           畳んだ行は畳んだ先で見る——折り返し表題の2行目は`<caption>`の中に在ること。
           この検査は存在と順序しか見ないので、export側の変換にはPDF↔Markdownの意味検証
           （サブエージェント）を必ず対にする）
           cross_engine.py（**取り込み正しさの独立検証**。bundleの文字集合を別実装の
           pypdfium2と突き合わせる——順序でなく文字マルチセットを比べ、pypdfium2が
           取れてbundleが落とした文字を報告。pypdfium2のハイフン誤読（`-`→`\x02`）は
           正規化。全68版で**取りこぼし0**を実測——独立エンジンが取る文字を
           bundleは一文字残らず取る。手動運用: `uv run --with pypdfium2`）
publish/   regenerate.py（**一括再生成のentry point**。bundle再変換→切替済み
           evidenceの再生成→下流indexの再導出→検査、の順で既存CLIを呼ぶ。
           `--verify`で凍結パリティ＋エラッタ増分検査、`--human`で図の描画→
           人向けMarkdown→差ゼロ検査も。失敗した段で止まる。全段成功＋
           `git status`が空＝冪等を実測——2026-09-01）
```

candidateの置き場は`.cache/pipeline-candidates/`（非コミット）。凍結CSVへ直接書く
toolはこの経路に無い（**切替済み・新設のCSVは例外**——`operating_conditions.csv`
（切替）と`debug_wiring.csv`（新設）の正本生成元は2026-09-01からこの経路）。

## ingestがPoCと違う点（4つの修正。1と2はD17の実測、3はCIの実戦検出、4は人向け出力の精査）

1. **決定性**: pdfminerがinline imageへ付ける`id()`由来の数字名を捨てる
   （converter自身の`p66-draw-image-00002`形式が識別子）。同一原本＋同一版なら
   bundleはbyte一致で再生成できる
2. **header/footerの検出が反復ベース**: 全ページを先に1回歩き、上下12%の帯で
   「数字を`#`に畳んだ同じ綴りが**ページの縁から同じ距離**に、全ページの25%以上
   （最低3ページ）繰り返す」行を拾う。y閾値だけのPoCはzh版footer（下端比93.8%）を
   系統的に取りこぼした。反復判定はheading判定より先（TOC等の小フォントページで
   footerがheadingに化ける実測があったため）。縁距離なので横向きページにも効く。
   **1.2.0で規則を2つ追加**（R-30の抽出が「footer未分類→表結合が切れる」を発見、
   全コーパス実測で67行の取りこぼしを確認）: 厳格帯（6%）では同綴り同距離
   **3ページ以上**で合格（章ごとに綴りが変わるheaderの変種、途中でfooterの
   位置が変わった文書——V00X RM zhはp198以降の32ページ＝14%が別距離）、
   合格した**綴りは距離が違っても余白扱い**（横向きpin表ページのfooter）。
   ページ番号だけの行（畳んで`#`）は新規則から除外——数字だけの本文を
   巻き込まない

3. **manifestのgeometry_sha256は非圧縮のJSONに対するhash**（converter 1.1.0）。
   gzipの圧縮バイト列はzlibの版で変わり、GitHub Actions上の再変換が
   geometry_sha256だけ全ページ不一致になった（2026-09-01、`structured-repro.yml`が
   **設計どおり環境差を検出**した初の実戦）。圧縮は保存の都合であって内容ではない

4. **90°回転の縦ラベルを読める順に組み直す**（converter 1.3.0）。封装図・
   引脚配置図のpin名はpdfplumberの行組みだと**鏡順**になり（`33DDV`＝VDD33）、
   さらに複数の縦ラベルが1行に混ざる。x0で列に分割し、列内はglyphのmatrixの
   向きで並べ替える（b=+1は下から上へ読む＝top降順）。回転行はheading判定から
   も外す（大フォントの図中ラベルがlevel-1見出しに化けていた）。**1.3.1で表セルにも同じ組み直しを適用**——引脚定义表の縦書き型番ヘッダが
   セルの中で鏡順だった（`6UEW714H`＝H417WEU6。322表／43文書）。あわせて
   **表captionの番号regexを行頭にanchor**——「注：表21-4的…」のような参照文が
   captionに化けていた6件を除去。`page["text"]`は触らないので凍結toolのbyte
   一致は崩れない

5. **datasheetの2カラム（overview/features）を左右に分離**（converter 1.5.0）。
   pdfplumberの行抽出は2カラムの左右を同一y行として1行に結合する
   （`- QingKe…core ● 3-group…`と混ざり読めない）。`Overview/Features/概述`等の
   見出しを持つdatasheetページに限り、表外wordのx0の中央域最大ギャップを列境界に、
   見出しbottom以降を左カラム全行→右カラム全行でcrop抽出（タイトルは全幅帯に
   残す）。見出しで絞るので比較表・bit図・pin表は対象外（全51対象ページが
   overview系＝誤検出0）。境界が出ない版は現状維持（安全側）

6. **下付き・上付きを本文行へ統合**（converter 1.6.0）。pdfplumberの行抽出は
   topでグループ化するので、`V`（top≈102）の下付き`DD`（top≈106・7pt・**bottomは
   Vと揃う**）が別行に落ち、`V`と`DD`が離れて`V_DD`が読めない（全datasheetで約
   4,600件）。本文より小さい行を内部のx空白で**クラスタに割り**、
   各クラスタをbottom（ベースライン）±2.5pt揃い・x的に含む本文行へ差し込む。挿入は
   **ベース行のtextをそのまま保って位置に入れる**——charには空白が無く（`itputs`）
   gap判定では単語間空白を復元できないため。跡の空白は次が記号なら詰め・英単語なら
   残す（`(VPOR/PDR)` と `VDD is` を両立）。複数下付き（`V…V`に`DD`/`PVD`）は
   クラスタ単位で右から入れるので位置がずれない（`VDD…VPVD`）。全クラスタが本文行に
   着地したときだけ統合し、外れたら小行を丸ごと残す（glyph欠落を作らない）。図中の
   極小ラベル（bottomの揃う本文行が無い）は統合されず残る。**下付き判定はページ全体の
   中央値でなく隣接する基底との相対サイズ**（`小 < 基底 × 0.82`）で見る（1.6.1）——
   図中の電圧ラベル`V_BAT`の下付きは8.2pt（body 10.6の77%）でグローバル閾値0.72には
   収まらないが、基底`V`11.9に対しては明確に小さい（L103DS0 p36の孤立18→0）。
   `page["text"]`は`extract_text()`が別に作るので凍結toolのbyte一致は崩れない

7. **表セルの中の下付き・上付きを元の位置へ戻す**（converter 1.7.0/1.7.1）。6.と
   同じ欠陥のセル版——pdfplumberはセル内の下付きを別の視覚行として拾うので、`VSS`が
   `V\nSS`、`VDD5*2-1.5`が`V *2-1.5DD5`、`2^20`が`220`になる（14,738セル／61文書）。
   1.7.0までは exporter と parity 検査だけが直していたので、**bundleのセルを読む
   抽出器には壊れた綴りのまま届いていた**。直す実体は
   `logical_tables.reattach_cell_subscripts`——3者が同じ関数を呼ぶので読みがずれない。

   **壊れた分割は情報を持っているので、そちらも残す。** pdfplumberが残す改行は
   下付きの境界で、凍結`build_operating.norm_symbol`はそれを正規化記号に変える
   （`I\nDD`→`I_DD`。`KEEP`はその形しか通さない）。1.7.0で繋いだ形だけを残したら、
   `evidence/operating_conditions.csv`の**`I_DD`系1,207行がエラーも出さずに消えた**。
   1.7.1からはセルが2つの面を持つ——表が`cells`と`extracted_rows`を両方持つのと
   同じ考え方で、`text`が復元後の読み順、`text_split`が版面の割り方。
   `logical_tables.text_grid(merged, "text_split")`で引け、`merge_cells`が結合セルにも
   引き継ぎ、`extract_low_power`がこれを読む。`extracted_rows`は**触らない**ので
   凍結tool 19本は無傷（pdfcompatの`Table.extract()`は`extracted_rows`を返し、
   `crop()`は未実装——凍結toolは`cells[].text`を見られない）

8. **壊れた文字は、覆わずに直す**（converter 1.8.0）。exporterだけが直していた3つを
   ここへ移した——**見た目の問題ではなく文字が壊れている**ので、bundleを読むものが
   全部間違った字を受け取っていた。

   - **私用領域コードポイント**（9,291個・65文書。`lines`・`words`・`page["text"]`・
     `cells`・`chars`の全部）。PDFが記号フォントのグリフを私用領域の符号位置のまま
     文字層に書いたもので、``はWingdings 0x6Cの箇条書き記号。実測のコードポイント
     ×フォント: 0xf06c=Wingdings 9,233・NSimSun 1・SimHei 1、0xf0b7=SymbolMT 24・
     SimHei 5、0xf0b4=SymbolMT 18、0xf06e=Wingdings 8、0xf0b1=SymbolMT 1。CJKフォントの
     7件も箇条書きの文脈なのでフォントで分けない。**情報は失われない**——元がどの
     グリフだったかはgeometryの`font`が持ち続ける。`page["text"]`も直す——壊れた文字は
     互換のための面ではない。
   - **重ね描きの畳み込み**（143件。`OOSSCC__IINN`→`OSC_IN`）。文字層だけ。`chars`は
     2つのグリフを持ったままなので、重ね描きだった事実はそこに残る。
   - **行の中に残った下付き・上付き**（805行）。`merge_subscript_lines`（1.6.0）は
     別の視覚行になった小行を畳むが、こちらは同じ行に残ったもの。潰れると**値が
     変わる**のが効く——`2^20`が`220`、`x^32+x^26`が`x32+x26`。セルと同じ関数・同じ
     歯止め（結果がグリフの読み順と一致すること）。`page["text"]`は触らない
     （`extract_text()`が行構造無しに作る面なので。`merge_subscript_lines`と同じ扱い）。

   **表題も同じ版で全文を持つ**ようにした。それまでbundleは折り返した表題の1行目だけを
   持ち、exporterと`extract_low_power`が**両方**`caption_full`を呼んで組み直していた
   ——同じ修復を2つの表面で掛けていた。いまは`caption.text`が全文、
   `caption.continuation_line_ids`が飲み込んだ行のidで、本文から落とす側はそれを読む
   だけでよい。移す前に測った——datasheet全件で、低消費電力表の表題パターンの当たり
   判定が1行目でも全文でも同じ（**選択が変わる表は0件**）。おまけにバグの型がひとつ
   消える: exporterは全文を私有キーで持っていたのでページ跨ぎ結合表へ載せ替える必要が
   あり、忘れると続き行が本文からも表題からも消え、parityでは検出できなかった。

9. **セル境界で二重に数えたグリフを落とし、途中で割れた行を繋ぐ**（converter 1.9.0）。
   exporterだけが直していた最後の4つ（9,288箇所）。

   - `strip_boundary_dupes`（2,337セル）: `[31:12] R`・`RO R`・`s Description`
     ——隣のセルの端の文字を二重取りしたもの。
   - `strip_straddling_dupes`（4,457セル）: 箱が境界を跨ぎ`crop`が両セルに入れたグリフを
     geometryで裏取りして落とす。
   - `clean_reset_column`（2,200セル）: 説明列の行末文字がreset値の列に降ったもの
     （`0`が`e 0 e`）。列を決めるのにヘッダ行が要るので、**継続断片では何もしない**
     （安全側）。ヘッダが揃う結合表ではexporter側がもう一度掛ける。
   - `split_line_merges`（294行）: 本文行が列境界で割れ、境目の1文字が両側に入ったもの
     （zh版datasheetは本文全行が x=241 で割れる）。

   **順序が効く**: 境界の二重取り落としは下付き復元の**後**。
   `reattach_cell_subscripts`は「結果がグリフの読み順と一致すること」を歯止めにして
   いるので、先にグリフを落とすと照合が外れて復元が黙って効かなくなる。

   **行の結合で行を消さない。** 繋いだ結果は左の行に入れ、右の行には`merged_into`
   （左のid）を付ける——消すと`reading_order`とidの対応が崩れ、**版面が二つに割って
   いた事実**も消える。読み手は`merged_into`のある行を飛ばすだけでよい。
   `split_line_merges`の戻り値は`{左id: (右id, 続き)}`に変えた（呼ぶのはconverterだけに
   なったので）。セル系3つはexporterにも残す——converterには見えないページ跨ぎの
   結合表という単位にも掛かるため。

実測（V003 zh/en）: 本文・語・表・文字は旧PoC bundleと**完全一致**、変わるのは
roleと画像名だけ。version+pageのfooterはen 35/35・zh 30/30で取りこぼし0。

## 実行

```sh
uv run pipeline/publish/regenerate.py                   # 一括再生成（bundles→evidence→index→checks）
uv run pipeline/publish/regenerate.py --full            # 全CSVの再生成（旧tool群をbundle入力で。約1.5時間）
uv run pipeline/publish/regenerate.py --verify --human  # ＋凍結パリティ・エラッタ・図・Markdown・差ゼロ検査
uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
uv run pipeline/ingest/convert_all.py --jobs 4          # catalogの68版。incremental
uv run pipeline/checks/check_bundle.py .cache/structured-bundles/<stem>.<lang> \
  --source <PDF>                                        # 独立検証ゲート（1.1.0以降）
```

`convert_all`は`structured/`のmanifestと原本SHA-256・engine版・converter版が
全部同じ文書を跳ばす（`--force`で全変換）。engineは`uv.lock`が固定する
pdfplumber。環境差（別マシン・CI）の検証は`.github/workflows/structured-repro.yml`。


## previewリポジトリ（人向けMarkdownの確認）

`structured-markdown`は量が多く（11k ファイル・約95MB）正式リポジトリに入れると
ログが汚れるので、**使い捨てのpreviewリポジトリ**に1コミットで公開して
GitHub Pagesで見る。推奨リポジトリ名: **`ch32-device-data-preview`**（org直下）。

```sh
uv run pipeline/review/export_markdown.py --all        # トップindexも生成される
pipeline/review/publish_preview.sh ../ch32-device-data-preview
# → https://ch32-riscv-ug.github.io/ch32-device-data-preview/
```

スクリプトは毎回orphan branchを作り直してforce pushするので、**リポジトリは
常に最新の1コミットだけ**を持ち、履歴が育たない。PagesのJekyllは既定で
`.md`相対リンクの変換とREADMEのindex化をやる（Liquidが特別扱いする並び——
波括弧の2連続と「波括弧＋percent」——は
全出力でゼロを確認済み）。11kファイルでPagesのビルドが時間切れになる場合でも、
github.comのファイルビューが同じMarkdownを描画する。

## baseline凍結

`baseline/tables.csv`は正本CSV（index manifest込み。凍結時点で54ファイル、現在60
——凍結後に生まれた5表はカバレッジの穴に気づいた2026-09-06に追加した）の行数と
SHA-256。凍結後は、

- 旧`tools/`のPDF直読み19本は既存CSVを再現する参照実装として更新を止める
- 新toolは凍結CSVへ直接書かず、旧新比較（`unchanged / added / changed / missing`）を
  通ってからCSV単位で正本を切り替える（受入5条件は調査報告の項目7）
- 凍結後に旧側へ修正が要るときは、明示的に凍結を解除して台帳を取り直す

**その約束を守らせるのが`tools/check_baseline.py`**で、これは「守らせるものが無かった」
から作りました。**台帳を読むコードが1本も無かった**ので、取り直しを忘れても何も落ちず、
2026-09-06に数えたら当時載っていた55表のうち**27表がずれていました**——正本はどれも正しく（1件ずつ
現行の生成器で再生成してbyte一致を確認）、台帳だけが5日古い状態でした。腐り検出器その
ものが腐っていたわけです。検査はCIと`regenerate.py`で走り、正本が動いたのに台帳が
動いていなければ落ちます。落ちたら**まずその変化が意図したものかを確かめてから**
——生成器を`--out`でスクラッチに走らせ正本とbyte比較——`uv run tools/check_baseline.py
--record`で書き直し、台帳を同じcommitに入れてください。
