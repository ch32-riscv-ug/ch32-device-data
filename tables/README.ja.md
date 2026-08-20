# 正規化テーブル

`tools/build_tables.py` が生成します。用語（ファミリー/シリーズ/確度…）の定義は [docs/glossary.ja.md](../docs/glossary.ja.md) にあります。**上から下に降りる階層**で、すべての値が「何を根拠にしているか」（`*_basis`列）を持ちます。

```
families.csv        12行   ファミリー一覧（mirror repository = 文書の単位）
  └ series.csv        27行   シリーズ（die）。core・ISA・共通スペック
      └ products.csv    103行   注文型番
          └ pins.csv          注文型番ごとのlead↔pad対応（キー: part_number）
          └ pin_functions.csv 注文型番ごとのpad→signal/route（キー: part_number）

マスタ表（各表から名前で参照される）
  packages.csv    25行  package。寸法・pitch・lead数
  cores.csv       13行  QingKe core。ISAとcore manualへの参照
  documents.csv   76行  文書カタログ。**両言語のページURL・DL URL・mirror URL**

付属表
  product_attributes.csv  995行  比較表の全属性（縦持ち。列に昇格していない残り全部）
  remap_fields.csv        262行  route selector定義（series×field: register/bit/reset/valid値）
  remap_routes.csv       4380行  selector値→(signal, pad)。pin_functionsのremap-Nを解決する
  errata.csv               21行  ロット依存の挙動・ハードウェア注意事項（curated/errata.csvから）
  operating_conditions.csv 76行  クロック（系統主頻F_MAIN・上限F_*）と動作電圧V_DD
  evt_examples.csv       1593行  EVT同梱の例題一覧（周辺グループ→例題→説明）
```

結合キーの対応（`tools/check_tables.py` が全参照の結合可能性を機械検査します）:

```
series.family / products.family / packages.families   → families.family
products.series                                        → series.series
products.package                                       → packages.package
series.core / families.cores                           → cores.core
pins.part_number / pin_functions.part_number           → products.part_number
product_attributes.part_number                          → products.part_number
remap_fields.series                                     → series.series
remap_routes.(series, selector)                         → remap_fields
errata.series / operating_conditions.series             → series.series
evt_examples.family                                     → families.family
*.datasheet(s) / families.reference_manuals・evt / cores.manual → documents.document
```

pins系は`tools/build_pins.py`、remap系は`tools/build_remap.py`、operating_conditions.csvは`tools/build_operating.py`、それ以外は`tools/build_tables.py`が生成します。

## 各ファイル

### `families.csv` — 最上位

1行1ファミリー。どのシリーズを含み、どのdatasheet・reference manual・EVTが該当するか。文書の対応は日次同期している`manifests/documents.json`から取ります。全体像はまずここを見ます。

### `series.csv`

1行1シリーズ（CH32V006, CH32V203, …）。core・ISAと、配下の全packageが共有する値だけを持ちます。packageで変わる値は`varies-by-package`として空になり、products.csvへ降ります。**シリーズとdatasheetは1対1ではありません**（CH32V203CCT6はCH32V205DS0に掲載）。

### `products.csv`

1行1注文型番。flash・GPIO数・温度など製品固有の値だけを持ち、**寸法系はpackage名でpackages.csvを参照**します。`listed_as`は比較表での略記（`CH32V208CB`→`CH32V208CBU6`、ワイルドカード`C6x6`→C6T6/C6U6）。

### `packages.csv`

1行1package名の**マスタ表**。body size・pin pitch・lead数はpackageの属性なのでここに正規化し、productsには持たせません。根拠は全productのordering表記載の集約＋PACKAGE.PDF（封装寸法図面、`WCH-common`にmirror）の両言語目次＋package名の数字です。同名packageが複数ファミリーで違う寸法を主張すればconflictとして現れます（現在0件）。QFN26C3とQSOP24のlead数のみreference（pin定義表と不一致=抽出行落ちの疑い、`?pin-table`）。

### `pins.csv` / `pin_functions.csv`

