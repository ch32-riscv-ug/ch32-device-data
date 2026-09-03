# Evidence (evidence/)

[日本語](README.ja.md)

**What the documents say**, copied row by row with its basis (`basis`) and confidence (`confidence`)
attached -- 33 tables ([docs/data-layout.ja.md](../docs/data-layout.ja.md) (Japanese)). Spelling is kept as in the original:
`pin_functions.signal` varies between `TX1` / `UTX` / `USART1_TX` exactly as the documents do, and `pad` keeps
decorations such as `PA0-WKUP`. When documents disagree, the value is not corrected; the row is marked `conflict` and both are kept.
The tables **to look things up in** (names normalised through the vocabulary, joined, split per part number) are in
[`index/`](../index/README.md), and the key names are in [`catalog/`](../catalog/README.md).

**Per-table reliability (how solid each table is, and the known gaps) is in
[docs/table-reliability.ja.md](../docs/table-reliability.ja.md) (Japanese)**; terminology is in
[docs/glossary.ja.md](../docs/glossary.ja.md) (Japanese).

## Column kinds

| Kind | Examples | Rule |
|---|---|---|
| Document spelling / value | `signal`, `pad`, `parameter`, `request`, `define` | As is. Only the type is normalised (number, hex, unit) |
| **Assigned identifier** | `remap_fields.selector`, `operating_conditions.symbol`, `product_attributes.attribute`, `pins.kind`, `clock_symbols.role`, `opa_cmp_registers.unit` | A key the repository assigns to something the documents do not name. The document's spelling (`field`, `parameter`, `label_zh/en`, `type`) stays in the same row |
| Catalog key | `part_number`, `series`, `family`, `document` | Normalised names (for joins) |
| Provenance | `confidence` and `basis` to the right of `#` (per column for `products`) | On every row |

Columns derived through the vocabulary (`peripheral`, `role`, `port`, `gpio`, and `channels` counted from pins) are
**not** here; they are in the index.

**Tables that can be read as is (stable)**: `interrupts`, `memory_map`, `systick`,
`clock_*` (5 tables), `evt_variants`, `clock_enables` and `pin_alternate`, copied from EVT headers, plus `memory_configs`,
`flash_geometry` and `adc_internal`, are not copied into the index because their names are machine vocabulary from the start.
Consumers may read these directly; their columns are kept stable in the same way as the index.

## Each file

### `pins.csv` / `pin_functions.csv`

**Per ordering part number.** pins.csv has one row per (part_number, pin, pad): "which pad sits on lead N of this part number"; pin_functions.csv has one row per (part_number, pad, signal, route): "the functions this part number's pad has". The datasheet pin table shares one pinout among several part numbers (the caption declares the scope: `CH32V103x8x6`, `CH32V006（除F4U6以外）`, `TSSOP20(F8)`), but that resolution is done at generation time, and **rows join directly to products.csv on part_number**. The fact that a pinout was shared remains in the datasheet/table columns on the meta side (source).

#### Meaning of the `route` values (**"default" means two different things**)

`route` is **the datasheet pin-table column itself**. All 12 families have the same 4 columns (confirmed by measuring the column headings).

| `route` | Source column | Meaning | **Active right after power-on?** | Rows |
|---|---|---|---|---|
| `main` | 主功能（复位后）/ Main function (after reset) | What the pad is doing right after reset | **Yes** | 4,510 |
| `default` | 默认复用功能 / Default alternate function / 引脚功能 | The function that appears **once the pad is put in AF mode** without touching the remap register (left at 0) | **No** | 9,335 |
| `remap-N` | 重映射功能 | Write N to the AFIO remap field | No | 9,869 |
| `af-N` | The AF number is written alongside in the same column (`SDA(AF7)`) | Write N to that pad's AF number | No | 4,497 |
| `alias` | Parentheses in the pad-name cell (`LO1\n(PA0)`) | **Not a function.** The pad's **name as a GPIO**, given by the document as an alias | -- | 30 |
| empty | -- | The document gives no route number; needs checking | -- | 242 |

#### `alias` -- when the pad name carries a GPIO name in parentheses (CH32M007 / CH32M103)

For the gate-driver outputs of CH32M007 and CH32M103, the pad cell of the pin table is **two lines, `LO1` and `(PA0)`**.
The pad's name is `LO1`; the parentheses say that this lead is PA0 on the plain CH32V007 (its name as a GPIO).
CH32M030, conversely, writes the same kind of pad as `PB9` and puts `HO0` on the `default` function side
-- **the same physical thing is written in opposite directions by the documents**, so we lean to neither and keep each document's direction.

| Document notation | `pins.pad` | `pin_functions` rows |
|---|---|---|
| CH32M030: pad `PB9`, default alternate function `HO0/TIM1_CH1` | `PB9` | `(PB9, HO0, default)` `(PB9, TIM1_CH1, default)` |
| CH32M007: pad `LO1 (PA0)`, primary function `LO1` | `LO1` | `(LO1, LO1, main)` **`(LO1, PA0, alias)`** |

**How to read it**:
- "Which lead is PA0 on the M007?" → look up `port=A, gpio=0` in the index `index/pinout.csv` (`port`/`gpio` are also filled from alias). Following the evidence alone: `signal=PA0, route=alias` in `pin_functions` → `pad` → `pin` in `pins`
- "Which lead is LO1 on the M007?" → `pad=LO1` in `pins`
- **Do not mix `alias` rows into function lists** (the index `index/pinout` does not list them as functions; the generated README shows
  `LO1 (PA0)` next to the pad name). The documents do not say whether it can be used as a GPIO output as PA0,
  so this table does not say so either
- `tools/check_tables.py` checks that the signal of an alias row is a GPIO name, that the pad is not a GPIO name,
  and that there is one per pad

**`default` does not mean "works without configuration".** It means "reachable without writing remap". Right after reset the GPIO is a floating input, and **the alternate function does not appear until the GPIO mode is set to alternate function**. The same holds for AF-style families: the reset value 0 of `GPIOx_AFLR` selecting AF0 and setting the GPIO mode to alternate function are separate settings.

Concretely, **UART has not a single `main` row** (TX/RX are all `default`/`remap-N`/`af-N`). Powering on alone does not bring up a UART. What appears under `main` is only `SWDIO`/`SWCLK`/`BOOT0`/`BOOT1` and the reset functions of dedicated pads (`NRST`, `OSC_IN`/`OSC_OUT`, `XI`/`XO`, Ethernet `MDI*`, USB3.0 `SS*`).

#### **Which column things go in is not consistent across families**

The same SWD is in the 主功能 (primary function) column in one datasheet and in the 既定代替功能 (default alternate function) column in another.

```
Written in the primary-function column:            CH32L103 / CH32V103 / CH32V20x / CH32V307
Written in the default-alternate-function column:  CH32H417 / CH32M030 / CH32V003 / CH32V006 / CH32V205 / CH32X035 / CH32X315
Appears in both:                                   CH32V407
```

CH32L103 writes PA13's primary function as `SWDIO`; CH32X035 writes PC18's primary function as `PC18` (GPIO) and its default alternate function as `DIO` (= SWDIO). **Physically, SWD is alive at reset on every family** (which is why a debugger connects out of the box). The column difference is a difference in how the documents are written.

**So when looking up "is it alive at reset", do not look at `main` alone.** Looking up `main` only drops the SWD of 7 families. This is why `tools/build_readme.py` looks at both `main` and `default`.

Because the policy is that `route` preserves the document's column (spelling and provenance are the evidence, so they are not changed), absorbing this variation is the reader's job.

Notation differences absorbed by cross-checking both language editions: shifted table numbers (X315: zh `表2-1-1` = en `Table 2-1`; matched by the series name in the caption), column-heading spelling (`QFN48×7`, `QFN28(6)`; zh `LQFP64M` = en image `LQFP64`, paired by elimination within the table), one column standing for several packages (`LQFP48/QFN48X7` is registered per component).

**Rows where the pin table and the RM remap grid disagree** (TIM3 of CH32V103: the pin table writes `TIM3_CH1_1` on both PB4 and PC6, but the RM grid has PB4=2, PC6=3 and value 1 is not defined. F-41) are marked `conflict` **with the value as in the pin table**, and the basis lists `!rm-remap-grid(=remap-2)` alongside the grid's value. It is the index `index/pinout.csv` that adopts the grid's value.

### `product_attributes.csv`

Holds **all attributes of the comparison table in long form** (except flash/sram/pin count/GPIO/temperature/package, which are already promoted to columns). Because the two language editions use different label words (`定时器`↔`Timer`), **rows are matched by LCS over the sequence of normalised values** -- the translation preserves the table's row order, so the same values in the same order are the same row. Matched rows whose values differ become conflict (e.g. the OPA count of CH32H417WEU6 is zh=1 / en=2, a genuine disagreement). The original labels are kept in `label_zh`/`label_en`.

**`order` is the document's row order.** The comparison table groups related rows together, so sorting by attribute name alphabetically makes it harder to read. The file is ordered this way too.

**`label` is the heading for display.** Following the same convention as `value`, it holds what the English edition says if it says anything, otherwise a translation of the Chinese (the originals stay in `label_zh`/`label_en`). **This is the only column with no Chinese mixed in**, so use it for display.

**`group` is the upper tier of the heading.** The heading column of the comparison table is two-tiered, and `label` holds the whole thing joined (`Communication interfaces CAN`). It is kept separately so that the upper tier can be stripped when only the lower tier is needed (for display). `group` is always a prefix of `label`.

Whether to strip is the reader's decision. Two guidelines: do not strip when stripping would give the same name as another row (`ADC/TKey Unit` and `HSADC Unit`), and do not strip when only an ordinary English word would remain (`Unit`, `Voltage`). If it contains an abbreviation or a number (`CAN`, `Basic (16-bit)`), it names something by itself and can be stripped. The `attribute` column (join key) is **built from the whole joined heading**, so stripping causes no collisions.

### Rows where several pads share the same lead number

**`(part_number, pin)` is not a primary key.** One lead can carry two pads, and the datasheet writes this by **merging the number cell vertically across two rows** (`CH32L103F8U6` does not use merging and writes `17` twice, saying the same thing another way). There are 96 such places, with 4 meanings.

| Form | Count | Meaning |
|---|---|---|
| `gpio` + `gpio` | 65 | **IO pair shorted inside the chip.** `PA11` and `PA13` on the same lead |
| `gpio` + `other` | 15 | A function pad and an IO sharing a lead, such as `BOOT0` and `PB9` |
| `power` + `power` | 12 | A reference voltage folded into a supply in a small package (`VREF-` and `VSSA`) |
| `power` ×3 | 2 | `VS1`/`VS2`/`VS3` -- the same supply node |
| `gpio` ×3 | 2 | 8-pin parts. Three IOs on one lead |

