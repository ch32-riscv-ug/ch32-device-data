# 抽出候補

文書状態: 機械抽出の生出力。**人のreviewを経ていません。**

`tools/build_all.py`が、mirrorしているdatasheetとreference manual、EVTヘッダから生成したSKUごとの候補です。`devices/`のrecordとは別物で、schemaにも準拠していません。

- 1ファイル1 SKU。ファイル名は型番の小文字
- `product_attributes`はdatasheetの製品比較表を、**資料が使っているラベルのまま**保持しています
- `route_selectors`はEVTヘッダのbit位置、RMのregister field表の`reset_value`、RMのremap格子の`valid_values`を結合したものです
- `bits`は**bitごとにregister名を持ちます**。CH32L103やCH32V30xではselectorがPCFR1とPCFR2にまたがるためです。ヘッダとRMは片方にしか書いていないことがあるので（CH32V20xのヘッダは`AFIO_PCFR2_`定義を持ちません）、両者の和を取り、補完した箇所は`_split_registers`と結合noteに残しています
- `pins`はdatasheetのpin表からで、`selection`は経路の結合が成立した箇所にのみ付きます。pin表の`default`列は値0の`selection`になります
- `_`で始まるkeyは抽出時の判断過程です。`_selector_resolved_by`は経路をどう同定したか、`_unresolved_selector`は同定できなかった箇所、`_combined_signal`はdatasheetが1 signalで書いている合成名、`_valid_values_source`は有効値をどの資料から得たか、`_values_not_in_grid`はpin表が実証したのにRMのremap格子に無い値を示します
- signal名の綴りの揺れ（`TX1`/`UTX`/`USART1_TX`）は`tools/signal_vocabulary.py`の語彙規則で吸収します。padの一致から1対1のalias表を導く方式は、1つのpadが複数機能を持つため原理的に決まらないので廃止しました

正規化・schemaへの写像・確度の確認は後段で行います。数値と現状の限界は[抽出可能性の事前調査](../docs/extraction-survey.ja.md)にまとめています。
