# WCH-Link 系デバッガのファームウェア調査

**目的**: 「手元のLinkが古いから更新する」の判断材料を表で出す。
古いファームウェアだと動作がおかしいことがあるため。

**現状**: ファイルの同定・更新手段・取得の自動化はできた。
**2026-08-29 に解決。** `wchlink.wcfg` の数は `major*10 + minor`（major は観測した全個体で 2）で、`evidence/link_firmware.csv` の `reported_version` から「あなたのは古い」が言えるようになった。下の節の「解けなかった」は**当時の記録**として残す——読み自体は最初から正しく、否定した根拠にした LinkE が古かっただけだった。
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

## 版番号の読み方（2026-08-29 に解決）

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

### 答え: `major*10 + minor`（2026-08-29）

**最初の読みが正しかった。** 上で「`major*10+minor`だと`42`が2.22になり、手元の LinkE が
申告する 2.12 と合わない」と否定しているが、**その LinkE が古かっただけ**。
WCH-LinkUtility 3.00（6月付のファーム同梱）で強制更新した純正 LinkE は **2.22** を名乗る。

| wcfg | 版 | | wcfg | 版 |
|---|---|---|---|---|
| `CH549Ver_ARM=31` | 2.11 | | `CH32V208Ver=34` | 2.14 |
| `CH549Ver_RV=32` | 2.12 | | `CH32V307Ver=42` | **2.22** |
| `CH32V203Ver=32` | 2.12 | | | |

`libmcuupdate.so` の `McuCompiler_GetDeviceVersion` が応答から数を作る式は閾値で2通りある:

```
eax = major<<4 + minor ; cmp eax,0x2f ; jg 枝B
枝A:  major*10 + minor          （10進）
枝B:  major*16 + minor - 12     （16進-12）
```

**major=2 では両者が一致する**（枝A=20+minor、枝B=32+minor-12=20+minor）ので実質 `20+minor`。
2.22 は 54>0x2f で枝Bに入り `54-12=42`。

**MounRiver Studio の表示関数は当てにしない。** `extension.js` の `w(e)`
（`12+e` を16進2桁にして上下の桁を major/minor と読む）は **minor が16以上だと壊れ**、
42 を「3.6」と表示する。比較の両辺が同じ関数を通るので WCH の UI 上は破綻しないが、
表に載せる値としては使えない。

### 更新のしかたと落とし穴（WCH-LinkUtility）

**繋いだだけでは更新ダイアログが出ない。** ある程度新しいファームが載っていると
黙って通るので、更新するには **`Synchronize Current WCH-Link Firmware`** を明示的に
選んで強制更新する必要がある。

**複数の LinkE を挿していると、選択中のものではなく一覧の一番上が更新される。**
UI 上どれを選んでいても対象が変わらないので、「更新したのに版が上がらない」が起きる。
実際、この調査で 2.12 のままだった2個体はこれに当たっていた可能性が高い
（`CH32V307Ver=42` が LinkE のものではないのでは、と一度誤った結論に傾いた原因）。

運用としては:

1. **更新する LinkE だけを挿す**（他は抜く）
2. `Synchronize Current WCH-Link Firmware` で強制更新
3. `uv run tools/read_link_version.py` で版が上がったことを確かめる

3 を挟まないと、更新できたかどうかが分からない。**版が上がっていなければ別の個体を
更新している**と考えてよい。

### 実機5通り（`tools/read_link_version.py`）

`81 0d 01 01` を投げるだけでターゲットには触らない。RV は EP 0x01/0x81、
DAP は 0x02/0x83 で、**問い合わせも応答も同じ形**。

| 個体 | type | モード | 応答 | 版 |
|---|---|---|---|---|
| `434A124C5596` | 1（CH549） | RV | `82 0d 04 02 0c 01 00` | 2.12 |
| `F90E8F067DFD` | 18（LinkE #1） | RV | `82 0d 04 02 0c 12 00` | 2.12（古い） |
| `FC928F068181` | 18（LinkE #2） | DAP | `82 0d 04 02 0c 12 01` | 2.12（古い） |
| `FC928F068181` | 18（**同一個体**） | RV | `82 0d 04 02 0c 12 00` | 2.12 |
| `0A388F068F0B` | 18（LinkE #3） | RV | `82 0d 04 02 16 12 00` | **2.22** |

CH549 は `CH549Ver_RV=32`=2.12 と一致。#3（最新版で強制更新）は `CH32V307Ver=42`=2.22 と一致。
**`CH32V305Ver`→`CH32V307Ver` の読み替えは正しかった。**

分かったついで: 応答6バイト目は device 型（1=CH549 / 18=LinkE。`minichlink` の分岐とも
`extension.js` の `g()` とも一致）、7バイト目はモード（RV=00 / DAP=01）。
**モードを変えても版もシリアルも変わらない**（同一個体で確認）。変わるのは
PID（`8010`↔`8012`）と EP だけ。

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
