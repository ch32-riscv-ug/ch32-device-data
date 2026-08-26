# WCH-Link 系デバッガのファームウェア調査

**目的**: 「手元のLinkが古いから更新する」の判断材料を表で出す。
古いファームウェアだと動作がおかしいことがあるため。

**現状**: ファイルの同定・更新手段・取得の自動化はできた。
**「そのファームウェアの版番号」が確定できていないので、目的はまだ果たせていない。**
`evidence/link_firmware.csv`は指紋（sha256）としては使えるが、
「あなたのは古い」を言うには実機の申告値との対応が要る。

## 取得元

| 配布物 | URL | 中身 |
|---|---|---|
| WCH-LinkUtility.ZIP | `https://file.wch.cn/download/file?id=418`（ページは`https://www.wch.cn/downloads/wch-linkutility_zip.html`） | Windows用ユーティリティ＋`Firmware_Link/` |
| MounRiver Studio Linux | WCH配布のtar.xz | 同じ`Firmware_Link/`を`resources/app/resources/linux/components/WCH/Others/`以下に同梱 |

`tools/build_link_firmware.py`がどちらからでも読める（`--zip`にZIPか展開済み
ディレクトリを渡す。無指定ならURLから取得）。

## ファイルの同定

配布される`.bin`は10本。**先頭命令で命令セットが判る**ので、MCUの割り当ては
推測ではない——`02`は8051の`LJMP`、`6f`はRISC-Vの`jal`。役割は
WCH-Link User Manual第6章の対応（p.20が①〜⑩として同じ10本を挙げる）。

| デバイス | MCU | モード | 役割 | ファイル | サイズ |
|---|---|---|---|---|---:|
| WCH-Link | CH549 | RISC-V | offline | `FIRMWARE_CH549.bin` | 42712 |
| WCH-Link | CH549 | RISC-V | iap | `WCH-Link_APP_IAP_RV.bin` | 45784 |
| WCH-Link | CH549 | ARM | offline | `FIRMWARE_DAP_CH549.bin` | 24662 |
| WCH-Link | CH549 | ARM | iap | `WCH-Link_APP_IAP_ARM.bin` | 27734 |
| **WCH-LinkE** | **CH32V305** | | offline | `FIRMWARE_CH32V305.bin` | 109544 |
| **WCH-LinkE** | **CH32V305** | | iap | `WCH-LinkE-APP-IAP.bin` | 117736 |
| WCH-LinkW | CH32V208 | | offline | `FIRMWARE_CH32V208.bin` | 114264 |
| WCH-LinkW | CH32V208 | | iap | `WCH-LinkW-APP-IAP.bin` | 122456 |
| WCH-DAPLink | CH32V203 | | offline | `FIRMWARE_CH32V203.bin` | 28100 |
| WCH-DAPLink | CH32V203 | | iap | `WCH-DAPLink_APP_IAP.bin` | 36292 |

`FIRMWARE_*`がBOOTモード（オフライン）用、`*APP_IAP*`がIAPモード経由の更新用。
**LinkEのMCUはCH32V305だが、プロトコル上の型番は`CH32V307`を名乗る**
（`minichlink`のtype 2が`CH32V307`、type 18が`LinkE`）。

**Windows版ZIPとMRS Linux版で10本すべてsha256が一致する**（2026-08-22実測）。
つまり配布経路が違うだけで中身は同じ。

## 版番号が確定できない（未解決）

版を名乗るものが3つあり、意味が違う。

| 出所 | Windows ZIP | MRS Linux | 判断 |
|---|---|---|---|
| `firmware_version.txt` | `v40` | `v43` | **中身が同一なのに違う** → 配布パッケージの版 |
| `sub_manifest.json` | 無し | パッケージ`v43` / 既定セット`v41` | 同上 |
| `wchlink.wcfg` | `CH549Ver_RV=32` `CH549Ver_ARM=31` `CH32V307Ver=42` `CH32V208Ver=34` `CH32V203Ver=32` | **完全に同じ** | 両配布で一致するので、これがファームウェア側の版 |

