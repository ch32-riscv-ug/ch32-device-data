"""Read a structured-datasheet bundle through the pdfplumber subset we use.

This compatibility layer lets existing extractors migrate independently.  It
implements text, lines, words, characters, drawing boxes and table geometry.
Raster cropping intentionally is not emulated: rendering is a separate,
hash-checked asset step because pixels are not semantic extraction input.
"""

from __future__ import annotations

import hashlib
import gzip
import json
import re
from pathlib import Path


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
                raise ValueError(
                    f"{self._entry['geometry_file']}: sha256 {actual} != manifest "
                    f"{self._entry['geometry_sha256']}")
            self._geometry = json.loads(gzip.decompress(payload))
        return self._geometry

    @property
    def rotation(self):
        return self._load()["rotation"]

    def extract_text(self, **_kwargs):
        return self._load()["text"]

    def extract_text_lines(self, **_kwargs):
        return [{**_object(line), "text": line["text"]}
                for line in self._load()["lines"]]

    def extract_words(self, **_kwargs):
        return [{**_object(word), "text": word["text"]}
                for word in self._load()["words"]]

    @property
    def chars(self):
        return [{**_object(char), "fontname": char["font"], "size": char["size"],
                 "upright": char["upright"]}
                for char in self._load_geometry()["chars"]]

    def _drawings(self, kind: str):
        out = []
        for item in self._load_geometry()["drawings"]:
            if item["type"] != kind:
                continue
            record = _object(item)
            if "name" in item:
                record["name"] = item["name"]
            if "source_size" in item:
                record["srcsize"] = tuple(item["source_size"])
            out.append(record)
        return out

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
    def __init__(self, bundle: Path):
        self.bundle = bundle
        self.manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest["conversion"]["scope"] != "all-pages":
            raise ValueError(f"{bundle}: extraction requires an all-pages bundle")
        self.pages = [Page(bundle, entry) for entry in self.manifest["pages"]]

    def close(self):
        for page in self.pages:
            page.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def open(path) -> Document:
    bundle = Path(path)
    if bundle.name == "manifest.json":
        bundle = bundle.parent
    return Document(bundle)