**注文型番単位**です。pins.csvは1行1(part_number, pin, pad)で「この型番のlead Nにどのpadが載るか」、pin_functions.csvは1行1(part_number, pad, signal, route)で「この型番のpadが持つ機能」。datasheetのpin表は1つのpinoutを複数型番で共有します（表題が適用範囲を宣言: `CH32V103x8x6`、`CH32V006（除F4U6以外）`、`TSSOP20(F8)`）が、その解決は生成時に済ませてあり、**行はpart_numberでそのままproducts.csvと結合できます**。共有していた事実はメタ側のdatasheet/table列（出典）に残ります。

`route`の値: `main`（リセット後の主機能）/ `default`（既定の代替機能）/ `remap-N`（remap値N）/ `af-N`（H41x・X315系のalternate function番号）/ 空（経路番号が資料になく要確認）。

両言語照合で吸収している表記ずれ: 表番号のずれ（X315はzh`表2-1-1`=en`Table 2-1`。表題中のシリーズ名で照合）、列見出しの綴り（`QFN48×7`、`QFN28(6)`、zh`LQFP64M`=en画像`LQFP64`は表内の消去法でペアリング）、1列が複数packageを兼ねる見出し（`LQFP48/QFN48X7`は成分ごとに登録）。

### `product_attributes.csv`

比較表の**全属性を縦持ち**で保持します（列に昇格済みのflash/sram/pin数/GPIO/温度/packageは除く）。両言語はラベルの語が違う（`定时器`↔`Timer`）ため、**正規化した値の並びのLCSで行を対応付け**ます——翻訳は表の行順を保つので、同値同順は同じ行です。対応付いて値が違う行はconflictになります（例: CH32H417WEU6のOPA数はzh=1/en=2で本物の食い違い）。`label_zh`/`label_en`に原文ラベルを残しています。

### `remap_fields.csv` / `remap_routes.csv`

AFIO route selectorの定義と、値→経路の対応です。pin_functions.csvの`remap-N`は、remap_routes（selector×値→signal/pad）→remap_fields（どのregisterの何bitか）と辿って解決します。出所はcandidates/（EVTヘッダ+RM register表+RM remap格子+datasheet pin表の結合）ですが、**根拠ごとの一致記録がファイルに残っていないため全行reference**です。EVTとRMの突き合わせを記録付きで再実行して確定へ昇格するのが次の課題です。H41x/X315系はremapではなくAF番号方式なので対象外（pin_functionsの`af-N`が持つ）。

読み方に注意が要る列が3つあります。

**`bits`はbitごとにregister名を持ちます**——`PCFR1:2;PCFR2:19;PCFR2:20`のように、値のLSBから順に`<register>:<bit>`を`;`で並べます。ほとんどのselectorは1つのregisterに収まりますが、CH32L103 / CH32M103 / CH32V20x / CH32V30x / CH32V4x7では**selectorがPCFR1とPCFR2にまたがります**。PCFR1だけを書くとエラーにならずに別の経路が選ばれるので、上位半分を落とさないための修飾です。`register`列は同じことを`PCFR1|PCFR2`と要約します。

**`peripheral`/`role`は`signal`を正規化した読みです**。`signal`は原典の表記のまま残してあり、同じ役割が資料により`USART1_TX` / `UART_TX` / `TX1` / `UTX`と書かれます。`tools/signal_vocabulary.py`の語彙規則がこれを1組へ読み、規則が当たらない行は**両方とも空**にします（推測で埋めるより、埋まっていないことが分かるほうが使えるため）。現在空なのは4380行中14行で、`AETR2`（ADCトリガでペリフェラル役割ではない）、`TIETR`（`T1ETR`の誤植に見えるがdatasheet原文未確認）、`ISINK1`/`ISINK2`（ペリフェラル_役割の形をしていない実在の信号）、`X`・`V`・`SW`・`PD0`・`DVP_`（pin表のテキスト層が壊れた断片）です。`uv run tools/signal_vocabulary.py --tables tables`で規則一覧と当たり具合を出せます。

**`value=0`の行は既定経路です**。datasheet pin表の`default`列を値0として展開したもので、`basis`が`candidates(datasheet-pin-table-default:en)`になります。remap後の経路と同じ表に並ぶので、既定位置を知るためにpin_functions.csvを引き直す必要はありません。