一方、**Linkが実機でUSBに申告する版は`major.minor`**。
`81 0d 01 01`への応答のbyte3・4で、`ch32fun/minichlink/pgm-wch-linke.c:386`が
`%d.%d`で表示する（応答例`82 0d 04 02 08 02 00`→「2.8」）。
WCH-Link User Manual p.19も「firmware version v2.8 and above」と書くので、
実機側は`2.x`系列で間違いない。

**`wchlink.wcfg`の数がこの`major.minor`のどれに当たるかが決まらない。**

- `CH549Ver_RV=32`を`major*10+minor`と読むと2.12、`CH549Ver_ARM=31`なら2.11で辻褄が合う
- しかし同じ読みだと`CH32V307Ver=42`は**2.22**になり、手元のLinkEが申告する2.12と合わない
- `42`を`4.2`と読む余地もあるが、それだと`2.x`系列と繋がらない

### 試して駄目だった方法

**バイナリから版を読む**。ファームウェアが応答テンプレート
（`82 0d 04 <major> <minor> <type> 00`）を定数で持っていれば取れるはずだったが、
10本すべてに`82 0d 04`の並びは無い。実行時に組み立てている。
`\x02<minor><type>`の三つ組を総当たりすると偶然の一致が大量に出るだけで、
判定に使えない。

**配布ページから読む**。`wch-linkutility_zip.html`はJavaScript生成で、
静的HTMLに版情報が無い。

### 次に試すこと（時間ができたら）

**実機で1回対応させるのが一番安い。** LinkEを更新する前後で`minichlink`を実行し、
表示される`LinkE version X.Y`を控える。`CH32V307Ver=42`が何に対応するかが
1回わかれば固定できる。基板は手元にある。

それが済んだら`link_firmware.csv`に`reported_version`列を足し、
`curated/`に実測値を置いて結合する形にする。

他に試せる線:

- 過去のWCH-LinkUtilityを複数版取得して`wchlink.wcfg`の数の推移を見る（`file?id=`の別ID）
- MRSのElectronアプリ側の更新ロジック（`resources/app`のJS）が版を表示する箇所を読む。
  IAPプロトコルの実装も同じ場所にあるはずなので、OSS実装の手がかりにもなる

## 更新手段

**Windows必須ではない。** MounRiver StudioのLinux版が同じファームウェアを同梱し、
本体がIAP更新を実行する（manual 6.1）。単体のCLI更新ツールは同梱されておらず、
更新ロジックはElectronアプリ側にある（OpenOCDはWCH版が別途同梱されているが、
これはターゲットを焼くためのもので、Link自身の更新には使われない）。

| 経路 | WCH-Link (CH549) | WCH-LinkE (CH32V305) |
|---|---|---|
| MounRiver Studio Linux（純正） | ○ IAP更新 | ○ IAP更新 |
| WCH-LinkUtility | ○（Windowsのみ） | ○（Windowsのみ） |
| `wchisp`（OSS）＋BOOTモード | ○ USB/UART ISP。READMEの動作確認済みに`CH549`あり | **✗** |
| もう1台のLinkから2線で焼く | — | ○ manual 6.3。`minichlink`/`wlink`/OpenOCDで代替できるはず（**未検証**） |

**LinkEはUSB ISPを持たない。** manual 6.5の注記が
「USB offline update is only supported by WCH-Link, WCH-DAPLink and WCH-LinkW」と
明記している。したがってIAP更新に失敗したときの復旧経路は2線経由だけで、
**LinkEはLinkより復旧リスクが高い**。

IAPモードへの入り方（manual 6.2〜6.3）: IAPボタンを長押ししたまま給電。
青LEDが点滅すればIAPモード。BOOTモード（manual 6.4〜6.5）はWCH-Linkの場合
J1短絡またはBOOTキー長押しで給電。

## バイナリを置かない理由

`evidence/link_firmware.csv`はsha256・サイズ・取得元URLだけを持ち、
**`.bin`自体はこのrepositoryに入れていない**。WCHのバイナリ再配布になり、
ライセンス条件が配布物に明示されていないため。`manifests/documents.json`が
文書のカタログを持つのと同じ扱いで、取得元を記録して各自が取る形にしている。
