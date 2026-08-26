# CH32 Device Data

[English](README.md)

WCHのCH32シリーズ（12 family・27 series・103型番）について、一次資料（datasheet 中英両版・
reference manual・EVT）から**機械抽出したCSV**と、そこから各familyリポジトリのREADMEを
生成するtoolを置く独立データリポジトリです。表は3つに分かれます（[docs/data-layout.ja.md](docs/data-layout.ja.md)）:

| | 何か | 読む人 |
|---|---|---|
| [`catalog/`](catalog/README.ja.md) 目録 7表 | 何が存在し何と呼ぶか（family・series・型番・package・core・文書・mirror版） | 全表の鍵 |
| [`evidence/`](evidence/README.ja.md) 証拠 33表 | 資料は何と書いているか。**綴りは原典のまま**、行ごとに出所（`basis`）と確度（`confidence`） | 正しさを確かめる人 |
| [`index/`](index/README.ja.md) 索引 | 証拠から語彙で揃えて組み直した、**引くための表**。1表1ファイル。型番や機能で絞って見るのは viewer（`pins.html`）で | 利用者・generator |

> [!IMPORTANT]
> このリポジトリはArduinoコアの対応宣言ではありません。表に載っている型番＝対応、ではありません。

**どこから読むか**: 引くなら [index/README.ja.md](index/README.ja.md)、表の意味と列は
[evidence/README.ja.md](evidence/README.ja.md)、表ごとの信頼度は
[docs/table-reliability.ja.md](docs/table-reliability.ja.md)、作業の状態は [docs/worklist.ja.md](docs/worklist.ja.md)。

## 構成

- `catalog/`・`evidence/`・`index/`: 上の3区分の表。`#`列より左がデータ、右が出所と確度のメタ。`tools/paths.py` が置き場所を1箇所で決める
- `.cache/candidates/*.json`: 全型番の機械抽出結果（`build_all.py` の出力。commit しない。`build_pins`/`build_remap`/`build_tables` の入力）
- `curated/`: 人手で確認した少数の上書き（pin表の列見出し・エラッタ・series事実）
- `manifests/documents.json`: 取得すべき文書のカタログ。mirrorはここを読んで取得する（[manifests/README.ja.md](manifests/README.ja.md)）
- `tools/check_tables.py` / `tools/check_counts.py`: 表どうしの参照結合・書式・数の不変量の検査
- `tools/extract_selectors.py`、`tools/extract_pins.py`、`tools/extract_remap.py`、`tools/extract_registers.py`: EVTヘッダ・datasheet・RMから候補を抽出するtool
- `tools/extract_remap_fields.py`: EVTの`GPIO_PinRemapConfig()`を**ホスト用にコンパイルして実行し**、remap fieldの位置と経路の列挙値を観測する。文書ではなく挙動を読む唯一のtoolで、**host Cコンパイラ（`cc`）が必要**。EVTはその場で読むだけでrepositoryへ複製しない
- `tools/build_candidate.py`: 上記4 toolの出力を1つの候補へ結合する
- `tools/signal_vocabulary.py`: 資料ごとに違うsignal名・field名の綴りを1つの読みへ揃える語彙規則。上の抽出toolと結合toolはすべてここを通す。`uv run tools/signal_vocabulary.py --tables evidence`で規則一覧とremap_routes.csvに対する当たり具合を出す
- `tools/extract_clock_tree.py` / `tools/build_clock.py`: EVTの`system_ch32*.c`から
  クロック設定（発振器・各ドメイン周波数・分周・PLL・flash latency・RCC外のレジスタ）を
  静的に読み、`evidence/clock_configs.csv`・`clock_prescalers.csv`・`clock_sources.csv`・
  `clock_symbols.csv`・`clock_init.csv`へ落とす。`clock_init.csv`だけは順序を持つ——
  `SystemInit`はベタのhexで書かれた分岐の無い一直線で、順序が方針ではなく転記だから
- `tools/extract_addresses.py`: device headerのbase定数の連鎖とstructのメンバー
  オフセットから`BLOCK->REGISTER`の絶対アドレスを解く。レジスタ名から場所は決まらない
  （CH32V205だけEXTENのregisterを`CTLR0`と呼び、CH32X315はEXTENを別の番地に置く）
- `tools/build_systick.py`: `core_riscv.h`からSysTickのregister配置を取り
  `evidence/systick.csv`にする。**CH32V103だけ配置が違い**、`CMP`の位置を他family
  と同じだと思うと`millis()`が動かない
- `tools/build_pin_alternate.py`: **AFIO remapを持たない3 family**（V205・X315・H417）の
  AF番号の書き込み先を`evidence/pin_alternate.csv`にする。`pin_functions`の`af-N`が
  4448行あるのにNをどこに書くか誰も言っていなかった。4bitずつという規則は
  EVTの`GPIO_PinAFConfig()`の式を読んで確かめる
