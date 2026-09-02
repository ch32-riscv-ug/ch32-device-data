#!/usr/bin/env python3
"""bundleの文字取り込みを独立エンジンpypdfium2と突き合わせる（取り込み正しさの検証）。

converter(pdfplumber=pdfminer)とpypdfium2は**別実装のPDFエンジン**。両者が取る
文字のマルチセットが一致すれば、「どちらか一方のエンジンの癖で文字が化けた・
落ちた」可能性が排除できる——独立した2つの読み手が同じ文字集合に到達したという
ことだから。読み順やheader/footerの分離は両エンジンで違う（bundleは列組み・
role分離、pypdfium2は物理順）ので**順序は見ず、文字の集合だけ**を比べる。

pypdfium2には**ハイフン`-`を制御文字`\\x02`として読む癖**がある（全コーパスで実測）
ので、比較前に正規化する。それ以外の既知の癖が出たらここへ足す。

報告するのは**pypdfium2が取れてbundleが落とした文字**（＝bundleの取りこぼし候補）。
逆（bundleにしか無い文字）は、bundleが回転文字などを余分に拾えているだけで
bundleの方が完全なので、情報として数だけ出す。

全67版で実測（2026-09-02）: 正規化後の取りこぼしは**0**——bundleは独立エンジンが
取る文字を一文字残らず取り、pypdfium2側のハイフン誤読も正しく処理している。

手動運用（mirrorのPDFとpypdfium2が要る。CIには入れない——scan_erataと同じ）:
    uv run --with pypdfium2 pipeline/checks/cross_engine.py --all
    uv run --with pypdfium2 pipeline/checks/cross_engine.py CH32X035RM.en
終了コード: 取りこぼしがあれば1。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipeline" / "ingest"))
import convert_all  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"

# pypdfium2の既知の癖。左をキーに、右へ正規化してから比較する。
PDFIUM_QUIRKS = {"\x02": "-"}

# **数式・単位記号のToUnicode化け**で、bundleが落としpypdfium2がASCIIに化けて
# 出す文字（全67版で実測。2026-09-02）。元のフォントが壊れていて**どちらの
# エンジンも正しく読めていない**——pypdfium2は生グリフコードをASCIIとして出し
# （`fxxx freq(max) !`の`!`、`RAIN R !" < Ts f #$ %`の`#$%`）、pdfminerは
# マッピング不能として落とす。lost_subscriptsと同じ壊れたToUnicodeの類で、
# 文字層では復元不能。**名前と数で固定**——増えたら新種の取りこぼしとして落ちる。
KNOWN_MISSED = {
    "CH32H417RM.zh": 11,
    "CH32V103DS0.en": 3,
}


def char_multiset(text: str) -> Counter:
    return Counter(re.sub(r"\s+", "", text))


def check_document(name: str, pdf_path: Path, limit: int = 6) -> tuple[int, int]:
    import pypdfium2  # noqa: PLC0415  --with で入れる
    manifest = json.loads((BUNDLES / name / "manifest.json").read_text(encoding="utf-8"))
    pdf = pypdfium2.PdfDocument(str(pdf_path))
    missed = Counter()      # pypdfium2が取れてbundleに無い（取りこぼし）
    extra = Counter()       # bundleにしか無い（bundleの方が完全）
    missed_pages: list[int] = []
    try:
        for entry in manifest["pages"]:
            page = json.loads((BUNDLES / name / entry["file"]).read_bytes())
            bundle = char_multiset(page["text"])
            raw = pdf[entry["number"] - 1].get_textpage().get_text_bounded()
            for quirk, real in PDFIUM_QUIRKS.items():
                raw = raw.replace(quirk, real)
            other = char_multiset(raw)
            page_missed = other - bundle
            if page_missed:
                missed += page_missed
                missed_pages.append(entry["number"])
            extra += bundle - other
    finally:
        pdf.close()
    total_missed = sum(missed.values())
    known = KNOWN_MISSED.get(name, 0)
    surprise = total_missed - known
    if total_missed:
        tag = "" if surprise == 0 else f" (KNOWN {known}, NEW {surprise})"
        stream = sys.stderr
        print(f"[{name}] {total_missed} char(s) pypdfium2 read but the bundle "
              f"dropped{tag}, on pages {missed_pages[:limit]}"
              f"{' ...' if len(missed_pages) > limit else ''}", file=stream)
        for ch, n in missed.most_common(limit):
            print(f"    {ch!r} U+{ord(ch):04X} x{n}", file=stream)
    return surprise, sum(extra.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*", help="文書名（CH32X035RM.en の形）")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    jobs = {job["name"]: job for job in convert_all.targets()}
    names = list(jobs) if args.all else args.names
    if not names:
        ap.error("give document names or --all")

    surprise = 0
    total_extra = 0
    for name in names:
        if name not in jobs:
            raise SystemExit(f"unknown document {name!r}")
        new_missed, extra = check_document(name, jobs[name]["pdf"])
        surprise += new_missed
        total_extra += extra
    known = sum(KNOWN_MISSED[n] for n in names if n in KNOWN_MISSED)
    print(f"\n{len(names)} documents: {surprise} NEW char(s) missed by the bundle "
          f"(known math/unit-glyph ToUnicode breakage: {known}), "
          f"{total_extra} extra (the bundle reads more than pypdfium2 -- rotated "
          f"labels etc.)", file=sys.stderr)
    if surprise == 0:
        print("取り込みは独立エンジン(pypdfium2)と文字集合一致"
              "——既知の数式グリフ化けを除き取りこぼし0", file=sys.stderr)
    return 1 if surprise else 0


if __name__ == "__main__":
    raise SystemExit(main())
