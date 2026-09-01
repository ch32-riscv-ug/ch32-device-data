#!/bin/sh
# structured-markdown を preview リポジトリへ写して1コミットで公開する。
#
# previewは**再生成できる使い捨ての表示**なので、履歴を積まない——毎回
# 「orphan branchを作り直してforce push」する。リポジトリは常に最新の1コミット
# だけを持ち、95MB前後から育たない。正式リポジトリのログも汚れない。
#
# 使い方（gitはユーザーが操作する前提。このスクリプトは手動で実行する）:
#   1. GitHubで空のリポジトリを作る（例: ch32-riscv-ug/ch32-device-data-preview）
#      Settings → Pages → Deploy from a branch → main / (root)
#   2. clone して、このスクリプトに場所を渡す:
#        pipeline/review/publish_preview.sh ../ch32-device-data-preview
#   3. ブラウザで https://ch32-riscv-ug.github.io/ch32-device-data-preview/
#      （Pagesのビルドが11kファイルで時間切れになる場合でも、
#        github.com のファイルビューが同じMarkdownをそのまま描画する）
set -eu

SRC="$(dirname "$0")/../../.cache/structured-markdown"
DST="${1:?usage: publish_preview.sh <path-to-preview-clone>}"

[ -d "$DST/.git" ] || { echo "$DST is not a git clone" >&2; exit 1; }
[ -f "$SRC/README.md" ] || { echo "run pipeline/review/export_markdown.py --all first" >&2; exit 1; }

rsync -a --delete --exclude .git "$SRC"/ "$DST"/

cd "$DST"
git checkout --orphan preview-next
git add -A
git commit -m "structured-markdown preview $(date +%F)"
git branch -M preview-next main
git push --force origin main
echo "published: $(git rev-parse --short HEAD)"
