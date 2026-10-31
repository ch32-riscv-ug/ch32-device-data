#!/bin/sh
# structured-markdown を preview リポジトリへ写して1コミットにする（push はしない）。
#
# preview は表の basis（`CH32V407DS0.PDF:zh(p.59)`）から、そのページを抽出器がどう読んだかを
# 見るための公開物。`<文書>.<言語>/pages/<NNNN>.md` の NNNN は basis の p.N と同じ PDF の
# 通しページ番号。原本との差ゼロは regenerate の --human 段（check_markdown_parity）が見ている。
#
# 再生成できる使い捨ての表示なので履歴を積まない——毎回 orphan branch を作り直し、
# リポジトリは常に最新の1コミットだけを持つ。コミットには元にした ch32-device-data の
# commit を書くので、作業ツリーが clean なとき（表を commit した後）にだけ走る。
#
# 使い方（リリースの手順。docs/handoff.ja.md「リリース」）:
#   pipeline/review/publish_preview.sh ../ch32-device-data-preview
#   git -C ../ch32-device-data-preview push --force origin main   # push は人が行う
set -eu

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO/.cache/structured-markdown"
DST="${1:?usage: publish_preview.sh <path-to-preview-clone>}"

[ -d "$DST/.git" ] || { echo "$DST is not a git clone" >&2; exit 1; }
if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
    echo "ch32-device-data has uncommitted changes: commit the tables first" >&2
    exit 1
fi
SOURCE="$(git -C "$REPO" rev-parse --short HEAD)"

# 公開の直前に必ず最新へ書き出す（数十秒）。古い Markdown を公開しないため。
echo "re-exporting structured-markdown before publish ..." >&2
( cd "$REPO" && uv run pipeline/review/export_markdown.py --all )

[ -f "$SRC/README.md" ] || { echo "export produced no $SRC/README.md" >&2; exit 1; }

rsync -a --delete --exclude .git "$SRC"/ "$DST"/

cd "$DST"
git checkout -q --orphan preview-next
git add -A
git commit -q -m "structured-markdown preview from ch32-device-data@$SOURCE"
git branch -M preview-next main
echo "committed $(git rev-parse --short HEAD) (ch32-device-data@$SOURCE); push with:" >&2
echo "  git -C $DST push --force origin main" >&2
