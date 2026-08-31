# 文書一覧

## いま使うもの

- [作業リスト](worklist.ja.md): 生きている項目・既知の穴・**次の作業の優先順**・資料側の問題台帳
- [テーブル別の信頼度](table-reliability.ja.md): 表ごとにどこまで信用してよいか、原典サンプル検証の結果
- [データの区分・形式・置き場所の定義](data-layout.ja.md): 目録 `catalog/`・証拠 `evidence/`・索引 `index/` の3区分と、その規則・形式・consumer の契約（2026-08-26 実施）。確認の記録は [worklist-archive](worklist-archive.ja.md) の「表の役割の確認」
- [作業引継ぎ](handoff.ja.md): 正本の所在、再開手順、守ること
- [用語集](glossary.ja.md)
- [PDF構造化PoC最終報告](structured-document-workflow.ja.md): datasheet全体＋RM全体を、検証可能な多段中間層（ページ物理→文書論理→review）経由へ移す実測・精度評価・legacy凍結・再調査ゲート・移行計画
- [PDF→構造化文書→抽出 先行PoC](structured-extraction-poc.ja.md): 電気特性を回帰標本にした変換器比較と値一致の記録
- [evidence/README.ja.md](../evidence/README.ja.md): 表の意味・列・生成順（データ構造の正本）

## 記録（判断の根拠。読み返す用）

- [作業リストの記録](worklist-archive.ja.md): 解決済みの穴・依頼の詳細（何を直し、なぜそう判断したか）
- [抽出可能性の事前調査](extraction-survey.ja.md): EVTとdatasheetのどこを機械抽出できるかの実測、資料側の崩れの一覧
- [レジスタマップの調査](register-map-survey.ja.md): consumerのR-20に対する現状調査。機械収集ぶんは`tables/register_*.csv`に実装済み（2026-08-25）
- [WCH-Linkファームウェアの調査](link-firmware-survey.ja.md): 配布物の同定と、版番号の読み方（`wcfg = major*10 + minor`。F-11 は 2026-08-29 に解決）

配置とArduino側のconsumer境界は、`ArduinoCore-CH32`のADR-0001に記録しています。
