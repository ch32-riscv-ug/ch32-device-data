# CH32 Device Data

[English](README.md)

CH32のexact orderable SKUを、出典と検証状態を含めて機械可読に記述するための独立データリポジトリです。

> [!IMPORTANT]
> 現在のschema version `0.1-draft`はQ-011を検討するための提案であり、確定仕様ではありません。
> `devices/`のrecordもArduinoコアの対応宣言ではありません。
> このリポジトリをdevice databaseの正本としますが、schema自体はまだ草案です。

## 構成

- `schemas/device.schema.json`: exact SKU、CPU、memory、package、peripheral、pin、出典のschema草案
- `devices/*.json`: schemaを評価するための代表SKUデータ
- `tools/validate.py`: JSON Schemaと追加の整合性規則を検査するvalidator
- `tools/extract_selectors.py`、`tools/extract_pins.py`、`tools/extract_remap.py`、`tools/extract_registers.py`: EVTヘッダ・datasheet・RMから候補を抽出するreview支援tool。recordは書き換えない
- `tools/extract_remap_fields.py`: EVTの`GPIO_PinRemapConfig()`を**ホスト用にコンパイルして実行し**、remap fieldの位置と経路の列挙値を観測する。文書ではなく挙動を読む唯一のtoolで、**host Cコンパイラ（`cc`）が必要**。EVTはその場で読むだけでrepositoryへ複製しない
- `tools/build_candidate.py`: 上記4 toolの出力を1つの候補へ結合する
- `tools/signal_vocabulary.py`: 資料ごとに違うsignal名・field名の綴りを1つの読みへ揃える語彙規則。上の抽出toolと結合toolはすべてここを通す。`uv run tools/signal_vocabulary.py --tables tables`で規則一覧とremap_routes.csvに対する当たり具合を出す
- `tools/extract_clock_tree.py` / `tools/build_clock.py`: EVTの`system_ch32*.c`から
  クロック設定（発振器・各ドメイン周波数・分周・PLL・flash latency・RCC外のレジスタ）を
  静的に読み、`tables/clock_configs.csv`・`clock_prescalers.csv`・`clock_sources.csv`・
  `clock_symbols.csv`・`clock_init.csv`へ落とす。`clock_init.csv`だけは順序を持つ——
  `SystemInit`はベタのhexで書かれた分岐の無い一直線で、順序が方針ではなく転記だから
- `tools/extract_addresses.py`: device headerのbase定数の連鎖とstructのメンバー
  オフセットから`BLOCK->REGISTER`の絶対アドレスを解く。レジスタ名から場所は決まらない
  （CH32V205だけEXTENのregisterを`CTLR0`と呼び、CH32X315はEXTENを別の番地に置く）
- `tools/build_systick.py`: `core_riscv.h`からSysTickのregister配置を取り
  `tables/systick.csv`にする。**CH32V103だけ配置が違い**、`CMP`の位置を他family
  と同じだと思うと`millis()`が動かない
- `tools/build_pin_alternate.py`: **AFIO remapを持たない3 family**（V205・X315・H417）の
  AF番号の書き込み先を`tables/pin_alternate.csv`にする。`pin_functions`の`af-N`が
  4448行あるのにNをどこに書くか誰も言っていなかった。4bitずつという規則は
  EVTの`GPIO_PinAFConfig()`の式を読んで確かめる
- `tools/build_interrupts.py`: 割り込みベクタ表を`tables/interrupts.csv`にする。
  **出所はreference manualではなくEVTのdevice header**で、`IRQn_Type`列挙が
  番号・名前・説明を全部持っている。variantで番号が入れ替わる（CH32V20xの61番は
  `_D6`で`UART4`、`_D8`で`ETH`）ので`#if`の条件を`condition`列に持つ
- `tools/build_memory_map.py`: アドレス空間の地図を`tables/memory_map.csv`にする。
  EVTの`*_BASE`定数から。**FLASHの番地は2つある**——ヘッダーの`FLASH_BASE`と
  linker scriptの`ORIGIN`は別の窓口を指すので両方持つ
- `tools/build_features.py`: familyが持つ周辺の一覧を`tables/features.csv`にする。
  比較表は「シリーズ内で差がある列」しか持たないので機能フラグを作れない。
  **機能説明章の節見出し**を採る。節番号は言語に依らないので中英が厳密に対応する
- `tools/build_memory.py`: FLASH/SRAMの境界がoption byteで動くpartの組合せを
  `tables/memory_configs.csv`にする。`products.csv`の`flash_bytes`/`sram_bytes`は
  datasheetの比較表が載せる1組しか言わないので、**振り直せること自体がそこから
  読めない**。reference manualが符号と適用先を、EVTの`Link.ld`が組合せを言い、
  両者を突き合わせる。**「出荷時の組」と言えるものは無い**——RMは復位値を`x`と
  しか書かず、EVTの例題も1組に揃っていない
