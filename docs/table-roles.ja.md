# テーブルの役割の定義と、データがそれに沿っているかの確認

作成: 2026-08-26。**確認だけ**で、データは変えていない。「正しさ（証拠）の表」と
「利用者が引くための表」を区別し、42表それぞれに役割を定義して、いまのデータが
その定義どおりかを見た。どちらの向きに寄せるかの判断はこの文書ではしない。

## 役割の3区分

| 区分 | 役割 | 綴り・値の規則 | 変えてよいこと |
|---|---|---|---|
| **A 証拠**（層1） | 原典に何が書いてあるかを、行ごとに出所と確度を付けて写す。**正しさの根拠** | 原典の綴りのまま。値の型だけ揃える（数は数、番地はhex） | 抽出の直し。原典どうしが食い違えば`conflict`＋両論。**原典に無いものを足さない** |
| **B 索引**（層2） | 利用者が「USART1のTXはどのpad」「PA0はどの足」のように**引く**ための表。Aを言い換えただけで新しい事実を足さない | 語彙規則で揃えた名前（`peripheral`/`role`/`port`/`pin`）。Aへ戻る手がかり（元の綴り）を持つ | 語彙規則の直し。Aから機械生成できること（`check_tables`が「Aに無い行が無い」ことを見る） |
| **C 集約**（表の表） | 型番・seriesの単位でAを畳んだもの、原典ではなくrepository自身の状態 | 列ごとに確度と根拠 | Aとの往復が検査できること |

**A と B の両方の列を1つの表に持つ「混在」**がいくつかある。混在自体は悪ではない
（Aの綴りを残したまま隣にBの読みを置けば、両方の用途を1表で満たす）が、**どの列が
どちらか**が定義されていないと、利用者は「この列は資料どおりか」を判断できない。

## 表ごとの定義と確認

凡例: ✓ 定義どおり ／ △ 定義どおりだが注意点あり ／ ✗ 定義から外れている箇所がある

### pin系（利用者の入口。検索性が最も問われる）

| 表 | 区分 | 1行 | 引くときのキー | 綴り | 確認 |
|---|---|---|---|---|---|
| `pins` | **A** | (型番, lead, pad) | 型番＋lead番号 → pad | `pad`は資料の綴り（`PA0-WKUP`・`VDD_VIO_1`・`LO1`）。lead番号は脚注を剥がした数、露出パッドは`0`→`EP`、`kind`は型欄からの分類 | △ `EP`と`kind`は**こちらの記法**（資料は`0`と`P`/`I/O`）。値は失っていないが「資料のまま」ではない列がAの中にある。padの綴りが版で違う同じ足（V203の`VDD_IO_1`／V205DS0の`VDD_VIO_1`）は**引き側で吸収されていない**（Bの表が無い） |
| `pin_functions` | **A**（一部✗） | (型番, pad, signal, route) | 型番＋pad → 機能 | `signal`は資料の綴り（`TX1`/`UTX`/`USART1_TX`が混在）。`route`は資料の列 | ✗ **12行で資料の値を書き換えている**（F-41: V103 TIM3の`remap-1`をRM格子の値に。`conflict`＋`basis`に元の値は残る）。**`alias`（30行）は資料の括弧書きの写しでAの範囲**。`route`空242行は資料に経路番号が無い行 |
| `pin_roles` | **B** | (型番, peripheral, role, pad, routing) | peripheral＋role → pad／port＋pin → pad | `peripheral`/`role`は語彙で揃えた名前。`signal`に元の綴りを保持 | ✓ `check_tables`が「pin_functionsに無い行が無い」「語彙で覆えない綴りが0」を毎回検査。**pin_functionsの4,247行を載せない**（pad自身のGPIO名3,609・電源の主機能607・`alias`30・`NC`1。実測）のは定義どおり。`port`/`pin`は`alias`からも埋める（B内の導出） |
| `pin_alternate` | **A** | (family, pad) | pad → AFレジスタ | EVTの名前 | ✓ |

**pin系での検索性の穴（確認できた事実）**:
- 「型番XのPA0はどの足か」を1表で引けない。`pins.pad`は`PA0-WKUP`や`LO1`と綴られ、`port`/`pin`は`pin_roles`にしか無い（しかも`pin_roles`はGPIO名の行を載せない）。**GPIO名→leadは`pins`と`pin_roles`の結合が要る**
- 「この足はリセット直後に何をしているか」は`route=main`と`default`の両方を見る必要があり（資料の書き方がfamilyで割れる）、Bの表はそれを畳んでいない

