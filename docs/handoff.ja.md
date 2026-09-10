# 作業引継ぎ

文書基準日: 2026-08-25（棚卸し）。**2026-08-17版の引継ぎ（JSON schema草案の時代）は
この版で置き換えた。** 当時の内容のうち生きているもの（一次資料の矛盾）は
[worklist.ja.md の「資料側の問題台帳」](worklist.ja.md#資料側の問題台帳原典の誤り記録のみ)へ移した。
2026-09-04: 「判断の指針」「PDF構造化（D18）の作業規約」「原本が更新されたとき」を追加。
これまで作業機ごとのAIエージェントのメモリに散っていた約束事を、**人もエージェントも
最初に読むこの文書**へ集めた（作業は複数マシンで行うので、機械ローカルには置かない）。

## セッションの始めに1回だけ（必須）

```
uv run pipeline/checks/check_sources.py --remote
```

**入力が三者でずれる**ので、始めた時点の状態を確定させる。①目録の版
（`catalog/documents.csv`。GitHub Actionsがcommitするので**このリポジトリのpull**が要る）、
②原本の実体（mirrorのPDF。**各mirrorのpull**が要る）、③変換済みの記録
（`structured/*/manifest.json`）。数秒で、読み取りだけ。

この検査は**④`.cache`のbundleが③と一致しているか**も見る（`cache_drift`）。正本CSVは
`.cache/structured-bundles`から作られ、その出自が③にcommitされるので、この2つは常に一致して
いなければならない。**片方だけ戻すと据え置きが黙って破れる**（下の節）。`regenerate.py`も
走る前にここで止まる。

- 「未取得のcommit」が出たら**ユーザーにpullを頼む**（順序は**このリポジトリ → 該当mirror**。
  mirrorは目録を読んで原本を落とすので、機械の順序と同じ向きで追う）
- 「原本が動いています」が出たら、それは**資料更新の取り込み待ち**。コード変更の作業に
  入る前に、取り込むのか後回しにするのかを決める（混ぜない。下の節）。後回しにするなら
  `regenerate.py --hold-sources`で**据え置いて**走る（動いた文書だけ再変換しない）
- **mirrorが目録に追いついていない間は変換しない**（`tools/check_mirrors.py`が
  「目録が割り当てたのにmirrorに無い」を報告する）。変換しても次のmirror更新で作り直しになる

入力を数時間おきに追いかけるのは`tools/pull_inputs.py`（**人が回す**。cron/timerから）。
再生成中は`.cache/regenerate.lock`を見て跳ばし、このリポジトリは作業ツリーがcleanな
ときだけpullする。**禁止ではなく排他**——数時間おきのpullそのものは良いことで、困るのは
全再生成（約12分）の途中で入ることだけ。

## いまの正本は `catalog/`・`evidence/`・`index/`

このrepositoryの成果物は **`catalog/`（目録8表）・`evidence/`（証拠40表）・`index/`（索引13表）と、そこから生成する各family
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

**先に照合する**（セッション開始時の必須手順と同じもの）:
`uv run pipeline/checks/check_sources.py` が、目録が割り当てた全文書に
ついて「mirrorのPDFのSHA」と「コミット済み`structured/<文書>/manifest.json`の原本SHA」を
比べる（読み取りだけ・ネットワーク不要）。動いている文書があれば名指しで出る。
`regenerate.py`は**走行の前と後**にこれを回す——前は高価な工程の前に止まり
（資料更新の取り込みなら`--accept-sources`）、後は**走行中にpullされた**ことを検出して
「この出力はどの入力状態にも対応しない」と言って落ちる。

**資料更新の再生成と、コード変更の再生成を混ぜない**（別commitにする）。混ぜると
**CSVが動いたのがコードのせいか資料のせいか区別できなくなる**——2026-09-08にこれで
誤診した: CH32X315のen版1.1→1.2がpullされた状態で`check_baseline`が赤くなり、最初
「自分の変更の回帰」と読んだが、実際は目録の自動更新が凍結台帳を書き直していないため
だった（別に本物の回帰も1件あったので、切り分けが要った）。順序は
「①コード変更を凍結した原本で検証してcommit → ②`--accept-sources`で資料更新を
取り込んでcommit」。

**作業の途中で原本が動いたとき**（mirrorのpullは数時間おきに入る。2026-09-09に
`CH32X035DS0.zh`がそれで、converter 1.15.0の検証中だった）: `regenerate.py --hold-sources`
で走る。動いた文書を**据え置き**（`convert_all.py --skip <文書>`。そのbundleは前の原本のまま）、
他の文書だけ再変換するので、出力は「コード変更＋前の入力状態」に対応する。コードをcommit
してから、`--accept-sources`で資料更新を**別のcommit**に取り込む。据え置いた文書の
`manifest.json`は動かないので、`check_sources`は取り込むまで同じ1件を出し続ける（それが正しい）。
このリポジトリ自身のpullは`pull_inputs.py`が作業ツリーdirtyで跳ばしている——commitして
cleanになれば次の周期で入る。
**据え置きは入口ゲートにも伝わる**（`pipeline/common/held_sources.py`。`regenerate.py`が環境変数
`CH32_HOLD_SOURCES`に置き、`pdfcompat.open`はその文書だけsha照合を省き、`render_assets`は描画を
跳ばす）。伝えないとゲートが据え置き文書を**黙って落とし**、`build_all`がfamilyごと目録から消す
（2026-09-09の走行2: families 12→11、`check_tables`の参照不整合147件で停止、正本46ファイルをHEADから
戻した）。ゲートは3経路（`pdfcompat.open`・`extract_low_power.bundle_tables`・`render_assets`）で、
`build_sources`も据え置きfamilyの行を前のまま保つ。据え置きを新しく読む経路（原本shaを比較する箇所）を
足すときは`held_sources.is_held`を通すこと。

**再生成中はpullしない**——`regenerate.py`は`.cache/regenerate.lock`を置き、
`tools/pull_inputs.py`はそれを見て跳ばす。守れなくても走行の後段照合が
「この出力はどの入力状態にも対応しない」と言って落ちるので、黙って混ざることはない。

**目録の自動更新は台帳も同じcommitに含める**（`update.yml`が`check_baseline --record`を
呼ぶ）。`catalog/documents.csv`は人が触らずに変わる唯一の表なので、台帳を置いていくと
**自分が作った変更で次のCIが赤くなる**。常時赤い検査は読まれなくなる。

1. **mirrorの`git pull`はユーザーが行う。** 上流との差は読み取りだけで分かる
   （`git -C /home/mt/dev_wch/<FAMILY> ls-remote origin HEAD` と `git log -1`）。「PDFが追加された」と
   聞いたら、まずローカルに本当に新しいファイルがあるか（`find … -mtime -3`、bundleの
   `manifest.json`のsha256との照合）を見る。無ければ上流にだけあるので、pullを頼む
2. `uv run pipeline/ingest/convert_all.py` — 増分変換（原本SHAとtool版が一致する文書は跳ばす。
   RM 600ページで約4分）
3. `uv run tools/build_sources.py` — 読んだmirrorのcommitを `catalog/sources.csv` に記録
4. `uv run pipeline/publish/regenerate.py --full --verify --human` — 原本更新時の正規手順
   （**約12分**。bundle→全CSV→索引→検査→エラッタ増分→図・Markdown・PDFとの差ゼロ検査。
   2026-09-10に原本直読みが無くなって1時間強から縮んだ）。
   エージェントのシェルは10分で切れるので `nohup setsid … > log 2>&1 &` で切り離し、ログの
   `=== [段] `／`FAILED`／`全段成功`／`Traceback` を監視する。**実行中は`pipeline/`を編集しない**
   （各段が読む）
5. 終わったら `git status` を**全体で**見て変わった表を確認し、commit対象（`structured/<文書>/manifest.json` を含む）
   を報告する。**走行を途中で止めた/結果を捨てたときは、正本CSVだけでなく `generated/` の派生物も戻す**
   （2026-09-08: 壊れた `--full` の README を戻し忘れ、そのままコミットされた）。
   **`.cache/structured-bundles/<文書>` も戻す**——tracked fileだけ戻すと`.cache`のbundleが新原本のまま
   残り、次の`--hold-sources`が「旧原本で据え置いている」と信じながら**新原本を読む**
   （2026-09-09。`convert_all --skip`は`.cache`を触らず、`pdfcompat`は据え置き文書のsha照合を省くため）。
   `check_sources`が`cache_drift`で報告し、`regenerate.py`は走る前に止まる。取り込み側へ揃えるなら
   `uv run pipeline/ingest/convert_all.py --force --only <文書>`。
   `pipeline/ingest/convert.py` の `CONVERTER_VERSION` を上げたときも同じ流れ
   （全bundleが増分再変換される。VSCodeの再起動で中断しても文書単位で原子的なので再開できる）

## 守ること

- **git の書き込み操作（add/commit/push/pull/checkout/stash/reset）はしない。** mirrorも含めて
  すべてユーザーが行う。読むだけ（`git show/log/status/diff/ls-remote`）は可。作業の最後に
  「どのリポジトリで何をcommitすべきか」を列挙する
- Pythonは **`uv run`** で動かす（`python3` 直はNG。構文確認の `python3 -c "import ast…"` だけは例外）
- **既知の穴を埋めるほうが新規より優先。** 選択肢を出すときは推奨を1つに絞って示し、決めた理由と
  「どう見ればいいか」を同じ変更でREADMEに書く。穴を埋める前に、その穴で検査が実際に落ちることを
  確かめる（壊して確認）
- **直すのは根に近い層で。** 同じ欠陥を「表示側で覆う」か「根で直す」かを選べるときは**根**を採る
  （converter＞結合層＞exporter）。根で直せばCSVにも効き、表示側の特例が増えない。**その結果
  凍結台帳（`pipeline/baseline/tables.csv`）のhashが動くのは良い方向の変化**——byte一致は
  「意図しない変化を検出する仕掛け」であって、意図した改善を止める枷ではない。台帳は同じ
  commitで更新し、何がなぜ動いたかをcommitとworklistに書く（ユーザー方針、2026-09-06）
- **崩しそうになったら撤退。** 出力を良くする変換は自律的に進めてよいが、崩れる兆候があれば戻す。
  戻した項目は [markdown-qa-log.ja.md](markdown-qa-log.ja.md) の撤退リストに履歴と再挑戦の条件つきで残す
- **抽出ロジックを移すときは出力の byte 一致を保つ。** 2026-09-10 に凍結toolは全部退役し、
  `run_patched`/`run_frozen`/`pdfcompat`（互換層）は消えた。移植は「新経路へ写す → byte 一致を
  実測 → 切替 → 旧を削除」の順で、**一致を確かめずに切り替えない**。正本CSVを綺麗にする修正は
  結合層（例: `pipeline/extract/datasheet/build_operating_conditions.py`）に置く
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
- **conflict を減らすガードは、落ちる件を1件ずつ原文で裁定してから入れる。** 偽の食い違い（対応付けの
  失敗）と本物の食い違い（資料が違うことを言っている）は、データの形では区別が付かない。
  2026-09-09 に「conflict は min/typ/max のどれかが一致すること」を測ったところ、誤照合1件と一緒に
  **CH32X035 の `I_DD`（zh 560µA 対 en 290/480µA）という本物の改定**も消えたので入れなかった。
  絞るなら**適用範囲**（ピン群・条件欄の有無）のように「別の行のことだ」と言える軸で絞る。
  誤照合が1件残るほうが、本物を黙って隠すよりよい——conflict は目に付く
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
