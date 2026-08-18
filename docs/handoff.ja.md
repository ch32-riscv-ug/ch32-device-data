# Device data作業引継ぎ

文書基準日: 2026-08-17

文書状態: 作業記録。配置は決定済み、schemaは未決定。

## 現在地

ArduinoCore-CH32のQ-011を検討するため、exact orderable SKU単位のJSON Schemaと8つのstress sampleを管理しています。Arduino対応SKUの宣言ではありません。

2026-08-17に`ArduinoCore-CH32`の仮置き領域から、この独立repositoryへ移しました（`b31e9ba`）。同日、抽出toolingを追加しています（`8775837`）。引継ぎ時は`git status --short`で未commitの変更を確認してください。

## 作成済みファイル

- `schemas/device.schema.json`: Draft 2020-12 schema、version `0.1-draft`
- `devices/*.json`: 8 sample record
- `tools/validate.py`: JSON Schema＋relation validator。`jsonschema`なしでも主要relationを検査
- `docs/schema-notes.ja.md`: schemaで確認したfamily/package差と未決定事項

抽出tooling（`8775837`、`docs/extraction-survey.ja.md`のみ後追い）:

- `pyproject.toml` / `uv.lock`: tool用のuv project定義。`jsonschema`と`pdfplumber`を固定
- `tools/extract_selectors.py`: EVTヘッダのregister bit定義からroute selector候補を作る
- `tools/extract_pins.py`: datasheetのpin表からpackage pin/function候補を作る
- `tools/extract_remap.py`: RMのremap格子から`(field, value, signal, pad)`候補を作る。datasheetにない default 経路とsilicon全体の経路を補い、datasheet側抽出との相互確認に使う
- `tools/extract_registers.py`: RMのregister field表から bit位置・`reset_value` 候補を作る。説明文に書かれた経路も読む
- `tools/extract_products.py`: datasheetの製品比較表から全SKUとその属性を取る。ユニーク型番92件を確認済み
- `tools/build_candidate.py`: 上記4 toolの出力を結合し、pinから参照されるselectorだけを残した候補を作る
- `tools/extract_ordering.py`: datasheetのordering表からorder model・package・body size・pin pitchを取る
- `tools/build_all.py`: 全SKUに対して候補を生成する。出力は`candidates/`（未review）
- `curated/pin-table-columns.json`: テキスト層が落とす列見出しを、画像確認した値で上書きする
- `manifests/documents.json`: 取得すべき文書のカタログ。mirrorはここを読んで取得する
- `templates/`: 全mirror共通の`update.sh`とworkflow。file IDの直書きを持たない
- `tools/sync_catalog.py` / `tools/check_mirrors.py`: カタログ同期とmirror追随確認。日次workflowが実行する
- `tools/crosscheck_languages.py`: 中国語版と英語版を別々に抽出して突き合わせる
- `tools/build_tables.py` / `tables/`: 正規化CSV。families→series→productsの階層＋packagesマスタで、値ごとに根拠一覧（basis）と確度を持つ。core/ISAは`curated/series-facts.json`（人手確認済み）から結合。確定の基準は`tables/README.ja.md`参照
- `tools/extract_package_dims.py`: PACKAGE.PDF（WCH-common mirror）目次からpackageごとのbody size・pitchを取る。両言語105件
- `tools/build_pins.py`: pin定義表を`tables/pins.csv`（lead↔pad対応）と`tables/pin_functions.csv`（pad→signal/route）に正規化する。両言語を別々に読んで突き合わせる
- `tools/build_remap.py`: candidatesから`tables/remap_fields.csv`/`remap_routes.csv`を生成。pin_functionsのremap-Nを解決する
- `tools/build_documents.py` / `tools/check_tables.py`: 文書カタログのCSV投影（標準ライブラリのみ、日次workflowが実行）と、全テーブルの参照結合検査（push/PRのcheck workflowと日次が実行）
- `tools/build_readme.py` / `generated/readme/`: **本来の目的である各mirror READMEの生成**。tablesから組み立ててここへcommitし、mirrorのupdate.shが日次で自分の分をfetchしてREADME.mdを置き換える（catalogueと同方式・クロスrepoトークン不要）。CH32V003で旧手製READMEとpin表72セル完全一致を確認済み。ch32_riscv_toolsへのリンクは生成版には無い（撤去方針）。画像はmirror側image/を生成時にスキャンして参照するだけで、手動維持。organizationプロフィール（`.github`リポジトリの`profile/README.md`、family→series対応表つき）も同方式で`generated/readme/_profile.md`から日次fetch
- `docs/extraction-survey.ja.md`: 上記5 toolでの実測と、機械抽出できる範囲の調査結果
- `docs/glossary.ja.md`: 用語集。ファミリー/シリーズの定義、型番の読み方、確度の語彙

