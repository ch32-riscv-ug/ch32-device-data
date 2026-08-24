#!/usr/bin/env python3
"""機能から pad を引くための索引 → tables/pin_roles.csv

`pin_functions.csv` は **資料が綴ったままの signal 名**を持つ。綴りは証拠なので
それでよいのだが、同じ役割が資料ごとに違う名前で出る:

    USART1_TX (CH32V307) / TX1 (CH32X035) / UTX (CH32V003) / UART_TX (CH32M030)
    SWDIO     (ほとんど) / DIO (CH32X033・X035 は凡例で対応を書いている)

そのため「USART1 の TX はどの pad か」を引くたびに、読む側が4通りの綴りを知って
いなければならなかった。実際 README の生成側がそれを抱え込み、`UART_TX` を
取りこぼして CH32M030 の欄が空になり、pad 名を条件に混ぜたせいで 2 線式 SDI の
family 全部で SWDIO の欄が空になっていた。

**この表は綴りを揃えた側の引き口**で、`tools/signal_vocabulary.py` の規則を
通した (peripheral, role) を持つ。読む側は素直に選ぶだけでよくなる。

**新しい事実は足さない。** `pin_functions.csv` の行を語彙で言い換えるだけで、
覆えない行は載せない——載せるとしたら語彙か抽出を直すのが筋で、ここで補うと
資料に無いものが表に生まれる。覆えなかった数は毎回出すので、穴は数で見える
（`tools/check_tables.py` が現在値と突き合わせる）。

    routing   default / main / remap-N / af-N   どの経路で出るか
    signal    資料が綴ったままの名前            層1 へ戻る手がかり

実行:
    uv run tools/build_pin_roles.py [--out tables]
"""

from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import signal_vocabulary  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

COLUMNS = ["part_number", "series", "family", "peripheral", "role", "pad",
           "routing", "signal", "#", "confidence", "basis"]


def roles(functions: list[dict], catalogue: dict) -> tuple[list[dict], collections.Counter]:
    """(索引の行, 語彙で覆えなかった {(datasheet, signal): 行数})。

    `tools/check_tables.py` が同じ計算をして、覆えない数が増えていないかを見る。
    """
    rows: list[dict] = []
    unresolved: collections.Counter = collections.Counter()
    for fn in functions:
        # **pad 自身の名前は役割ではない。** `PA9` の主機能が `PA9`、`VSS` の
        # 主機能が `VSS` と書かれるのは、その pad が何であるかを言っているだけ。
        # pad 名と違う綴りでも同じことが起きる——`PC13-RTC` の主機能は `PC13`、
        # `OSC_IN` の主機能は `PD0` で、どちらもその pad の GPIO としての名前。
        # 載せると「PC13 という周辺の PC13 という役割」が索引に生まれる。
        if fn["route"] == "main" and fn["signal"] == fn["pad"]:
            continue
        if signal_vocabulary.is_pad_name(fn["signal"]):
            continue
        pair = signal_vocabulary.split(fn["signal"])
        if not pair:
            unresolved[(fn["datasheet"], fn["signal"])] += 1
            continue
        product = catalogue.get(fn["part_number"])
        if not product:
            continue
        rows.append({
            "part_number": fn["part_number"],
            "series": product["series"],
            "family": product["family"],
            "peripheral": pair[0],
            "role": pair[1],
            "pad": fn["pad"],
            "routing": fn["route"],
            # 層1 へ戻る手がかり。綴りは資料のまま。
            "signal": fn["signal"],
            "confidence": fn["confidence"],
            "basis": fn["basis"],
        })

    rows.sort(key=lambda r: (r["part_number"], r["peripheral"], r["role"],
                             r["pad"], r["routing"]))
    return rows, unresolved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "tables")
    args = ap.parse_args()

    with (args.out / "products.csv").open(newline="", encoding="utf-8") as f:
        catalogue = {r["part_number"]: r for r in csv.DictReader(f)}
    with (args.out / "pin_functions.csv").open(newline="", encoding="utf-8") as f:
        functions = list(csv.DictReader(f))

    rows, unresolved = roles(functions, catalogue)
    dest = args.out / "pin_roles.csv"
    with dest.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**row, "#": "#"} for row in rows)

    total = len(rows) + sum(unresolved.values())
    print(f"{dest}: {len(rows)} 行 / 語彙で覆えた {len(rows)}/{total} "
          f"({len(rows) / total:.1%})", file=sys.stderr)
    if unresolved:
        names = collections.Counter()
        for (_, signal), count in unresolved.items():
            names[signal] += count
        print(f"  - 語彙に無い signal {len(names)} 種 / {sum(unresolved.values())} 行"
              "（`tools/signal_vocabulary.py` に規則を足すか、抽出を直す）:",
              file=sys.stderr)
        for signal, count in names.most_common(15):
            print(f"      {signal} ×{count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