### 型番・カタログ系

| 表 | 区分 | 1行 | 綴り | 確認 |
|---|---|---|---|---|
| `products` | **C**（列ごとに根拠） | 型番 | 値は正規化（`flash_bytes`はバイト数。比較表の`480K`から） | ✓ 列ごとの`*_basis`に両言語の出所。**零等待領域を`flash_bytes`とする規約**は資料の見出しではなくこちらの定義（READMEに明記） |
| `product_attributes` | **混在（A＋B）** | (型番, 属性) | `label`/`label_zh`/`label_en`＝資料の見出し（A）、`attribute`＝正規化キー（B）、`value`＝正規化値（`128KB`等） | △ AとBが同居しているが列で分かれている。`#`列が無い（列順の規約から外れる） |
| `series` / `families` / `packages` / `cores` | **C** | series等 | 正規化 | △ `families`は`#`も確度も無い（repositoryの構成情報）。`packages.pin_count`等は列ごと確度 |
| `documents` / `sources` / `eval_boards` / `evt_variants` / `evt_examples` | **A**（EVT・目録） | 文書／mirror／board／macro／例題 | 目録の綴り | △ `documents`は`#`も確度も無い（カタログ由来。版番号の遅れF-33は記録済み） |
| `features` | **A** | (series, 節) | 節見出しの原文（両言語） | ✓ |
| `feature_tags` | **B** | (tag, series) | 正規化タグ。`features`（原文）を保持 | ✓ AとBが**別表に分かれている好例**（`precision`列で粒度も明示） |
| `errata` | **A**（curated） | 事項 | 人手 | ✓ |
| `memory_configs` | **A** | (型番, 符号) | RMの符号。列にEVT/RM両論 | ✓ 全行conflictは意図した記録 |

### 電気・動作条件

| 表 | 区分 | 綴り | 確認 |
|---|---|---|---|
| `operating_conditions` | **混在** | `symbol`は**こちらで揃えた記号**（`F_HCLK`・`ACC_HSI`。資料は`F HCLK`や添字の分断）、`parameter`/`condition`は原文（F-36で添字を戻した） | △ `symbol`がBの役割を兼ねる（seriesを横断して同じ量を引くための鍵）。資料の綴りは`parameter`に残る |
| `adc_internal` | **A** | 数値は単位を揃えた（mV・uV/℃） | ✓ 単位の揃えはAの「型を揃える」範囲 |
| `flash_geometry` | **A** | 数値 | ✓ |

### remap系

| 表 | 区分 | 綴り | 確認 |
|---|---|---|---|
| `remap_fields` | **A** | `field`は**出所ごとの綴り**（`*_RM`はRM、`*_REMAP`はEVT）、`selector`はこちらのID | △ `selector`（`afio-tim3-remap`）はB的な鍵。`field`の綴りが出所で揺れるのはA定義どおりだが、引く側は`canonical_field`で畳む必要がある（README記載） |
| `remap_routes` | **混在** | `signal`/`pad`は資料の綴り（A）、`peripheral`/`role`は語彙（B。4,918/4,919で埋まる） | ✓ 列で分かれている。`pin_roles`と同じ語彙 |

### レジスタ系（R-20）

