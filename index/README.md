# Index (index/)

[日本語](README.ja.md)

The tables **to look things up in**. `tools/build_index.py` derives them from the
[evidence](../evidence/README.ja.md) (what the documents say, spelled as they spell it) and the
[catalog](../catalog/README.ja.md) (the names) -- and from nothing else: `tools/check_tables.py`
verifies on every run that each index row can be traced back to evidence rows. The three-way
split is defined in [docs/data-layout.ja.md](../docs/data-layout.ja.md) (Japanese).

## Where to look

| Question | Table |
|---|---|
| Which part meets my requirements? | [`parts.csv`](parts.csv) |
| Which parts have capability X, and how many of it? | [`capabilities.csv`](capabilities.csv) |
| Which series have feature X? | [`features.csv`](features.csv) |
| What is this lead of this part? Which lead carries USART1 TX? | [`pinout.csv`](pinout.csv) |
| Which remap value routes the signal where I want it? | [`routes.csv`](routes.csv) |
| Registers and bit fields (header generation) | [`registers.csv`](registers.csv) |
| Absolute register addresses | [`register_map.csv`](register_map.csv) |
| DMA request -> channel | [`dma.csv`](dma.csv) |
| Timers, with the channels that reach pins | [`timers.csv`](timers.csv) |
| Which families share a register layout | [`register_layouts.csv`](register_layouts.csv) |
| sha256 of every file here | [`manifest.csv`](manifest.csv) |

Every table is **one combined file** (every part, every family) and generators read it as is.
CSV is for programs; people filter by part or feature in the viewer ([`pins.html`](../pins.html),
served from GitHub Pages). There are no per-part copies -- they would only duplicate the file.

## The viewer

`pins.html` reads `catalog/products`, `index/pinout`, `index/capabilities` and two evidence
tables (`product_attributes`, `remap_fields`) -- 3.5 MB, 218 KB over the wire, parsed in about
a quarter of a second. It has no per-series build output on purpose: a display cache would be a
second copy of the index to keep in step.

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

## Rules

- Names are normalised through `tools/signal_vocabulary.py` (`peripheral`, `role`, `port`, `gpio`).
  **The original spelling sits in the next column** (`signal`, `spelled`, `define`), so every row
  leads back to the evidence.
- `confidence` is the confidence of the evidence rows used (the weakest, where several were
  folded). `basis` is copied when the row maps 1:1 to an evidence row; wide tables such as
  `parts.csv` say per column which evidence table to consult instead.
- Data columns are English; everything right of `#` is provenance.
- The index disagrees with the evidence in exactly one place: where a datasheet's pin table
  states a remap value that the reference manual's remap grid contradicts, `pinout.route`
  takes the grid's value (12 rows, CH32V103 TIM3). The evidence keeps the pin table's value as
  `conflict` with `!rm-remap-grid(=remap-N)` in `basis`; the grid *defines* the value, the pin
  table only quotes it.

## Contract for consumers

Read: every table in `catalog/`, the combined tables in `index/`, and the evidence tables the
evidence README marks *stable* (those copied from EVT headers: `interrupts`, `memory_map`,
`clock_*`, `systick`, `evt_variants`, `clock_enables`, `pin_alternate`, `memory_configs`,
`flash_geometry`, `adc_internal`, `debug_data`). Other evidence tables may change shape. Pin by commit plus
the sha256 of the files you read (or the single sha256 of `manifest.csv`). Column changes are
recorded in [docs/worklist.ja.md](../docs/worklist.ja.md) and in this README.

## Tables

### `parts.csv` -- product comparison

One row per part. Identity and headline specs from `catalog/products.csv` (`flash_bytes`,
`sram_bytes`, `gpio_count`, `temperature`; per-column provenance lives there), `pins` from
`catalog/packages`, `clock_max` / `vdd_min` / `vdd_max` from `evidence/operating_conditions`
(`F_MAIN`, else `F_HCLK` -> `F_SYSCLK` -> `F_CORE`; `V_DD` envelope), and the comparison-table
counts (`usart`, `spi`, `i2c`, `can`, `usb`, `adc`, `dac`, `opa`, `cmp`, `timers_advanced`,
`timers_general`, `rtc`, `ethernet`) **verbatim** from `evidence/product_attributes` (`4`,
`1/10`, `√`; two attributes landing in one column are joined with `;`). No counting rules are
applied here -- `tools/check_counts.py` does the reconciliation.

