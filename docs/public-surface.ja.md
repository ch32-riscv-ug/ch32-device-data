# 公開面の方針（案）

文書基準日: 2026-09-30。**案**——ユーザーの判断待ちの項目は末尾の「決めること」に集めた。
決まったら、この文書を方針として確定し、`index/README`・`evidence/README`・`data-layout.ja.md` を合わせる。

## 前提: ルールはある。守られていないだけ

consumer の契約は2026-08-25から決まっている（`index/README` の「Contract for consumers」:
`catalog/` の全表＋`index/`＋`evidence/` のうち「安定」印の表）。起きているのは、consumer がその外を
読んでいること。ルールの穴ではない。正式な経路は **consumer が依頼 → このリポジトリが保証・保守できる
形に整えて公開 → consumer がそこへ移る**。consumer が evidence を直接読んで先に済ませる道は無い。

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

1. **公開面は1つのフォルダで、その下は全部が契約**。個別の表を名前で指定しない。consumer は path の
   接頭辞だけで「契約の内か」を判定できる（lock も検査も1行で書ける）
2. **公開面に置くのは、このリポジトリが保証でき、保守し続けられる表だけ**。保証するのは次の4つで、
   **行の真偽ではない**（資料が誤っていれば行も誤る。そのかわり、そのことを confidence と basis で正直に言う）
   - 列の名前・意味・書式が固定されている（生成器の定数で決まり、`check_tables` の `column_drift` が見る）
   - 全行に `confidence`・`basis` がある（catalog の鍵表は列ごとの出所）
   - 不変条件が機械検査に載っている（結合・書式・数）
   - 原本が更新されたら `regenerate.py` で作り直せる（人手の表は `curated/` にあり、検査が見張っている）
3. **evidence をそのまま契約にしない**。資料の綴りを残す層なので、形が変わってよい層のままにする。
   公開してよい表は**公開フォルダへ写す**（byte 一致の写し。写しの一致は検査する）。写しの元の形を
   変えたら、それは公開面の変更になる
4. **consumer ごとの専用表は作らない**。欲しい列が既存の表にあればその表を公開し、無ければ抽出（evidence）を
   直してから公開する。専用表は consumer の数だけ保守が増える

## 形: `index/` を公開フォルダにする（推奨）

**`index/` の下を全部、公開面にする**。今ある index 表はそのまま置き、`catalog/` の鍵表と、公開してよい
evidence の表を `index/` へ写す。

- **推奨する理由**: 契約を守っている唯一の consumer（wch-protocols）と `pins.html`、core の `index/` 読みが
  何も変えずに済む。大きい表（`pinout` 3MB・`registers` 4MB）は既に index にあるので、写すのは小さい表だけ
  （計約1.4MB）。名前も衝突しない（写す表の名前はどれも index に無い）
- 次点は新しい `public/` を作って index も写す案。フォルダ名は分かりやすいが、index の 9.4MB が二重になり、
  wch-protocols・pins.html・core の index 読みも付け替えが要る
- index の性格は「導出」から「導出＋写し」に変わる。**写しにも事実は足さない**（byte 一致）ので、
  「索引に事実を足さない」は保てる

### 置くもの

| 種類 | 表 | 扱い |
|---|---|---|
| 導出（今の index） | `parts`・`pinout`・`routes`・`registers`・`register_map`・`dma`・`timers`・`features`・`capabilities`・`conflicts`・`debug_interfaces` | そのまま |
| 写し: 目録の鍵 | `families`・`series`・`products`・`packages`・`cores` | `catalog/` から写す |
| 写し: 今の「安定」evidence 16表 | `interrupts`・`memory_map`・`systick`・`clock_*`（5表）・`evt_variants`・`clock_enables`・`pin_alternate`・`memory_configs`・`flash_geometry`・`flash_program_method`・`adc_internal`・`debug_data` | 写す。今の約束を引き継ぐ（core と ch32rv が読んでいる） |
| 写し: 依頼で新たに公開（下の節） | `device_ids`・`option_bytes`・`option_byte_fields`・`register_blocks`・`errata`・`operating_conditions` | 写す（ユーザー判断） |
| 表の説明 | `manifest.csv`（今のまま: path・行数・sha256）・**`columns.csv`（新設: 表・列・意味・書式・空欄の意味）**・**`VERSION`（新設）** | 生成する |

### 置かないもの

- `register_layouts` — 同じ型かどうかを言うハッシュで、header の版で値が変わる。生成の途中の道具なので
  evidence 側へ移す（読んでいる consumer はいない）
- `catalog/documents`・`sources`・`toolchains` — mirror の運用と生成の出所。consumer には `manifest.csv` と
  commit で足りる（mirror は今までどおり `manifests/documents.json` を読む）
- evidence の他の表 — index に正規化した形がある（下の対応表）か、まだ誰も依頼していない。依頼があれば判定する

## 届いている依頼への答え

### index で足りる → consumer が読み先を移す（新しい公開は無し）

2026-09-30 に行で突き合わせた。

