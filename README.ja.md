# CH32 Device Data

[English](README.md)

CH32のexact orderable SKUを、出典と検証状態を含めて機械可読に記述するための独立データリポジトリです。

> [!IMPORTANT]
> 現在のschema version `0.1-draft`はQ-011を検討するための提案であり、確定仕様ではありません。
> `devices/`のrecordもArduinoコアの対応宣言ではありません。
> このリポジトリをdevice databaseの正本としますが、schema自体はまだ草案です。

## 構成

- `schemas/device.schema.json`: exact SKU、CPU、memory、package、peripheral、pin、出典のschema草案
- `devices/*.json`: schemaを評価するための代表SKUデータ
- `tools/validate.py`: JSON Schemaと追加の整合性規則を検査するvalidator
- `tools/extract_selectors.py`、`tools/extract_pins.py`、`tools/extract_remap.py`、`tools/extract_registers.py`: EVTヘッダ・datasheet・RMから候補を抽出するreview支援tool。recordは書き換えない
- `tools/build_candidate.py`: 上記4 toolの出力を1つの候補へ結合する
- `candidates/*.json`: 全SKUの機械抽出結果。未reviewで、schemaにも準拠しない
- `docs/schema-notes.ja.md`: schema調査、確認済みの構造差、未決定事項
- `docs/extraction-survey.ja.md`: 機械抽出できる範囲の実測と、資料側の崩れの一覧
- `docs/handoff.ja.md`: 作業状態、既知の資料矛盾、再開手順

## データの境界

- recordの単位は注文可能な正確な型番とする
- WCHのseries名と、コア内部で共有する実装familyは同一と仮定しない
- packageのbond-out差をdevice recordに保持する
- pin routeは人間向けのroute名に加え、`route_selectors`でcontroller、register、field、bit位置、有効値、reset値を定義し、各functionの`selection`からraw selector値とともに参照する。AFIO remap以外のOPA入力選択などにも同じ構造を使う。連続fieldは`bit_offset`/`bit_width`、V003のような分散fieldはLSB順の`bit_positions`で表し、bit幅内でもreservedの値はvalidatorが拒否する
- board固有のLED、connector、clock、upload設定はdevice dataへ入れない
- Arduino core固有のFQBN、variant、build flagはsource dataへ入れず、consumer側の生成物にする
- compilerの`-march`/`-mabi`はdatasheetのISA表記から推測せず、toolchain認定後に追加する
- `coverage`により未採取、部分採取、採取完了を区別し、物理package pinとpin functionも別々に評価する
- `verification`により領域ごとに単一資料からの採取、相互確認、実機確認を区別する
- 対応tierは実測後に別のsupport/board manifestで扱い、このrecordだけから対応を宣言しない

## 出典

`sources`には公式download URL、文書版、英語・中国語、mirror repositoryのcommit、対象fileのSHA-256を記録できます。`hash_scope`でdownload artifact全体とarchive内の個別source fileを区別します。`evidence`は値を確認したtable/sectionへ戻るためのlocatorです。

兄弟repositoryは一次資料のmirrorとして参照します。EVTや旧Arduinoコアのsourceをこのrepositoryへ自動的にコピーしません。

## 検証

```sh
python3 tools/validate.py
```

`jsonschema` packageが利用可能ならJSON Schema全体を検査します。なくても標準libraryだけで、ID、出典参照、pin coverageなどの追加規則を検査します。

抽出toolは外部packageを使うため、`pyproject.toml`と`uv.lock`で固定したuv経由で実行します。抽出できる範囲と資料側の崩れは[抽出可能性の事前調査](docs/extraction-survey.ja.md)にまとめています。

```sh
uv run tools/extract_selectors.py <EVT>/Peripheral/inc/ch32xxx.h --compare devices/<id>.json
uv run tools/extract_pins.py <datasheet>.PDF --package TSSOP20 --compare devices/<id>.json
uv run tools/extract_remap.py <manual>.PDF --compare devices/<id>.json
uv run tools/extract_registers.py <manual>.PDF --compare devices/<id>.json
```
