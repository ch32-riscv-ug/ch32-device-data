# 取得すべき文書の一覧

[English](README.md)

このディレクトリが、WCHの公開文書と各mirrorリポジトリの対応の正本です。mirrorリポジトリは`documents.json`を読み、自分に割り当てられた文書だけをダウンロードします。

## なぜここで持つか

「どの文書がどのリポジトリのものか」は導出ではなく判断だからです。実例として次があります。

- `CH32V007DS0.PDF`は`CH32M007`も覆う。文書名とfamily名が一致しない
- `CH32xRM.PDF`は`CH32F103x`と`CH32V103x`の両方を覆う
- `CH32V307DS0.PDF`と`CH32V20x_30xDS0.PDF`は同一文書の別名配布
- `CH32X315`は独立したRMとEVTを持つため、既存リポジトリの配下ではなく新規リポジトリになる

この判定を各mirrorが自前で持つと、同じ非自明な規則が10箇所以上に複製され、ずれても誰も気づきません。またどのリポジトリにも属さない文書（未割当）は、全体を見る場所でしか検出できません。

## 対象範囲

RISC-VコアのCH32系です。Cortex-M3の`CH32F`系は`status: excluded`として理由つきで残しています。除外を記録するのは、次回の掃引で「新規」として再浮上させないためです。

WCHのBLE系（CH572/573/583/585/587/592/595/596）はRISC-Vですが現時点では未対象です。CH578/579はCortex-M0のため、RISC-V基準では対象外になります。

## 言語

**中国語版が原典で、英語版はその翻訳です。** 版数が食い違う場合は中国語版が新しく、英語版が存在しない文書もあります（`CH32M030DS2.PDF`、`CH32V006DS2.PDF`）。`primary_language`は`zh`です。

両言語を別ソースとして扱い、`sources.en`と`sources.zh`にそれぞれのdownload idと版数を保持します。

## 項目

| key | 意味 |
|---|---|
| `name` | 配布ファイル名 |
| `kind` | `datasheet` / `reference-manual` / `evt` / `core-manual` / `package-drawing` / `other` |
| `repositories` | 取得すべきmirrorリポジトリ。複数可。空なら未割当 |
| `status` | `assigned` / `unassigned` / `excluded` / `duplicate` |
| `reason` | 除外・重複の理由 |
| `duplicate_of` | `duplicate` のとき、代わりに実体を取得する文書 |
| `sources.<lang>.file_id` | WCHのdownload id。`download_url`のテンプレートに入れる |
| `sources.<lang>.version` | サイトが表示する版数 |
| `sources.<lang>.scope` | その文書が覆う製品・SKU（WCH記載のまま） |

**repositoryの分離規則はEVT単位（1 repository = 1 EVT archive）です。** update.shはEVTを`./EVT`へ全置換で展開するため、2本のEVTを同居させると後勝ちで壊れます（CH32V205を分離した理由）。family横断の文書（QingKe core manual・WCH-Link manual・PACKAGE寸法図面）は専用mirror **`WCH-common`** が保持します。WCHの原典は中国サイトの可用性が不安定なため、出典（言語別`file_id`と版）はこのカタログが記録し、実体の可用性はGitHub mirrorが担保します。`ch32-device-data`自体はPDFを持ちません。

## EVT の中にだけある文書（`evt-documents.json`）

WCH のダウンロードページに単独の配布物が無く、**EVT の中にだけ入っている文書**は `evt-documents.json` に人が書きます。今は PIOC（一部の CH32 に内蔵された RISC8B コアの eMCU）の2冊で、CH32X035・CH32V205・CH32H417 の EVT の `EXAM/PIOC/Tool_Manual/Manual/` にあります。

- `CHRISC8B.PDF`: RISC8B コアの命令セットとアセンブラ（zh・en とも版 2B）
- `PIOC.PDF`: PIOC の手册（zh 1.1・en 1.0）

`documents.json` に入れないのは、そちらが**サイトの一覧と毎日同期し、各 mirror のダウンロードの入力も兼ねる**からです。download id の無い行を混ぜると、mirror の取得と「サイトから消えた」の判定を壊します。mirror は EVT を展開するだけで、この2冊のために何もしません。

項目は `documents.json` と同じ（`name`・`kind`・`repositories`・`status`）に人が読む `note` を足したもので、`sources.<lang>` が `version`（**表紙に刷られた版**）と `files`（**mirror ごとの、その mirror の中のパス**）を持ちます。パスを mirror ごとに書くのは、ファイル名の大小とその言語版の有無が mirror ごとに違うからです（CH32V205 は `PIOC.pdf` で、CHRISC8B の en 版を持たない）。原本は名前順で最初の mirror のもので、各 family の README は自分の mirror のファイルを指します（無ければ原本の mirror）。`catalog/documents.csv` には page・download の URL を空、mirror の URL を EVT の中の PDF にして載り、変換・表・検査はほかの文書と同じに扱います。版が上がったかは `check_sources` が原本の sha で気づくので、そのとき `version` を書き直します。

## 更新

`.github/workflows/update.yml`が日次で実行します（13:07 UTC）。mirror群の更新は15:07 UTCなので、同じ日のカタログを読ませるため2時間先行しています。

手元で動かす場合は次のとおりです。

```sh
uv run pipeline/build/sync_catalog.py           # サイトと突き合わせて差分を表示
uv run pipeline/build/sync_catalog.py --write   # 差分を反映（割当は上書きしない）
uv run tools/check_mirrors.py          # mirrorがカタログに追随しているか確認
```

新規文書は`status: unassigned`で追加され、警告として run ページに出ます。割当は人が決めます。

## 失敗を運用の入口にする

WCHはdownload idを変えることがあり、検索APIそのものが変わることもあります。**そのときジョブが失敗するようにしてあります。**赤いrunが見直しの合図です。

| 事象 | 挙動 |
|---|---|
| APIが応答しない・JSONでない・`data`が無い | 原因つきで即失敗。カタログは書き換えない |
| APIの形が変わり取得件数が激減 | manifestの8割を下回ったら失敗。**空のカタログを書き込まない** |
| 新規文書が現れた | 警告注記＋`unassigned`で追加。ジョブは成功 |
| 文書がサイトから消えた | 警告注記。手元の記録は残す |
| mirrorにカタログ外のファイルが残っている | 警告注記。`update.sh`は取得しなくなったファイルを消さないため |

件数の下限を設けているのは、仕様変更が「エラー」ではなく「極端に少ない結果」として現れるためです。黙って通すとカタログが空になり、全mirrorが取得対象を失います。
