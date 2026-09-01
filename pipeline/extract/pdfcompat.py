"""bundleをpdfplumberの部分集合として読む互換層（本番。D18工程4）。

PoCの`tools/structured_pdf.py`のfork。凍結した抽出器のロジックを**入力だけ**
構造化bundleへ差し替えるために使う——抽出器モジュールの`pdfplumber`属性を
このmoduleに差し替えると、`pdfplumber.open(<PDFの実パス>)`がbundleを開く。

PoCとの違い:

1. **入口ゲート**（D16の設計どおり）: `open()`に**原本PDFの実パス**を渡すと、
   mirror上のPDFのSHA-256とbundleのmanifestが持つ原本SHA-256を照合し、
   欠落・不一致なら**停止する**。PDFへのsilent fallbackは無い。
2. `extract_tables()`を実装（`build_operating`が使う）。
3. bundleの置き場は`pipeline/ingest/convert.py`の既定（`.cache/structured-bundles`）。

pageの中身はmanifestのSHA-256と照合してから使う（PoCから継承）。pixelの
crop（描画）は意味抽出の入力ではないので実装しない——原本hashを固定した
別のasset rendererの仕事。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUNDLES = REPO / ".cache" / "structured-bundles"

_LANG_DIR = re.compile(r"^datasheet_(zh|en)$")


def _object(item: dict) -> dict:
    x0, top, x1, bottom = item["bbox"]
    return {"x0": x0, "top": top, "x1": x1, "bottom": bottom,
            "width": x1 - x0, "height": bottom - top,
            **({"text": item["text"]} if "text" in item else {})}


class Row:
    def __init__(self, cells):
        self.cells = cells


class Table:
    def __init__(self, record: dict):
        self._record = record
        self.bbox = tuple(record["bbox"])
        self.cells = [tuple(cell["bbox"]) for cell in record["cells"]]
        self.rows = [Row([tuple(cell) if cell is not None else None for cell in row])
                     for row in record["row_cells"]]

    def extract(self, **_kwargs):
        return self._record["extracted_rows"]


class Page:
    def __init__(self, bundle: Path, entry: dict):
        self._bundle = bundle
        self._entry = entry
        self._record = None
        self._geometry = None
        self.page_number = entry["number"]
        self.width = entry["width"]
        self.height = entry["height"]

    def _load(self) -> dict:
        if self._record is None:
            payload = (self._bundle / self._entry["file"]).read_bytes()
            actual = hashlib.sha256(payload).hexdigest()
            if actual != self._entry["sha256"]:
                raise ValueError(
                    f"{self._entry['file']}: sha256 {actual} != manifest {self._entry['sha256']}")
            self._record = json.loads(payload)
        return self._record

    def _load_geometry(self) -> dict:
        if self._geometry is None:
            payload = (self._bundle / self._entry["geometry_file"]).read_bytes()
            actual = hashlib.sha256(payload).hexdigest()
            if actual != self._entry["geometry_sha256"]:
                raise ValueError(f"{self._entry['geometry_file']}: sha256 differs from manifest")
            self._geometry = json.loads(gzip.decompress(payload))
        return self._geometry

    @property
    def rotation(self):
        return self._load()["rotation"]

    def extract_text(self, **_kwargs):
        return self._load()["text"]

    def extract_text_lines(self, **_kwargs):
        return [_object(line) for line in self._load()["lines"]]

    def extract_words(self, **_kwargs):
        return [_object(word) for word in self._load()["words"]]

    @property
    def chars(self):
        return [{**_object(item), "fontname": item["font"], "size": item["size"],
                 "upright": item["upright"]}
                for item in self._load_geometry()["chars"]]

    def _drawings(self, kind: str):
        return [_object(item) for item in self._load_geometry()["drawings"]
                if item["type"] == kind]

    @property
    def lines(self):
        return self._drawings("line")

    @property
    def rects(self):
        return self._drawings("rect")

    @property
    def curves(self):
        return self._drawings("curve")

    @property
    def images(self):
        return self._drawings("image")

    def find_tables(self, *_args, **_kwargs):
        return [Table(record) for record in self._load()["tables"]]

    def extract_tables(self, *_args, **_kwargs):
        return [table.extract() for table in self.find_tables()]

    def search(self, pattern, **_kwargs):
        compiled = pattern if hasattr(pattern, "finditer") else re.compile(pattern)
        found = []
        for line in self._load()["lines"]:
            for match in compiled.finditer(line["text"]):
                x0, top, x1, bottom = line["bbox"]
                found.append({"text": match.group(0), "x0": x0, "top": top,
                              "x1": x1, "bottom": bottom})
        return found

    def flush_cache(self):
        self._record = None
        self._geometry = None

    close = flush_cache

    def crop(self, _bbox):
        raise NotImplementedError(
            "structured pages do not contain pixels; use the hash-checked asset renderer")


class Document:
    def __init__(self, bundle: Path, source_sha256: str | None = None):
        self.bundle = bundle
        if not (bundle / "manifest.json").exists():
            raise FileNotFoundError(
                f"{bundle}: bundle is missing -- run pipeline/ingest/convert_all.py "
                "(extraction never falls back to reading the PDF)")
        self.manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest["conversion"]["scope"] != "all-pages":
            raise ValueError(f"{bundle}: extraction requires an all-pages bundle")
        if source_sha256 and self.manifest["source"]["sha256"] != source_sha256:
            raise ValueError(
                f"{bundle}: bundle was converted from a different original "
                f"({self.manifest['source']['sha256'][:12]} != PDF {source_sha256[:12]}) "
                "-- reconvert before extracting")
        self.pages = [Page(bundle, entry) for entry in self.manifest["pages"]]

    def close(self):
        for page in self.pages:
            page.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def open(path) -> Document:
    """PDFの実パス（mirror）か、bundle dirを開く。

    PDFパスを渡した場合が**入口ゲート**: そのPDFのSHA-256とbundleのmanifestを
    照合し、bundleが欠落・古い場合は例外で停止する。
    """
    path = Path(path)
    if path.is_dir() or path.name == "manifest.json":
        return Document(path.parent if path.name == "manifest.json" else path)
    lang_dir = _LANG_DIR.match(path.parent.name)
    if not lang_dir:
        raise ValueError(f"{path}: cannot infer language -- expected .../datasheet_<lang>/<doc>")
    bundle = BUNDLES / f"{path.stem}.{lang_dir.group(1)}"
    return Document(bundle, hashlib.sha256(path.read_bytes()).hexdigest())
