#!/usr/bin/env python3
"""比較表の属性を「型番 × 能力」の縦持ちにする → index/capabilities.csv

`evidence/product_attributes.csv` は資料の比較表を**綴りのまま**縦に持っています
（1,721行・158種類の属性）。同じ「SPI が何本か」を family ごとに `spi`・
`communication_interface_spi`・`communication_interfaces_spi` と別の鍵で書くので、
横断で引くには158種類の綴りを利用者が知っている必要がありました。

そこで**能力の語彙に寄せた索引**を作ります。`index/parts.csv` は横長の比較表で、
列に持てるのは13種類だけです。残り145種類は行に落とすほうが引けます:

    ADC を2基以上持ち、CAN FD と USBHS がある型番
    32bit の general-purpose timer を持つ family
    USB host と USB PD の両方がある型番

**新しい事実は足しません。** やるのは名前を揃えることと、値が素の整数なら
`count` にも入れておくことだけ。値は `value` に資料の綴りのまま残ります
（索引の共通規則。`index/README.md`）。

**行があること自体が「持っている」の主張**です。比較表が `-` と書いたセルは
`product_attributes` の時点で落ちているので、この索引にも現れません。ただし
**その読みが効くのは family の中だけ**です——ある属性の行が無いのは「その型番が
持っていない」か「その family の比較表にその行が無い」かのどちらかで、
表からは区別できません。family をまたいで「持っていない型番」を数えないこと。

実行:
    uv run tools/build_capabilities.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

CAPABILITY_COLUMNS = ["part_number", "series", "family", "capability", "qualifier",
                      "stated", "count", "value", "attribute", "#", "confidence", "basis"]

# `evidence/product_attributes.attribute` → `capability` または `capability:qualifier`。
#
# **regex ではなく総当たりの辞書**にしてあります。綴りは資料の見出しから機械的に
# 作った鍵で、`adc`（チャネル数）と `adc_unit`（ユニット数）のように**似た綴りで
# 意味が違う**ものが混ざるため、規則で畳むと静かに間違えます。ここに無い属性が
# 現れたら生成が落ちるので、新しい family を読んだときに必ず人の目を通ります。
#
# `qualifier` は**資料自身がその能力の中で付けている区別**（bit幅・instance名・
# `include PHY`・host/device）だけを持ちます。綴りの違い（`USART` と `USART/UART`）は
# 区別ではないので `attribute` 列に残します。
CAPABILITIES: dict[str, str] = {
    # -------- serial / bus
    "usart": "usart",
    "serial_port": "usart",
    "communication_interface_usart": "usart",
    "communication_interface_usart_uart": "usart",
    "communication_interfaces_usart_uart": "usart",
    "communication_interface_uart": "usart:uart",
    "spi": "spi",
    "communication_interface_spi": "spi",
    "communication_interfaces_spi": "spi",
    "communication_interfaces_i2s": "i2s",
    # 「SPI/I2S」を1つのセルで数える family がある（値 `3/2`）。どちらが何本かは
    # 資料が並べているだけなので分解せず、その能力として持つ。
    "spi_i2s": "spi-i2s",
    "i2c": "i2c",
    "communication_interface_i2c": "i2c",
    "communication_interfaces_i2c": "i2c",
    "i3c": "i3c",
    "can": "can",
    "communication_interface_can": "can",
    "communication_interfaces_can": "can",
    "communication_interface_can_fd": "can-fd",
    "ethernet": "ethernet",
    "communication_interface_ethernet": "ethernet",
    "communication_interfaces_ethernet": "ethernet",
    "communication_interfaces_ble_5_3": "ble",
    "sdio": "sdio",
    "communication_interfaces_sdio": "sdio",
    "sdmmc": "sdmmc",
    "qspi": "qspi",
    "fsmc": "fsmc",
    "fmc_fsmc": "fsmc",
    "communication_interfaces_fsmc": "fsmc",
    "fmc_sdram": "sdram",
    "swpmi": "swpmi",
    "serdes": "serdes",
    "pioc": "pioc",
    "pioc_1_wire_interface": "pioc",
    "uhsif": "uhsif",
    # -------- USB
    "usb_device": "usb:device",
    "pdusb_usb_host": "usb:host",
    "communication_interface_pdusb_usb_host_device": "usb:host-device",
    "pdusb_usbfs": "usb-fs",
    "communication_interface_pdusb_usbfs": "usb-fs",
    "pdusb_usbfs_otg_fs": "usb-fs:otg",
    "communication_interface_usb_fs_usbd": "usb-fs:usbd",
    "communication_interfaces_usb_fs_usbd": "usb-fs:usbd",
    "communication_interface_usb_fs_usbhd": "usb-fs:usbhd",
    "communication_interfaces_usb_fs_usbhd": "usb-fs:usbhd",
    "communication_interface_usbhd_2_0fs": "usb-fs:usbhd",
    "pdusb_usbhs": "usb-hs",
    "pdusb_usbhs_usb_2_0": "usb-hs",
    "usbhs_include_phy": "usb-hs:include-phy",
    "communication_interfaces_usbhs_include_phy": "usb-hs:include-phy",
    "pdusb_usbss_usb_3_0": "usb-ss",
    "pdusb_usbpd": "usb-pd",
    "pdusb_usbpd_type_c": "usb-pd",
    "pdusb_usb_pd_type_c": "usb-pd",
    "communication_interface_pdusb_usb_pd_type_c": "usb-pd",
    "type_c_source_sink_drp": "usb-pd:drp",
    # -------- video / display
    "dvp": "dvp",
    "communication_interfaces_dvp": "dvp",
    "ltdc": "ltdc",
    "argb": "argb",
    "gpha": "gpha",
    "sai": "sai",
    # -------- analogue
    # **`adc` はチャネル数**（値 `8+2` は外部8＋内部2）。ユニット数を数えるのは
    # `adc_unit` / `adc_tkey_unit(s)` のほうで、混ぜると数が化ける。
    "adc": "adc-channel",
    "adc_channel": "adc-channel",
    "adc_channel_no": "adc-channel",
    "adc_adc1_channel": "adc-channel:adc1",
    "adc_adc2_channel": "adc-channel:adc2",
    "adc_adc3_channel": "adc-channel:adc3",
    "adc_adc4_channel": "adc-channel:adc4",
    "adc_tkey_channel": "adc-channel:with-tkey",
    "adc_tkey_channels": "adc-channel:with-tkey",
    "adc_tkey_number_of_channels": "adc-channel:with-tkey",
    # 値が `10@2`（チャネル@ユニット）の書き方をする family。
    "adc_tkey_channel_unit_count": "adc-channel:with-tkey-per-unit",
    "adc_tkey_channel_unitcount": "adc-channel:with-tkey-per-unit",
    "adc_unit": "adc",
    "adc_tkey_unit": "adc:with-tkey",
    "adc_tkey_units": "adc:with-tkey",
    "hsadc_units": "hsadc",
    "hsadc_channels": "hsadc-channel",
    "dac_unit": "dac",
    "opa": "opa",
    "opa1": "opa:opa1",
    "opa2": "opa:opa2",
    "opa3": "opa:opa3",
    "opa4": "opa:opa4",
    "opa_polling": "opa:polling",
    "cmp": "cmp",
    "cmp1": "cmp:cmp1",
    "cmp2": "cmp:cmp2",
    "cmp3": "cmp:cmp3",
    # 「OPA/CMP」を対で数える family がある（`4` は対の数で、OPA が4でも CMP が4でもない。
    # `tools/check_counts.py` が同じ理由でこの行を突き合わせから外している）。
    "opa_cmp": "opa-cmp",
    "tkey": "tkey-channel",
    "capacitive_touchkey": "tkey-channel",
    "touch_key_button": "tkey-channel",
    "dfsdm": "dfsdm",
    "rng": "rng",
    # -------- timers
    "adtm": "timer-advanced",
    "advanced_control_timer": "timer-advanced",
    "timer_advanced": "timer-advanced",
    "timer_adtm_16_bit": "timer-advanced:16bit",
    "timer_advanced_control_16_bit": "timer-advanced:16bit",
    "timer_advanced_control_16_bits": "timer-advanced:16bit",
    "timer_advanced_control_tim1_16_bit": "timer-advanced:tim1-16bit",
    "gptm": "timer-general",
    "general_purpose_timer": "timer-general",
    "timer_general_purpose": "timer-general",
    "timer_general_purpose_16_bit": "timer-general:16bit",
    "timer_general_purpose_16_bits": "timer-general:16bit",
    "timer_gptm_16_bit": "timer-general:16bit",
    "timer_general_purpose_32_bit": "timer-general:32bit",
    "timer_general_purpose_32_bits": "timer-general:32bit",
    "timer_gptm_32_bit": "timer-general:32bit",
    "timer_general_purpose_tim2_16_bit": "timer-general:tim2-16bit",
    "timer_general_purpose_tim2_3_16_bit": "timer-general:tim2-3-16bit",
    "timer_general_purpose_tim4_32_bit": "timer-general:tim4-32bit",
    "timer_basic_16_bit": "timer-basic:16bit",
    "streamlined_timer": "timer-streamlined",
    "timer_streamlined_tim3_16_bit": "timer-streamlined:tim3-16bit",
    "timer_lptim": "timer-lptim",
    "timer_low_power_timer_lptim": "timer-lptim",
    "timer_systick": "systick",
    "timer_systick_32_bit": "systick:32bit",
    "timer_system_time_base_32_bit": "systick:32bit",
    "timer_systick_64_bit": "systick:64bit",
    "timer_systick_64_bits": "systick:64bit",
    "watchdog": "watchdog",
    "timer_watchdog": "watchdog",
    "timer_watchdog_wdt": "watchdog",
    "timer_wwdg": "watchdog:wwdg",
    "rtc": "rtc",
    # -------- motor / power（CH32M 系）
    "half_bridge_gate_driver": "gate-driver:half-bridge",
    "3_phase_gate_drive_structure": "gate-driver:3-phase-structure",
    "structure": "gate-driver:structure",
    "3_phase_gate_drive_voltage": "gate-driver:3-phase-voltage",
    "three_phase_pre_drive_voltage": "gate-driver:3-phase-voltage",
    "current_sampling_isp_isn": "current-sense",
    "programmable_current_injection_module_isink": "isink",
    "source_current_module_isource": "isource",
    "signal_decoding_qii": "qii",
    "high_voltage_i_o_hv_i_0": "hv-io",
    "pre_drive_i_o_mv_i_0": "pre-drive-io",
    # -------- 主要仕様（能力ではないが、比較表がここで言っているぶん）。
    # **数として引くなら `index/parts.csv` のほうが出所が良い**——クロックと電圧は
    # `evidence/operating_conditions`、Flash/SRAM/GPIO は `catalog/products` から
    # 来ていて、比較表の自由文（`Max: 144MHz`）ではなく数になっている。
    "cpu_main_frequency": "clock",
    "cpu_clock_speed": "clock",
    "cpu_clock_frequency": "clock",
    "system_clock_source": "clock:sources",
    "rated_voltage": "voltage",
    "operating_voltage": "voltage",
    "code_flash_bytes": "flash",
    "extended_psram_bytes": "psram",
    "sram_core_1_hs_dtcm": "sram:core1-hs-dtcm",
    "sram_core_1_hs_itcm": "sram:core1-hs-itcm",
    "sram_shared_code_and_data_area": "sram:shared",
}

# 能力ではない属性。**落とす理由を書いて明示的に持つ**——`CAPABILITIES` に無い
# 属性は生成が落ちるので、ここに無ければ黙って消えることはない。
NOT_CAPABILITIES: dict[str, str] = {
    "main_applications_and_features": "自由文の位置づけ（`General-purpose, pin optimized`）で、"
                                      "能力の有無でも数でもない",
}

# 同じ (型番, 能力, qualifier) が2行になるものの数。**いまは0**——
# CH32H416RDU6 の SRAM 共有領域が zh `512KB` / en `512K` で対にならず2行に
# なっていたが、F-57（`canonical_value` に容量単位の同一視）で解消した
# （その部品の SRAM は6行の reference から3行の confirmed になった）。
# 0 のまま固定するので、同種の綴り差が新しく出れば生成が落ちる。
KNOWN_DOUBLED = 0

COUNT = re.compile(r"^\d+$")
# 「持っている」とだけ言う印。資料が数を言っていないので `count` は空になる。
MARKERS = frozenset({"√", "Support", "Supported", "support", "supported", "Yes", "yes"})


def rows_for(attributes: list[dict], products: list[dict]) -> tuple[list[dict], list[str]]:
    where = {p["part_number"]: (p["series"], p["family"]) for p in products}
    unknown = sorted({a["attribute"] for a in attributes
                      if a["attribute"] not in CAPABILITIES
                      and a["attribute"] not in NOT_CAPABILITIES})
    rows = []
    for a in attributes:
        mapped = CAPABILITIES.get(a["attribute"])
        if mapped is None:
            continue
        capability, _, qualifier = mapped.partition(":")
        value = a["value"].strip()
        if COUNT.match(value):
            stated, count = "count", value
        elif value in MARKERS:
            stated, count = "marker", ""
        else:
            stated, count = "text", ""
        series, family = where.get(a["part_number"], ("", ""))
        rows.append({"part_number": a["part_number"], "series": series, "family": family,
                     "capability": capability, "qualifier": qualifier,
                     "stated": stated, "count": count, "value": value,
                     "attribute": a["attribute"],
                     "confidence": a["confidence"], "basis": a["basis"]})
    rows.sort(key=lambda r: (r["part_number"], r["capability"], r["qualifier"], r["attribute"]))
    return rows, unknown


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="出力先の上書き（試験用）")
    args = ap.parse_args()

    rows, unknown = rows_for(paths.load("product_attributes"), paths.load("products"))
    if unknown:
        print(f"能力の語彙に無い属性が {len(unknown)} 種あります"
              "——tools/build_capabilities.py の CAPABILITIES か NOT_CAPABILITIES に足すこと:",
              file=sys.stderr)
        for name in unknown:
            print(f"  - {name}", file=sys.stderr)
        return 1

    seen = collections.Counter((r["part_number"], r["capability"], r["qualifier"]) for r in rows)
    doubled = sorted(k for k, n in seen.items() if n > 1)
    if len(doubled) != KNOWN_DOUBLED:
        print(f"同じ (型番, 能力, qualifier) の行が {len(doubled)} 組"
              f"（記録は {KNOWN_DOUBLED} 組）——語彙が2つの属性を1つに畳んでいないか、"
              "証拠側で zh/en の対が増えたか: "
              f"{doubled[:5]}", file=sys.stderr)
        return 1

    dest = paths.index("capabilities", args.out)
    paths.write(dest, rows, CAPABILITY_COLUMNS)
    kinds = collections.Counter(r["stated"] for r in rows)
    names = {(r["capability"], r["qualifier"]) for r in rows}
    print(f"{dest}: {len(rows)} 行  能力 {len({c for c, _ in names})} 種"
          f"（qualifier 込みで {len(names)}）  {dict(kinds)}", file=sys.stderr)
    # **どの属性にも当たらない語彙は報告する。** 証拠側で綴りが直ると（F-57/F-58 が
    # `general_purpose_i_o` と SRAM の重複行を消したように）辞書の項が黙って死ぬ。
    used = {a["attribute"] for a in paths.load("product_attributes")}
    unused = sorted((set(CAPABILITIES) | set(NOT_CAPABILITIES)) - used)
    if unused:
        print(f"  - どの属性にも当たらない語彙 {len(unused)}: {unused}", file=sys.stderr)
    dropped = collections.Counter(a["attribute"] for a in paths.load("product_attributes")
                                  if a["attribute"] in NOT_CAPABILITIES)
    if dropped:
        print(f"  - 能力ではないので載せない属性: {dict(dropped)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
