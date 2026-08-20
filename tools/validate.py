#!/usr/bin/env python3
"""Validate draft CH32 device records without modifying them."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "device.schema.json"
DEVICE_DIR = ROOT / "devices"


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def evidence_nodes(value: object):
    if isinstance(value, dict):
        if set(value) == {"source", "locator"}:
            yield value
        for child in value.values():
            yield from evidence_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from evidence_nodes(child)


def validate_relations(path: Path, record: dict[str, object]) -> list[str]:
    errors: list[str] = []
    expected_id = path.stem
    if record.get("id") != expected_id:
        errors.append(f"id {record.get('id')!r} does not match filename {expected_id!r}")

    identity = record.get("identity", {})
    if isinstance(identity, dict):
        part_number = identity.get("part_number")
        if isinstance(part_number, str) and part_number.lower() != expected_id:
            errors.append("identity.part_number does not match the case-insensitive record id")

    sources = record.get("sources", [])
    source_ids = [item.get("id") for item in sources if isinstance(item, dict)]
    if len(source_ids) != len(set(source_ids)):
        errors.append("source ids are not unique")
    known_sources = set(source_ids)
    for evidence in evidence_nodes(record):
        if evidence["source"] not in known_sources:
            errors.append(f"evidence refers to unknown source {evidence['source']!r}")

    coverage = record.get("coverage", {})
    pins = record.get("pins", [])
    package = record.get("package", {})
    if isinstance(coverage, dict) and coverage.get("package_pins") == "complete":
        if not isinstance(pins, list) or not isinstance(package, dict):
            errors.append("complete package pin coverage requires pins and package objects")
        elif len(pins) != package.get("pin_count") + package.get("exposed_pad_count", 0):
            errors.append("complete package pin coverage requires one entry per lead and exposed pad")
        else:
            expected_numbers = set(range(1, package["pin_count"] + 1))
            actual_numbers = {pin.get("number") for pin in pins if isinstance(pin, dict) and isinstance(pin.get("number"), int)}
            if actual_numbers != expected_numbers:
                errors.append("complete package pin coverage requires consecutive pin numbers from 1 to pin_count")
            exposed_pads = {
                pin.get("number")
                for pin in pins
                if isinstance(pin, dict) and isinstance(pin.get("number"), str) and pin.get("number", "").startswith("EP")
            }
            if len(exposed_pads) != package.get("exposed_pad_count", 0):
                errors.append("exposed-pad entries do not match package.exposed_pad_count")
            gpio_count = sum(pin.get("kind") == "gpio" for pin in pins if isinstance(pin, dict))
            if gpio_count != package.get("gpio_count"):
                errors.append("GPIO pin entries do not match package.gpio_count")
    if isinstance(pins, list):
        route_selectors = record.get("route_selectors", [])
        if not isinstance(route_selectors, list):
            route_selectors = []
            errors.append("route_selectors must be an array")
        selector_by_id = {
            item.get("id"): item
            for item in route_selectors
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if len(selector_by_id) != len(route_selectors):
            errors.append("route-selector ids are missing or not unique")
        selector_fields: set[tuple[object, object, object]] = set()
        occupied_bits: dict[object, set[tuple[str, int]]] = {}
        for selector in route_selectors:
            if not isinstance(selector, dict):
                continue
            field_key = (selector.get("controller"), selector.get("register"), selector.get("field"))
            if field_key in selector_fields:
                errors.append(f"route-selector field {field_key!r} is defined more than once")
            selector_fields.add(field_key)
            bits = selector.get("bits")
            if (
                not isinstance(bits, list)
                or not bits
                or any(
                    not isinstance(bit, dict)
                    or not isinstance(bit.get("register"), str)
                    or not bit["register"]
                    or not isinstance(bit.get("bit"), int)
                    or not 0 <= bit["bit"] <= 31
                    for bit in bits
                )
            ):
                errors.append(f"route selector {selector.get('id')!r} has invalid bits")
                continue
            field_bits = {(bit["register"], bit["bit"]) for bit in bits}
            if len(field_bits) != len(bits):
                errors.append(f"route selector {selector.get('id')!r} repeats a bit")
                continue
            named = list(dict.fromkeys(bit["register"] for bit in bits))
            if selector.get("register") != "|".join(named):
                errors.append(
                    f"route selector {selector.get('id')!r} register does not match its bits"
                )
            width = len(bits)
            valid_values = selector.get("valid_values")
            field_limit = 1 << width
            if (
                not isinstance(valid_values, list)
                or not valid_values
                or any(not isinstance(value, int) or value < 0 or value >= field_limit for value in valid_values)
                or len(valid_values) != len(set(valid_values))
            ):
                errors.append(f"route selector {selector.get('id')!r} has invalid valid_values")
            elif selector.get("reset_value") not in valid_values:
                errors.append(f"route selector {selector.get('id')!r} reset value is not valid")
            # Bits are compared per register, so a field split across PCFR1 and
            # PCFR2 still cannot overlap either register's other fields.
            controller = selector.get("controller")
            if field_bits & occupied_bits.setdefault(controller, set()):
                errors.append(
                    f"route selector {selector.get('id')!r} overlaps another field in {controller!r}"
                )
            occupied_bits[controller].update(field_bits)
        numbers = [pin.get("number") for pin in pins if isinstance(pin, dict)]
        if len(numbers) != len(set(numbers)):
            errors.append("package pin numbers are not unique")
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            functions = pin.get("functions", [])
            function_keys = [
                (item.get("signal"), item.get("peripheral"), item.get("route"), item.get("conditions"))
                for item in functions
                if isinstance(item, dict)
            ]
            if len(function_keys) != len(set(function_keys)):
                errors.append(f"pin {pin.get('number')!r} contains duplicate functions")
            for function in functions:
                if not isinstance(function, dict) or "selection" not in function:
                    continue
                selection = function.get("selection")
                if not isinstance(selection, dict):
                    continue
                selector_id = selection.get("selector")
                selector = selector_by_id.get(selector_id)
                if selector is None:
                    errors.append(f"pin {pin.get('number')!r} refers to unknown route selector {selector_id!r}")
                    continue
                values = selection.get("values", [])
                selector_width = (
                    len(selector["bits"]) if isinstance(selector.get("bits"), list) else None
                )
                if isinstance(values, list) and isinstance(selector_width, int):
                    if not values or any(not isinstance(value, int) for value in values):
                        errors.append(f"pin {pin.get('number')!r} has empty or non-integer selection values")
                    elif len(values) != len(set(values)):
                        errors.append(f"pin {pin.get('number')!r} has duplicate selection values")
                    limit = 1 << selector_width
                    if any(not isinstance(value, int) or value < 0 or value >= limit for value in values):
                        errors.append(
                            f"pin {pin.get('number')!r} has a selection value outside selector {selector_id!r} width"
                        )
                    valid_values = selector.get("valid_values", [])
                    if isinstance(valid_values, list) and any(value not in valid_values for value in values):
                        errors.append(
                            f"pin {pin.get('number')!r} uses a reserved value of selector {selector_id!r}"
                        )

    if isinstance(coverage, dict) and coverage.get("pin_functions") == "complete":
        if coverage.get("package_pins") != "complete":
            errors.append("complete pin-function coverage requires complete package-pin coverage")

    memory = record.get("memory", {})
    if isinstance(memory, dict):
        regions = memory.get("regions", [])
        region_ids = [item.get("id") for item in regions if isinstance(item, dict)]
        known_regions = set(region_ids)
        if len(region_ids) != len(known_regions):
            errors.append("memory region ids are not unique")
        for region in regions:
            if isinstance(region, dict) and "subset_of" in region and region["subset_of"] not in known_regions:
                errors.append(f"memory region refers to unknown parent {region['subset_of']!r}")

    package = record.get("package", {})
    if isinstance(package, dict):
        special_io = package.get("special_io_counts", [])
        special_kinds = [item.get("kind") for item in special_io if isinstance(item, dict)]
        if len(special_kinds) != len(set(special_kinds)):
            errors.append("package special-I/O kinds are not unique")

    components = record.get("integrated_components", [])
    component_ids = [item.get("id") for item in components if isinstance(item, dict)]
    if len(component_ids) != len(set(component_ids)):
        errors.append("integrated component ids are not unique")
    return errors


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    try:
        import jsonschema
    except ImportError:
        jsonschema = None

    failures = 0
    paths = sorted(DEVICE_DIR.glob("*.json"))
    if not paths:
        print(f"error: no device records in {DEVICE_DIR}", file=sys.stderr)
        return 1

    for path in paths:
        record = load_json(path)
        errors: list[str] = []
        if not isinstance(record, dict):
            errors.append("top-level value is not an object")
        else:
            if jsonschema is not None:
                validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
                errors.extend(error.message for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path)))
            errors.extend(validate_relations(path, record))
        if errors:
            failures += 1
            for error in errors:
                print(f"{path.relative_to(ROOT)}: {error}", file=sys.stderr)
        else:
            print(f"ok: {path.relative_to(ROOT)}")

    if jsonschema is None:
        print("warning: jsonschema is not installed; schema validation was skipped", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
