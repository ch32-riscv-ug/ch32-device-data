# 用語集

文書基準日: 2026-08-18

この repository と `tables/` のCSVが使う用語の定義です。特に **ファミリーとシリーズはこのプロジェクトの運用単位** であり、WCHの公式分類とは限りません。

## 階層

上から下へ: ファミリー → シリーズ → 注文型番 → package/pin。

| 用語 | 定義 | 例 | 対応 |
|---|---|---|---|
| **ファミリー family** | mirror repository = 文書の単位。共通のdatasheet群・reference manual・EVTを共有するシリーズの集まり。このプロジェクトがrepository構成に合わせて定めた単位で、WCH公式の分類名ではない | `CH32V20x` | `tables/families.csv`（1行1ファミリー） |
| **シリーズ series** | 型番の先頭8文字（`CH32`+英字1+数字3）が表す製品系列。die・coreの単位に最も近い | `CH32V203` | `tables/series.csv`（1行1シリーズ） |
| **注文型番 part number** | 実際に注文できる完全型番。SKUと同義に使う | `CH32V006K8U7` | `tables/products.csv`（1行1型番） |
| **package** | 物理パッケージ。同一型番＝単一package。寸法・pitch・lead数はpackageの属性としてマスタ表に正規化し、productsは名前で参照する | `LQFP48` | `tables/packages.csv`（1行1package） |
| ~~silicon~~ | 旧称。**series** に改称した（`silicon.csv`→`series.csv`） | — | — |

注意:

- シリーズとdatasheetは**1対1ではない**。1つのdatasheetが複数シリーズを載せ（CH32V007DS0にV007とM007）、1つのシリーズが複数datasheetに散る（CH32V203CCT6はCH32V205DS0掲載）
- 同一ファミリー内にcoreの違うシリーズが混在する（CH32V20x内: V203=V4B、V205=V3B、V208=V4C）

## 型番の読み方

`CH32 V203 C 8 T 6` の分解:

| 部位 | 意味 | 確度 |
|---|---|---|
| `CH32` | 共通プレフィックス | — |
| `V203` | シリーズ（英字1+数字3） | 規則として採用（`rule:part-number-structure`） |
| `C` | pin数クラスの英字。観測値: J=8, D=12, A=16, F=20, E=24-26, G=28, K=32, C=48, R=60-64, W=68, M=76-88, V=100, Q=128 | 観測的（103型番から集計）。厳密な1対1でないため規則としては未採用 |
| `8` | 容量コード（4=16K, 8=64K, B=128K…） | **規則として不採用**。V30x/H41x系は比較表が最大構成（480K等）を載せるため24/92件で対応しない |
| `T` | package種別。T=LQFP, U=QFN, P=TSSOP, M=SOP, R=QSOP | **採用**（`rule:pn-letter`）。ordering表84件+人手record8件で無例外 |
| `6` | 温度グレード。6=-40〜85℃、7=-40〜105℃（記載のある32件で無例外、`rule:pn-temp-grade`として採用）。1・3はpackage寸法違い等の別バリエーションで温度の主張を持たない | 6/7のみ規則採用 |

- **略記 listed_as**: 比較表がordering表の完全型番を省いた表記。`CH32V208CB`→`CH32V208CBU6`
- **ワイルドカード**: 略記中の小文字`x`はpackage文字の任意一致。`CH32V203C6x6`はC6T6とC6U6の共通列

## データの確度

| 用語 | 定義 |
|---|---|
| **confirmed（確定）** | 独立した根拠が2つ以上一致、**または人が内容確認して根拠を記録した**値。2言語一致だけが条件ではない |
| **reference（参考）** | 根拠が1つだけで、裏取りも矛盾もない値 |
| **conflict** | 根拠同士が矛盾。人の判断待ち |
| **missing** | どの根拠にも記載がない |
| **partial** / **varies-by-package** | （series.csvのみ）配下の確度不揃い / package依存の値でシリーズの属性ではない |
| **basis（根拠）** | 値の出所一覧（`*_basis`列、`+`区切り）。`!規則`=矛盾（conflict化）、`?規則`=soft照合の不一致 |
| **soft照合** | 一致すれば確度を押し上げるが、不一致でもconflictにしない照合。抽出欠落がありうる根拠（pin-table）に使う |
| **`manual:`** | 人が確認して記録した根拠。記録は`curated/`にあるものだけが名乗れる |

## 一次資料

| 用語 | 定義 |
|---|---|
| **原典 / 翻訳** | 中国語版（zh）が原典、英語版（en）はその翻訳。矛盾時はzhを優先（例: CH32V004F6U1はzh `QFN20L`が正） |
| **DS / datasheet** | 型番・電気特性・pin配置の文書。`CH32V006DS0.PDF`。DS2は補足版 |
| **RM / reference manual** | register・機能の文書。remap格子とregister field表の出所 |
| **EVT** | WCHの評価ボードexample一式（ZIP）。**コンパイルされる値**（register bit定義・linker MEMORY）は信頼できる。コメントや文書プロースは黙って腐る |
| **比較表 products table** | DS冒頭の製品比較表。シリーズ内の全型番と属性。行/列転置の両layoutがある |
| **ordering表** | DS末尾の注文情報表。**完全な注文型番を持つ唯一の表**。package・body size・pin pitchの出所 |
| **pin定義表 pin table** | package別のpin配置表。lead番号は物理pin。小packageは複数padを1 leadに結線する（CH32V003J4M6は8 leadに11行） |
| **QingKe（青稞）** | WCHのRISC-V core。V2A/V2C/V3A/V3B/V3F/V3V/V4B/V4C/V4F/V5F。core manualは本repositoryが保持 |
| **EP / exposed pad** | packageの裏面放熱pad。WCHはpin番号0として記載する。lead数には数えない |

## リポジトリ内の場所

| 場所 | 中身 |
|---|---|
| mirror / 兄弟repository | `/home/mt/dev_wch/CH32*`と`WCH-common`（GitHub `ch32-riscv-ug/*`）。一次資料の保管場所。`WCH-common`はfamily横断文書（QingKe core manual・WCH-Link・PACKAGE寸法図面）専用で、ファミリーではない |
| `manifests/documents.json` | 取得すべき文書のカタログ。日次同期。mirrorはこれを読んで取得する |
| `candidates/` | **未review**の機械抽出出力。根拠にはなるが確定ではない |
| `curated/` | 人が確認して記録した確定情報（根拠・確認日つき） |
| `tables/` | 正規化CSV。確度と根拠つき。階層はこの用語集の通り |
| `devices/` | schema検証用のsample record（Arduino対応宣言ではない） |
