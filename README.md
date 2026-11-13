# CH32 Device Data

[日本語](README.ja.md)

Machine-extracted data about WCH's CH32 microcontrollers (12 families, 27 series,
105 part numbers), built from the primary sources -- datasheets in both languages,
reference manuals and the EVT packages -- plus the tools that generate the README of
each family repository from it. The tables come in three kinds
([docs/data-layout.ja.md](docs/data-layout.ja.md), Japanese):

| | What | For whom |
|---|---|---|
| [`index/`](index/README.md) | **the public surface**: the key tables (families, series, parts, packages, cores), the facts published as read, and lookup tables derived from the evidence with normalised names; filter by part or feature in the viewer (`pins.html`) | users and generators |
| [`evidence/`](evidence/README.md) (15 tables) | the material the index is derived from: what the documents say, **spelled as they spell it**, every row with its provenance (`basis`) and confidence (`confidence`) | anyone checking correctness |
| [`catalog/`](catalog/README.md) (4 tables) | the part catalogue (published through `index/parts.csv`), and the documents, mirror commits and upstream tool versions the tables are built from | maintainers |

> [!IMPORTANT]
> This repository does not declare Arduino core support for any part. A part being listed in the tables does not mean it is supported.

**Where to start**: [index/README.md](index/README.md) for what to look up where,
[evidence/README.md](evidence/README.md) for what each table and column means,
[docs/table-reliability.ja.md](docs/table-reliability.ja.md) (Japanese) for how far each table can be
trusted, and [docs/worklist.ja.md](docs/worklist.ja.md) (Japanese) for work in progress.
Contributors -- people and AI agents alike -- **read [docs/handoff.ja.md](docs/handoff.ja.md) (Japanese) first**:
where the sources of record are, how to resume, what to do when a mirror gains a PDF, the rules,
and the working conventions for the structured-PDF pipeline.

## Layout

- `catalog/`, `evidence/`, `index/`: the three kinds of table above. Data columns first, then the confidence and basis columns. `pipeline/common/paths.py` is the one place that knows where each table lives
- `.cache/candidates/*.json`: per-SKU machine extraction (written by `build_all.py`; not committed; input to `extract_pin_tables`, `build_remap`, `build_tables`)
- `curated/`: the few hand-verified overrides (pin-table column headers, errata, series facts)
- `manifests/documents.json`: catalogue of the documents to fetch; the mirrors read it. Documents found only inside an EVT (PIOC, RISC8B) are in `manifests/evt-documents.json` ([manifests/README.md](manifests/README.md))
- `tools/check_tables.py`, `tools/check_counts.py`: joins, formats and count invariants across the tables
- `tools/check_docs.py`: **the row counts and hole states the documents claim**, checked against the tables and the work-list ledger. Data can be right while the prose that explains it is stale, and the stale prose is what users read (the kind of rot the 2026-08-29 audit found)
- `tools/check_viewer.js`: what `pins.html` shows, evaluated without a DOM. **The tables and the documents had checks but the display did not**, and a hole survived where the series view's Defaults looked only at the first part (G1). The only check that needs node
- `pipeline/build/extract_selectors.py`, `pipeline/extract/datasheet/extract_pins.py`, `pipeline/extract/rm/extract_remap.py`, `pipeline/extract/rm/register_fields.py`: extract candidates from EVT headers, datasheets and reference manuals
- `pipeline/build/extract_remap_fields.py`: **compiles EVT's `GPIO_PinRemapConfig()` for the host and runs it** to observe the remap field positions and route values. The only tool that reads behaviour rather than a document, and it **needs a host C compiler (`cc`)**. It reads the EVT in place and copies nothing into this repository
- `pipeline/build/build_candidate.py`: joins the output of those four tools into one candidate
- `pipeline/common/signal_vocabulary.py`: the vocabulary rules that bring each document's spelling of signal and field names to one reading. Every extraction and join tool above goes through it. `uv run pipeline/common/signal_vocabulary.py --tables evidence` prints the rules and how many rows of remap_routes.csv they cover
- `pipeline/build/extract_clock_tree.py` / `pipeline/build/build_clock.py`: read the clock setup statically from EVT's `system_ch32*.c`
  (oscillators, domain frequencies, dividers, PLL, flash latency, registers outside RCC) into
  `index/clock_configs.csv`, `clock_prescalers.csv`, `clock_sources.csv`,
  `clock_symbols.csv` and `clock_init.csv`. Only `clock_init.csv` is ordered --
  `SystemInit` is straight-line code with literal hex and no branches, so the order is transcription, not policy