全datasheetの掃引では31 pin定義表・102変種列から4035 pin、21853 pin function（要確認252件）を取得できています。対象SKUをどこまで広げるかは未合意です。

`tools/build_all.py`で全SKUの候補を`candidates/`へ生成済みです（98ファイル・4.0MB、**全SKUでpin取得**、3989 pin・22186 function・7108経路・585 selector）。**未reviewの機械出力**であり、`devices/`へは反映していません。

残る資料側の欠落は、reference manualがmirrorされていないCH32V407です（経路0件）。

## Sample recordの状態

| Exact SKU | 主な目的 | Package pin | Pin function |
|---|---|---:|---:|
| CH32V003F4P6 | RV32E、小容量、分散AFIO field、OPA | complete | complete、実機未確認 |
| CH32V006K8U7 | 新しいV00x構造のstress sample | 未採取 | 未採取 |
| CH32V103C8T6 | 標準RV32IMACのstress sample | 未採取 | 未採取 |
| CH32X035F8U6 | USB PD/USBFS/PIOC、QFN20+EP | complete | complete、実機未確認 |
| CH32M030C8T7 | motor/analog/PD、MV I/O、LQFP48 | complete | complete、実機未確認 |
| CH32M030C8U7 | package固有HV I/O・内蔵Type-C Rd | 未採取 | 未採取 |
| CH32V407VET6 | 大規模memory/peripheral stress sample | 未採取 | 未採取 |
| CH32H417QEU6 | dual-core、分割memory、USB3 stress sample | 未採取 | 未採取 |

## 重要な確認結果

- CH32X035は複数のraw selector値が同じpin routeを選ぶ
- CH32M030はbit幅内にreserved selector値があり、`valid_values`が必要
- CH32V003のI2C/USART selectorは非連続bit `[1,22]`/`[2,21]`で、`bit_positions`が必要
- AFIO以外のOPA input selectorも同じ`selection`構造で表現できる
- CH32V003の`TIM1_1_RM`はTIM1_CH1を内部LSIへ接続し、package pin recordだけでは表せない
- exact SKUのflat recordではsilicon共通selectorがpackageごとに重複する
- signal名が`T1C1`/`TIM1_CH1`、`UART`/`USART`などseries・資料間で統一されていない。RMとrecordでinstance番号の有無も揺れる（`SPI_RM`/`SPI1_REMAP`、`I2C1_SCL`/`I2C_SCL`）
- CH32H41xはAFIO remapではなくpinごとのalternate function多重化（`TIM8_CH1(AF0)`）で、現在の`route_selectors`では表せない
- 型番の末尾2文字目がpackage種別を表す（`T`=LQFP、`U`=QFN、`P`=TSSOP、`M`=SOP、`R`=QSOP）。ordering表84件と人手record 8件のすべてで一致し例外がない
- SKUの母集合は製品比較表とordering表の和。ordering表だけが完全な注文型番を持つ（比較表の`CH32V208CB`はordering表では`CH32V208CBU6`）

## 一次資料の矛盾

