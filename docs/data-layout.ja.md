# データの区分・形式・置き場所の再定義（案）

作成: 2026-08-26。[table-roles.ja.md](table-roles.ja.md)（42表の役割定義と確認）を入力に、
**「どう管理するのがいいか」をゼロベースで**考え直したもの。利用者はいま1人（ArduinoCore-CH32
のgenerator＝自分）なので、破壊的な変更を前提にしている。判断が要る箇所は**推奨を1つ**に絞って
書いた。データはまだ動かしていない（移行手順は末尾）。

## 1. 前提にした事実（実測）

| 事実 | 数 | 意味 |
|---|---|---|
| GitHubのCSVビューアが表示しない表（512KB超） | `register_fields` 3.8MB・`pin_functions` 2.6MB・`pin_roles` 2.5MB・`remap_routes` 547KB | **利用者の入口である pin 系が、GitHub上では開けない** |
| 1型番あたりの行数 | `pin_roles` 平均235・最大1,186／`pin_functions` 最大1,291 | 型番で割れば1ファイル数百行＝GitHubで表として読める大きさ |
| family×peripheral型あたりの `register_fields` | 257組・平均129行・最大3,028 | 同上。ヘッダ生成の単位（D-3/D-4「peripheral型×family」）とも一致 |
| 行の `confidence`+`basis` がファイルに占める割合 | `registers` 46%・`pin_functions` 36%・`pin_roles` 32%・`register_fields` 24% | 出所列は重いが、正しさの根拠そのもの。証拠の表からは外せない |
| consumerが読んでいる表 | 16表（`vendor/ch32-device-data.lock.toml`。commit＋ファイルごとのsha256で固定） | **A（`pins`/`pin_functions`）を直接読んでいる**。Aの綴り・形を直すたびにconsumerが揺れる |
| 利用者の問い（worklist U1〜U5） | 「このピンは何」「要求を満たす型番は」「この機能はどのピンに出せる・remap値は」「メモリマップ・割込み・機械可読定義」「最新版は・いつ同期したか」 | 問いは**型番から始まる**（U1/U3/U4）か、**型番を探す**（U2）かの2種類 |
| 他の公開形 | 12 familyのmirror README（`generated/readme/`→各repo）、`pins.html`（`tables/*.csv`をfetch。Pagesの有効化は未確認） | 人向けの「表示」は表の外で作っている |
| 中間生成物 | `candidates/*.json` 6.2MB（型番ごと。判断過程の`_`キー付き。`build_pins`/`build_remap`/`build_tables`の入力） | 「正本」でも「索引」でもない。READMEは「tablesの原料」と説明 |

## 2. 区分のやり直し

### なぜ A/B/C では収まらなかったか

- **C「集約」が雑多だった**。中身は (i) 名前を決めて全表が参照する**鍵**（families/series/products/packages/cores/documents/sources）と、(ii) Aを畳んだ**導出**（products の flash/sram 列、register_layouts）で、性質が違う。(i) は資料の写しでも導出でもなく「repositoryが管理する名前」、(ii) は B と同じ「Aから機械生成できるもの」
- **README・html は表の区分ではない**。表から作る「表示」で、別の層
- **A に導出列が混ざる理由が定義されていなかった**。`remap_routes.peripheral`（語彙で導出）と `remap_fields.selector`（資料に名前が無いのでこちらが付けた識別子）は、どちらも「資料の綴りでない列」だが役割が違う。前者はBの仕事、後者はAが結合のために持つ鍵

### 新しい区分: 目録・証拠・索引（＋表示）

| 区分 | 答える問い | 1行 | 綴り | 読む人 | 変えてよいこと |
|---|---|---|---|---|---|
| **目録** `catalog/` | 何が存在し、何と呼ぶか | 1つの名前（family・series・型番・package・core・文書・mirror版） | repositoryが決めた名前。資料の表記は別列で持つ | 全表（鍵として参照） | 名前の追加・改名は**全表に波及**するので worklist に記録して行う |
| **証拠** `evidence/` | 資料は何と書いているか | 1資料（または両言語で照合した1組）の1つの記述 | **原典のまま**。型だけ揃える（数・hex・単位） | 正しさを確かめる人（保守者・監査） | 抽出の直し。資料どうしが食い違えば`conflict`で**両方残す**。**訂正はしない**（訂正は索引で） |
| **索引** `index/` | この型番／familyについて、いま知りたいことは何か | 用途で決まる（型番×lead×機能、family×型×register×field…） | 語彙で揃えた名前（`peripheral`/`role`/`port`/`pin`）。**元の綴りを隣に持つ** | 利用者（人・generator） | 語彙規則と用途の形。**証拠から機械生成できること**（`check`が「証拠に無い行が無い」ことを毎回見る） |
| （表示） `generated/`・`pins.html` | 読みやすく見せる | — | 索引に従う | 人 | 何でも。表ではないので検査対象は「索引と一致するか」だけ |