- `pipeline/build/extract_addresses.py`: resolves the absolute address of `BLOCK->REGISTER` from the chain of base
  constants and the struct member offsets in the device header. A register's name does not fix its location
  (only CH32V205 calls the EXTEN register `CTLR0`, and CH32X315 puts EXTEN at a different address)
- `pipeline/build/build_systick.py`: takes the SysTick register layout from `core_riscv.h` into
  `index/systick.csv`. **CH32V103 alone has a different layout**; assume `CMP` sits where it
  does in the other families and `millis()` does not work
- `pipeline/build/build_pin_alternate.py`: where to write the AF number for **the three families without AFIO remap**
  (V205, X315, H417), into `index/pin_alternate.csv`. `pin_functions` has `af-N` in
  4,499 rows, yet nothing said where to write N. The 4-bits-per-pin rule is confirmed by reading
  the expression in EVT's `GPIO_PinAFConfig()`
- `pipeline/build/build_interrupts.py`: the interrupt vector table into `index/interrupts.csv`.
  **The source is EVT's device header, not the reference manual**: the `IRQn_Type` enumeration carries
  number, name and description. Numbers change with the variant (on CH32V20x, 61 is
  `UART4` under `_D6` and `ETH` under `_D8`), so the `#if` condition is kept in the `condition` column
- `pipeline/build/build_memory_map.py`: the address-space map into `index/memory_map.csv`,
  from EVT's `*_BASE` constants. **FLASH has two addresses** -- the header's `FLASH_BASE` and the
  linker script's `ORIGIN` point at different windows, so both are kept
- `pipeline/extract/datasheet/extract_features.py`: the peripherals each family has, into `evidence/features.csv`.
  The comparison table only has the columns that differ within a series, so it cannot give feature flags.
  This takes **the section headings of the functional-description chapter**; section numbers do not depend on
  the language, so Chinese and English match exactly
- `pipeline/extract/rm/extract_memory.py`: the FLASH/SRAM splits for parts whose boundary moves with an option byte, into
  `index/memory_configs.csv`. `flash_bytes`/`sram_bytes` in `products.csv` give only the one pair
  the datasheet comparison table prints, so **that the split can be changed at all cannot be
  read from there**. The reference manual gives the encoding and the parts it applies to, EVT's `Link.ld` gives the combinations,
  and the two are checked against each other. **There is no "factory pair"** -- the RM gives the reset value only as `x`,
  and the EVT examples do not agree on one pair
- `pipeline/build/build_link_firmware.py`: the firmware WCH distributes for its WCH-Link debuggers, into
  `index/link_firmware.csv`. No binaries, only fingerprints and where they came from.
  The distribution's version number (`wchlink.wcfg`) maps to the `major.minor` the probe reports as
  `wcfg = major*10 + minor`, checked against what `tools/read_link_version.py` reads from a probe
  ([docs/link-firmware-survey.ja.md](docs/link-firmware-survey.ja.md), Japanese)
- `pipeline/build/build_capabilities.py`: the comparison-table attributes (154 spellings, 1,741 rows) as
  a long "part × capability" index, `index/capabilities.csv`. `index/parts.csv` is wide
  and can hold only 13 of them as columns. The attribute-to-capability mapping is **an exhaustive dictionary**;
  generation fails when an attribute not in it appears (`adc` is a channel count and `adc_unit` a unit count --
  similar spellings with different meanings, which rules cannot fold)
- `pipeline/build/build_conflicts.py`: gathers the `conflict` marks of every table into `index/conflicts.csv`,
  taking from the `!` terms of `basis` the disagreeing column (`field`), the value the table kept (`kept`) and the
  other value (`alternative`)
