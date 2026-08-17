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
- `docs/extraction-survey.ja.md`: 上記2 toolでの実測と、機械抽出できる範囲の調査結果

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
- signal名が`T1C1`/`TIM1_CH1`、`UART`/`USART`などseries・資料間で統一されていない

## 一次資料の矛盾

- CH32M030 RM Table 6-15の`ADC_ETRGIN_RM`対応は他の3根拠と逆。recordはdatasheet Table 2-1、RM register説明/reset、EVT実装が一致する`0=PA14`、`1=PB6`を採用
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
```

`python3 -S`は`jsonschema`なしのfallback pathを確認します。mirror hash検査には、recordの`mirror.repository`に対応する兄弟repositoryが`/home/mt/dev_wch/`以下に必要です。

テストで生成したPDF text、`__pycache__`、`.pyc`等はrepositoryへ残しません。

## 次に必要な判断

1. canonical signal IDとvendor表記の分離方法を決める
2. silicon/package/exact SKUを正規化するか、flat recordを当面の正本にするか決める
3. pinを持たないinternal routeを同じschemaに入れるか分離する
4. verificationをfunction/selector単位まで細分化するか決める
5. Arduino側のdata lock/consumer形式を作る
6. CH32V006とCH32V103のpin/register構造でschemaを再度stress testする

2について、生成先である各family repositoryのpin表はpackage横断の1表であり、必要SKU数を規定します。詳細は[抽出可能性の事前調査](extraction-survey.ja.md)を参照してください。同文書の末尾に、抽出toolingから出てきた未決定事項も記録しています。

## 禁止・注意事項

- 旧Arduino core、EVT tree、公式PDFを新repositoryへ無断コピーしない
- `ch32_riscv_tools/PinAlternateFunctions`の手製表を検証根拠やimport元にしない
- sample recordをArduino対応宣言として扱わない
- schema・対象範囲・初期SKUを合意なしに決定済みへ変更しない
- commit、push、releaseは依頼または合意なしに行わない
