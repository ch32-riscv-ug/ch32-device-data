# Index (index/)

[日本語](README.ja.md)

**Everything under `index/` is the public surface, and nothing outside it is** (see
[Contract for consumers](#contract-for-consumers)). It holds two kinds of table:

- **Facts published as read** ([Published as read](#published-as-read)): the key tables (families,
  series, packages, cores) and facts read from the documents and the EVT headers, written here
  directly by their generators.
- **Lookup tables** ([Tables](#tables)): derived by `pipeline/build/build_index.py` from the
  [evidence](../evidence/README.md) (what the documents say, spelled as they spell it), the catalog and
  the tables above, with names normalised -- and from nothing else: `tools/check_tables.py` verifies on
  every run that each lookup row can be traced back to evidence rows.

The split between `index/`, `evidence/` and `catalog/` is defined in
[docs/data-layout.ja.md](../docs/data-layout.ja.md) (Japanese).

## Where to look

| Question | Table |
|---|---|
| Which part meets my requirements? Its name, package, memory, clock, supply and peripheral counts | [`parts.csv`](parts.csv) |
| Which parts have capability X, and how many of it? | [`capabilities.csv`](capabilities.csv) |
| Where do the sources disagree with each other? | [`conflicts.csv`](conflicts.csv) |
| Which series have feature X? | [`features.csv`](features.csv) |
| What is this lead of this part? Which lead carries USART1 TX? | [`pinout.csv`](pinout.csv) |
| Is the debug wiring 1-wire (SWIO) or 2-wire (SWDIO+SWCLK)? | [`debug_interfaces.csv`](debug_interfaces.csv) |
| Which remap value routes the signal where I want it? | [`routes.csv`](routes.csv) |
| Pads that move with which peripherals are enabled (not an AFIO remap) | [`pin_conditions.csv`](pin_conditions.csv) |
| Registers and bit fields (header generation) | [`registers.csv`](registers.csv) |
| Absolute register addresses | [`register_map.csv`](register_map.csv) |
| DMA request -> channel | [`dma.csv`](dma.csv) |
| Timers, with the channels that reach pins | [`timers.csv`](timers.csv) |
| Which families share a register layout | [`register_layouts.csv`](register_layouts.csv) |
| Series, families, packages, cores | [`series.csv`](series.csv), [`families.csv`](families.csv), [`packages.csv`](packages.csv), [`cores.csv`](cores.csv) |
| Chip ID, option bytes, flash geometry and programming | [`device_ids.csv`](device_ids.csv), [`option_bytes.csv`](option_bytes.csv), [`option_byte_fields.csv`](option_byte_fields.csv), [`flash_geometry.csv`](flash_geometry.csv), [`flash_program_method.csv`](flash_program_method.csv) |
| Absolute maximum ratings | [`absolute_maximum_ratings.csv`](absolute_maximum_ratings.csv) |
| OPA/CMP and USB-PD register fields | [`opa_cmp_registers.csv`](opa_cmp_registers.csv), [`usbpd_plumbing.csv`](usbpd_plumbing.csv) |
| FLASH/SRAM split set by the option bytes | [`memory_configs.csv`](memory_configs.csv) |
| WCH-Link firmware files, and the versions measured to fail | [`link_firmware.csv`](link_firmware.csv), [`link_firmware_issues.csv`](link_firmware_issues.csv) |
| Clock tree, interrupts, memory map, operating conditions, errata | see [Published as read](#published-as-read) |
| What every column here means, how it is written, what an empty cell means | [`columns.csv`](columns.csv) |
| sha256 of every file here | [`manifest.csv`](manifest.csv) |

Every table is **one combined file** (every part, every family) and generators read it as is.
CSV is for programs; people filter by part or feature in the viewer ([`pins.html`](../pins.html),
served from GitHub Pages).

## The viewer

`pins.html` reads `index/parts`, `index/pinout`, `index/capabilities` and two evidence tables
(`product_attributes`, `remap_fields`). It has no per-series build output: a display cache would be
a second copy of the index to keep in step.

| Parameter | Meaning |
|---|---|
| `?chip=CH32V307` | series view: pad x function matrix and the product comparison |
| `?chip=CH32V307VCT6` | product view: that part's lead numbers, its series' remap selectors, and the instances its comparison table does **not** give it greyed out |
| `&features=ADC,TIM` | show only these function columns (`UART` accepted for `USART`) |
| `&routes=default,remap,af,unstated` | show only these routes |
| `&q=USART1` | search: pad, the datasheet's spelling, or the normalised peripheral/role |
| `&tim=split` | one column per timer instance instead of one `TIM` column |

With no `?chip=` it lists every series and part to choose from. Cells carry the evidence's
confidence: `~` one source only, `!` the two editions disagree, `?` after a remap value means
no selector field could be tied to it. Clicking a remap value jumps to the selector's register
row.

## Contract for consumers

- **Read only files under `index/`.** `catalog/` and `evidence/` are this repository's working layers and
  may change shape at any time. If something you need is not here, ask for it to be published (a data
  request) rather than reading around the surface.
- **Pin by commit plus the sha256 of `manifest.csv`.** The manifest lists every CSV here with its row count
  and sha256. There is no version number in the data: a breaking change stops a reader plainly when it moves
  its pin (a column it reads is gone), and releases are named by tags.
- **Releases.** A tag `v<major>.<minor>...` publishes a GitHub release carrying this directory as one zip
  (`ch32-device-data-index-<tag>.zip`: every CSV and the two READMEs). Changes that can break a consumer
  -- removing or renaming a column, changing how a column is written, renaming a key or a `fixed` value --
  are listed in the release notes. Take the zip to build without the network, and check it against its own
  `manifest.csv`.
- **Read columns by name, not by position.** Column order is not part of the contract, and tables and
  columns are added without notice.
- **[`columns.csv`](columns.csv) describes every column** of every table here: `meaning`, `format`
  (`text`, `name`, `integer`, `decimal`, `hex`, `bits`, `reg-bits`, `list(;)`, `list(,)`, `list(|)`, `url`, `path`,
  or `enum(a|b|...)`), what an `empty` cell means, and its `role`: `data`, or `provenance` for the
  confidence and basis columns, which always come after the data columns. `tools/check_tables.py` checks it
  against the data (every column covered, enum values, integer/hex shapes, `never empty`, provenance last).
- **`columns.csv` `spelling` says whose spelling a column carries**: `fixed` = chosen by this repository
  (keys, assigned identifiers such as `routes.selector` and `operating_conditions.symbol`, normalised
  vocabulary such as `pinout.peripheral`/`role`); renaming an existing value is a breaking change (listed in the release notes), so match on
  these. `as-printed` = the datasheet's, reference manual's or EVT header's own spelling (`pinout.signal`,
  `memory_map.region`, `clock_symbols.symbol`, `operating_conditions.condition`); it follows the documents and
  can change when one is revised. `prose` = text for people, not for matching.
  Empty = a value column (numbers, addresses).
- **Adding tables, columns or rows is not a breaking change**; read columns by name and ignore what you do
  not know.
- **`family` is a unit of WCH's EVT packages**, named after its archive `<family>EVT.ZIP`. It is not a
  product line and not a datasheet or reference-manual unit (`CH32V20x_30xDS0` spans CH32V20x and CH32V307;
  CH32V006 covers CH32V002 to CH32V007 and CH32M007). If WCH regroups its EVT packages, the families follow
  and that is a breaking change.
- **`confidence` is one of `confirmed`, `reference`, `conflict`**, and empty exactly when the value it
  describes is empty (the column's `empty` says why). `confirmed` = two or more independent bases agree, or a
  person checked the content and recorded the basis; `reference` = one basis, neither corroborated nor
  contradicted; `conflict` = the bases disagree, the table kept one value, and `basis` names the other side.
  A value made of several rows takes the weakest of them. What to do with each level is the consumer's
  decision.
- **`basis` follows one grammar** ([below](#basis)), so a program can read which document, edition and page
  states a value, and which source disagrees with it.
- What is guaranteed is the shape (columns, their meaning and spelling rules), provenance on every row,
  the invariants `tools/check_tables.py` checks, and regeneration when the sources change -- **not** that
  every row is true: where a document is wrong, the row is wrong and says so through `confidence`/`basis`.

## basis

A `basis` cell (and every `<column>_basis` cell) lists the sources of the value it sits next to.

```
basis    := term ("+" term)*                     terms are split on "+" outside parentheses
term     := [mark] source [dissent]
mark     := "!"   a source that states something else (always followed by a dissent)
          | "?"   a check that could not be applied cleanly (not a disagreement)
source   := [kind ":"] document [":" lang] ["(" locator ")"]
          | kind [":" label] ["(" detail ")"]
document := a document name from the catalog (ends in .PDF), with "@V<version>" for a past edition
lang     := "zh" | "en"
locator  := "p." <PDF page number> [";" detail]  |  detail
dissent  := "(" column "=" value ("," column "=" value)* ")"
```

- `CH32V407DS0.PDF:zh(p.59)` = the Chinese edition of that datasheet, PDF page 59. The page number is the
  PDF's own page index, the same number the structured preview uses
  (`https://ch32-riscv-ug.github.io/ch32-device-data-preview/<document stem>.<lang>/pages/<NNNN>.md`).
- `!CH32V007DS0.PDF:zh(max=115)` = that source states `max` as 115; the table kept the other value.
  [`conflicts.csv`](conflicts.csv) collects every such term: `field` is the column, `kept` the table's value,
  `alternative` the dissenting value.
- `kind` names how the source was read: `pin-table:zh`, `products:en` (comparison table), `rm:<manual>`,
  `rm-address:<manual>` (the chapter's absolute-address table), `rm-remap-grid`, `evt(<file>)`,
  `evt-api(<file>)`, `measured:<date>(<record>)`, `rule:<name>`, and so on. The full list with a line each is
  `KINDS` in `pipeline/common/basis_grammar.py`; `tools/check_tables.py` rejects a kind not in it.
- Parentheses always pair; a `detail` or `value` may contain balanced parentheses, commas and `+`.

## Rules

- Names are normalised through `pipeline/common/signal_vocabulary.py` (`peripheral`, `role`, `port`, `gpio`).
  **The original spelling sits in the next column** (`signal`, `spelled`, `define`), so every row
  leads back to the evidence.
- Data columns are English.
- The index disagrees with the evidence in exactly one place: where a datasheet's pin table states a
  remap value that the reference manual's remap grid contradicts, `pinout.route` takes the grid's value.
  The evidence keeps the pin table's value as `conflict` with `!rm-remap-grid(route=remap-N)` in `basis`;
  the grid *defines* the value, the pin table only quotes it.

## Published as read

Each generator writes these tables here directly (`paths.PUBLISHED`), one row per fact with its
`confidence` and `basis`. Every column is described in [`columns.csv`](columns.csv); how each table is
read from the sources is in the [catalog README](../catalog/README.md) and the
[evidence README](../evidence/README.md) under the same table name.
Keys: `families`, `series`, `packages`, `cores`.
From EVT headers: `interrupts`, `memory_map`, `systick`, `evt_variants`, `clock_configs`, `clock_prescalers`,
`clock_sources`, `clock_symbols`, `clock_init`, `clock_enables`, `pin_alternate`.
Reference manual and datasheet: `flash_geometry`, `flash_program_method`, `adc_internal`, `debug_data`,
`device_ids`, `option_bytes`, `option_byte_fields`, `register_blocks`, `errata`, `operating_conditions`, `esig`,
`absolute_maximum_ratings`, `opa_cmp_registers`, `usbpd_plumbing`, `pin_conditions`, `memory_configs`.
WCH-LinkUtility: `link_firmware`; measured failures: `link_firmware_issues`.

## Tables

### `parts.csv` -- one row per part

The part table. **Every value column has its own `<column>_confidence` and `<column>_basis`**:

- identity and headline specs from the catalog (`part_number`, `series`, `family`, `package`,
  `flash_bytes`, `sram_bytes`, `gpio_count`, `temperature`, `packing`, `listed_as`, `datasheet`), checked
  between the comparison table and the ordering table;
- `pins` from `packages.pin_count`;
- `clock_max` / `vdd_min` / `vdd_max` from `operating_conditions` (`F_MAIN`, else `F_HCLK` -> `F_SYSCLK`
  -> `F_CORE`; the `V_DD` envelope), with the confidence and basis of the rows used;
- the comparison-table counts (`usart`, `spi`, `i2c`, `can`, `usb`, `adc`, `dac`, `opa`, `cmp`,
  `timers_advanced`, `timers_general`, `rtc`, `ethernet`) **verbatim** from `evidence/product_attributes`
  (`4`, `1/10`, `√`; two attributes landing in one column are joined with `;`). No counting rules are
  applied here -- `tools/check_counts.py` does the reconciliation.

`family`, `listed_as` and `datasheet` are names the catalog assigns, so they carry no confidence.

### `pinout.csv` -- part x lead x function

One row per (part, lead, function). **Leads with no function (power, NC, plain GPIO) still get
one row**, so `port`+`gpio` -> lead is a single lookup.

| Column | Meaning |
|---|---|
| `pin` | lead number; exposed pad is `EP` |
| `pad` | as the datasheet spells it (`PA0-WKUP`, `LO1`, `VDD_VIO_1`) |
| `port`, `gpio` | the pad read as a GPIO (`A`, `0`), decorations dropped; also filled from a parenthesised alias (`LO1 (PA0)`) and from a GPIO name the pin table lists with no route on a function-named pad (`OSC_IN` -> `PD0`), unless another lead of the part carries that GPIO (100-pin packages, where `PD0` is its own lead); empty for non-GPIO pads |
| `kind` | `gpio` / `power` / `analog` / `other` / `nc` (a lead the datasheet marks as not connected -- it has a number but no pad name, type or function) |
| `peripheral`, `role` | normalised function (`USART1`, `TX`) |
| `signal` | the datasheet's spelling (`USART1_TX` / `TX1` / `UTX`) |
| `route` | `main` (primary function, live at reset) / `default` (default alternate function: reachable without remap once in AF mode) / `remap-N` / `af-N`. **`main` and `default` are different things** and which column a datasheet uses varies by family |
| `selector`, `value` | the AFIO selector that picks this route (`afio-tim2-remap`) and its value; key into `routes.csv`; `0` for `default`/`main`; empty when no selector applies |
| `af` | N of `af-N` (AF-number families: V205, X315, H41x); the register lives in `pin_alternate` |

Not listed: a pad's own GPIO name as its primary function (`PA9` -> `PA9`) and power pads. Pads
whose name *is* the function (`NRST`, `OSC_IN`, `BOOT0`) are listed. Spellings the vocabulary
cannot read are not listed; their count is pinned to 0 in `tools/check_tables.py`.

### `routes.csv` -- remap selector values

One row per (series, selector, value, signal): `evidence/remap_fields` (register and bits of the
selector) joined with `evidence/remap_routes` (signal and pad per value), plus `peripheral`,
`role`, `port`, `gpio`. `controller` is the block that owns the selector's register (`afio`, or
`extend` for the EXTEN block). `register` reads `PCFR1|PCFR2` when a field spans two registers. A route
that holds only when certain peripherals are enabled is completed by `pin_conditions.csv`.

### `registers.csv` -- family x type x register x field

One row per bit define, plus one row per register the header gives no bit defines for. `kind` says which:
`field` (a bit field), `value` (an enumerated value within a field, `of_field` names the field), or
`register` (the register alone). A register with bit defines appears only on its field and value rows,
each repeating the register's `offset`, `width_bits` and `count`.

`type` is the EVT `*_TypeDef` stem; `register` the struct member, arrays per element (`EXTICR[1]`, offset =
first + index x width) and nested structs flattened (`sTxMailBox[0].TXMIR`). **`register` is the
header's own spelling, so the same register can be spelled differently across families**: AFIO's
EXTI configuration is an array `EXTICR[0]`..`EXTICR[3]` in most families (`EXTICR[0]`/`[1]` on X035),
one member `EXTICR` on V003/V006/M030, and two members `EXTICR1`/`EXTICR2` on H417. The names are not
normalised (that would invent names the header does not have); to find "the k-th word" of such a
register, order the rows of that `type` by `offset`. `field` is the readable name, `define` the EVT
spelling (`RCC_APB2PCENR_USART1EN`). Rows with an empty `offset` are defines whose banner could not be
tied to a struct member. `access` / `reset` come from the reference manual's field table (Chinese
edition), matched by name; `access_confidence`/`access_basis` say whether the English edition prints the
same term.

**Where the header and the manual put a field at different bits and a bench measurement has
settled it, this index takes the measured position** (`bits`/`mask`), while the row keeps
`confidence=conflict` and a `basis` that shows both documents and the measurement -- the same
rule as `pinout.csv` taking the RM remap grid's value. CH32L103 `FLASH_OBR` `DATA0`/`DATA1` is such a
case: the header says `[17:10]`/`[25:18]`, the manual `[19:12]`/`[27:20]`, and reading `FLASH_OBR` back
over WCH-LinkE showed the manual is right (`basis` ends `obr-readback:wch-linke(bits=19:12)`).
`evidence/register_fields.csv` keeps the header's bits, because it records what the documents say.

### `register_map.csv` -- absolute addresses

One row per (family, block, register): `register_blocks` base addresses x `registers`,
`address = base + offset`. Blocks whose struct is not in the header (`USBHSH` on V407/X315) get
one row with `register` empty.

### `dma.csv`

`evidence/dma_requests` read: `spelled` is the manual's spelling (`TIM1_UP*`, `USART1_TX_1`),
`request` the bare name, `remap` the marker (`selectable` = `*`; X315's `_0`/`_1` = `default` /
`remap`), `peripheral` the normalised owner (`SPI/I2S2_RX` -> `SPI2`). Rows with `request_id`
(CH32H417's DMAMUX) are request numbers, not fixed channels.

### `timers.csv`

`evidence/timers` (kind, counter width, update vector from the RM) plus `channels` (highest
channel number reaching a pin, counted from `pinout.csv` -- not the silicon's limit) and
`complementary` (`1` if any `CHxN` reaches a pin). A timer that exists only in some variants names them
in `condition`.

### `capabilities.csv` -- part x capability, long format

One row per (part, capability, qualifier, source attribute), from
`evidence/product_attributes` alone (by `pipeline/build/build_capabilities.py`). `parts.csv` lays the
comparison table out wide in 13 columns; this table holds every attribute as a row, under a normalised
capability name, so a query does not have to know that "how many SPI" is spelled `spi` in one family and
`communication_interfaces_spi` in another.

| Column | Meaning |
|---|---|
| `capability` | normalised name (`usart`, `can-fd`, `usb-hs`, `timer-general`, `adc`, `adc-channel`, ...) |
| `qualifier` | the distinction the document itself draws inside that capability (`32bit`, `tim1`, `include-phy`, `adc1`, `with-tkey`). Spelling differences are **not** a distinction -- they stay in `attribute` |
| `stated` | how the document states the value: `count` (a bare integer), `marker` (`√`, `Supported` -- it claims presence without a number), `text` (anything else: `8+2`, `3/2`, `10@2`, `MAC+10M/100M PHY`) |
| `count` | the integer, and only when `stated` is `count`. **No counting rule is applied**: `8+2` is not read as 10 |
| `value` | the document's value verbatim |
| `attribute` | the `evidence/product_attributes` key this row came from -- the way back |

**The existence of a row is the claim that the part has it.** A comparison-table cell reading `-`
is already dropped in `product_attributes`, so it is absent here too. **That reading only holds
within a family**: a missing row means either "this part does not have it" or "this family's
comparison table has no such row", and the table cannot tell the two apart. Do not count
"parts without X" across families.

`adc` is the **unit** count and `adc-channel` the **channel** count; the source spells both "ADC"
in places (`adc` = `8+2` channels, `adc_unit` = `2` units), which is why the attribute-to-capability
map is an exhaustive dictionary rather than a set of patterns. Clock, voltage, flash, SRAM and GPIO
rows are carried too, so the comparison table is fully represented -- but for those, `parts.csv` has the
better-sourced value rather than the comparison table's prose (`Max: 144MHz`).

### `conflicts.csv` -- where the sources disagree

One row per `conflict` mark in any table, by `pipeline/build/build_conflicts.py`. The tables never
resolve a disagreement by picking a side silently; they keep one value, mark the row `conflict`, and name
the other side in `basis`. This table collects those marks.

| Column | Meaning |
|---|---|
| `table`, `subject` | where the row lives, and its key columns as `col=value` |
| `field` | the column in dispute: the column of a per-column confidence, else the column the dissent names. Several columns are joined with `;` |
| `kept` | the table's value of `field` |
| `dissenting` | the sources marked `!` in `basis` |
| `alternative` | what those sources state for `field` |

**A `conflict` mark is not always a disagreement about the fact.** Some `product_attributes` rows differ in
wording only (`Typical: 72MHz` against `Typ. 72MHz`), and `option_byte_fields` rows whose `field` is `field`
differ in the spelling of the field's name, not in its bits or default. Read `field` to tell them apart.
For a Chinese dissent, `alternative` is the translated reading the basis carries, not the original spelling.

### `debug_interfaces.csv` -- is the debug wiring 1-wire or 2-wire?

By `pipeline/build/build_debug_interfaces.py`. One row per series. `debug_if` comes from crossing two pieces
of evidence: **the datasheet's debug section heading** (`evidence/features.csv`: `1-wire` -> `swio`,
`2-wire` -> `rvswd`) and **the WCH-Link manual's wiring table plus its dual-support note**
(`evidence/debug_wiring.csv`); `both` means the manual lists the series as supporting 1-wire and 2-wire. A
stated heading must not contradict the manual (`swio` is consistent with `both` as a subset). Where the
manual lumps V002/V004 into the dual-support group (SWCLK=PB3) but their pin tables carry no SWCLK and the
headings say 1-wire, the heading wins and the manual's dissent is recorded in basis
(`!WCH-LinkUserManual.PDF(swclk=PB3,dual=yes)`). `swdio_pads`/`swclk_pads` copy the normalised pads from
`pinout.csv`; the build also verifies the manual's pads exist there.

### `features.csv`, `register_layouts.csv`, `manifest.csv`

`features.csv` (by `pipeline/build/build_feature_tags.py`): one row per (tag, series); `precision` says
whether the comparison table (`part`) or a datasheet section heading (`datasheet`) decided it.
A feature with no section heading at all (CH32V208's Ethernet appears only in the overview and
block diagram) is tagged from the comparison table alone when the tag already exists from another
datasheet's headings and is the last token of the attribute name; `features`/`sections` are then empty
and `basis` is `attributes(...)`.
`register_layouts.csv` (by `pipeline/extract/rm/extract_registers.py`): (family, type) -> layout hash; equal
hashes share register definitions. `manifest.csv`: path, row count and sha256 of every CSV here.

```sh
uv run pipeline/build/build_capabilities.py   # capabilities.csv (before build_index -- the manifest hashes it)
uv run pipeline/build/build_conflicts.py      # conflicts.csv (likewise)
uv run pipeline/build/build_index.py          # the lookup tables and the manifest (seconds; evidence must be current)
uv run tools/check_tables.py                  # index ⊆ evidence, manifest matches, basis grammar
```
