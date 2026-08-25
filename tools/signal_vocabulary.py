#!/usr/bin/env python3
"""Read a datasheet signal name as (peripheral, role).

The remap tables keep every signal exactly as its document spells it, because the
spelling is evidence. That leaves the same role written several ways:

    CH32V307   USART1_TX      the peripheral and the role, both spelled out
    CH32M030   UART_TX        the peripheral's first instance left unnumbered
    CH32X035   TX1            the datasheet's own shorthand
    CH32V003   UTX            the same shorthand with the instance implied

A consumer that wants "the TX pad of USART2" has to read all four. This module is
the one place that knows how, so the tables can carry a normalised (peripheral,
role) pair beside the verbatim name instead of every reader re-deriving it.

Only three series use shorthand -- CH32V003, CH32X033 and CH32X035 -- and within a
series the datasheet is consistent, so these are vocabulary rules rather than a
per-signal dictionary. A name no rule covers returns None: an empty pair says "not
decided", which a consumer can skip, and that is more useful than a wrong guess.

    >>> split("TX2")
    ('USART2', 'TX')
    >>> split("T1C1N")
    ('TIM1', 'CH1N')
    >>> split("UART5_TX")
    ('USART5', 'TX')
    >>> split("PIOC_IO0")
    ('PIOC', 'IO0')
    >>> split("LPT_OUT")
    ('LPTIM', 'OUT')
    >>> split("AETR2") is None
    True
    >>> split("A10")
    ('ADC1', 'IN10')
    >>> split("C3N0")
    ('CMP3', 'N0')
    >>> split("O2O0")
    ('OPA2', 'OUT0')
    >>> split("OPO")
    ('OPA1', 'OUT')
    >>> split("MCO")
    ('RCC', 'MCO')
    >>> split("XO")
    ('OSC', 'OUT')
    >>> is_pad_name("PC13")
    True
"""

from __future__ import annotations

import re

# The instance number is the trailing digits only; I2C and I2S carry digits inside
# the name itself.
INSTANCE = re.compile(r"^([A-Z][A-Z0-9]*?)(\d*)$")

# Peripherals the documents number from 1 but leave unnumbered for the first
# instance: CH32M030 writes SPI_MISO and UART_TX for its only SPI and only UART,
# while CH32V307 writes SPI1_MISO and USART1_TX. Reading the missing number as 1
# makes the two comparable. Every name here is one that appears both ways across
# the corpus, or always with a number; peripherals that are never numbered
# (ETH, SDMMC, UHSIF, LPTIM, PIOC, I2S) keep the spelling they are given.
IMPLIED_INSTANCE = frozenset({"USART", "UART", "SPI", "I2C", "TIM", "CAN", "ADC"})

# WCH calls the same peripheral both things, sometimes within one series. CH32V307
# writes UART5_TX in its pin table and USART5_REMAP in its AFIO register, CH32M030
# writes UART_TX and UART1_REMAP, and CH32L103 writes LPT_OUT in its pin table for
# the field it calls LPTIM_RM. Folding one onto the other is what makes a signal
# find its own selector. Each pair is safe because no family defines both
# spellings as AFIO fields -- checked across all twelve EVT headers -- so the two
# never name different peripherals on the same silicon.
SAME_PERIPHERAL = {"UART": "USART", "LPT": "LPTIM"}

# Serial roles, in both the long and the shorthand spelling. The shorthand takes
# the instance as a trailing digit (TX2) or leaves it implied behind a U (UTX).
SERIAL_ROLES = ("TX", "RX", "CK", "CTS", "RTS")
SERIAL = re.compile(rf"^U?(?P<role>{'|'.join(SERIAL_ROLES)})(?P<n>\d?)$")