**`valid_values`は下限です**。3つの資料の和を採っています——RMのremap格子が挙げる値、datasheet pin表が実際に経路を持つと示した値、EVTヘッダが定数として列挙している値。格子は「どちらでもよい」桁を`x`で書くので過大に出ることがあり（CH32X035の`USART4_RM=1xx`が4通りに展開される）、逆にどの資料も触れていない値は落ちます。**列挙されていない値が使えないとは限りません**が、列挙されている値はいずれかの資料が実証しています。`remap_routes.csv`に出る経路はすべてここに含まれます。

`tools/check_tables.py`が表だけを読んで検査する内容: `bits`が`register:bit`形式であること・重複がないこと・`register`列と一致すること、`valid_values`が`bits`の幅に収まること、`reset_value`が`valid_values`に含まれること、**`remap_routes.value`がすべて`remap_fields.valid_values`に含まれること**、`peripheral`と`role`が揃って埋まるか揃って空であること。

### `errata.csv`

1行1エラッタ（ロット依存の挙動・ハードウェア注意事項）。ソースは`curated/errata.csv`（手編集）で、`condition`列がどのロット/型番に該当するかを持ちます。**両言語datasheetの記載ページ（source_zh/source_en）が記録済みの行はconfirmed**、片方のみはreferenceです。

エラッタは今後のdatasheet改版で増えうるため、`tools/scan_errata.py`が全datasheetを走査して既知（curated/errata.csvの`match`列の正規表現で識別）と照合し、未知の記述があれば`NEW`として報告します（終了コード1）。NEWが出たらcurated/errata.csvに行を追加し、再実行でNEW: 0を確認します。

### `operating_conditions.csv`

シリーズごとのクロックと動作電圧です。生成は`tools/build_operating.py`。

- **`F_MAIN`**: datasheet 1ページ目の特徴リストが謳う**系統主頻**。製品として語られる周波数がこれです
- `F_HCLK`/`F_PCLK*`/`F_CORE*`: 電気的特性章「一般動作条件」表の**上限値**。F_MAINとは別の事実で、値も食い違います（CH32V003は本文48MHz・電気的特性の上限50MHz）。README の Clock 列は F_MAIN を優先し、無いシリーズ（CH32X035・CH32H41x）だけ F_HCLK / F_CORE に落とします
- `V_DD`: 動作電圧。ADC使用時・USB使用時などの条件行があります

表示テキストは英語版、最小/最大/単位は両言語照合で一致すればconfirmedです。シリーズ列はdatasheet→products結合で展開しています（`;`区切り）。電気特性章の残り（絶対最大定格・消費電流・flash耐久等）は未収集です（docs/extraction-survey.ja.md参照）。

### `evt_examples.csv`

EVTに同梱される例題の一覧です。生成は`tools/build_evt_examples.py`。EVTの目録（`EVT/<name>_List_EN.txt`と中国語版。中国語版はGBK）を索引の権威とし、**展開済みEVTツリーに実在するか**を突き合わせます。目録2版＋実体の3根拠のうち2つ以上でconfirmed。

referenceは目録と実体の食い違いで、文書側の事実です（目録が触れていないグループ、実体に無い例題名、目録内の綴りゆれ）。目録に無いグループは生成時にstderrへ報告します（現在: CH32V407のUSBHS、CH32X035のSYSTICK、CH32X315のUSBHS/USBSS）。説明は英語版のみを採用し、中国語版にしか説明が無い行は空にします。

### `cores.csv`

1行1 QingKe core。coreのISA仕様（core manual一覧表、両言語確認済み）と、どのmanualに書いてあるかを持ちます。series.csvのISAはchip側datasheetの記述で、coreの任意実装部分（V3Bの[M][B]等）をchipがどう選んだかを表すため、cores.csvのISAとは別の事実です。

### `documents.csv`

1行1文書。`CH32L103DS0.PDF`という名前だけでは場所が分からないため、**中国語/英語それぞれのオリジナルページ（.html）・ダウンロードURL・mirror（GitHub raw）URL**と版数を持ちます。除外文書も`status`付きで載る完全なカタログです。EVT（ZIP）はarchive自体をmirrorに置かないため、mirror URLは展開済みツリーを指します。

