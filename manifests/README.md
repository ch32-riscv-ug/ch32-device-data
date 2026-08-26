# List of documents to fetch

[日本語](README.ja.md)

This directory is the source of truth for the mapping between WCH's public documents and the individual mirror repositories. Each mirror repository reads `documents.json` and downloads only the documents assigned to it.

## Why it lives here

Because "which document belongs to which repository" is a judgment, not a derivation. Real examples:

- `CH32V007DS0.PDF` also covers `CH32M007`. The document name and the family name do not match
- `CH32xRM.PDF` covers both `CH32F103x` and `CH32V103x`
- `CH32V307DS0.PDF` and `CH32V20x_30xDS0.PDF` are the same document distributed under different names
- `CH32X315` has its own RM and EVT, so it becomes a new repository rather than living under an existing one

If each mirror held this decision on its own, the same non-obvious rules would be duplicated in ten or more places, and nobody would notice when they drift apart. Also, documents that belong to no repository (unassigned) can only be detected from a place that sees the whole picture.

## Scope

The RISC-V core CH32 families. The Cortex-M3 `CH32F` families are kept with `status: excluded` and a reason. Exclusions are recorded so that the next sweep does not resurface them as "new".

WCH's BLE families (CH572/573/583/585/587/592/595/596) are RISC-V but are not covered at this time. CH578/579 are Cortex-M0 and therefore fall outside the RISC-V criterion.

## Language

**The Chinese edition is the original; the English edition is its translation.** When the version numbers differ, the Chinese edition is the newer one, and some documents have no English edition at all (`CH32V407RM.PDF`, `CH32M030DS2.PDF`, `CH32V006DS2.PDF`). `primary_language` is `zh`.

The two languages are treated as separate sources; `sources.en` and `sources.zh` each hold their own download id and version number.

## Fields

| key | meaning |
|---|---|
| `name` | Distributed file name |
| `kind` | `datasheet` / `reference-manual` / `evt` / `core-manual` / `other` |
| `repositories` | Mirror repositories that should fetch it. May be more than one. Empty means unassigned |
| `status` | `assigned` / `unassigned` / `excluded` / `duplicate` |
| `reason` | Reason for exclusion or duplication |
| `sources.<lang>.file_id` | WCH download id. Inserted into the `download_url` template |
| `sources.<lang>.version` | Version number as displayed on the site |
| `sources.<lang>.scope` | Products / SKUs the document covers (as written by WCH) |

**The rule for splitting repositories is per EVT (1 repository = 1 EVT archive).** update.sh extracts the EVT into `./EVT` with a full replace, so putting two EVTs in one repository breaks it with last-one-wins (the reason CH32V205 was split out). Cross-family documents (QingKe core manual, WCH-Link manual, PACKAGE dimension drawings) are held by the dedicated mirror **`WCH-common`**. Because the availability of WCH's originals on the Chinese site is unstable, this catalog records the provenance (per-language `file_id` and version) while the GitHub mirrors guarantee the availability of the files themselves. `ch32-device-data` itself holds no PDFs.

## Updating

`.github/workflows/update.yml` runs daily (13:07 UTC). The mirrors update at 15:07 UTC, so this runs two hours ahead to let them read the same day's catalog.

To run it locally:

```sh
uv run tools/sync_catalog.py           # compare against the site and show the diff
uv run tools/sync_catalog.py --write   # apply the diff (does not overwrite assignments)
uv run tools/check_mirrors.py          # check that the mirrors are keeping up with the catalog
```

New documents are added with `status: unassigned` and appear as warnings on the run page. Assignment is decided by a person.

## Making failure the entry point of operations

WCH sometimes changes download ids, and the search API itself may change. **The job is built to fail when that happens.** A red run is the signal to take a look.

| Event | Behavior |
|---|---|
| API does not respond, is not JSON, or has no `data` | Fails immediately with the cause. The catalog is not rewritten |
| API shape changes and the number of results drops sharply | Fails when below 80% of the manifest. **Never writes an empty catalog** |
| A new document appears | Warning annotation, added as `unassigned`. The job succeeds |
| A document disappears from the site | Warning annotation. The local record is kept |
| A mirror still has files not in the catalog | Warning annotation. `update.sh` does not delete files it no longer fetches |

The lower bound on the count exists because a spec change shows up not as an "error" but as an "extremely small result". Letting it through silently would empty the catalog, and every mirror would lose its fetch targets.
