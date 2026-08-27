# Catalog (catalog/)

[日本語](README.ja.md)

The eight tables that decide **what exists and what it is called** ([docs/data-layout.ja.md](../docs/data-layout.ja.md) (Japanese)).
Every other table (evidence `evidence/`, index `index/`) joins on the names defined here -- family, series, part number,
package, core, document, and mirror version. Adding or renaming a name propagates to every table, so it is done by
recording it in the [worklist](../docs/worklist.ja.md) (Japanese).

`products.csv` holds, in addition to identification (part number, series, family, package, the datasheet it is listed in),
the main specifications (flash, SRAM, GPIO count, temperature) obtained by cross-checking the comparison table against the
ordering table, **with per-column confidence and basis**. The reader-friendly comparison table for users is the index's
[`index/parts.csv`](../index/README.md).

`toolchains.csv` alone is not a key for the other tables: it records **the versions of the upstream tools** and joins nothing.

`tools/build_tables.py` generates products/packages/series/families/cores, `tools/build_documents.py`
generates documents, `tools/build_sources.py` generates sources, and `tools/build_toolchains.py` generates toolchains. For how to read confidence and basis, see
"Criteria for confirmed" and "Kinds of basis" in [evidence/README.md](../evidence/README.md).

### `families.csv` -- top level

One row per family. Which series it contains, and which datasheets, reference manuals and EVTs apply. The document mapping is taken from `manifests/documents.json`, which is synchronised daily. Start here for the overall picture.

### `series.csv`

One row per series (CH32V006, CH32V203, ...). Holds the core and ISA, and only the values shared by every package under it. Values that vary by package are left empty as `varies-by-package` and go down to products.csv (**empty here does not mean unknown**: the Series table of the generated README lists every value the parts have instead, as `128K/256K`). **Series and datasheets are not one-to-one** (CH32V203CCT6 is listed in CH32V205DS0).

### `products.csv`

One row per orderable part number. Holds only product-specific values such as flash, GPIO count and temperature; **dimensions are looked up in packages.csv by package name**. `listed_as` is the abbreviation used in the comparison table (`CH32V208CB` -> `CH32V208CBU6`; the wildcard `C6x6` -> C6T6/C6U6).

`flash_bytes` is **the region that executes with zero wait** (the amount that goes into `FLASH` in the linker script).
The CH32V303/305/307 datasheets have "Code FLASH（字节）480K" and "Flash（字节）256K" in
separate columns; the former is the whole program flash on the die, the latter is the zero-wait region.
When two columns map to the same field, **the more specific spelling is promoted** and
the loser is dropped into `product_attributes.csv` (480K is also a fact, so it is not deleted).
For parts that can be repartitioned, see `memory_configs.csv`.

**`flash_bytes` for CH32X305/X315 is 192K.** The comparison table has only one column, 480K, and
the split is in the footnote prose ("480KB闪存包含192KB的零等待程序运行区域").
Since the sentence states both the total and the zero-wait amount, the zero-wait side is taken from it
(480K remains in `product_attributes.csv` as `code_flash_bytes`).
All seven `Link.ld` files in the EVT are also based on 192K. CH32H41x does not fit this pattern --
the comparison-table column calls itself "非零等待Code FLASH", and **there is no FLASH that runs with zero wait**
(the zero-wait code region is in the ITCM on the SRAM side).

`sram_bytes`, conversely, **was underestimated**. The CH32H41x datasheet does not put the total in the table
but splits it into three rows: ITCM 128K, DTCM 256K, and a shared region of 512K. The total of 896KB
matches the body text stating a built-in SRAM total of 896 KB (F-15). The three rows are
kept in `product_attributes.csv`.

### `packages.csv`

