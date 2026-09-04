# CH32M030

<!-- This file is generated from ch32-riscv-ug/ch32-device-data (index/ + evidence/ + tools/build_readme.py). Edit there, not here. -->

*Generated from the mirror at commit [`8c02eb4`](https://github.com/ch32-riscv-ug/CH32M030/tree/8c02eb46c1f212527f85d0a04f0e54fe3b324e77) (2026-09-01). Newer PDFs may exist upstream; see Documents below.*

[Choose a part](#product-comparison) &middot; [Pin viewer](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030) &middot; [Pin maps](#pin-maps--alternate-functions) &middot; [Examples](#evt-examples) &middot; [Documents](#documents) &middot; [Address map](#address-map)

## Quick start

### Debug / serial defaults

Where these land **without writing a remap register**. SWD is live at reset; the UART pads are not -- the pin must still be put into alternate-function mode. See `route` in evidence/README.ja.md.

| Series | SWDIO | SWCLK | UART TX | UART RX |
|---|---|---|---|---|
| CH32M030 | PA3 | PA2 | PC1 (USART1) | PC0 (USART1) |

## Series

| Series | Core | ISA | Flash | SRAM | Main clock | VDD | Packages | Products | Official |
|---|---|---|---|---|---|---|---|---|---|
| **CH32M030** | QingKe V3B | RV32IMCB | 64K | 12K | 72 MHz | - | LQFP48,QFN32,QFN48,QFN48X7_A,QSOP28 | 5 | [en](https://www.wch-ic.com/products/CH32M030.html) / [zh](https://www.wch.cn/products/CH32M030.html) |

## Product comparison

### CH32M030 product comparison

Only the 14 rows that differ between these 5 products; the other 15 are the same for all of them.

| | [CH32M030&#8203;C8T7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8T7)&#8203;(LQFP48) | [CH32M030&#8203;C8U3](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8U3)&#8203;(QFN48X7_A) | [CH32M030&#8203;C8U7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8U7)&#8203;(QFN48) | [CH32M030&#8203;G8R7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030G8R7)&#8203;(QSOP28) | [CH32M030&#8203;K8U7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030K8U7)&#8203;(QFN32) |
|---|---|---|---|---|---|
| **GPIO** | 35 | 36 | 36 | 17 | 24 |
| **Temperature** | -40..105C | - | -40..105C | -40..105C | -40..105C |
| Half-bridge gate driver | 4 | 4 | 4 | 3 | 2 |
| Pre-drive I/O (MV I/0) | 8 | 8 | 8 | 6 | 6 |
| High voltage I/O（HV I/0） | - | 2 | 1 | - | 1 |
| ADC | 20 | 20 | 20 | 11 | 16 |
| OPA1 | 1 | 1 | 1 | - | - |
| CMP1 | 1 | 1 | 1 | - | - |
| Current sampling ISP, ISN | Differential *2 | Differential*2 | Differential *2 | Differential *2 | Differential *1 Single end*1 |
| Signal decoding QII | 2 | 2 | 2 | 1 | 1 |
| Programmable current injection module ISINK | 2 | 2 | 2 | 1 | 2 |
| Source current module ISOURCE | 2 | 2 | 2 | - | 1 |
| SPI | 1 | 1 | 1 | - | 1 |
| USB PD Type-C | (CC1, CC2) (CC3, CC4) | (CC1R, CC2R) (CC3, CC4) Built-in Rd(1) | (CC1R, CC2R) (CC3, CC4) Built-in Rd(1) | (CC3, CC4) | (CC1R, CC2R) (CC3, CC4) Built-in Rd(1) |

<details><summary>All 29 rows</summary>

| | [CH32M030&#8203;C8T7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8T7)&#8203;(LQFP48) | [CH32M030&#8203;C8U3](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8U3)&#8203;(QFN48X7_A) | [CH32M030&#8203;C8U7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8U7)&#8203;(QFN48) | [CH32M030&#8203;G8R7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030G8R7)&#8203;(QSOP28) | [CH32M030&#8203;K8U7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030K8U7)&#8203;(QFN32) |
|---|---|---|---|---|---|
| **Flash** | 64K | 64K | 64K | 64K | 64K |
| **SRAM** | 12K | 12K | 12K | 12K | 12K |
| **GPIO** | 35 | 36 | 36 | 17 | 24 |
| **Temperature** | -40..105C | - | -40..105C | -40..105C | -40..105C |
| Half-bridge gate driver | 4 | 4 | 4 | 3 | 2 |
| Pre-drive I/O (MV I/0) | 8 | 8 | 8 | 6 | 6 |
| Advanced-control TIM1 (16-bit) | 1 | 1 | 1 | 1 | 1 |
| High voltage I/O（HV I/0） | - | 2 | 1 | - | 1 |
| General-purpose TIM2 (16-bit) | 1 | 1 | 1 | 1 | 1 |
| Streamlined TIM3 (16-bit) | 1 | 1 | 1 | 1 | 1 |
| WWDG | 1 | 1 | 1 | 1 | 1 |
| System time base (32-bit) | √ | √ | √ | √ | √ |
| ADC | 20 | 20 | 20 | 11 | 16 |
| OPA1 | 1 | 1 | 1 | - | - |
| OPA2 | 1 | 1 | 1 | 1 | 1 |
| OPA3 | 1 | 1 | 1 | 1 | 1 |
| OPA4 | 1 | 1 | 1 | 1 | 1 |
| CMP2 | 1 | 1 | 1 | 1 | 1 |
| CMP1 | 1 | 1 | 1 | - | - |
| CMP3 | 1 | 1 | 1 | 1 | 1 |
| Current sampling ISP, ISN | Differential *2 | Differential*2 | Differential *2 | Differential *2 | Differential *1 Single end*1 |
| Signal decoding QII | 2 | 2 | 2 | 1 | 1 |
| Programmable current injection module ISINK | 2 | 2 | 2 | 1 | 2 |
| UART | 1 | 1 | 1 | 1 | 1 |
| Source current module ISOURCE | 2 | 2 | 2 | - | 1 |
| I2C | 1 | 1 | 1 | 1 | 1 |
| USBFS | Host Device | Host Device | Host Device | Host Device | Host Device |
| SPI | 1 | 1 | 1 | - | 1 |
| USB PD Type-C | (CC1, CC2) (CC3, CC4) | (CC1R, CC2R) (CC3, CC4) Built-in Rd(1) | (CC1R, CC2R) (CC3, CC4) Built-in Rd(1) | (CC3, CC4) | (CC1R, CC2R) (CC3, CC4) Built-in Rd(1) |

</details>

## Packages & pinout drawings

Pinout drawings are in the datasheet (chapter *Pinouts*):

| Package | Products | Datasheet | Outline |
|---|---|---|---|
| LQFP48 | CH32M030C8T7 | [en](https://ch32-riscv-ug.github.io/CH32M030/datasheet_en/CH32M030DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP48.png) |
| QFN48X7_A | CH32M030C8U3 | [en](https://ch32-riscv-ug.github.io/CH32M030/datasheet_en/CH32M030DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_QFN48X7_A.png) |
| QFN48 | CH32M030C8U7 | [en](https://ch32-riscv-ug.github.io/CH32M030/datasheet_en/CH32M030DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_QFN48.png) |
| QSOP28 | CH32M030G8R7 | [en](https://ch32-riscv-ug.github.io/CH32M030/datasheet_en/CH32M030DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_QSOP28.png) |
| QFN32 | CH32M030K8U7 | [en](https://ch32-riscv-ug.github.io/CH32M030/datasheet_en/CH32M030DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_QFN32.png) |

## Pin maps & alternate functions

> [!NOTE]
> These are the **pin-table superset**: the datasheet prints one pad table for every product that shares a pinout, so a pad row does not mean this part has the peripheral. Use the product comparison table above for what a given part number contains.

### CH32M030 pin map

Pin functions (filterable): [ALL](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030) [ADC](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030&features=ADC) [I2C](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030&features=I2C) [SPI](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030&features=SPI) [SYS](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030&features=SYS) [TIM](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030&features=TIM) [UART](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030&features=UART) [USB](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030&features=USB)

| Pin name | Type | [CH32M030&#8203;C8T7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8T7)&#8203;(LQFP48) | [CH32M030&#8203;C8U3](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8U3)&#8203;(QFN48X7_A) | [CH32M030&#8203;C8U7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030C8U7)&#8203;(QFN48) | [CH32M030&#8203;G8R7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030G8R7)&#8203;(QSOP28) | [CH32M030&#8203;K8U7](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32M030K8U7)&#8203;(QFN32) | Notes |
|---|---|---|---|---|---|---|---|
| PA0 | I/O/A | 37 | 37 | 35 | - | 23 |  |
| PA1 | I/O/A | 38 | 38 | 36 | - | 24 |  |
| PA2 | I/O/A | 39 | 39 | 37 | 26 | 25 | SWCLK |
| PA3 | I/O/A | 40 | 40 | 38 | 27 | 26 | SWDIO |
| PA4 | I/O/A | 43 | 43 | 41 | - | 29 |  |
| PA5 | I/O/A | 44 | 44 | 42 | - | - |  |
| PA6 | I/O/A | 45 | 45 | 43 | - | 29 |  |
| PA7 | I/O/A | 46 | 46 | 44 | 2 | 30 |  |
| PA8 | I/O/A | 47 | 47 | 45 | 3 | 31 |  |
| PA10 | I/O/A | 1 | 1 | 47 | 5 | 1 |  |
| PA11 | I/O/A | 2 | 2 | 48 | 6 | - |  |
| PA12 | I/O/A | 3 | 3 | 1 | - | - |  |
| PA13 | I/O/A | 4 | 4 | 2 | 8 | 2 |  |
| PA14 | I/O/A | 5 | 5 | 3 | - | 3 |  |
| PA15 | I/O/A | 6 | 6 | 4 | - | - |  |
| PB0 | I/O/A | 41 | 41 | 39 | 28 | 27 |  |
| PB1 | I/O/A | 42 | 42 | 40 | 1 | 28 |  |
| PB2 | I/O/A | 7 | 7 | 5 | - | 4 |  |
| PB3 | I/O/A | 8 | 8 | 6 | - | 5 |  |
| PB4 | I/O/A | 9 | 9 | 7 | 7 | 6 |  |
| PB5 | I/O/A | 10 | 10 | 8 | 8 | 7 |  |
| PB6 | I/O/A | 11 | 11 | 9 | 9 | 8 |  |
| PB7 | O | - | 29 | - | - | - |  |
| PB8 | I/O | 12 | 12 | 10 | 10 | 9 |  |
| PB9 | O | 15 | 15 | 13 | 13 | 11 |  |
| PB10 | I/O | 16 | 16 | 14 | 14 | 13 |  |
| PB11 | O | 19 | 19 | 17 | 17 | 15 |  |
| PB12 | I/O | 20 | 20 | 18 | 18 | - |  |
| PB13 | O | 23 | 23 | 21 | 21 | 17 |  |
| PB14 | I/O | 24 | 24 | 22 | - | - |  |
| PB15 | O | 27 | 27 | 25 | - | 18 |  |
| PC0 | I/O | 29 | 30 | 27 | - | - | UART RX (USART1) |
| PC1 | I/O | 30 | 31 | 28 | - | - | UART TX (USART1) |
| PC2 | I/O | 31 | - | 29 | - | - |  |
| PC3 | I/O | 32 | 32 | 30 | - | - |  |
| PC4 | I/O | 33 | 33 | 31 | - | - |  |
| PC5 | I/O | - | 34 | 32 | - | 20 |  |
| GND | P | 36 | EP | EP | 25 | EP |  |
| ISP1 | A | 48 | 48 | 46 | 4 | 32 |  |
| VB1 | P | 18 | 18 | 16 | 16 | 16 |  |
| VB2 | P | 22 | 22 | 20 | 20 | 16 |  |
| VB3 | P | 26 | 26 | 24 | - | 16 |  |
| VBO | P | 14 | 14 | 12 | 12 | 12 |  |
| VDD33 | P | 34 | 35 | 33 | 23 | 21 |  |
| VDD8 | P | 28 | 28 | 26 | 22 | 19 |  |
| VHV | P | 35 | 36 | 34 | 24 | 22 |  |
| VS1 | P | 17 | 17 | 15 | 15 | 14 |  |
| VS2 | P | 21 | 21 | 19 | 19 | 14 |  |
| VS3 | P | 25 | 25 | 23 | - | 14 |  |
| VSO | P | 13 | 13 | 11 | 11 | 10 |  |

<details><summary><b>CH32M030 alternate functions</b></summary>

| Pad | default | remap-1 | remap-2 | remap-3 | remap-4 | remap-5 |
|---|---|---|---|---|---|---|
| PA0 | ADC_IN13, CC1(CC1R), SPI_NSS | - | SPI_NSS | TIM1_CH3 | TIM1_CH3 | - |
| PA1 | ADC_IN14, CC2(CC2R), SPI_SCK | - | SPI_SCK | SPI_SCK | TIM1_CH4 | - |
| PA2 | ADC_IN15, CC3, SWCLK | I2C_SCL, SPI_NSS | UART_CTS | I2C_SCL, SPI_NSS, TIM3_CH1_ETR | UART_RX | UART_TX |
| PA3 | ADC_IN16, CC4, CMP3_P0, SWDIO, SWIM | TIM2_CH1_ETR | - | I2C_SDA | UART_TX | UART_RX |
| PA4 | ADC_IN5, ISOURCE1, TIM2_CH2N, TIM2_CH4 | SPI_MISO | TIM1_ETR, UART_RTS | SPI_MISO, TIM1_ETR, TIM3_CH1N | TIM1_ETR | - |
| PA5 | ADC_IN6, CMP3_N0, ISOURCE2, TIM2_CH1_ETR | - | - | - | - | - |
| PA6 | CMP3_N1, ISINK1, TIM2_CH2 | - | - | - | - | - |
| PA7 | ADC_IN2, CMP3_N2, ISINK2, TIM2_CH1N, TIM2_CH3 | - | - | - | - | - |
| PA8 | ADC_IN7, CMP3_OUT0, ISN1, MCO | - | - | SPI_MOSI | - | - |
| PA10 | ISP2 | - | - | - | - | - |
| PA11 | ADC_IN8, ISN2 | - | SPI_MOSI | - | - | - |
| PA12 | ADC_IN19, QII1 | - | - | - | - | - |
| PA13 | ADC_IN18, QII2 | TIM1_BKIN | - | - | - | - |
| PA14 | ADC_ETR, ADC_IN9, Q_DET1, UART_CTS | UART_CTS | I2C_SDA | - | - | - |
| PA15 | ADC_IN10, Q_DET2, RST, TIM1_BKIN, UART_RTS | UART_RTS | I2C_SCL, TIM1_BKIN | TIM1_BKIN | TIM1_BKIN | - |
| PB0 | ADC_IN11, CMP3_P1, UDP | TIM2_CH2 | - | UART_RX | - | - |
| PB1 | ADC_IN12, CMP3_P2, UDM | TIM2_CH1N, TIM2_CH3 | - | TIM2_CH1N, TIM2_CH3, UART_TX | - | - |
| PB2 | ADC_IN0, CMP3_N3, I2C_SDA, TIM3_CH1N | TIM2_CH2N, TIM2_CH4, TIM3_CH2 | TIM3_CH1_ETR | TIM2_CH2N, TIM2_CH4, UART_CTS | UART_CTS | UART_CTS |
| PB3 | ADC_IN1, CMP3_P3, I2C_SCL, TIM3_CH2N | TIM3_CH2N | TIM3_CH2 | UART_RTS | UART_RTS | UART_RTS |
| PB4 | ADC_IN17, CMP3_OUT1, V_DET | - | TIM3_CH1N | - | - | - |
| PB5 | ADC_IN3, CMP2_P0, CMP3_OUT2, XI | SPI_MOSI | TIM3_CH2N, UART_RX | TIM2_CH1_ETR, TIM3_CH2 | - | - |
| PB6 | ADC_IN4, CMP2_N0, XO | ADC_ETR, I2C_SDA, SPI_SCK | UART_TX | TIM2_CH2, TIM3_CH2N | - | - |
| PB8 | LO0, TIM1_CH1N | TIM1_CH1N | TIM1_CH1N | - | TIM1_CH1N | - |
| PB9 | HO0, TIM1_CH1 | TIM1_CH1 | TIM1_CH1 | - | TIM1_CH1 | - |
| PB10 | LO1, TIM1_CH2N | TIM1_CH2N | TIM1_CH2N | - | TIM1_CH2N | - |
| PB11 | HO1, TIM1_CH2 | TIM1_CH2 | TIM1_CH2 | - | TIM1_CH2 | - |
| PB12 | LO2, TIM1_CH3N | TIM1_CH3N | TIM2_CH1N, TIM2_CH3 | - | TIM1_CH3N, TIM3_CH1N | - |
| PB13 | HO2, TIM1_CH3 | TIM1_CH3 | TIM2_CH1_ETR | - | TIM1_CH3, TIM3_CH1_ETR | - |
| PB14 | LO3 | - | TIM1_CH3N, TIM2_CH2N, TIM2_CH4 | - | TIM3_CH2N | - |
| PB15 | HO3 | TIM1_CH4 | TIM1_CH3, TIM2_CH2 | - | TIM3_CH2 | - |
| PC0 | RST, TIM1_CH4, TIM3_CH1_ETR, UART_RX | TIM3_CH1_ETR | - | TIM1_CH3N | TIM1_CH3N | - |
| PC1 | TIM1_ETR, TIM3_CH2, UART_TX | TIM1_ETR, TIM3_CH1N, UART_TX | - | TIM1_CH2N | TIM1_CH2N | - |
| PC2 | - | UART_RX | TIM1_CH4 | TIM1_CH1N | TIM1_CH1N | - |
| PC3 | SPI_MOSI | - | - | TIM1_CH1 | TIM1_CH1 | - |
| PC4 | SPI_MISO | - | SPI_MISO | TIM1_CH2 | TIM1_CH2 | - |
| PC5 | - | - | TIM2_CH2 | TIM1_CH4 | - | - |

</details>

<details><summary><b>Remap selectors (AFIO)</b></summary>

| Series | Field | Register | Bits | Values | Reset |
|---|---|---|---|---|---|
| CH32M030 | ADC_ETRGIN_REMAP | PCFR1 | PCFR1:15 | 0;1 | 0 |
| CH32M030 | I2C1_REMAP | PCFR1 | PCFR1:0;PCFR1:1 | 0;1;2;3 | 0 |
| CH32M030 | SPI1_REMAP | PCFR1 | PCFR1:5;PCFR1:6 | 0;1;2;3 | 0 |
| CH32M030 | TIM1_REMAP | PCFR1 | PCFR1:7;PCFR1:8;PCFR1:9 | 0;1;2;3;4 | 0 |
| CH32M030 | TIM2_REMAP | PCFR1 | PCFR1:10;PCFR1:11 | 0;1;2;3 | 0 |
| CH32M030 | TIM3_REMAP | PCFR1 | PCFR1:12;PCFR1:13;PCFR1:14 | 0;1;2;3;4 | 0 |
| CH32M030 | UART1_REMAP | PCFR1 | PCFR1:2;PCFR1:3;PCFR1:4 | 0;1;2;3;4;5 | 0 |
| CH32M030 | ISINK1_ADJ | CTR | CTR:0;CTR:1;CTR:2;CTR:3;CTR:4;CTR:5 | 0 |  |
| CH32M030 | ISINK2_ADJ | CTR | CTR:16;CTR:17;CTR:18;CTR:19;CTR:20;CTR:21 | 0 |  |

</details>

## Block diagrams

### CH32M030
<img src="image/architecture_CH32M030.png" alt="CH32M030 block diagram" />

## EVT examples

120 routines in [EVT/EXAM](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM):

[ADC](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/ADC) 7 · [APPLICATION](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/APPLICATION) 24 · [DMA](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/DMA) 2 · [EXTI](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/EXTI) 1 · [FLASH](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/FLASH) 2 · [GPIO](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/GPIO) 1 · [I2C](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/I2C) 6 · [IAP](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/IAP) 1 · [INT](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/INT) 2 · [OPA](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/OPA) 3 · [PWR](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/PWR) 4 · [RCC](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/RCC) 3 · [SDI_Printf](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/SDI_Printf) 1 · [SPI](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/SPI) 7 · [SYSTICK](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/SYSTICK) 1 · [TIM](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/TIM) 18 · [UART](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/UART) 9 · [USART](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/USART) 8 · [USB](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/USB) 17 · [USBPD](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/USBPD) 2 · [WWDG](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT/EXAM/WWDG) 1

## Documents

| Document | Kind | English | 中文 |
|---|---|---|---|
| CH32M030DS0.PDF | datasheet | [page](https://www.wch-ic.com/downloads/CH32M030DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32M030/datasheet_en/CH32M030DS0.PDF) v1.2 | [page](https://www.wch.cn/downloads/CH32M030DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030DS0.PDF) v1.3 |
| CH32M030DS2.PDF | datasheet | - | [page](https://www.wch.cn/downloads/CH32M030DS2_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030DS2.PDF) v1.2 |
| CH32M030RM.PDF | reference-manual | [page](https://www.wch-ic.com/downloads/CH32M030RM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32M030/datasheet_en/CH32M030RM.PDF) v1.2 | [page](https://www.wch.cn/downloads/CH32M030RM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32M030/datasheet_zh/CH32M030RM.PDF) v1.2 |
| CH32M030EVT.ZIP | evt | - | [page](https://www.wch.cn/downloads/CH32M030EVT_ZIP.html) [mirror](https://github.com/ch32-riscv-ug/CH32M030/tree/main/EVT) v1.5 |

### Evaluation boards

- board-manual:en: [CH32M030 Evaluation Board Reference-EN.pdf](https://github.com/ch32-riscv-ug/CH32M030/blob/main/EVT/PUB/CH32M030%20Evaluation%20Board%20Reference-EN.pdf)
- board-manual:zh: [CH32M030评估板说明书.pdf](https://github.com/ch32-riscv-ug/CH32M030/blob/main/EVT/PUB/CH32M030%E8%AF%84%E4%BC%B0%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6.pdf)
- schematic-pdf: [CH32M030SCH.pdf](https://github.com/ch32-riscv-ug/CH32M030/blob/main/EVT/PUB/CH32M030SCH.pdf)

5 board schematics under `EVT/PUB/SCHPCB/`: `CH32M030C8T7-R0`, `CH32M030C8U3-R0`, `CH32M030C8U7-R0`, `CH32M030G8R7-R0`, `CH32M030K8U7-R0`

## Reference

### Address map

| Region | Base | Kind |
|---|---|---|
| PERIPH | `0x40000000` | bus |
| HBPERIPH | `0x40020000` | bus |
| FLASH | `0x00000000` | link-origin |
| RAM | `0x20000000` | link-origin |
| FLASH | `0x08000000` | memory |
| OB | `0x1ffff300` | memory |
| SRAM | `0x20000000` | memory |

`link-origin` is what the EVT linker scripts use; the `memory` row for FLASH is the address the device header states. Both windows are real -- CH32V307 answers at `0x08000000` and at `0x00000000`.

Peripheral base addresses are in [memory_map.csv](https://github.com/ch32-riscv-ug/ch32-device-data/blob/main/evidence/memory_map.csv); interrupt numbers in [interrupts.csv](https://github.com/ch32-riscv-ug/ch32-device-data/blob/main/evidence/interrupts.csv).

---
Data: [ch32-device-data](https://github.com/ch32-riscv-ug/ch32-device-data) (evidence/ and index/ -- each value carries its evidence and confidence there).