3つの区分は「**誰が作るか**」でも切れる: 目録は人が決める（＋カタログ同期）、証拠は抽出器が写す、索引は生成器が組む。

### 区分ごとの規則

**目録**
- 小さく保つ（7表）。`basis` は任意（repositoryの決定なので）。資料の表記との対応（`listed_as`・`label_zh`）は列で持つ
- 手で書くもの（`curated/`の core-facts・series-facts）と、WCHカタログから同期するもの（documents）がある。どちらも「名前の正本」

**証拠**
- 資料の綴り・値のまま。合成しない（構造体入れ子の平坦化名 `sTxMailBox[0].TXMIR` のような**こちらの記法は、元の名前を別列で残す**）
- **付与識別子は持ってよい**——資料が名前を付けていないもの（remap selector、動作条件の記号、比較表の属性）に repository が付けた鍵。条件: 資料の綴り（`field`・`parameter`・`label_zh/en`）が同じ行に残っていること。README の列一覧で「付与」と明示する
- **語彙で導出した列は持たない**（`peripheral`/`role`/`port`/`pin`、pin_roles から数えた `channels` など）。それは索引の仕事
- 資料が間違っていると判断しても**値は書き換えない**。もう1つの資料（RM格子など）を `basis` の `!source(=値)` で並べ、`conflict` にする。どちらを採るかは索引を作るときの規則（README に書く）
- 目録の鍵（`part_number`/`series`/`family`/`document`）だけは正規化した名前で持つ（結合のため）

**索引**
- 証拠から**だけ**作る。事実を足さない。証拠に無い行は検査で落とす（いまの `pin_roles` と同じ）
- **用途の単位でファイルを割る**——問いが型番から始まるなら型番ごと、familyの周辺なら family×型ごと。GitHub でそのまま表として開ける大きさ（数百行）になる
- 「どの型番が」を探す表（比較表・機能索引）は横断なので1ファイル
- `confidence` は必ず持つ（使った証拠行の最小）。`basis` は証拠行と1対1のとき写す。複数の証拠表を畳んだ横長の表（比較表）は `basis` を持たず、README で「この列は `evidence/○○` から」と書く
- 元の綴り（`signal`・`label`）を列で持ち、証拠へ戻れるようにする
- 資料側の訂正（F-41 のような「RMの格子を優先する」）は**ここで**適用し、その規則を README に書く

**索引を作る条件**（全部を索引に写すのではない）
1. 綴りが揺れる（datasheet の pin 表: `TX1`/`UTX`/`USART1_TX`）
2. 問いに答えるのに証拠表を2つ以上結ばないといけない（lead↔pad↔機能↔remap値、block base＋register offset）
3. 横断して探す（機能→型番）

EVT ヘッダから写した表（`interrupts`・`memory_map`・`clock_*`・`systick`・`evt_variants`・`clock_enables`・`pin_alternate`）は**名前が最初から機械の語彙**で結合も要らないので、索引に写さず**証拠のまま使ってよい**。README で「安定（そのまま読める）」と印を付ける。

### 決着する3つの✗（table-roles で見つけた定義違反）

| 表 | 新しい規則での扱い |
|---|---|
| `pin_functions` の12行（F-41 の訂正） | 証拠は datasheet の値に戻し `conflict`＋`!rm-grid(=値)`。索引（型番ごとの pinout）が RM 格子の値を採る。採る規則は `index/README` に |
| `register_fields.field`（define名の接頭辞を落とした） | 証拠に `define` 列（EVTの綴り）を足す。`field` は残す（読むための名前） |
| `dma_requests.request`（`*`・`_0/_1`・脚注を剥がした） | 証拠は資料の綴りに戻す。`peripheral`・`remap`・`note` の分解は索引 `families/<F>/dma.csv` へ |

## 3. 形式