- `pipeline/build/build_evt_variants.py`: takes part → compile-time macro (`CH32V20x_D8W` and so on) from the
  device header's comments into `index/evt_variants.csv`. Without the macro a build silently falls through to the
  default variant, so the table records which part is which
- `pipeline/build/build_index.py`: builds the index (`index/`) from the evidence and the catalogue **only**; it adds no new facts
- `pipeline/publish/regenerate.py`: **the entry point for regenerating every table**. Runs bundles → evidence → index → checks in dependency order (stages and examples under "Running" in [pipeline/README.md](pipeline/README.md))
- `docs/worklist.ja.md`: the work list (live items, known holes, priority of next work, ledger of problems in the documents)
- `docs/table-reliability.ja.md`: per-table reliability (how far each can be trusted, results of sampling against the sources)
- `docs/handoff.ja.md`: **the handoff that people and AI agents alike read first.** Where the sources of record are, how to resume, what to do when a mirror is updated, the rules, guidance for judgement calls, and the structured-PDF conventions
- `docs/worklist-archive.ja.md`: record of resolved holes and requests (what was fixed and why)
- `docs/extraction-survey.ja.md`: measurements of what can be machine-extracted, and the list of breakage in the documents

The notes in docs are in Japanese.

## Data boundaries

- The unit is the exact orderable part number. A WCH series name and the implementation family shared inside a core are not assumed to be the same
- The evidence tables copy the documents' spelling and values and do not correct them (a disagreement keeps both, marked `conflict`). Correction and vocabulary normalisation belong to the index
- No board-specific LEDs, connectors, clocks or upload settings, and no Arduino-core-specific FQBNs, variants or build flags (those are the consumer's output)
- No support tier is declared from this data
- Sibling repositories are referenced as mirrors of the primary sources. Official PDFs, EVT trees, legacy Arduino core sources and hand-written legacy pin tables are not copied into this repository; records retain URLs, hashes, revisions and document locators instead

## Validation

```sh
uv run tools/check_tables.py    # joins, formats, index ⊆ evidence, manifest across all tables
uv run tools/check_counts.py    # peripheral counts in the comparison table vs counts derivable from the pin tables
uv run tools/check_docs.py      # row counts and hole states the documents claim vs the actual tables and ledger
uv run pipeline/checks/check_doctests.py   # the specification of the normalisation rules (each module's doctests)
node tools/check_viewer.js      # what pins.html shows (evaluates its functions without a DOM)
```

The first three need **only the standard library** (uv resolves pdfplumber for the extraction tools, not for these).
`check_doctests.py` runs the doctests of `pipeline/` and `tools/` -- the specification of the normalisation rules -- so it imports the extraction tools and needs their packages.
`check_viewer.js` evaluates `pins.html`'s script without a DOM and needs `node`.

The extraction tools need third-party packages and run through uv, which resolves them from `pyproject.toml` and `uv.lock`. What can be extracted and where the documents break is summarised in the [extraction survey](docs/extraction-survey.ja.md) (Japanese).

Of the extraction tools, only `extract_remap_fields.py` uses a host C compiler (to run EVT's function).
If `cc` is on the system nothing else is needed. To keep a toolchain locally, put it in `.tools/` (gitignored).

```sh
uv run pipeline/build/extract_remap_fields.py --mirrors <parent of the EVT clones> --compare evidence
```

Reference manuals are **read in both languages and merged**, because the Chinese edition is newer
and has more (CH32X035: register fields 876→895; the CH32V407 RM exists only in Chinese).
When a scalar disagrees, the Chinese edition, read second, wins and the note records it.

The consistency of the generated tables themselves can be checked without the documents or the EVT.

```sh
uv run tools/check_tables.py                      # references between tables, and internal consistency of the remap tables
uv run pipeline/common/signal_vocabulary.py --tables evidence # signal-name vocabulary rules and their coverage
```

Running the extraction tools one at a time:

```sh
uv run pipeline/build/extract_selectors.py <EVT>/Peripheral/inc/ch32xxx.h
uv run pipeline/extract/datasheet/extract_pins.py <datasheet>.PDF --package TSSOP20
uv run pipeline/extract/rm/extract_remap.py <manual>.PDF
uv run pipeline/extract/rm/register_fields.py <manual>.PDF
```
