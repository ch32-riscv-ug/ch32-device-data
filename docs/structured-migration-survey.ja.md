# PDF構造化 本番移行の事前調査（D17）

作成: 2026-09-01。**同日に全8項目を完了した調査報告**。[D16最終報告](structured-document-workflow.ja.md)が
定めた再調査8項目を、その時点の原本・tool・consumer要件でやり直した。範囲は調査のみで、
converter・`pipeline/`の実装はしない。**設計案（項目6）と受入条件（項目7）は2026-09-01に
ユーザーが「いまの方針のまま」で暫定承認した**——実装（D18）で前提が崩れたら
この報告へ戻って更新する。前提となる4つの方針決定
（最初の移行CSV＝`operating_conditions.csv`、bundle保存は成立条件の実測後に決める、
**engine選定は白紙からの全面比較でやり直す**、zh/en対応付けの独立項目化）は
[worklist](worklist.ja.md)のD17に記録した。

## 状態一覧

| # | 調査項目 | 状態 | 結果の要約 |
|---|---|---|---|
| 1 | 文書inventory再棚卸し | ✅ 2026-09-01 | 対象55版＋将来10版すべて所在・SHA-256・ページ数を確定。欠落0、複数mirror写しは全一致 |
| 2 | baseline走査（既存tool・CSV） | 🔧 方法確定 | PDF直読みtoolは19本でD16の移行単位表と過不足なし。PDF APIはpdfplumber 0.11.10のみ。CSV正本53表・165,618行。hash台帳は凍結時に確定 |
| 3 | 難易度別fixture選定 | ✅ 2026-09-01 確定 | 11難所×7文書を第一版として確定（下表）。監査で新しい難所が出たら追加する |
| 4 | 変換engine比較 | ✅ 2026-09-01 決着 | **現行pdfplumberを本線とし、限界が出たら候補から追加**（ユーザー決定）。追加トリガーを明文化。基準線実測: 速度0.31s/p・容量125KB/p・検査50ms/p。**唯一の非決定性（inline imageのid()由来name）を特定、正規化で潰せる** |
| 5 | 難所の標本監査 | 🔧 第一回 2026-09-01 | fixture 7文書をbundle化し既知難所8種＋role精度を検査。**全難所がL0に材料を残す**。RMは表の85%がページ継続でL1結合が主戦場。zh/en対応はcaption番号だけでV003 30/30・H417 104/104の1:1（衝突0）。header/footer roleは**擬陽性0だがzh版footerを系統的に取りこぼす**（本番は反復ベース検出を要件に） |
| 6 | L0/L1/L2・無効化規則の設計 | ✅ 2026-09-01 暫定承認 | 本文末尾の設計案を「いまの方針のまま」で承認（ユーザー）。実装で矛盾が出たらこの報告に戻って更新する |
| 7 | 受入条件・移行単位の合意 | ✅ 2026-09-01 批准 | 最初の移行CSVは`operating_conditions.csv`。完了条件はD16の5点をそのまま採用（同日ユーザー承認） |
| 8 | 人間向け表示の用途確認 | ✅ 2026-09-01 確認 | **PDFと同じ内容をMarkdown/HTMLでそのまま読む**。第一歩はheader/footerの除去だけ、分割は後。主課題は図の扱い |

## 1. 文書inventory再棚卸し（✅）

`catalog/documents.csv`のassigned行のうちdatasheet・reference-manual（＝最初の移行完了条件の
55版）と、将来対象のcore-manual・package-drawingを、ローカルmirrorで実測した。

| 区分 | 版数 | ページ計 | PDF計 |
|---|---:|---:|---:|
| datasheet | 34（zh 18 / en 16） | 1,978 | 33.5 MB |
| reference-manual | 21（zh 11 / en 10） | 8,385 | 89.4 MB |
| **移行対象 計** | **55** | **10,363** | **122.9 MB** |
| core-manual（将来） | 8 | — | — |
| package-drawing（将来） | 2 | — | — |
| WCH-Link manual（将来。2026-09-01追加） | 2 | — | — |
| 総計 | 67 | 11,016 | 133.9 MB |

- **欠落0**。全65版がmirrorに存在する
- **複数repositoryが持つ写しは全一致**（例: `CH32FV2x_V3xRM.PDF`はCH32V20xとCH32V307の
  両mirrorにあり、zh/enともSHA-256が一致）
- zh単独版が3つある: `CH32M030DS2.PDF`・`CH32V006DS2.PDF`（datasheet）、
  `CH32V407RM.PDF`（RM）。zh/en照合の設計はこの3版を「対応相手なし」として扱う必要がある
- **zh/enで版番号がずれる文書が3つある**（今回の実測で確認）: `CH32M030DS0.PDF`
  zh 1.3 / en 1.2、`CH32X315DS0.PDF` zh 1.2 / en 1.1、`CH32X315RM.PDF` zh 1.2 / en 1.1。
  zh/en照合は「同じ版どうしの突き合わせ」を前提にできない——照合keyは版番号ではなく
  文書対＋canonical IDで持つ（D16の方針を裏付ける実例）
- 最大文書は`CH32H417RM.PDF` en 1,042ページ（8.7MB）。上位は全てRMで、
  RMがページ数の81%を占める
- 版番号は`documents.csv`（WCH APIのメタデータ）の写しで、表紙との既知の食い違いは
  F-33の1件（`CH32V20x_30xDS0.PDF` API 3.5 / 表紙V3.9）のみ