| 表 | 区分 | 綴り | 確認 |
|---|---|---|---|
| `register_blocks` | **A** | header の define 名（`USART1`）・型名 | ✓ `layout`はB的な鍵（ハッシュ）だが列で分かれている |
| `registers` | **A** | 構造体メンバー名。入れ子は`sTxMailBox[0].TXMIR`という**こちらの記法**で平坦化 | △ 平坦化名は資料に無い綴り（構造からの導出。READMEに書いてある） |
| `register_fields` | **A**（一部✗） | `register`はbannerの綴り、`field`は**define名から`RCC_`/`AFIO_PCFR1_`の接頭辞を落とした名前** | ✗ **元のdefine名を列で持っていない**。`RCC_USART1EN`→`USART1EN`は`type_`+`field`で戻せるが、`AFIO_PCFR1_TIM1_REMAP`→`TIM1_REMAP`は`register_`+`field`で、**どちらを落としたかが行に無い**。EVTの綴りへ確実に戻れないのはAとして穴 |
| `register_layouts` | **B/C** | ハッシュ | ✓ 導出（定義どおり「同じか違うか」だけ） |
| `dma_requests` | **混在（一部✗）** | `request`は「資料の綴り」と書いたが、**`*`印・`_0`/`_1`接尾辞・脚注番号を落としている**（60行）。落とした情報は`remap`/`note`に移してある | ✗ 値は失っていないが、**`request`列は資料の綴りそのままではない**。`peripheral`はB |
| `opa_cmp_registers` / `clock_enables` / `usbpd_plumbing` | **A** | EVTのdefine名・RMの綴り | ✓ `unit`（OPA/CMP）は説明文の多数決で決めたこちらの分類（READMEに明記） |
| `timers` | **混在** | `kind`/`counter_width_bits`はRM（A）、`channels`/`complementary`は**`pin_roles`から数えた導出**（B）、`update_vector`は`interrupts`から | △ 1表にAと導出が同居。`basis`はRMだけを言っていて、導出列の出所（pin_roles）が行に無い |

### EVTからの写し

| 表 | 区分 | 確認 |
|---|---|---|
| `interrupts` / `memory_map` / `systick` / `clock_*`（5表） | **A** | ✓ EVTの名前のまま。`clock_init`の`step`順もEVTの順。`clock_symbols.role`はこちらの分類（列で分かれている） |
| `link_firmware` | **A** | △ 版番号が未確定（F-11） |

## 確認結果のまとめ

**定義から外れている箇所（✗）は3つ**。いずれも「値は失っていないが、Aの表なのに資料の綴り・値そのままでない」:

1. `pin_functions` の12行——RM格子で**資料の値を訂正**している（F-41）。`conflict`と`basis`で元の値は追えるが、「Aは写す」の例外
2. `register_fields.field`——define名の接頭辞を落とし、**元のdefine名に確実に戻れない**
3. `dma_requests.request`——`*`・`_0/_1`・脚注を`remap`/`note`へ移し、**列の名前が言う「資料の綴り」ではない**

**混在（A＋B）は5表**（`product_attributes`・`operating_conditions`・`remap_routes`・`timers`・`dma_requests`）。列で分かれているものと（`remap_routes`）、行の`basis`が導出列を説明していないもの（`timers`）がある。

**Bの表は実質3つ**（`pin_roles`・`feature_tags`・`register_layouts`）。利用者が引く鍵として足りているかを見ると:

| 引きたいこと | いま辿る経路 | 1表で引けるか |
|---|---|---|
| peripheral＋role → pad | `pin_roles` | ✓ |
| port＋pin → lead番号 | `pin_roles`（port/pin）→`pins`（pad→lead）。GPIO名の行は`pin_roles`に無いので**padで結合** | ✗ 2表 |
| lead番号 → その足の全機能 | `pins`→`pin_functions`（pad）→`pin_roles`（言い換え） | ✗ 3表 |
| 型番 → 機能の有無 | `feature_tags`（series粒度）＋`product_attributes`（型番粒度） | △ 粒度が違う2表 |
| 機能の同義語（`UTX`/`TX1`/`USART1_TX`） | `pin_roles.signal`→`role` | ✓ |
| register の絶対アドレス | `register_blocks`＋`registers`（type で結合） | ✗ 2表 |
| bit field → register → block | `register_fields`（`member`が空の行は結べない） | △ |

## 次に決めること（この文書では決めない）

- Aの表に「資料の値の訂正」を入れ続けるか（F-41方式）、Aは写すだけにして訂正はBで行うか
- `register_fields`に元のdefine名の列を足すか（Aの穴を塞ぐ。列追加だけ）
- `dma_requests.request`を資料の綴りに戻して（`USART1_TX_1`・`TIM1_UP*`）、揃えた名前を別列にするか
- pin系のBを増やすか——例: 型番×lead×pad×port×pin×kindを1表にした「lead索引」、または`pins`に`port`/`pin`列を足す
- 混在表は「どの列がA/Bか」を`tables/README`の各節に書くだけで済ませるか、表を割るか
