# 公開面の方針

文書基準日: 2026-09-30。**方針は確定**（同日ユーザーが決めた。末尾「決めたこと」）。**実装も同日**
（`paths.PUBLISHED`・`build_index.py` の写し・`index/VERSION`・`check_tables.published_surface`・
`check_docs.check_stable_lists`）。残りは末尾「残り」。consumer 向けの約束の本文は
[index/README の「Contract for consumers」](../index/README.md#contract-for-consumers)（英語・日本語版あり）。

## 前提: ルールはあった。守られていなかった

consumer の契約は2026-08-25から決まっていた（`catalog/` の全表＋`index/`＋`evidence/` のうち「安定」印の
表）。起きていたのは、consumer がその外を読んでいたこと。正式な経路は **consumer が依頼 → この
リポジトリが保証・保守できる形に整えて公開 → consumer がそこへ移る**。consumer が evidence を直接
読んで先に済ませる道は無い。

2026-09-30 の実測（読んでいるのは3つ。pytest-cli・dev-oep・wireskein はどの表も読んでいない）:

| consumer | 取り方 | 契約の外 |
|---|---|---|
| wch-protocols | `index/` だけ。`index/manifest.csv` の sha256 で照合 | **なし**（手本になる読み方） |
| ch32rv | 兄弟 path を `cargo xtask db-gen` が読み、生成物を commit。lock なし（生成物の頭に rev だけ） | `evidence/device_ids`・`option_bytes`・`option_byte_fields`（R-34） |
| ArduinoCore-CH32 | lock（commit＋表ごとの sha256）。ただし bench の `regcheck.py` の分は lock の外 | `evidence/pins`・`pin_functions`・`register_blocks`・`register_fields`・`remap_fields`・`timers`・`errata`・`operating_conditions`（R-33） |

外に出た理由は、契約が**表の名前の列挙**だったこと。「安定」印は evidence の中に混ざっていて、path を
見ても契約の内か外か分からない。列挙も2つの README と `paths.STABLE_EVIDENCE` にあって、実際に
ずれた（`flash_program_method`。2026-09-30 に `check_docs` で固定した）。

## 原則

1. **公開面は `index/` の下で、その下は全部が契約**。個別の表を名前で指定しない。consumer は path の
   接頭辞だけで「契約の内か」を判定できる
2. **公開面に置くのは、このリポジトリが保証でき、保守し続けられる表だけ**。保証するのは次の4つで、
   **行の真偽ではない**（資料が誤っていれば行も誤る。そのかわり、そのことを confidence と basis で正直に言う）
   - 列の名前・意味・書式が固定されている（生成器の定数で決まり、`check_tables` の `column_drift` が見る）
   - 全行に `confidence`・`basis` がある（catalog の鍵表は列ごとの出所）
   - 不変条件が機械検査に載っている（結合・書式・数）
   - 原本が更新されたら `regenerate.py` で作り直せる（人手の表は `curated/` にあり、検査が見張っている）
3. **evidence をそのまま契約にしない**。資料の綴りを残す層なので、形が変わってよい層のままにする。
   公開する表は **`index/` へ写す**。行はそのまま、consumer に要らない内部の列だけを落とす
   （`check_tables.published_surface` が「元の表から名指しした列を落としただけ」を毎回見る）。写しの元の
   形を変えたら、それは公開面の変更になる
4. **consumer ごとの専用表は作らない**。欲しい列が既存の表にあればその表を公開し、無ければ抽出（evidence）を
   直してから公開する。専用表は consumer の数だけ保守が増える

## 形

`index/` を公開フォルダにした。契約を守っている唯一の consumer（wch-protocols）と `pins.html`、core の
`index/` 読みが何も変えずに済み、大きい表（`pinout` 3MB・`registers` 4MB）は二重にならない。写すのは
小さい表だけ（計約1.4MB）。index の性格は「導出」から「導出＋写し」に変わるが、**写しにも事実は足さない**
ので「索引に事実を足さない」は保てる。

| 種類 | 表 | 扱い |
|---|---|---|
| 導出（前からの index） | `parts`・`pinout`・`routes`・`registers`・`register_map`・`dma`・`timers`・`features`・`capabilities`・`conflicts`・`register_layouts`・`debug_interfaces` | そのまま |
| 写し: 目録の鍵 | `families`・`series`・`products`・`packages`・`cores` | `products` の packing の3列を落とす（102行が空。consumer に意味が無い） |
| 写し: 前の「安定」evidence 15表 | `interrupts`・`memory_map`・`systick`・`clock_*`（5表）・`evt_variants`・`clock_enables`・`pin_alternate`・`flash_geometry`・`flash_program_method`・`adc_internal`・`debug_data` | `clock_configs.evt_copies`（一致した EVT 写しの数。生成の記録）を落とす |
| 写し: 依頼で公開（R-33・R-34） | `device_ids`・`option_bytes`・`option_byte_fields`・`register_blocks`・`errata`・`operating_conditions` | `operating_conditions.datasheet` を落とす（`basis` にある） |
| 表の説明 | `manifest.csv`（path・行数・sha256。CSV と `VERSION` を覆う）・`VERSION`（整数1つ。いま `1`） | manifest は生成、VERSION は人が上げる |

写しの一覧と落とす列は `tools/paths.py` の `PUBLISHED` だけが持つ。表を公開面に足すのはそこに1行足すこと。

### 置かなかったもの

- `memory_configs` — 前は「安定」だったが外した。全行が `conflict`（EVT ヘッダと RM の `FLASH_OBR` の幅が
  食い違う）で信頼度 🟡、2026-09-30 にも F-77 で L103 の読みが動いた。読んでいる consumer も無い
- `device_id_addresses` — `device_ids.id_addr` で足りる
- `catalog/documents`・`sources`・`toolchains` — mirror の運用と生成の出所。consumer には commit と
  `manifest.csv` で足りる（mirror は今までどおり `manifests/documents.json` を読む）
- evidence の他の表 — index に正規化した形がある（下の対応表）か、まだ誰も依頼していない。依頼があれば
  上の原則で判定する

## 届いている依頼への答え

### index で足りる → consumer が読み先を移す

2026-09-30 に行で突き合わせた。

| 今読んでいる | 移る先 | 確かめたこと |
|---|---|---|
| `evidence/pins`（`pad`・`kind`） | `index/pinout` | pins の (型番, pad, kind) は**全行** pinout にある |
| `evidence/pin_functions`（`pad`・`signal`・`route`） | `index/pinout` | route の remap・default・af は同数。**違いが2つ**: `main` 行（pad 自身の GPIO 名）は `port`/`gpio` 列になった。`alias` 行（30行）は無く、括弧の別名から `port`/`gpio` を埋めている。core の「機能名で呼ばれる pad → port 名」は `port`/`gpio` で引ける見込みだが、core 側で確かめてもらう |
| `evidence/register_fields`（`register`・`field`・`kind`・`bits`） | `index/registers` | 同じ行が `(type, register)` に割って入っている（`ADC_CTLR3` → `ADC`＋`CTLR3`、`AFIO_EXTICR1` → `AFIO`＋`EXTICR1`）。`bits` の `hi:lo` も同じ |
| `evidence/remap_fields`（`selector`・`bits`） | `index/routes` | 287 selector が全部 routes にあり、`register`・`bits`（`REG:bit;REG:bit`）も同じ。`controller` 列は core の依頼で 2026-09-30 に routes へ足した（`remap_fields` から写しただけ。VERSION は 1 のまま） |
| `evidence/timers`（regcheck） | `index/timers` | index は evidence の上位（`channels`・`complementary` 付き） |
| `evidence/register_blocks`・`errata`・`operating_conditions`・`device_ids`・`option_bytes`・`option_byte_fields` | `index/` の同名の写し | 公開した（`operating_conditions` は `datasheet` 列が無い） |
| 前の「安定」evidence 表・`catalog/` の鍵表 | `index/` の同名の写し | 公開した（`products` は packing の列、`clock_configs` は `evt_copies` が無い） |

## core が挙げた論点への答え

- **置き場**: `index/` の下が全部。consumer は `TABLE_DIRS` の写しを持たず、`index/<表>.csv` だけを読む。
  `tools/paths.py` を consumer 向けに出す必要は無い
- **lock**: commit ＋ `index/manifest.csv` の sha256 を1つ（manifest に全ファイルの sha256 がある）。
  wch-protocols の読み方がこれ。core の regcheck 分も同じ lock に入る
- **列の書き方**: 表の README（index の表は `index/README`、写しは元の表の `catalog/README`・`evidence/README`）に
  ある。**列は名前で読む**——位置では読まない（ch32rv は今いくつかの表を位置で読んでいる）。約束するのは
  列の名前と意味で、並び順ではない。機械で読める列の説明（`columns.csv`）は「残り」
- **confidence**: 公開面の行は全部このリポジトリの答え。`conflict` は「資料が食い違い、basis の根拠で片方を
  採った」という印で、値は採用した値。使うか捨てるかは consumer が決める（ch32rv の flash は conflict で
  止まる。これは正しい使い方）。両論は `conflicts.csv` にある
- **family 名・schema の版**: `index/VERSION` を1つ持つ（表ごとではない）。**consumer を壊しうる変更**——
  列の削除・改名、列の書き方の変更、family などの鍵の改名——は先にこれを上げる。表・列・行を足すだけなら
  上げない。したがって family 名は VERSION 1 の間は凍結

## 守らせ方

- このリポジトリ（実装済み）: `check_tables.published_surface` が、写しが元と一致すること、`index/` に
  索引でも写しでもない CSV が無いこと、`VERSION` が正の整数であることを見る。manifest は `index/` の CSV と
  `VERSION` を全部覆う。`check_docs.check_stable_lists` が README の写しの一覧と `paths.PUBLISHED` の一致を見る。
  凍結台帳（`pipeline/baseline/tables.csv`）も写しを覆う
- consumer: 読む path が全部 `index/` で始まることを、consumer 自身の検査に入れてもらう（lock を
  manifest の sha256 にすれば自然にそうなる）。**公開前のデータが要るときは consumer 側に手持ちで置く**
  （ch32rv の `provisional/skus.csv` の形）。evidence を読んで代用しない

## 移る順

1. ~~ユーザーが決める~~（2026-09-30）
2. ~~このリポジトリ: 写しと `VERSION` を生成し、検査を足し、README を直す~~（2026-09-30）
3. consumer へ連絡: 公開の commit と、上の「index で足りる」対応表（commit の後）
4. consumer が読み先を移す。**猶予期間は evidence の旧 path も残る**（evidence は消さない。ただし契約ではない）
5. ~~移り終わったら `paths.STABLE_EVIDENCE` と `evidence/README` の「安定」印を消す~~（2026-10-01。ch32rv ed7a703・core は 5339df5 に固定して移行、wch-protocols は元から `index/` だけ）

## 決めたこと（ユーザー、2026-09-30）

1. 公開フォルダは `index/`
2. index の外の表は、**安定して出せるなら公開面に出す**。そのとき不要な列は落としてよい
   → 前の安定表から `memory_configs` を除いた15表、目録の鍵5表、依頼6表を写した（上の表）
3. `index/VERSION` を持つ。consumer を壊しうる変更はこれを上げてから
4. `confidence` の扱いは consumer に任せる

## 残り

- 機械で読める列の説明 `index/columns.csv`（表・列・意味・書式・空欄の意味）。いまは README の文章だけ
- ~~`routes.controller`~~（2026-09-30 に追加）・~~consumer への連絡~~（2026-09-30）
- ~~core の `alias` の確認~~（2026-09-30。pinout の `port`/`gpio` と全件一致。併せて OSC_IN/OSC_OUT の `port`/`gpio` を埋めた＝5339df5）
- ~~移り終わった後の「安定」印の撤去~~（2026-10-01）