- **`WCH-LinkUserManual.PDF`（kind=other・assigned・WCH-commonにmirror済み）を
  将来対象に追加した**（2026-09-01、ユーザー判断）。動機はR-29（debug配線の対応表と
  両対応の注記を持つ——変換して実在を確認済み）とR-28（attach手順）。これも
  zh 2.8 / en 2.7 と**版番号が言語間でずれる**文書に当たる

全65版の文書・言語・版・ページ数・SHA-256の一覧は付録Aに固定した。

## 2. baseline走査（🔧 方法確定・台帳は凍結時に）

- **PDFを読むtoolは21本**、うち本番で凍結対象になる直読みtoolは**19本**:
  `build_adc_internal` `build_all` `build_debug_data` `build_dma_requests` `build_features`
  `build_flash_geometry` `build_memory` `build_operating` `build_pins` `build_registers`
  `build_timers` `extract_images` `extract_ordering` `extract_package_dims` `extract_pins`
  `extract_products` `extract_registers` `extract_remap` `scan_errata`。
  残り2本（`convert_structured` `document_converter`）はPoC側。
  **D16の移行単位表はこの19本と過不足なく一致した**——表の完全性を実測で確認
- **PDF APIはpdfplumberのみ**（fitz/pypdf/pdfminer直接importは0件）。版は`uv.lock`が
  0.11.10に固定
- **CSV正本は53表・165,618行**（catalog 8・evidence 33・index 12。2026-09-01時点）。
  D1が言う「51表」から2表増えており、凍結時に数え直す
- hash台帳の取り方は確定した（全CSVのSHA-256と行数）。**凍結はまだしない**——
  日次の自動更新でcatalogが動くため、台帳は凍結を宣言する時点で取り直し、
  そのcommitと一緒に記録する。この調査のsnapshot時点はcommit `2983be3`（clean tree）

## 3. 難易度別fixture（✅ 確定 2026-09-01）

既知の難所（worklistのF台帳・先行PoCの検出実績）から選んだ。**「過去に一度壊れた形」を
優先**し、電気特性4文書（先行PoCの回帰標本）を土台に足す。この集合を第一版として
確定し、標本監査（項目5）で新しい難所が出たら行を足す。

| 難所 | fixture候補 | 根拠 |
|---|---|---|
| 電気特性表の値一致（回帰標本） | CH32V003 / CH32L103 / CH32H417 / CH32V007 DS zh+en | [先行PoC](structured-extraction-poc.ja.md)で全件一致済み |
| ページ跨ぎの比較表 | CH32H417DS0 en | F-19（en 141行欠落の実績） |
| pin表見出しがページ境界で割れる | CH32X315DS0 en（CH32X305RCT6） | F-53 |
| 同じ封装列を持つpin表が複数 | CH32V20x_30xDS0 zh（CH32V317） | F-50（88経路がV307と混線した実績） |
| 表番号の重複 | CH32V007DS0 en（3-9-2） | 先行PoCが検出 |
| 罫線図・タイミング図の表誤認 | 先行PoC 4文書の検出例 | 先行PoCが値抽出前に検出 |
| 縦書き・回転文字 | 任意DSのpin表（縦書き封装名） | F-53と同根 |
| zh/en構成差 | CH32H417DS0（A6: 1.4.26節がzh/enで別機能、F-51） | 資料側の実績 |
| 対応相手のないzh単独版 | CH32M030DS2 / CH32V006DS2 / CH32V407RM | inventory実測 |
| 大型RM（時間・容量・検査コスト） | CH32H417RM en 1,042p | inventory実測で最大 |
| RMのregister格子・結合セル | CH32FV2x_V3xRM | remap格子・複数familyを1冊が扱う |

## 4. 変換engine比較（✅ 決着 2026-09-01）

**決着**: ゼロベースで候補を洗い直した上で（下の一次調査・予備実測）、
**L0は現行pdfplumberを本線とし、限界が出たときに候補リストからtoolを追加する**
（2026-09-01、ユーザー決定）。候補表と予備実測は追加時の出発点として残す。

**追加のトリガー**（どの限界が出たらどれを検討するか）:

| 限界の種類 | 兆候 | 追加する候補 |
|---|---|---|
| 欠落 | fixture監査・変換検証で、pdfplumberが取れない構造が出る（縦書き/回転の崩れ、glyph→Unicode欠落、罫線の読み違い） | pypdfium2で同じ箇所を読んで突き合わせる（監査比較） |
| 速度 | 再変換の頻度が上がり「55版・約1時間」が運用の妨げになる | pypdfium2ベースのL0実装を見積る（文字層は完全一致・約23倍速を予備実測済み） |
| 表構造 | L1の論理表結合・複雑な結合セルで、罫線ベースの候補生成の精度が足りない | Docling（TableFormer）を候補生成の第二の目として難所だけに適用。控えはgmft/Camelot |

いずれの追加も**L0の正本はpdfplumber系のまま**、追加toolは監査・候補生成の
補助に限る（変換器の系統誤りを全抽出器が共有する危険への歯止めは
「第二engineによる難所比較」であり、これはD16の方針どおり）。

以下は決着に至る比較の記録。比較軸はD16の4つ（欠落・速度・容量・依存量）に、
この調査で効くと分かった軸を足した7つ:

1. **欠落**——文字・表・結合セル・縦書き/回転文字・CJK・図形描画命令が取れるか（fixtureで実測）
2. **速度**——55版10,363ページの全変換時間
3. **容量**——bundle換算の総量
4. **依存量**——インストールサイズ、ML model要否、ネイティブ依存
5. **決定性**——同一入力で同一出力か（bundle非保存方針の前提）
6. **license**——repoに同梱・再配布できるか
7. **座標の粒度**——char/word/線分のbboxが取れるか（L0の要件。表構造の独自復元と
   原本照合に必須）

