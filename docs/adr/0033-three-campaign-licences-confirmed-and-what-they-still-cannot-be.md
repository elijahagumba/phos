# ADR 0033 — Three campaign licences confirmed, and what they still cannot be

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle evaluation campaign (data gate)
- **Supersedes:** nothing
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0024](0024-corpus-intake-a-confirmed-licence-a-version-pin-and-two-label-sources-that-disagree.md)

## Context

The cycle contract wants ≥3 public ICS process types. HAI (water) and one distillation
mixture are integrated. Three campaign candidates sat at `read once` because two fetches of
one page are not two surfaces.

Second surfaces were read on 2026-08-22:

| Corpus | Surface 1 | Surface 2 | SPDX |
| --- | --- | --- | --- |
| data4cyber (grid) | Zenodo API `license.id` = `cc-by-4.0` on record 19965384 | Panasonic Newsroom: "Publication format: Open data (CC BY 4.0)" | CC-BY-4.0 |
| s7-data-modification (battery + PV) | Zenodo API `license.id` = `cc-by-4.0` on record 15373938 | KITopen 1000181992: "Creative Commons Namensnennung 4.0 International" | CC-BY-4.0 |
| 3W Petrobras (offshore wells) | GitHub README: data files CC BY 4.0 | figshare API article 29205836: `"license": {"name": "CC BY 4.0"}` | CC-BY-4.0 |

## Decision

**Licences are `confirmed`.** Acquisition is **not** implied. Confirmed is the gate for a
later PART to fetch. This record does not add registry fetchable rows, prepare paths, or
eval numbers.

What each corpus **cannot** be, even after fetch:

- **data4cyber:** 5,880 normal seconds (~1.6 h). It cannot support ADR 0003's false-positives
  per normal hour as a control-room budget. Attack windows and Modbus pcaps are why it is
  still worth a prepare PART. `pcapng` is not yet the dpkt pcap path (ADR 0012).
- **s7-data-modification:** `packets_dataset.parquet` is a parsed packet **table**. Feeding it
  as if it were a capture would bypass the dissector. Process parquet is Track A only, and
  small. Labels are textual (`normal` / `data_modification`).
- **3W:** class labels 1–9 are **faults**, not cyber-attacks. Collapsing them to "attack"
  would be a false statement. Real / simulated / hand-drawn provenances must stay split.

## Consequences

**Gained.** The data gate is no longer why these three process types are untouched.

**Cost.** Cross-plant at 2–3/day is still unearned. Confirmation is not a detection claim.

**Rejected:** treating two Zenodo versions of Data4Cyber, or two fetches of one HTML page,
as two surfaces.
