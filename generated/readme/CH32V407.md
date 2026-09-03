# CH32V407

<!-- This file is generated from ch32-riscv-ug/ch32-device-data (index/ + evidence/ + tools/build_readme.py). Edit there, not here. -->

*Generated from the mirror at commit [`7503337`](https://github.com/ch32-riscv-ug/CH32V407/tree/7503337fc5064fb05a64744ec6db2dec10390108) (2026-08-29). Newer PDFs may exist upstream; see Documents below.*

[Choose a part](#product-comparison) &middot; [Pin viewer](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407) &middot; [Pin maps](#pin-maps--alternate-functions) &middot; [Errata](#errata) &middot; [Examples](#evt-examples) &middot; [Documents](#documents) &middot; [Address map](#address-map)

## Quick start

### Debug / serial defaults

Where these land **without writing a remap register**. SWD is live at reset; the UART pads are not -- the pin must still be put into alternate-function mode. See `route` in evidence/README.ja.md.

| Series | SWDIO | SWCLK | UART TX | UART RX |
|---|---|---|---|---|
| CH32V407 | PA13 | PA14 | PA9 (USART1); PA2 (USART2) | PA10 (USART1); PA3 (USART2) |
| CH32V467 | PA13 | PA14 | PA9 (USART1); PA2 (USART2) | PA10 (USART1); PA3 (USART2) |

## Series

| Series | Core | ISA | Flash | SRAM | Main clock | VDD | Packages | Products | Official |
|---|---|---|---|---|---|---|---|---|---|
| **CH32V407** | QingKe V3V | RV32IMABCV-X | 512K | 200K | 200 MHz | 2.9-3.6V | LQFP100,LQFP64,QFN68 | 3 | [en](https://www.wch-ic.com/products/CH32V407.html) / [zh](https://www.wch.cn/products/CH32V407.html) |
| **CH32V467** | QingKe V3V | RV32IMABCV-X | 512K | 200K | 200 MHz | 2.9-3.6V | LQFP100,LQFP64,QFN68 | 3 | [en](https://www.wch-ic.com/products/CH32V467.html) / [zh](https://www.wch.cn/products/CH32V467.html) |

## Product comparison

### CH32V407 product comparison

Only the 3 rows that differ between these 3 products; the other 25 are the same for all of them.

| | [CH32V407&#8203;RET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407RET6)&#8203;(LQFP64) | [CH32V407&#8203;VET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407VET6)&#8203;(LQFP100) | [CH32V407&#8203;WEU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407WEU6)&#8203;(QFN68) |
|---|---|---|---|
| **GPIO** | 49 | 77 | 55 |
| USBHS (Include PHY) | 1 (USBHS1) | 2 | 2 |
| FSMC | - | 1 | - |

<details><summary>All 28 rows</summary>

| | [CH32V407&#8203;RET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407RET6)&#8203;(LQFP64) | [CH32V407&#8203;VET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407VET6)&#8203;(LQFP100) | [CH32V407&#8203;WEU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407WEU6)&#8203;(QFN68) |
|---|---|---|---|
| **Flash** | 512K | 512K | 512K |
| **SRAM** | 200K | 200K | 200K |
| **GPIO** | 49 | 77 | 55 |
| **Temperature** | -40..85C | -40..85C | -40..85C |
| Advanced-control (16-bit)(1) | 2 | 2 | 2 |
| General-purpose (16-bit) (1) | 4 | 4 | 4 |
| Basic (16-bit) | 2 | 2 | 2 |
| Timer Watchdog | 2 (WWDG + IWDG) | 2 (WWDG + IWDG) | 2 (WWDG + IWDG) |
| SysTick (32-bit) | Support | Support | Support |
| RTC | Support | Support | Support |
| ADC Unit | 2 | 2 | 2 |
| ADC channel | 16+2 | 16+2 | 16+2 |
| DAC (Unit) | 2 | 2 | 2 |
| OPA | 1 | 1 | 1 |
| RNG | 1 | 1 | 1 |
| USART | 10 | 10 | 10 |
| SPI/I2S | 3/2 | 3/2 | 3/2 |
| I2C | 1 | 1 | 1 |
| I3C | 1 | 1 | 1 |
| CAN | 1 | 1 | 1 |
| SDIO | 1 | 1 | 1 |
| USBHS (Include PHY) | 1 (USBHS1) | 2 | 2 |
| Ethernet | MAC+10M/100M PHY | MAC+10M/100M PHY | MAC+10M/100M PHY |
| DVP | 1 | 1 | 1 |
| LTDC | 1 | 1 | 1 |
| FSMC | - | 1 | - |
| ARGB | 1 | 1 | 1 |
| CPU main frequency | Max: 200MHz | Max: 200MHz | Max: 200MHz |

</details>

### CH32V467 product comparison

Only the 4 rows that differ between these 3 products; the other 25 are the same for all of them.

| | [CH32V467&#8203;RET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467RET6)&#8203;(LQFP64) | [CH32V467&#8203;VET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467VET6)&#8203;(LQFP100) | [CH32V467&#8203;WEU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467WEU6)&#8203;(QFN68) |
|---|---|---|---|
| **GPIO** | 48 | 76 | 54 |
| Extended PSRAM (Bytes) | 4M | 8M | 8M |
| USBHS (Include PHY) | 1 (USBHS1) | 2 | 2 |
| FSMC | - | 1 | - |

<details><summary>All 29 rows</summary>

| | [CH32V467&#8203;RET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467RET6)&#8203;(LQFP64) | [CH32V467&#8203;VET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467VET6)&#8203;(LQFP100) | [CH32V467&#8203;WEU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467WEU6)&#8203;(QFN68) |
|---|---|---|---|
| **Flash** | 512K | 512K | 512K |
| **SRAM** | 200K | 200K | 200K |
| **GPIO** | 48 | 76 | 54 |
| **Temperature** | -40..85C | -40..85C | -40..85C |
| Extended PSRAM (Bytes) | 4M | 8M | 8M |
| Advanced-control (16-bit)(1) | 2 | 2 | 2 |
| General-purpose (16-bit) (1) | 4 | 4 | 4 |
| Basic (16-bit) | 2 | 2 | 2 |
| Timer Watchdog | 2 (WWDG + IWDG) | 2 (WWDG + IWDG) | 2 (WWDG + IWDG) |
| SysTick (32-bit) | Support | Support | Support |
| RTC | Support | Support | Support |
| ADC Unit | 2 | 2 | 2 |
| ADC channel | 16+2 | 16+2 | 16+2 |
| DAC (Unit) | 2 | 2 | 2 |
| OPA | 1 | 1 | 1 |
| RNG | 1 | 1 | 1 |
| USART | 10 | 10 | 10 |
| SPI/I2S | 3/2 | 3/2 | 3/2 |
| I2C | 1 | 1 | 1 |
| I3C | 1 | 1 | 1 |
| CAN | 1 | 1 | 1 |
| SDIO | 1 | 1 | 1 |
| USBHS (Include PHY) | 1 (USBHS1) | 2 | 2 |
| Ethernet | MAC+10M/100M PHY | MAC+10M/100M PHY | MAC+10M/100M PHY |
| DVP | 1 | 1 | 1 |
| LTDC | 1 | 1 | 1 |
| FSMC | - | 1 | - |
| ARGB | 1 | 1 | 1 |
| CPU main frequency | Max: 200MHz | Max: 200MHz | Max: 200MHz |

</details>

## Packages & pinout drawings

Pinout drawings are in the datasheet (chapter *Pinouts*):

| Package | Products | Datasheet | Outline |
|---|---|---|---|
| LQFP64 | CH32V407RET6 | [en](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP64.png) |
| LQFP100 | CH32V407VET6 | [en](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP100.png) |
| QFN68 | CH32V407WEU6 | [en](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_QFN68.png) |
| LQFP64 | CH32V467RET6 | [en](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP64.png) |
| LQFP100 | CH32V467VET6 | [en](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP100.png) |
| QFN68 | CH32V467WEU6 | [en](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_QFN68.png) |

## Pin maps & alternate functions

> [!NOTE]
> These are the **pin-table superset**: the datasheet prints one pad table for every product that shares a pinout, so a pad row does not mean this part has the peripheral. Use the product comparison table above for what a given part number contains.

### CH32V407 pin map

Pin functions (filterable): [ALL](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407) [ADC](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407&features=ADC) [I2C](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407&features=I2C) [SPI](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407&features=SPI) [SYS](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407&features=SYS) [TIM](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407&features=TIM) [UART](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407&features=UART) [USB](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407&features=USB)

<details><summary><b>CH32V407 pin map</b> (92 pads x 3 products)</summary>

| Pin name | Type | [CH32V407&#8203;RET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407RET6)&#8203;(LQFP64) | [CH32V407&#8203;VET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407VET6)&#8203;(LQFP100) | [CH32V407&#8203;WEU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V407WEU6)&#8203;(QFN68) | Notes |
|---|---|---|---|---|---|
| PA1 | I/O/A | 15 | 24 | 15 |  |
| PA2 | I/O/A | 16 | 25 | 16 | UART TX (USART2) |
| PA3 | I/O/A | 17 | 26 | 17 | UART RX (USART2) |
| PA4 | I/O/A | 19 | 29 | 19 |  |
| PA5 | I/O/A | 20 | 30 | 20 |  |
| PA6 | I/O/A | 21 | 31 | 21 |  |
| PA7 | I/O/A | 22 | 32 | 22 |  |
| PA8 | I/O | 43 | 67 | 43 |  |
| PA9 | I/O | 44 | 68 | 44 | UART TX (USART1) |
| PA10 | I/O | 45 | 69 | 45 | UART RX (USART1) |
| PA11 | I/O/A | 46 | 70 | 46 |  |
| PA12 | I/O/A | 47 | 71 | 47 |  |
| PA13 | I/O | 48 | 72 | 48 | SWDIO |
| PA14 | I/O | 50 | 76 | 52 | SWCLK |
| PA15 | I/O | 51 | 77 | 53 |  |
| PB0 | I/O/A | 25 | 35 | 25 |  |
| PB1 | I/O/A | 26 | 36 | 26 | UART TX (USART9) |
| PB2 | I/O | - | 37 | 27 |  |
| PB3 | I/O | 56 | 89 | 58 |  |
| PB4 | I/O | 57 | 90 | 59 |  |
| PB5 | I/O | 58 | 91 | 60 |  |
| PB6 | I/O | 59 | 92 | 61 |  |
| PB7 | I/O | 60 | 93 | 62 |  |
| PB8 | I/O | 61 | 95 | 64 |  |
| PB9 | I/O | 62 | 96 | 65 |  |
| PB10 | I/O | 40 | 49 | 42 | UART TX (USART3) |
| PB11 | I/O | 39 | 50 | 41 | UART RX (USART3) |
| PB12 | I/O/A | 35 | 52 | 37 |  |
| PB13 | I/O/A | 36 | 53 | 38 |  |
| PB14 | I/O | 37 | 54 | 39 |  |
| PB15 | I/O | 38 | 55 | 40 |  |
| PC0 | I/O/A | 8 | 15 | 8 | UART TX (USART6) |
| PC1 | I/O/A | 9 | 16 | 9 | UART RX (USART6) |
| PC2 | I/O/A | 10 | 17 | 10 | UART TX (USART7) |
| PC3 | I/O/A | 11 | 18 | 11 | UART RX (USART7) |
| PC4 | I/O/A | 23 | 33 | 23 | UART TX (USART8) |
| PC5 | I/O/A | 24 | 34 | 24 | UART RX (USART8) |
| PC6 | I/O | - | 63 | - |  |
| PC7 | I/O | - | 64 | - |  |
| PC8 | I/O | - | 65 | - |  |
| PC9 | I/O | - | 66 | - |  |
| PC10 | I/O | 52 | 78 | 54 | UART TX (USART4) |
| PC11 | I/O | 53 | 79 | 55 | UART RX (USART4) |
| PC12 | I/O | 54 | 80 | 56 | UART TX (USART5) |
| PD0 | I/O/A | - | 81 | - |  |
| PD1 | I/O/A | - | 82 | - |  |
| PD2 | I/O | 55 | 83 | 57 | UART RX (USART5) |
| PD3 | I/O | - | 84 | - |  |
| PD4 | I/O | - | 85 | - |  |
| PD5 | I/O | - | 86 | - |  |
| PD6 | I/O | - | 87 | - |  |
| PD7 | I/O | - | 88 | - |  |
| PD8 | I/O | 34 | 51 | 36 |  |
| PD9 | I/O | - | 56 | - |  |
| PD10 | I/O | - | 57 | - |  |
| PD11 | I/O | - | 58 | - |  |
| PD12 | I/O | - | 59 | - |  |
| PD13 | I/O | - | 60 | - |  |
| PD14 | I/O | 41 | 61 | - |  |
| PD15 | I/O | 42 | 62 | - |  |
| PE0 | I/O | - | 97 | 66 |  |
| PE1 | I/O | - | 98 | 67 |  |
| PE2 | I/O | - | 1 | - |  |
| PE3 | I/O | - | 2 | - |  |
| PE4 | I/O | - | 3 | - |  |
| PE5 | I/O | - | 4 | - |  |
| PE6 | I/O | - | 5 | - |  |
| PE7 | I/O | - | 48 | - |  |
| PE8 | I/O | - | 38 | 28 |  |
| PE9 | I/O | - | 39 | 29 |  |
| PE10 | I/O | - | 73 | 49 |  |
| PE11 | I/O | - | 74 | 50 |  |
| PE12 | I/O | - | 94 | 63 |  |
| MDIRN | ETH | 28 | 42 | 31 |  |
| MDIRP | ETH | 29 | 43 | 32 |  |
| MDITN | ETH | 30 | 44 | 33 |  |
| MDITP | ETH | 31 | 45 | 34 |  |
| NRST | I | 7 | 14 | 7 |  |
| OSC_IN | I/A | 5 | 12 | 5 | OSC |
| OSC_OUT | O/A | 6 | 13 | 6 | OSC |
| PA0-WKUP | I/O/A | 14 | 23 | 14 |  |
| PC13-TAMPER-RTC | I/O | 2 | 7 | 2 |  |
| PC14-OSC32_IN | I/O/A | 3 | 8 | 3 | OSC |
| PC15-OSC32_OUT | I/O/A | 4 | 9 | 4 | OSC |
| VBAT | P | 1 | 6 | 1 |  |
| VDD | P | 18/32/49/64 | 11/28/46/75/100 | 18/35/51/68 |  |
| VDDA | P | 13 | 22 | 13 |  |
| VDDK | P | 27 | 40 | 30 |  |
| VREF+ | P | 13 | 21 | 13 |  |
| VREF- | P | 12 | 20 | 12 |  |
| VSS | P | 33/63 | 10/27/41/47/99 | EP |  |
| VSSA | P | 12 | 19 | 12 |  |

</details>

<details><summary><b>CH32V407 alternate functions</b></summary>

| Pad | default | (no route stated) | remap-1 | remap-2 | remap-3 |
|---|---|---|---|---|---|
| PA1 | ADC_IN1, LTDC_R4, TIM2_CH2, TIM5_CH2, USART2_RTS | - | LTDC_R4 | TIM2_CH2 | - |
| PA2 | ADC_IN2, LTDC_R5, TIM2_CH3, TIM5_CH3, USART2_TX | - | LTDC_R5, TIM2_CH3 | - | - |
| PA3 | ADC_IN3, LTDC_R6, TIM2_CH4, TIM5_CH4, USART2_RX | - | LTDC_R6, TIM2_CH4 | - | - |
| PA4 | ADC_IN4, DAC1_OUT, DVP_HSYNC, SPI1_NSS, USART2_CK | - | DVP_HSYNC, I2S3_WS, LTDC_G5, SPI3_NSS, USART9_TX | - | - |
| PA5 | ADC_IN5, DAC2_OUT, DVP_VSYNC, OPA_N2, SPI1_SCK | - | DVP_VSYNC, USART9_RX | USART1_CTS | USART1_CK, USART6_CK |
| PA6 | ADC_IN6, DVP_PCLK, OPA_P2, SPI1_MISO, TIM3_CH1, TIM8_BKIN | - | DVP_PCLK, TIM1_BKIN, USART7_TX | - | USART1_TX |
| PA7 | ADC_IN7, LTDC_R7, OPA_OUT1, SPI1_MOSI, TIM3_CH2, TIM8_CH1N, USART8_CK | - | LTDC_R7, TIM1_CH1N, USART7_RX | - | TIM1_CH4, USART1_RX |
| PA8 | I2S3_MCK, LTDC_B4, MCO, TIM1_CH1, USART1_CK | - | DVP_D2, LTDC_B4, TIM1_CH1, USART1_CK | USART1_RX, USART7_CK | USART7_CK |
| PA9 | DVP_D0, TIM1_CH2, USART1_TX | - | DVP_D0, LTDC_DE, SDIO_D6, TIM1_CH2 | USART1_RTS, USART7_TX | USART7_TX |
| PA10 | DVP_D1, TIM1_CH3, USART1_RX | - | DVP_D1, LTDC_CLK, SDIO_D7, TIM1_CH3 | USART1_CK, USART7_RX | USART7_RX |
| PA11 | CAN_RX, TIM1_CH4, USART1_CTS, USBHS1_DM | - | TIM1_CH4, USART1_CTS | - | - |
| PA12 | CAN_TX, TIM1_ETR, USART1_RTS, USBHS1_DP | - | TIM1_ETR, USART1_RTS | - | - |
| PA13 | LTDC_B5, SWDIO, SWIO, USART4_CTS | - | LTDC_B5, TIM8_CH1N | USART3_TX, USART6_CK | - |
| PA14 | LTDC_B6, SWCLK | - | LTDC_B6, TIM8_CH2N, USART8_TX | USART3_RX, USART6_CTS | - |
| PA15 | ARGB_OUT, I2S3_WS, LTDC_B7, SPI3_NSS | - | LTDC_B7, SPI1_NSS, TIM2_CH1, TIM2_ETR, TIM8_CH3N, USART8_RX | USART6_RTS | TIM2_CH1, TIM2_ETR |
| PB0 | ADC_IN8, LTDC_G2, TIM3_CH3, TIM8_CH2N, USART6_CK, USART8_CTS | - | LTDC_G2, TIM1_CH2N, USART4_TX, USART7_CK | TIM3_CH3, USART5_CTS | USART5_CTS |
| PB1 | ADC_IN9, LTDC_G3, OPA_OUT2, TIM3_CH4, TIM8_CH3N, USART8_RTS, USART9_TX | - | LTDC_G3, TIM1_CH3N, USART4_RX | TIM3_CH4, USART5_RTS | USART5_RTS |
| PB2 | BOOT1, LTDC_G4, USART9_RX | - | USART4_CK | USART5_CK | USART5_CK |
| PB3 | DVP_D5, I2S3_CK, SPI3_SCK, USART5_CTS | - | DVP_D5, LTDC_G4, SPI1_SCK, TIM2_CH2, USART5_CK | - | TIM2_CH2 |
| PB4 | LTDC_HSYNC, SPI3_MISO, USART5_RTS | - | DVP_D3, I3C_SCL, SPI1_MISO, USART5_TX | TIM3_CH1 | - |
| PB5 | I2C_SMBA, I2S3_SD, LTDC_VSYNC, SPI3_MOSI, USART5_CK | - | DVP_D10, I3C_SDA, SPI1_MOSI, USART5_RX, USART6_CK | TIM3_CH2 | - |
| PB6 | DVP_D5, I2C_SCL, TIM4_CH1, USBHS2_DM | - | TIM8_CH1, USART1_TX | USART7_CTS | - |
| PB7 | FSMC_NADV, I2C_SDA, TIM4_CH2, USBHS2_DP | - | FSMC_NADV, TIM8_CH2, USART1_RX | USART7_RTS | - |
| PB8 | DVP_D6, SDIO_D4, TIM4_CH3 | - | DVP_D6, I2C_SCL, LTDC_HSYNC, SDIO_D4, TIM8_CH3, USART10_TX, USART5_CTS, USART6_TX | CAN_RX, USART4_CTS | TIM1_CH3, USART4_CTS |
| PB9 | DVP_D7, SDIO_D5, TIM4_CH4 | - | DVP_D7, I2C_SDA, LTDC_VSYNC, SDIO_D5, TIM8_BKIN, USART10_RX, USART5_RTS, USART6_RX | CAN_TX, USART4_RTS | USART4_RTS |
| PB10 | I3C_SCL, LTDC_B3, USART3_TX | - | LTDC_B3 | TIM2_CH3 | TIM1_BKIN, TIM2_CH3 |
| PB11 | FSMC_D9, I3C_SDA, LTDC_B2, USART3_RX | - | FSMC_D9, LTDC_B2 | TIM2_CH4, USART8_CK | TIM2_CH4, USART8_CK |
| PB12 | FSMC_D10, I2S2_WS, LTDC_G6, OPA_P1, SPI2_NSS, TIM1_BKIN, USART3_CK | - | FSMC_D10, LTDC_G6 | USART8_RTS | USART8_RTS |
| PB13 | FSMC_D11, I2S2_CK, LTDC_G7, OPA_N1, SPI2_SCK, TIM1_CH1N, USART3_CTS | - | FSMC_D11, LTDC_G7, USART3_CTS | USART8_CTS | USART8_CTS |
| PB14 | FSMC_D12, LTDC_B0, SDIO_D0, SPI2_MISO, TIM1_CH2N, USART3_RTS | - | FSMC_D12, LTDC_B0, SDIO_D0, USART3_RTS | USART8_RX | USART8_RX |
| PB15 | I2S2_SD, LTDC_B1, SDIO_D1, SPI2_MOSI, TIM1_CH3N | - | LTDC_B1, SDIO_D1, USART8_CK | USART1_TX, USART8_TX | USART8_TX |
| PC0 | ADC_IN10, LTDC_R0, USART6_TX | - | LTDC_R0 | - | USART6_TX |
| PC1 | ADC_IN11, LTDC_R1, USART6_RX, USART7_CK | - | LTDC_R1 | - | USART6_RX |
| PC2 | ADC_IN12, LTDC_R2, USART6_CTS, USART7_TX | - | LTDC_R2 | - | USART6_CTS |
| PC3 | ADC_IN13, LTDC_R3, USART6_RTS, USART7_RX | - | LTDC_R3 | - | USART6_RTS |
| PC4 | ADC_IN14, LTDC_G0, USART7_CTS, USART8_TX | - | FSMC_D4, LTDC_G0, USART4_CTS, USART7_CTS | - | USART1_CTS |
| PC5 | ADC_IN15, LTDC_G1, USART7_RTS, USART8_RX | - | LTDC_G1, USART4_RTS, USART7_RTS | - | USART1_RTS |
| PC6 | I2S2_MCK, SDIO_D6, TIM8_CH1 | - | - | - | TIM3_CH1 |
| PC7 | I2S3_MCK, SDIO_D7, TIM8_CH2 | - | - | - | TIM3_CH2 |
| PC8 | DVP_D2, SDIO_D0, TIM8_CH3 | - | - | - | TIM3_CH3, USART7_CTS |
| PC9 | DVP_D3, SDIO_D1, TIM8_CH4 | - | - | - | TIM3_CH4, USART7_RTS |
| PC10 | DVP_D8, SDIO_D2, USART4_TX | - | DVP_D8, I2S3_CK, SDIO_D2, SPI3_SCK, USART3_TX | - | - |
| PC11 | DVP_D4, SDIO_D3, USART4_RX | - | DVP_D4, SDIO_D3, SPI3_MISO, USART3_RX | - | - |
| PC12 | DVP_D9, SDIO_CK, USART4_CK, USART5_TX | - | DVP_D9, I2S3_SD, SDIO_CK, SPI3_MOSI, USART3_CK | - | - |
| PD0 | FSMC_D2 | - | FSMC_D2 | - | CAN_RX |
| PD1 | FSMC_D3 | - | FSMC_D3 | - | CAN_TX |
| PD2 | DVP_D11, FSMC_NADV, SDIO_CMD, TIM3_ETR, USART4_RTS, USART5_RX | - | DVP_D11, SDIO_CMD, TIM3_ETR | TIM3_ETR | - |
| PD3 | FSMC_CLK | - | FSMC_CLK, USART2_CTS | - | - |
| PD4 | FSMC_NOE | - | FSMC_NOE, USART2_RTS | - | - |
| PD5 | FSMC_NWE | - | FSMC_NWE, USART2_TX | - | - |
| PD6 | DVP_D10, FSMC_NWAIT | - | FSMC_NWAIT, USART2_RX | - | - |
| PD7 | FSMC_NCE2, FSMC_NE1 | - | FSMC_NCE2, FSMC_NE1, USART2_CK | - | - |
| PD8 | FSMC_D13, LTDC_G5, USART9_CK | - | FSMC_D13, USART9_CK | - | USART3_TX |
| PD9 | FSMC_D14 | - | FSMC_D14 | - | USART3_RX |
| PD10 | FSMC_D15 | - | FSMC_D15 | USART10_CK, USART3_CK | USART10_CK, USART3_CK |
| PD11 | FSMC_A16 | - | FSMC_A16 | USART10_TX, USART3_CTS | USART10_TX, USART3_CTS |
| PD12 | FSMC_A17 | - | FSMC_A17, TIM4_CH1 | USART10_RX, USART3_RTS | USART10_RX, USART3_RTS |
| PD13 | FSMC_A18 | - | FSMC_A18, TIM4_CH2 | USART10_CTS | USART10_CTS |
| PD14 | FSMC_D0 | - | FSMC_D0, LED0, TIM4_CH3 | USART10_RTS | USART10_RTS |
| PD15 | FSMC_D1 | FSMC_D1 | LED1, TIM4_CH4 | - | - |
| PE0 | FSMC_NBL0, LTDC_DE, TIM4_ETR, USART10_TX | - | FSMC_NBL0, TIM4_ETR, USART6_CTS | USART4_TX | USART4_TX |
| PE1 | FSMC_NBL1, LTDC_CLK, USART10_RX | - | FSMC_NBL1, USART6_RTS | USART4_RX | USART4_RX |
| PE2 | FSMC_A23 | - | FSMC_A23 | USART9_CK | USART9_CK |
| PE3 | FSMC_A19 | - | FSMC_A19 | USART9_TX | USART9_TX |
| PE4 | FSMC_A20 | - | FSMC_A20 | USART9_RX | USART9_RX |
| PE5 | FSMC_A21 | - | FSMC_A21 | USART9_CTS | USART9_CTS |
| PE6 | FSMC_A22 | - | FSMC_A22 | USART9_RTS | USART9_RTS |
| PE7 | FSMC_D4 | - | - | - | TIM1_ETR |
| PE8 | FSMC_D5, LED0, USART9_CTS | - | FSMC_D5, USART9_CTS | USART5_TX | TIM1_CH1N, USART5_TX |
| PE9 | FSMC_D6, LED1, TIM1_CH1_3, USART9_RTS | - | FSMC_D6, USART9_RTS | USART5_RX | USART5_RX |
| PE10 | FSMC_D7 | - | FSMC_D7, USART8_CTS | USART6_TX | TIM1_CH2N |
| PE11 | FSMC_D8 | - | FSMC_D8, USART8_RTS | USART6_RX | TIM1_CH2 |
| PE12 | BOOT0, USART10_CK | - | USART10_CK | USART4_CK | USART4_CK |
| OSC_IN | - | PD0 | - | - | - |
| OSC_OUT | - | PD1 | - | - | - |
| PA0-WKUP | ADC_IN0, TIM2_CH1, TIM2_ETR, TIM5_CH1, TIM8_ETR, USART2_CTS, WKUP | - | TIM8_ETR | TIM2_CH1, TIM2_ETR | - |
| PC13-TAMPER-RTC | TAMPER-RTC | - | TIM8_CH4 | - | - |
| PC14-OSC32_IN | OSC32_IN, USART10_CTS | - | USART10_CTS | - | - |
| PC15-OSC32_OUT | OSC32_OUT, USART10_RTS | - | USART10_RTS | - | - |

</details>

### CH32V467 pin map

Pin functions (filterable): [ALL](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467) [ADC](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467&features=ADC) [I2C](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467&features=I2C) [SPI](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467&features=SPI) [SYS](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467&features=SYS) [TIM](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467&features=TIM) [UART](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467&features=UART) [USB](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467&features=USB)

<details><summary><b>CH32V467 pin map</b> (92 pads x 3 products)</summary>

| Pin name | Type | [CH32V467&#8203;RET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467RET6)&#8203;(LQFP64) | [CH32V467&#8203;VET6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467VET6)&#8203;(LQFP100) | [CH32V467&#8203;WEU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V467WEU6)&#8203;(QFN68) | Notes |
|---|---|---|---|---|---|
| PA1 | I/O/A | 15 | 24 | 15 |  |
| PA2 | I/O/A | 16 | 25 | 16 | UART TX (USART2) |
| PA3 | I/O/A | 17 | 26 | 17 | UART RX (USART2) |
| PA4 | I/O/A | 19 | 29 | 19 |  |
| PA5 | I/O/A | 20 | 30 | 20 |  |
| PA6 | I/O/A | 21 | 31 | 21 |  |
| PA7 | I/O/A | 22 | 32 | 22 |  |
| PA8 | I/O | 43 | 67 | 43 |  |
| PA9 | I/O | 44 | 68 | 44 | UART TX (USART1) |
| PA10 | I/O | 45 | 69 | 45 | UART RX (USART1) |
| PA11 | I/O/A | 46 | 70 | 46 |  |
| PA12 | I/O/A | 47 | 71 | 47 |  |
| PA13 | I/O | 48 | 72 | 48 | SWDIO |
| PA14 | I/O | 50 | 76 | 52 | SWCLK |
| PA15 | I/O | 51 | 77 | 53 |  |
| PB0 | I/O/A | 25 | 35 | 25 |  |
| PB1 | I/O/A | 26 | 36 | 26 | UART TX (USART9) |
| PB2 | I/O | - | 37 | 27 |  |
| PB3 | I/O | 56 | 89 | 58 |  |
| PB4 | I/O | 57 | 90 | 59 |  |
| PB5 | I/O | 58 | 91 | 60 |  |
| PB6 | I/O | 59 | 92 | 61 |  |
| PB7 | I/O | 60 | 93 | 62 |  |
| PB8 | I/O | 61 | 95 | 64 |  |
| PB9 | I/O | 62 | 96 | 65 |  |
| PB10 | I/O | 40 | 49 | 42 | UART TX (USART3) |
| PB11 | I/O | 39 | 50 | 41 | UART RX (USART3) |
| PB12 | I/O/A | 35 | 52 | 37 |  |
| PB13 | I/O/A | 36 | 53 | 38 |  |
| PB14 | I/O | 37 | 54 | 39 |  |
| PB15 | I/O | 38 | 55 | 40 |  |
| PC0 | I/O/A | 8 | 15 | 8 | UART TX (USART6) |
| PC1 | I/O/A | 9 | 16 | 9 | UART RX (USART6) |
| PC2 | I/O/A | 10 | 17 | 10 | UART TX (USART7) |
| PC3 | I/O/A | 11 | 18 | 11 | UART RX (USART7) |
| PC4 | I/O/A | 23 | 33 | 23 | UART TX (USART8) |
| PC5 | I/O/A | 24 | 34 | 24 | UART RX (USART8) |
| PC6 | I/O | - | 63 | - |  |
| PC7 | I/O | - | 64 | - |  |
| PC8 | I/O | - | 65 | - |  |
| PC9 | I/O | - | 66 | - |  |
| PC10 | I/O | 52 | 78 | 54 | UART TX (USART4) |
| PC11 | I/O | 53 | 79 | 55 | UART RX (USART4) |
| PC12 | I/O | 54 | 80 | 56 | UART TX (USART5) |
| PD0 | I/O/A | - | 81 | - |  |
| PD1 | I/O/A | - | 82 | - |  |
| PD2 | I/O | 55 | 83 | 57 | UART RX (USART5) |
| PD3 | I/O | - | 84 | - |  |
| PD4 | I/O | - | 85 | - |  |
| PD5 | I/O | - | 86 | - |  |
| PD6 | I/O | - | 87 | - |  |
| PD7 | I/O | - | 88 | - |  |
| PD8 | I/O | - | 51 | - |  |
| PD9 | I/O | - | 56 | - |  |
| PD10 | I/O | - | 57 | - |  |
| PD11 | I/O | - | 58 | - |  |
| PD12 | I/O | - | 59 | - |  |
| PD13 | I/O | - | 60 | - |  |
| PD14 | I/O | 41 | 61 | - |  |
| PD15 | I/O | 42 | 62 | - |  |
| PE0 | I/O | - | 97 | 66 |  |
| PE1 | I/O | - | 98 | 67 |  |
| PE2 | I/O | - | 1 | - |  |
| PE3 | I/O | - | 2 | - |  |
| PE4 | I/O | - | 3 | - |  |
| PE5 | I/O | - | 4 | - |  |
| PE6 | I/O | - | 5 | - |  |
| PE8 | I/O | - | 38 | 28 |  |
| PE9 | I/O | - | 39 | 29 |  |
| PE10 | I/O | - | 73 | 49 |  |
| PE11 | I/O | - | 74 | 50 |  |
| PE12 | I/O | - | 94 | 63 |  |
| MDIRN | ETH | 28 | 42 | 31 |  |
| MDIRP | ETH | 29 | 43 | 32 |  |
| MDITN | ETH | 30 | 44 | 33 |  |
| MDITP | ETH | 31 | 45 | 34 |  |
| NRST | I | 7 | 14 | 7 |  |
| OSC_IN | I/A | 5 | 12 | 5 | OSC |
| OSC_OUT | O/A | 6 | 13 | 6 | OSC |
| PA0-WKUP | I/O/A | 14 | 23 | 14 |  |
| PC13-TAMPER-RTC | I/O | 2 | 7 | 2 |  |
| PC14-OSC32_IN | I/O/A | 3 | 8 | 3 | OSC |
| PC15-OSC32_OUT | I/O/A | 4 | 9 | 4 | OSC |
| VBAT | P | 1 | 6 | 1 |  |
| VDD | P | 18/32/49/64 | 11/28/46/75/100 | 18/35/51/68 |  |
| VDD18 | P | 34 | 48 | 36 |  |
| VDDA | P | 13 | 22 | 13 |  |
| VDDK | P | 27 | 40 | 30 |  |
| VREF+ | P | 13 | 21 | 13 |  |
| VREF- | P | 12 | 20 | 12 |  |
| VSS | P | 33/63 | 10/27/41/47/99 | EP |  |
| VSSA | P | 12 | 19 | 12 |  |

</details>

<details><summary><b>CH32V467 alternate functions</b></summary>

| Pad | default | (no route stated) | remap-1 | remap-2 | remap-3 |
|---|---|---|---|---|---|
| PA1 | ADC_IN1, LTDC_R4, TIM2_CH2, TIM5_CH2, USART2_RTS | - | LTDC_R4 | TIM2_CH2 | - |
| PA2 | ADC_IN2, LTDC_R5, TIM2_CH3, TIM5_CH3, USART2_TX | - | LTDC_R5, TIM2_CH3 | - | - |
| PA3 | ADC_IN3, LTDC_R6, TIM2_CH4, TIM5_CH4, USART2_RX | - | LTDC_R6, TIM2_CH4 | - | - |
| PA4 | ADC_IN4, DAC1_OUT, DVP_HSYNC, SPI1_NSS, USART2_CK | - | DVP_HSYNC, I2S3_WS, LTDC_G5, SPI3_NSS, USART9_TX | - | - |
| PA5 | ADC_IN5, DAC2_OUT, DVP_VSYNC, OPA_N2, SPI1_SCK | - | DVP_VSYNC, USART9_RX | USART1_CTS | USART1_CK, USART6_CK |
| PA6 | ADC_IN6, DVP_PCLK, OPA_P2, SPI1_MISO, TIM3_CH1, TIM8_BKIN | - | DVP_PCLK, TIM1_BKIN, USART7_TX | - | USART1_TX |
| PA7 | ADC_IN7, LTDC_R7, OPA_OUT1, SPI1_MOSI, TIM3_CH2, TIM8_CH1N, USART8_CK | - | LTDC_R7, TIM1_CH1N, USART7_RX | - | TIM1_CH4, USART1_RX |
| PA8 | I2S3_MCK, LTDC_B4, MCO, TIM1_CH1, USART1_CK | - | DVP_D2, LTDC_B4, TIM1_CH1, USART1_CK | USART1_RX, USART7_CK | USART7_CK |
| PA9 | DVP_D0, TIM1_CH2, USART1_TX | - | DVP_D0, LTDC_DE, SDIO_D6, TIM1_CH2 | USART1_RTS, USART7_TX | USART7_TX |
| PA10 | DVP_D1, TIM1_CH3, USART1_RX | - | DVP_D1, LTDC_CLK, SDIO_D7, TIM1_CH3 | USART1_CK, USART7_RX | USART7_RX |
| PA11 | CAN_RX, TIM1_CH4, USART1_CTS, USBHS1_DM | - | TIM1_CH4, USART1_CTS | - | - |
| PA12 | CAN_TX, TIM1_ETR, USART1_RTS, USBHS1_DP | - | TIM1_ETR, USART1_RTS | - | - |
| PA13 | LTDC_B5, SWDIO, SWIO, USART4_CTS | - | LTDC_B5, TIM8_CH1N | USART3_TX, USART6_CK | - |
| PA14 | LTDC_B6, SWCLK | - | LTDC_B6, TIM8_CH2N, USART8_TX | USART3_RX, USART6_CTS | - |
| PA15 | ARGB_OUT, I2S3_WS, LTDC_B7, SPI3_NSS | - | LTDC_B7, SPI1_NSS, TIM2_CH1, TIM2_ETR, TIM8_CH3N, USART8_RX | USART6_RTS | TIM2_CH1, TIM2_ETR |
| PB0 | ADC_IN8, LTDC_G2, TIM3_CH3, TIM8_CH2N, USART6_CK, USART8_CTS | - | LTDC_G2, TIM1_CH2N, USART4_TX, USART7_CK | TIM3_CH3, USART5_CTS | USART5_CTS |
| PB1 | ADC_IN9, LTDC_G3, OPA_OUT2, TIM3_CH4, TIM8_CH3N, USART8_RTS, USART9_TX | - | LTDC_G3, TIM1_CH3N, USART4_RX | TIM3_CH4, USART5_RTS | USART5_RTS |
| PB2 | BOOT1, LTDC_G4, USART9_RX | - | USART4_CK | USART5_CK | USART5_CK |
| PB3 | DVP_D5, I2S3_CK, SPI3_SCK, USART5_CTS | - | DVP_D5, LTDC_G4, SPI1_SCK, TIM2_CH2, USART5_CK | - | TIM2_CH2 |
| PB4 | LTDC_HSYNC, SPI3_MISO, USART5_RTS | - | DVP_D3, I3C_SCL, SPI1_MISO, USART5_TX | TIM3_CH1 | - |
| PB5 | I2C_SMBA, I2S3_SD, LTDC_VSYNC, SPI3_MOSI, USART5_CK | - | DVP_D10, I3C_SDA, SPI1_MOSI, USART5_RX, USART6_CK | TIM3_CH2 | - |
| PB6 | DVP_D5, I2C_SCL, TIM4_CH1, USBHS2_DM | - | TIM8_CH1, USART1_TX | USART7_CTS | - |
| PB7 | FSMC_NADV, I2C_SDA, TIM4_CH2, USBHS2_DP | - | FSMC_NADV, TIM8_CH2, USART1_RX | USART7_RTS | - |
| PB8 | DVP_D6, SDIO_D4, TIM4_CH3 | - | DVP_D6, I2C_SCL, LTDC_HSYNC, SDIO_D4, TIM8_CH3, USART10_TX, USART5_CTS, USART6_TX | CAN_RX, USART4_CTS | TIM1_CH3, USART4_CTS |
| PB9 | DVP_D7, SDIO_D5, TIM4_CH4 | - | DVP_D7, I2C_SDA, LTDC_VSYNC, SDIO_D5, TIM8_BKIN, USART10_RX, USART5_RTS, USART6_RX | CAN_TX, USART4_RTS | USART4_RTS |
| PB10 | I3C_SCL, LTDC_B3, USART3_TX | - | LTDC_B3 | TIM2_CH3 | TIM1_BKIN, TIM2_CH3 |
| PB11 | FSMC_D9, I3C_SDA, LTDC_B2, USART3_RX | - | FSMC_D9, LTDC_B2 | TIM2_CH4, USART8_CK | TIM2_CH4, USART8_CK |
| PB12 | FSMC_D10, I2S2_WS, LTDC_G6, OPA_P1, SPI2_NSS, TIM1_BKIN, USART3_CK | - | FSMC_D10, LTDC_G6 | USART8_RTS | USART8_RTS |
| PB13 | FSMC_D11, I2S2_CK, LTDC_G7, OPA_N1, SPI2_SCK, TIM1_CH1N, USART3_CTS | - | FSMC_D11, LTDC_G7, USART3_CTS | USART8_CTS | USART8_CTS |
| PB14 | FSMC_D12, LTDC_B0, SDIO_D0, SPI2_MISO, TIM1_CH2N, USART3_RTS | - | FSMC_D12, LTDC_B0, SDIO_D0, USART3_RTS | USART8_RX | USART8_RX |
| PB15 | I2S2_SD, LTDC_B1, SDIO_D1, SPI2_MOSI, TIM1_CH3N | - | LTDC_B1, SDIO_D1, USART8_CK | USART1_TX, USART8_TX | USART8_TX |
| PC0 | ADC_IN10, LTDC_R0, USART6_TX | - | LTDC_R0 | - | USART6_TX |
| PC1 | ADC_IN11, LTDC_R1, USART6_RX, USART7_CK | - | LTDC_R1 | - | USART6_RX |
| PC2 | ADC_IN12, LTDC_R2, USART6_CTS, USART7_TX | - | LTDC_R2 | - | USART6_CTS |
| PC3 | ADC_IN13, LTDC_R3, USART6_RTS, USART7_RX | - | LTDC_R3 | - | USART6_RTS |
| PC4 | ADC_IN14, LTDC_G0, USART7_CTS, USART8_TX | - | FSMC_D4, LTDC_G0, USART4_CTS, USART7_CTS | - | USART1_CTS |
| PC5 | ADC_IN15, LTDC_G1, USART7_RTS, USART8_RX | - | LTDC_G1, USART4_RTS, USART7_RTS | - | USART1_RTS |
| PC6 | I2S2_MCK, SDIO_D6, TIM8_CH1 | - | - | - | TIM3_CH1 |
| PC7 | I2S3_MCK, SDIO_D7, TIM8_CH2 | - | - | - | TIM3_CH2 |
| PC8 | DVP_D2, SDIO_D0, TIM8_CH3 | - | - | - | TIM3_CH3, USART7_CTS |
| PC9 | DVP_D3, SDIO_D1, TIM8_CH4 | - | - | - | TIM3_CH4, USART7_RTS |
| PC10 | DVP_D8, SDIO_D2, USART4_TX | - | DVP_D8, I2S3_CK, SDIO_D2, SPI3_SCK, USART3_TX | - | - |
| PC11 | DVP_D4, SDIO_D3, USART4_RX | - | DVP_D4, SDIO_D3, SPI3_MISO, USART3_RX | - | - |
| PC12 | DVP_D9, SDIO_CK, USART4_CK, USART5_TX | - | DVP_D9, I2S3_SD, SDIO_CK, SPI3_MOSI, USART3_CK | - | - |
| PD0 | FSMC_D2 | - | FSMC_D2 | - | CAN_RX |
| PD1 | FSMC_D3 | - | FSMC_D3 | - | CAN_TX |
| PD2 | DVP_D11, FSMC_NADV, SDIO_CMD, TIM3_ETR, USART4_RTS, USART5_RX | - | DVP_D11, SDIO_CMD, TIM3_ETR | TIM3_ETR | - |
| PD3 | FSMC_CLK | - | FSMC_CLK, USART2_CTS | - | - |
| PD4 | FSMC_NOE | - | FSMC_NOE, USART2_RTS | - | - |
| PD5 | FSMC_NWE | - | FSMC_NWE, USART2_TX | - | - |
| PD6 | DVP_D10, FSMC_NWAIT | - | FSMC_NWAIT, USART2_RX | - | - |
| PD7 | FSMC_NCE2, FSMC_NE1 | - | FSMC_NCE2, FSMC_NE1, USART2_CK | - | - |
| PD8 | FSMC_D13, LTDC_G5, USART9_CK | - | FSMC_D13, USART9_CK | - | USART3_TX |
| PD9 | FSMC_D14 | - | FSMC_D14 | - | USART3_RX |
| PD10 | FSMC_D15 | - | FSMC_D15 | USART10_CK, USART3_CK | USART10_CK, USART3_CK |
| PD11 | FSMC_A16 | - | FSMC_A16 | USART10_TX, USART3_CTS | USART10_TX, USART3_CTS |
| PD12 | FSMC_A17 | - | FSMC_A17, TIM4_CH1 | USART10_RX, USART3_RTS | USART10_RX, USART3_RTS |
| PD13 | FSMC_A18 | - | FSMC_A18, TIM4_CH2 | USART10_CTS | USART10_CTS |
| PD14 | FSMC_D0 | - | FSMC_D0, LED0, TIM4_CH3 | USART10_RTS | USART10_RTS |
| PD15 | FSMC_D1 | FSMC_D1 | LED1, TIM4_CH4 | - | - |
| PE0 | FSMC_NBL0, LTDC_DE, TIM4_ETR, USART10_TX | - | FSMC_NBL0, TIM4_ETR, USART6_CTS | USART4_TX | USART4_TX |
| PE1 | FSMC_NBL1, LTDC_CLK, USART10_RX | - | FSMC_NBL1, USART6_RTS | USART4_RX | USART4_RX |
| PE2 | FSMC_A23 | - | FSMC_A23 | USART9_CK | USART9_CK |
| PE3 | FSMC_A19 | - | FSMC_A19 | USART9_TX | USART9_TX |
| PE4 | FSMC_A20 | - | FSMC_A20 | USART9_RX | USART9_RX |
| PE5 | FSMC_A21 | - | FSMC_A21 | USART9_CTS | USART9_CTS |
| PE6 | FSMC_A22 | - | FSMC_A22 | USART9_RTS | USART9_RTS |
| PE8 | FSMC_D5, LED0, USART9_CTS | - | FSMC_D5, USART9_CTS | USART5_TX | TIM1_CH1N, USART5_TX |
| PE9 | FSMC_D6, LED1, TIM1_CH1_3, USART9_RTS | - | FSMC_D6, USART9_RTS | USART5_RX | USART5_RX |
| PE10 | FSMC_D7 | - | FSMC_D7, USART8_CTS | USART6_TX | TIM1_CH2N |
| PE11 | FSMC_D8 | - | FSMC_D8, USART8_RTS | USART6_RX | TIM1_CH2 |
| PE12 | BOOT0, USART10_CK | - | USART10_CK | USART4_CK | USART4_CK |
| OSC_IN | - | PD0 | - | - | - |
| OSC_OUT | - | PD1 | - | - | - |
| PA0-WKUP | ADC_IN0, TIM2_CH1, TIM2_ETR, TIM5_CH1, TIM8_ETR, USART2_CTS, WKUP | - | TIM8_ETR | TIM2_CH1, TIM2_ETR | - |
| PC13-TAMPER-RTC | TAMPER-RTC | - | TIM8_CH4 | - | - |
| PC14-OSC32_IN | OSC32_IN, USART10_CTS | - | USART10_CTS | - | - |
| PC15-OSC32_OUT | OSC32_OUT, USART10_RTS | - | USART10_RTS | - | - |

</details>

<details><summary><b>Remap selectors (AFIO)</b></summary>

| Series | Field | Register | Bits | Values | Reset |
|---|---|---|---|---|---|
| CH32V407 | CAN_REMAP | PCFR1 | PCFR1:13;PCFR1:14 | 0;1;2;3 | 0 |
| CH32V407 | DVP_REMAP | PCFR2 | PCFR2:13 | 0;1 | 0 |
| CH32V407 | ETHPHY_LED_REMAP | PCFR1 | PCFR1:31 | 0;1 | 0 |
| CH32V407 | FSMC_REMAP | PCFR2 | PCFR2:0 | 0;1 | 0 |
| CH32V407 | I2C1_REMAP | PCFR1 | PCFR1:1 | 0;1 | 0 |
| CH32V407 | I3C_REMAP | PCFR2 | PCFR2:14 | 0;1 | 0 |
| CH32V407 | LTDC_REMAP | PCFR2 | PCFR2:11 | 0;1 | 0 |
| CH32V407 | SDIO_REMAP | PCFR2 | PCFR2:12 | 0;1 | 0 |
| CH32V407 | SPI1_REMAP | PCFR1 | PCFR1:0 | 0;1 | 0 |
| CH32V407 | SPI3_REMAP | PCFR1 | PCFR1:28 | 0;1 | 0 |
| CH32V407 | TIM1_REMAP | PCFR1 | PCFR1:6;PCFR1:7 | 0;1;2;3 | 0 |
| CH32V407 | TIM2_REMAP | PCFR1 | PCFR1:8;PCFR1:9 | 0;1;2;3 | 0 |
| CH32V407 | TIM3_REMAP | PCFR1 | PCFR1:10;PCFR1:11 | 0;1;2;3 | 0 |
| CH32V407 | TIM4_REMAP | PCFR1 | PCFR1:12 | 0;1 | 0 |
| CH32V407 | TIM8_REMAP | PCFR2 | PCFR2:2 | 0;1 | 0 |
| CH32V407 | USART1_REMAP | PCFR1\|PCFR2 | PCFR1:2;PCFR2:26 | 0;1;2;3 | 0 |
| CH32V407 | USART10_REMAP | PCFR2 | PCFR2:30;PCFR2:31 | 0;1;2;3 | 0 |
| CH32V407 | USART2_REMAP | PCFR1 | PCFR1:3 | 0;1 | 0 |
| CH32V407 | USART3_REMAP | PCFR1 | PCFR1:4;PCFR1:5 | 0;1;2;3 | 0 |
| CH32V407 | USART4_REMAP | PCFR2 | PCFR2:16;PCFR2:17 | 0;1;2;3 | 0 |
| CH32V407 | USART5_REMAP | PCFR2 | PCFR2:18;PCFR2:19 | 0;1;2;3 | 0 |
| CH32V407 | USART6_REMAP | PCFR2 | PCFR2:20;PCFR2:21 | 0;1;2;3 | 0 |
| CH32V407 | USART7_REMAP | PCFR2 | PCFR2:22;PCFR2:23 | 0;1;2;3 | 0 |
| CH32V407 | USART8_REMAP | PCFR2 | PCFR2:24;PCFR2:25 | 0;1;2;3 | 0 |
| CH32V407 | USART9_REMAP | PCFR2 | PCFR2:28;PCFR2:29 | 0;1;2;3 | 0 |
| CH32V467 | CAN_REMAP | PCFR1 | PCFR1:13;PCFR1:14 | 0;1;2;3 | 0 |
| CH32V467 | DVP_REMAP | PCFR2 | PCFR2:13 | 0;1 | 0 |
| CH32V467 | ETHPHY_LED_REMAP | PCFR1 | PCFR1:31 | 0;1 | 0 |
| CH32V467 | FSMC_REMAP | PCFR2 | PCFR2:0 | 0;1 | 0 |
| CH32V467 | I2C1_REMAP | PCFR1 | PCFR1:1 | 0;1 | 0 |
| CH32V467 | I3C_REMAP | PCFR2 | PCFR2:14 | 0;1 | 0 |
| CH32V467 | LTDC_REMAP | PCFR2 | PCFR2:11 | 0;1 | 0 |
| CH32V467 | SDIO_REMAP | PCFR2 | PCFR2:12 | 0;1 | 0 |
| CH32V467 | SPI1_REMAP | PCFR1 | PCFR1:0 | 0;1 | 0 |
| CH32V467 | SPI3_REMAP | PCFR1 | PCFR1:28 | 0;1 | 0 |
| CH32V467 | TIM1_REMAP | PCFR1 | PCFR1:6;PCFR1:7 | 0;1;2;3 | 0 |
| CH32V467 | TIM2_REMAP | PCFR1 | PCFR1:8;PCFR1:9 | 0;1;2;3 | 0 |
| CH32V467 | TIM3_REMAP | PCFR1 | PCFR1:10;PCFR1:11 | 0;1;2;3 | 0 |
| CH32V467 | TIM4_REMAP | PCFR1 | PCFR1:12 | 0;1 | 0 |
| CH32V467 | TIM8_REMAP | PCFR2 | PCFR2:2 | 0;1 | 0 |
| CH32V467 | USART1_REMAP | PCFR1\|PCFR2 | PCFR1:2;PCFR2:26 | 0;1;2;3 | 0 |
| CH32V467 | USART10_REMAP | PCFR2 | PCFR2:30;PCFR2:31 | 0;1;2;3 | 0 |
| CH32V467 | USART2_REMAP | PCFR1 | PCFR1:3 | 0;1 | 0 |
| CH32V467 | USART3_REMAP | PCFR1 | PCFR1:4;PCFR1:5 | 0;1;2;3 | 0 |
| CH32V467 | USART4_REMAP | PCFR2 | PCFR2:16;PCFR2:17 | 0;1;2;3 | 0 |
| CH32V467 | USART5_REMAP | PCFR2 | PCFR2:18;PCFR2:19 | 0;1;2;3 | 0 |
| CH32V467 | USART6_REMAP | PCFR2 | PCFR2:20;PCFR2:21 | 0;1;2;3 | 0 |
| CH32V467 | USART7_REMAP | PCFR2 | PCFR2:22;PCFR2:23 | 0;1;2;3 | 0 |
| CH32V467 | USART8_REMAP | PCFR2 | PCFR2:24;PCFR2:25 | 0;1;2;3 | 0 |
| CH32V467 | USART9_REMAP | PCFR2 | PCFR2:28;PCFR2:29 | 0;1;2;3 | 0 |

</details>

## Block diagrams

### CH32V407
<img src="image/architecture_CH32V407.png" alt="CH32V407 block diagram" />

### CH32V467
<img src="image/architecture_CH32V467.png" alt="CH32V467 block diagram" />

## Errata

- The non-zero-wait flash area additionally supports RVV instructions and 64-bit DMA access. *(applies: CH32V407, CH32V467; 5th-to-last digit of lot number > 0)*
- Current consumption is higher than the CH32V407 values in the datasheet tables: about +2~22mA in operating mode and +90uA in stop mode. *(applies: CH32V467; all lots)*
- PSRAM supports clocks above 200MHz, variable and instruction access, and byte write; in stop mode (voltage regulator in low-power mode) PSRAM data is retained. *(applies: CH32V467; 5th-to-last digit of lot number != 0)*
- In stop mode with the voltage regulator in low-power mode, bit LDO18_EN in register PWR_CTLR must be configured to 0. *(applies: CH32V467; 5th-to-last digit of lot number = 0)*

## EVT examples

161 routines in [EVT/EXAM](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM):

[ADC](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/ADC) 14 · [APPLICATION](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/APPLICATION) 4 · [ARGB](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/ARGB) 2 · [BKP](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/BKP) 1 · [CAN](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/CAN) 3 · [CPU](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/CPU) 9 · [CRC](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/CRC) 1 · [DAC](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/DAC) 8 · [DMA](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/DMA) 1 · [DVP](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/DVP) 2 · [ETH](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/ETH) 18 · [EXTI](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/EXTI) 1 · [FLASH](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/FLASH) 1 · [FSMC](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/FSMC) 4 · [GPIO](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/GPIO) 1 · [I2C](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/I2C) 6 · [I2S](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/I2S) 2 · [I3C](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/I3C) 1 · [IAP](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/IAP) 1 · [INT](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/INT) 1 · [IWDG](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/IWDG) 1 · [LTDC](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/LTDC) 1 · [OPA](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/OPA) 1 · [PSRAM](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/PSRAM) 1 · [PWR](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/PWR) 8 · [RCC](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/RCC) 4 · [RNG](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/RNG) 1 · [RTC](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/RTC) 2 · [SDIO](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/SDIO) 2 · [SDI_Printf](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/SDI_Printf) 1 · [SPI](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/SPI) 7 · [SYSTICK](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/SYSTICK) 1 · [TIM](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/TIM) 16 · [USART](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/USART) 9 · [USB](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/USB) 24 · [WWDG](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT/EXAM/WWDG) 1

## Documents

| Document | Kind | English | 中文 |
|---|---|---|---|
| CH32V407DS0.PDF | datasheet | [page](https://www.wch-ic.com/downloads/CH32V407DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407DS0.PDF) v1.2 | [page](https://www.wch.cn/downloads/CH32V407DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407DS0.PDF) v1.2 |
| CH32V407RM.PDF | reference-manual | [page](https://www.wch-ic.com/downloads/CH32V407RM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V407/datasheet_en/CH32V407RM.PDF) v1.2 | [page](https://www.wch.cn/downloads/CH32V407RM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V407/datasheet_zh/CH32V407RM.PDF) v1.2 |
| CH32V407EVT.ZIP | evt | - | [page](https://www.wch.cn/downloads/CH32V407EVT_ZIP.html) [mirror](https://github.com/ch32-riscv-ug/CH32V407/tree/main/EVT) v1.4 |

### Evaluation boards

- board-manual:en: [CH32V4x7 Evaluation Board Reference-EN.pdf](https://github.com/ch32-riscv-ug/CH32V407/blob/main/EVT/PUB/CH32V4x7%20Evaluation%20Board%20Reference-EN.pdf)
- board-manual:zh: [CH32V4x7评估板说明书.pdf](https://github.com/ch32-riscv-ug/CH32V407/blob/main/EVT/PUB/CH32V4x7%E8%AF%84%E4%BC%B0%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6.pdf)
- schematic-pdf: [CH32V4x7SCH.pdf](https://github.com/ch32-riscv-ug/CH32V407/blob/main/EVT/PUB/CH32V4x7SCH.pdf)

4 board schematics under `EVT/PUB/SCHPCB/`: `CH32V4x7RET-R0`, `CH32V4x7VET-R0`, `CH32V4x7VET-USB`, `CH32V4x7WEU-R0`

## Reference

### Address map

| Region | Base | Kind |
|---|---|---|
| HBPERIPH | `0x40000000` | bus |
| PERIPH | `0x40000000` | bus |
| FLASH | `0x00000000` | link-origin |
| RAM | `0x20000400` | link-origin |
| FLASH | `0x08000000` | memory |
| OB | `0x1ffff800` | memory |
| SRAM | `0x20000000` | memory |

`link-origin` is what the EVT linker scripts use; the `memory` row for FLASH is the address the device header states. Both windows are real -- CH32V307 answers at `0x08000000` and at `0x00000000`.

Peripheral base addresses are in [memory_map.csv](https://github.com/ch32-riscv-ug/ch32-device-data/blob/main/evidence/memory_map.csv); interrupt numbers in [interrupts.csv](https://github.com/ch32-riscv-ug/ch32-device-data/blob/main/evidence/interrupts.csv).

---
Data: [ch32-device-data](https://github.com/ch32-riscv-ug/ch32-device-data) (evidence/ and index/ -- each value carries its evidence and confidence there).
