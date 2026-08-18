# 正規化テーブル

`tools/build_tables.py` が生成します。**すべての値が「何を根拠にしているか」を持ち、確度はその総合判断です。**

## 確定の基準は「根拠の総合判断」

2言語の一致だけを確定とはしません。独立した根拠（下表）を値ごとに集め、次で判定します。

| `*_confidence` | 判定 |
|---|---|
| `confirmed` | 独立した根拠が2つ以上一致している |
| `reference` | 根拠が1つだけで、裏取りも矛盾もない。参考値 |
| `conflict` | 根拠同士が矛盾している。**人の判断が要る** |
| `missing` | どの根拠にも記載がない |
| `partial` | （silicon.csvのみ）配下packageの確度が揃っていない |
| `varies-by-package` | （silicon.csvのみ）packageごとに値が違い、siliconの属性ではない |

`*_basis` 列が根拠の一覧そのものです。`+`区切りで、`!規則` は矛盾（conflictになる）、`?規則` はsoft照合の不一致（後述、conflictにしない）を表します。

## 根拠の種類

| basis表記 | 中身 | 扱い |
|---|---|---|
| `products:zh` / `products:en` | 製品比較表。zhが原典、enはその翻訳 | 通常の根拠 |
| `ordering:zh` / `ordering:en` | ordering表。完全な注文型番を持つ唯一の表 | 通常の根拠 |
| `pin-table` | pin定義表のlead番号の異なり数・GPIO pad数（candidates/から） | **soft**。一致すれば確定を押し上げるが、不一致は`?pin-table`と記録するだけ。表抽出が行を落とすことがあり、不一致は文書の矛盾より抽出欠落を疑うべきため |
| `rule:pn-letter` | 型番の末尾2文字目=package種別（T=LQFP, U=QFN, P=TSSOP, M=SOP, R=QSOP）。ordering表84件+人手record8件で無例外 | 照合規則。矛盾すればconflict |
| `rule:package-name` | package名の数字=lead数（LQFP64→64） | pin_countの根拠・照合 |
| `rule:part-number-structure` | seriesは型番の先頭構造（CH32x###）から決まる | seriesの根拠 |

1根拠でも規則の裏付けがあれば確定になります（例: ordering:zhにしかない型番でも、pn-letterがpackageと一致すればpackageはconfirmed）。逆にコメントや説明文のような弱い出所しかない値は`reference`に留まります。

**採用しなかった規則**: 型番の容量コード（8=64K等）。V30x/H41x系は比較表が最大構成（480K等）を載せ、コードは既定構成を指すため、92件中24件で不一致になり規則として成立しません。

## ファイル

### `silicon.csv`

1行1silicon。CH32V006が何であるかを、packageごとのファイルを開かずに見るためのものです。配下の全packageが同じ値を持つ項目だけが載り、packageで変わる項目は `varies-by-package` として空になります。

### `products.csv`

1行1注文型番。packageごとに変わる値はこちらです。`listed_as` は比較表での略記（`CH32V208CB` → `CH32V208CBU6`）です。

## 吸収している表記差

同じ事実を資料が別の書き方で述べるため、比較前に正規化します。**吸収しないと本物の差が埋もれます。**

| 種類 | 例 |
|---|---|
| 単位語・全角記号 | `8-channel`↔`8路`、`QFN48X7`↔`QFN48×7` |
| 温度・容量表記 | `-40℃~85℃`→数値2つ、`62K`→`63488` |
| packageセルへの寸法同居 | 比較表 `LQFP64M(10*10)` = ordering表 `LQFP64M`+`10*10mm` |
| ワイルドカード列 | 比較表の `CH32V203C6x6`（小文字x）はC6T6とC6U6の共通列。pn-letterで各型番のpackageを選ぶ |
| 略記型番 | 比較表 `CH32V303RC` はordering表のRCT6/RCT7両方に展開 |

## 既知のconflict（人手確認待ち）

- **CH32V004F6U1 の package**: 中国語版 `QFN20L` / 英語版 `QFN20`。4根拠中zh系がQFN20L。中国語版が原典なので `QFN20L` が正しく、翻訳で `L` が落ちたと見られる

## 現況（2026-08-18生成）

products.csv 103行・silicon.csv 27行。値ベースで confirmed 905 / reference 57 / missing 170 / conflict 1。part_number・series・packageは全型番で確定（conflict 1件を除く）。temperatureのmissing 71は記載自体がない型番です。

## 生成

```sh
uv run tools/build_tables.py --out tables
uv run tools/build_tables.py --out tables --family CH32V006   # 1familyだけ
```