# TIM roles. The datasheets shorten CH to C, BKIN to BK and ETR to ET, and write
# the timer instance as a bare digit after T.
TIMER_CHANNEL = re.compile(r"^T(?P<n>\d)C(?:H)?(?P<ch>\d)(?P<neg>N?)$")
TIMER_COMBINED = re.compile(r"^T(?P<n>\d)C(?:H)?(?P<ch>\d)ETR$")
TIMER_OTHER = re.compile(r"^T(?P<n>\d)(?P<role>BK(?:IN)?|ET(?:R)?)$")
TIMER_ROLE = {"BK": "BKIN", "BKIN": "BKIN", "ET": "ETR", "ETR": "ETR"}

# Roles that name their peripheral only by convention.
FIXED = {
    "SCL": ("I2C", "SCL"),
    "SDA": ("I2C", "SDA"),
    "MISO": ("SPI", "MISO"),
    "MOSI": ("SPI", "MOSI"),
    "SCK": ("SPI", "SCK"),
    "NSS": ("SPI", "NSS"),
    # The pin tables call SPI's slave select CS; the register descriptions and
    # every other series call it NSS.
    "CS": ("SPI", "NSS"),
    # **CH32X033/X035 の凡例がそのまま書いている。** ピン表は略記で書き、同じ
    # ページに対応を並べる:
    #
    #     CS:SPI_NSS   UDP:USBDP   UDM:USBDM   DIO:SWDIO   DCK:SWCLK
    #
    # 略記のままだと、他の family が `SWDIO` と綴る同じ pad が結合できない
    # ——CH32X035 の SWD pad が pins.html に出ていなかったのがこれ。
    "DIO": ("SDI", "SWDIO"),
    "DCK": ("SDI", "SWCLK"),
    "UDP": ("USB", "DP"),
    "UDM": ("USB", "DM"),
    # 綴り切った側も同じ対に寄せる。1線式（CH32V003 系）は SWIO だけを持つ。
    "SWDIO": ("SDI", "SWDIO"),
    "SWCLK": ("SDI", "SWCLK"),
    "SWIO": ("SDI", "SWDIO"),
}


# **CH32X033/X035 のピン図の凡例がそのまま規則を書いている**（datasheet p.16）:
#
#     A:ADC_   (A10:ADC_IN10)
#     C:CMP_   (C3N0:CMP3_N0)
#     T:TIME_  (T2C4:TIM2_CH4、T2C2N:TIM2_CH2N)
#     O:OPA_   (O1N2:OPA1_N2、O2O0:OPA2_OUT0)
#
# 番号の付き方が3通りある——ADC は instance を持たず channel だけ、CMP と OPA は
# 「instance＋端子の種類＋その番号」。`O` の綴りだけ役割名が伸びる（OUT）のは
# 凡例が `O2O0:OPA2_OUT0` と書いているとおり。EVT header の
# `CMP_STATR_CMP1_OUT` も CMP 側の出力が OUT であることを裏付ける。
ADC_CHANNEL = re.compile(r"^A(?P<ch>\d{1,2})$")
ANALOG_UNIT = re.compile(r"^(?P<kind>[CO])(?P<unit>\d)(?P<role>[NPO])(?P<n>\d?)$")
ANALOG_PERIPHERAL = {"C": "CMP", "O": "OPA"}
# CH32V003 は OPA を1つしか持たないので instance を書かない。
V003_OPA = re.compile(r"^OP(?P<role>[NPO])(?P<n>\d?)$")

