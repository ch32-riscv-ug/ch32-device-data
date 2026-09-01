# 作業引継ぎ

文書基準日: 2026-08-25（棚卸し）。**2026-08-17版の引継ぎ（JSON schema草案の時代）は
この版で置き換えた。** 当時の内容のうち生きているもの（一次資料の矛盾）は
[worklist.ja.md の「資料側の問題台帳」](worklist.ja.md#資料側の問題台帳原典の誤り記録のみ)へ移した。

## いまの正本は `catalog/`・`evidence/`・`index/`

このrepositoryの成果物は **`catalog/`（目録8表）・`evidence/`（証拠33表）・`index/`（索引13表）と、そこから生成する各family
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
```

全生成は `evidence/README.ja.md` の「生成」どおり（`build_all` → `build_tables` →
`build_pins` → `build_remap` → … → `build_index` → `build_readme`）。出力先は `tools/paths.py` が決める。
`build_all` は2並列で約13〜17分。**mirrorの`git pull`は`build_all`に入れていない**
（作業中に入力が変わるのを避ける）。読んだ版は `catalog/sources.csv` に残る。

## 守ること

- **git の書き込み操作（add/commit/push/stash/reset）はしない。** mirrorも含めて
  すべてユーザーが行う。読むだけ（`git show/log/status/diff`）は可
- Pythonは **`uv run`** で動かす（`python3` 直はNG）
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
