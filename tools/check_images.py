#!/usr/bin/env python3
"""READMEが参照する画像の必要一覧と、各リポジトリでの有無を報告する。

READMEは画像の存在を確認してから節を出すのではなく、**決まった名前の画像を
常に参照**します。よって「どの名前の画像を作ればよいか」はデータから機械的に
決まります。このツールがその一覧です。

  image/architecture_<SERIES>.png       シリーズごとの内部ブロック図
  image/pinout_<PART>_<PACKAGE>.png     ピン配置図。ピン配置が実際に異なる
                                        単位で1枚（同一配置の型番は共有し、
                                        名前はその中で最小の型番を使う）

パッケージの外形寸法図はチップに依らないため各リポジトリには置かず、
WCH-common に1枚ずつ置いて全リポジトリから参照します。

  WCH-common/image/package_<PACKAGE>.png

実行: uv run python tools/check_images.py [--missing]
"""

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

MIRRORS = Path("/home/mt/dev_wch")
REPO = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402


def load(name):
    with paths.table(name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pinout_groups():
    """{(family, filename): [part_number, ...]} — 実際に異なる配置ごとに1枚。"""
    pads = defaultdict(dict)
    for r in load("pins"):
        pads[r["part_number"]][r["pin"]] = r["pad"]
    groups = defaultdict(list)
    for p in load("products"):
        signature = tuple(sorted(pads[p["part_number"]].items()))
        # シリーズは鍵に入れない。CH32V303/305/307 の LQFP64M のように、
        # 配置が同じならデータシートも図を1枚しか描かない。
        groups[(p["family"], p["package"], signature)].append(p["part_number"])
    out = {}
    for (family, package, _), parts in groups.items():
        lead = sorted(parts)[0]
        out[(family, f"pinout_{lead}_{package}.png")] = sorted(parts)
    return out


def required():
    """{family: {filename: 説明}}"""
    need = defaultdict(dict)
    for s in load("series"):
        need[s["family"]][f"architecture_{s['series']}.png"] = (
            f"{s['series']} internal block diagram")
    for (family, name), parts in pinout_groups().items():
        need[family][name] = "pinout: " + ", ".join(parts)
    for p in load("packages"):
        need["WCH-common"][f"package_{p['package']}.png"] = (
            f"{p['package']} package outline"
            + (f" ({p['body_size']})" if p.get("body_size") else ""))
    return need


def suspicious(path, edge_ratio=0.015):
    """切り出しに失敗した疑いのある画像を、目視の前に拾う。

    - 断片だけ取れた場合は極端に小さいか細長くなる
    - 図が切れている／隣の図が入り込んでいる場合は、画像の最外周にインクが
      並ぶ。枠線が1本触れているだけの正常な図と区別するため、辺の長さに
      対する割合で判定する
    """
    try:
        from PIL import Image
        image = Image.open(path).convert("L")
    except Exception as exc:
        return f"読めない ({exc})"
    width, height = image.size
    if width < 300 or height < 200:
        return f"小さすぎる ({width}x{height})"
    ratio = height / width
    if ratio > 3 or ratio < 0.12:
        return f"細長い ({width}x{height})"

    px = image.load()
    counts = {"上": 0, "下": 0, "左": 0, "右": 0}
    for x in range(width):
        counts["上"] += px[x, 0] < 200
        counts["下"] += px[x, height - 1] < 200
    for y in range(height):
        counts["左"] += px[0, y] < 200
        counts["右"] += px[width - 1, y] < 200
    hits = [f"{side}{counts[side]}px" for side, length in
            (("上", width), ("下", width), ("左", height), ("右", height))
            if counts[side] > length * edge_ratio]
    if hits:
        return "縁にインクが接している (" + ", ".join(hits) + ")"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--missing", action="store_true",
                    help="未作成のファイルだけを出す")
    ap.add_argument("--prune", action="store_true",
                    help="READMEから参照されない画像を削除する")
    ap.add_argument("--with-pinouts", action="store_true",
                    help="ピン配置図も必要一覧に含める（現在READMEは未使用）")
    args = ap.parse_args()

    need = required()
    if not args.with_pinouts:
        need = {family: {n: d for n, d in names.items()
                         if not n.startswith("pinout_")}
                for family, names in need.items()}
    total = missing_total = suspicious_total = 0
    for family in sorted(need):
        image_dir = MIRRORS / family / "image"
        have = {p.name for p in image_dir.iterdir()} if image_dir.is_dir() else set()
        rows = sorted(need[family].items())
        missing = [(n, d) for n, d in rows if n not in have]
        total += len(rows)
        missing_total += len(missing)
        extra = sorted(h for h in have
                       if h not in need[family] and not h.startswith("."))
        print(f"== {family}: 必要 {len(rows)} / 未作成 {len(missing)}")
        for name, description in (missing if args.missing else rows):
            mark = " " if name in have else "*"
            print(f"  {mark} {name:44} {description}")
        for name, _ in rows:
            path = image_dir / name
            if path.exists():
                note = suspicious(path)
                if note:
                    print(f"    要確認 {name}: {note}")
                    suspicious_total += 1
        if extra:
            print(f"    参照されない既存ファイル: {', '.join(extra)}")
            if args.prune:
                for name in extra:
                    (image_dir / name).unlink()
                print(f"    → {len(extra)} 件を削除しました")
    # 同じ切り出しを複数の名前で共有している箇所。データシートが1枚の図で
    # 複数のパッケージを兼ねている場合（CH32V103Cx）は正常だが、取り違えて
    # 同じ図を書いてしまった場合もこれで見える。
    import hashlib
    from collections import defaultdict
    same = defaultdict(list)
    for family in need:
        image_dir = MIRRORS / family / "image"
        for name in need[family]:
            path = image_dir / name
            if path.exists():
                same[hashlib.md5(path.read_bytes()).hexdigest()].append(
                    f"{family}/{name}")
    shared = [names for names in same.values() if len(names) > 1]
    if shared:
        print("\n同じ切り出しを共有している画像:")
        for names in shared:
            print("  - " + ", ".join(names))

    print(f"\n合計: 必要 {total} / 未作成 {missing_total} "
          f"/ 要確認 {suspicious_total}")


if __name__ == "__main__":
    main()
