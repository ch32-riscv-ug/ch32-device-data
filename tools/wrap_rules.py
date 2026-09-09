#!/usr/bin/env python3
"""行末のハイフンで割れた語を繋ぐ規則（`high-`⏎`speed` → `high-speed`）。

pdfplumber のセル文字列は版面の行で割れる。`\\n` を空白に置くだけだと `high- speed`・
`pre- division`・`General- purpose` になり、正本CSVにそのまま入っていた
（`operating_conditions` 86箇所・`product_attributes` 28箇所。2026-09-08）。

繋がないのは2つだけ:
- **左が全大文字**（2文字以上）: 記号の末尾のマイナス（`V_REF-`⏎`equal to VSS`）
- **右が接続詞・機能語**: 保留ハイフン（`both low-`⏎`and high-speed`）

全corpusの表セル112件を実測: この2条件で残るのは `REF- equal/is/should` と
`power- on`（RM の説明文。正本には届かない）だけで、他106件は全部語の折り返し
（`pull-down`・`floating-point`・`high-speed`・`pre-division`…）。

使う側: `pipeline/extract/datasheet/operating_rows.norm_text`（operating_conditions の条件文）と
`tools/extract_products`（比較表の見出し）。凍結toolの入力層ではなく**正規化層**なので、
凍結の対象外（値の解釈は変えず、綴りの結合だけ）。
"""

from __future__ import annotations

import re

HYPHEN_WRAP = re.compile(r"([A-Za-z][A-Za-z0-9]*)-\n([a-z]+)")
# 改行が既に空白へ解決された形（`General- purpose`）。読み手が先に `\n`→空白にしている経路
# （extract_products の join_wrap 等）から届く。同じガードで同じ判断をする。
HYPHEN_SPACED = re.compile(r"([A-Za-z][A-Za-z0-9]*)- ([a-z]+)")
KEEP_RIGHT = frozenset(("and", "or", "to", "of", "the", "a", "an", "in", "on", "at",
                        "by", "for", "with", "as", "is", "are", "be", "not", "but", "nor"))


def _seam(left: str, right: str) -> str:
    if (left.isupper() and len(left) >= 2) or right in KEEP_RIGHT:
        return f"{left}- {right}"
    return f"{left}-{right}"


def join_hyphen_wrap(text: str) -> str:
    """セル文字列の中の `X-\\nY` を規則で繋ぐ（それ以外の改行は触らない）。

    >>> join_hyphen_wrap("Runs in a high-\\nspeed internal RC")
    'Runs in a high-speed internal RC'
    >>> join_hyphen_wrap("greater than V\\nREF-\\nequal to VSS")
    'greater than V\\nREF- equal to VSS'
    >>> join_hyphen_wrap("both low-\\nand high-speed")
    'both low- and high-speed'
    >>> join_hyphen_wrap('Timer General- purpose (16-bit)')   # 既に空白へ解決された形
    'Timer General-purpose (16-bit)'
    >>> join_hyphen_wrap('V REF- equal to VSS')
    'V REF- equal to VSS'
    """
    text = HYPHEN_WRAP.sub(lambda m: _seam(m.group(1), m.group(2)), text or "")
    return HYPHEN_SPACED.sub(lambda m: _seam(m.group(1), m.group(2)), text)


def join_lines(parts: list[str]) -> str:
    """見出しの段（別セル）を空白で繋ぐ。ただし段の切れ目が `X-`／`y…` なら同じ規則で繋ぐ。

    >>> join_lines(["Timer", "General-", "purpose (16-bit)"])
    'Timer General-purpose (16-bit)'
    >>> join_lines(["Advanced-", "control timer"])
    'Advanced-control timer'
    """
    return join_hyphen_wrap("\n".join(p for p in parts if p)).replace("\n", " ")
