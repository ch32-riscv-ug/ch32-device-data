# CH32 Device Data

[日本語](README.ja.md)

Normalised, machine-extracted data about WCH's CH32 microcontrollers (12 families,
27 series, 103 part numbers): `tables/*.csv` (41 tables) built from the primary
sources -- datasheets in both languages, reference manuals and the EVT packages --
plus the tools that generate the README of each family repository from them.
Every value carries its provenance (`basis`) and confidence (`confidence`).

This repository does not declare Arduino core support for any part.

Start with [tables/README.ja.md](tables/README.ja.md) (what each table and column
means), [docs/table-reliability.ja.md](docs/table-reliability.ja.md) (how far each
table can be trusted) and [docs/worklist.ja.md](docs/worklist.ja.md) (work in progress).

## Layout

- `tables/*.csv`: the normalised tables (canonical). Data columns left of `#`, provenance to the right
- `candidates/*.json`: unreviewed machine extraction, one file per SKU; the raw material of `tables/`
- `curated/`: the few hand-verified overrides (pin-table column headers, errata, series facts)
- `manifests/documents.json`: catalogue of the documents to fetch; the mirrors read it
- `tools/check_tables.py`, `tools/check_counts.py`: joins, formats and count invariants across the tables
- `tools/extract_*.py`, `tools/build_*.py`: extraction from EVT headers, datasheets and reference manuals, and table generation (run order in `tables/README.ja.md`)
- `docs/`: Japanese notes -- work list (`worklist.ja.md`), per-table reliability (`table-reliability.ja.md`), handoff, extraction survey, and the archive of resolved items

## Validation

```sh
uv run tools/check_tables.py
uv run tools/check_counts.py
```

The tools need third-party packages (pdfplumber) and run through uv, which resolves
them from `pyproject.toml` and `uv.lock`.

Official PDFs, EVT trees, legacy Arduino core sources, and hand-written legacy pin tables are not copied into this repository. Records retain URLs, hashes, revisions, and document locators instead.
