# Device data schema調査ノート

文書状態: 提案

配置状態: `ch32-device-data`を正本とする。schema version `0.1-draft`は未確定。

## 目的

ArduinoCore-CH32のQ-011にあるdevice/board manifest形式を決める前に、構造の異なるCH32製品を同じschemaで表現できるか確認します。schemaは[`schemas/device.schema.json`](../schemas/device.schema.json)、sample recordは[`devices/`](../devices/)にあります。

この調査は対応SKUの決定ではありません。特にCH32V407とCH32H417は、大規模deviceを将来追加してもschemaを壊さないためのstress sampleです。

## 確認済みの構造差

英語datasheetの製品比較表を確認した結果、少なくとも次を単純なfamily共通値にできません。

- CH32V003とCH32V006は同じV00xに見えても、vendor core、ISA表記、memory、peripheral構成が異なる
- CH32M030はpackage SKUによりhalf-bridge、GPIO、MV/HV I/O、OPA/CMP、USB PDのCC構成、内蔵Rdが異なる
- CH32X035はUSB PD、USBFS、programmable protocol I/Oを持ち、一般的なGPIO alternate functionだけでは能力を表せない
- CH32V407は総program memory、zero-wait Flash、構成変更可能なzero-wait SRAMを区別する必要がある
- CH32H417はdual-coreで、core別の通常/条件付きperformance clockとITCM/DTCM/shared memoryを持つ
- packageのpin数とGPIO数は異なり、電源・reset・analog専用pinも含めたbond-out表が必要である

## Schema草案の判断

以下はまだADRで確定していない提案です。

- 正本recordはJSONとし、JSON Schemaで構造を検査する
- recordはexact orderable SKU単位とする
- WCHのseries名は事実として記録するが、内部実装familyは実装比較まで固定しない
- datasheetのISA表記は`isa_claim`へ原文どおり記録し、compilerの`-march`/`-mabi`へ自動変換しない
- memoryを単一のFlash/RAM値ではなくregion配列にする
- peripheral summaryとpackage pin/function表を分ける
- pin functionにはsignal、peripheral、routeと機械可読な`selection`条件を保持できるようにする
- route selectorはcontroller、register、field、bit位置、有効値、reset値を一度だけ定義し、各functionの`selection`がraw selector値とともに参照する。AFIO remapだけでなくOPA入力選択などにも使い、連続fieldとV003のI2C/USARTにある分散bit fieldの両方を表す。`1x0`のように複数値が同じ配置を選ぶ場合やreserved値も区別する
- source URL、mirror commit、file SHA-256、文書内locatorをrecordに含める
- `coverage`と`verification`を分け、空欄を「機能なし」と誤解させない
- source dataはArduino固有形式にせず、Arduino coreは固定versionを取得して必要なdescriptorを生成するconsumerとする案を検討する

## 現在のsample

| Record | Schema上の主な役割 | 対応宣言 |
|---|---|---|
| CH32V003F4P6 | RV32E、小容量、TSSOP20 | しない |
| CH32V006K8U7 | 新V00x、62K Flash、QFN32 | しない |
| CH32V103C8T6 | 標準的なRV32IMAC、LQFP48 | しない |
| CH32X035F8U6 | USB PD/USBFS/PIOC、QFN20 | しない |
| CH32M030C8T7 | motor/analog/PD、package依存能力 | しない |
| CH32M030C8U7 | MV/HV I/O、制御可能な内蔵Type-C Rd | しない |
| CH32V407VET6 | zero-wait memory、大規模peripheral | しない |
| CH32H417QEU6 | dual-core、分割memory、USB3 | しない |

現在は代表SKUでschemaをstress testしている段階です。

