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
    if sep and tail:
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

    fixed = FIXED.get(signal)
    if fixed:
        return canonical_peripheral(fixed[0]), fixed[1]
    return None


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
