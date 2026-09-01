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
extract/   pdfcompat.py（bundle互換層＋原本hashの入口ゲート。PDFへのsilent fallbackなし）
           datasheet/run_operating.py（凍結ロジックをbundle入力で走らせる。
           evidence/operating_conditions.csv の1,588行を**byte一致**で再現——2026-09-01実測）
reconcile/ compare_csv.py（凍結CSVとcandidateの unchanged/added/changed/missing）。zh/en照合は今後
checks/    compare_manifest.py（環境差の検証）。fixture回帰は今後
review/    （予定）検査・annotation・人間向け表示
publish/   （予定）candidate → 承認済み正本
```

candidateの置き場は`.cache/pipeline-candidates/`（非コミット）。凍結CSVへ直接書く
toolはこの経路に無い。

## ingestがPoCと違う点（D17が特定した2欠陥の修正）

1. **決定性**: pdfminerがinline imageへ付ける`id()`由来の数字名を捨てる
   （converter自身の`p66-draw-image-00002`形式が識別子）。同一原本＋同一版なら
   bundleはbyte一致で再生成できる
2. **header/footerの検出が反復ベース**: 全ページを先に1回歩き、上下12%の帯で
   「数字を`#`に畳んだ同じ綴りが**ページの縁から同じ距離**に、全ページの25%以上
   （最低3ページ）繰り返す」行を拾う。y閾値だけのPoCはzh版footer（下端比93.8%）を
   系統的に取りこぼした。反復判定はheading判定より先（TOC等の小フォントページで
   footerがheadingに化ける実測があったため）。縁距離なので横向きページにも効く

実測（V003 zh/en）: 本文・語・表・文字は旧PoC bundleと**完全一致**、変わるのは
roleと画像名だけ。version+pageのfooterはen 35/35・zh 30/30で取りこぼし0。

## 実行

```sh
uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
uv run pipeline/ingest/convert_all.py --jobs 4          # catalogの67版。incremental
uv run tools/check_document_bundle.py .cache/structured-bundles/<stem>.<lang> \
  --source <PDF>                                        # 独立検証ゲート
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
