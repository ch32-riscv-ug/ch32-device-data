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
ingest/    PDF → bundle（L0）。convert.py（1文書）・convert_all.py（catalogの67版）
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
           paragraph行として写るので文字を境界にすると領域が潰れる。67文書で
           3,676 asset・**図caption 2,871の全部に実画像（100%・警告0）**——caption無しでも回転文字入りの大クラスタ（封装図・引脚配置図）は独立assetとして描画——
           図全体が1つの無caption表として誤検出される場合（過滤器編号の示例・
           波形図・応答グラフ）もcaption直下ならクラスタへ算入する。
           本文の参照文（「图19-2是…」「figure 21-1.」等）はcaption扱いしない
           ——判定は`pipeline/common/figure_captions.py`に一本化）
           export_markdown.py（人が読むMarkdown。**最終ゴール「PDFとの差ゼロ」の本体**。
           header/footerはコメント化、表はrowspan/colspan保持のHTML、
           **ページを跨ぐ表はL1で結合して開始ページに全体を描き、続きページには
           可視ポインタ**（67文書で3,770表を結合）、**ページ境界でセルの中身が
           割れた「宙ぶらりん行」は直前セルへ畳む**（`fold_boundary_spills`。
           MCO説明の続き`Other: No clock output.`等——1,937セル／50文書。
           同一ページ内は比較表の縦並びを誤結合するので境界行だけが対象。
           継続セルはグリッドから消して空行を残さない。exporterとparityが
           共通で呼び、抽出器の凍結CSVは触らない）、**セル内の物理行は折り返しか
           意図的な改行かを文字種で出し分ける**（句読点終わりは`<br>`、識別子途中
           （`USAR`+`T1`）は直結、英単語は空白。原本の段落を保つ）、
           **表の1行目は`<th>`・原本の太字/斜体を`<strong>`/`<em>`で再現**
           （fontから。太字3%・斜体3.5%を実測。textは不変なので凍結CSVは無傷）、
           **caption行を持つ表だけが`<caption>`を出す**（無caption表が
           continuation継承で前ページの表番号を借りて名乗るのを止めた。内部IDは
           コメントへ）、
           **レジスタのbit図を組み直す**（`31 30 … 16`のbit番号行を表のヘッダ行へ
           畳み、bitを等幅の折り返し列で描く。各フィールドはbit番号glyphのx中心
           （geometry由来）で列へ割り当てるので、抽出が16列の空箱でも8〜9列に潰れて
           名前入りでも同じように扱える。狭い列で縦に割れた名前（`Reser`+`ved`→
           `Reserved`）は連結し、TIMのCCMRのような出力名/入力名の2段は2行で残す。
           変換は`pipeline/common/logical_tables.apply_bitfield`に共通化し
           exporterとparity検査が呼ぶ）、
           **表セルは既定で中央寄せ・長い/複数行セルは左寄せ**（PDFに寄せる）、
           **既知の取りこぼしはその場所に見える印**——図caption直後の警告＋原本
           ページへのリンク、大きい画像の占位、表issuesの警告、(cid:N)化けの警告、
           **添字が`*`に化けたglyphの警告**（壊れたToUnicode。pdfplumberでも
           pypdfium2でも同一＝文字層では復元不能——806 glyph／14文書を実測。
           判定は`pipeline/common/lost_subscripts.py`に一本化し、parity検査が
           印を必須にする））
checks/    compare_manifest.py（環境差の検証）
           check_markdown_parity.py（bundle→Markdownで本文行・表セルが読み順どおり
           全部現れること＋取りこぼしの印があることの機械検査。**67文書全合格**）
           cross_engine.py（**取り込み正しさの独立検証**。bundleの文字集合を別実装の
           pypdfium2と突き合わせる——順序でなく文字マルチセットを比べ、pypdfium2が
           取れてbundleが落とした文字を報告。pypdfium2のハイフン誤読（`-`→`\x02`）は
           正規化。全67版で**取りこぼし0**を実測——独立エンジンが取る文字を
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
   4,600件）。本文の0.72倍以下の小フォント行を内部のx空白で**クラスタに割り**、
   各クラスタをbottom（ベースライン）±2.5pt揃い・x的に含む本文行へ差し込む。挿入は
   **ベース行のtextをそのまま保って位置に入れる**——charには空白が無く（`itputs`）
   gap判定では単語間空白を復元できないため。跡の空白は次が記号なら詰め・英単語なら
   残す（`(VPOR/PDR)` と `VDD is` を両立）。複数下付き（`V…V`に`DD`/`PVD`）は
   クラスタ単位で右から入れるので位置がずれない（`VDD…VPVD`）。全クラスタが本文行に
   着地したときだけ統合し、外れたら小行を丸ごと残す（glyph欠落を作らない）。図中の
   極小ラベル（bottomの揃う本文行が無い）は統合されず残る。`page["text"]`は
   `extract_text()`が別に作るので凍結toolのbyte一致は崩れない

実測（V003 zh/en）: 本文・語・表・文字は旧PoC bundleと**完全一致**、変わるのは
roleと画像名だけ。version+pageのfooterはen 35/35・zh 30/30で取りこぼし0。

## 実行

```sh
uv run pipeline/publish/regenerate.py                   # 一括再生成（bundles→evidence→index→checks）
uv run pipeline/publish/regenerate.py --full            # 全CSVの再生成（旧tool群をbundle入力で。約1.5時間）
uv run pipeline/publish/regenerate.py --verify --human  # ＋凍結パリティ・エラッタ・図・Markdown・差ゼロ検査
uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
uv run pipeline/ingest/convert_all.py --jobs 4          # catalogの67版。incremental
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

`baseline/tables.csv`は凍結時点の正本CSV（catalog 8・evidence 33・index 13、
manifest込み54ファイル）の行数とSHA-256。凍結後は、

- 旧`tools/`のPDF直読み19本は既存CSVを再現する参照実装として更新を止める
- 新toolは凍結CSVへ直接書かず、旧新比較（`unchanged / added / changed / missing`）を
  通ってからCSV単位で正本を切り替える（受入5条件は調査報告の項目7）
- 凍結後に旧側へ修正が要るときは、明示的に凍結を解除して台帳を取り直す