## 確定の基準は「根拠の総合判断」

各CSVには名前も値もすべて `#` の区切り列があり、**そこから右はデータ本体ではなくメタデータ**（confidence/basis）です。全行のそのセルに`#`が入るので、ファイルのどこを見ていても「ここまでがデータ」の境界が分かります。読むときは`#`以降の列を落とせば素のデータ表になります。別ファイルに分けないのは、データとメタが構造的にずれないようにするためです。

| `*_confidence` | 判定 |
|---|---|
| `confirmed` | 独立した根拠が2つ以上一致、**または人が内容を確認して根拠を記録した** |
| `reference` | 根拠が1つだけで裏取りも矛盾もない。参考値 |
| `conflict` | 根拠同士が矛盾。**人の判断が要る** |
| `missing` | どの根拠にも記載がない |
| `partial` / `varies-by-package` | （series.csvのみ）配下の確度不揃い / package依存 |

**確定は自動化に限りません。** 使い捨てスクリプトで該当箇所を提示させ、人が両言語を突き合わせて確認できたら確定とし、根拠を`curated/`に記録します。core・ISAはこの方式です（`curated/series-facts.json`、2026-08-18確認）。

## 根拠の種類（basis表記）

| basis | 中身 | 扱い |
|---|---|---|
| `products:zh/en`・`ordering:zh/en` | 比較表・ordering表。zhが原典、enは翻訳 | 通常の根拠 |
| `pin-table` | pin定義表のlead数・GPIO数（candidates/から） | **soft**: 一致すれば確定を押し上げ、不一致は`?pin-table`と記録するだけ（表抽出の行落ちがありうるため） |
| `package-pdf:zh/en` | PACKAGE.PDF（封装寸法図面）目次のbody size・pitch | 通常の根拠。`QFN48X7_A`のような変種suffixは基本名で引く |
| `rule:pn-letter` | 型番末尾2文字目=package種別（T=LQFP等、84+8件無例外） | 照合。矛盾はconflict（`!`表記） |
| `rule:pn-temp-grade` | 型番末尾数字=温度グレード（6=-40〜85℃、7=-40〜105℃。記載のある32件無例外） | temperatureの根拠・照合。比較表が最大値だけ載せる場合は`products:zh(max)`として照合に回る。末尾1・3は対象外 |
| `rule:package-name` | package名の数字=lead数 | pin_countの根拠・照合 |
| `rule:part-number-structure` | seriesは型番構造から決まる | seriesの根拠 |
| `manual:…` | 人が確認して記録した根拠（curated/） | 確定として扱う |

**採用しなかった規則**: 型番の容量コード（8=64K等）。V30x/H41x系は比較表が最大構成を載せるため92件中24件で不一致になり、規則として成立しません。

## 吸収している表記差

単位語（`8-channel`↔`8路`）、全角記号、温度→数値2つ、容量→バイト数（脚注`(2)`除去含む）、packageセルへの寸法同居（`LQFP64M(10*10)`）、ワイルドカード列（`C6x6`）、略記型番の展開。**吸収しないと本物の差が埋もれます。**

## 既知の要確認事項

- **CH32V004F6U1のpackage**: zh `QFN20L` / en `QFN20`のconflictだったが、en版datasheetの改版で`QFN20L`に修正され、再生成で両言語4根拠一致のconfirmedへ自己解消（2026-08-19確認）
- **CH32V203CCT6**: V205DS0掲載の256K品。series=V203に数えているが設計はV205（青稞V3B）系の可能性。内核の個別記述未確認
- **CH32H415/H416のcore**: H417の記述（V5F+V3F双核）からの推定でreference

## 並び順と列順

再生成や途中挿入でdiffが局所に収まるよう、規則を固定しています。

- **行順**: 各表とも行の識別子の単純昇順。families=`family`、series=`series`、products=`(part_number, family, datasheet)`。productsのpart_numberだけでは一意保証がない（同じ型番が複数datasheetに載りうる）ため、識別子の組で並べます
- **列順**: 左から重要な値（識別子 → スペック → package詳細 → 出典）。次に区切りの `#` 列（全行`#`）、その右に`*_confidence`ブロック、`*_basis`ブロックを同じ順で並べます
- **pins系**: 行の識別子は（part_number, pin, pad）/（part_number, pad, signal, route）で、その昇順。出典の`table`・`datasheet`は確認用データとして`#`の右（メタ側）にあります

