# CH32 Device Data

[日本語](README.ja.md)

Machine-readable CH32 device records with source provenance and validation state.

The repository is the canonical home of the device database. The current schema version, `0.1-draft`, is still under design, and the sample records do not declare Arduino support.

## Layout

- `schemas/device.schema.json`: JSON Schema for exact orderable SKUs
- `devices/*.json`: representative device records
- `tools/validate.py`: schema and cross-reference validator
- `docs/`: Japanese design notes and work handoff

## Validation

```sh
python3 tools/validate.py
python3 -S tools/validate.py
```

The second command exercises the standard-library fallback without the optional `jsonschema` package.

Official PDFs, EVT trees, legacy Arduino core sources, and hand-written legacy pin tables are not copied into this repository. Records retain URLs, hashes, revisions, and document locators instead.