**Being an internal connection is not held in a separate column or notation.** The matching number is the fact itself, so looking up `(part_number, pin)` returns the partner. Adding a notation such as `PA13 (PA11)` would split the same fact into two places that could disagree, and would get in the way of searching.

**"Both must not be outputs at the same time" has no column either.** It follows from there being two or more `kind=gpio` rows on the same `pin` -- the datasheet note says so:

> the PC10 and PC17 pins are short-joined inside the chip, and **both IOs are prohibited from being configured as output functions** (CH32X035DS0 note 4)

Shared power pads (`VS1`/`VS2`/`VS3`, `VREF-` and `VSSA`) are naturally used simultaneously, so `kind` separates the two cases by itself.

The reading can be checked elsewhere in the documents. Note 8 of CH32L103 **names 4 pairs** for `F8U6` -- `PB1`/`PB10`, `PB6`/`PB13`, `PA12`/`PA14`, `PA11`/`PA13` -- matching the 4 pairs recovered from the merged cells. That `VREF-` and `VSSA` of CH32V407 fall on the same lead is independently backed by `V_REF- is equal to V_SS` in the electrical characteristics table.

#### Leads the datasheet marks as not connected (`kind=nc`)

A lead that carries nothing still has a number, and the pin table prints a row for it: the same document family spells that row's pad cell four ways -- `NC`, `NC.`, `未使用`, `Unused` -- with the type and function cells empty. Those rows are kept, with the pad spelled `NC` and `kind=nc` (the same normalisation as numbering the exposed pad `EP`), and no `pin_functions` rows: 8 leads on 5 part numbers (CH32V203RBT6 47/48, CH32V205VCT6 and CH32V303/307/317VCT6 73).

**They are kept because the count is a check.** `catalog/packages.pin_count` says an LQFP100 has leads 1..100 and nothing else, which is the one invariant on the pin tables that does not come from the pin tables -- `tools/check_tables.py` (`pin_numbering`) measures the reading against it. Dropping the NC rows did not merely lose them: with the pad cell unrecognised, lead 47 of CH32V203RBT6 inherited the pad name above it and **became `VDD_2`**, a pad the LQFP64M table does not put there at all (worklist F-49).

### `timers.csv`

A machine-readable table of **"how many bits is this timer's counter"**. The comparison table only has **sentences** such as `Timer General-purpose TIM4 (32-bit)` at series granularity, and the spelling varies between `ADTM`/`GPTM`/`高级定时器`. If consumers hand-write the list of 32-bit timers, a mistake there silently skews period calculations.

The source is **the RM register headings**. The heading states the kind and the target timers, and the field table right below it states the width.

```
14.4.10 高级定时器的计数器（TIMx_CNT）（x=1/8）      [15:0] CNT[15:0]  → advanced 16bit
15.4.11 通用定时器的计数器（TIMx_CNT）（x=9/10/11/12） [31:0] CNT[31:0]  → 32bit
```

Channel counts (`channels`, `complementary`) are not in this table; the index's [`index/timers.csv`](../index/README.md) holds them as a derivation counted from the functions on pins. `update_vector` is taken from `interrupts.csv`. Advanced timers split their vectors into 4 (`BRK`/`UP`/`TRG_COM`/`CC`), so **the update interrupt `TIMn_UP` is selected by name**.

**Some widths vary by variant.** TIM5 of CH32V20x is one; the RM note says

> 注：32位的TIM5_CNT仅适用于型号为CH32F20x_D8W、CH32V20x_D8、CH32V20x_D8W系列的产品，其他系列芯片的TIM5_CNT为16位。

The named macros go in `condition` (held the same way as in `interrupts.csv`) and `confidence` is `varies-by-package`. **When another family sharing the same RM does not have that variant, it becomes `conflict`** -- CH32V307 shares its RM with CH32V20x but has none of the variants in the note, so it cannot be declared 32-bit.

### `flash_geometry.csv`

**The premises for a low-level flash API.** `products.csv` only holds the capacity; the erase unit and programming granularity differ per family.

| Column | Meaning |
|---|---|
| `page_erase_bytes` | Unit of standard page erase (1K/2K/4K) |
| `fast_erase_bytes` | Unit of fast page erase (64B/128B/256B). V407/X315/H417 **have no per-page fast erase**, only block erase (empty) |
| `fast_program_bytes` | Unit of fast page programming |
| `block_erase_bytes` | Unit of fast block erase (32K; 64K on V205) |
| `program_word` | Whether `FLASH_ProgramWord`/`ProgramHalfWord` exist in the driver. **Empty = fast page only** (L103/M030/V006/V205/X035) |
| `zero_wait_note` | Relation between `flash_bytes` (zero-wait region) and total capacity. Families where it moves with option bytes point to `memory_configs.csv`; total capacity points to `code_flash_bytes` in `product_attributes` |
| `note` | Mode dependence. CH32H417 becomes 8K pages / 64K blocks with `FLASH_CFGR0` bit28 (dual flash mode). Column values are for single mode |

The sources are two: **the `@brief` of the EVT flash driver** (`page size 4KB`, `1page = 256Byte`) and **the body text of the RM 闪存 (flash) chapter** (`标准页（1K字节）`, `快速编程按页（128字节）`); they are cross-checked to decide confidence. **There is actually one disagreement** -- the CH32V103 driver writes `ProgramPage_Fast ... 256Byte`, but the RM says `快速编程按页（128字节）`, the erase side of the same driver is also 128B, and the argument condition of `ROM_ERASE` is `StartAddr%128 == 0`. Judged to be a copying error in the EVT comment; the value is 128, marked `conflict`, with both readings kept in `basis`.

### `opa_cmp_registers.csv`

**The premises for comparator/OPA classes.** The base is in `memory_map.csv` and the input pads in `index/pinout.csv`, so what was missing is **the field layout** -- enable, input select, output, gain.

**The block placement differs per family, and that is why this table is needed.**

| family | Placement |
|---|---|
| X035 / L103 / V006 | OPA block. `CTLR1` is OPA, `CTLR2` is CMP (same block) |
| M030 | `CMP_CTLR`/`CMP_STATR` inside the OPA block (sharing it with QII/ISP) |
| V205 / H417 | `OPA_CFGR1`/`CMP_CTLR`... all spelled out by name in the OPA block |
| V30x / V407 | The OPA block is a single `CR` |
| V003 | OPA is **bits 16-18 of `EXTEN_CTR`** (no block of its own) |

The `unit` column says **whether the register belongs to the OPA or the CMP**. The RM heading only says `OPA控制寄存器 2（OPA_CTLR2）` (it names the block only), so it is decided by majority vote over the field descriptions ("CMP3正端输入通道选择" versus "OPA2正向输入端选择"). For families where the RM writes no field at all for that block (`CR` of V30x/V407, H417), everything except `CMP_*` recognisable by name is taken as OPA.

The source is the EVT header structures (layout) and bit defines (`OPA_CTLR2_EN1 ((uint32_t)0x00000001)`), **cross-checked against the RM register tables**. Where bit positions agree it is confirmed (199 of 293 rows). **There are 5 disagreements**, with both readings kept in `basis` (F-44/F-45) -- CH32X035's `OPA_CTLR2_CMP_LOCK` is written as `0x2000` (bit13, the same as `PSEL3`) but the RM has bit31; **writing with the header's value breaks the CMP3 positive-input selection**. L103's `ITRIMN`/`ITRIMP` are 5 bits in the header and 6 bits in the RM; V205's `HYS1_H`/`HYS2_H` are bits 29/30 in the header and bits 19/29 in the RM.

`purpose` is assigned mechanically from the spelling of the field name (`EN`→enable, `PSEL`→positive input select, ...). Fields that do not declare one are empty. Enumerated values of multi-bit fields (`BKIN_CFG_0`/`_1`) are not fields and are not listed. Families without OPA/CMP bit defines (V20x, V103, X315) have no rows.

### `clock_enables.csv`

**family × peripheral → which bit of which RCC register.** What consumers used to hand-write per family as defines such as `CH32_RCC_APB1_TIM4`, completed for every peripheral.

The source is the EVT `ch32*_rcc.h` -- the constants passed to `RCC_<bus>PeriphClockCmd()` are the per-peripheral bits, and **the bus name states the register** (`RCC_AHBPeriph_USBPD`→`RCC->AHBPCENR`). The bus names differ per family (AHB/APB1/APB2, HB/PB1/PB2, HB/HB1/HB2). That `RCC_<bus>PeriphClockCmd` writes to `RCC-><bus>PCENR` was verified in the rcc.c of 8 families, with no exceptions.

Cross-checked against the RM register tables (`USBPDEN` in `RCC_HBPCENR`): **370 of 429 rows confirmed, 0 conflict**. The 59 reference rows are those whose RM field name did not match the EVT spelling (`ETH_MAC_Rx` etc.), not bit errors. GPIO is spelled `GPIOA` in EVT and `IOPAEN` in the RM, so it is looked up under an alias.

### `adc_internal.csv`

**The premises for a `temperatureRead()`-style API.** **Which ADC channel** the temperature sensor and the internal reference voltage are on differs per family, and some families have no temperature sensor (V003/V006/M030/X035/X315 have a `vrefint` row only).

| Column | Meaning |
|---|---|
| `source` | `temperature_sensor` / `vrefint` / `vdd_half` |
| `channel` | ADC_IN number |
| `sample_time` / `sample_time_unit` | Sample time needed when reading. **The unit differs per family** (`us` or `adc_cycles` = number of ADC clock cycles), so both are kept without normalising. `sample_clock_mhz` is the condition when the unit is `us` |
| `v25_mv` (min/max) | Temperature sensor output at 25℃ |
| `avg_slope_uv_c` (min/max) | Average slope (negative temperature coefficient. The datasheet uses mV/℃; here uV/℃) |
| `vrefint_mv` (min/max) | Internal reference voltage |
| `temp_range_c` / `temp_error_c` | Measurement range and error |

The sources are the datasheet prose ("温度传感器在内部被连接到IN16输入通道上") and the electrical characteristics tables (`温度传感器特性`, `内置参考电压`). The English edition has the same tables, so matching numbers give confirmed. **For V003 and X035 the datasheet does not give the channel number; the RM ADC chapter does** (`连接ADC_IN8通道` / `ADC_IN15`), so those are taken from the RM and noted in `basis`.

**conflict is the zh/en disagreement itself.** The Avg_Slope maximum of CH32V20x/V307 is zh 4.8 / en 4.7 mV/℃.

### `usbpd_plumbing.csv`

**The premises for extending PD to series other than X035.** What was missing was **the RCC enable bit** (the USBPD row of `clock_enables.csv`) and **the location of the PHY configuration bits**; the latter sits in a different place per family.

