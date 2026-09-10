"""文字層で添字が`*`に化けたglyphの検出（exporterとparity検査が共有する1つの定義）。

一部のdatasheet/RMは、添字（V_DDのDD等）の位置に**小さなアスタリスクが印刷されている**。
2026-09-02に「ToUnicodeが添字glyphを`*`に写す破損」と記録したが、**2026-09-10に原本を
描画して確かめたところ誤りだった**——`CH32H417DS0.en` p.104 の `0.45*V*+0.41` も
`CH32V205DS0.en` p.56 の `CL = 50pF, V* = 2.7-3.6V` も、**PDFの版面そのものが `*` を
刷っている**（pypdfium2で該当セルを切り出して目視）。文字層の問題ではなく**資料側の
組版の欠落**で、描画+OCRでもfont形状解析でも復元できない（`DD` はどこにも無い）。
どのtext engineで読んでも`*`になるのは、単に版面が`*`だから。
**取りこぼしを隠さない**——人向け出力に印を出し、parity検査で印を必須にする。

判定: `*`のglyphで、**直前の実文字（`*`と空白を遡る）よりサイズが小さい**もの。
本文サイズの脚注`*`や、図中ラベルの乗算記号（`USART*8`——H417 RMの系統図。
同サイズ）は数えない。全67版の実測で806 glyph／14文書（DS群に集中）。

>>> lost_subscript_count([
...     {"text": "V", "size": 10.6}, {"text": "*", "size": 7.0}])
1
>>> lost_subscript_count([
...     {"text": "8", "size": 6.2}, {"text": "*", "size": 6.2}])
0
>>> lost_subscript_count([
...     {"text": "3", "size": 10.6}, {"text": " ", "size": 10.6},
...     {"text": "*", "size": 7.0}])
1
"""

from __future__ import annotations

SHRINK = 0.85   # 錨の文字に対してこの比以下なら添字


def lost_subscript_count(chars: list[dict]) -> int:
    count = 0
    for index, char in enumerate(chars):
        if char["text"] != "*":
            continue
        j = index - 1
        while j >= 0 and (chars[j]["text"] == "*" or not chars[j]["text"].strip()):
            j -= 1
        if j >= 0 and char["size"] <= SHRINK * chars[j]["size"]:
            count += 1
    return count