- CH32M030 RM Table 6-15の`ADC_ETRGIN_RM`対応は他の3根拠と逆。recordはdatasheet Table 2-1、RM register説明/reset、EVT実装が一致する`0=PA14`、`1=PB6`を採用。`tools/extract_remap.py`はこの矛盾を照合時に自動で提示する
- CH32V003 RMの`ADC_ETRGINJ_RM` register説明はregular triggerのPD3/PC2を誤って繰り返す。recordはdatasheet Table 2-2とRM Table 7-13が一致する`0=PD1`、`1=PA2`を採用

いずれも実機未確認であり、document error候補としてrecordの`notes`に残しています。

## Validatorが検査するrelation

- filename、record ID、part number
- source/evidence参照とsource ID一意性
- complete packageのlead番号、exposed pad、GPIO数
- function重複
- memory parent、integrated component、special-I/O ID
- route selector ID/field一意性
- register内のselector bit重複
- 連続fieldとLSB順の非連続`bit_positions`
- selectorのbit幅、有効値、reset値、reserved値
- functionからselectorへの参照

## 再開時の検証

```sh
cd /home/mt/dev_wch/ch32-device-data
python3 tools/validate.py
python3 -S tools/validate.py
git diff --check
```

抽出toolを使う場合はuv経由です。recordは書き換えず、候補と要確認事項を表示するだけです。

```sh
uv run tools/extract_selectors.py \
  /home/mt/dev_wch/CH32V003/EVT/EXAM/SRC/Peripheral/inc/ch32v00x.h \
  --compare devices/ch32v003f4p6.json
uv run tools/extract_pins.py \
  /home/mt/dev_wch/CH32V003/datasheet_en/CH32V003DS0.PDF \
  --package TSSOP20 --compare devices/ch32v003f4p6.json
uv run tools/extract_remap.py \
  /home/mt/dev_wch/CH32M030/datasheet_en/CH32M030RM.PDF \
  --compare devices/ch32m030c8t7.json
uv run tools/extract_registers.py \
  /home/mt/dev_wch/CH32M030/datasheet_en/CH32M030RM.PDF \
  --compare devices/ch32m030c8t7.json
```

`python3 -S`は`jsonschema`なしのfallback pathを確認します。mirror hash検査には、recordの`mirror.repository`に対応する兄弟repositoryが`/home/mt/dev_wch/`以下に必要です。

テストで生成したPDF text、`__pycache__`、`.pyc`等はrepositoryへ残しません。

## 次に必要な判断

1. canonical signal IDとvendor表記の分離方法を決める。CH32V003はdatasheetが`T1CH1`、RMが`TIM1_CH1`で、辞書なしでは資料間の結合が0件になる
2. silicon/package/exact SKUを正規化するか、flat recordを当面の正本にするか決める
3. pinを持たないinternal routeを同じschemaに入れるか分離する。あわせてCH32H41xのAF多重化の表現も決める
4. verificationをfunction/selector単位まで細分化するか決める
5. Arduino側のdata lock/consumer形式を作る
6. CH32V006とCH32V103のpin/register構造でschemaを再度stress testする

2について、生成先である各family repositoryのpin表はpackage横断の1表であり、必要SKU数を規定します。詳細は[抽出可能性の事前調査](extraction-survey.ja.md)を参照してください。同文書の末尾に、抽出toolingから出てきた未決定事項も記録しています。

## 禁止・注意事項

- 旧Arduino core、EVT tree、公式PDFを新repositoryへ無断コピーしない
- `ch32_riscv_tools/PinAlternateFunctions`の手製表を検証根拠やimport元にしない
- sample recordをArduino対応宣言として扱わない
- schemaは拡張してよい。対象は全SKU・全項目とし、正規化と分解は公開時に行う
- git操作（add・commit・push・reset等の書き込み操作）は一切行わない。mirrorリポジトリも含め、すべてユーザーが操作する。作業はファイル編集までで止め、commit/pushすべき内容を報告する
