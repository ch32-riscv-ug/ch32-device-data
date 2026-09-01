"""図のcaption行の判定（renderer・exporter・parity検査が共有する1つの定義）。

`Figure N-N`／`图N-N`で**始まる**行にはcaptionと本文の参照文の両方がある——
「图19-2是I2C模块功能框图。」「Figure 22-17 illustrates how ...」は文章で、
図がその場に無いのは当然だから、警告もasset探索も要らない。区別:

- 全角句点`。`を含む行は文章（captionは句点で終わらない）
- 番号の直後が参照の言い回し（zh: 所示/是/说明/描述/给出/展示/显示/和、
  en: shows/is/are/illustrates/describes/depicts/gives/presents/explains/
  below/above——小文字のみ。captionの題名はTitle Caseで始まる）なら文章
- **半角ピリオドで終わる行も文章**——折り返しで行頭に残った参照の尻尾
  （「…see figure 21-1.」の`figure 21-1.`）や「Figure 6-1, the block diagram
  … watchdog.」がこれ。67版の全行で実測して、ピリオドで終わる本物の
  captionは0、該当13行は全部が参照文だった（2026-09-01）

>>> bool(caption_match("图12-6 4通道同步注入转换"))
True
>>> bool(caption_match("图19-2是I2C模块功能框图。"))
False
>>> bool(caption_match("Figure 1-1 System block diagram"))
True
>>> bool(caption_match("Figure 22-17 illustrates how the RX-FIFO is managed"))
False
>>> bool(caption_match("图8-1 中断映射结构"))
True
>>> bool(caption_match("figure 21-1."))
False
>>> bool(caption_match("Figure 38-2: SWP Bus States."))
False
>>> bool(caption_match("图40-15和图40-16显示了异步存储器释放WAIT之后，在存储器访问阶段增加的HCLK时钟周期"))
False
"""

from __future__ import annotations

import re

CAPTION = re.compile(r"^(?:Figure|图)\s*(\d+(?:-\d+)*)", re.IGNORECASE)
ZH_REFERENCE = re.compile(r"^\s*(?:所示|是|说明|描述|给出|展示|显示|和)")
EN_REFERENCE = re.compile(r"^\s+(?:shows|is|are|illustrates|describes|depicts"
                          r"|gives|presents|explains|below|above)\b"
                          r"|^\s*[~～]")  # 範囲参照「Figure 40-3 ~ Figure 40-15)」の折り返し


def caption_match(text: str) -> re.Match | None:
    stripped = text.strip()
    match = CAPTION.match(stripped)
    if not match:
        return None
    if "。" in stripped:
        return None
    tail = stripped[match.end():]
    if ZH_REFERENCE.match(tail) or EN_REFERENCE.match(tail):
        return None
    if tail.rstrip().endswith("."):
        return None
    return match