## 現況（2026-08-20生成）

| 表 | 行数 | confirmed | reference | conflict |
|---|---:|---:|---:|---:|
| products.csv | 103 | 643 | 79 | 0 |
| packages.csv | 25 | 73 | 2 | 0 |
| series.csv | 27 | 100 | 4 | 0 |
| cores.csv | 13 | 13 | 0 | 0 |
| product_attributes.csv | 995 | 926 | 68 | 1 |
| remap_fields.csv | 262 | 0 | 262 | 0 |
| remap_routes.csv | 4380 | 0 | 4380 | 0 |
| errata.csv | 21 | 21 | 0 | 0 |
| operating_conditions.csv | 76 | 75 | 1 | 0 |
| pins.csv | 4312 | 4022 | 290 | 0 |
| pin_functions.csv | 29493 | 24718 | 4775 | 0 |

pins系は全103型番がpin行を持ちます（型番→pin表列の解決失敗ゼロ）。

series.csvはcore・ISAとも全27シリーズで値が入っています（ISAはdatasheetとQingKe core manual両方で確認。H415/H416のみcore推定に依存するためreference）。temperatureは型番末尾の温度グレード規則で補っており、規則単独の値はreferenceです。

part_number・series・packageは全型番で確定（conflict 0件）。残るconflictはproduct_attributesの1件（CH32H417WEU6のOPA数: zh=1/en=2）です。productsのreference 79件の大半は温度グレード規則単独のtemperatureです。pins系のreferenceはM030・V20x・V30x・H41xに偏っており、片方の版で表の行が抽出できていない箇所です（文書の矛盾ではなく抽出欠落。今後の改善対象）。

## 画像（現在は未使用）

生成READMEは画像を参照していません。データシートから図を切り出す仕組みは
用意しましたが（`tools/extract_images.py` / `tools/check_images.py`）、切り出し
品質の調整が済んでいないため、生成物はミラーに置いていません。READMEはピン
配置図の代わりに、パッケージ→型番→データシートの対応表を出します。

切り出しで分かったこと（再開するときの前提）:

- 図の見出しはデータシートごとに置き方も表記も違う。上・下・内側・1行に横並びの4通り、表記は完全型番・伏字（`CH32V103Cx`）・温度グレード省略（`CH32V007K8U`）・スラッシュ連結（`CH32V303RxT6/CH32V303RCT7`）の4通り
- 90度回転した文字はPDF上の座標が実際の描画とずれるため、座標計算だけでは範囲が決まらない。描いた画像の縁を見て広げ直す必要がある
- 同じピン配置でも型番ごとに図が別々にあるため、ファイル名の代表型番と図中の型番が食い違いうる（82枚中6枚）
- CH32V407DS0のようにピン番号がフッタ罫線に重なる版がある

シリーズ構成図（`system_*.png`）は原典のデータシートには無く、WCHの製品ページ由来です。手作りが27シリーズ中10枚あり、17シリーズ分が欠けています。`tools/build_system_figures.py` でtables/から同等の情報をSVGとして生成できますが、見た目が別物になるため採用は保留しています。

## 生成

```sh
uv run tools/build_tables.py --out tables                     # families/series/products/packages/cores/documents
uv run tools/build_pins.py --out tables                       # pins/pin_functions（数分かかる）
uv run tools/build_remap.py --out tables                      # remap_fields/remap_routes（candidates/から）
uv run tools/build_operating.py                               # operating_conditions（数分かかる）
uv run tools/build_evt_examples.py                            # evt_examples（EVTツリーと目録から）
uv run tools/extract_images.py                                # 各repoのimage/（数分かかる）
uv run tools/check_images.py [--missing|--prune]              # 画像の必要一覧と検査
uv run tools/check_tables.py                                  # 全テーブルの参照結合検査
uv run tools/scan_errata.py                                   # エラッタ増分チェック（NEWで終了コード1）
uv run tools/build_tables.py --out tables --family CH32V006   # 1familyだけ
```
