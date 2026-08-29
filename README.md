# CH32 Device Data

[日本語](README.ja.md)

Machine-extracted data about WCH's CH32 microcontrollers (12 families, 27 series,
103 part numbers), built from the primary sources -- datasheets in both languages,
reference manuals and the EVT packages -- plus the tools that generate the README of
each family repository from it. The tables come in three kinds
([docs/data-layout.ja.md](docs/data-layout.ja.md), Japanese):

| | What | For whom |
|---|---|---|
| [`catalog/`](catalog/README.md) (8 tables) | what exists and what it is called: families, series, parts, packages, cores, documents, mirror versions, upstream tool versions | the keys every other table joins on |
| [`evidence/`](evidence/README.md) (33 tables) | what the documents say, **spelled as they spell it**, every row with its provenance (`basis`) and confidence (`confidence`) | anyone checking correctness |
| [`index/`](index/README.md) | lookup tables derived from the evidence with normalised names: one file per table; filter by part or feature in the viewer (`pins.html`) | users and generators |

This repository does not declare Arduino core support for any part.

Start with [index/README.md](index/README.md) (what to look up where), then
[evidence/README.md](evidence/README.md) (what each table and column means),
[docs/table-reliability.ja.md](docs/table-reliability.ja.md) (how far each table can be
trusted) and [docs/worklist.ja.md](docs/worklist.ja.md) (work in progress).

## Layout

- `catalog/`, `evidence/`, `index/`: the three kinds of table above. Data columns left of `#`, provenance to the right. `tools/paths.py` is the one place that knows where each table lives
- `.cache/candidates/*.json`: per-SKU machine extraction written by `build_all.py` (not committed; input to `build_pins`, `build_remap`, `build_tables`)
- `curated/`: the few hand-verified overrides (pin-table column headers, errata, series facts)
- `manifests/documents.json`: catalogue of the documents to fetch; the mirrors read it ([manifests/README.md](manifests/README.md))
- `tools/check_tables.py`, `tools/check_counts.py`: joins, formats and count invariants across the tables
- `tools/check_docs.py`: the row counts and hole states the documents claim, checked against the tables and the work list -- data can be right while the prose that explains it is stale
- `tools/check_viewer.js`: what `pins.html` shows, evaluated headlessly against the committed tables -- the viewer used to be the one thing nothing checked
- `tools/extract_*.py`, `tools/build_*.py`: extraction from EVT headers, datasheets and reference manuals, and table generation (run order in `evidence/README.md`); `tools/build_index.py` derives the index
- `docs/`: Japanese notes -- work list (`worklist.ja.md`), per-table reliability (`table-reliability.ja.md`), handoff, extraction survey, and the archive of resolved items

## Validation

```sh
uv run tools/check_tables.py
uv run tools/check_counts.py
uv run tools/check_docs.py
node tools/check_viewer.js
```

The first three need only the standard library (`uv` resolves pdfplumber for the extractors, not
for these). `check_viewer.js` evaluates `pins.html`'s script without a DOM and needs `node`.

The tools need third-party packages (pdfplumber) and run through uv, which resolves
them from `pyproject.toml` and `uv.lock`.

Official PDFs, EVT trees, legacy Arduino core sources, and hand-written legacy pin tables are not copied into this repository. Records retain URLs, hashes, revisions, and document locators instead.