| 今読んでいる | 移る先 | 確かめたこと |
|---|---|---|
| `evidence/pins`（`pad`・`kind`） | `index/pinout` | pins の (型番, pad, kind) は**全行** pinout にある |
| `evidence/pin_functions`（`pad`・`signal`・`route`） | `index/pinout` | route の remap・default・af は同数。**違いが2つ**: `main` 行（pad 自身の GPIO 名）は `port`/`gpio` 列になった。`alias` 行（30行）は無く、括弧の別名から `port`/`gpio` を埋めている。core の「機能名で呼ばれる pad → port 名」は `port`/`gpio` で引ける見込みだが、core 側で確かめてもらう |
| `evidence/register_fields`（`register`・`field`・`kind`・`bits`） | `index/registers` | 同じ行が `(type, register)` に割って入っている（`ADC_CTLR3` → `ADC`＋`CTLR3`、`AFIO_EXTICR1` → `AFIO`＋`EXTICR1`）。`bits` の `hi:lo` も同じ |
| `evidence/remap_fields`（`selector`・`bits`） | `index/routes` | 287 selector が全部 routes にあり、`register`・`bits`（`REG:bit;REG:bit`）も同じ。**`controller` 列だけ routes に無い**——core が使うなら routes へ写す（索引の列を足すだけで事実は足さない） |
| `evidence/timers`（regcheck） | `index/timers` | index は evidence の上位（`channels`・`complementary` 付き） |

### index に無い → 公開面に写す候補（R-33・R-34）

| 表 | 依頼 | 信頼度（table-reliability） | 判断案 |
|---|---|---|---|
| `device_ids` | ch32rv | ✅ reference 72・型番が products に実在・id_addr の一致を検査 | 写す |
| `option_bytes` | ch32rv | ✅ confirmed 98・base が OB block と一致 | 写す |
| `option_byte_fields` | ch32rv | ✅ confirmed 101 / conflict 3 | 写す |
| `register_blocks` | core（block の base） | ✅ confirmed 548 / ref 128 | 写す（`register_map` から番地−offset で出せるが、consumer に計算させない） |
| `errata` | core（id の存在確認） | ✅ 人が確認した表（`curated/`）、資料の引用が空振りすると落ちる | 写す。**id は改名しない**ことを約束に入れる |
| `operating_conditions` | core（`F_HSI`・`F_LSI`・`f_ADC`） | ✅ 3,939行・`symbol` はこのリポジトリが付けた鍵 | 写す（表ごと）。`condition` は資料の文のままで、書式を約束しない列と `columns.csv` に書く |

## core が挙げた論点への答え（案）

- **置き場**: `index/` の下が全部。consumer は `TABLE_DIRS` の写しを持たず、`index/<表>.csv` だけを読む。
  `tools/paths.py` を consumer 向けに出す必要は無くなる
- **lock**: commit ＋ `index/manifest.csv` の sha256 を1つ（manifest に全表の sha256 がある）。wch-protocols の
  読み方がこれ。core の regcheck 分も同じ lock に入る
- **列の書き方**: `index/columns.csv` に表・列ごとに書く（意味・書式・空欄の意味）。対象は
  `REG:bit;REG:bit`・`hi:lo`・`;` の並び・`route` の語彙・pad の装飾など。**列は名前で読む**——位置では
  読まない（ch32rv は今いくつかの表を位置で読んでいる）。約束するのは列の名前と意味で、並び順ではない
- **confidence**: 公開面の行は全部このリポジトリの答え。`conflict` は「資料が食い違い、basis の根拠で片方を
  採った」という印で、値は採用した値。使うか捨てるかは consumer の安全要求で決める（ch32rv の flash は
  conflict で止まる。これは正しい使い方）。両論は `conflicts.csv` にある
- **family 名・schema の版**: `VERSION` を1つ持つ（表ごとではない）。**同じ major の間は、列の削除・改名・
  書式の変更・family 名と鍵の改名をしない**。列や行を足すのは minor。consumer は major で互換を判定する

## 守らせ方

- このリポジトリ: `index/` の写しが元と byte 一致すること、`columns.csv` が全表・全列を覆うこと、
  `manifest.csv` が `index/` の全ファイルを覆うことを `check_tables` に載せる。`evidence/README` の
  「consumer はこれらを直接読んでよく」は「`index/` の写しを読む」に直す
- consumer: 読む path が全部 `index/` で始まることを、consumer 自身の検査に入れてもらう（lock を
  manifest の sha256 にすれば自然にそうなる）。**公開前のデータが要るときは consumer 側に手持ちで置く**
  （ch32rv の `provisional/skus.csv` の形）。evidence を読んで代用しない

## 移る順

1. ユーザーが「決めること」を決める
2. このリポジトリ: 写しと `columns.csv`・`VERSION` を生成し、検査を足し、README を直す（1 commit）
3. consumer へ連絡: 公開の commit と、上の「index で足りる」対応表
4. consumer が読み先を移す。**猶予期間は evidence の旧 path も残す**（evidence は消さないので自然に残る。
   ただし契約ではない）
5. 移り終わったら、`evidence/README` から「安定」印を外す（契約は `index/` だけになる）

## 決めること（ユーザー）

1. 公開フォルダ: **`index/` を公開フォルダにする**（推奨）か、新しい `public/` を作るか
2. 公開面に写す表: 今の安定16表をそのまま引き継ぐか（推奨）。**依頼6表**（`device_ids`・`option_bytes`・
   `option_byte_fields`・`register_blocks`・`errata`・`operating_conditions`）を写すか
3. 版: `VERSION` を1つ持ち、上の規則で major／minor を分けるか。**v1 で family 名を凍結する**か
4. confidence の扱い: consumer に任せる（推奨）か、このリポジトリが「conflict を除け」と規則にするか
