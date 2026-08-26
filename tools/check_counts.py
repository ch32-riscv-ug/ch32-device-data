#!/usr/bin/env python3
"""比較表が数える周辺の数と、pin表が持つ実際の instance を突き合わせる。

**`pin_functions.csv` は pinout 単位で、型番単位ではありません。** datasheet の
pin 表がそう書いています（CH32V20x_30xDS0 は表の直前に断っている）:

    注意，下表中的引脚功能描述针对的是**所有功能，不涉及具体型号产品**。
    不同型号之间外设资源有差异

同じ pinout を共有する型番は同じ pad 行を読むので、`pin_functions.csv` は
**その silicon が出せる機能の和**になります。どの型番がどれを実際に持つかは
比較表（`product_attributes.csv`）が型番単位で数えます。CH32V303CBT6 は
USART を 3 つしか持ちませんが、pin 表には UART8_TX まで並びます。

そこでこの2つを突き合わせます。**向きで意味が違います。**

    pin の instance 数 > 比較表の数   上位集合として正常（共有 pinout の分）
    pin の instance 数 < 比較表の数   **その封装に出ていない**か、抽出の漏れ

不足のほうが穴の手掛かりになります——比較表が「I2C が 2 つ」と言っているのに
pin 表から I2C2 が1本も取れていなければ、読み落としを疑う入口になります。

実行:
    uv run tools/check_counts.py [--tables tables] [--short]
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

# 比較表が数える周辺のうち、pin に出るので突き合わせられるもの。TIM は比較表が
# 高級/通用/基本と種類で分けて数えるので、instance 番号と対応が取れず外す。
COUNTED = ("USART", "SPI", "I2C", "CAN", "I2S", "ADC", "DAC", "OPA", "CMP", "LPTIM")
# instance は**末尾の数字**。名前の途中に数字を持つ周辺があるので
# （`I2C1` の 2 は名前の一部、`I2S2`・`USBHS` も同型）、先頭を `[A-Z]+` に
# 限ると1つも割れない。
INSTANCE = re.compile(r"^([A-Z0-9]*[A-Z])(\d+)$")
NUMBER = re.compile(r"^\d+$")
# **数えているものが instance ではない行**。比較表は同じ周辺について「何個か」と
# 「何チャネルか」の両方を数え、綴りが似ているので混ざる（`ADC/TKey Unit` と
# `ADC/TKey Channel`）。チャネル数や動作モード数を instance 数と比べても
# 合わないのが当たり前なので外す。
NOT_INSTANCES = re.compile(r"channel|通道|路数|polling|轮询|No\.", re.IGNORECASE)
# **ADC は instance を突き合わせられない。** datasheet はチャネルを `ADC_IN3` /
# `A3` と綴って**どの ADC ユニットのものか書かない**ので、語彙は instance 1 に
# 寄せる（`IMPLIED_INSTANCE`）。pin から ADC2 以降が見えないのは資料の書き方で
# あって漏れではない。
UNCOUNTABLE = frozenset({"ADC"})


# **記録してある実測値。** 目標は「資料のとおり」で、動いたら理由を確かめる。
#
#   superset  共有 pinout の上位集合。CH32V303CBT6 は USART を 3 つしか持たないが
#             pin 表には UART8_TX まで並ぶ（datasheet が「所有功能」と断っている）
#   short     その封装／その silicon で pad に出ていない instance。
#             CMP2（CH32M007・CH32V007）と LPTIM1（CH32H416）で、どちらも
#             入力が内部だけの可能性があり、資料からは漏れと言い切れない
#   empty     比較表が数えているのに instance が1つも出ない。**これは 0 が目標**
KNOWN = {"superset": 30, "short": 9, "empty": 0}




def observed(roles: list[dict]) -> dict[tuple[str, str], set[int]]:
    """(型番, 周辺) → pin に出ている instance 番号。"""
    found: dict[tuple[str, str], set[int]] = collections.defaultdict(set)
    for row in roles:
        name = row["peripheral"]
        m = INSTANCE.match(name)
        if m and m.group(1) in COUNTED:
            found[(row["part_number"], m.group(1))].add(int(m.group(2)))
        elif name in COUNTED:
            found[(row["part_number"], name)].add(1)
    return found


def stated(attributes: list[dict]) -> list[tuple[str, str, int, str]]:
    """(型番, 周辺, 数, ラベル)。数として読める行だけ。"""
    out = []
    for row in attributes:
        value = row["value"].strip()
        if not NUMBER.fullmatch(value):
            continue
        tokens = set(row["attribute"].split("_"))
        if NOT_INSTANCES.search(row["label"]):
            continue
        named = [n for n in COUNTED if n.lower() in tokens and n not in UNCOUNTABLE]
        # **2つ以上の周辺をまとめて数える行は使えない。** `OPA/CMP = 4` の 4 は
        # 対に対する数で、OPA が 4 とも CMP が 4 とも言っていない。片方ずつに
        # 当てると、どちらも合わないのに「漏れ」に見える。
        if len(named) != 1:
            continue
        out.append((row["part_number"], named[0], int(value), row["label"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--short", action="store_true", help="不足の側も1件ずつ出す")
    args = ap.parse_args()

    seen = observed(paths.load_index("pinout"))
    claims = stated(paths.load("product_attributes"))

    agree = superset = missing = 0
    gaps: list[tuple] = []
    for part, name, count, label in claims:
        instances = seen.get((part, name), set())
        if len(instances) == count:
            agree += 1
        elif len(instances) > count:
            superset += 1
        else:
            missing += 1
            gaps.append((part, name, count, sorted(instances), label))

    print(f"突き合わせた組 {len(claims)}  一致 {agree}  "
          f"pin側が多い（共有pinoutの上位集合）{superset}  pin側が少ない {missing}",
          file=sys.stderr)
    empty = [g for g in gaps if not g[3]]
    now = {"superset": superset, "short": missing, "empty": len(empty)}
    moved = [f"{k}: {KNOWN[k]} → {v}" for k, v in now.items() if v != KNOWN[k]]
    if gaps:
        # **1本も取れていないものが最も怪しい。** 比較表がその周辺を数えているのに
        # pin 表から instance が1つも出ないのは、封装の都合というより読み落とし。
        print(f"  - 比較表が数えているのに pin に1つも出ない: {len(empty)} 組",
              file=sys.stderr)
        for part, name, count, _, label in sorted(empty)[:20]:
            print(f"      {part:<14}{name:<6}表={count}  ({label})", file=sys.stderr)
        if args.short:
            for part, name, count, instances, label in sorted(gaps):
                if instances:
                    print(f"      {part:<14}{name:<6}表={count}  pin={instances}",
                          file=sys.stderr)
    if moved:
        print("  - **記録してある実測値から動いた**（tools/check_counts.py の KNOWN）:",
              file=sys.stderr)
        for line in moved:
            print(f"      {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
