# 文書一覧

## いま使うもの

- [作業リスト](worklist.ja.md): 生きている項目・既知の穴・**次の作業の優先順**・資料側の問題台帳
- [テーブル別の信頼度](table-reliability.ja.md): 表ごとにどこまで信用してよいか、原典サンプル検証の結果
- [データの区分・形式・置き場所の定義](data-layout.ja.md): 目録 `catalog/`・証拠 `evidence/`・索引 `index/` の3区分と、その規則・形式・consumer の契約（2026-08-26 実施）。確認の記録は [worklist-archive](worklist-archive.ja.md) の「表の役割の確認」
- [作業引継ぎ](handoff.ja.md): 正本の所在、再開手順、守ること
- [用語集](glossary.ja.md)
- [evidence/README.ja.md](../evidence/README.ja.md): 表の意味・列・生成順（データ構造の正本）

## 記録（判断の根拠。読み返す用）

- [作業リストの記録](worklist-archive.ja.md): 解決済みの穴・依頼の詳細（何を直し、なぜそう判断したか）
- [抽出可能性の事前調査](extraction-survey.ja.md): EVTとdatasheetのどこを機械抽出できるかの実測、資料側の崩れの一覧
- [レジスタマップの調査](register-map-survey.ja.md): consumerのR-20に対する現状調査。機械収集ぶんは`tables/register_*.csv`に実装済み（2026-08-25）
- [WCH-Linkファームウェアの調査](link-firmware-survey.ja.md): 版番号が確定しない理由（F-11）

配置とArduino側のconsumer境界は、`ArduinoCore-CH32`のADR-0001に記録しています。
