# CH32X315

<!-- This file is generated from ch32-riscv-ug/ch32-device-data (tables/ + tools/build_readme.py). Edit there, not here. -->

## Series

| Series | Core | ISA | Flash | SRAM | Packages | Products | Official |
|---|---|---|---|---|---|---|---|
| **CH32X305** | QingKe V3F | RV32IMAFBC-X | 480K | 64K | LQFP64 | 1 | [en](https://www.wch-ic.com/products/CH32X305.html) / [zh](https://www.wch.cn/products/CH32X305.html) |
| **CH32X315** | QingKe V3F | RV32IMAFBC-X | 480K | 64K | QFN48,QFN68X7,QFN76 | 3 | [en](https://www.wch-ic.com/products/CH32X315.html) / [zh](https://www.wch.cn/products/CH32X315.html) |

## Debug / serial defaults

| Series | SWDIO | SWCLK | UART TX | UART RX |
|---|---|---|---|---|
| CH32X305 | - | - | - | - |
| CH32X315 | - | - | - | - |

## Documents

| Document | Kind | English | 中文 |
|---|---|---|---|
| CH32X315DS0.PDF | datasheet | [page](https://www.wch-ic.com/downloads/CH32X315DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32X315/datasheet_en/CH32X315DS0.PDF) v1.1 | [page](https://www.wch.cn/downloads/CH32X315DS0_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32X315/datasheet_zh/CH32X315DS0.PDF) v1.1 |
| CH32X315RM.PDF | reference-manual | [page](https://www.wch-ic.com/downloads/CH32X315RM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32X315/datasheet_en/CH32X315RM.PDF) v1.1 | [page](https://www.wch.cn/downloads/CH32X315RM_PDF.html) [mirror](https://ch32-riscv-ug.github.io/CH32X315/datasheet_zh/CH32X315RM.PDF) v1.1 |
| CH32X315EVT.ZIP | evt | - | [page](https://www.wch.cn/downloads/CH32X315EVT_ZIP.html) [mirror](https://github.com/ch32-riscv-ug/CH32X315/tree/main/EVT) v1.0 |

## Product comparison

### CH32X315 product comparison

| | CH32X315&#8203;CCU6&#8203;(QFN48) | CH32X315&#8203;MCU6&#8203;(QFN76) | CH32X315&#8203;WCU6&#8203;(QFN68X7) |
|---|---|---|---|
| **Flash** | 480K | 480K | 480K |
| **SRAM** | 64K | 64K | 64K |
| **GPIO** | 40 | 64 | 59 |
| **Temperature** | -40..85C | -40..85C | -40..85C |
| ADC | 8+1 | 12+1 | 12+1 |
| ARGB | 1 | 1 | 1 |
| I2C | 2 | 2 | 2 |
| PDUSB | Host/Device | Host/Device | Host/Device |
| SPI | 3 | 3 | 3 |
| Timer | 1 | 1 | 1 |
| USART | 4 | 4 | 4 |
| CPU main frequency | - | Max: 480MHz | - |
| RTC | - | Support | - |

## Pin definitions

### CH32X305 pin map

Pin functions (filterable): [ALL](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305) [ADC](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305&features=ADC) [I2C](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305&features=I2C) [SPI](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305&features=SPI) [SYS](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305&features=SYS) [TIM](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305&features=TIM) [UART](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305&features=UART) [USB](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305&features=USB)

| Pin name | Type | [CH32X305&#8203;RCT6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X305RCT6)&#8203;(LQFP64) | Notes |
|---|---|---|---|
| PA0 | I/O/A | 17 |  |
| PA1 | I/O/A | 18 |  |
| PA2 | I/O/A | 19 |  |
| PA3 | I/O/A | 20 |  |
| PA4 | I/O/A | 21 |  |
| PA5 | I/O/A | 22 |  |
| PA6 | I/O/A | 23 |  |
| PA7 | I/O/A | 24 |  |
| PA8 | I/O/A | 45 |  |
| PA9 | I/O/A | 46 |  |
| PA10 | I/O | 47 |  |
| PA11 | I/O | 48 |  |
| PA12 | I/O | 49 |  |
| PA13 | I/O | 50 |  |
| PA14 | I/O | 51 |  |
| PA15 | I/O | 52 |  |
| PB0 | I/O/A | 25 |  |
| PB4 | I/O/A | 26 |  |
| PB5 | I/O/A | 27 |  |
| PB6 | I/O/A | 28 |  |
| PB7 | I/O/A | 29 |  |
| PB8 | I/O/A | 37 |  |
| PB9 | I/O/A | 38 |  |
| PB10 | I/O/A | 39 |  |
| PB11 | I/O/A | 40 |  |
| PB12 | I/O | 53 |  |
| PB13 | I/O | 54 |  |
| PB14 | I/O | 55 |  |
| PB15 | I/O | 56 |  |
| PC0 | I/O/A | 4 |  |
| PC1 | I/O/A | 5 |  |
| PC2 | I/O/A | 6 |  |
| PC3 | I/O/A | 7 |  |
| PC4 | I/O/A | 8 |  |
| PC5 | I/O/A | 9 |  |
| PC6 | I/O/A | 10 |  |
| PC7 | I/O/A | 11 |  |
| PC8 | I/O/A | 30 |  |
| PC9 | I/O/A | 31 |  |
| PC10 | I/O/A | 32 |  |
| PC11 | I/O/A | 33 |  |
| PC12 | I/O/A | 35 |  |
| PC13 | I/O/A | 36 |  |
| PD2 | I/O | 3 |  |
| PD3 | I/O | 57 |  |
| PD6 | I/O/A | 60 |  |
| PD7 | I/O/A | 61 |  |
| PD10 | I/O/A | 41 |  |
| PD11 | I/O/A | 42 |  |
| PD12 | I/O/A | 43 |  |
| PD13 | I/O/A | 44 |  |
| VDD | P | 16/34/64 |  |
| VDDA | P | 14 |  |
| VDDK | P | 62 |  |
| VREF+ | P | 13 |  |
| VREF- | P | 12 |  |
| VSS | P | 15/63 |  |
| XI | I/A | 1 |  |
| XO | O/A | 2 |  |

<details><summary><b>CH32X305 alternate functions</b></summary>

| Pad | default | af-0 | af-1 | af-2 | af-3 | af-4 | af-5 | af-6 | af-7 |
|---|---|---|---|---|---|---|---|---|---|
| PA0 | ADC4_IN10 | - | - | - | I2C1_SCL | - | - | TIM1_CH1N | TIM4_ETR |
| PA1 | ADC4_IN11 | - | - | - | I2C1_SDA | - | - | TIM1_CH2N | - |
| PA2 | ADC1_IN0 | - | - | - | - | - | - | TIM1_CH3N | - |
| PA3 | ADC1_IN1 | - | USART2_CK | - | - | - | - | - | - |
| PA4 | ADC1_IN2 | - | USART2_TX | - | - | SPI1_SCS | - | TIM2_CH1_ETR | - |
| PA5 | ADC1_IN3 | - | USART2_RX | - | - | SPI1_SCK | - | TIM2_CH2 | - |
| PA6 | ADC1_IN4 | - | USART2_CTS | - | - | SPI1_MOSI | - | TIM2_CH3 | - |
| PA7 | ADC1_IN5 | - | USART2_RTS | - | - | SPI1_MISO | - | TIM2_CH4 | - |
| PA8 | ADC3_IN8 | - | USART4_TX | - | I2C1_SCL | - | - | TIM1_CH2N | - |
| PA9 | ADC3_IN9 | - | USART4_RX | - | I2C1_SDA | - | - | TIM1_CH3N | - |
| PA10 | - | - | USART1_RX | - | - | - | ADCS0 | TIM1_CH1 | - |
| PA11 | - | - | USART1_TX | - | I2C2_SCL | - | ADCS1 | TIM1_CH2 | - |
| PA12 | - | - | USART1_RX | - | I2C2_SDA | SPI1_SCS | ADCS2 | TIM1_CH3 | - |
| PA13 | SWDIO, SWIO | - | USART3_TX | USART2_RX | I2C1_SDA | SPI1_SCK | - | TIM1_CH1N | - |
| PA14 | SWCLK | - | USART3_RX | USART2_TX | I2C1_SCL | SPI1_MOSI | - | TIM1_CH2N | - |
| PA15 | - | MCO | - | - | - | SPI1_MISO | ARGB_TX | TIM1_CH3N | TIM3_CH4 |
| PB0 | ADC1_IN6 | - | - | - | - | SPI1_SCS | - | - | - |
| PB4 | ADC1_IN10 | - | - | - | - | SPI2_SCS | - | TIM2_CH1_ETR | - |
| PB5 | ADC1_IN11 | - | - | - | - | SPI2_SCK | - | TIM2_CH2 | - |
| PB6 | ADC2_IN0 | - | USART3_CTS | - | - | SPI2_MOSI | - | TIM2_CH3 | - |
| PB7 | ADC2_IN1 | - | USART3_RTS | - | - | SPI2_MISO | - | TIM2_CH4 | - |
| PB8 | ADC2_IN10 | - | - | - | - | - | - | TIM1_CH1 | - |
| PB9 | ADC2_IN11 | - | - | - | I2C2_SCL | - | - | TIM1_CH2 | - |
| PB10 | ADC3_IN0 | - | - | - | I2C2_SDA | - | - | TIM1_CH3 | - |
| PB11 | ADC3_IN1 | - | - | - | - | - | - | TIM1_CH4 | - |
| PB12 | - | - | USART4_TX | - | - | SPI2_SCS | - | - | - |
| PB13 | - | - | USART4_RX | - | - | SPI2_SCK | - | - | - |
| PB14 | - | - | - | - | I2C1_SCL | SPI2_MOSI | - | - | - |
| PB15 | - | - | - | - | I2C1_SDA | SPI2_MISO | - | - | - |
| PC0 | ADC4_IN2 | - | - | - | - | - | - | - | - |
| PC1 | ADC4_IN3 | - | - | - | - | - | - | - | - |
| PC2 | ADC4_IN4 | - | - | - | - | - | - | - | - |
| PC3 | ADC4_IN5 | - | USART1_CK | - | - | - | - | TIM1_ETR | - |
| PC4 | ADC4_IN6 | - | USART1_TX | - | - | SPI3_SCS | - | TIM1_CH1 | TIM4_CH1 |
| PC5 | ADC4_IN7 | - | - | - | - | - | - | TIM1_CH2 | TIM4_CH2 |
| PC6 | ADC4_IN8 | - | USART1_CTS | - | - | SPI3_MOSI | - | TIM1_CH3 | TIM4_CH3 |
| PC7 | ADC4_IN9 | - | USART1_RTS | - | - | SPI3_MISO | - | TIM1_CH4 | TIM4_CH4 |
| PC8 | ADC2_IN2 | RTC | USART3_TX | - | - | SPI3_SCS | - | - | TIM3_CH1 |
| PC9 | ADC2_IN3 | - | USART3_RX | - | - | SPI3_SCK | - | - | TIM3_CH2 |
| PC10 | ADC2_IN4 | - | USART3_CK | - | I2C2_SCL | SPI3_MOSI | - | - | TIM3_CH3 |
| PC11 | ADC2_IN5 | - | - | - | I2C2_SDA | SPI3_MISO | - | - | TIM3_CH4 |
| PC12 | ADC2_IN6 | - | USART2_TX | - | - | - | - | - | TIM3_ETR |
| PC13 | ADC2_IN7 | - | USART2_RX | - | - | - | - | - | - |
| PD2 | NRST | - | - | - | - | SPI1_MOSI | - | - | - |
| PD3 | - | - | - | - | - | SPI1_MISO | ARGB_TX | TIM1_BKIN | TIM3_CH1 |
| PD6 | USBHS_DM | - | USART2_TX | - | I2C2_SCL | - | - | - | - |
| PD7 | USBHS_DP | - | USART2_RX | - | I2C2_SDA | - | - | - | - |
| PD10 | ADC3_IN4 | - | - | - | - | SPI3_SCS | - | - | TIM4_CH1 |
| PD11 | ADC3_IN5 | - | USART4_CK | - | - | SPI3_SCK | - | - | TIM4_CH2 |
| PD12 | ADC3_IN6 | - | USART4_CTS | - | - | SPI3_MOSI | - | - | TIM4_CH3 |
| PD13 | ADC3_IN7 | - | USART4_RTS | - | - | SPI3_MISO | - | TIM1_CH1N | TIM4_CH4 |
| XI | PD0（2） | - | USART1_RX | - | I2C2_SCL | SPI1_SCS | - | - | - |
| XO | PD1（2） | - | USART1_TX | - | I2C2_SDA | SPI1_SCK | - | - | - |

</details>

### CH32X315 pin map

Pin functions (filterable): [ALL](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315) [ADC](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315&features=ADC) [I2C](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315&features=I2C) [SPI](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315&features=SPI) [SYS](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315&features=SYS) [TIM](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315&features=TIM) [UART](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315&features=UART) [USB](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315&features=USB)

| Pin name | Type | [CH32X315&#8203;CCU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315CCU6)&#8203;(QFN48) | [CH32X315&#8203;MCU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315MCU6)&#8203;(QFN76) | [CH32X315&#8203;WCU6](https://ch32-riscv-ug.github.io/ch32-device-data/pins.html?chip=CH32X315WCU6)&#8203;(QFN68X7) | Notes |
|---|---|---|---|---|---|
| PA0 | I/O/A | 10 | 18 | 15 |  |
| PA1 | I/O/A | 11 | 19 | 16 |  |
| PA2 | I/O/A | 12 | 20 | 17 |  |
| PA3 | I/O/A | 13 | 21 | 18 |  |
| PA4 | I/O/A | 14 | 22 | 19 |  |
| PA5 | I/O/A | 15 | 23 | 20 |  |
| PA6 | I/O/A | 16 | 24 | 21 |  |
| PA7 | I/O/A | 17 | 25 | 22 |  |
| PA8 | I/O/A | 30 | 53 | 50 |  |
| PA9 | I/O/A | 31 | 54 | 51 |  |
| PA10 | I/O | 32 | 55 | 52 |  |
| PA11 | I/O | 33 | 56 | 53 |  |
| PA12 | I/O | 34 | 57 | 54 |  |
| PA13 | I/O | 35 | 59 | 55 |  |
| PA14 | I/O | 36 | 60 | 56 |  |
| PA15 | I/O | 37 | 61 | 57 |  |
| PB0 | I/O/A | - | 26 | 23 |  |
| PB1 | I/O/A | - | 27 | 24 |  |
| PB2 | I/O/A | - | 28 | 25 |  |
| PB3 | I/O/A | - | 29 | 26 |  |
| PB4 | I/O/A | 18 | 30 | 27 |  |
| PB5 | I/O/A | 19 | 31 | 28 |  |
| PB6 | I/O/A | 20 | 32 | 29 |  |
| PB7 | I/O/A | 21 | 33 | 30 |  |
| PB8 | I/O/A | 24 | 43 | 40 |  |
| PB9 | I/O/A | 25 | 44 | 41 |  |
| PB10 | I/O/A | 26 | 45 | 42 |  |
| PB11 | I/O/A | 27 | 46 | 43 |  |
| PB12 | I/O | - | 62 | - |  |
| PB13 | I/O | - | 63 | - |  |
| PB14 | I/O | - | 64 | - |  |
| PB15 | I/O | - | 65 | - |  |
| PC0 | I/O/A | - | 6 | 5 |  |
| PC1 | I/O/A | - | 7 | 6 |  |
| PC2 | I/O/A | - | 8 | 7 |  |
| PC3 | I/O/A | - | 9 | 8 |  |
| PC4 | I/O/A | 4 | 10 | 9 |  |
| PC5 | I/O/A | 5 | 11 | 10 |  |
| PC6 | I/O/A | 6 | 12 | 11 |  |
| PC7 | I/O/A | 7 | 13 | 12 |  |
| PC8 | I/O/A | 22 | 34 | 31 |  |
| PC9 | I/O/A | 23 | 35 | 32 |  |
| PC10 | I/O/A | - | 36 | 33 |  |
| PC11 | I/O/A | - | 37 | 34 |  |
| PC12 | I/O/A | - | 39 | 36 |  |
| PC13 | I/O/A | - | 40 | 37 |  |
| PC14 | I/O/A | - | 41 | 38 |  |
| PC15 | I/O/A | - | 42 | 39 |  |
| PD2 | I/O | 3 | 3 | - |  |
| PD3 | I/O | 38 | 66 | 58 |  |
| PD4 | I/O/A | 39 | 67 | 59 |  |
| PD5 | I/O/A | 40 | 68 | 60 |  |
| PD6 | I/O/A | 41 | 69 | 61 |  |
| PD7 | I/O/A | 42 | 70 | 62 |  |
| PD8 | I/O/A | - | 47 | 44 |  |
| PD9 | I/O/A | - | 48 | 45 |  |
| PD10 | I/O/A | - | 49 | 46 |  |
| PD11 | I/O/A | - | 50 | 47 |  |
| PD12 | I/O/A | 28 | 51 | 48 |  |
| PD13 | I/O/A | 29 | 52 | 49 |  |
| PD14 | I/O/A | - | 4 | 3 |  |
| PD15 | I/O/A | - | 5 | 4 |  |
| SSRXA | USB | 47 | 75 | 67 |  |
| SSRXB | USB | 46 | 74 | 66 |  |
| SSTXA | USB | 44 | 72 | 64 |  |
| SSTXB | USB | 43 | 71 | 63 |  |
| VDD | P | 48 | 17/38/58/76 | 35/68 |  |
| VDDA | P | 9 | 16 | 14 |  |
| VDDK | P | 45 | 73 | 65 |  |
| VREF+ | P | 8 | 15 | 13 |  |
| VREF- | P | - | 14 | - |  |
| VSS | P | EP | EP | EP |  |
| XI | I/A | 1 | 1 | 1 |  |
| XO | O/A | 2 | 2 | 2 |  |

<details><summary><b>CH32X315 alternate functions</b></summary>

| Pad | default | af-0 | af-1 | af-2 | af-3 | af-4 | af-5 | af-6 | af-7 |
|---|---|---|---|---|---|---|---|---|---|
| PA0 | ADC4_IN10 | - | - | - | I2C1_SCL | - | - | TIM1_CH1N | TIM4_ETR |
| PA1 | ADC4_IN11 | - | - | - | I2C1_SDA | - | - | TIM1_CH2N | - |
| PA2 | ADC1_IN0 | - | - | - | - | - | - | TIM1_CH3N | - |
| PA3 | ADC1_IN1 | - | USART2_CK | - | - | - | - | - | - |
| PA4 | ADC1_IN2 | - | USART2_TX | - | - | SPI1_SCS | - | TIM2_CH1_ETR | - |
| PA5 | ADC1_IN3 | - | USART2_RX | - | - | SPI1_SCK | - | TIM2_CH2 | - |
| PA6 | ADC1_IN4 | - | USART2_CTS | - | - | SPI1_MOSI | - | TIM2_CH3 | - |
| PA7 | ADC1_IN5 | - | USART2_RTS | - | - | SPI1_MISO | - | TIM2_CH4 | - |
| PA8 | ADC3_IN8 | - | USART4_TX | - | I2C1_SCL | - | - | TIM1_CH2N | - |
| PA9 | ADC3_IN9 | - | USART4_RX | - | I2C1_SDA | - | - | TIM1_CH3N | - |
| PA10 | - | - | USART1_RX | - | - | - | ADCS0 | TIM1_CH1 | - |
| PA11 | - | - | USART1_TX | - | I2C2_SCL | - | ADCS1 | TIM1_CH2 | - |
| PA12 | - | - | USART1_RX | - | I2C2_SDA | SPI1_SCS | ADCS2 | TIM1_CH3 | - |
| PA13 | SWDIO, SWIO | - | USART3_TX | USART2_RX | I2C1_SDA | SPI1_SCK | - | TIM1_CH1N | - |
| PA14 | SWCLK | - | USART3_RX | USART2_TX | I2C1_SCL | SPI1_MOSI | - | TIM1_CH2N | - |
| PA15 | - | MCO | - | - | - | SPI1_MISO | ARGB_TX | TIM1_CH3N | TIM3_CH4 |
| PB0 | ADC1_IN6 | - | - | - | - | SPI1_SCS | - | - | - |
| PB1 | ADC1_IN7 | - | - | - | - | SPI1_SCK | - | - | - |
| PB2 | ADC1_IN8 | - | - | - | - | SPI1_MOSI | - | - | - |
| PB3 | ADC1_IN9 | - | - | - | - | SPI1_MISO | - | - | - |
| PB4 | ADC1_IN10 | - | - | - | - | SPI2_SCS | - | TIM2_CH1_ETR | - |
| PB5 | ADC1_IN11 | - | - | - | - | SPI2_SCK | - | TIM2_CH2 | - |
| PB6 | ADC2_IN0 | - | USART3_CTS | - | - | SPI2_MOSI | - | TIM2_CH3 | - |
| PB7 | ADC2_IN1 | - | USART3_RTS | - | - | SPI2_MISO | - | TIM2_CH4 | - |
| PB8 | ADC2_IN10 | - | - | - | - | - | - | TIM1_CH1 | - |
| PB9 | ADC2_IN11 | - | - | - | I2C2_SCL | - | - | TIM1_CH2 | - |
| PB10 | ADC3_IN0 | - | - | - | I2C2_SDA | - | - | TIM1_CH3 | - |
| PB11 | ADC3_IN1 | - | - | - | - | - | - | TIM1_CH4 | - |
| PB12 | - | - | USART4_TX | - | - | SPI2_SCS | - | - | - |
| PB13 | - | - | USART4_RX | - | - | SPI2_SCK | - | - | - |
| PB14 | - | - | - | - | I2C1_SCL | SPI2_MOSI | - | - | - |
| PB15 | - | - | - | - | I2C1_SDA | SPI2_MISO | - | - | - |
| PC0 | ADC4_IN2 | - | - | - | - | - | - | - | - |
| PC1 | ADC4_IN3 | - | - | - | - | - | - | - | - |
| PC2 | ADC4_IN4 | - | - | - | - | - | - | - | - |
| PC3 | ADC4_IN5 | - | USART1_CK | - | - | - | - | TIM1_ETR | - |
| PC4 | ADC4_IN6 | - | USART1_TX | - | - | SPI3_SCS | - | TIM1_CH1 | TIM4_CH1 |
| PC5 | ADC4_IN7 | - | USART1_RX | - | - | SPI3_SCK | - | TIM1_CH2 | TIM4_CH2 |
| PC6 | ADC4_IN8 | - | USART1_CTS | - | - | SPI3_MOSI | - | TIM1_CH3 | TIM4_CH3 |
| PC7 | ADC4_IN9 | - | USART1_RTS | - | - | SPI3_MISO | - | TIM1_CH4 | TIM4_CH4 |
| PC8 | ADC2_IN2 | RTC | USART3_TX | - | - | SPI3_SCS | - | - | TIM3_CH1 |
| PC9 | ADC2_IN3 | - | USART3_RX | - | - | SPI3_SCK | - | - | TIM3_CH2 |
| PC10 | ADC2_IN4 | - | USART3_CK | - | I2C2_SCL | SPI3_MOSI | - | - | TIM3_CH3 |
| PC11 | ADC2_IN5 | - | - | - | I2C2_SDA | SPI3_MISO | - | - | TIM3_CH4 |
| PC12 | ADC2_IN6 | - | USART2_TX | - | - | - | - | - | TIM3_ETR |
| PC13 | ADC2_IN7 | - | USART2_RX | - | - | - | - | - | - |
| PC14 | ADC2_IN8 | - | - | - | I2C1_SCL | - | - | - | - |
| PC15 | ADC2_IN9 | - | - | - | I2C1_SDA | - | - | - | - |
| PD2 | NRST | - | - | - | - | SPI1_MOSI | - | - | - |
| PD3 | - | - | - | - | - | SPI1_MISO | ARGB_TX | TIM1_BKIN | TIM3_CH1 |
| PD4 | ADC3_IN10 | - | USART1_TX | CC1 | I2C1_SCL | - | ARGB_TX | TIM1_CH4 | TIM3_CH2 |
| PD5 | ADC3_IN11 | - | USART1_RX | CC2 | I2C1_SDA | - | - | - | TIM3_CH3 |
| PD6 | USBHS_DM | - | USART2_TX | - | I2C2_SCL | - | - | - | - |
| PD7 | USBHS_DP | - | USART2_RX | - | I2C2_SDA | - | - | - | - |
| PD8 | ADC3_IN2 | - | USART1_TX | - | - | - | - | - | - |
| PD9 | ADC3_IN3 | - | USART1_RX | - | - | - | - | - | - |
| PD10 | ADC3_IN4 | - | - | - | - | SPI3_SCS | - | - | TIM4_CH1 |
| PD11 | ADC3_IN5 | - | USART4_CK | - | - | SPI3_SCK | - | - | TIM4_CH2 |
| PD12 | ADC3_IN6 | - | USART4_CTS | - | - | SPI3_MOSI | - | - | TIM4_CH3 |
| PD13 | ADC3_IN7 | - | USART4_RTS | - | - | SPI3_MISO | - | TIM1_CH1N | TIM4_CH4 |
| PD14 | ADC4_IN0 | - | - | - | - | SPI1_MISO | - | - | - |
| PD15 | ADC4_IN1 | - | - | - | - | - | - | - | - |
| VDD | DD, Main V | - | - | - | - | - | - | - | - |
| XI | PD0, PD0（2） | - | USART1_RX | - | I2C2_SCL | SPI1_SCS | - | - | - |
| XO | PD1, PD1（2） | - | USART1_TX | - | I2C2_SDA | SPI1_SCK | - | - | - |

</details>

---
Data: [ch32-device-data](https://github.com/ch32-riscv-ug/ch32-device-data) (tables/ -- each value carries its evidence and confidence there).
