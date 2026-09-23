#!/usr/bin/env python3
"""データシート横断のエラッタ収集スキャナ（用途別・単体実行）。

ミラーのデータシート（既定は DS0、--rm でリファレンスマニュアルも）から
ロット依存・シリコン版依存・訂正系の記述を機械的に抽出し、
curated/errata.csv の match 列（正規表現）と照合して KNOWN / NEW を表示する。

エラッタは後から増える可能性があるため、データシート更新後などに
単体で実行して NEW が出ないか確認する運用:

    uv run pipeline/extract/scan_errata.py         # DS0 のみ
    uv run pipeline/extract/scan_errata.py --rm    # RM も走査

NEW が出たら curated/errata.csv に行を追加し（match 列にその記述を
識別する正規表現を書く）、再実行して NEW: 0 になることを確認する。
match は「リポジトリ相対パス + 空白 + 前後文脈」に対して検索される。

終了コード: NEW 候補があれば 1、なければ 0。

読み手は `pipeline/extract/bundle_pages.py`（sha 照合つき。凍結 `tools/scan_errata.py` の
移植＝退役 第11号）。使うのはページ本文だけ。

**出力の mirror 相対パスは変えない**——`curated/errata.csv` の `match` はこの文字列
（`CH32V003/datasheet_zh/CH32V003DS0.PDF` ＋ 文脈）に対して掛かるので、綴りが変わると
KNOWN が NEW に化ける。凍結版は mirror を glob していたが、こちらは目録
（`catalog/documents.csv` の `repositories`）から同じ並びを組む——**DS のみ34件・RM 込み58件が、
順序まで含めて glob と一致する**ことを実測で確かめた（`CH32FV2x_V3xRM.PDF` だけ2つの
repository に載るので2回走るのも凍結版と同じ）。
"""

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "extract"))

import bundle_pages  # noqa: E402

MIRRORS = Path("/home/mt/dev_wch")

# エラッタらしさのシグナル。広すぎる語（注/Note 単独など）はノイズに
# なるため、ロット・版数・訂正の文脈を示す語だけに絞る。
PATTERNS = {
    "zh": re.compile(r"批号|批次|勘误|倒数第|流片|芯片版本"),
    "en": re.compile(
        r"lot\s*number|batch\s*(?:number|code)|errat|penultimate"
        r"|silicon\s*(?:revision|version)|chip\s*version",
        re.IGNORECASE,
    ),
}
WINDOW = 160  # マッチ位置の前後をこの文字数だけ文脈として拾う