The **master table**, one row per package name. Body size, pin pitch and lead count are attributes of the package, so they are normalised here and not carried in products. The basis is the aggregate of the ordering-table entries of every product, plus the tables of contents in both languages of PACKAGE.PDF (the package dimension drawings, mirrored in `WCH-common`), plus the digits in the package name. If a package of the same name claims different dimensions across families, it shows up as a conflict (currently 0). Only the lead counts of QFN26C3 and QSOP24 are reference (they disagree with the pin definition table = suspected dropped rows in extraction, `?pin-table`).

### `cores.csv`

One row per QingKe core. Holds the core's ISA specification (from the overview table in the core manual, confirmed in both languages) and which manual it is described in. The ISA in series.csv is the statement of the chip-side datasheet and expresses how the chip chose the optional implementation parts of the core (such as [M][B] on V3B), so it is a separate fact from the ISA in cores.csv.

### `documents.csv`

One row per document. Since a name like `CH32L103DS0.PDF` alone does not tell where it is, it holds **the original page (.html), the download URL and the mirror (GitHub raw) URL for Chinese and English respectively**, plus the version number. It is a complete catalog that also lists excluded documents with a `status`. Because the EVT (ZIP) archive itself is not placed on the mirror, the mirror URL points to the extracted tree.

### `sources.csv`

**Which version of the originals was read to generate this.** One row per family.

This repository does not hold the originals itself; it reads the PDFs and EVTs of
**separate git repositories (mirrors)** at `/home/mt/dev_wch/<FAMILY>/`. The mirrors are re-fetched from WCH
and committed/pushed by GitHub Actions every day at 15:07 UTC, so **the input moves on its own**.
Without recording the version, there is no way to tell whether a difference in the generated output was caused by

1. a change to the extraction code
2. an update to the mirror
3. someone forgetting to regenerate

`tools/build_all.py` produces no diff no matter how many times it is run when the input and the code are the same
(measured), so **as long as the version is recorded, a diff can be narrowed down to 1 or 3**.

**The generation time is not included.** Including it would change the rows on every run, and the very test
"a diff means something is wrong" would become unusable. Only the commit hash and the date carried by
that commit itself are recorded -- neither moves on re-execution.

`dirty` is a flag that the mirror had uncommitted changes; for rows where it is set,
**the commit hash does not describe what was read**. `tools/check_tables.py` fails on it.

This table is run as part of the series of runs that rebuild `evidence/`. It may be run after synchronising the mirrors,
either before or after generation, but **do not synchronise in the middle of generation**.


### `toolchains.csv` -- versions of the upstream tools

One row per file that MounRiver currently calls the latest: the IDE (MounRiver Studio), the RISC-V
toolchain (`MRS_Toolchain_*`) and the vendor chip-support packs -- the tools needed to build
ArduinoCore-CH32. `.github/workflows/toolchains.yml` refetches it weekly.

The versions are published only on <https://www.mounriver.com/download>, but that page is a Vue SPA
whose content comes from a public JSON API (`https://api.mounriver.com/mountriver/api/version/…`).
The docstring of `tools/build_toolchains.py` records which endpoint returns what.

| column | meaning |
|---|---|
| `kind` | `toolchain` (`MRS_Toolchain_*`) / `ide` / `ide-community` / `components` (vendor chip-support pack) |
| `edition` | For the IDE, the product line (`mrs1` / `mrs2` / `community`); for `components`, the **vendor** (`wch` and others). Empty for `toolchain` |
| `os` / `arch` | `windows`, `linux`, `macos` / `x86`, `x64`, `arm64`. The vocabulary is normalised here, not upstream's spelling (`MAC`, `X64`). Where upstream states no bits, it is taken from **the word in the file name** (empty when neither states it) |
| `version` | Upstream's version number. For `components` alone it is a running index (`verIndex`); the date of the artefact itself is in the file name |
| `size_bytes` | The size actually served (checked with a HEAD at generation time) |
| `released` | The date upstream lists |
| `download_api` | **The API that returns a URL.** Calling it yields a download URL valid at that moment |