- `tools/build_link_firmware.py`: WCHが配るWCH-Link系デバッガのファームウェア
  一覧を`tables/link_firmware.csv`にする。バイナリは置かず指紋と取得元だけ。
  **版番号は未解決**（[docs/link-firmware-survey.ja.md](docs/link-firmware-survey.ja.md)）
- `tools/build_evt_variants.py`: device headerのコメントから型番→コンパイル時macro
  （`CH32V20x_D8W`等）を取り`tables/evt_variants.csv`にする。macroを設定しないと
  既定のvariantで黙って通るので、どの型番がどれかを表にしておく
- `tools/crosscheck_ch32data.py`: [ch32-rs/ch32-data](https://github.com/ch32-rs/ch32-data)と
  AFIO remap fieldを突き合わせる。**上流ではなく検算相手**——向こうは
  CH32V205/V407/V467/X305/X315/M030/M103のレジスタ定義を持たないため
- `candidates/*.json`: 全SKUの機械抽出結果。未reviewで、schemaにも準拠しない
- `docs/schema-notes.ja.md`: schema調査、確認済みの構造差、未決定事項
- `docs/extraction-survey.ja.md`: 機械抽出できる範囲の実測と、資料側の崩れの一覧
- `docs/handoff.ja.md`: 作業状態、既知の資料矛盾、再開手順

## データの境界

- recordの単位は注文可能な正確な型番とする
- WCHのseries名と、コア内部で共有する実装familyは同一と仮定しない
- packageのbond-out差をdevice recordに保持する
- pin routeは人間向けのroute名に加え、`route_selectors`でcontroller、register、field、bit位置、有効値、reset値を定義し、各functionの`selection`からraw selector値とともに参照する。AFIO remap以外のOPA入力選択などにも同じ構造を使う。bit位置はLSB順の`bits`で表し、**bitごとにregister名を持つ**——CH32L103やCH32V30xではselectorがPCFR1とPCFR2にまたがり、PCFR1だけを書くとエラーにならずに別の経路が選ばれるため。bit幅内でもreservedの値はvalidatorが拒否する
- board固有のLED、connector、clock、upload設定はdevice dataへ入れない
- Arduino core固有のFQBN、variant、build flagはsource dataへ入れず、consumer側の生成物にする
- compilerの`-march`/`-mabi`はdatasheetのISA表記から推測せず、toolchain認定後に追加する
- `coverage`により未採取、部分採取、採取完了を区別し、物理package pinとpin functionも別々に評価する
- `verification`により領域ごとに単一資料からの採取、相互確認、実機確認を区別する
- 対応tierは実測後に別のsupport/board manifestで扱い、このrecordだけから対応を宣言しない

## 出典

`sources`には公式download URL、文書版、英語・中国語、mirror repositoryのcommit、対象fileのSHA-256を記録できます。`hash_scope`でdownload artifact全体とarchive内の個別source fileを区別します。`evidence`は値を確認したtable/sectionへ戻るためのlocatorです。

兄弟repositoryは一次資料のmirrorとして参照します。EVTや旧Arduinoコアのsourceをこのrepositoryへ自動的にコピーしません。

## 検証

```sh
python3 tools/validate.py
```

`jsonschema` packageが利用可能ならJSON Schema全体を検査します。なくても標準libraryだけで、ID、出典参照、pin coverageなどの追加規則を検査します。

抽出toolは外部packageを使うため、`pyproject.toml`と`uv.lock`で固定したuv経由で実行します。抽出できる範囲と資料側の崩れは[抽出可能性の事前調査](docs/extraction-survey.ja.md)にまとめています。

抽出toolのうち`extract_remap_fields.py`だけはhost Cコンパイラを使います（EVTの関数を動かすため）。
`cc`が環境にあれば追加の用意は不要です。ローカルへtoolchainを置く場合は`.tools/`（gitignore済み）へ。

```sh
uv run tools/extract_remap_fields.py --mirrors <EVT cloneの親> --compare tables
uv run tools/crosscheck_ch32data.py --ch32-data <ch32-dataのclone>
```

reference manualは**両言語版を読んで和を取ります**。中国語版のほうが新しく、
内容も多いためです（CH32X035はregister field 876→895件、CH32V407のRMは中国語版にしか無い）。
scalarが食い違ったときは後に読んだ中国語版を採り、noteに残します。

生成した表そのものの整合は、資料もEVTも要らずに検査できます。

```sh
uv run tools/check_tables.py                      # 表どうしの参照と、remap表の内部整合
uv run tools/signal_vocabulary.py --tables tables # signal名の語彙規則と、その当たり具合
```

```sh
uv run tools/extract_selectors.py <EVT>/Peripheral/inc/ch32xxx.h --compare devices/<id>.json
uv run tools/extract_pins.py <datasheet>.PDF --package TSSOP20 --compare devices/<id>.json
uv run tools/extract_remap.py <manual>.PDF --compare devices/<id>.json
uv run tools/extract_registers.py <manual>.PDF --compare devices/<id>.json
```