- CH32V003F4P6はTSSOP20の全20物理pinを採取し、18 GPIOと2 power pinの整合性を検査した
- CH32V003F4P6は公開pin function 110 entryを採取し、digital remapをRM Tables 7-8〜7-14とEVT GPIO定義で相互確認した。OPA selectorもRM Chapter 17/EVTと照合した。個々のADC channel padと実機は未確認だが、公開表に対するcoverageは`complete`
- CH32V003のI2C1/USART1 selectorは連続fieldではなく物理bit 1と22 / 2と21に分散するため、LSB順の`bits`で表現した
- CH32V003 RMの`ADC_ETRGINJ_RM` register説明はregular triggerのPD3/PC2対応を誤って繰り返している。datasheet Table 2-2とRM Table 7-13が一致する`0=PD1`、`1=PA2`を採用した
- CH32X035F8U6はQFN20のlead 1〜20とexposed GND padを採取し、19 GPIO、CC1/CC2、USB D-/D+、PIOC、debug pinを表現した
- CH32X035F8U6はQFN20にbond-outされたremap functionを採取し、datasheet Table 2-3、RM Section 8.3.2.1、EVT GPIO定義を相互確認した。複数のraw selector値が同じ配置を選ぶ場合も保持している
- CH32M030C8T7はLQFP48の全48 lead、35 GPIO、公開pin functionを採取した。8本のMV pre-drive端子、固定pull-down、output-only、4組のgate-driver電源、high-voltage-resistant CC端子を表現し、124 selector経路を収録した。RMが列挙する120 digital routeは期待値との機械比較で過不足0、datasheetだけが`TIM3_CH1_ETR`と明記する4 routeは`TIM3_CH1`と`TIM3_ETR`へ分けて保持した
- CH32M030C8T7/C8U7の比較からMV/HV I/O数をpackage属性として保持し、C8U7だけにあるPA0/PA1の制御可能な約5.1 kΩ Rdを内蔵componentとして記録した
- CH32M030 RM Table 6-15の`ADC_ETRGIN_RM`対応は、datasheet Table 2-1、同RMのregister説明/reset値、EVT実装と逆である。後者3資料が一致する`0=PA14`、`1=PB6`をrecordへ採用し、Table 6-15を文書誤り候補として残した
- 他のSKUのpin一覧は未採取、全SKUのperipheralは部分採取

## 今回見つかった未決定事項

以下は実データ入力によって見つかったschema上の論点であり、まだ決定ではありません。

- signal名が資料・series間で`T1C1`/`TIM1_CH1`、`UART`/`USART`のように異なる。検索・code生成用のcanonical IDとvendor表記を分離するか
- remap selectorはsiliconで共通、bond-outはpackage固有である。正本をsilicon定義・package定義・exact SKU合成へ正規化し、現在のflat exact-SKU recordを生成物にするか
- default routeでもselector値0を明示すべきか。M030の`ADC_ETRGIN_RM`のような資料矛盾を扱うには有用だが、全functionに付けるとrecordが大きくなる
- pin function全体のverificationには、digital remapは相互確認済み、analogは単一資料、実機は未確認という混在がある。現在の領域単位より細かいverificationを持つか
- CH32V003の`TIM1_1_RM`はTIM1_CH1をpackage pinではなく内部LSIへ接続する。pin databaseとは別に内部signal routeを表現するか

これらを決めるまではschema versionを`0.1-draft`のままとします。

## 次の検証

1. CH32V003F4P6の個々のADC channel padとsystem functionをRM/実機で確認する
2. CH32V003F4P6のinterrupt、DMA、clock/reset情報をdevice recordと分離すべきか検討する
3. CH32M030の`ADC_ETRGIN_RM`とpackage固有のelectrical behaviorを実機確認する
4. 最初の実機boardが決まった後に、deviceと分離したboard schemaを作る
5. X035/M030のpin構造をreviewした時点でQ-011をADR候補にする
6. schemaを固めた後、consumer向けreleaseとversion固定方法を試作する

## 他repositoryとの境界

device databaseはArduino core専用ではなく、複数のlibrary、tool、文書生成から利用できる正本として、このrepositoryに配置します。

既存`ch32_riscv_tools/PinAlternateFunctions`は手動作成された検索・表示用データです。現状はseries単位で、exact SKU/package bond-out、source revision/hash、coverageを持たないため、検証根拠や自動取込元にはしません。将来はこのrepositoryの固定releaseから生成するviewer候補として扱います。

pin表の抽出はPDF layoutに依存するため、完全自動変換を正本へ直接mergeしません。抽出器は候補JSONと出典locatorを生成し、schema validationと人間のreviewを通す方針が妥当です。
