#!/usr/bin/env python3
"""L2 reviewの判断を1件記録する（`structured/<stem>.<lang>/review.json`が正本）。

sidecarは**人の判断**の置き場（D16設計）。このCLIは1回の実行で1つのblock
（表）に approved／rejected を記録する。rejectedにしたblockは新経路の抽出器が
正本生成から外す（`pipeline/common/review_sidecar.py`）。

- block IDは実在するものしか受け付けない（bundleの全ページを見て確認——
  綴り間違いの判断が黙って眠るのを防ぐ）
- sidecarの`source_sha256`はmanifestの原本hash。**原本が変わったら判断は
  流用されない**（converterが再変換を止め、読む側も止まる）
- 文書の`status`は、decisionsが1つでもあれば`partial`にする（全blockの
  承認を宣言したいときは`--document-status approved`で明示）

実行:
    uv run pipeline/review/record_decision.py CH32X035RM.zh p234-table-002 rejected \
        --note "waveform boxes misdetected as a table"
    uv run pipeline/review/record_decision.py <doc.lang> <table-id> approved \
        [--canonical <table number>] [--note <text>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import convert  # noqa: E402  schemaのvalidatorを流用

BUNDLES = REPO / ".cache" / "structured-bundles"
STRUCTURED = REPO / "structured"


def table_exists(name: str, table_id: str) -> bool:
    bundle = BUNDLES / name
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["pages"]:
        page = json.loads((bundle / entry["file"]).read_bytes())
        if any(t["id"] == table_id for t in page["tables"]):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("document", help="文書名（CH32V003DS0.zh の形）")
    ap.add_argument("table_id", help="blockのID（p0234-table-002 の形）")
    ap.add_argument("status", choices=("approved", "rejected"))
    ap.add_argument("--canonical", help="canonicalの表番号（例 3-6）")
    ap.add_argument("--note", help="判断の理由（英語で。公開されるsidecarに入る）")
    ap.add_argument("--document-status", choices=("partial", "approved", "rejected"),
                    help="文書全体のstatusの明示（既定: decisionsがあればpartial）")
    args = ap.parse_args()

    committed = STRUCTURED / args.document
    manifest_path = committed / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{manifest_path}: 無い（変換済みの文書名を指定する）")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_sha = manifest["source"]["sha256"]

    if not (BUNDLES / args.document / "manifest.json").exists():
        raise SystemExit(f"{BUNDLES / args.document}: bundleが無い"
                         "——pipeline/ingest/convert_all.py を先に")
    if not table_exists(args.document, args.table_id):
        raise SystemExit(f"{args.document} に {args.table_id} という表は無い")

    review_path = committed / "review.json"
    if review_path.exists():
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review["source_sha256"] != source_sha:
            raise SystemExit(f"{review_path}: 原本が変わっている——新しい原本に"
                             "対してreviewし直すこと（判断の自動流用はしない）")
    else:
        review = {"schema_version": "0.2", "source_sha256": source_sha,
                  "status": "unreviewed", "decisions": {}}

    decision: dict = {"status": args.status}
    if args.canonical:
        decision["canonical_table_number"] = args.canonical
    if args.note:
        decision["note"] = args.note
    review["decisions"][args.table_id] = decision
    review["status"] = args.document_status or (
        "partial" if review["status"] == "unreviewed" else review["status"])

    convert.validate(review, convert.REVIEW_SCHEMA)
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    print(f"{review_path}: {args.table_id} -> {args.status} "
          f"(decisions {len(review['decisions'])}, document {review['status']})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