### `pinout.csv` -- part x lead x function

One row per (part, lead, function). **Leads with no function (power, NC, plain GPIO) still get
one row**, so `port`+`gpio` -> lead is a single lookup.

| Column | Meaning |
|---|---|
| `pin` | lead number; exposed pad is `EP` |
| `pad` | as the datasheet spells it (`PA0-WKUP`, `LO1`, `VDD_VIO_1`) |
| `port`, `gpio` | the pad read as a GPIO (`A`, `0`), decorations dropped; also filled from a parenthesised alias (`LO1 (PA0)`); empty for non-GPIO pads |
| `kind` | `gpio` / `power` / `analog` / `other` / `nc` (a lead the datasheet marks as not connected -- it has a number but no pad name, type or function) |
| `peripheral`, `role` | normalised function (`USART1`, `TX`) |
| `signal` | the datasheet's spelling (`USART1_TX` / `TX1` / `UTX`) |
| `route` | `main` (primary function, live at reset) / `default` (default alternate function: reachable without remap once in AF mode) / `remap-N` / `af-N`. **`main` and `default` are different things** and which column a datasheet uses varies by family |
| `selector`, `value` | the AFIO selector that picks this route (`afio-tim2-remap`) and its value; key into `routes.csv`; `0` for `default`/`main`; empty when no selector applies |
| `af` | N of `af-N` (AF-number families: V205, X315, H41x); the register lives in `evidence/pin_alternate` |

Not listed: a pad's own GPIO name as its primary function (`PA9` -> `PA9`) and power pads. Pads
whose name *is* the function (`NRST`, `OSC_IN`, `BOOT0`) are listed. Spellings the vocabulary
cannot read are not listed; their count is pinned to 0 in `tools/check_tables.py`.

### `routes.csv` -- remap selector values

One row per (series, selector, value, signal): `evidence/remap_fields` (register and bits of the
selector) joined with `evidence/remap_routes` (signal and pad per value), plus `peripheral`,
`role`, `port`, `gpio`. `register` reads `PCFR1|PCFR2` when a field spans two registers.

### `registers.csv` -- family x type x register x field

One row per (register, bit define): `evidence/registers` (struct offsets) joined with
`evidence/register_fields`. Registers without defines get one row with `field` empty. `type` is
the EVT `*_TypeDef` stem; `register` the struct member, arrays per element (`EXTICR[1]`, offset =
first + index x width) and nested structs flattened (`sTxMailBox[0].TXMIR`). `field` is the
readable name, `define` the EVT spelling (`RCC_APB2PCENR_USART1EN`). Rows with an empty
`offset` are defines whose banner could not be tied to a struct member (1,591). `access` /
`reset` come from the reference manual where the bit position matched (`confirmed`).

### `register_map.csv` -- absolute addresses

One row per (family, block, register): `evidence/register_blocks` base addresses x `registers`,
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
`complementary` (`1` if any `CHxN` reaches a pin).

### `capabilities.csv` -- part x capability, long format

One row per (part, capability, qualifier, source attribute), from
`evidence/product_attributes` alone (by `tools/build_capabilities.py`). `parts.csv` is the
comparison table laid out wide and can hold 13 of the 158 attribute spellings as columns; this
table holds all of them as rows, under a normalised capability name, so a query does not have to
know that "how many SPI" is spelled `spi` in one family and `communication_interfaces_spi` in
another.

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
rows are carried too, so the comparison table is fully represented -- but for those,
`parts.csv` has the better-sourced value (`evidence/operating_conditions`, `catalog/products`)
rather than the comparison table's prose (`Max: 144MHz`).

### `features.csv`, `register_layouts.csv`, `manifest.csv`

`features.csv` (by `tools/build_feature_tags.py`): one row per (tag, series); `precision` says
whether the comparison table (`part`) or a datasheet section heading (`datasheet`) decided it.
`register_layouts.csv` (by `tools/build_registers.py`): (family, type) -> layout hash; equal
hashes share register definitions. `manifest.csv`: path, row count and sha256 of every other CSV
here.

```sh
uv run tools/build_capabilities.py   # capabilities.csv (before build_index -- the manifest hashes it)
uv run tools/build_index.py          # rebuild everything (seconds; evidence must be current)
uv run tools/check_tables.py         # index ⊆ evidence, manifest matches
```