| family | PHY configuration bits |
|---|---|
| X035 | `USBPD_PHY_V33`(bit8) / `USBPD_IN_HVT`(bit9) in `AFIO->CTLR` |
| L103 / V205 | `USBPD_IN_HVT`(bit9) in `AFIO->CR` |
| X315 | `USBPDHVT`(bit0) / `USBPDRISE`(bit2:1) in `AFIO->CR` |
| H417 | `USBPD_CC_HVT`(bit20) in `AFIO->PCFR1` |
| M030 | `USBPD0/1_CC_REF` / `CC_HVT` / `LVE_T` in `EXTEN->EXTEN_CTLR0` (two PDs) |

**Only PD fields** are listed. The `UDP_*`/`UDM_*` (USB D+/D- pad control) in X035's `AFIO_CTLR` and M030's `EXTEN_CTLR1` are USB plumbing, not PD, so they are not included. One row is one PHY field; the RCC-side columns repeat on every row. The source is the EVT headers (the define name states the register, or, where it does not, the preceding banner "Bit definition for EXTEN_CTLR0 register"), with bit positions cross-checked against the RM register tables.

### `register_blocks.csv` / `registers.csv` / `register_fields.csv`

**The mechanically collectable part of the register map** (consumer's R-20; 2026-08-25). The source is the EVT device
headers (`ch32*.h`), the only machine-readable source covering all 12 families, with bit positions cross-checked
against the reference manual (zh) register tables. Following the convention that **EVT is referenced, not duplicated**,
the header definitions are not copied verbatim; only the facts decomposed into structure (block → type → register → field) are kept.

| Table | One row | What it tells |
|---|---|---|
| `register_blocks` | family × block (`USART1`), 676 rows | Type (`USART`), base address, layout key. From `#define USART1 ((USART_TypeDef *) USART1_BASE)`. **Blocks where the address of at least one register matches the RM zh edition's absolute address table are confirmed (548)**. One block (`UHSIF` of H417) has no type structure in the device header; its layout is empty |
| `registers` | family × type × register, 4,995 rows | Offset within the structure, width (8/16/32/64), array count. Nested structures (CAN's `sTxMailBox[0].TXMIR`) are flattened to offsets from the parent. Registers overlapping in a union (`CNT` and `CNT_32` of H417 TIM) are two rows at the same offset. `rm_address_check` is the check against the RM absolute address table (`ok:N` = number of matching instances, `mismatch:N`); `rm_reset` is the reset value from that table (may contain `x`, as in `0x0000xx83`) |
| `register_fields` | family × register × bit define, 33,365 rows (field 24,792, value 8,573) | Bit position (`hi:lo`), mask, kind (`field`, or a `value` within a field), EVT's one-line description, RM access/reset. **`define` is the EVT spelling as is** (`RCC_APB2PCENR_USART1EN`); `field` is a readable name with the type and register prefix dropped. 27.5% of the fields (6,829) match the RM bit position; 38 are conflict |

The derived **layout key** (family × type → hash of the structure's shape; families with the same key can share the same register definitions) is in the index's [`index/register_layouts.csv`](../index/README.md). The lookup that joins register × field and attaches absolute addresses is also in the index (`index/registers.csv`, `index/register_map.csv`).

**How to read it**:
- **Absolute address** = `register_blocks.base_address` + `registers.offset` (join on `type` within the same family).
  For `USART1->STATR`: blocks(USART1)=0x40013800 + registers(USART, STATR)=0x000
- **`register_fields.register` is the spelling of the header banner** (`Bit definition for RCC_APB2PCENR register`),
  the same form as the RM register tables (`RCC_APB2PCENR`). The mapping to a structure member is in the `member` column
  (`RCC.APB2PCENR`), **attached only where one can be**. Banners containing an instance number (`DMA_CNTR7` →
  `DMA_Channel.CNTR`) get one, but CAN mailboxes/filters (`CAN_TXMI0R`, `CAN_F30R2`) and
  define groups without a structure (H417's `SERDES_*`/`TKEY_*`, M030's `UART_*`/`CMP_*`) have an empty `member` (1,591 rows = 4.8%). **Rows are not dropped when it is empty**
  -- the bit position and mask are as the header says
- **`kind=value` is a value within a field.** `RCC_PLLMULL_3` is a value of `PLLMULL`. `of_field` is the parent, `value` is its value
  (`mask >> lo`). Counting only `kind=field` gives the number of fields
- **A `field` with empty `bits`** is one whose mask is not contiguous (a few). Look at the mask
- **D-5 (type versions) is `index/register_layouts.layout`.** A breakdown such as "I2C has 4 types" comes out of grouping by
  `layout` per `type`. The key is a hash, so **it carries no meaning; it only says same or different**.
  It changes if even one definition on the header side changes (an edition bump can change it for the same silicon)
- **Cross-checking against the RM covers only names whose spelling matched.** The `x`/`y` in the RM's `GPIOx_CFGLR`, `IDRy` are compared with the digits dropped.
  Matched and same bit position → `confirmed`; different → `conflict` (`!rm(...)(=hi:lo)` in `basis`);
  no same name in the RM → `reference`. **`reference` is not an error; it is awaiting corroboration**, and `value` rows are outside the check,
  so they are always `reference`
- `conflict` is a genuine disagreement (e.g. CH32V003's `GPIO_LCKR.LCKK` is EVT bit8 / RM bit16;
  `ADC_RDATAR.DATA` is EVT 32bit / RM 16bit). No side is favoured
- **Corroboration of absolute addresses**: of the 8,369 rows in the tables at the start of each RM zh chapter (`R32_PWR_CTLR | 0x40007000 | description | reset value`),
  **5,110 rows match EVT block base + offset, 4 rows mismatch** (the 4 conflicts in `registers` =
  H417 CAN2's `FMCFGR`/`FSCFGR`/`FAFIFOR`/`FWR`, which are +4 in the RM. CAN1 matches). The remaining 2,937 rows are names that
  cannot be tied to a header structure (`BMC_*`, `ESIG_*`, `PFIC_*`, V20x's `CAN1_TTCNT`, etc.: types outside the device header,
  or registers not in the header). Registers the RM writes under a 32-bit name such as `R32_USBPD_STATUS` are
  checked against the 32-bit member EVT overlays in a union (`USBPD_STATUS`@0x08), not the 8-bit `STATUS`@0x09

**Not held**: the RM field descriptions (Chinese; too many rows, so not included. Obtainable with `extract_registers.py`).
D-7 (DMA channel → peripheral) is `dma_requests.csv`.

### `dma_requests.csv`

**Which peripheral's request connects to which DMA channel** (consumer's R-20 D-7). Not in the EVT headers;
only the "DMAx各通道外设映射表" (DMAx per-channel peripheral mapping table) in the DMA chapter of the reference manual has this information. The zh and en editions are read separately and matched on
(family, variant, dma, channel, request); agreement of both editions gives `confirmed`, one edition only gives `reference`.
Of 650 rows, 577 are confirmed; the 73 reference rows are all CH32V407 (whose RM exists only in zh).
**Spelling is as in the documents** (`request`: the zh edition's spelling, keeping the `*` of `TIM1_UP*` and X315's `_0`/`_1`; where the en edition spells it differently, `request_en`). The reading of the marks (`remap`) and the vocabulary-normalised `peripheral` are in the index's [`index/dma.csv`](../index/README.md).

| Column | Meaning |
|---|---|
| `variant` | Groups with a different DMA configuration within the same RM (CH32V20x/V30x). EVT macro names (`CH32V20x_D6` etc., `|`-separated). Empty otherwise |
| `dma` / `channel` | `DMA1`/`DMA2` and the 1-based channel number. **Empty for H417** (see below) |
| `request_id` | **H417 only.** DMAMUX request input number (1 to 123; the value written to `CHANNELx_MUX` is the number minus 1). Channels are not fixed; this request can be assigned to any channel |
| `request` / `request_en` | Document spelling. The `*` mark (V205/V20x/V30x: requests whose route is selected by `EXTEN_CTLR1`; the same request appears on both DMA1 and DMA2) is sometimes given only by the zh edition, in which case `request_en` holds the en spelling. X315's `_0`/`_1` are the default/remap side selected by `EXTEN_CTR` |
| `note` | Footnote marks (V006's `（1）（2）` = the TIM3 assignment differs between CH32M007 and V006/V007), notes on typos in the documents (V407's `13C`, H417's `I3X_RX`: spelling kept, "as printed") |

**How to read it**:
- "Which channel is USART1_TX on?" → look up `request=USART1_TX` (or peripheral=USART1) in the index `index/dma.csv`. When looking it up in this table, note that `request` may carry a mark. One request can appear on several channels (V205's `*`-marked ones, X315's `_0`/`_1`)
- Where one cell lists several requests (`TIM1_CH4` and `TIM1_TRIG`), the rows are split. The document's implication that **several requests on the same channel = cannot be used simultaneously** stands as is
- For CH32V20x/V30x, filter by `variant`. V20x_D6 is 1 DMA, 8ch; V20x_D8/D8W is 1 DMA, 8ch; V30x_D8/D8C is DMA1 7ch + DMA2 11ch
- H417 uses DMAMUX, and this table is its "request number table". Assignment to channels is done at run time by writing to `DMAMUX`

The tables come in 5 shapes (a one-page grid / continued on the next page without headings / channel 8 onwards in a separate table / 2 DMAs + `*` marks + cells
spanning pages / DMAMUX number table), all read with one reading method. The reading rules and the documents' quirks are written
at the top of `tools/build_dma_requests.py`.

### `pin_functions.csv` is **per pinout**, not a per-part-number function list

The datasheet pin table says so (`CH32V20x_30xDS0` states it right before the table):

> 注意，下表中的引脚功能描述针对的是**所有功能，不涉及具体型号产品**。不同型号之间外设资源有差异

Part numbers sharing the same pinout read the same pad rows, so `pin_functions.csv` (and `index/pinout.csv`) is **the union of the functions that silicon can provide**. CH32V303CBT6 has only 3 USARTs, but the pin table lists up to `UART8_TX`. **Which part number actually has what is counted per part number by the comparison table** (`product_attributes.csv`). Individual exceptions are named by footnotes (note 17: "CH32V303CBT6和CH32V303RBT6芯片均不支持TIM8").

If a consumer builds per-part-number function lists, **combine the two**. `tools/check_counts.py` cross-checks them and reports the counts:

```
pairs cross-checked 391  agree 352  more on the pin side (superset from a shared pinout) 30  fewer on the pin side 9
  - counted by the comparison table but on no pin at all: 0 pairs
```

"More on the pin side" is the shared-pinout share; "fewer on the pin side" are instances not brought out on that package (`CMP2`, `LPTIM1`, whose inputs may be internal only). **That "on no pin at all" is 0** is the guarantee that every peripheral the comparison table counts can be looked up from pins.

### `remap_fields.csv` / `remap_routes.csv`

Definitions of the AFIO route selectors and the value → route mapping. A `remap-N` in pin_functions.csv is resolved by following remap_routes (selector × value → signal/pad) → remap_fields (which bits of which register). The source is candidates/ (a join of EVT headers + RM register tables + RM remap grid + datasheet pin tables), but **every row is reference because the per-basis agreement record was not kept in the file**. Re-running the EVT/RM cross-check with a record and promoting to confirmed is the next task. The H41x/X315 line uses AF numbers rather than remap and is out of scope (held by `af-N` in pin_functions).

Three columns need care when reading.

**`bits` holds a register name per bit** -- `PCFR1:2;PCFR2:19;PCFR2:20`, listing `<register>:<bit>` separated by `;` from the LSB of the value upwards. Most selectors fit in one register, but on CH32L103 / CH32M103 / CH32V20x / CH32V30x / CH32V4x7 **selectors straddle PCFR1 and PCFR2**. Writing PCFR1 alone selects a different route without any error, so this is the qualification that keeps the upper half from being dropped. The `register` column summarises the same thing as `PCFR1|PCFR2`.

**`signal` is the original spelling as is**; the same role is written `USART1_TX` / `UART_TX` / `TX1` / `UTX` depending on the document. The vocabulary-normalised `peripheral`/`role` are in the index's [`index/routes.csv`](../index/README.md) (rows where no rule applies have both empty there).

**`UART` and `USART` are folded into one.** WCH's naming wavers even within one series: CH32V307's pin table says `UART5_TX` while the AFIO field is `USART5_REMAP`, and CH32M030's pin table says `UART_TX` while the field is `UART1_REMAP`. Without folding, a signal cannot find its own selector (in practice USART5 to 8 of CH32V303/V307/V317 were lost wholesale). The EVT headers of all 12 families were checked and **no family has AFIO fields for both UARTn and USARTn**, so they never denote different peripherals on the same silicon. The index's `peripheral` column becomes the normalised `USART5`, but the `field` column of `remap_fields.csv` and the `selector` id (assigned identifier) keep the original spelling (`UART1_REMAP` / `afio-uart1-remap`).

**Rows with `value=0` are the default route.** They expand the `default` column of the datasheet pin table as value 0, with `basis` `candidates(datasheet-pin-table-default:en)`. Since they sit in the same table as the post-remap routes, there is no need to go back to pin_functions.csv to find the default position.

**`valid_values` is a lower bound.** It is the union of three documents -- the values the RM remap grid lists, the values the datasheet pin table shows as actually having a route, and the values the EVT header enumerates as constants. The grid writes "don't care" digits as `x`, so it can overshoot (CH32X035's `USART4_RM=1xx` expands to 4 values); conversely, values no document mentions are dropped. **A value that is not enumerated is not necessarily unusable**, but every enumerated value is attested by some document. Every route appearing in `remap_routes.csv` is included here.

What `tools/check_tables.py` checks reading the tables alone: `bits` is in `register:bit` form, has no duplicates, and agrees with the `register` column; `valid_values` fits within the width of `bits`; `reset_value` is among `valid_values`; **every `remap_routes.value` is among `remap_fields.valid_values`**.

### `clock_configs.csv` / `clock_prescalers.csv` / `clock_sources.csv` / `clock_symbols.csv` / `clock_init.csv` / `evt_variants.csv`

The clock configurations EVT provides in `system_ch32*.c`. One function = one configuration, and the body is nothing but a sequence of register writes, so the oscillator, the frequency of each clock domain, bus dividers, PLL settings, flash latency and registers outside RCC are read out of it (`tools/extract_clock_tree.py` → `tools/build_clock.py`). **No PDF and no compiler are needed; it is read statically.**

Four columns need care when reading.

**`domains` lists `name=Hz` separated by `;`** -- `SYSCLK=400000000;CoreCLK[V5F]=400000000;CoreCLK[V3F]=100000000`. Most families have only `SYSCLK`, but **CH32V407 has SYSCLK and HCLK separate**, **CH32X315 has the three tiers SYSCLK/CoreCLK/HCLK**, and **CH32H417 is dual-core, so CoreCLK is per core**. A single-tier model `SYSCLK = HCLK` cannot represent these 3 families. Configurations whose name does not state a frequency (`SetSysClockToHSE` = tied directly to the crystal) are left **empty**, because the crystal frequency is a board attribute, not a chip attribute.

**`condition` is a compile-time branch.** CH32V307's 144MHz writes `RCC_PLLMULL18` under `#ifdef CH32V30x_D8` and `RCC_PLLMULL18_EXTEN` under `#else`. **One function, two facts**, so the rows are split per branch and `condition` says which.

**`outside_rcc` is the registers touched outside RCC.** CH32L103/V103/V205/V20x/V30x touch `EXTEN` when running the PLL from HSI (`EXTEN->EXTEN_CTR |= EXTEN_PLL_HSI_PRE`). **Only CH32V205 calls this register `CTLR0`.** It cannot be built under a "just look at RCC" model.

**`evt_copies` is "how many copies write this configuration".** EVT distributes `system_ch32*.c` per example, and **the copies are not identical** (CH32H417 has 12 kinds among 390). `162/168` is the mainstream, `4/168` is dedicated to specific examples. All are listed without discarding, leaving the judgement to the consumer.

Watch `ppre1`. CH32V20x/V30x have `ppre1=2` at every HSI-derived frequency, so **`PCLK1 = HCLK/2`**. Writing USART(BRR), I2C(FREQ/CKCFGR) or SPI(BR) under the assumption `PCLK1 = F_CPU` breaks the moment the PLL is used.

A row with an empty `flash_latency` means **that configuration does not write latency**. The range written also differs among the families that write it: V003 0 to 1, V006/V103/L103/X035 0 to 2, M030 0 to 3, V205 0 to 4.

**`flash_sck_div` is not wait cycles but the flash clock divider.** The FLASH_ACTLR of CH32X315 and CH32H417 has no `LATENCY[n:0]`; `SCK_CFG[1:0]` selects **how HCLK is divided**. Since the symbol name is `FLASH_ACTLR_LATENCY_HCLK_DIV4`, putting it in `flash_latency` would be read as "4 waits"; the units differ, so the column was split (`check_tables.py` rejects rows that have both). **CH32X315 is HCLK/1, /2, /4, /8; CH32H417 is HCLK/2.** Raising to 240MHz with the default left as is fails, so this is a fact that cannot be left out.

These 2 families **also write it differently** -- instead of touching the register directly, they copy it to a local variable, fix it, and write it back (`FLASH_Temp = FLASH->ACTLR; FLASH_Temp &= ~FLASH_ACTLR_SCK_CFG; ...`). Looking only at `BLOCK->REGISTER op= value` misses the whole thing, and this was the cause of the error "X315 does not write latency".

**These 3 tables alone are keyed by family, not by series.** The clock tree is a property of the silicon, and an EVT clone covers one silicon (`families.csv` holds which series it covers). Keyed by series, CH32V20x's 19 configurations would be duplicated to V203 and V208, and where two family dirs touch the same series (V203 has SKUs built from both CH32V20x and CH32V205) it **would pick up the tree of a different silicon**.

`clock_sources.csv` is "which clock can feed" USB, RTC, ADC, I2S, RNG, ETH etc.: pairs of the `RCC_*CLKSource_*` constants in `<fam>_rcc.h` and the register field they go to (`RCC_*CLKConfig` in `<fam>_rcc.c`). `condition` is needed here too -- for CH32V20x, **the value 0x300 of `RCC_RTCCLKSource_*` is `HSE/512` on D8/D8W and `HSE/128` otherwise**. The same value means something different, so dropping the branch puts the RTC off by 4×. USB's `PLLCLK_Div5` is also D8/D8W only. CH32X035 has no choices at all, consistent with its USB PHY needing no clock selection.

**`clock_symbols.csv` resolves the symbols of `pll` and `outside_rcc` to numbers.** These 2 columns alone hold **symbol names**, not values (`RCC_PLLMULL18`, `EXTEN_PLL_HSI_PRE`). The value cannot be derived from the name -- on CH32V307, `RCC_PLLMULL18` is `0x003C0000` and `RCC_PLLMULL18_EXTEN` is `0x00000000`: **the same "×18" is a different value** (`RCC_PLLMULL15` is `0x00340000`, the `_EXTEN` version `0x00380000`; the offset is not constant either). One row is (family, symbol); `value` is **the shifted decimal** (same convention as `clock_prescalers.value`), `register` is the destination as `BLOCK->REGISTER`, and `address` is that register's **absolute address**.

The address is included because the register name does not determine the location. EVT writes it as **a chain of base constants** such as `#define EXTEN_BASE (HBPERIPH_BASE + 0x3800)`, and the spelling differs by family (`HBPERIPH_BASE` versus `AHBPERIPH_BASE`). **Only CH32V205 calls the EXTEN register `CTLR0`, and CH32X315 places EXTEN at `0x400220C0`** (the others at `BASE+0x3800`). `tools/extract_addresses.py` resolves the base chain and the struct member offsets (counting reserved arrays too).

**`evt_variants.csv` is part number → compile-time macro.** The `condition` column refers to macros such as `CH32V20x_D8W` and `CH32V30x_D8`, but which part numbers fall under which is **written only in the comments** of the EVT device header. Three families are affected, and the `default` column says the default (what the header enables from the start):

| family | macro | Part numbers |
|---|---|---|
| CH32V20x | `CH32V20x_D6` (default) | F6/F8/G6/G8/K8/C6/C8 of CH32V203 (11 part numbers) |
| CH32V20x | `CH32V20x_D8` | CH32V203RBT6 only |
| CH32V20x | `CH32V20x_D8W` | the 4 part numbers of CH32V208 |
| CH32V307 | `CH32V30x_D8` | the 5 part numbers of CH32V303 |
| CH32V307 | `CH32V30x_D8C` (default) | the 9 part numbers of CH32V305/V307/V317 |
| CH32V006 | `CH32V002` / `CH32V004` / `CH32V005` / `CH32V006` (default) / `CH32V007_M007` | 26 part numbers by prefix match on the part number |

**A project that sets no macro silently builds with the default variant.** Building CH32V203RBT6 as D6 leaves HSE_VALUE at 24MHz (correctly 32MHz) and gives a different set of peripherals, in ways that do not show up in the tables.

**The `role` column of `clock_symbols.csv` says what the symbol is.** It is decided from observation -- `&= ~X` gives `mask`, `|= X` gives `value`, `while(REG & X)` gives `poll`. The breakdown of the 429 rows is value 222 / mask 173 / poll 34.

Masks are needed because **the setters are all read-modify-write**. Values alone cannot be written. However, **the vendor's own code sometimes ORs without clearing the field** (CH32V20x writes `RCC->CFGR0 |= RCC_HPRE_DIV1` relying on the reset value), so observing the source alone does not yield a complete set of masks. The shortfall is recognised from the shape of the header -- "the name is a prefix, at a `_` boundary, of two or more other symbols, and the value is a single contiguous run of bits". This matches exactly `RCC_HPRE` (versus `RCC_HPRE_DIV1..DIV512`), `RCC_SW` (versus `RCC_SW_HSI/HSE/PLL`) and `FLASH_ACTLR_LATENCY`, and does not match single bits such as `RCC_HSEON`. The register location is taken from the header's banner comment (`/*** Bit definition for RCC_CFGR0 register ***/`) -- because the name does not say that `RCC_ADCPRE` belongs to CFGR0.

The source is distinguished by `basis`: **`evt(device-header+system_ch32*.c)` is what the configuration code actually wrote (303 rows); `evt(device-header)` is merely defined in the header (126 rows)**.

**`confidence=conflict` is a symbol whose header contradicts itself within one line.** There are 5. The representative is `FLASH_ACTLR_LATENCY`: on CH32V003/V006/V103/X035 the value is `0x03` (2 bits wide) while the comment says `LATENCY[2:0]` (3 bits wide). The mask you can write changes depending on whether you trust the name or the number, and the narrower one cannot write latency 4. Both readings are kept in `basis` (`+!evt(device-header-comment:FLASH_ACTLR_LATENCY[2:0])`). **The mask width itself also differs by family**: `0x03` on V003/V006/V103/L103/X035, `0x07` on V20x/V307/M030, `0x0F` on V205.

The comparison is by **width**, not by position. The convention is that comments give bit numbers *within the field*, so `RCC_SWS[1:0]` does not contradict the mask `0xC` (2 bits placed at 3:2). Comparing by position would flag every family as contradictory.

**`clock_init.csv` is the `SystemInit` procedure.** Only this table has an order (`step` column), because the order is a **transcription**, not a policy -- `SystemInit` is a straight line without branches, and `RCC->CTLR |= 1` must come before clearing SW or there is no clock left to run on. On the other hand, **the order of clock switching (where latency is raised or lowered, enable → ready → switch → wait for SWS, timeout policy) is not included**. That is policy, and policy is not a device fact.

This table is needed because `SystemInit` is **written in raw hex, not symbols** (`RCC->CFGR0 &= 0xF8FF0000`). Symbol-based extraction sees nothing of it. `action` is one of 5: `set` (`|=`), `clear` (`&=`), `write` (`=`), `poll` (`while`) and `trim`, and **the `value` of `clear` is the AND mask as in the original** (the bits kept, not the bits dropped). Inverting it would be interpretation, so it is kept as is.

**The HSI factory trim** is also included as `action=trim` rows. 3 families read the factory value from a fixed address and calibrate with it. Skipping it leaves HSI out of spec.

| family | Read from | Address | Mask | Condition | Written to | Appears in function |
|---|---|---|---|---|---|---|
| CH32V003 | `CFG0_PLL_TRIM` | `0x1FFFF7D4` | `0x1F` | `!= 0xFF` | `RCC->CTLR` | `SetSysClockTo_48MHZ_HSI` |
| CH32L103 | `HSI_LP_TRIM_BASE` | `0x1FFFF72A` | `0x1F` | -- | `RCC->CTLR` | `SetSysClockToHSI_LP` |
| CH32V205 | `HSI_LP_TRIM_BASE` | `0x1FFFF72A` | `0x1F` | -- | `RCC->CTLR` | `SetSysClockToHSI_LP` |

**The symbol names differ by family** (`CFG0_PLL_TRIM` and `HSI_LP_TRIM_BASE`). CH32V003 also unconditionally writes the default `0x10` in `SystemInit` and later overwrites it if the factory value is not `0xFF` -- so **unprogrammed parts stay at the default**. On CH32L103 and CH32V205 it is only inside the low-power HSI configuration function, not always.

The sources are `evt(system_ch32*.c)`, `evt(rcc-header+rcc-driver)`, `evt(device-header+system_ch32*.c)`, `evt(device-header)`, `evt(system_ch32*.c+device-header)` and `evt(device-header-comment)`; being a single document, **every row is reference except the conflicts**. The reference manual describes the same fields, so making it the second reading is the path to confirmation.

### `debug_data.csv`

**Hart-side addresses of the debug module's data0/data1 registers** (consumer request R-27: the
addresses SDI print -- printf through the DMDATA0/1 mailbox -- writes to). One row per family.
**The address differs per die**: the V2 families (V003/V00x) use `0xE00000F4`, the V4 families
(L103/M103, V20x, V30x, X035) `0xE0000380`, most V3 families (M030, V205, V407, X315) `0xE0000340`,
but V103 (V3A) `0xE0000380`. The core generation does not decide it, hence per family.

Three sources; a row where they agree is `confirmed`:

| basis | Meaning |
|---|---|
| `evt(<debug.c>)` | `#define DEBUG_DATA0_ADDRESS ((volatile uint32_t*)0x…)` in each EVT's debug.c (the SDI_Printf implementation). All debug.c files of a family must agree (`+N more`) |
| `manual:qingke-vN(dataaddr=0x380)` | The hartinfo table in the QingKe processor manual's debug chapter. **V2 (`0x0f4`) and V4 (`0x380`) are fixed values**; V3 and V5 print `0xXXX` ("subject to what is actually read out"), recorded as `dataaddr=read hartinfo` and not counted as a source |
| `hartinfo:wch-linke(consumer 2026-08-26)` | hartinfo.dataaddr read through WCH-LinkE by the consumer (`curated/debug-data-measured.json`: V003, V103, V203, X035, L103) |

CH32H417 has no define in its EVT (no SDI_Printf example) and the V5/V3 manuals do not fix the value,
so its row stays with empty addresses and `missing`; a hartinfo reading is needed to fill it.
`dm_data1_addr` is always `dm_data0_addr + 4` (checked by `check_tables`). Built by `tools/build_debug_data.py`.

### `debug_wiring.csv`

**The WCH-Link manual's evidence for the debug wiring** (1-wire SWIO vs 2-wire
SWDIO+SWCLK; consumer request R-29). One row per series (26 rows; M103 is not in
the manual -- its wire count comes from the datasheet section heading). The source
is `WCH-LinkUserManual.PDF` (zh 2.8 / en 2.7, mirrored in WCH-common), two places,
and a row is `confirmed` when the editions agree:

- the **wiring table** (chip models / SWDIO / SWCLK) -> `swdio_pad`, `swclk_pad`;
  a `-` in the SWCLK column (V003) means 1-wire only, `swclk_pad` empty
- the **dual-support note** -> `dual_support=yes`

Extracted on the new path (`pipeline/extract/manual/extract_debug_wiring.py`,
structured-bundle input; the zh edition's page-spanning table is joined through
the L1 layer first). Chip-group tokens map to series through an exhaustive
dictionary; an unknown CH32 token fails the build. **Two rows disagree with the
pin tables** (V002/V004: the manual lumps the V00x group as dual-support, but
their pin tables have no SWCLK and the datasheet headings say 1-wire) -- the
evidence keeps the manual's claim as printed; the adjudication lives in
`index/debug_interfaces` (heading wins, the manual's dissent recorded in basis).

### `option_bytes.csv`

**The write layout of the user option bytes region** (consumer request R-30:
structured `target option get/set` and factory-restore flows need each byte's
meaning, the placement of the inverse-code bytes, and the write unit). One row
per byte, per family, from the RM option-bytes chapter's "User option bytes
information structure" table -- all 11 reference manuals carry it under that
caption (measured 2026-09-01). Extracted on the new path
(`pipeline/extract/rm/extract_option_bytes.py`, structured-bundle input;
page-spanning fragments joined through L1).

- `address` / `offset`: the byte's absolute address and its distance from the
  OB base (the region's lowest address). `check_tables` cross-checks the base
  against the `OB` block of `register_blocks.csv` -- the RM table against the
  EVT header, two independent sources
- `byte`: the byte's name as printed (RDPR / USER / Data0 / WRPR0 / Reserved ...)
- `complement_address`: where the inverse-code byte (`nRDPR` ...) sits; empty
  for bytes the table leaves unpaired (Reserved words)
- `write_unit`: how the region is programmed, classified from the control bit
  the "user option bytes programming" procedure names -- `half-word (OBPG)`
  (V003 style) or `fast page, 32-bit buffer writes (FTPG)` (L103/M030 style);
  `; complement auto-computed` is appended when the RM states the FPEC derives
  the high byte itself. The classification failing to match exactly one pattern
  stops the build

Rows are `confirmed` when the zh and en editions agree; CH32V407 (zh-only RM)
stays `reference`.

### `option_byte_fields.csv`

**Bit assignments and RM-stated reset values of the option bytes** (the
uncaptioned "Name/Byte" table that follows the structure table). One row per
stated field or byte group: `byte` (RDPR / USER / Data0-Data1 / WRPR0-WRPR3),
`bits`, `field`, `default`, and on the WRPR group row `wrpr_bit_protects` --
what one WRPR bit write-protects, from the group's description ("N sectors of
SIZE", plain "4KB", or the DBMODE-conditional sector size; a description
matching none of the three stops the build). The reset values are kept **at
the granularity the RM states** -- a full factory byte string would be a derivation, so composing
one is left to the consumer (who also holds factory-fresh dumps to compare).
Editions are compared on the **sequence of value tokens** in the reset cell
(the prose around them differs by language, and stray punctuation drifts into
the cell in the text layer); identifiers and values keep the source spelling
with whitespace and dashes folded. zh/en discrepancies backed by third
evidence are adjudicated (2026-09-02): X315's bit is `USBHSDLEN` (the EVT's
`ch32x3x5_flash.h` agrees with zh, not en's `USBFSDLEN`), FV2x/V3x's SRAM-split
field is `RAM_CODE_MOD` (the OBR readout side agrees; the en edition leaves it
unnamed), X035's reset value is `xxxb` (`rule:bit-width` -- [7:5] is 3 bits) --
each confirmed with the other edition's dissent kept in basis. Discrepancies
without third evidence stay `conflict` (the IWDG_SW/IWDGSW spelling, which
flips per document, and X315's WRPR granularity).

### `device_id_addresses.csv`

**Where the 32-bit chip identifier is read from, per family** (consumer request
R-28: chip-ID based target detection). The primary source is the EVT's
`DBGMCU_GetCHIPID()` -- the literal address in `*_dbgmcu.c`, or the `CHIPID`
macro resolved through the device header's `CHIPID_BASE` (L103/V205). All 12
families have a row, **including the ones third-party databases lack** (V205 /
V407 / X315 at `0x1ffff704`, and M030 at its own `0x1ffff384`). `check_tables`
cross-checks the address against `memory_map.csv`'s CHIPID region where one
exists, and against every `device_ids.csv` row's `id_addr`.

### `device_ids.csv`

**The 32-bit device_id per part number** (package variants differ in bits
[19:16]). Values imported from **ch32-rs/ch32-data** (`data/chips/*.yaml`; the
clone's commit and file are in `basis`) are `reference` -- a third-party
machine-readable database is not a primary source. A row becomes `confirmed`
only against a real-silicon read (WCH-LinkE; basis `device-id:wch-linke`, the
same style as `debug_data`'s `hartinfo:wch-linke`); `id_source` records the
measurement channel (`memory` address read / `attach` probe response) and is
empty for imported values. `dont_care_bits` is `[7:4]` (silicon revision, per
ch32-data's bit layout and probe-rs's match mask). ch32-data part numbers that
are not in `catalog/products.csv` are dropped visibly, not remapped -- several
differ from WCH's current catalog only in the trailing grade digit
(`CH32V006F8P6` vs our `CH32V006F8P7`).

### `link_firmware.csv`

The list of debugger firmware distributed by WCH. Generated by `tools/build_link_firmware.py`, which
reads `WCH-LinkUtility.ZIP` (or the same directory bundled with MounRiver Studio).
**The `.bin` files themselves are not placed in this repository** -- that would be redistribution; only
sha256, size and source URL are listed.

**This table can say "your Link is old"** (2026-08-29, F-11 resolved). The `wcfg_version` column is
WCH's own number (`CH32V307Ver=42` etc. in `wchlink.wcfg`); its correspondence to the `major.minor`
the device reports over USB is **`wcfg = major*10 + minor`** (major is 2 on every unit observed).
`reported_version` is that number decoded, and `measured_version` is what `tools/read_link_version.py`
read from a real device. **A row where the two disagree is marked `conflict`**; today they all agree
(only the two device kinds on hand are filled in, the other eight rows are empty). The derivation and
the measurements are in [docs/link-firmware-survey.ja.md](../docs/link-firmware-survey.ja.md) (Japanese).
"Is my local file the same as what is being distributed now" is answered by **sha256**.

The MCU assignment is not a guess but derived from the first instruction (`02` = 8051 `LJMP`,
`6f` = RISC-V `jal`). The 10 files in the Windows ZIP and in the Linux MounRiver Studio
**match completely, down to sha256**, so Windows is not needed to update.

### `systick.csv`

SysTick register layout. Extracted mechanically from `SysTick_Type` in `core_riscv.h`
(`tools/build_systick.py`). **There are 4 layouts, and only CH32V103 has `CMP` in a different position**
-- the other 11 families have `CMP@0x10`, but on CH32V103 `0x10` is `CMPHR` (upper 32 bits) and
the lower half of the compare value is at `0x0C`. The `write_bits` column says "writable only in 8-bit units".
CH32H417 has two `SysTick`s (dual-core, so one per core). The bit definitions exist only in the reference manual,
so they were placed in [register-map-survey](../docs/register-map-survey.ja.md#先出し1-systickr-24追補3のe-1) (Japanese).

### `pin_alternate.csv`

**Where to write the AF number.** The destination of the N in `route = af-N` (4,497 rows) of `pin_functions.csv`,
one row per (family, pad). `tools/build_pin_alternate.py`.

The 3 families CH32V205, CH32X315 and CH32H417 are **the generation without AFIO remap**;
they select routes with a 4-bit AF number per pin. This table is the counterpart of `remap_fields.csv`
for the remaining 9 families.

| Generation | Route selection | Table |
|---|---|---|
| remap (9 families) | Route number in the per-peripheral field of `AFIO->PCFR1` | `remap_fields.csv` / `remap_routes.csv` |
| AF (3 families) | AF number in the per-pin 4 bits of `AFIO->GPIOx_AFLR`/`AFHR` | This table + `pin_functions.route = af-N` |

`pin 0-7` is `AFLR`, `pin 8-15` is `AFHR`, 4 bits each from the bottom. This rule is not hard-coded;
it was verified by reading `~(0xF << (tmp << 2))` and `GPIO_PinSource >= 0x08` in EVT's `GPIO_PinAFConfig()`.
**The addresses differ per family** -- on CH32H417 the AF registers follow `PCFR1` directly in AFIO,
so `GPIOA_AFLR` is `0x40010004`; on CH32V205 and CH32X315, `ECR`/`EXTICR`/`CR` come first,
so they start at `0x40010020`. The same address points to a different register depending on the family
(`GPIOD_AFHR` of CH32H417 and `GPIOA_AFLR` of CH32V205).

`check_tables.py` checks **that the destination exists for every `af-N` row**.
This prevents route information from dead-ending; without it, V205's PWM had been wiped out wholesale
on the consumer side (F-10/F-12 in docs/worklist.ja.md (Japanese)).

### `memory_configs.csv`

The combination table for **parts whose FLASH/SRAM boundary moves with the 用户选择字 (user option bytes)**.
One row per (part number, code). `flash_bytes`/`sram_bytes` in `products.csv` state only the one pair the datasheet
comparison table lists, so the fact that it can be reassigned cannot be read from there (`tools/build_memory.py`).

The scope is **19 parts / 3 families** -- CH32V20x's `_D8`/`_D8W` (V203RB, V208),
CH32V30x's C parts (V303RC/VC, V307RC/VC/WC, V317VC/WC), CH32V407/V467.
CH32X315's `Link.ld` comment says it is variable, but **that is false**
(a leftover copy from V407: the header has no `RAM_CODE_MOD`, and 480K is fixed as 192K zero-wait +
288K non-zero-wait).

**There is nothing that can be called "the shipped pair".** RM 32.4.6 writes the reset value of `RAM_CODE_MOD` as `x`
and notes "USER and RDPRT are loaded from the 用户选择字 area after a system reset" --
the option bytes decide, and the RM does not state their shipped value. Nor does EVT decide.
Each example links a different pair (counting only the pairs in the code table):

```
CH32V20x   128K+64K ×14  144K+48K ×1
CH32V307   256K+64K ×17  192K+128K ×8  288K+32K ×2
CH32V407   576K+136K ×7  512K+200K ×1
```

So the column does not call itself "default" but **is named after its source** -- `datasheet_value` is
**the pair the datasheet comparison table lists** (the row corresponding to `sram_bytes` in `products.csv`) and
means nothing more. **Whoever produces a linker script for a variable part must write the option bytes
to match their own script**, rather than hard-coding one pair.

`condition` is a constraint attached to that code only (`110` is only for parts whose 批号倒数第六位 (sixth digit from the end of the batch number) is non-zero).
The write destination and the read source are held in separate columns -- `option_byte_bits` is
the position within the USER byte at `0x1FFFF800` (write side), `obr_bits` the position within `FLASH_OBR`
(read side).

**Every row is `conflict`.** The Chinese RM writes `RAM_CODE_MOD[2:0]` as `[9:7]`, the English one
writes `SRAM_CODE_MODE` as `[9:8]`, and the EVT header has the same 2-bit mask as the latter.
Since there are 5 combinations, 3 bits are required (with 2 bits `110` and `111` would be the same value),
so the Chinese edition is right; both are kept in `basis`.

### `interrupts.csv`

The interrupt vector table. One row per (family, number, condition). **The source is not the reference manual but
the EVT device header**, whose `IRQn_Type` enumeration carries number, name and one-line description all together.
Being the very definition that gets compiled, it is more reliable than reading the RM table.

`kind` separates `exception` (RISC-V processor exceptions) from `irq` (PFIC peripheral interrupts).
**The boundary number differs per family** -- most start at 16, but CH32H41x starts at **32**,
and 16 to 28 are IPC (inter-core communication) and HSEM (two cores, so the processor-side range is wider).
Hard-coding the number would misassign 5 of them, so the header's own banners
(`RISC-V Processor Exceptions Numbers` / `RISC-V specific Interrupt Numbers`) are
read. The check takes the form "every exception number is smaller than every interrupt number".

**The same number may denote a different peripheral.** Number 61 of CH32V20x is `UART4` under `_D6` and
`ETH` under `_D8`/`_D8W`. The `condition` column holds that condition, and `evt_variants.csv` holds
which part numbers set that macro (followed the same way as `clock_configs.condition`).

### `memory_map.csv`

The map of the address space. One row per (family, kind, region). Taken **from the `*_BASE` constants of the EVT
device header, not from the figure in DS chapter 1.2**. Resolution of relative chains
(`EXTEN_BASE = HBPERIPH_BASE + 0x3800`) is in `tools/extract_addresses.py`.

`kind` has 4 values:

```
memory       FLASH, SRAM, OB (用户选择字)
bus          PERIPH_BASE / APB1PERIPH_BASE / AHBPERIPH_BASE ── the bundling side
peripheral   TIM2_BASE, GPIOA_BASE … individual peripherals
link-origin  the start address the EVT linker script actually uses
```

**FLASH has two addresses.** The header's `FLASH_BASE` is `0x08000000` on CH32V307, while
the EVT linker script uses `ORIGIN = 0x00000000`. Both are real windows, and
**the one a linker-script producer needs is the latter**, so both are held as separate rows.
IAP examples write an ORIGIN shifted by the size of the bootloader, so `link-origin` takes
**the most common value** (= the start of the region).

`FLASH_R` is the FLASH control register (`0x40022000`), not storage, so it is `peripheral`.

### `features.csv`

The list of peripherals the series covered by a datasheet have. One row per (series group, section number).

**It cannot be built from the comparison table.** The comparison table only has "columns that differ within the series",
so peripherals common to the series have no column at all -- CH32V307 has only 6 attributes, with no row for USBHS or
Ethernet (it actually has both). **"No attribute = no feature" is
wrong.** The functional description chapter is a different thing: it lists the peripherals the product has as section headings.

**The chapter number cannot be hard-coded.** CH32L103 is `1.4`, CH32V103 is `1.5`, CH32V20x/V30x is
`2.5`. The chapter is found by its title (`Functional Description` / `功能概述`).

**Section numbers are language-independent**, so the zh/en correspondence can be taken without guessing ... but **that is no
guarantee**. For CH32V208, 18 of 23 sections correspond, while the English edition nests the communication peripherals as `2.5.15.1〜6`
and the Chinese edition numbers the same ones flat as `2.5.19〜`, so the rest do not line up
(11 `reference` rows). **Whether that section is absent from one edition or merely numbered differently cannot be
decided from this table** -- it takes matching the titles, so generation does not assert it and reports
the counts of matches and one-edition-only rows.

**Granularity is `series`.** One family can have several datasheets
(CH32V006 has 4: V002/V004/V006/V007), and **section numbers are unique only within one document**,
so with family as the primary key the `1.4.17` of different documents would collide.

The programming interface (worklist A8) also appears here -- `1-wire Serial Debug Interface (SDI)`
(CH32V002/V003/V004/V006/V007) and `2-wire SDI Serial Debug Interface`
(CH32L103, V103, V203, V30x, X035) stand as section headings.

### `eval_boards.csv`

Evaluation board documents and schematics. **Bundled with EVT rather than distributed by WCH separately**, so they are not in `documents.csv`
(the document catalog with download URLs). `kind` separates 5 kinds:

```
board          per-part-number board (SCHPCB/<part number>-R<revision>/)        78
board-variant  derived board for a different purpose (-UHSIF- / -USB)            3
board-manual:en / :zh   per-family manual              12 / 12
schematic-pdf  per-family schematic PDF                      12
```

**`board` is the most useful** -- it answers "is there an evaluation board for my part number, and which revision".

**Board names are spelled differently from part numbers, and 27 of the 80 boards miss on a plain match** (dropped temperature-grade
digit `CH32V203CCT`, shared with the CH32F line `CH32F&V208C`, `_` as separator, `x` wildcard
`CH32V4x7RET`, derived board `-UHSIF-`). The same kind of problem as `listed_as`, but boards are **built per package**,
so matching several part numbers is normal, and up to 3 trailing characters need completing (`CH32V208C` → `CBU6`).
The requirements differ from `resolve_full_names` for the comparison table (up to 2 characters, wants to converge on one), so the rule is separate.

The 3 boards that cannot be decided have an empty `parts` -- `CH32V006K8U6` and `CH32V203K6T6` are part numbers not in the catalogue,
`CH32X035USBPD_CH211` is a reference board including a companion chip. Forcing them onto a nearby part number would be a lie.

`path` is the location within the mirror. **It is excluded from the CJK check** --
`EVT/PUB/CH32V30x评估板说明书.pdf` is a real file with a Chinese name, and translating it would leave nothing
at the target. It is an identifier, not a "display value".

### `errata.csv`

One row per erratum (lot-dependent behaviour, hardware cautions). The source is `curated/errata.csv` (hand-edited); the `condition` column holds which lots/part numbers it applies to. **Rows with the page in both language datasheets recorded (source_zh/source_en) are confirmed**; one side only is reference.

Since errata can grow with future datasheet revisions, `tools/scan_errata.py` scans all datasheets, matches against the known ones (identified by the regular expressions in the `match` column of curated/errata.csv), and reports any unknown text as `NEW` (exit code 1). When NEW appears, add a row to curated/errata.csv and re-run to confirm NEW: 0.

### `operating_conditions.csv`

**The electrical characteristics chapter, per series** -- clocks, supply voltages, oscillators,
ADC, flash, I/O levels and reset timing. Generated by
`pipeline/extract/datasheet/build_operating_conditions.py` (the new structured path:
the frozen extraction logic on bundle input, plus the consumption-current and
wake-up-time rows; `tools/build_operating.py` remains as the frozen reference).
The combining layer cleans the `parameter`/`condition` text of the base rows without
touching the frozen logic: split subscripts are rejoined (`V DD` -> `VDD`), fullwidth
punctuation in the description columns is normalized, and a cell cut by a page break
(`Accuracy of HSI oscillator (after` + `calibration)` on the next page) is completed from
the bundle's merged table grid when exactly one continuation closes the parenthesis.

**Which rows are taken is not decided by a list of symbols.** A symbol names its physical
quantity in its stem (`V_*` a voltage, `I_*` a current, `t_*` a time), so a row is taken when
its unit matches the quantity its stem claims (`UNIT_FOR`). A datasheet's notation is fixed, so
this survives a new family better than a list would. `T_S_*` (an ADC sampling time, not a
temperature), `t_RET` (years) and `N_END` (times) are stated ahead of the general rules.

Values may be a formula rather than a number: an I/O threshold is written against the supply
(`0.29*VDD-0.07`, `0.41*(VDD-1.8)+1.3`), and a bound may be another symbol (`F_HCLK`, `VREF+`).

**Not collected** (the reasons are in the tool's docstring):

- **supply current under a stated condition** -- `I_DD` is tabulated with the operating
  condition (`F_HCLK = 48MHz`, `开启`) in the column the parser reads as `min`, so the value is
  not a value. A table-shape problem, not a symbol problem
- **formulas whose subscript became `*` in the text layer** (`0.45*V+*0.41`, which is
  `0.45*V_DD+0.41`). A sibling row makes it obvious to a person, but that is a guess, so the
  row is dropped rather than filled in
- **rows where two symbols were folded into one** (`t_/t_r(SCK)_f(SCK)`): the values cannot be
  assigned to either symbol

- **`F_MAIN`**: the **系统主频 (system main frequency)** advertised in the feature list on page 1 of the datasheet. This is the frequency the product is marketed with
- `F_HCLK`/`F_PCLK*`/`F_CORE*`: **the maximum** from the "general operating conditions" table in the electrical characteristics chapter. A separate fact from F_MAIN, and the values disagree (CH32V003: 48MHz in the text, 50MHz maximum in the electrical characteristics). The Clock column of the README prefers F_MAIN and falls back to F_HCLK / F_CORE only for the series that lack it (CH32X035, CH32H41x)
- `V_DD`: operating voltage. There are condition rows such as with ADC in use, with USB in use
- **`F_USBCLK` / `F_HCLK(USB)`** (added 2026-08-22): USB clock requirements. They are in the body text rather than a table, so they are taken from prose.
  **48MHz is not the story for every family** -- CH32V407/V467 and CH32X305/X315, which have USBHS/USBSS, have dedicated PLLs
  (`USBHS_PLL` 320/480MHz, `USBSS_PLL` 125/357/625MHz) and do not use a 48MHz USBCLK.
  No rows appear for these 2 families. `F_HCLK(USB)` is **the enumeration of CPU frequencies allowed while USB is in use**,
  stated directly by the documents (V103: 48/72; L103: 48/72/96; V20x, V30x: 48/96/144).
  **A discrete set cannot be expressed as min/max**, so there is one row per allowed value (value in `typ`)
- **`typ` column** (added 2026-08-21): oscillators are specified as "**nominal value + accuracy**" and have no min/max. The spread of `F_HSI` is on the ±% side in `ACC_HSI`, and the frequency itself appears only in `typ`. While this column was missing, `F_HSI` was a row with empty min/max, and **SYSCLK could not be computed because the PLL input was undetermined**. Some tables have a typical-value column in only one of the two languages, so they are cross-checked only when both have a value, and the Chinese edition fills in where the English is empty (numbers are language-independent)

  **HSI is not 8MHz. There are 5 values across families.**

  | HSI nominal | family |
  |---|---|
  | **8 MHz** | CH32L103/M103, V103, V203/V205/V208, V303 to V317 |
  | **20 MHz** | CH32V407/V467, X305/X315 |
  | **24 MHz** | CH32V002 to V007, M007, V003 |
  | **25 MHz** | CH32H415/H416/H417 |
  | **48 MHz** | CH32X033/X035 |

  The low-power-mode HSI is a separate row too (**1MHz** on CH32L103/M103 and V203/V205; 30 to 58kHz on CH32V00x with `HSI_LP=1`). `F_LSI` also has min/typ/max, and **CH32V203 has 25/32/45kHz only for `applied for V203RBT6`**, differing from the other part numbers (25/39/60kHz) -- which matches the only part number `evt_variants.csv` assigns to `CH32V20x_D8`
- **Oscillators** (added 2026-08-21): `F_HSI`/`F_LSI` and `ACC_HSI`/`ACC_LSI` (**accuracy**; the `condition` column holds the temperature range, one row per range), `F_HSE_ext`/`F_LSE_ext` (**allowed range of an external clock**. E.g. CH32L103 3 to 25MHz, CH32M030 4 to 25MHz, CH32V00x 3 to 32MHz, CH32H41x 5 to 32MHz), `F_OSC_IN`/`F_XI` (crystal), `DuCy_*` (duty cycle)
- **PLL** (same): min/max of `F_PLL_IN`/`F_PLL_OUT`/`F_VCO`. E.g. CH32L103 input 3 to 25MHz, output 18 to 96MHz; CH32H41x output 100 to 600MHz
- **`f_ADC`** (same): the ADC clock maximum. **It differs greatly by family, and it also depends on the supply voltage.** Only this symbol starts in lower case, following the original's notation

  | family | ADC clock maximum |
  |---|---|
  | CH32V003 | **6 / 12 / 24 MHz** (V_DD 2.8 to / 3.2 to / 4.5 to 5.5V) |
  | CH32X033/X035 | **6 / 8 MHz** (V_DD < 3.2V / ≥ 3.2V) |
  | CH32V103/V203/V208/V303 to V317 | 14 MHz |
  | CH32M030 | 18 MHz |
  | CH32V407/V467 | 30 MHz |
  | CH32L103/M103/M007/V002/V004 to V007 | 48 MHz |
  | CH32V205 | 64 MHz (zh and en disagree; the zh edition says 96 MHz → conflict) |
  | CH32H41x/X305/X315 | 80 MHz |

  When `SYSCLK` is raised, the ADC divider must be re-selected, and this is the criterion. Note that **X035 is 6 to 8MHz, nearly an order of magnitude stricter than the other families**

Some rows have the maximum written as another symbol -- the `max` of `F_PCLK1` as `F_HCLK`. Not a number, but it is the very fact "PCLK1 does not exceed HCLK", so it is taken.

The display text comes from the English edition; min/typ/max/unit are confirmed when the two language editions agree. The series column is expanded through the datasheet → products join (`;`-separated).

The oscillator and ADC tables are on separate pages from the main table (6 kinds: HSI/LSI/external high-speed/external low-speed/crystal/ADC), and the extractor **walks all pages rather than stopping after finding one target table**. Moreover, **tables span pages, and the continuation page has no header row** (the ADC clock maximum row of CH32V003 is only on the page after the caption). If the column count is the same, the previous column layout is inherited for reading. As a side effect, other `F_*` on the same page (`F_prog` = flash programming clock, `F_max(IO)out` = maximum IO output frequency) also come in, but all of them are real frequency limits. Table inheritance (continuation rows with an empty symbol cell) is right for multi-condition rows but picks up the wrong symbol when a different parameter follows, so rows are rejected by **the fit of symbol, unit and value** (e.g. a row where an `F_*` carries a duty-cycle `%`). Rejected rows are listed at run time.

The rest of the electrical characteristics chapter (absolute maximum ratings, current consumption, flash endurance, wake-up time) is not yet collected (see docs/extraction-survey.ja.md (Japanese)).

### `evt_examples.csv`

The list of examples bundled with EVT. Generated by `tools/build_evt_examples.py`. The EVT catalog (`EVT/<name>_List_EN.txt` and its Chinese edition; the Chinese edition is GBK) is the authority for the index, cross-checked against **whether the example actually exists in the unpacked EVT tree**. Confirmed when 2 or more of the 3 bases (the two catalog editions + the actual tree) agree.

reference is a disagreement between catalog and tree, a fact on the document side (groups the catalog does not mention, example names absent from the tree, spelling variations within the catalog). Groups absent from the catalog are reported to stderr at generation time (currently: USBHS of CH32V407, SYSTICK of CH32X035, USBHS/USBSS of CH32X315). Descriptions are taken from the English edition only; rows with a description only in the Chinese edition are left empty.

## Confirmation is "an overall judgement of the bases"

Every CSV has a separator column whose name and every value are `#`; **everything to its right is metadata (confidence/basis), not the data proper**. Because that cell is `#` on every row, wherever you look in the file you can see the boundary "data ends here". When reading, dropping the columns from `#` onwards gives a plain data table. They are not split into a separate file so that data and metadata cannot drift apart structurally.

| `*_confidence` | Judgement |
|---|---|
| `confirmed` | Two or more independent bases agree, **or a person checked the content and recorded the basis** |
| `reference` | Only one basis, with neither corroboration nor contradiction. A reference value |
| `conflict` | Bases contradict each other. **Needs human judgement** |
| `missing` | Not stated in any basis |
| `partial` / `varies-by-package` | (series.csv only) uneven confidence among the members / package dependent |

**Confirmation is not limited to automation.** A throwaway script presents the relevant passages, a person cross-checks both language editions, and if confirmed, the basis is recorded in `curated/`. Core and ISA are done this way (`curated/series-facts.json`, checked 2026-08-18).

## Kinds of basis (basis notation)

| basis | Content | Treatment |
|---|---|---|
| `products:zh/en`, `ordering:zh/en` | Comparison table, ordering table. zh is the original, en the translation | Normal basis |
| `pin-table` | Lead count and GPIO count from the pin definition table (from candidates/) | **soft**: agreement pushes confidence up; disagreement is only recorded as `?pin-table` (the table extraction may drop rows) |
| `package-pdf:zh/en` | Body size and pitch from the table of contents of PACKAGE.PDF (package outline drawings) | Normal basis. Variant suffixes such as `QFN48X7_A` are looked up by the base name |
| `rule:pn-letter` | Second-to-last character of the part number = package type (T=LQFP etc.; 84+8 cases, no exceptions) | Check. A contradiction is conflict (`!` notation) |
| `rule:pn-temp-grade` | Last digit of the part number = temperature grade (6 = -40 to 85℃, 7 = -40 to 105℃; 32 cases stated, no exceptions) | Basis and check for temperature. Where the comparison table lists only the maximum, it goes to the check as `products:zh(max)`. Trailing 1 and 3 are out of scope |
| `rule:package-name` | The number in the package name = lead count | Basis and check for pin_count |
| `rule:part-number-structure` | The series is determined by the part number structure | Basis for series |
| `manual:…` | A basis a person checked and recorded (curated/) | Treated as confirmed |

**Rule not adopted**: the capacity code in the part number (8 = 64K etc.). Because the comparison table lists the maximum configuration for the V30x/H41x line, 24 of 92 cases disagree, so it does not hold as a rule.

## Notation differences absorbed

Unit words (`8-channel`↔`8路`), full-width symbols, temperature → two numbers, capacity → bytes (including removal of footnote `(2)`), dimensions sharing the package cell (`LQFP64M(10*10)`), wildcard columns (`C6x6`), expansion of abbreviated part numbers. **Without absorbing these, real differences get buried.**

## Known items to check

- **Package of CH32V004F6U1**: was a conflict between zh `QFN20L` / en `QFN20`, but a revision of the en datasheet corrected it to `QFN20L`, and regeneration resolved it by itself to confirmed with 4 bases agreeing in both languages (checked 2026-08-19)
- **CH32V203CCT6**: the 256K part listed in V205DS0. Counted as series=V203, but the design may be of the V205 (青稞V3B) line. Individual core description not yet checked
- **Core of CH32H415/H416**: reference, inferred from the H417 description (V5F+V3F dual core)

## Row order and column order

The rules are fixed so that regeneration or mid-file insertion keeps diffs local.

- **Row order**: in every table, simple ascending order of the row's identifier. families = `family`, series = `series`, products = `(part_number, family, datasheet)`. Since part_number alone does not guarantee uniqueness in products (the same part number may appear in several datasheets), rows are ordered by the identifier tuple
- **Column order**: important values from the left (identifier → specs → package details → source). Then the separator `#` column (`#` on every row), and to its right the `*_confidence` block and the `*_basis` block in the same order
- **pins tables**: the row identifier is (part_number, pin, pad) / (part_number, pad, signal, route), in ascending order. The source `table` and `datasheet` are to the right of `#` (meta side) as data for verification

## Images (currently unused)

The generated READMEs do not reference images. A mechanism to cut figures out of the datasheets was
prepared (`tools/extract_images.py` / `tools/check_images.py`), but since the tuning of the cut-out
quality is not finished, the output is not placed in the mirror. Instead of pinout
figures, the README outputs a package → part number → datasheet correspondence table.

What was learned from the cut-outs (premises for resuming):

- Figure captions differ per datasheet in both placement and notation. Placement: above, below, inside, or side by side on one line (4 ways); notation: full part number, masked (`CH32V103Cx`), temperature grade omitted (`CH32V007K8U`), slash-joined (`CH32V303RxT6/CH32V303RCT7`) (4 ways)
- Text rotated 90 degrees has PDF coordinates that differ from the actual rendering, so the extent cannot be determined by coordinate calculation alone. The edges of the rendered image must be inspected and the area widened again
- Even for the same pinout there is a separate figure per part number, so the representative part number in the file name and the part number in the figure can differ (6 of 82)
- Some editions, such as CH32V407DS0, have pin numbers overlapping the footer rule

The series block diagrams (`system_*.png`) are not in the original datasheets; they come from WCH's product pages. 10 of the 27 series are hand-made, and 17 series are missing. `tools/build_system_figures.py` can generate the equivalent information from tables/ as SVG, but since the appearance is different, adoption is on hold.

## Generation

**The front door is `uv run pipeline/publish/regenerate.py --full`** — it runs
everything below in dependency order on structured-bundle input and finishes
with the checks (about an hour; `regenerate.py` without `--full` is the fast
new-path-only variant). The list below is for regenerating one table at a time.
PDF-reading tools run through `pipeline/extract/run_patched.py`, which swaps
their input layer to the structured bundles (the tool's own code is unchanged);
running them as plain `tools/<name>.py` would read the PDFs directly, which is
off the execution path since the switchover. Each tool decides its output
location in `tools/paths.py` (`--out <dir>` is an override for testing). In
order from the top.

```sh
uv run pipeline/extract/run_patched.py build_all --jobs 1  # .cache/candidates/ (extraction candidates per part number; serial -- the patch does not survive worker processes)
uv run pipeline/extract/run_patched.py build_tables                    # catalog: families/series/products/packages/cores/documents  evidence: product_attributes/errata
uv run pipeline/extract/run_patched.py build_pins                      # pins/pin_functions (takes a few minutes)
uv run pipeline/extract/run_patched.py build_remap                     # remap_fields/remap_routes (from candidates)
uv run pipeline/extract/datasheet/build_operating_conditions.py  # operating_conditions (new path, bundle input; frozen base rows + A11 rows)
uv run tools/build_evt_examples.py              # evt_examples (from the EVT tree and catalog)
uv run tools/build_clock.py                     # clock_configs/clock_prescalers/clock_sources/clock_symbols/clock_init (from EVT)
uv run tools/build_systick.py                   # systick (from EVT's core_riscv.h)
uv run tools/build_pin_alternate.py             # pin_alternate (from EVT's AFIO structure and GPIO driver)
uv run pipeline/extract/run_patched.py build_memory                    # memory_configs (from the RM and EVT's Link.ld; takes a few minutes)
uv run tools/build_interrupts.py                # interrupts (from EVT's IRQn_Type enumeration)
uv run tools/build_memory_map.py                # memory_map (from EVT's *_BASE and Link.ld ORIGIN)
uv run pipeline/extract/run_patched.py build_features                  # features (from the datasheet functional description chapter; takes a few minutes)
uv run pipeline/extract/run_patched.py build_timers                    # timers (from the RM's TIMx_CNT headings; takes a few minutes)
uv run pipeline/extract/run_patched.py build_flash_geometry            # flash_geometry (EVT flash driver + RM 闪存 (flash) chapter)
uv run pipeline/extract/run_patched.py build_opa_cmp_registers         # opa_cmp_registers (EVT headers + RM register tables. Reads the whole RM; slow)
uv run pipeline/extract/run_patched.py build_clock_enables             # clock_enables (EVT rcc.h + RM register tables. Reads the whole RM; slow)
uv run pipeline/extract/run_patched.py build_adc_internal              # adc_internal (prose and electrical characteristics tables of both datasheet editions)
uv run pipeline/extract/run_patched.py build_usbpd_plumbing            # usbpd_plumbing (after clock_enables. EVT headers + RM)
uv run pipeline/extract/run_patched.py build_registers  # register_blocks/registers/register_fields + index/register_layouts (EVT headers + whole RM; about 19 minutes on bundles. No cache -- a stale --rm-cache once rolled the canonical back to a pre-revision RM reading)
uv run pipeline/extract/run_patched.py build_dma_requests              # dma_requests (DMA chapter grids of the RM zh/en. Scans all pages; about 15 minutes)
uv run tools/build_eval_boards.py               # eval_boards (from EVT's PUB/)
uv run tools/build_feature_tags.py              # index/features (from features + the comparison table. No PDF needed)
uv run tools/build_capabilities.py              # index/capabilities (from product_attributes. No PDF needed; before build_index, whose manifest hashes it)
uv run tools/build_conflicts.py                 # index/conflicts (every conflict mark in catalog/ and evidence/. No PDF needed; likewise before build_index)
uv run tools/build_sources.py                   # catalog/sources (editions of the mirror that was read. **Run as part of the full generation**)
uv run tools/build_evt_variants.py              # evt_variants (from the EVT device headers)
uv run tools/build_link_firmware.py             # link_firmware (from WCH's distribution)
uv run pipeline/extract/run_patched.py build_debug_data                # debug_data (defines in EVT debug.c + QingKe manual hartinfo table + measurements)
uv run pipeline/extract/manual/extract_debug_wiring.py  # debug_wiring (WCH-Link manual wiring table + dual-support note; new path, bundle input)
uv run pipeline/extract/rm/extract_option_bytes.py  # option_bytes + option_byte_fields (RM option-bytes chapter; new path, bundle input)
uv run tools/build_device_ids.py                # device_id_addresses + device_ids (EVT DBGMCU_GetCHIPID + ch32-data import)
uv run tools/build_index.py                     # **index**: index/parts, pinout, routes, registers, register_map, dma, timers + manifest (seconds)
uv run tools/build_readme.py                    # generated/readme/*.md (README for each family)
uv run pipeline/extract/images/run_extract_images.py  # image/ in each repo (frozen tool via the source-hash gate; takes a few minutes)
uv run tools/check_images.py [--missing|--prune] # list of required images and check
uv run tools/check_tables.py                    # reference joins of all tables, index ⊆ evidence, manifest
uv run tools/check_counts.py                    # peripheral counts of the comparison table vs pin instance counts
uv run tools/check_docs.py                      # row counts and hole states claimed by the documents vs the tables
node tools/check_viewer.js                      # what pins.html shows (its script evaluated without a DOM)
uv run pipeline/extract/run_scan_errata.py                     # incremental errata check (exit code 1 on NEW)
uv run tools/build_tables.py --family CH32V006  # one family only
```
