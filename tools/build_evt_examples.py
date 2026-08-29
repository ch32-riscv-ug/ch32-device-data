#!/usr/bin/env python3
"""EVTの例題一覧 → tables/evt_examples.csv

各EVTに同梱される目録（`EVT/<name>_List_EN.txt` と中国語版）は、例題ごとに
1行の説明を持つツリーです。これを解析して「どの周辺にどんな例題があるか」を
表にします。EVT展開ツリーの実ディレクトリも突き合わせ、**目録2版と実体の
3つの根拠**で確度を決めます（実体＋どちらかの目録で確定）。

実行: uv run python tools/build_evt_examples.py [--out <dir>]
"""

import argparse
import csv
import re
import sys
from pathlib import Path

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

# 目録の1行。`  |      |-- NAME: description` 形式で、深さは "|" の数で決まる。
# 区切りは半角コロンと全角コロンの両方が使われる（CH32L103は全角）。
ENTRY = re.compile(r"^(?P<indent>[ |]*)\|--\s*(?P<name>[^:：]+?)\s*(?:[:：]\s*(?P<desc>.*))?$")
# 例題ではないディレクトリ（ドライバ・起動ファイル等）
NOT_EXAMPLE = {"SRC", "PUB", "Core", "Debug", "Ld", "Peripheral", "Startup"}
# 目録のグループ名に付く注記。英語版は`BLE ----only for CH32V20x_D8W`、
# 中国語版は全角ダッシュ（`DVP ——仅适用于CH32V30x_D8C`）を使う。
GROUP_NOTE = re.compile(r"\s*(?:[-–]{2,}|—+).*$")
# 目録には説明書PDFなどファイルの行も混ざる。例題はディレクトリだけ。
FILE_LIKE = re.compile(r"\.[A-Za-z0-9]{1,4}(?:-[A-Za-z]{2})?$")
# 中国語版だけが中国語名で書いている項目（英語版は別名、実体も無い）。
# 表示値に中国語は載せられないので落とし、件数だけ報告する。
CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

COLUMNS = ["family", "group", "example", "description",
           "#", "confidence", "basis", "source"]


def parse_list(path):
    """目録テキスト → {(group, example): description}

    EXAM配下の2階層（周辺グループ→例題）を拾う。さらに深い階層は
    `PARENT/CHILD` として親の名前を前置きする。
    """
    # 中国語版の目録はGBK（EVTのZIPがそのまま同梱している）。UTF-8で読めた
    # ものだけUTF-8扱いにし、駄目ならGB18030で読む。全角コロンの区切りが
    # 化けると行全体が名前として取り込まれてしまうため、ここは厳密に扱う。
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gb18030", errors="replace")
    out = {}
    stack = {}  # depth → name
    exam_depth = None
    for raw in text.splitlines():
        m = ENTRY.match(raw.rstrip())
        if not m:
            continue
        depth = m.group("indent").count("|")
        name = m.group("name").strip()
        desc = (m.group("desc") or "").strip()
        stack[depth] = name
        for deeper in [d for d in stack if d > depth]:
            del stack[deeper]

        if name == "EXAM":
            exam_depth = depth
            continue
        if exam_depth is None or depth <= exam_depth:
            continue
        group = GROUP_NOTE.sub("", stack.get(exam_depth + 1, "")).strip()
        if not group or group in NOT_EXAMPLE:
            continue
        if depth == exam_depth + 1:
            continue  # グループ行そのもの
        parts = [GROUP_NOTE.sub("", stack[d]).strip()
                 for d in sorted(stack) if exam_depth + 1 < d <= depth]
        if FILE_LIKE.search(parts[-1]):
            continue  # 説明書PDF等
        out[(group, "/".join(parts))] = desc
    return out


def disk_coverage(evt_dir, keys):
    """目録のキーが実体として存在するか。併せて目録に無いグループ直下も数える。

    例題の階層はグループ直下とは限らない（USB/USBHS/DEVICE/CH372Device）。
    実体側を機械的に走査すると各プロジェクトの内部フォルダまで拾ってしまう
    ため、**目録を索引の権威**として、その相対パスが実在するかを確認する。
    """
    exam = evt_dir / "EXAM"
    present = set()
    if not exam.is_dir():
        return present, []
    # 目録と実体で大小文字が揺れる（目録`TIM_trigger`／実体`TIM_Trigger`）ため
    # 小文字で引き当てる。
    actual = {p.relative_to(exam).as_posix().lower()
              for p in exam.rglob("*") if p.is_dir()}
    for group, example in keys:
        if f"{group}/{example}".lower() in actual:
            present.add((group, example))
    listed_groups = {g for g, _ in keys}
    unlisted = [d.name for d in sorted(exam.iterdir())
                if d.is_dir() and d.name not in NOT_EXAMPLE
                and d.name not in listed_groups]
    return present, unlisted


def main():
    # 他の生成器と同じく試験用の出力先を受ける。受けないと、抽出を変えて様子を
    # 見るのに正本を上書きするしか手が無い（`build_operating.py` で実際に事故った）。
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None,
                    help="出力先のディレクトリを上書きする（試験用）")
    args = ap.parse_args()
    rows = []
    for repo in sorted(MIRRORS.glob("CH32*")):
        evt = repo / "EVT"
        if not evt.is_dir():
            continue
        lists = {}
        for path in sorted(evt.glob("*List*.txt")):
            lang = "en" if re.search(r"[-_]EN\.txt$", path.name, re.I) else "zh"
            lists[lang] = (path.name, parse_list(path))
        keys = set()
        for _, entries in lists.values():
            keys |= set(entries)
        if not keys:
            print(f"{repo.name}: EVT目録が読めない", file=sys.stderr)
            continue
        chinese = {k for k in keys if CJK.search(k[0]) or CJK.search(k[1])}
        if chinese:
            keys -= chinese
            print(f"{repo.name}: 中国語名のみの項目を除外 "
                  f"{sorted(e for _, e in chinese)}", file=sys.stderr)
        disk, unlisted = disk_coverage(evt, keys)
        if unlisted:
            print(f"{repo.name}: 目録に無いグループ {unlisted}", file=sys.stderr)
        for group, example in sorted(keys):
            evidence = []
            if (group, example) in disk:
                evidence.append("evt:tree")
            for lang, (name, entries) in sorted(lists.items()):
                if (group, example) in entries:
                    evidence.append(f"evt:list-{lang}")
            # 表示は英語のみ。中国語版にしか説明が無い場合は空にし、
            # 中国語の存在自体は basis の evt:list-zh が示す。
            description = lists.get("en", ("", {}))[1].get((group, example), "")
            rows.append({
                "family": repo.name, "group": group, "example": example,
                "description": description, "#": "#",
                "confidence": "confirmed" if len(evidence) >= 2 else "reference",
                "basis": "+".join(evidence),
                "source": lists.get("en", lists.get("zh", ("", {})))[0],
            })

    rows.sort(key=lambda r: (r["family"], r["group"], r["example"]))
    dest = paths.table("evt_examples", args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    shown = dest.relative_to(REPO) if dest.is_relative_to(REPO) else dest
    print(f"{shown}: {len(rows)} 行",
          dict(Counter(r["confidence"] for r in rows)))


if __name__ == "__main__":
    main()
