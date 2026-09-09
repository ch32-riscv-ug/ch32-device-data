"""据え置いた原本の名簿（`regenerate.py --hold-sources`）。

作業の途中で mirror の PDF が動いた（`pull_inputs.py` は数時間おきに走る）とき、コード変更の検証を
「コード変更＋前の入力状態」で回すために、動いた文書だけ**前の原本の bundle のまま**据え置く。
再変換しないだけでは足りない——凍結tool（`pdfcompat.open`）と図の描画（`render_assets`）は
**原本の SHA-256 と bundle の manifest を照合する入口ゲート**を持ち、据え置いた文書では必ず
食い違う。2026-09-09 の走行では `CH32X035DS0.zh` がゲートで拒否され、`build_all` が X035 family
を**丸ごと落として**目録から消えた（families 12→11・pins 4,563→4,302…。`check_tables` の参照不整合
147件で停止）。ゲートに「この文書は知っていて据え置いている」と伝えるのがこの名簿。

`regenerate.py` が `--hold-sources` で動いた文書名を環境変数 `CH32_HOLD_SOURCES`（bundle 名の
カンマ区切り。子プロセスに継承される）に置き、読む側は `is_held(name)` で判定する:

- `pdfcompat.open`: 据え置き文書は sha 照合を省いて前の原本の bundle を開く（凍結tool の出力は
  前の原本のまま＝正本と一致する）
- `render_assets`: 据え置き文書は描画を跳ばす（原本 PDF は新しいものしか無く、bundle と合わない。
  既存の assets はそのまま）

取り込むときは `--accept-sources` で全部を新原本に揃える（別の commit）。
"""

from __future__ import annotations

import os

ENV = "CH32_HOLD_SOURCES"


def names() -> frozenset[str]:
    return frozenset(n for n in os.environ.get(ENV, "").split(",") if n)


def is_held(name: str) -> bool:
    """bundle 名（`CH32X035DS0.zh`）が据え置き中か。"""
    return name in names()