def load_known():
    """curated/errata.csv の match 列 → [(id, compiled_regex)]"""
    known = []
    with (REPO / "curated/errata.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("match"):
                known.append((row["id"], re.compile(row["match"])))
    return known


def source_kind(row: dict) -> str:
    """その行の出所が**いまの資料に文として在るはず**かどうか。

    - `measured` … 実機で測った行（`source_zh` が `measured 2026-09-22 (…)`）。
      資料に文が無いのが正しい（x035 の open-drain 2件）
    - `edition` … 出所が**過去の版**を名指す行（`CH32H417DS0.PDF@V1.8 p.4`）。
      WCH がその注記を後の版で消したもので、いまの版に無いのが正しい
    - `rm` … 出所が application manual の行。既定の走査（DS のみ）では見えないので、
      `--rm` の全走査でだけ判定する
    - `document` … それ以外。いまの資料のどこかに `match` が当たらなければ
      **台帳が根拠を失っている**

    >>> source_kind({"source_zh": "measured 2026-09-22 (x)", "source_en": ""})
    'measured'
    >>> source_kind({"source_zh": "CH32H417DS0.PDF@V1.8 p.4", "source_en": ""})
    'edition'
    >>> source_kind({"source_zh": "CH32H417RM.PDF p.374", "source_en": "CH32H417RM.PDF p.440"})
    'rm'
    >>> source_kind({"source_zh": "CH32X315DS0.PDF p.6", "source_en": "CH32X315DS0.PDF p.8"})
    'document'
    """
    sources = [row.get(f"source_{lang}", "").strip() for lang in ("zh", "en")]
    sources = [x for x in sources if x]
    if sources and all(x.startswith("measured ") for x in sources):
        return "measured"
    if sources and all("@V" in x.split(" ", 1)[0] for x in sources):
        return "edition"
    if sources and all("RM" in x.split(" ", 1)[0] for x in sources):
        return "rm"
    return "document"


def load_kinds() -> dict[str, str]:
    with (REPO / "curated/errata.csv").open(encoding="utf-8") as f:
        return {row["id"]: source_kind(row) for row in csv.DictReader(f)}


def scan_pdf(bundle, lang):
    """ページ全文に対して finditer し、行またぎのマッチも文脈窓で拾う。"""
    hits = []
    pat = PATTERNS[lang]
    for page_number, text in bundle_pages.texts(bundle):
        last_end = -1
        for m in pat.finditer(text):
            if m.start() < last_end:  # 直前の窓に含まれる分は割愛
                continue
            lo = max(0, m.start() - WINDOW)
            hi = min(len(text), m.end() + WINDOW)
            last_end = hi
            snip = " / ".join(
                s.strip() for s in text[lo:hi].splitlines() if s.strip())
            hits.append((page_number, snip))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rm", action="store_true",
                    help="リファレンスマニュアル(RM)も走査する")
    ap.add_argument("--only", help="ファイル名の部分一致でPDFを絞る")
    args = ap.parse_args()

    known = load_known()
    # 目録から mirror の並びを組む（glob と順序まで一致することを実測済み）。
    rows = bundle_pages.documents("datasheet") + bundle_pages.documents("reference-manual")
    repos = sorted({r for row in rows for r in row["repositories"].split(";")}
                   & {p.name for p in MIRRORS.glob("CH32*")})
    targets = []
    for repo in repos:
        for lang in ("zh", "en"):
            for row in sorted(rows, key=lambda r: r["document"]):
                document = row["document"]
                if repo not in row["repositories"].split(";"):
                    continue
                bundle = f"{Path(document).stem}.{lang}"
                if not (bundle_pages.BUNDLES / bundle / "manifest.json").exists():
                    continue
                if "RM" in document and not args.rm:
                    continue
                if args.only and args.only not in document:
                    continue
                targets.append((f"{repo}/datasheet_{lang}/{document}", bundle, lang))

    new_count = 0
    found_ids = set()
    for rel, bundle, lang in targets:
        try:
            hits = scan_pdf(bundle, lang)
        except Exception as exc:  # 壊れたPDFはスキップして報告
            print(f"{rel}: 読み取り失敗 {exc}", file=sys.stderr)
            continue
        for page_no, snip in hits:
            target = f"{rel} {snip}"
            labels = [kid for kid, kre in known if kre.search(target)]
            if labels:
                found_ids.update(labels)
                print(f"{rel} p.{page_no} [KNOWN:{';'.join(labels)}]")
            else:
                new_count += 1
                print(f"{rel} p.{page_no} [NEW]")
                print(f"    {snip[:320]}")

    known_ids = {kid for kid, _ in known}
    missing = known_ids - found_ids
    print()
    print(f"既知 {len(known_ids)} 件中 {len(known_ids) - len(missing)} 件を"
          f"データシート上で確認")
    # **未確認を種類で分ける。** 以前はまとめて印字するだけで終了コードに効かず、
    # `--verify` は緑のまま通っていた——台帳の行が根拠を失っても誰も気づかない
    # （2026-09-23: `h41x-*` の2件は CH32H417DS0 V1.9 で注記ごと消えていた）。
    # 実測の行と過去の版を名指す行は、いまの資料に無いのが正しい。
    kinds = load_kinds()
    by_kind: dict[str, list[str]] = {}
    for kid in sorted(missing):
        by_kind.setdefault(kinds.get(kid, "document"), []).append(kid)
    if by_kind.get("measured"):
        print(f"未確認・実測の行（資料に文が無いのが正しい）: {by_kind['measured']}")
    if by_kind.get("edition"):
        print(f"未確認・過去の版を名指す行（いまの版に無いのが正しい）: {by_kind['edition']}")
    # 判定するのは**その走査が見た資料を引く行**だけ。既定（DS のみ）は `document`、
    # `--rm` の全走査は `rm` も。`--only` で絞った走査では判定しない。
    judged = [] if args.only else (["document", "rm"] if args.rm else ["document"])
    orphaned = [kid for kind in judged for kid in by_kind.get(kind, [])]
    if by_kind.get("rm") and not args.rm:
        print(f"未確認・manual を引く行（`--rm` の走査で判定する）: {by_kind['rm']}")
    if orphaned:
        print(f"**根拠を失った行**（資料を引くのに match がどこにも当たらない）: {orphaned}")
        print("  資料が注記を消したなら出所を `<文書>@V<版> p.N` にして過去の版を名指す。"
              "引き方の誤りなら match か出所を直す。")
    elif args.only and (by_kind.get("document") or by_kind.get("rm")):
        print("未確認(絞った走査のため判定しない): "
              f"{by_kind.get('document', []) + by_kind.get('rm', [])}")
    print(f"NEW 候補: {new_count} 件")
    return 1 if (new_count or orphaned) else 0


if __name__ == "__main__":
    sys.exit(main())