# 周辺が持つのではなく**チップが持つ**端子。周辺名が無いので `SYS` でまとめる
# ——`OSC_IN` が `(OSC, IN)` に割れるのと同じで、`_` の左に相当するものを置く。
SYSTEM = {
    # リセット。`RST` と綴る family と `NRST` と綴る family がある。
    "RST": ("SYS", "NRST"),
    "NRST": ("SYS", "NRST"),
    "BOOT0": ("SYS", "BOOT0"),
    "BOOT1": ("SYS", "BOOT1"),
    # 高速外部発振子。`OSC_IN`/`OSC_OUT` と綴る family は `_` があるので既に
    # `(OSC, IN)` に割れている。同じ端子を CH32H417 は pad 名ごと `XI`/`XO`、
    # CH32V003 は `OSCI`/`OSCO` と綴るので、そちらへ寄せる。
    "XI": ("OSC", "IN"),
    "XO": ("OSC", "OUT"),
    # **`X0` は `XO` の綴り違い。** CH32V002/V004/V006 の PA2 に両方の綴りで
    # 現れる（同じ pad なので O と 0 の取り違え）。
    "X0": ("OSC", "OUT"),
    "OSCI": ("OSC", "IN"),
    "OSCO": ("OSC", "OUT"),
    # クロック出力。EVT header の `RCC_MCO_SYSCLK` が RCC のものだと言っている。
    "MCO": ("RCC", "MCO"),
    # 起床端子。EVT header の `PWR_WakeUpPinCmd` が PWR のものだと言っている。
    "WKUP": ("PWR", "WKUP"),
    # USB の差動対。`UDP`/`UDM` の綴り切った側（FIXED にある）と同じ対。
    "USBDP": ("USB", "DP"),
    "USBDM": ("USB", "DM"),
    # CH32V103 は USB を USBHD と呼ぶ（比較表の `通信接口 USB(FS) USBHD`）。
    "USBHDP": ("USBHD", "DP"),
    "USBHDM": ("USBHD", "DM"),
    # Ethernet の LED。CH32V407 の注記が `register FEATURE_SIGN` の
    # `ETH_LED_EN` で有効になると書いていて、持ち主が ETH だと分かる。
    "LED0": ("ETH", "LED0"),
    "LED1": ("ETH", "LED1"),
    # PC13 が持つ RTC の2つの端子。改竄検知の入力と RTC の出力。
    "TAMPER": ("RTC", "TAMPER"),
    "RTC": ("RTC", "OUT"),
}

# **1つの綴りが2つの役割を名指しすることがある。** PC13 は改竄検知の入力と
# RTC の出力を兼ねていて、CH32L103 の pin 表は `TAMPER` と `RTC` を改行で分けて
# 書くのに、CH32V103/V20x/V30x/V4x7 は `TAMPER-RTC` と1語で書く。同じ silicon の
# 同じ pad なので、綴りが違うだけで指しているものは同じ。
COMPOUND = {
    "TAMPER-RTC": (("RTC", "TAMPER"), ("RTC", "OUT")),
}

# 役割ではない綴り。`NC` は「どこにも繋がっていない」という pad についての
# 断り書きで、周辺の機能ではない。
NOT_A_ROLE = frozenset({"NC"})
# Type-C の構成チャネル。比較表が `PDUSB USBPD Type-C` の行で数える周辺。
# CH32M030 は同じ端子を `CC1(CC1R)` と書く——括弧の中は「Rd を内蔵した側の
# 呼び名」で（datasheet p.16「PA0/CC1R and PA1/CC2R pins have built-in
# controllable Rd」）、指しているのは同じ CC1。
TYPE_C = re.compile(r"^CC(?P<n>[1-4])(?:\([A-Z0-9]+\))?$")
# CH32X315 の ADC スキャン回数出力。datasheet p.12 が
# 「the round count can be output through GPIO (ADCS0/PA10, ...)」と書く。
ADC_SCAN = re.compile(r"^ADCS(?P<n>\d)$")

# **pad 自身の GPIO 名は役割ではない。** ピン表の「リセット後の主機能」欄は
# `PC13-RTC` のような pad に `PC13` と書く——その pad が GPIO であること自体を
# 言っているだけで、周辺の役割ではない。`pin_roles` に載せると
# 「PC13 という周辺の PC13 という役割」が生まれてしまう。
GPIO_NAME = re.compile(r"^P[A-Z]\d{1,2}$")


