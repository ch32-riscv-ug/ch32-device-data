#!/usr/bin/env python3
"""bundle のページを読む共通の入口（新経路の抽出器が使う。D18工程5の切替先）。

凍結tool（`tools/build_*.py`）は `pdfplumber.open(pdf)` → `pdf.pages` → `page.extract_text()`
の形で原本を読み、`run_patched.py` が `pdfplumber` を `pdfcompat` に差し替えて bundle を
読ませていた。退役した抽出器は**差し替えを介さず bundle を直接読む**ので、その入口をここに
1つ置く（3本目の退役から。それまでは各抽出器が同じ10行を持っていた）。

- `pages(name)` / `texts(name)`: manifest の順にページ record を返す。**ページの sha256 を
  manifest と照合する**（`pdfcompat.Page._load` と同じ入口ゲート——変換中で一部だけ
  書き換わった bundle を読まない。2026-09-09 に走行中の bundle を読んで実際に発火した）
- `rm_bundles(family)`: family → {lang: (bundle dir, 原本のPDF名)}。**目録**
  （`catalog/documents.csv` の `repositories`）で引く。凍結toolは mirror の
  `datasheet_{lang}/*RM.PDF` の先頭を採っていたが、mirror は目録を読んで原本を落とすので
  同じ文書になる（12 family 全部で一致を確認済み。2026-09-09）

**原本と bundle の対応は `regenerate.py` の前後照合（`check_sources`）が保証する**——ここで
PDF は開かない。だから据え置き（`--hold-sources`）のときもゲートと食い違わない（凍結tool側は
`held_sources` で照合を省く必要があった）。
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUNDLES = REPO / ".cache" / "structured-bundles"


def manifest(name: str) -> dict:
    """bundle の manifest。無ければ止まる（**PDFへ黙って落ちない**）。"""
    path = BUNDLES / name / "manifest.json"
    if not path.exists():
        raise SystemExit(f"{name}: bundle が無い（{path}）——"
                         "`uv run pipeline/ingest/convert_all.py` で変換してください "
                         "（抽出は原本PDFへfallbackしません）")
    return json.loads(path.read_text(encoding="utf-8"))


def load_page(name: str, entry: dict) -> dict:
    """manifest の項目から1ページ。**sha256 を照合する。**"""
    payload = (BUNDLES / name / entry["file"]).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != entry["sha256"]:
        raise SystemExit(f"{name}/{entry['file']}: sha256 {actual[:12]} != manifest "
                         f"{entry['sha256'][:12]}——bundle を作り直してください")
    return json.loads(payload)


def load_geometry(name: str, entry: dict) -> dict:
    """ページの字形（gzip）。hashは**非圧縮のJSON**に対して照合する。"""
    payload = gzip.decompress((BUNDLES / name / entry["geometry_file"]).read_bytes())
    actual = hashlib.sha256(payload).hexdigest()
    if actual != entry["geometry_sha256"]:
        raise SystemExit(f"{name}/{entry['geometry_file']}: sha256 が manifest と違う"
                         "——bundle を作り直してください")
    return json.loads(payload)


def pages(name: str, limit: int | None = None):
    """ページ record を manifest の順に。`limit` は先頭N枚（`pdf.pages[:N]`と同じ）。"""
    for entry in manifest(name)["pages"][:limit]:
        yield load_page(name, entry)


def texts(name: str, limit: int | None = None):
    """(ページ番号, ページ本文) を manifest の順に。`page.extract_text()` の置き換え。"""
    for page in pages(name, limit):
        yield page["number"], (page.get("text") or "")


def extracted_tables(page: dict) -> list[list[list[str | None]]]:
    """ページの表を`Table.extract()`の平坦化行で返す（`page.extract_tables()`の置き換え）。

    `extracted_rows`は**pdfplumberが返したそのまま**——converterの修復は`cells`側に閉じている
    （converter 1.14.0で確定した契約）。この面を読む抽出器は、凍結toolと同じ行列を見る。
    """
    return [table["extracted_rows"] for table in page.get("tables", [])]


def captioned_tables(page: dict) -> list[tuple[str, list[list[str | None]]]]:
    """ページの表を`(表題, 平坦化行)`で返す。**pdfplumberには無い面**——`extract_tables()`は
    表題を持たないので、凍結toolは「ページ本文に見出し語が出るか」でしか表を選べなかった。
    bundleは表ごとに表題を持つ（converterが対応付けたもの）ので、**表そのもの**を選べる。
    """
    return [((table.get("caption") or {}).get("text") or "", table["extracted_rows"])
            for table in page.get("tables", [])]


def documents(kind: str) -> list[dict]:
    """目録の assigned な文書（`kind`で絞る）。文書名順。"""
    with (REPO / "catalog" / "documents.csv").open(newline="", encoding="utf-8") as f:
        return sorted((row for row in csv.DictReader(f)
                       if row["kind"] == kind and row["status"] == "assigned"),
                      key=lambda row: row["document"])


def rm_bundles(family: str) -> dict[str, tuple[Path, str]]:
    """family → {lang: (bundle dir, 原本のPDF名)}。目録で`repositories`にfamilyを含む
    reference-manual（複数なら文書名順の先頭＝凍結toolの`sorted(glob)[0]`と同じ）。"""
    out: dict[str, tuple[Path, str]] = {}
    docs = [row for row in documents("reference-manual")
            if family in row["repositories"].split(";")]
    for lang in ("zh", "en"):
        for row in docs:
            if row[f"version_{lang}"]:
                out[lang] = (BUNDLES / f"{Path(row['document']).stem}.{lang}", row["document"])
                break
    return out