**It holds no direct download URL.** Upstream's URLs are signed and **bound to the requesting IP**
(`?sign=…&from=<IP>`), so a URL copied into the table answers 403 from any other host. The table
carries the URL-returning API instead. A consumer does this:

```sh
curl -s "$(grep MRS_Toolchain_Linux catalog/toolchains.csv | cut -d, -f9)" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"])'
```

Confidence comes from two sources, the listing and the file store. `confirmed` = the listed file is
actually served (the signed URL resolves and HEAD answers 200; where upstream states a size, it
matches), `conflict` = the size served differs from the one listed, `reference` = listing only
(`--no-verify`).

**Older versions are not in the table** (it holds only what is current). For the IDE, upstream's
archive is printed by `uv run tools/build_toolchains.py --history`. For the toolchain, upstream's API
does not keep one; older builds are in the releases of
[ch32-riscv-ug/MounRiver_Studio_Community_miror](https://github.com/ch32-riscv-ug/MounRiver_Studio_Community_miror/releases)
(1.91, 1.92).

Note this is a different thing from what the [worklist](../docs/worklist.ja.md) (Japanese) excludes --
the **per-chip support status** of toolchains. That would have to be transcribed by a person with no
way to detect staleness. This is upstream's own list of versions, refetched by machine every week,
and the run goes red when upstream breaks.


## Join keys across all tables

`tools/check_tables.py` mechanically checks that every reference can be joined:

```
series.family / products.family / packages.families   → families.family
products.series                                        → series.series
products.package                                       → packages.package
series.core / families.cores                           → cores.core
pins.part_number / pin_functions.part_number           → products.part_number
product_attributes.part_number                          → products.part_number
index/pinout.(part_number, pad, pin)                    → pins.(part_number, pad, pin)
index/pinout.(part_number, pad, route, signal)          → pin_functions.(the same 4-tuple; some rows take route from the RM grid instead)
remap_fields.series                                     → series.series
remap_routes.(series, selector)                         → remap_fields
clock_configs.family / clock_prescalers.family / clock_sources.family → families.family
clock_symbols.family / clock_init.family / evt_variants.family → families.family
clock_configs.(family, hpre|ppre1|ppre2)                → clock_prescalers.(family, field, divider)
clock_configs.(family, each symbol of pll|outside_rcc)  → clock_symbols.(family, symbol)
macro in clock_configs.condition / clock_sources.condition → evt_variants.(family, macro)
evt_variants.part_number                                → products.part_number
memory_configs.part_number                              → products.part_number
pin_alternate.family                                    → families.family
interrupts.family / memory_map.family / features.family / sources.family → families.family
eval_boards.family / feature_tags.family                → families.family
eval_boards.parts                                       → products.part_number
feature_tags.series                                     → series.series
features.series                                         → series.series
macro in interrupts.condition                           → evt_variants.(family, macro)
pin_functions(route=af-N).part_number+pad               → pin_alternate.family+pad
errata.series / operating_conditions.series             → series.series
evt_examples.family                                     → families.family
*.datasheet(s) / families.reference_manuals / families.evt / cores.manual → documents.document
```

The pins tables are generated by `tools/build_pins.py`, the remap tables by `tools/build_remap.py`, the clock tables by `tools/build_clock.py`, operating_conditions.csv by `tools/build_operating.py`, evt_variants.csv by `tools/build_evt_variants.py`, systick.csv by `tools/build_systick.py`, pin_alternate.csv by `tools/build_pin_alternate.py`, eval_boards.csv by `tools/build_eval_boards.py`, feature_tags.csv by `tools/build_feature_tags.py`, sources.csv by `tools/build_sources.py`, interrupts.csv by `tools/build_interrupts.py`, memory_map.csv by `tools/build_memory_map.py`, features.csv by `tools/build_features.py`, memory_configs.csv by `tools/build_memory.py`, link_firmware.csv by `tools/build_link_firmware.py`, and everything else by `tools/build_tables.py`.
