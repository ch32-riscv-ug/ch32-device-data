"""文字層で添字が`*`に化けたglyphの検出（exporterとparity検査が共有する1つの定義）。

一部のdatasheet/RMは、添字（V_DDのDD等）のglyphをToUnicodeが`*`に写す壊れた
fontで組まれている——**どのtext engineで読んでも`*`になる**（pdfplumberと
pypdfium2で同一を実測。2026-09-02）。中身の復元は文字層では不可能で、
候補は描画+OCRかfont形状解析（調査報告の「欠落→追加tool」トリガーの初発火）。
まずは**取りこぼしを隠さない**——人向け出力に印を出し、parity検査で印を必須にする。

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