- `tools/build_interrupts.py`: 割り込みベクタ表を`evidence/interrupts.csv`にする。
  **出所はreference manualではなくEVTのdevice header**で、`IRQn_Type`列挙が
  番号・名前・説明を全部持っている。variantで番号が入れ替わる（CH32V20xの61番は
  `_D6`で`UART4`、`_D8`で`ETH`）ので`#if`の条件を`condition`列に持つ
- `tools/build_memory_map.py`: アドレス空間の地図を`evidence/memory_map.csv`にする。
  EVTの`*_BASE`定数から。**FLASHの番地は2つある**——ヘッダーの`FLASH_BASE`と
  linker scriptの`ORIGIN`は別の窓口を指すので両方持つ
- `tools/build_features.py`: familyが持つ周辺の一覧を`evidence/features.csv`にする。
  比較表は「シリーズ内で差がある列」しか持たないので機能フラグを作れない。
  **機能説明章の節見出し**を採る。節番号は言語に依らないので中英が厳密に対応する
- `tools/build_memory.py`: FLASH/SRAMの境界がoption byteで動くpartの組合せを
  `evidence/memory_configs.csv`にする。`products.csv`の`flash_bytes`/`sram_bytes`は
  datasheetの比較表が載せる1組しか言わないので、**振り直せること自体がそこから
  読めない**。reference manualが符号と適用先を、EVTの`Link.ld`が組合せを言い、
  両者を突き合わせる。**「出荷時の組」と言えるものは無い**——RMは復位値を`x`と
  しか書かず、EVTの例題も1組に揃っていない
- `tools/build_link_firmware.py`: WCHが配るWCH-Link系デバッガのファームウェア
  一覧を`evidence/link_firmware.csv`にする。バイナリは置かず指紋と取得元だけ。
  **版番号は未解決**（[docs/link-firmware-survey.ja.md](docs/link-firmware-survey.ja.md)）
- `tools/build_evt_variants.py`: device headerのコメントから型番→コンパイル時macro
  （`CH32V20x_D8W`等）を取り`evidence/evt_variants.csv`にする。macroを設定しないと
  既定のvariantで黙って通るので、どの型番がどれかを表にしておく
- `tools/crosscheck_ch32data.py`: [ch32-rs/ch32-data](https://github.com/ch32-rs/ch32-data)と
  AFIO remap fieldを突き合わせる。**上流ではなく検算相手**——向こうは
  CH32V205/V407/V467/X305/X315/M030/M103のレジスタ定義を持たないため
- `docs/worklist.ja.md`: 作業リスト（生きている項目・既知の穴・次の作業の優先順・資料側の問題台帳）
- `docs/table-reliability.ja.md`: テーブル別の信頼度（どこまで信用してよいか・原典サンプル検証の結果）
- `docs/handoff.ja.md`: 正本の所在、再開手順、守ること
- `docs/worklist-archive.ja.md`: 解決済みの穴・依頼の記録（何を直し、なぜそう判断したか）
- `docs/extraction-survey.ja.md`: 機械抽出できる範囲の実測と、資料側の崩れの一覧

## データの境界

- 単位は注文可能な正確な型番。WCHのseries名と、コア内部で共有する実装familyは同一と仮定しない
- 証拠の表は資料の綴りと値を写すだけで、訂正しない（食い違いは`conflict`で両方残す）。訂正や語彙の揃えは索引の側
- board固有のLED・connector・clock・upload設定、Arduino core固有のFQBN・variant・build flagは入れない（consumer側の生成物）
- 対応tierはこのデータから宣言しない
- 兄弟repositoryは一次資料のmirrorとして参照する。EVTや旧Arduinoコアのsourceをこのrepositoryへ複製しない

## 検証

```sh
uv run tools/check_tables.py    # 全表の参照結合・書式・索引⊆証拠・manifest
uv run tools/check_counts.py    # 比較表が数える周辺の数 vs pin表から引ける数
```

抽出toolは外部packageを使うため、`pyproject.toml`と`uv.lock`で固定したuv経由で実行します。抽出できる範囲と資料側の崩れは[抽出可能性の事前調査](docs/extraction-survey.ja.md)にまとめています。

抽出toolのうち`extract_remap_fields.py`だけはhost Cコンパイラを使います（EVTの関数を動かすため）。
`cc`が環境にあれば追加の用意は不要です。ローカルへtoolchainを置く場合は`.tools/`（gitignore済み）へ。

```sh
uv run tools/extract_remap_fields.py --mirrors <EVT cloneの親> --compare evidence
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
uv run tools/extract_selectors.py <EVT>/Peripheral/inc/ch32xxx.h
uv run tools/extract_pins.py <datasheet>.PDF --package TSSOP20
uv run tools/extract_remap.py <manual>.PDF
uv run tools/extract_registers.py <manual>.PDF
```

全表の生成順は [evidence/README.ja.md](evidence/README.ja.md) の「生成順」を参照。
