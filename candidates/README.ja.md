# 抽出候補

文書状態: 機械抽出の生出力。**人のreviewを経ていません。**

`tools/build_all.py`が、mirrorしているdatasheetとreference manual、EVTヘッダから生成したSKUごとの候補です。`devices/`のrecordとは別物で、schemaにも準拠していません。

- 1ファイル1 SKU。ファイル名は型番の小文字
- `product_attributes`はdatasheetの製品比較表を、**資料が使っているラベルのまま**保持しています
- `route_selectors`はEVTヘッダのbit位置、RMのregister field表の`reset_value`、RMのremap格子の`valid_values`を結合したものです
- `pins`はdatasheetのpin表からで、`selection`は経路の結合が成立した箇所にのみ付きます
- `_`で始まるkeyは抽出時の判断過程です。`_selector_resolved_by`は経路をどう同定したか、`_unresolved_selector`は同定できなかった箇所、`_combined_signal`はdatasheetが1 signalで書いている合成名、`_bit_disagreement`は資料間でbit位置が食い違う箇所を示します
- `signal_aliases`はdatasheetとRMのsignal名対応で、padと selector値の一致から導出した**素案**です

正規化・schemaへの写像・確度の確認は後段で行います。数値と現状の限界は[抽出可能性の事前調査](../docs/extraction-survey.ja.md)にまとめています。
