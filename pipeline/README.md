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
ingest/    PDF -> bundle (L0): convert.py (one document), convert_all.py (all 68 catalogued versions)
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
           images/run_extract_images.py (runs the frozen `extract_images` -- which
           builds each family repo's image/ -- with **only `pdfplumber.open`
           wrapped in the source-hash gate**. Pixel crops need the original PDF and
           pdfcompat cannot stand in, so the gate just checks the hash on open --
           the last direct-PDF read now meets the execution-path requirement too)
reconcile/ compare_csv.py (frozen-vs-candidate multiset diff: unchanged/added/changed/missing);
           zh/en pairing comes later
common/    review_sidecar.py (**L2: the reader of human decisions**. The committed
           record is structured/<stem>.<lang>/review.json -- approved/rejected per
           block ID, pinned to the original's SHA-256. The new-path extractors
           drop rejected blocks from canonical generation, and stop loudly when a
           required table is rejected instead of degrading silently. A sidecar
           whose original changed is never reused -- the same gate the converter
           applies on reconversion, enforced on the reading side too. Decisions
           are recorded with review/record_decision.py.
           **zh/en table pairing is automatic where caption numbers match**
           (measured 2026-09-02: 16 of 32 document pairs match completely; the
           asymmetric residue is **83 caption numbers corpus-wide**) -- the
           residue is laid out side by side with original captions by
           review/propose_pairs.py, and an approved pair gets the same
           canonical_table_number recorded on both blocks)