def is_pad_name(signal: str) -> bool:
    """pad 自身の GPIO 名か。役割ではないので索引に載せない。"""
    return bool(GPIO_NAME.match(signal))


def canonical_peripheral(token: str) -> str:
    """Spell a peripheral with its instance number present where one is implied."""
    m = INSTANCE.match(token)
    if not m:
        return token
    name, digits = m.groups()
    # Fold the alternative spelling before deciding whether an instance number is
    # implied, because the two spellings need not agree about that: LPT is the
    # unnumbered LPTIM, and LPTIM is never numbered, while UART is USART, which
    # always is.
    name = SAME_PERIPHERAL.get(name, name)
    if not digits and name not in IMPLIED_INSTANCE:
        return name
    return f"{name}{digits or '1'}"


# A selector field's name, minus the suffix that says it is one: USART1_RM,
# I2C1_REMAP. A field split across two registers names its upper half three ways,
# and all three fold onto the name of the field they belong to:
#   CH32L103 header    USART1_RM_H    the _H suffix
#   CH32V30x header    USART1_REMAP   the same name in the other register
#   CH32V20x manual    USART1_RM1     the field name plus the bit's index
FIELD_SUFFIX = re.compile(r"_(?:RM|REMAP)(?:_H|\d)?$")


def canonical_field(field: str) -> str:
    """The name two documents agree on for a selector field.

    Used as a join key between the EVT header, the manual's register table and the
    manual's remap grid, which suffix and number the same field differently.
    """
    base = FIELD_SUFFIX.sub("", field)
    head, _, tail = base.partition("_")
    return canonical_peripheral(head) + (f"_{tail}" if tail else "")


def split(signal: str) -> tuple[str, str] | None:
    """(peripheral, role) for a signal name, or None where no rule applies."""
    head, sep, tail = signal.partition("_")
    # **1文字は周辺の名前ではない。** `PERIPHERAL_ROLE` の形をしていない signal を
    # `_` で割ると、CH32M030 の `Q_DET1`（電荷検出）が「Q という周辺の DET1」に、
    # `V_DET` が「V という周辺」になる。`extract_pins.stem()` が同じ理由で同じ
    # 条件を持っている。覆えないものは覆えないと出るほうが使える。
    if sep and tail and len(head) > 1:
        return canonical_peripheral(head), tail

    m = SERIAL.match(signal)
    if m:
        # CH32M030 numbers its UART selector but not its UART signals, so the
        # peripheral name has to come from somewhere; USART is what every series
        # that spells the peripheral out uses alongside this shorthand.
        return f"USART{m.group('n') or '1'}", m.group("role")

    m = TIMER_CHANNEL.match(signal)
    if m:
        return f"TIM{m.group('n')}", f"CH{m.group('ch')}{m.group('neg')}"

    m = TIMER_COMBINED.match(signal)
    if m:
        # One pad carrying both the channel and the external trigger; the
        # documents write it as one signal and the records keep it that way.
        return f"TIM{m.group('n')}", f"CH{m.group('ch')}_ETR"

    m = TIMER_OTHER.match(signal)
    if m:
        return f"TIM{m.group('n')}", TIMER_ROLE[m.group("role")]

    fixed = FIXED.get(signal) or SYSTEM.get(signal)
    if fixed:
        return canonical_peripheral(fixed[0]), fixed[1]

    m = ADC_CHANNEL.match(signal)
    if m:
        # 凡例の `A10:ADC_IN10`。ADC は instance を書かないので 1 に補う。
        return canonical_peripheral("ADC"), f"IN{m.group('ch')}"

    m = ANALOG_UNIT.match(signal)
    if m:
        role = "OUT" if m.group("role") == "O" else m.group("role")
        name = ANALOG_PERIPHERAL[m.group("kind")] + m.group("unit")
        return name, f"{role}{m.group('n')}"

    m = V003_OPA.match(signal)
    if m:
        role = "OUT" if m.group("role") == "O" else m.group("role")
        return "OPA1", f"{role}{m.group('n')}"

    m = TYPE_C.match(signal)
    if m:
        return "USBPD", f"CC{m.group('n')}"

    m = ADC_SCAN.match(signal)
    if m:
        return canonical_peripheral("ADC"), f"S{m.group('n')}"
    return None


