# 作業引継ぎ

文書基準日: 2026-08-25（棚卸し）。**2026-08-17版の引継ぎ（JSON schema草案の時代）は
この版で置き換えた。** 当時の内容のうち生きているもの（一次資料の矛盾）は
[worklist.ja.md の「資料側の問題台帳」](worklist.ja.md#資料側の問題台帳原典の誤り記録のみ)へ移した。
2026-09-04: 「判断の指針」「PDF構造化（D18）の作業規約」「原本が更新されたとき」を追加。
これまで作業機ごとのAIエージェントのメモリに散っていた約束事を、**人もエージェントも
最初に読むこの文書**へ集めた（作業は複数マシンで行うので、機械ローカルには置かない）。

## いまの正本は `catalog/`・`evidence/`・`index/`

このrepositoryの成果物は **`catalog/`（目録8表）・`evidence/`（証拠38表）・`index/`（索引13表）と、そこから生成する各family
リポジトリのREADME**。一次資料（datasheet zh/en・reference manual・EVT）を
`/home/mt/dev_wch/<FAMILY>/` のmirrorから機械抽出し、出所を`basis`、確度を
`confidence`に残す。

| 知りたいこと | 読む場所 |
|---|---|
| 表の意味・列・生成順 | [evidence/README.ja.md](../evidence/README.ja.md) |
| 表ごとの信頼度と既知の穴 | [table-reliability.ja.md](table-reliability.ja.md) |
| 生きている作業と次にやる順 | [worklist.ja.md](worklist.ja.md) |
| 解決済みの記録（なぜそう作ったか） | [worklist-archive.ja.md](worklist-archive.ja.md) |
| 用語 | [glossary.ja.md](glossary.ja.md) |
| 抽出できる範囲の実測（設計の根拠） | [extraction-survey.ja.md](extraction-survey.ja.md) |
| PDF→構造化bundle→Markdown/CSVの経路と各段の挙動 | [pipeline/README.ja.md](../pipeline/README.ja.md) |
| Markdown出力のQA記録（直したこと・撤退したこと・検証結果） | [markdown-qa-log.ja.md](markdown-qa-log.ja.md) |
| どのPDFがどのmirrorのものか | `catalog/documents.csv`（mirrorの`update.sh`が読む公開形は `manifests/documents.json`） |

JSON schema草案（`schemas/`・`devices/`・`tools/validate.py`・`docs/schema-notes.ja.md`、2026-08-17）は
2026-08-25に**削除した**。記録は git の履歴にある。

## 再開手順

```sh
cd /home/mt/dev_wch/ch32-device-data
git status --short                      # 未commitの変更（commitはユーザーが行う）
uv run tools/check_tables.py            # 全表の参照結合・書式・索引⊆証拠・manifest
uv run tools/check_counts.py            # 比較表の数 vs pin側の数
uv run tools/check_docs.py              # 文書が書いている行数・穴の状態 vs 実際の表と台帳
node tools/check_viewer.js              # pins.html の表示（node が要る唯一の検査）
uv run pipeline/publish/regenerate.py   # 新経路の一括再生成（bundle→切替済みevidence→index→検査）
```

全生成は `evidence/README.ja.md` の「生成」どおり（`build_all` → `build_tables` →
`build_pins` → `build_remap` → … → `build_index` → `build_readme`）。出力先は `tools/paths.py` が決める。
`build_all` は2並列で約13〜17分。**mirrorの`git pull`は`build_all`に入れていない**
（作業中に入力が変わるのを避ける）。読んだ版は `catalog/sources.csv` に残る。

### 原本（mirror）にPDFが追加・更新されたとき

1. **mirrorの`git pull`はユーザーが行う。** 上流との差は読み取りだけで分かる
   （`git -C /home/mt/dev_wch/<FAMILY> ls-remote origin HEAD` と `git log -1`）。「PDFが追加された」と
   聞いたら、まずローカルに本当に新しいファイルがあるか（`find … -mtime -3`、bundleの
   `manifest.json`のsha256との照合）を見る。無ければ上流にだけあるので、pullを頼む
2. `uv run pipeline/ingest/convert_all.py` — 増分変換（原本SHAとtool版が一致する文書は跳ばす。
   RM 600ページで約4分）
3. `uv run tools/build_sources.py` — 読んだmirrorのcommitを `catalog/sources.csv` に記録
4. `uv run pipeline/publish/regenerate.py --full --verify --human` — 原本更新時の正規手順（1時間強。
   bundle→全CSV→索引→検査→凍結toolのparity→図・Markdown・PDFとの差ゼロ検査）。
   エージェントのシェルは10分で切れるので `nohup setsid … > log 2>&1 &` で切り離し、ログの
   `=== [段] `／`FAILED`／`全段成功`／`Traceback` を監視する。**実行中は`pipeline/`を編集しない**
   （各段が読む）
5. 終わったら `git status` で変わった表を確認し、commit対象（`structured/<文書>/manifest.json` を含む）
   を報告する。`pipeline/ingest/convert.py` の `CONVERTER_VERSION` を上げたときも同じ流れ
   （全bundleが増分再変換される。VSCodeの再起動で中断しても文書単位で原子的なので再開できる）

## 守ること

- **git の書き込み操作（add/commit/push/pull/checkout/stash/reset）はしない。** mirrorも含めて
  すべてユーザーが行う。読むだけ（`git show/log/status/diff/ls-remote`）は可。作業の最後に
  「どのリポジトリで何をcommitすべきか」を列挙する
- Pythonは **`uv run`** で動かす（`python3` 直はNG。構文確認の `python3 -c "import ast…"` だけは例外）
- **既知の穴を埋めるほうが新規より優先。** 選択肢を出すときは推奨を1つに絞って示し、決めた理由と
  「どう見ればいいか」を同じ変更でREADMEに書く。穴を埋める前に、その穴で検査が実際に落ちることを
  確かめる（壊して確認）
- **崩しそうになったら撤退。** 出力を良くする変換は自律的に進めてよいが、崩れる兆候があれば戻す。
  戻した項目は [markdown-qa-log.ja.md](markdown-qa-log.ja.md) の撤退リストに履歴と再挑戦の条件つきで残す
- **凍結tool（`tools/build_*.py` をbundle入力で走らせる `run_patched`）の出力はbyte一致を保つ。**
  正本CSVを綺麗にする修正は結合層（例: `pipeline/extract/datasheet/build_operating_conditions.py`）に置き、
  凍結ロジックには触れない
- **公開する情報（表の全列・生成 README・各ディレクトリの README）に日本語を入れない。** 表は `basis` 列も含めて英語、中国語は `*_zh` 列と `path` だけ（`check_tables` が全列を見て落とす）。README は英語版（`README.md`）を必ず置き、日本語版（`.ja.md`）は併記。`docs/` の作業文書だけが日本語
- **索引（`index/`）に事実を足さない。** 直すのは語彙か抽出（証拠 `evidence/`）。
  証拠の綴りは資料どおりに残し、訂正しない（食い違いは `conflict`）。区分の定義は
  [data-layout.ja.md](data-layout.ja.md)
- 資料どうしが食い違ったら**片方に寄せず`conflict`＋両論を`basis`に**。
  RMが書いていない値を推測で埋めない
- 穴は**名前と数で固定**する（`KNOWN_ROLE_GAPS`・`KNOWN_SHARED_LEADS`・`check_counts.KNOWN`・
  `build_capabilities.KNOWN_DOUBLED`）。増減はどちらも検査で落とす
- **文書に書いた数と状態も生成物と合わせる**（`check_docs.py`）。データを直したら、それを説明して
  いる文章も同じ commit で直す。数の綴りを変えたときは `check_docs.py` の `ROW_COUNTS`／`PROSE`
  も直す（当たらなくなったら失敗する）
- 旧Arduino core・EVT tree・公式PDFをこのrepositoryへコピーしない。
  `ch32_riscv_tools/PinAlternateFunctions`の手製表を根拠にしない
- 生成物に「Arduinoコアの対応状況」を載せない（上流の状態は陳腐化する）

## 判断の指針

- **zh版とen版が食い違ったら、経験上zh版が正しいことが多い**（en版は翻訳で、値や単位の写し間違いが
  入りやすい。例: CH32V407 t_WUSTDBYのus/ms、H417のstop電流3件）。ただしzh版だけが誤る例もある
  （表7-13の類）ので、**データだけでzh側を自動採用する規則にはしない**。conflict行は両論を`basis`に
  残し、「zh寄り」は人がreviewするときの事前確率、あるいはWCHへの報告文の書き出しにだけ使う
- 判断の委任: 実装の細部は任されている（「ある程度自分で判断してどんどん進めて」）。CSVごとの受入儀式は
  最小にし、まず「新経路が従来データ以上を取れる」状態まで進め、その後カバレッジを100%へ近づける

## PDF構造化（D18・`pipeline/`）の作業規約

- **最終ゴールは、人が読むMarkdownがPDFと差がなくなること。** CSV抽出はその上に載る消費者の1つ。
  bundle（`.cache/structured-bundles`）は再生成物でcommitしない。commitするのは
  `structured/<文書>/manifest.json`（原本SHA・ページSHA・変換器版）と `review.json`（人の判断）
- **既知の取りこぼしは隠さず、出力の中で見えるようにする**（図の占位、vector図の警告、`(cid:N)`化けの
  警告、表issuesの警告、「Table continued」のポインタ）
- **parity検査（`pipeline/checks/check_markdown_parity.py`）は正しさの番人ではない。** bundleの各行・各セルが
  Markdownに**同じ順で存在する**かしか見ず、exporterと同じ変換関数を共有するので、変換が間違って
  いても一致する。実際に見逃した例: 過剰除去（`SWIER22`→`SWIE22`）、行番号の付帯情報
  （`_folded_rows`・`row_pages`）を繰り上げ忘れて実データ行が消えた、空`<td>`省略の列ずれ、
  ページ跨ぎ結合表で表題の続き行が本文からも表題からも消えた
- したがって **export側の変換を変えたら、必ず意味検証を対にする**: 除去・変更の多いページ上位を抽出し、
  サブエージェント（sonnet/opus）に原文（説明表・zh/en対・PDF）と突き合わせさせる。最も収穫が大きいのは
  **PDFページを直接読ませて生成Markdownと突合**する形（CSVに効く欠陥も見つかる）
- geometryで重複グリフを落とすときは「グリフ中心がセル外」だけを根拠にしない。**別のセルが≥50%の面積で
  そのグリフを所有し、そのセルのtextにもその文字が行端にある**ことまで確かめる（狭い列で名前が
  あふれる`SWIER22`・`INTEN1`の教訓）。行を増減する変換は、行番号を持つ付帯情報を必ず一緒に更新する
- QAの回し方: 切り口（層化・ランダム・連続ページ・表構造・図・レジスタ・PDF直接突合）とモデルを変えながら
  サブエージェントを回し、新しい指摘が出なくなるまで続ける。直したこと・撤退したこと・検証結果は
  [markdown-qa-log.ja.md](markdown-qa-log.ja.md) に必ず記録する