review/    render_assets.py (**pixel rendering of figures**: verifies the original's
           hash, then renders each figure region to a 150-dpi PNG recorded in
           assets.json with its bbox and SHA-256. Regions come from **vertical
           clusters of graphics**, not text -- in-figure labels arrive as paragraph
           lines and collapse any text-based boundary. 3,829 assets across the 68
           documents; **all 3,023 figure captions carry a real image
           (100%, zero notices)**, and uncaptioned graphics clusters containing
           rotated text (package/pinout diagrams) are rendered as standalone
           assets -- a whole figure misdetected as one uncaptioned "table"
           (filter-numbering examples, waveforms, response plots) also joins the
           cluster when it sits directly below a caption.
           Prose references such as "Figure 22-17 illustrates ..." or "figure 21-1."
           are not captions -- the shared classifier lives in
           pipeline/common/figure_captions.py)
           export_markdown.py (the human-readable Markdown -- the end goal is zero
           difference against the PDF. Headers/footers fold into HTML comments, tables
           keep rowspan/colspan as HTML, **page-spanning tables are joined through L1
           and rendered in full where they start, with a visible pointer on the
           following pages** (3,914 tables joined across the 68 documents),
           **a cell whose content was split at a page break is folded back into
           the cell above it** (`fold_boundary_spills` -- e.g. the MCO
           description's trailing `Other: No clock output.`; 1,937 cells across
           50 documents. Only rows at a page boundary qualify, since an in-page
           "one non-empty cell" row is usually a real standalone cell in a
           comparison table; the continuation cell is dropped from the grid so no
           empty row is left; exporter and parity share it, the frozen CSVs never
           see it), **a cell's internal line breaks are split by character class**
           (punctuation end -> `<br>`; identifier mid-word `USAR`+`T1` -> joined;
           English words -> space -- preserving the original's paragraphs), **the
           first table row becomes `<th>` and the original's bold/italic are
           reproduced as `<strong>`/`<em>`** (from the font; 3% bold, 3.5% italic
           measured; the text is unchanged so the frozen CSVs are untouched),
           **only a table with a real caption
           line emits a `<caption>`** (an uncaptioned table used to borrow the
           previous page's table number through continuation inheritance; the
           internal id moves to a comment),
           **register bit-field diagrams are rebuilt** (the `31 30 … 16`
           bit-number line becomes the table's header row and the bits render as
           equal-width wrapping columns; field cells are mapped to bit columns by the
           x-centres of the number glyphs -- from the geometry, so the varied
           extraction is handled uniformly whether the boxes come out as 16 empty
           columns or collapse to 8-9 with the names inside; the number line is
           taken as any strictly-descending run of >=8 values in 0..31, so
           byte-boundary diagrams (`31 24 23 16 15 8 7 0`) and non-16-wide ones
           (`11 10 … 0`) are handled too, while a side-by-side mix
           (`8 7 5 3 0 9 8 7`) is rejected; where the diagram has no ruled box a
           single full-width field line is synthesised into a header+field table;
           a field name split
           vertically by a narrow column -- `Reser`+`ved` -> `Reserved` -- is
           rejoined, while a two-mode TIM CCMR keeps its output-name row above its
           input-name row; bit-field diagrams are also kept out of the page-spanning
           table chaining (a back-to-back pair used to merge, losing the cell
           geometry the rebuild needs). A diagram **split across a page break** --
           its number line at the foot of one page, its boxes at the head of the
           next -- is paired across the break (export_markdown.document_bitfields):
           the boxes are rebuilt with the previous page's number centres and the
           number line leaves a visible "diagram on the next page" pointer. The
           shared transforms are pipeline/common/logical_tables.apply_bitfield and
           export_markdown.document_bitfields, used by the exporter, the parity
           check and the audit),
           **table cells are centre-aligned by default with long/multi-line cells
           left-aligned** (closer to the PDF),
           **cell-boundary glyph duplicates are removed** (pdfplumber's crop puts a
           glyph that straddles a cell border into both cells -- `[31:12] R`, `RO R`,
           `ReservedR`, a zh description's trailing `，` landing in the reset-value
           column. `strip_boundary_dupes` handles the text-adjacent case; for the rest
           `strip_straddling_dupes` confirms against the geometry that the specific
           glyph sits mostly in another cell whose text has it at a line edge, and
           never touches a glyph that is mostly inside its own cell -- so a name that
           overflows a narrow column (`PB14`, `SWIER22`) keeps every letter; merged
           page-spanning tables carry each cell's source page so the right page's
           glyphs are consulted), **a wrapped header (`Reset` / `value`) that
           pdfplumber split into a bogus data row is folded back into the header**
           (`fold_header_wrap`; the row indices kept by `fold_boundary_spills` are
           shifted with it), **empty grid slots not covered by a span are padded with
           `<td></td>`** so a continuation fragment that lost its first column no
           longer shifts left, **tables with no content are dropped and tables inside a
           figure region are emitted as plain text** (both are diagram boxes that the
           table finder mistook for tables; 1,115 and 3,758 across the corpus),
           **large-font body blocks that the converter marked as headings are demoted
           back to paragraphs** (a run of 3+ font-size-only headings, a `Note:`/`注：`
           lead-in, >50 characters, or a CJK sentence-ending -- 2,390 lines; numbered
           and chapter headings are never touched), **a chapter title's wrapped second
           line is joined to the first** (`(SerDes)`), **a table caption that wrapped
           onto a second line -- an unclosed parenthesis or a dangling `or`/`with` at
           the line end -- is rendered whole in `<caption>` and the continuation line
           leaves the body** (`logical_tables.caption_full`, shared with the
           operating-conditions extractor so the CSV condition prefix is whole too;
           `…SRAM (RISC-V5F` + `+ RISC-V3F)`), **a list item's own bullet is
           not doubled**, **glyphs picked twice by a bold overprint are collapsed**
           (`OOSSCC__IINN` -> `OSC_IN`; hex values are excluded), and **a figure that
           pdfium rendered blank** (embedded JPEG or palette raster in an encrypted
           PDF) **is recovered by decoding the image stream directly** in
           render_assets (11 figures were blank), and
           **every known gap is marked visibly in place**: a notice with a PDF page
           link after each figure caption, placeholders for large images, table-issue
           warnings, undecodable-glyph warnings, and **lost-subscript warnings** --
           some PDFs map subscript glyphs (the DD of V_DD) to `*` in their text
           layer (broken ToUnicode; identical under pdfplumber and pypdfium2, so
           no text engine can recover them -- 806 glyphs across 14 documents
           measured). The shared detector is pipeline/common/lost_subscripts.py
           and the parity check makes the notice mandatory)
checks/    compare_manifest.py (cross-environment reproducibility)
           check_markdown_parity.py (machine check that every body line and table cell
           reaches the Markdown in reading order and that gap notices are present --
           **all 68 documents pass**. Lines the exporter folds away are checked for
           the place they were folded into: a wrapped caption's second line must
           appear inside `<caption>`. The check sees existence and order only, so
           an export-side transform is always paired with a semantic PDF-vs-Markdown
           review as well)
           cross_engine.py (**independent verification of the text ingestion**:
           compares the bundle's character multiset against a second PDF engine,
           pypdfium2 -- order is ignored, only the set of characters. pypdfium2's
           hyphen misread (`-` -> `\x02`) is normalized. Measured across all 68
           versions: **0 characters missed** apart from 14 known math/unit-glyph
           ToUnicode breakages (garbled in both engines), pinned by name and
           count. Manual: `uv run --with pypdfium2`)
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

## What ingest fixes over the PoC (five fixes: 1-2 measured in D17, 3 caught live by CI, 4-5 from reviewing the human output)

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

4. **Vertical (90°-rotated) labels are rebuilt in reading order** (converter
   1.3.0). Package/pinout-diagram pin names come out of pdfplumber's line
   builder **mirror-reversed** (`33DDV` = VDD33), and several vertical labels
   merge into one "line". The fix splits by x0 into columns and orders each
   column by the glyph matrix direction (b=+1 reads bottom-to-top = descending
   top). Rotated lines are also excluded from the heading heuristic (a
   large-font in-figure label used to become a level-1 heading). **1.3.1
   applies the same rebuild to table cells** -- the vertical part-number
   headers of the pin-definition tables were mirror-reversed inside cells
   (`6UEW714H` = H417WEU6; 322 tables across 43 documents). The same
   version anchors the **table-caption number regex to the line start** --
   prose like "Note: the options in Table 21-4 ..." had become captions (6
   measured). page["text"] is untouched, so the frozen tools' byte-identity
   is preserved.

5. **The two columns of a datasheet's overview/features page are split**
   (converter 1.5.0). pdfplumber's line builder merges the left and right
   columns into one y-row (`- QingKe...core ● 3-group...`, unreadable).
   On datasheet pages with an `Overview/Features/概述` heading, the column
   boundary is the widest word-x0 gap in the central band, and everything
   below the heading is re-extracted left-column-then-right (the title
   stays full-width). The heading gate keeps comparison tables, bit
   diagrams and pin tables out (all 51 target pages are overview-type,
   zero false hits); pages with no clear boundary are left as is.

6. **Subscripts/superscripts are merged back into the body line**
   (converter 1.6.0). pdfplumber groups lines by top, so the `DD` subscript
   of `V` (top≈106, 7pt, **bottom aligned with the V**) drops onto its own
   line, leaving `V` and `DD` apart and `V_DD` unreadable (~4,600 across all
   datasheets). Lines smaller than the body are split into clusters by
   internal x-gap, and each cluster is inserted into the body line whose
   baseline (bottom) it matches within 2.5pt and whose x-range contains it.
   The insertion **keeps the base line's own text** and drops the subscript
   in by position -- the chars carry no spaces (`itputs`), so a gap rule
   cannot rebuild word spacing. The vacated space is closed before a symbol
   but kept before a word (so both `(VPOR/PDR)` and `VDD is` come out right).
   Multiple subscripts on one line (`V...V` with `DD`/`PVD`) are inserted
   right-to-left per cluster so positions do not drift (`VDD...VPVD`). A
   small line is merged only when every cluster lands on a body line;
   otherwise it is kept whole (no dropped glyphs). Figure micro-labels with
   no baseline-aligned body line are left separate. **Whether a line is a
   subscript is judged against the neighbouring base, not the page median**
   (`small < base * 0.82`, converter 1.6.1): a figure voltage label's `BAT`
   subscript is 8.2pt (77% of the 10.6 body -- above the global 0.72 gate) yet
   is clearly smaller than its base `V` at 11.9 (L103DS0 p36 orphans 18 -> 0).
   page["text"] is built
   by extract_text() independently, so the frozen tools' byte-identity holds.

Measured on CH32V003 (zh/en): text, words, tables and characters are
**identical** to the PoC bundles; only roles and image names change. The
version+page footers are caught 35/35 (en) and 30/30 (zh).

## Running

```sh
uv run pipeline/publish/regenerate.py             # bundles -> evidence -> index -> checks
uv run pipeline/publish/regenerate.py --full      # regenerate every CSV (frozen tools on bundle input; ~1.5h)
uv run pipeline/publish/regenerate.py --verify --human  # + parity, errata, figures, Markdown
uv run pipeline/ingest/convert.py <PDF> --lang {zh,en} --document-type <type>
uv run pipeline/ingest/convert_all.py --jobs 4    # all 68 versions, incremental
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
