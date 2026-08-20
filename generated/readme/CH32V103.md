# CH32V103

<!-- This file is generated from ch32-riscv-ug/ch32-device-data (tables/ + tools/build_readme.py). Edit there, not here. -->

## Series

| Series | Core | ISA | Flash | SRAM | Clock | VDD | Packages | Products | Official |
|---|---|---|---|---|---|---|---|---|---|
| **CH32V103** | QingKe V3A | RV32IMAC | - | - | 80 MHz | 2.7-5.5V | LQFP48,LQFP64M,QFN48X7 | 4 | [en](https://www.wch-ic.com/products/CH32V103.html) / [zh](https://www.wch.cn/products/CH32V103.html) |

## Debug / serial defaults

| Series | SWDIO | SWCLK | UART TX | UART RX |
|---|---|---|---|---|
| CH32V103 | - | - | PA9 | PA10 |

## Documents

| Document | Kind | English | 中文 |
|---|---|---|---|
| CH32V103DS0.PDF | datasheet | [page](https://www.wch-ic.com/downloads/CH32V103DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V103/datasheet_en/CH32V103DS0.PDF) v1.2 | [page](https://www.wch.cn/downloads/CH32V103DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V103/datasheet_zh/CH32V103DS0.PDF) v1.2 |
| CH32xRM.PDF | reference-manual | [page](https://www.wch-ic.com/downloads/CH32xRM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V103/datasheet_en/CH32xRM.PDF) v2.0 | [page](https://www.wch.cn/downloads/CH32xRM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32V103/datasheet_zh/CH32xRM.PDF) v2.0 |
| CH32V103EVT.ZIP | evt | - | [page](https://www.wch.cn/downloads/CH32V103EVT_ZIP.html) [mirror](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT) v2.7 |

## Pinouts

Pinout drawings are in the datasheet (chapter *Pinouts*):

| Package | Products | Datasheet | Outline |
|---|---|---|---|
| LQFP48 | CH32V103C6T6 | [en](https://ch32-riscv-ug.github.io/CH32V103/datasheet_en/CH32V103DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V103/datasheet_zh/CH32V103DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP48.png) |
| LQFP48 | CH32V103C8T6 | [en](https://ch32-riscv-ug.github.io/CH32V103/datasheet_en/CH32V103DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V103/datasheet_zh/CH32V103DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP48.png) |
| QFN48X7 | CH32V103C8U6 | [en](https://ch32-riscv-ug.github.io/CH32V103/datasheet_en/CH32V103DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V103/datasheet_zh/CH32V103DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_QFN48X7.png) |
| LQFP64M | CH32V103R8T6 | [en](https://ch32-riscv-ug.github.io/CH32V103/datasheet_en/CH32V103DS0.PDF) / [zh](https://ch32-riscv-ug.github.io/CH32V103/datasheet_zh/CH32V103DS0.PDF) | [drawing](https://raw.githubusercontent.com/ch32-riscv-ug/WCH-common/main/image/package_LQFP64M.png) |

## Product comparison

### CH32V103 product comparison

| | CH32V103&#8203;C6T6&#8203;(LQFP48) | CH32V103&#8203;C8T6&#8203;(LQFP48) | CH32V103&#8203;C8U6&#8203;(QFN48X7) | CH32V103&#8203;R8T6&#8203;(LQFP64M) |
|---|---|---|---|---|
| **Flash** | 32K | 64K | 64K | 64K |
| **SRAM** | 10K | 20K | 20K | 20K |
| **GPIO** | 37 | 37 | 37 | 51 |
| **Temperature** | -40..85C | -40..85C | -40..85C | -40..85C |
| ADC/TKey (Number of channels) | 10 | 10 | 10 | 16 |
| CommunicationInterface | 1 | 2 | 2 | 2 |
| CPU clock frequency | Typical: 72MHz | - | - | - |
| CPU主频 | Typ. 72MHz | - | - | - |
| 工作电压 | 2.7V～5.5V | - | - | - |
| Operating voltage | 2.7V~5.5V | - | - | - |
| Timer | 2 | 3 | 3 | 3 |

## Pin definitions

### CH32V103 pin map

Pin functions (filterable): [ALL](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103) [ADC](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103&features=ADC) [I2C](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103&features=I2C) [SPI](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103&features=SPI) [SYS](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103&features=SYS) [TIM](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103&features=TIM) [UART](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103&features=UART) [USB](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103&features=USB)

| Pin name | Type | [CH32V103&#8203;C6T6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103C6T6)&#8203;(LQFP48) | [CH32V103&#8203;C8T6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103C8T6)&#8203;(LQFP48) | [CH32V103&#8203;C8U6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103C8U6)&#8203;(QFN48X7) | [CH32V103&#8203;R8T6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32V103R8T6)&#8203;(LQFP64M) | Notes |
|---|---|---|---|---|---|---|
| PA1 | I/O/A | 11 | 11 | 11 | 15 |  |
| PA2 | I/O/A | 12 | 12 | 12 | 16 |  |
| PA3 | I/O/A | 13 | 13 | 13 | 17 |  |
| PA4 | I/O/A | 14 | 14 | 14 | 20 |  |
| PA5 | I/O/A | 15 | 15 | 15 | 21 |  |
| PA6 | I/O/A | 16 | 16 | 16 | 22 |  |
| PA7 | I/O/A | 17 | 17 | 17 | 23 |  |
| PA8 | I/O | 29 | 29 | 29 | 41 |  |
| PA9 | I/O | 30 | 30 | 30 | 42 | UART TX |
| PA10 | I/O | 31 | 31 | 31 | 43 | UART RX |
| PA11 | I/O/A | 32 | 32 | 32 | 44 |  |
| PA12 | I/O/A | 33 | 33 | 33 | 45 |  |
| PA13 | I/O | 34 | 34 | 34 | 46 |  |
| PA14 | I/O | 37 | 37 | 37 | 49 |  |
| PA15 | I/O | 38 | 38 | 38 | 50 |  |
| PB0 | I/O/A | 18 | 18 | 18 | 26 |  |
| PB1 | I/O/A | 19 | 19 | 19 | 27 |  |
| PB2 | I/O | 20 | 20 | 20 | 28 |  |
| PB3 | I/O | 39 | 39 | 39 | 55 |  |
| PB4 | I/O | 40 | 40 | 40 | 56 |  |
| PB5 | I/O | 41 | 41 | 41 | 57 |  |
| PB6 | I/O/A | 42 | 42 | 42 | 58 |  |
| PB7 | I/O/A | 43 | 43 | 43 | 59 |  |
| PB8 | I/O/A | 45 | 45 | 45 | 61 |  |
| PB9 | I/O/A | 46 | 46 | 46 | 62 |  |
| PB10 | I/O | 21 | 21 | 21 | 29 |  |
| PB11 | I/O | 22 | 22 | 22 | 30 |  |
| PB12 | I/O | 25 | 25 | 25 | 33 |  |
| PB13 | I/O | 26 | 26 | 26 | 34 |  |
| PB14 | I/O | 27 | 27 | 27 | 35 |  |
| PB15 | I/O | 28 | 28 | 28 | 36 |  |
| PC0 | I/O/A | - | - | - | 8 |  |
| PC1 | I/O/A | - | - | - | 9 |  |
| PC2 | I/O/A | - | - | - | 10 |  |
| PC3 | I/O/A | - | - | - | 11 |  |
| PC4 | I/O/A | - | - | - | 24 |  |
| PC5 | I/O/A | - | - | - | 25 |  |
| PC6 | I/O | - | - | - | 37 |  |
| PC7 | I/O | - | - | - | 38 |  |
| PC8 | I/O | - | - | - | 39 |  |
| PC9 | I/O | - | - | - | 40 |  |
| PC10 | I/O | - | - | - | 51 |  |
| PC11 | I/O | - | - | - | 52 |  |
| PC12 | I/O | - | - | - | 53 |  |
| PD2 | I/O | - | - | - | 54 |  |
| BOOT0 | I | 44 | 44 | 44 | 60 |  |
| NRST | I/O | 7 | 7 | 7 | 7 |  |
| OSC8M_IN | I/A | 5 | - | - | - |  |
| OSC_IN | I/A | - | 5 | 5 | 5 |  |
| OSC_OUT | O/A | - | 6 | 6 | 6 |  |
| PA0-WKUP | I/O/A | 10 | 10 | 10 | 14 |  |
| VBAT | P | 1 | 1 | 1 | 1 |  |
| VDDA | P | 9 | 9 | 9 | 13 |  |
| VDD_1 | P | 24 | 24 | 24 | 32 |  |
| VDD_2 | P | 36 | 36 | 36 | 48 |  |
| VDD_3 | P | 48 | 48 | 48 | 64 |  |
| VDD_4 | P | - | - | - | 19 |  |
| VSSA | P | 8 | 8 | 8 | 12 |  |
| VSS_1 | P | 23 | 23 | 23 | 31 |  |
| VSS_2 | P | 35 | 35 | 35 | 47 |  |
| VSS_3 | P | 47 | 47 | 47 | 63 |  |
| VSS_4 | P | - | - | - | 18 |  |

<details><summary><b>CH32V103 alternate functions</b></summary>

| Pad | default | (no route stated) | remap-1 |
|---|---|---|---|
| PA1 | ADC_IN1, TIM2_CH2, USART2_RTS | - | - |
| PA2 | ADC_IN2, TIM2_CH3, USART2_TX | - | - |
| PA3 | ADC_IN3, TIM2_CH4, USART2_RX | - | - |
| PA4 | ADC_IN4, SPI1_NSS, USART2_CK | - | - |
| PA5 | ADC_IN5, SPI1_SCK | - | - |
| PA6 | ADC_IN6, SPI1_MISO, TIM3_CH1 | - | TIM1_BKIN |
| PA7 | ADC_IN7, SPI1_MOSI, TIM3_CH2 | - | TIM1_CH1N |
| PA8 | MCO, TIM1_CH1, USART1_CK | - | - |
| PA9 | TIM1_CH2, USART1_TX | - | - |
| PA10 | TIM1_CH3, USART1_RX | - | - |
| PA11 | TIM1_CH4, USART1_CTS, USBHDM | - | - |
| PA12 | R, TIM1_ET, TIM1_ETR, USART1_RTS, USBHDP | - | - |
| PA13 | - | PA13 | - |
| PA14 | - | PA14 | - |
| PA15 | - | - | SPI1_NSS, TIM2_CH1, TIM2_ETR |
| PB0 | ADC_IN8, TIM3_CH3 | - | TIM1_CH2N |
| PB1 | ADC_IN9, TIM3_CH4 | - | TIM1_CH3N |
| PB3 | - | - | SPI1_SCK, TIM2_CH2 |
| PB4 | - | - | SPI1_MISO, TIM3_CH1 |
| PB5 | I2C1_SMBAI | - | SPI1_MOSI, TIM3_CH2 |
| PB6 | I2C1_SCL, TIM4_CH1 | - | USART1_TX |
| PB7 | I2C1_SDA, TIM4_CH2 | - | USART1_RX |
| PB8 | TIM4_CH3 | - | I2C1_SCL |
| PB9 | TIM4_CH4 | - | I2C1_SDA |
| PB10 | I2C2_SCL, USART3_TX | - | TIM2_CH3 |
| PB11 | I2C2_SDA, USART3_RX | - | TIM2_CH4 |
| PB12 | I2C2_SMBAI, SPI2_NSS, TIM1_BKIN, USART3_CK | - | - |
| PB13 | SPI2_SCK, TIM1_CH1N, USART3_CTS | - | - |
| PB14 | SPI2_MISO, TIM1_CH2N, USART3_RTS | - | - |
| PB15 | SPI2_MOSI, TIM1_CH3N | - | - |
| PC0 | ADC_IN10 | - | - |
| PC1 | ADC_IN11 | - | - |
| PC2 | ADC_IN12 | - | - |
| PC3 | ADC_IN13 | - | - |
| PC4 | ADC_IN14 | - | - |
| PC5 | ADC_IN15 | - | - |
| PC6 | - | - | TIM3_CH1 |
| PC7 | - | - | TIM3_CH2 |
| PC8 | - | - | TIM3_CH3 |
| PC9 | - | - | TIM3_CH4 |
| PC10 | - | - | USART3_TX |
| PC11 | - | - | USART3_RX |
| PC12 | - | - | USART3_CK |
| PD2 | TIM3_ETR | - | - |
| OSC8M_IN | - | PD0 | - |
| OSC_IN | - | PD0 | - |
| OSC_OUT | - | PD1 | - |
| PA0-WKUP | ADC_IN0, TIM2_CH1, TIM2_ETR, USART2_CTS, WKUP | - | - |

</details>

<details><summary><b>Remap selectors (AFIO)</b></summary>

| Series | Field | Register | Bits | Values | Reset |
|---|---|---|---|---|---|
| CH32V103 | I2C1_REMAP | PCFR1 | PCFR1:1 | 0;1 |  |
| CH32V103 | SPI1_REMAP | PCFR1 | PCFR1:0 | 0;1 |  |
| CH32V103 | TIM1_REMAP | PCFR1 | PCFR1:6;PCFR1:7 | 0;1;3 |  |
| CH32V103 | TIM2_REMAP | PCFR1 | PCFR1:8;PCFR1:9 | 0;1;2;3 |  |
| CH32V103 | TIM3_REMAP | PCFR1 | PCFR1:10;PCFR1:11 | 0;1;2;3 |  |
| CH32V103 | TIM4_REMAP | PCFR1 | PCFR1:12 | 0 |  |
| CH32V103 | USART1_REMAP | PCFR1 | PCFR1:2 | 0;1 |  |
| CH32V103 | USART2_REMAP | PCFR1 | PCFR1:3 | 0 |  |
| CH32V103 | USART3_REMAP | PCFR1 | PCFR1:4;PCFR1:5 | 0;1;3 |  |

</details>

## Block diagrams

### CH32V103
<img src="image/architecture_CH32V103.png" alt="CH32V103 block diagram" />

## EVT examples

93 routines in [EVT/EXAM](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM):

[ADC](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/ADC) 9 · [APPLICATION](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/APPLICATION) 2 · [BKP](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/BKP) 1 · [CRC](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/CRC) 1 · [DMA](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/DMA) 2 · [EXTI](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/EXTI) 1 · [FLASH](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/FLASH) 1 · [FreeRTOS](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/FreeRTOS) 1 · [GPIO](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/GPIO) 1 · [HarmonyOS](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/HarmonyOS) 1 · [I2C](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/I2C) 6 · [IAP](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/IAP) 1 · [IWDG](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/IWDG) 1 · [PWR](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/PWR) 5 · [RCC](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/RCC) 5 · [RT-Thread](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/RT-Thread) 1 · [RTC](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/RTC) 2 · [SPI](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/SPI) 7 · [SYSTICK](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/SYSTICK) 1 · [TIM](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/TIM) 16 · [TOUCHKEY](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/TOUCHKEY) 1 · [TencentOS](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/TencentOS) 1 · [USART](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/USART) 9 · [USB](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/USB) 16 · [WWDG](https://github.com/ch32-riscv-ug/CH32V103/tree/main/EVT/EXAM/WWDG) 1

---
Data: [ch32-device-data](https://github.com/ch32-riscv-ug/ch32-device-data) (tables/ -- each value carries its evidence and confidence there).