def roles(signal: str) -> list[tuple[str, str]]:
    """この綴りが名指す (peripheral, role) の全部。規則が当たらなければ空。

    ほとんどは1つだが、`TAMPER-RTC` のように資料が2つを1語で書くことがある
    （`COMPOUND`）。索引はそのどちらでも引けるべきなので、両方返す。
    """
    if signal in NOT_A_ROLE or is_pad_name(signal):
        return []
    compound = COMPOUND.get(signal)
    if compound:
        return list(compound)
    pair = split(signal)
    return [pair] if pair else []


def canonical(signal: str) -> str | None:
    """The signal spelled PERIPHERAL_ROLE, or None where no rule applies."""
    pair = split(signal)
    return f"{pair[0]}_{pair[1]}" if pair else None


def comparable(signal: str) -> str:
    """The name to match two documents on, falling back to the verbatim spelling.

    Used for joining, where a name no rule covers must still compare equal to
    itself rather than collapsing every unknown into one bucket.
    """
    return canonical(signal) or signal


def _rules() -> list[tuple[str, str]]:
    """The rules as text, so they can be printed instead of transcribed."""
    roles = "|".join(SERIAL_ROLES)
    return [
        (f"U?({roles})n", "USARTn_*  (nが無ければinstance 1: UTX -> USART1_TX)"),
        ("TxCy / TxCHy / +N", "TIMx_CHy[N]"),
        ("TxCyETR / TxCHyETR", "TIMx_CHy_ETR  (1 padがchannelとETRを兼ねる合成名)"),
        ("TxBK / TxBKIN", "TIMx_BKIN"),
        ("TxET / TxETR", "TIMx_ETR"),
        ("SCL / SDA", "I2C1_*"),
        ("MISO / MOSI / SCK / NSS", "SPI1_*"),
        ("CS", "SPI1_NSS  (pin表だけがCSと書く)"),
        ("PERIPHERAL_ROLE", "そのまま。instance番号は " + " ".join(sorted(IMPLIED_INSTANCE))
                            + " にだけ補う"),
        (" / ".join(f"{k}->{v}" for k, v in sorted(SAME_PERIPHERAL.items())),
         "同じ周辺の別綴り。pin表とAFIOフィールドで綴りが違う"),
    ]


def main() -> int:
    import argparse
    import collections
    import csv
    import doctest
    import pathlib

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", type=pathlib.Path,
                    help="remap_routes.csv を読んで規則の当たり具合を出す")
    args = ap.parse_args()

    print("語彙規則:")
    for pattern, meaning in _rules():
        print(f"  {pattern:26} -> {meaning}")

    failures, _ = doctest.testmod(verbose=False)
    print(f"\ndoctest: {'失敗 ' + str(failures) if failures else '全件通過'}")

    if args.tables:
        rows = list(csv.DictReader((args.tables / "remap_routes.csv").open(encoding="utf-8")))
        total = collections.Counter()
        undecided: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for r in rows:
            total[r["series"]] += 1
            if split(r["signal"]) is None:
                undecided[r["series"]][r["signal"]] += 1
        covered = len(rows) - sum(sum(c.values()) for c in undecided.values())
        print(f"\nremap_routes.csv {len(rows)} 行中 {covered} 行に規則が当たる")
        for series in sorted(undecided):
            names = ", ".join(f"{s}×{n}" for s, n in sorted(undecided[series].items()))
            print(f"  {series}: 未決 {sum(undecided[series].values())}/{total[series]}  {names}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
