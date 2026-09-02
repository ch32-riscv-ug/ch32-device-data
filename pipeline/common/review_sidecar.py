"""L2 review sidecarの読み手（正本は`structured/<stem>.<lang>/review.json`）。

sidecarは**人の判断**を持つ: 文書全体の`status`と、block（表）IDごとの
`decisions`（approved／rejected・canonical番号・note。schemaは
`schemas/structured-document-review.schema.json`）。書くのは人
（`pipeline/review/record_decision.py`）で、変換は上書きしない。

新経路の抽出器はここを通して**rejectedのblockを正本生成から外す**
（D16の完了条件(3)「未承認blockを正本生成に使わない」の実行部）。sidecarの
`source_sha256`がmanifestの原本と違ったら**流用せず止まる**（同(5)。converterの
再変換ゲートと同じ判定を読む側でも行う——sidecarだけ古いまま残る事故を防ぐ）。

>>> rejected_ids("no-such-document")   # sidecarが無い文書は空集合
set()
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STRUCTURED = REPO / "structured"


def load(name: str) -> dict:
    """文書のsidecar。無ければunreviewedの空。原本が違えば止まる。"""
    path = STRUCTURED / name / "review.json"
    if not path.exists():
        return {"status": "unreviewed", "decisions": {}}
    review = json.loads(path.read_text(encoding="utf-8"))
    manifest_path = STRUCTURED / name / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if review.get("source_sha256") != manifest["source"]["sha256"]:
            raise SystemExit(
                f"{path}: source hash differs from the manifest -- the original "
                "changed; review it against the new original first")
    return review


def rejected_ids(name: str) -> set[str]:
    """rejectedと判断されたblock ID（表のID）の集合。"""
    return {block_id for block_id, decision in load(name)["decisions"].items()
            if decision.get("status") == "rejected"}
