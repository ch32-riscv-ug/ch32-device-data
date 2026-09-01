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
common/    logical_tables.py (**L1: joins the physical fragments of a page-spanning
           table into one logical table**. The decision is structural, independent of
           the converter's continuation flag: no caption, first content on its page,
           the previous page ends in a table, vertical continuity, compatible column
           structure. Columns align positionally when the fragment column counts
           match, else by the union of x-edges. Shared by review and extract)
extract/   pdfcompat.py (bundle compatibility layer + the source-hash entry gate;
           no silent fallback to the PDF)
           datasheet/run_operating.py (runs the frozen extraction logic on bundle
           input; reproduces evidence/operating_conditions.csv **byte-identically**,
           all 1,588 rows -- measured 2026-09-01)
           datasheet/extract_low_power.py (A11: consumption current and wake-up
           times; caption-scoped selection, fragment joining, two-phase zh/en pairing
           -- zero false conflicts)
           datasheet/build_operating_conditions.py (**generator of record for
           operating_conditions.csv**: frozen-logic base + A11 rows. Accepted
           2026-09-01 -- the **first CSV switched over**, 2,796 rows)
           manual/extract_debug_wiring.py (**generator of record for
           debug_wiring.csv** -- the first evidence table this path added to the
           canonical set: the WCH-Link manual's wiring table + dual-support note)
           run_frozen.py (runs frozen tools unmodified on bundle input and
           byte-compares their output against the frozen CSVs -- the old-vs-new
           parity harness; the ledger is in the worklist under D18)
           run_scan_errata.py (the incremental errata scan (KNOWN/NEW) on bundle
           input; target selection stays the frozen tool's)
reconcile/ compare_csv.py (frozen-vs-candidate multiset diff: unchanged/added/changed/missing);
           zh/en pairing comes later
review/    render_assets.py (**pixel rendering of figures**: verifies the original's
           hash, then renders each figure region to a 150-dpi PNG recorded in
           assets.json with its bbox and SHA-256. Regions come from **vertical
           clusters of graphics**, not text -- in-figure labels arrive as paragraph
           lines and collapse any text-based boundary. 3,337 assets across the 67
           documents; **all 2,871 figure captions carry a real image (100%, zero
           notices)** -- a whole figure misdetected as one uncaptioned "table"
           (filter-numbering examples, waveforms, response plots) also joins the
           cluster when it sits directly below a caption.
           Prose references such as "Figure 22-17 illustrates ..." or "figure 21-1."
           are not captions -- the shared classifier lives in
           pipeline/common/figure_captions.py)
           export_markdown.py (the human-readable Markdown -- the end goal is zero
           difference against the PDF. Headers/footers fold into HTML comments, tables
           keep rowspan/colspan as HTML, **page-spanning tables are joined through L1
           and rendered in full where they start, with a visible pointer on the
           following pages** (3,770 tables joined across the 67 documents), and
           **every known gap is marked visibly in place**: a notice with a PDF page
           link after each figure caption, placeholders for large images, table-issue
           warnings, undecodable-glyph warnings)
checks/    compare_manifest.py (cross-environment reproducibility)
           check_markdown_parity.py (machine check that every body line and table cell
           reaches the Markdown in reading order and that gap notices are present --
           **all 67 documents pass**)
publish/   regenerate.py (**the single regeneration entry point**: bundle
           reconversion -> switched-over evidence -> derived index tables ->
           checks, calling the existing CLIs in order. --verify adds the frozen
           parity batch and the errata scan; --human adds figure rendering,
           the human-readable Markdown and the zero-difference check. Stops at
           the first failing stage. All stages green with a clean `git status`
           = regeneration is idempotent, measured 2026-09-01)
```

Candidates live in `.cache/pipeline-candidates/` (not committed). No tool on this
path writes to the frozen CSVs directly (**switched-over and newly added CSVs are
the exception**: `operating_conditions.csv` (switched) and `debug_wiring.csv`
(new) are generated by this path since 2026-09-01).

## What ingest fixes over the PoC (three fixes: 1-2 measured in D17, 3 caught live by CI)

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
   **1.2.0 adds two rules** (the R-30 extraction found "unclassified footer
   breaks the table chain"; a corpus measurement confirmed 67 missed lines):
   within the strict band (6%) the same spelling at the same distance qualifies
   from **3 pages** (per-chapter header variants; documents whose footer moved
   partway -- V00X RM zh has 32 pages = 14% at a different distance), and a
   qualified **spelling counts at any distance** (footers of rotated pin-table
   pages). Page-number-only lines (folded to `#`) are exempt from the new rules
   so numeric body text is never swept in.

3. **The manifest's geometry_sha256 hashes the uncompressed JSON** (converter
   1.1.0). gzip bytes vary with the zlib build, and a GitHub Actions
   reconversion differed in geometry_sha256 alone on every page (2026-09-01 --
   the first real catch by `structured-repro.yml`, doing exactly what it was
   built for). Compression is storage, not content.

Measured on CH32V003 (zh/en): text, words, tables and characters are
**identical** to the PoC bundles; only roles and image names change. The
version+page footers are caught 35/35 (en) and 30/30 (zh).

## Running

```sh
uv run pipeline/publish/regenerate.py             # bundles -> evidence -> index -> checks
uv run pipeline/publish/regenerate.py --verify --human  # + parity, errata, figures, Markdown
uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
uv run pipeline/ingest/convert_all.py --jobs 4    # all 67 versions, incremental
uv run pipeline/checks/check_bundle.py .cache/structured-bundles/<stem>.<lang> \
  --source <PDF>                          # independent verification gate (1.1.0+)
```

`convert_all` skips documents whose committed manifest already matches the
original's SHA-256 and both tool versions (`--force` reconverts everything).
The engine is pdfplumber, pinned by `uv.lock`. Cross-environment reproducibility
is checked by `.github/workflows/structured-repro.yml`.


## Preview repository (reviewing the human-readable Markdown)

`structured-markdown` is large (11k files, ~95 MB), so it is published to a
**disposable preview repository** as a single commit and read through GitHub
Pages. Recommended name: **`ch32-device-data-preview`** (in the org).

```sh
uv run pipeline/review/export_markdown.py --all   # also writes the root index
pipeline/review/publish_preview.sh ../ch32-device-data-preview
# -> https://ch32-riscv-ug.github.io/ch32-device-data-preview/
```

The script recreates an orphan branch and force-pushes it, so the repository
always holds exactly one commit and never grows. Pages' default Jekyll rewrites
relative `.md` links and serves README.md as the directory index (the output
contains none of the sequences Liquid treats specially -- double open-brace and
open-brace-percent -- verified). If the 11k-file Pages build
ever times out, github.com's file view renders the same Markdown as a fallback.

## Baseline freeze

`baseline/tables.csv` records rows and SHA-256 of every canonical CSV (catalog
8, evidence 33, index 13, including the index manifest -- 54 files) at freeze
time. After the freeze the 19 direct-PDF tools in `tools/` stop changing, new
tools never write to the frozen CSVs directly, and a CSV switches source only
after the old-vs-new comparison passes the five acceptance criteria (survey
item 7). Unfreezing is an explicit act that re-records the ledger.
