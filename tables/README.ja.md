# 正規化テーブル

`tools/build_tables.py` が生成します。用語（ファミリー/シリーズ/確度…）の定義は [docs/glossary.ja.md](../docs/glossary.ja.md) にあります。**上から下に降りる階層**で、すべての値が「何を根拠にしているか」（`*_basis`列）を持ちます。

```
families.csv        11行   ファミリー一覧（mirror repository = 文書の単位）
  └ series.csv        27行   シリーズ（die）。core・ISA・共通スペック
      └ products.csv    103行   注文型番。silicon以外はpackage名で参照
          └ pins.csv         3835行  lead↔padの物理対応（datasheet×package列ごと）
          └ pin_functions.csv 9876行  pad→signal/routeの論理機能（表ごとに1回）

packages.csv   25行  packageマスタ。寸法・pitch・lead数（productsから名前で参照）
```

pins系は`tools/build_pins.py`、それ以外は`tools/build_tables.py`が生成します。

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

pin定義表を物理と論理に分けたものです。**pins.csv**は「このpackageのlead Nにどのpadが載るか」で、1行1(datasheet, 表, package, pin, pad)。**pin_functions.csv**は「このpadがどの信号を持つか」で、機能は表の行（pad）に1回だけ書かれpackage列に依存しないため、package重複なしの1行1(datasheet, 表, pad, signal, route)です。

`route`の値: `main`（リセット後の主機能）/ `default`（既定の代替機能）/ `remap-N`（remap値N）/ `af-N`（H41x・X315系のalternate function番号）/ 空（経路番号が資料になく要確認）。

両言語照合で吸収している表記ずれ: 表番号のずれ（X315はzh`表2-1-1`=en`Table 2-1`。表題中のシリーズ名で照合）、列見出しの綴り（`QFN48×7`、`QFN28(6)`、zh`LQFP64M`=en画像`LQFP64`は表内の消去法でペアリング）、1列が複数packageを兼ねる見出し（`LQFP48/QFN48X7`は成分ごとに登録）。

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
| `rule:package-name` | package名の数字=lead数 | pin_countの根拠・照合 |
| `rule:part-number-structure` | seriesは型番構造から決まる | seriesの根拠 |
| `manual:…` | 人が確認して記録した根拠（curated/） | 確定として扱う |

**採用しなかった規則**: 型番の容量コード（8=64K等）。V30x/H41x系は比較表が最大構成を載せるため92件中24件で不一致になり、規則として成立しません。

## 吸収している表記差

単位語（`8-channel`↔`8路`）、全角記号、温度→数値2つ、容量→バイト数（脚注`(2)`除去含む）、packageセルへの寸法同居（`LQFP64M(10*10)`）、ワイルドカード列（`C6x6`）、略記型番の展開。**吸収しないと本物の差が埋もれます。**

## 既知の要確認事項

- **CH32V004F6U1のpackage（conflict）**: zh `QFN20L` / en `QFN20`。原典がzhなので`QFN20L`が正、翻訳で`L`欠落とみられる
- **CH32V203CCT6**: V205DS0掲載の256K品。series=V203に数えているが設計はV205（青稞V3B）系の可能性。内核の個別記述未確認
- **CH32H415/H416のcore**: H417の記述（V5F+V3F双核）からの推定でreference

## 並び順と列順

再生成や途中挿入でdiffが局所に収まるよう、規則を固定しています。

- **行順**: 各表とも行の識別子の単純昇順。families=`family`、series=`series`、products=`(part_number, family, datasheet)`。productsのpart_numberだけでは一意保証がない（同じ型番が複数datasheetに載りうる）ため、識別子の組で並べます
- **列順**: 左から重要な値（識別子 → スペック → package詳細 → 出典）。次に区切りの `#` 列（全行`#`）、その右に`*_confidence`ブロック、`*_basis`ブロックを同じ順で並べます

## 現況（2026-08-18生成）

| 表 | 行数 | confirmed | reference | conflict |
|---|---:|---:|---:|---:|
| products.csv | 103 | 639 | 14 | 1 |
| packages.csv | 25 | 73 | 2 | 0 |
| pins.csv | 3835 | 3621 (94%) | 214 | 0 |
| pin_functions.csv | 9876 | 8567 (87%) | 1309 | 0 |

part_number・series・packageは全型番で確定（conflict 1件=V004F6U1を除く）。temperatureのmissing（71件）は記載自体がない型番です。pins系のreferenceはM030・V20x・V30x・H41xに偏っており、片方の版で表の行が抽出できていない箇所です（文書の矛盾ではなく抽出欠落。今後の改善対象）。

## 生成

```sh
uv run tools/build_tables.py --out tables                     # families/series/products/packages
uv run tools/build_pins.py --out tables                       # pins/pin_functions（数分かかる）
uv run tools/build_tables.py --out tables --family CH32V006   # 1familyだけ
```
