# 正規化テーブル

`tools/build_tables.py` が生成します。**確定した情報と未確定の情報を、列ごとに区別して持ちます。**

## 確定の基準は「両言語の一致」

WCHは各文書を中国語と英語で出しており、中国語版が原典で英語版はその翻訳です。**両方を別々に抽出して突き合わせ、一致したものを確定とします。**

| `*_confidence` | 意味 |
|---|---|
| `confirmed` | 両言語が同じ値を述べている |
| `zh-only` / `en-only` | 片方の版にしか記載がない |
| `conflict` | 両言語が違う値を述べている。**人の判断が要る** |
| `missing` | どちらにも記載がない |
| `partial` | （silicon.csvのみ）配下のpackageで確度が揃っていない |
| `varies-by-package` | （silicon.csvのみ）packageごとに値が違うため、siliconの属性ではない |

## ファイル

### `silicon.csv`

1行1silicon。CH32V006が何であるかを、packageごとのファイルを開かずに見るためのものです。配下の全packageが同じ値を持つ項目だけがsiliconの属性として載り、packageで変わる項目は `varies-by-package` として空になります。

### `products.csv`

1行1注文型番。packageごとに変わる値はこちらにあります。

## 比較時に吸収している表記差

同じ内容を両言語が別の書き方で述べるため、次を正規化してから比較します。**これを吸収しないと、実質すべてが不一致になり本物の差が埋もれます。**

| 種類 | 例 |
|---|---|
| 単位語 | `8-channel` ↔ `8路` |
| 全角記号 | `2 (OPA1/3)` ↔ `2（OPA1/3）`、`QFN48X7` ↔ `QFN48×7` |
| 温度表記 | `Industrial grade -40℃~85℃` ↔ `-40~85°C` → 数値2つに還元 |
| 容量表記 | `62K` → `63488` バイト |
| 項目数の差 | 中国語版が英語版にない行を持つ場合がある（翻訳時の欠落） |

言語依存の記述（`Package Description` の説明文など）は、原理的に一致しないため比較対象から外しています。

## 既知のconflict

- **CH32V004F6U1 の package**: 中国語版 `QFN20L` / 英語版 `QFN20`。中国語版が原典なので `QFN20L` が正しく、翻訳で `L` が落ちたと見られる

## 生成

```sh
uv run tools/build_tables.py --out tables
uv run tools/build_tables.py --out tables --family CH32V006   # 1familyだけ
```
