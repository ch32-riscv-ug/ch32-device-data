# 取得すべき文書の一覧

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

**中国語版が原典で、英語版はその翻訳です。** 版数が食い違う場合は中国語版が新しく、英語版が存在しない文書もあります（`CH32V407RM.PDF`、`CH32M030DS2.PDF`、`CH32V006DS2.PDF`）。`primary_language`は`zh`です。

両言語を別ソースとして扱い、`sources.en`と`sources.zh`にそれぞれのdownload idと版数を保持します。

## 項目

| key | 意味 |
|---|---|
| `name` | 配布ファイル名 |
| `kind` | `datasheet` / `reference-manual` / `evt` / `core-manual` / `other` |
| `repositories` | 取得すべきmirrorリポジトリ。複数可。空なら未割当 |
| `status` | `assigned` / `unassigned` / `excluded` / `duplicate` |
| `reason` | 除外・重複の理由 |
| `sources.<lang>.file_id` | WCHのdownload id。`download_url`のテンプレートに入れる |
| `sources.<lang>.version` | サイトが表示する版数 |
| `sources.<lang>.scope` | その文書が覆う製品・SKU（WCH記載のまま） |

family横断の文書（QingKe core manual・WCH-Link manual・PACKAGE寸法図面）は専用mirror **`WCH-common`** が保持します。WCHの原典は中国サイトの可用性が不安定なため、出典（言語別`file_id`と版）はこのカタログが記録し、実体の可用性はGitHub mirrorが担保します。`ch32-device-data`自体はPDFを持ちません。

## 更新

`.github/workflows/update.yml`が日次で実行します（13:07 UTC）。mirror群の更新は15:07 UTCなので、同じ日のカタログを読ませるため2時間先行しています。

手元で動かす場合は次のとおりです。

```sh
uv run tools/sync_catalog.py           # サイトと突き合わせて差分を表示
uv run tools/sync_catalog.py --write   # 差分を反映（割当は上書きしない）
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
