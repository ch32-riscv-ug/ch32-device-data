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
           datasheet/extract_low_power.py（A11: 消費電流・ウェイクアップ時間のcandidate。
           caption選定＋断片結合＋表番号スコープの2段階zh/en照合。1,208行・偽conflict 0）
reconcile/ compare_csv.py（凍結CSVとcandidateの unchanged/added/changed/missing）。zh/en照合は今後
review/    render_assets.py（**図のpixel描画**。原本hashを照合してから、図領域を
           150dpiのPNGに描いて`assets.json`（領域bbox・PNGのSHA-256）と置く。
           図領域は文字ではなく**graphicsの縦クラスタ**で決める——図中のラベルは
           paragraph行として写るので文字を境界にすると領域が潰れる。67文書で
           3,307 asset・図caption 2,884のうち**2,837に実画像（98.4%）**。
           本文の参照文（「图19-2是…」等）はcaption扱いしない——判定は
           `pipeline/common/figure_captions.py`に一本化）
           export_markdown.py（人が読むMarkdown。**最終ゴール「PDFとの差ゼロ」の本体**。
           header/footerはコメント化、表はrowspan/colspan保持のHTML、
           **ページを跨ぐ表はL1で結合して開始ページに全体を描き、続きページには
           可視ポインタ**（67文書で3,759表を結合）、
           **既知の取りこぼしはその場所に見える印**——図caption直後の警告＋原本
           ページへのリンク、大きい画像の占位、表issuesの警告、(cid:N)化けの警告）
checks/    compare_manifest.py（環境差の検証）
           check_markdown_parity.py（bundle→Markdownで本文行・表セルが読み順どおり
           全部現れること＋取りこぼしの印があることの機械検査。**67文書全合格**）
publish/   （予定）candidate → 承認済み正本
```

candidateの置き場は`.cache/pipeline-candidates/`（非コミット）。凍結CSVへ直接書く
toolはこの経路に無い。

## ingestがPoCと違う点（3つの修正。1と2はD17の実測、3はCIの実戦検出）

1. **決定性**: pdfminerがinline imageへ付ける`id()`由来の数字名を捨てる
   （converter自身の`p66-draw-image-00002`形式が識別子）。同一原本＋同一版なら
   bundleはbyte一致で再生成できる
2. **header/footerの検出が反復ベース**: 全ページを先に1回歩き、上下12%の帯で
   「数字を`#`に畳んだ同じ綴りが**ページの縁から同じ距離**に、全ページの25%以上
   （最低3ページ）繰り返す」行を拾う。y閾値だけのPoCはzh版footer（下端比93.8%）を
   系統的に取りこぼした。反復判定はheading判定より先（TOC等の小フォントページで
   footerがheadingに化ける実測があったため）。縁距離なので横向きページにも効く

3. **manifestのgeometry_sha256は非圧縮のJSONに対するhash**（converter 1.1.0）。
   gzipの圧縮バイト列はzlibの版で変わり、GitHub Actions上の再変換が
   geometry_sha256だけ全ページ不一致になった（2026-09-01、`structured-repro.yml`が
   **設計どおり環境差を検出**した初の実戦）。圧縮は保存の都合であって内容ではない

実測（V003 zh/en）: 本文・語・表・文字は旧PoC bundleと**完全一致**、変わるのは
roleと画像名だけ。version+pageのfooterはen 35/35・zh 30/30で取りこぼし0。

## 実行

```sh
uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
uv run pipeline/ingest/convert_all.py --jobs 4          # catalogの67版。incremental
uv run pipeline/checks/check_bundle.py .cache/structured-bundles/<stem>.<lang> \
  --source <PDF>                                        # 独立検証ゲート（1.1.0以降）
```

`convert_all`は`structured/`のmanifestと原本SHA-256・engine版・converter版が
全部同じ文書を跳ばす（`--force`で全変換）。engineは`uv.lock`が固定する
pdfplumber。環境差（別マシン・CI）の検証は`.github/workflows/structured-repro.yml`。

## baseline凍結

`baseline/tables.csv`は凍結時点の正本CSV（catalog 8・evidence 33・index 13、
manifest込み54ファイル）の行数とSHA-256。凍結後は、

- 旧`tools/`のPDF直読み19本は既存CSVを再現する参照実装として更新を止める
- 新toolは凍結CSVへ直接書かず、旧新比較（`unchanged / added / changed / missing`）を
  通ってからCSV単位で正本を切り替える（受入5条件は調査報告の項目7）
- 凍結後に旧側へ修正が要るときは、明示的に凍結を解除して台帳を取り直す
