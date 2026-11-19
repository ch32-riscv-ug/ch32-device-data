"""並列で走らせる worker の数の既定値（build_all・convert_all）。

コア数だけで決めると、同じ機械でほかの作業（別の repository のビルド・試験）が走っているときに、
worker どうしとほかの作業が CPU を取り合い、全体が遅くなる（4 コアで load average 14 のとき、
build_all の 3 worker は各 40% しか回らなかった。2026-11-19）。**そのときの空きコア**
（コア数 − 1分間の load average）で上限を下げ、混んでいれば 1 本にする。出力は worker の数に
よらない。

>>> default_workers(cap=6, cpus=4, load=0.3)
3
>>> default_workers(cap=6, cpus=4, load=2.6)
1
>>> default_workers(cap=6, cpus=4, load=14.2)
1
>>> default_workers(cap=6, cpus=16, load=1.0)
6
"""

from __future__ import annotations

import math
import os


def default_workers(cap: int, cpus: int | None = None, load: float | None = None) -> int:
    """`min(cap, コア数 − 1, 空きコア)`、少なくとも 1。"""
    cpus = cpus if cpus is not None else (os.cpu_count() or 2)
    if load is None:
        try:
            load = os.getloadavg()[0]
        except OSError:   # load average を持たない OS
            load = 0.0
    free = math.floor(cpus - load)
    return max(1, min(cap, cpus - 1, free))