| 区分 | 形式 | 理由 | 見送った案 |
|---|---|---|---|
| 目録 | CSV（1表1ファイル） | 小さい。手で直す。GitHub で読める | — |
| 証拠 | **CSV のまま**（1表1ファイル、`#` 列で data／出所を分ける規約も維持） | 1行＝1記述で diff が読める（抽出の変化を review する唯一の手段）。出所列が重いのは性質上仕方がなく、圧縮は git がする。表示できない大きさになるのは構わない（証拠は「読む」ものではなく「確かめる」もの） | SQLite（結合は楽だが diff が無くなり、変更ごとに全体が blob で積まる）／Parquet（同上）／JSONL（冗長で GitHub が描画しない）／YAML（ch32-data 方式。手書き向きで、10万行の生成物には不向き） |
| 索引 | **CSV、用途の単位で分割**（`index/parts/CH32V203C8T6.csv` のように） | GitHub でクリックして表として読める。diff がその型番に閉じる。generator は glob で全部読む。行＝1事実で JSON より形が崩れにくい | 型番ごとの JSON（generator には便利だが GitHub で読めず、入れ子が schema の揺れを招く。**8/25 に消した `devices/*.json` と同じ形に見える**——あれは手で書く正本、これは生成物、という違いはあるが、いま戻す理由が無い） |
| 表示 | Markdown（mirror README）・HTML（viewer） | 現状どおり | — |

CSV の規約（継続）: data 列は英語（CJK 検査）、`*_zh` 列だけ中国語可。`#` 列の左が data、右が出所。並びは決定的（生成は冪等）。

## 4. 置き場所と公開

```
catalog/     目録  families / series / products(識別だけ) / packages / cores / documents / sources
evidence/    証拠  いまの tables/ の大半（名前は変えない）
index/       索引  parts.csv, features.csv, register_layouts.csv,
                   parts/<PART>.csv, series/<SERIES>/routes.csv,
                   families/<FAMILY>/{map.csv, dma.csv, timers.csv, registers/<TYPE>.csv}
curated/     人手の入力（変更なし。errata・core-facts は「人が確認した証拠」、他は抽出規則）
generated/   表示（mirror README）。pins.html は index/ を読む
.cache/      中間生成物（RM の読み取り、candidates/）。commit しない
tools/ docs/
```

- **正本は GitHub のこの repository**。tag/release はまだ作らない（利用者1人。consumer は commit で固定している）。索引の列を変えたら worklist に記録し、`index/README` の列表を更新する
- **consumer の契約は `catalog/`＋`index/`＋「安定」印の `evidence/` 表**。証拠の他の表は形を変えてよい。lock は今のまま「commit＋読む表の sha256」で足りる。索引を型番ごとに割ると lock の行が増えるので、`index/manifest.csv`（ファイル・sha256・生成元 commit）を生成して**そのハッシュ1つ**を固定してもよい
- **`pins.html` は GitHub Pages で配る**（main の root、`.nojekyll` 付き。有効化は要確認）。索引が型番ごとに割れるので、viewer は `index/parts/<PART>.csv` を1つ fetch すればよくなる
- **mirror README は表示のまま**（各 family repo へ生成。「Edit there, not here」の注も維持）
- **`candidates/` は commit を止めて `.cache/candidates/`**。証拠の CSV が review 対象の抽出結果になったので、判断過程（`_selector_resolved_by` 等）を型番 JSON で二重に持つ理由が消えた。build_pins 等の入力としては残る（`build_all` が作る）。**注意**: `_unresolved_selector`（F-6）のような「決まらなかった」記録は worklist にあるが、消す前に一度 `candidates/_report.json` の内容が worklist に写っているか確認する
- 文書: `tables/README.ja.md`（約1,000行）を3つに割る——`catalog/README.ja.md`（鍵の定義）、`evidence/README.ja.md`（保守者向け。列の A/付与の区別、確定基準、basis 表記）、`index/README.md`＋`README.ja.md`（**利用者向け。英語も置く**——mirror README から辿ってくる人の入口になる）。`docs/table-reliability.ja.md` は証拠の表ごとの信頼度のまま

## 5. 42表の行き先

