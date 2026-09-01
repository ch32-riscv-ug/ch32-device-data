# pipeline/ -- the production structured-PDF path (D18)

[日本語](README.ja.md)

The production replacement for the direct-PDF extractors in `tools/`. The
groundwork is the [pre-implementation survey (D17)](../docs/structured-migration-survey.ja.md)
and the [D16 final report](../docs/structured-document-workflow.ja.md) (Japanese);
the design was provisionally approved on 2026-09-01. The legacy `tools/` and the
canonical CSVs are **frozen as the baseline** (ledger:
[`baseline/tables.csv`](baseline/tables.csv)); output from this path replaces
them one CSV at a time, only after old-vs-new comparison.

## Placement and persistence

| What | Where | Persisted |
|---|---|---|
| bundle (pages, geometry) | `.cache/structured-bundles/<stem>.<lang>/` | **no** -- regenerated deterministically (measured in D17) |
| manifest (source SHA-256, per-page/geometry SHA-256, engine/converter versions) | `structured/<stem>.<lang>/manifest.json` | **committed** -- the drift detector |
| review sidecar (human decisions) | `structured/<stem>.<lang>/review.json` | **committed** -- not regenerable; reconversion never overwrites it and stops if the original changed |
| baseline freeze ledger | `pipeline/baseline/tables.csv` | committed together with the freeze commit |

## Stages

```text
ingest/    PDF -> bundle (L0): convert.py (one document), convert_all.py (all 67 catalogued versions)
review/    (planned) inspection, annotation, human-readable rendering
extract/   (planned) per-domain extraction; first CSV to migrate: operating_conditions
reconcile/ (planned) zh/en pairing, old-vs-new diffs
publish/   (planned) candidate -> approved canonical CSVs
checks/    (planned) unit, fixture, old-vs-new regression
```

## What ingest fixes over the PoC (the two defects D17 pinned)

1. **Determinism**: pdfminer names anonymous inline images after `id()` (a
   memory address); those digit names are dropped -- the converter's own stable
   id (`p66-draw-image-00002`) is the identifier. Same original + same versions
   regenerate the bundle byte-identically.
2. **Repetition-based header/footer detection**: a first pass collects lines in
   the top/bottom 12% bands whose digit-folded spelling repeats **at the same
   distance from the page edge** on >= 25% of pages (min 3). The PoC's pure
   y-threshold systematically missed the Chinese editions' footers (93.8% of
   page height). The repetition check runs before the heading heuristic, and
   edge distance makes it work on rotated pages too.

Measured on CH32V003 (zh/en): text, words, tables and characters are
**identical** to the PoC bundles; only roles and image names change. The
version+page footers are caught 35/35 (en) and 30/30 (zh).

## Running

```sh
uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
uv run pipeline/ingest/convert_all.py --jobs 4    # all 67 versions, incremental
uv run tools/check_document_bundle.py .cache/structured-bundles/<stem>.<lang> \
  --source <PDF>                                  # independent verification gate
```

`convert_all` skips documents whose committed manifest already matches the
original's SHA-256 and both tool versions (`--force` reconverts everything).
The engine is pdfplumber, pinned by `uv.lock`. Cross-environment reproducibility
is checked by `.github/workflows/structured-repro.yml`.

## Baseline freeze

`baseline/tables.csv` records rows and SHA-256 of every canonical CSV (catalog
8, evidence 33, index 13, including the index manifest -- 54 files) at freeze
time. After the freeze the 19 direct-PDF tools in `tools/` stop changing, new
tools never write to the frozen CSVs directly, and a CSV switches source only
after the old-vs-new comparison passes the five acceptance criteria (survey
item 7). Unfreezing is an explicit act that re-records the ledger.