### 候補の一次調査（🔧 2026-09-01 机上＋予備実測）

**このrepoはMIT licenseなので、AGPL系はtools/への同梱ができない**——licenseが
最初のふるいになる。表専用のtool（L0の文字・座標層を持たない）は本線ではなく
「表構造の監査比較（第二の目）」の候補として分ける。

| 候補 | 種別 | license | 依存量 | L0適性（文字・座標・描画） | 表構造 | 一次判定 |
|---|---|---|---|---|---|---|
| pdfplumber 0.11.10（現行） | pure Python（pdfminer.six） | MIT | 小 | char/line/rect/curveのbbox完備 | 罫線ベース＋現行toolの補正実装 | **基準線**。実測は下記 |
| pypdfium2 | pdfium（Chromium）binding | Apache-2.0 / BSD-3 | 小（wheelにpdfium同梱） | char bbox完備。**非空白文字はpdfplumberと完全一致**（予備実測）。描画はpath objectとして見えるが線分詳細は低レベルAPI直叩き | なし（自前実装が必要） | **速いL0候補**（char走査で約23倍速）。罫線分解の実装コストを見積る予備実験が要る |
| PyMuPDF（fitz） | MuPDF binding | **AGPL-3.0** | 小 | 完備・速い | `find_tables()`あり | **licenseで除外**（MIT repoに同梱不可。商用license購入は過剰） |
| Docling | ML（DocLayNet＋TableFormer） | MIT | **大**（torch＋model download数GB級） | 画像経由（72dpi）。char座標はpdfium系から取得 | **最強クラス**（画像から論理構造・header種別まで復元） | 全55版のL0には速度が非現実的（表1つ2〜6秒/CPU）。**難所の表構造の監査比較に有力** |
| gmft | ML（Table Transformer）＋pypdfium2 | MIT | 大（torch） | 表専用 | 強い | 監査比較の控え |
| Camelot | 表専用（lattice/stream） | MIT | 中（Ghostscript等） | 表専用 | 罫線表はlatticeが強い | 監査比較の控え |
| poppler（pdftotext -bbox等） | C++ CLI | GPL-2 | system依存 | 文字bboxのみ | なし | 外部CLIとして呼べば同梱回避できるが利点が薄い。見送り想定 |
| marker / MinerU / unstructured | ML文書変換 | GPL系/AGPL/Apache（要確認） | 大 | 変換先がMarkdown等で**座標・原本照合を失う** | — | L0要件（原本座標の保存）を満たさず本線から外す想定 |

