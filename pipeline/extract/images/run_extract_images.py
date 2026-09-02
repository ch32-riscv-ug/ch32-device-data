#!/usr/bin/env python3
"""凍結した`tools/extract_images.py`を、原本hashの入口ゲート付きで走らせる。

extract_imagesはfamily repoの`image/`用にdatasheet/PACKAGE.PDFの図をpixelで
切り出す（`page.crop().to_image()`）。pixelのcropは原本PDFが要り、bundle互換層
（`pdfcompat`）は「意味抽出の入力ではない」としてcropを実装しない——なので
`run_patched`/`run_frozen`のようにpdfplumberをまるごと差し替える方式は使えない。

代わりに**`pdfplumber.open`だけをゲート付きに差し替える**（cropは本物のまま）。
開くPDFのSHA-256を、対応するbundle（`structured/<stem>.<lang>/manifest.json`）の
原本hashと照合し、欠落・不一致なら停止する。render_assetsの入口ゲートと同じ
考えで、「原本とbundleがずれたら検出する」という実行経路の要件を満たしつつ、
pixel描画に必要な原本PDFはそのまま読む。extract_images本体は無改変。

実行:
    uv run pipeline/extract/images/run_extract_images.py [--dry-run] [--family F] ...
    （残りの引数はextract_imagesにそのまま渡す）
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))

import pdfplumber as _real  # noqa: E402
import extract_images  # noqa: E402

BUNDLES = REPO / ".cache" / "structured-bundles"
STRUCTURED = REPO / "structured"
_LANG = re.compile(r"datasheet_(zh|en)")


def _gate(path: str) -> None:
    p = Path(path)
    m = _LANG.search(str(p))
    if not m:                       # datasheet_* 以外は対象外（保険）
        return
    name = f"{p.stem}.{m.group(1)}"
    manifest = STRUCTURED / name / "manifest.json"
    if not manifest.exists():
        raise SystemExit(f"{name}: bundleのmanifestが無い"
                         "——pipeline/ingest/convert_all.py を先に")
    committed = json.loads(manifest.read_text(encoding="utf-8"))
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    if committed["source"]["sha256"] != actual:
        raise SystemExit(f"{p}: 原本SHA-256がbundleのmanifestと違う"
                         "——原本が変わっている（再変換して確認）")


class _Gated:
    """`open`だけ原本hash照合を挟むpdfplumberの薄い包み。他は素通し。"""

    def open(self, path, *args, **kwargs):
        _gate(str(path))
        return _real.open(str(path), *args, **kwargs)

    def __getattr__(self, name):
        return getattr(_real, name)


def main() -> int:
    extract_images.pdfplumber = _Gated()
    print("[extract_images] pdfplumber.open -> hash-gated open", file=sys.stderr)
    return extract_images.main()


if __name__ == "__main__":
    raise SystemExit(main())