| いまの表 | 行き先 | 変えること |
|---|---|---|
| `families` `series` `packages` `cores` `documents` `sources` | `catalog/` | そのまま |
| `products` | `catalog/products.csv`（`part_number` `series` `family` `package` `datasheet` `listed_as`＋その basis）と `index/parts.csv`（下記） | 列ごとの `*_confidence/*_basis` 28列をやめる。仕様の列は索引へ |
| `pins` | `evidence/` | `EP`（露出パッドの lead）と `kind` は「付与」と README に印。`pad` は資料のまま |
| `pin_functions` | `evidence/` | F-41 の12行を資料の値に戻す（`conflict`）。`alias` 行はそのまま（資料の括弧書き） |
| `pin_roles` | **廃止** → `index/parts/<PART>.csv` | 型番ごとに分割し、`pins` の lead と `remap_routes` の selector/値を結んだ形にする |
| `pin_alternate` | `evidence/`（安定） | そのまま |
| `product_attributes` | `evidence/` | `attribute` は付与識別子として残す（`label_zh/en` が隣にある）。`#` 列を入れて列順の規約に合わせる |
| `feature_tags` | `index/features.csv` | 名前だけ |
| `features` `errata` `memory_configs` `adc_internal` `flash_geometry` `eval_boards` `evt_examples` `link_firmware` | `evidence/` | そのまま |
| `operating_conditions` | `evidence/` | `symbol` は付与識別子（`parameter` が隣）。README に印 |
| `remap_fields` | `evidence/` | `selector` は付与識別子。そのまま |
| `remap_routes` | `evidence/` | `peripheral`/`role` 列を外す（→ `index/series/<S>/routes.csv`） |
| `timers` | `evidence/` | `channels`/`complementary` を外す（→ `index/families/<F>/timers.csv`）。RM の `kind`/`counter_width_bits`/`update_vector`/`condition` は残す |
| `register_blocks` `registers` `register_fields` | `evidence/` | `register_fields` に `define` 列。`registers` の平坦化 `register` は残し、`member_path`（元の入れ子）を足す |
| `register_layouts` | `index/register_layouts.csv` | 導出（ハッシュ）なので索引。横断（family をまたいで同じ型か）なので1ファイル |
| `dma_requests` | `evidence/` | `request` を資料の綴りに戻す。`peripheral`/`remap`/`note` の分解は `index/families/<F>/dma.csv` へ |
| `opa_cmp_registers` `clock_enables` `usbpd_plumbing` | `evidence/`（`clock_enables` は安定） | `unit`（OPA/CMP の分類）は付与と印 |
| `interrupts` `memory_map` `systick` `clock_configs` `clock_prescalers` `clock_sources` `clock_symbols` `clock_init` `evt_variants` | `evidence/`（**安定**——そのまま読める） | そのまま。`clock_symbols.role` は付与と印 |

証拠 32表・目録 7表・索引 4種（＋型番/series/family ごとのファイル）。

## 6. 新しく作る索引の中身

**`index/parts.csv`**（U2: 型番を選ぶ）。1行＝1型番。
`part_number, series, family, package, pins, flash_bytes, sram_bytes, gpio_count, clock_max_hz, vdd_min, vdd_max, temperature, usart, spi, i2c, can, usb, adc_channels, timers_advanced, timers_general, opa, ..., #, confidence`
——`products` の仕様列と `product_attributes` の正規化値を横に並べたもの。列ごとの出所は README で「`evidence/product_attributes` の `attribute=○○`」と書く。

**`index/parts/<PART>.csv`**（U1/U3: この型番の足）。1行＝1（lead, 機能）。機能の無い lead（電源・NC・GPIO だけ）も1行持つので、**port＋pin→lead が1表で引ける**。
`pin, pad, port, gpio, kind, peripheral, role, signal, route, selector, value, af, #, confidence, basis`
- `pin` は lead 番号（`EP` 含む）、`pad` は資料の綴り（`PA0-WKUP`・`LO1`）、`port`/`gpio` は語彙で取った `A`/`0`（`alias` からも埋める）
- `route` は `main`/`default`/`remap-N`/`af-N`、`selector`/`value` は `remap_routes` から結んだ AFIO の鍵と値、`af` は `pin_alternate` の AF 番号
- `signal` は資料の綴り（証拠へ戻る手がかり）
- 訂正規則（RM 格子と datasheet の route 番号が食い違えば RM 格子）はここで適用

**`index/series/<SERIES>/routes.csv`**（U3: remap 値を選ぶ）。1行＝1（selector, 値, 信号）。
`selector, register, bits, value, peripheral, role, signal, pad, port, gpio, #, confidence, basis`
——`remap_fields`×`remap_routes` を結び、語彙で `peripheral`/`role` を付けたもの（いまの `remap_routes` の B 列が移る）。