机上調査の主な出典: [Docling Technical Report](https://arxiv.org/html/2408.09869v1)
（TableFormerの処理時間・決定性の公称）、
[Camelot比較資料](https://camelot-py.readthedocs.io/en/latest/user/comparison.html)。
license・依存量は各projectの配布metadataで、fixture比較の着手時に版を固定して再確認する。

#### 予備実測: pdfplumber vs pypdfium2（CH32V003DS0 en・37ページ）

| 軸 | pdfplumber | pypdfium2 |
|---|---|---|
| 非空白文字数 | 42,240 | **42,240（完全一致）** |
| 空白の扱い | 空白5,056個を語間に合成 | 改行`\r\n`各1,593個を行末に合成 |
| Unicode化できない字 | `-` 7字を復元 | 同じ7字が`￾`（欠落） |
| char＋bbox全走査 | 6.5 s | **0.28 s（約23倍速）** |
| 罫線・描画 | line 810・rect 951・curve 7,706 | path object 7,014個（線分詳細は低レベルAPI要） |

読み: **文字層の内容は等価**で、pdfium系は速度が1桁半速い。ただしL0が要る
罫線分解（表の物理構造の根拠）はpdfplumberが即持っており、pypdfium2では
自前実装になる。表検出も自前。「変換が55版で約1時間」（下の基準線実測）を
許容するなら現行pdfplumberで足り、頻繁な再変換や将来の対象拡大を見込むなら
pypdfium2の実装コストを測る価値がある。

#### 次の実測（fixture確定後）

1. 難所fixture（項目3）で pdfplumber / pypdfium2（＋自前罫線）/ Docling の
   欠落・速度・容量・依存量・決定性を同一条件で測る
2. pypdfium2の罫線分解（低レベルpath API）の実装コストを1ページ分の予備実験で見積る
3. Doclingの表構造出力を、既知の難所表（結合セル・ページ跨ぎ）で現行実装と突き合わせる

### 現行pdfplumber（基準線）の実測

bundle保存方針（「再生成できる中間物は保存しない」が成立するか）の分かれ目になる実測。
現行converterは設計時点で決定性に配慮している（gzipに`mtime=0`、`engine_version`を
manifestに記録、全page・geometryのSHA-256をmanifestが台帳として持つ）。

#### 再現性（同一環境・同一入力の2回変換）

| 対象 | ページ | 結果 |
|---|---:|---|
| CH32V003DS0 en（datasheet） | 37 | **byte一致** |
| CH32V003DS0 zh（CJK） | 31 | **byte一致** |
| CH32H417RM en（最大文書） | 1,042 | **14ページのみ差分**（原因特定済み・下記） |
| CH32H417RM en（**本番converter 1.0.0**・D18） | 1,042 | **byte一致**——id()由来nameの正規化で非決定が消えたことを実証（2026-09-01） |

**非決定性の源を1つ特定した。** pdfminerは、点線や網掛けをinline image
（3×1pxなどの断片）として描くPDFに対し、無名のimageへ`id()`（メモリアドレス）由来の
`name`を付け、現行converterがそれをJSONへ写している。1,042ページ中、inline imageを
持つ14ページだけが2回の変換で異なり、`name`欄をマスクした意味比較では
**全1,042ページが完全一致**、manifestの差分もその14ページのpage hashのみだった。

帰結: **決定性はengineから自動では得られないが、非決定の源は列挙可能で、
出力の正規化で潰せる**。converter自身の安定ID（`p66-draw-image-00002`形式）は
既に決定的なので、本番converterの仕様に「engine由来のprocess依存値
（id()由来name等）を安定IDへ正規化する」を含めればbyte一致が成立する見込み。
残る未確認は**環境差**（別マシン・OS・Python版）で、凍結前にCI（GitHub Actions）上で
同じ変換を回してローカルとhash一致するかを確認する。

#### ズレ検出（bundleを保存しない場合の担保）

`manifest.json`（原本SHA-256・全pageのSHA-256・geometryのSHA-256・engine_version）だけを
コミットすれば、再生成bundleと突き合わせて**どのpageがいつからズレたか**をpage単位で
言える。manifestは1文書あたり数十KBで、65版でも数MBに収まる。
再現性が成立する限り、bundle本体の保存は不要と判断できる材料が揃いつつある。

#### 性能・容量の実測と外挿

| 対象 | ページ | 変換時間 | bundle容量 | 1ページあたり |
|---|---:|---:|---:|---:|
| CH32V003DS0 en | 37 | 8.5〜10.6 s | 3.8 MB | 103 KB/p |
| CH32V003DS0 zh | 31 | ―（同程度） | 2.8 MB | 89 KB/p |
| CH32V003RM en（PoC実測） | 188 | ― | 27 MB | 144 KB/p |
| CH32H417RM en（最大） | 1,042 | 322 s（0.31 s/p） | 130 MB | 125 KB/p |

- 外挿: 55版・10,363ページ → **bundle総量 約1.3GB**（125KB/p平均）、変換は
  **単核で約1時間**（文書単位で独立なので並列化可能）。repoへの直接コミットは
  非現実的で、「manifest＋review sidecarだけコミット」案を裏付ける
- 検査ゲート`check_document_bundle.py`はCH32V003DS0 en（37p）で1.9秒、
  CH32H417RM en（1,042p）で**51.9秒**——約50ms/pの線形で、55版全体でも約9分。
  **D16が懸念した「大型RMでの完全schema検査の高コスト」は実測では許容範囲**で、
  「精密層はhash＋envelope検査に分ける」案は現時点では不要見込み

## 5. 難所の標本監査（🔧 第一回 2026-09-01）

fixture 7文書（V003 DS zh/en・H417 DS zh/en・X315 DS en・V20x_30x DS zh・V007 DS en・
FV2x_V3x RM en）をbundle化し、既知の難所が中間層にどう写るかを検査した。

| 難所 | 実測 | 含意・L1への期待値 |
|---|---|---|
| 表番号の重複（V007 en） | p48に「Table 3-9-2」のcaption行が**2本**（M007E8U7/E8R6の消費電流表）。両方bundleに存在 | 表番号はIDにできない。captionの`line_id`で区別する（先行PoCの検出と一致） |
| pin表見出しのページ割れ（X315 en・F-53） | Table 2-1（p19・23行）→p20の26行が`continues_from_previous=True`の断片として保存 | 見出しが割れてもL0は落とさない。期待値: p19＋p20で1 logical table |
| 同名封装の複数pin表（V20x_30x zh・F-50） | 表3-1（p24）と表3-2 CH32V317（p35）が別captionで独立に存在 | caption scopeでの表選択の材料が中間層に残る |
| ページ跨ぎ比較表（H417 en・F-19） | p3（41×8）とp4（11×8）の2断片。**現行PoCの継続推定はこの対を結ばない** | L1結合は隣接だけでなく列構造一致を使う（D16方針の実証）。期待値: p3＋p4で1 logical table |
| zh/en構成差（H417・A6） | zh 1.4.26＝USB3.0超高速（USBSS）／en 1.4.26＝「USB**2.0** SuperSpeed（USBSS）」がheading行として対で取れる | 資料側の齟齬はL2（zh/en対応・注記）の記録対象 |
| 縦書き・回転文字 | geometry層の`upright`で検出可能（X315 en: 11ページ1,531字、V20x_30x zh: 26ページ4,373字） | 基本層は読み用・精密層が向きを持つ、の分担で足りる |
| 結合セルの重なり・表の崩れ | converterが`issues`として表単位に記録（文書あたり1〜14表） | review sidecarの入力になる（自動修正しない方針どおり） |
| RMの規模 | FV2x_V3x RM en（627p・81MB）: 表**1,101個**、うち**85%（937個）が`continues_from_previous`**、caption付きは113個のみ | **RMの主戦場はL1の表結合**。caption番号によるzh/en対応はRMでは1割にしか効かない |
| header/footerのrole精度（項目8の前提。2026-09-01実測） | **擬陽性0**（8 bundleとも本文をheader/footer扱いした行なし）。headerは両言語で検出（en 135/148p・zh 119/130p等）。**footerはzh版で系統的に未検出**——`V1.8 頁番号`の行がV003 zh 30/31p・H417 zh 126/130p・V20x_30x zh 86/87pで`paragraph`のまま（en版は31/37p検出・4p取りこぼし） | 原因特定済み: 現行PoCの判定は**y閾値そのもの**（top<6%→header・bottom>94%→footer。`document_converter.py`）で、zhのfooterはbottom≈93.8%と**閾値の外側0.2%**に落ちる。擬陽性0も「極端な余白しか旗を立てない」設計の帰結。表示の第一歩（カット）はPoC exporterに実装済み（該当role行をHTMLコメント化）。**本番のheader/footer検出は反復ベース（全ページで同位置・同形の行）を要件にする**——本文はページ高の90%位置まで来るので閾値を緩めると本文を切る |

### zh/en対応付け・自動候補の第一回実測

caption番号（converterが`source_number`として抽出済み）だけをkeyにした1:1対応:

| 文書対 | zh番号付き表 | en番号付き表 | 1:1一致 |
|---|---:|---:|---|
| CH32V003DS0 | 30 | 30 | **30（100%・衝突0）** |
| CH32H417DS0 | 104 | 104 | **104（100%・衝突0）** |

datasheetでは「caption番号で候補生成→内容照合で確認」が成立する見込み。RMは
caption付きが1割なので、L1結合後に章構造・register名で対応付ける工程が別途要る。
版番号がzh/enでずれる文書がある（項目1）ため、対応の記録は原本hashを固定した
版対に付ける。

## 6〜8. 残り（設計・合意・表示）

- **6 L0/L1/L2設計**: 入力が揃った——bundle非保存＋manifestコミット＋review sidecar
  コミット（項目4）、決定性の正規化要件（項目4）、L1結合が列構造一致を要すること・
  RMでは結合が主戦場であること（項目5）、zh/en対応の候補生成の初期値（項目5）。
  これらからartifact分割・stable ID・結合候補・review粒度・原本更新時の無効化規則を
  設計する。**設計案を下に起草し、2026-09-01にユーザーが暫定承認した**
- **7 受入条件・移行単位**: 最初の移行CSVは`operating_conditions.csv`（決定済み）。
  完了条件はD16の5点（schema互換・説明できない欠落0・追加変更行の原文リンク・
  consumer検査合格・再実行で同一結果）を本番用に批准する
- **8 表示用途**: ✅ 利用者に確認した（2026-09-01）。**用途は「PDFと同じものを
  Markdown/HTMLでそのまま読む」**。
  - 第一歩は**header/footerの除去だけ**。L0は行に`header`/`footer`のroleを既に付けていて、
    PoCの`export_document_markdown.py`は該当roleの行をHTMLコメントに落とすので、
    仕組みは既にある。付与精度は実測した（項目5の表）——**擬陽性0**だが、
    **zh版のfooterを現行PoCはほぼ全ページ取りこぼす**。本番converterは反復ベースの
    header/footer検出を要件にする（y閾値では本文まで切れてしまう）
  - **分割（文書・章・原本ページ）はその後**に決める——分割仕様を中間層から
    独立させる方針どおり
  - **主課題は図の扱い**。当面は図のbboxに占位を置き、原本PDFの`#page=N`リンクで
    代替する。pixel cropは原本hashを固定した別のasset renderer（D16の次工程）で
    生成し、表示はそのassetを参照する形に寄せる

### 項目6の設計案（2026-09-01 起草・同日ユーザー暫定承認）

この調査の実測から導いた案。**「いまの方針のまま」で暫定承認済み**——本番schema・
architecture decisionの出発点であり、実装で前提が崩れたらここへ戻って更新する。

#### artifactと保存の分割

| 層 | 中身 | 保存 | 根拠 |
|---|---|---|---|
| L0 bundle（pages・geometry） | 変換器の直接出力 | **非保存**（`.cache/`等で再生成） | 総量約1.3GB。決定的に再生成できる（項目4） |
| L0 manifest | 原本hash・全page/geometryのhash・engine版 | **repoにコミット**（数十KB/文書・65版でも数MB） | ズレ検出をpage単位で可能にする |
| L1 文書論理層 | logical table/section（L0断片への**参照のみ**、内容コピーなし） | **非保存**（L0＋結合規則の版から決定的に再生成）。結合結果のhashはmanifest側の台帳に足す | 結合はコードの純関数にし、人の判断を持ち込まない |
| L2 sidecar | 承認・却下・canonical ID・zh/en対応・注記・翻訳 | **repoにコミット（正本）** | 人の判断は再生成不能（項目4の前提と同じ） |

#### 設計規則

1. **決定性は仕様**——engine由来のprocess依存値の正規化（id()由来name→安定ID）、
   set順序への依存禁止、gzipは`mtime=0`、engine版をmanifestに記録、CIで再現hash検査
2. **stable ID**は現行の`p{page}-{type}-{連番}`形式（同一原本内で決定的）。IDに内容hashを
   混ぜる案は、微修正で全IDが変わり差分追跡を壊すので**採らない**
3. **L2のkeyは`(source_sha256, stable ID)`**。bundleを再生成してもkeyは不変。原本が
   改版されたら旧hashのL2エントリは自動で失効し、新版への引き継ぎは対応表を人が
   reviewして移す（D16「古いreviewを自動流用しない」の実装）
4. **L1の結合候補**は隣接＋列構造一致＋繰り返しheader＋captionの有無から作る
   （継続flagだけでは不足——項目5でH417比較表の対を結ばないことを実証）。候補は
   スコア付きでL2の承認待ちに出す
5. **zh/en対応**はdatasheetがcaption番号で候補生成（実測100%・衝突0）→内容照合で確認、
   RMはL1結合後に章番号・register名で対応付ける。対応の記録は両言語の原本hashを
   固定した版対に付ける
6. **開いた設計点**——L1を別ファイルにするか同bundle内の別sectionにするか／L2の承認粒度
   （表単位か章単位か）。manifestのコミット先は**`structured/<stem>.<lang>/`に決めた**
   （D18実装、2026-09-01。既存`manifests/`はWCH APIの写しなので使わない。
   review sidecarも同じ場所に置く）

## 付録A: 対象文書の実測台帳（2026-09-01）

mirror写しが複数ある文書はSHA-256の一致を確認済み（代表pathの値を記す）。

| document | kind | lang | version | pages | bytes | mirrors | sha256 |
|---|---|---|---|---:|---:|---|---|
| CH32H417DS0.PDF | datasheet | en | 1.8 | 148 | 1,868,282 | CH32H417 | `686bcd003996cca45401c598c7fca4b9eb9acbb5c780cde64a23c76660fd4fb1` |
| CH32H417DS0.PDF | datasheet | zh | 1.8 | 130 | 2,021,288 | CH32H417 | `0436de8690f8690cd6f1596cd6a4a45b4f9fda631c1f59ed33ee355ac7d4c332` |
| CH32L103DS0.PDF | datasheet | en | 2.1 | 70 | 913,868 | CH32L103 | `9c096cbc423ef4b6910a536e6b8c06df3cc541876b129bcc0f3485478613fce6` |
| CH32L103DS0.PDF | datasheet | zh | 2.1 | 58 | 997,523 | CH32L103 | `7ee87a9b127bf6e95d8b037cade194cdfe28968041b21875e555239506734ecc` |
| CH32M030DS0.PDF | datasheet | en | 1.2 | 57 | 831,830 | CH32M030 | `aa4331e7649686faf4edcc36024f01f67938594aeb3ae8de6f5d702461f7394c` |
| CH32M030DS0.PDF | datasheet | zh | 1.3 | 47 | 825,334 | CH32M030 | `62d031cc4c65e43f153007bc65b30a5ad440695b2c887f23290af17cb389c598` |
| CH32M030DS2.PDF | datasheet | zh | 1.2 | 12 | 229,894 | CH32M030 | `b5cfb614e03e2894fe4505f776b37e7bb6fa7d02f5ad9722cda1d52f64cbe1ad` |
| CH32V002DS0.PDF | datasheet | en | 1.7 | 47 | 686,388 | CH32V006 | `4022fad7e39f80997a00b502b5cf2b2ce7b53b2df36492bd102b772199bb7ae1` |
| CH32V002DS0.PDF | datasheet | zh | 1.7 | 35 | 725,067 | CH32V006 | `3c238006e7f63dfb162675bf067a8abf7fd48bbc2d11ef04fcbf885bb256e998` |
| CH32V003DS0.PDF | datasheet | en | 1.8 | 37 | 723,483 | CH32V003 | `186210d35123325ea49305e3a0152cbfa6e377d8e6efc2e610e3497daabe17f8` |
| CH32V003DS0.PDF | datasheet | zh | 1.8 | 31 | 730,661 | CH32V003 | `2c05b25a3ef9269ca3685db09de05a2b31c650e1b389b0cecc735d4176985b91` |
| CH32V004DS0.PDF | datasheet | en | 1.9 | 39 | 647,197 | CH32V006 | `3c3f995fc315ac0a407e5c67943c65468a4b59ce68a84d9843e6e784289258de` |
| CH32V004DS0.PDF | datasheet | zh | 1.9 | 32 | 683,387 | CH32V006 | `3d79323557a7c264bdea2345aaf5104edeb12446994326541ed297270d47f7ec` |
| CH32V006DS0.PDF | datasheet | en | 2.0 | 62 | 793,018 | CH32V006 | `806ff03d11ebe8f522b6a10bfce20040f30f3cff6a751bd982efca788f9601f2` |
| CH32V006DS0.PDF | datasheet | zh | 2.0 | 44 | 817,766 | CH32V006 | `49b06f8a70d02e9adc909cbbd250070e1733bba0c9cdf7fcbf44bd773ebaf472` |
| CH32V006DS2.PDF | datasheet | zh | 1.1 | 35 | 771,322 | CH32V006 | `daec3fe3c22ec1b4dae91edc9f11b104919bfd9dc81272b162fb41a89eea47ad` |
| CH32V007DS0.PDF | datasheet | en | 1.8 | 73 | 867,678 | CH32V006 | `2952c163dbff06256dda9b811b48d3c530a9b7c1cc35dcb5b309ecf8e9469043` |
| CH32V007DS0.PDF | datasheet | zh | 1.8 | 50 | 908,734 | CH32V006 | `e225c19209016e79be3015156362695d322ee796256999b952ba2c2c2dffa7f5` |
| CH32V103DS0.PDF | datasheet | en | 1.2 | 41 | 937,072 | CH32V103 | `5719208b1846c735434e9e630a9c43068b38898f9bf6432556255187f3a213d4` |
| CH32V103DS0.PDF | datasheet | zh | 1.2 | 36 | 973,508 | CH32V103 | `51d2a9f352d2275e52443df131061ec550d674b965722a948f1e6e3393ae93e1` |
| CH32V203DS0.PDF | datasheet | en | 3.0 | 66 | 906,434 | CH32V20x | `10af5de2779ce1e985162dceae2e829800b2d633d34491333b1ce90f4ffcbdd2` |
| CH32V203DS0.PDF | datasheet | zh | 3.0 | 56 | 980,292 | CH32V20x | `ed9f61b06af910a217c9a8e1c0b6cea74cdb86e1d961e554917d9d5938f36a9d` |
| CH32V205DS0.PDF | datasheet | en | 1.3 | 79 | 1,266,615 | CH32V205 | `e1fd68cff64e376f963d662914d6c20de70d9b53dc0fe0ffa363d56449cc6134` |
| CH32V205DS0.PDF | datasheet | zh | 1.3 | 68 | 1,136,378 | CH32V205 | `49bfe7e3b29fecf3ab7e6f7cc8165ded972c87401ea7b4b4d17a7332d606acbb` |
| CH32V208DS0.PDF | datasheet | en | 2.7 | 49 | 870,880 | CH32V20x | `fb27cf113671f332bf576dec8e939bdaa1c2cdae50df83223f282935cbc2e9d3` |
| CH32V208DS0.PDF | datasheet | zh | 2.7 | 42 | 865,671 | CH32V20x | `4c651cf3c1b4d8262b6b98c81f72f04c6bc22ff64b7f1ddd74f5ff77a118e569` |
| CH32V20x_30xDS0.PDF | datasheet | en | 3.5 | 99 | 1,707,866 | CH32V307 | `9747c52e34d1f48cfb437cd7fbd65837e5c0f975a73f784f33634f539ed41250` |
| CH32V20x_30xDS0.PDF | datasheet | zh | 3.5 | 87 | 1,661,254 | CH32V307 | `5f87f9f397529ca80c17a341188f26819a4420f79535a5a613c4cfe9a9575bb6` |
| CH32V407DS0.PDF | datasheet | en | 1.2 | 84 | 1,450,736 | CH32V407 | `b0bb7b390d186bee35b57aeec56c8526304b43d251a393acf198a2b02bc8d766` |
| CH32V407DS0.PDF | datasheet | zh | 1.2 | 74 | 1,489,781 | CH32V407 | `14a0cdebae2a2782ab75e6a9a68dd05220a93b13e92c47d428566293b1d74d69` |
| CH32X035DS0.PDF | datasheet | en | 2.2 | 47 | 764,829 | CH32X035 | `8cccb68de9f878f56055c8925c5d11c771391f8ec0ecc705ac8ca77599402166` |
| CH32X035DS0.PDF | datasheet | zh | 2.2 | 41 | 795,809 | CH32X035 | `147f0d22d0738729f7b5288e933806df3b31c624ff0ea157c2bb709cd3841498` |
| CH32X315DS0.PDF | datasheet | en | 1.1 | 55 | 824,263 | CH32X315 | `4ec0a1a3b99bb3f1bf805c3a89773ab45e0099547262ae351e9963b9278e80c1` |
| CH32X315DS0.PDF | datasheet | zh | 1.2 | 47 | 832,109 | CH32X315 | `b608baf2eb812effdc3f63ef8d988c110e931655cacf0d6c63aef49c51682408` |
| CH32FV2x_V3xRM.PDF | reference-manual | en | 2.5 | 627 | 5,553,146 | CH32V20x;CH32V307 | `d961d2291a5d9079a8c391e89e5f9807d0c0fc22f66595c417acfd4ecebdbc44` |
| CH32FV2x_V3xRM.PDF | reference-manual | zh | 2.5 | 553 | 7,345,516 | CH32V20x;CH32V307 | `6bdc58b159a95c40e815eb9973df1f7e7309b08e8018bad1991a71c792cefb95` |
| CH32H417RM.PDF | reference-manual | en | 1.7 | 1042 | 8,736,372 | CH32H417 | `ec734cc2092c8174e6c27518a39ae1bcb27031c9cfdeae687eaf867195816f18` |
| CH32H417RM.PDF | reference-manual | zh | 1.7 | 879 | 8,188,806 | CH32H417 | `b57ebb0c0ae2cd772d32cb9ddeb6a6315fcc3916bcd3576e5a83eaeb7dfa6967` |
| CH32L103RM.PDF | reference-manual | en | 2.2 | 370 | 3,374,710 | CH32L103 | `7dc8e971fad5635e252e20ac9ef0e282f28d4ac70bd788817c288310d4c7b415` |
| CH32L103RM.PDF | reference-manual | zh | 2.2 | 313 | 3,331,776 | CH32L103 | `27a1b969cb2cb99d296ac562cac134ec63d52e4f0c75cf9d6bad7c696bc66fe3` |
| CH32M030RM.PDF | reference-manual | en | 1.2 | 274 | 4,230,544 | CH32M030 | `3143314893b1ecc3b04f3c5714c0ee4b7a249c29446c37fb58f9e388e1cce347` |
| CH32M030RM.PDF | reference-manual | zh | 1.2 | 251 | 4,563,783 | CH32M030 | `109a7bb0ab9a0b7029f82f05bbf8ba212f879b32a20b00a0c3e1a8f5948629ae` |
| CH32V003RM.PDF | reference-manual | en | 1.9 | 188 | 2,472,575 | CH32V003 | `2758a463045dc6e9ec36600a76317d7c5e75ffd421b5a44d8f58a060e6f271ff` |
| CH32V003RM.PDF | reference-manual | zh | 1.9 | 194 | 2,155,889 | CH32V003 | `7a6bf439ecd68e0b87ffdd6765da2ef9b1796ce16084b7d1f25a658380c3bcfe` |
| CH32V00XRM.PDF | reference-manual | en | 1.5 | 269 | 2,622,820 | CH32V006 | `3983a3912e4356d17a2c32d4d36b721c13b9e6cbdba01e67478af62e1f337334` |
| CH32V00XRM.PDF | reference-manual | zh | 1.5 | 229 | 3,211,719 | CH32V006 | `7d216d69fd04d990c4d1c1bf276f741c66023fd6747b6d0a2bba50a03b30c3df` |
| CH32V205RM.PDF | reference-manual | en | 1.2 | 461 | 4,616,979 | CH32V205 | `b5d41c433237eda42111ef2d7bcbfccaa2ed5e22221d52edbff2b38fbe89d03e` |
| CH32V205RM.PDF | reference-manual | zh | 1.2 | 389 | 4,718,058 | CH32V205 | `b1ed9ef040455a1f9a32f1ab9f9be0e9d3391709bc0b6fa141b2f581593b6c59` |
| CH32V407RM.PDF | reference-manual | zh | 1.2 | 537 | 5,214,830 | CH32V407 | `63625af9027af6abfff57a58f8d2afdb2b68ee7d31c323e407da6ea786573c56` |
| CH32X035RM.PDF | reference-manual | en | 1.9 | 261 | 2,568,824 | CH32X035 | `c5dc49eb6a0086857bc120cf4c1646fa8530006fe5a21e7bbb632a075daf036a` |
| CH32X035RM.PDF | reference-manual | zh | 1.9 | 246 | 2,578,952 | CH32X035 | `c7e301eac4790ca1ba112f946bf057139ec7f36be28e142cafc1c286bcc9daa4` |
| CH32X315RM.PDF | reference-manual | en | 1.1 | 365 | 3,122,157 | CH32X315 | `b96ef8345c0cf7dfec4877d0bbd3522cb67722a222b94745e8389372fd9c8699` |
| CH32X315RM.PDF | reference-manual | zh | 1.2 | 310 | 3,113,343 | CH32X315 | `b6a752f9e9bdbb1d1fd9c8ba62f6e52633620c06c0d21fbc450925541a0c2785` |
| CH32xRM.PDF | reference-manual | en | 2.0 | 341 | 3,438,470 | CH32V103 | `7da287f39a8e68944d5d29ebab1f044d3e66552576acdcee1abb493f5a1b9142` |
| CH32xRM.PDF | reference-manual | zh | 2.0 | 286 | 4,281,279 | CH32V103 | `b4ade26ba00e0f03ea8c13d89badf5491bcdebbfa10957c4839ecc60f34b3cad` |
| QingKeV2_Processor_Manual.PDF | core-manual | en | 1.3 | 32 | 395,334 | WCH-common | `a7d0c2cd9aa4a5a7153a3aeb97c1947376e96114514fad1077f9a6d48c39e1cc` |
| QingKeV2_Processor_Manual.PDF | core-manual | zh | 1.3 | 27 | 455,773 | WCH-common | `5430356218fca280023429a2516c3ac4aa200477a7fedd7d21af2f3562d70e7b` |
| QingKeV3_Processor_Manual.PDF | core-manual | en | 1.5 | 66 | 645,007 | WCH-common | `e8cf8a3d2cf2f26427b9b03fdd4dac9913fb6135df76d9c380baf4e254a498c3` |
| QingKeV3_Processor_Manual.PDF | core-manual | zh | 1.5 | 56 | 793,505 | WCH-common | `fcc16b54d8818b04b9f8a7a7fbce6c504b87ca3787f0933edecc4da7112438d5` |
| QingKeV4_Processor_Manual.PDF | core-manual | en | 1.5 | 44 | 482,933 | WCH-common | `975594d2fdb518c7a4ece5fb8e655bf7bde23c72e568d6c7d86a1b5ad0a97939` |
| QingKeV4_Processor_Manual.PDF | core-manual | zh | 1.5 | 37 | 564,663 | WCH-common | `b543a875a199a67091193afc16e0f7c4ec365df3b8d35bf93b4cc6546e362591` |
| QingKeV5_Processor_Manual.PDF | core-manual | en | 1.0 | 55 | 567,573 | WCH-common | `0095d6edad602bc770dad1478397a826c9941ff0e665d681f0540af0f18319ea` |
| QingKeV5_Processor_Manual.PDF | core-manual | zh | 1.0 | 47 | 704,001 | WCH-common | `0a849c719d1358856f0a5cf6409060a6fa8c3b7f501e0986cea0485b26a22a1b` |
| PACKAGE.PDF | package-drawing | en | 4.0 | 119 | 706,949 | WCH-common | `2a1037853831632510e2e1a0cd6b7a43b0004f0a63ff947ab52544c580726669` |
| PACKAGE.PDF | package-drawing | zh | 4.0 | 117 | 616,307 | WCH-common | `62af4259cdde0a1f6daa2aa28c9950f6e6b150c7b9ddf0eb5bda2b6501b2c96c` |
| WCH-LinkUserManual.PDF | other | en | 2.7 | 29 | 1,377,280 | WCH-common | `cf54329bc5f9f8879a5c6f3fcb1db869c6f624631a4f12f27b4dd52da387a375` |
| WCH-LinkUserManual.PDF | other | zh | 2.8 | 24 | 3,581,840 | WCH-common | `1ca6897d1a22224c165acdd287450fbbd016782c350ac274b179789e9d16dc47` |