**`index/families/<FAMILY>/registers/<TYPE>.csv`**（U4: ヘッダ生成）。1行＝1（register, field）。
`register, offset, width_bits, count, field, define, bits, mask, value, description, access, reset, #, confidence, basis`
**`index/families/<FAMILY>/map.csv`**: 1行＝1（block, register）で**絶対番地**を持つ（`block, type, register, address, width_bits, #, confidence`）——「register の絶対アドレスを1表で」に答える。
**`index/families/<FAMILY>/dma.csv`**: `dma, channel, request_id, peripheral, direction, request, remap, condition, note, #, confidence, basis`。
**`index/families/<FAMILY>/timers.csv`**: `timer, kind, counter_width_bits, channels, complementary, update_vector, condition, #, confidence`（`channels` は `parts/*.csv` から数える）。

**`index/features.csv`**: いまの `feature_tags` のまま。**`index/register_layouts.csv`**: いまのまま。

## 7. 検査（`check_tables`）

- 目録: 鍵の一意性、全表からの参照が結合できること（いまと同じ）
- 証拠: 列順の規約（`#`）、CJK、`confidence` の語、既知の穴の数・名前（いまと同じ）。**「付与」列は README の列表と一致していること**（README を機械可読にするなら `evidence/columns.csv` を生成して見る）
- 索引: **証拠に無い行が無い**（いまの pin_roles 検査を全索引に広げる）、語彙で覆えない綴り 0、型番ごとのファイル数＝`catalog/products` の行数、`index/manifest.csv` の sha256 が一致
- 表示: mirror README・`pins.html` が索引の列名だけを参照していること（grep）

## 8. 移行手順（順番と規模）

consumer は commit を固定しているので、途中の状態で壊れることはない。移行が終わってから lock を進める。

1. **ディレクトリを作って移す**（`tables/*.csv` → `catalog/`・`evidence/`。`pin_roles.csv` は消える）。git の操作はユーザー
2. **tools のパス**——35本が `tables` を参照（`build_readme` 13箇所、`build_pins`/`build_operating` 4箇所、他は1〜2箇所）。`tools/paths.py` に `CATALOG`/`EVIDENCE`/`INDEX` を置いて全部そこから引く
3. **証拠の直し**（小さい）: `pin_functions` F-41 の戻し、`register_fields.define`、`registers.member_path`、`dma_requests.request` の戻し、`remap_routes`/`timers` の B 列外し、`product_attributes` の `#` 列
4. **索引の生成器**（新規4本）: `build_index_parts.py`（`parts.csv`＋`parts/<PART>.csv`。`build_pin_roles` の語彙処理を引き継ぐ）、`build_index_routes.py`、`build_index_registers.py`（`registers/<TYPE>`・`map`・`dma`・`timers`）、`build_index_manifest.py`
5. **検査**の拡張（7章）、`build_readme`・`pins.html` を索引の列名へ
6. **文書**: README 3分割、`docs/` と README.md/README.ja.md のパス（`tables/` 参照は docs 12ファイル・workflows 3箇所）、glossary の区分の定義、`table-roles.ja.md` はこの文書に吸収して削除
7. **candidates を `.cache/` へ**（`_report.json` の未解決一覧が worklist にあることを確認してから）
8. consumer 側（ArduinoCore-CH32）: lock のパスを `index/`・`catalog/`・安定な `evidence/` に付け替え、`pin_roles` 読みを `parts/*.csv` に。これは別 repository の作業

規模の目安: 1〜3 は機械的（半日）、4〜5 が本体（1日）、6〜8 は追従（半日）。生成の一式（RM 全読みを含む）は今と同じ時間。

## 9. この案で決めたこと（推奨）と、決めていないこと

決めたこと（反対がなければこの通り進める）:
- 区分は**目録・証拠・索引**の3つ＋表示。A/B/C の呼び名はやめる
- 証拠は CSV のまま、訂正を入れない。付与識別子は可、語彙導出列は不可
- 索引は CSV を**用途の単位で分割**。consumer の契約は目録＋索引＋「安定」印の証拠
- `tables/` は `catalog/`・`evidence/` に改名（`tables` は3区分になった時点で何も言っていない名前）
- `candidates/` は commit しない
- `index/README` は英語も置く

決めていないこと:
- GitHub Pages が有効か（`gh` が無く確認できなかった。設定画面で見る）
- consumer の lock を manifest 1ハッシュにするか、ファイル列挙のままか（consumer 側の都合。どちらでも索引側は同じ）
