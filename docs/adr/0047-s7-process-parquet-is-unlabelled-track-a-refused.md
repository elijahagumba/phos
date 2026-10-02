# ADR 0047 — S7 process parquet is unlabelled: labelled Track A is refused

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Public process types, honest labels (sequence item 3)
- **Supersedes:** nothing
- **Amends:** [ADR 0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md)
  on one clause only — the claim that S7 *process* parquet carries textual
  `normal` / `data_modification` labels is **false for the process file**. It does not
  amend the licence confirmation, and it does not amend that
  `packets_dataset.parquet` is a table, not a pcap
  ([ADR 0012](0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md)).
- **Depends on:** [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0012](0012-dpkt-the-dissector-seam-and-containing-hostile-packet-input.md),
  [ADR 0033](0033-three-campaign-licences-confirmed-and-what-they-still-cannot-be.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0044](0044-public-surfaces-on-main-must-move-with-every-advancement.md),
  [ADR 0046](0046-data4cyber-track-a-is-process-phase-telemetry-not-a-control-room-ruler.md)

## Context

Command-lead sessions 1–5 are complete by refusal of a labelled public command corpus
(ADR 0040). Data4Cyber Track A is measured as process-phase telemetry (ADR 0046) and still
cannot be a control-room budget. The tracker named S7 process parquet as the next licence-
confirmed public process type.

Campaign prose and ADR 0033 treated the process table as Track A with textual labels
(`normal` / `data_modification`). That vocabulary is how the **Zenodo record** describes
the **packet** source. Files win (ADR 0024). The process file was not read until this
record.

`process_dataset.parquet` was fetched for inspection only (359,657 bytes, MD5
`ebc3e048e0319f044ea47cc08e498999`, matches Zenodo record 15373938). Payloads remain
gitignored (ADR 0006). `packets_dataset.parquet` (201.8 MB) was **not** fetched. It is
still not a pcap.

PyArrow is not a PHOS dependency. Inspection used an ephemeral extra. The detection path
does not read parquet.

## Decision

**Labelled Track A on this corpus is refused.** The shipped process table has:

| Fact | Value |
|---|---|
| Rows | **13,912** |
| Columns | **21** (clock `archive_recv_ts` + 20 float process/actuator/state signals) |
| Label column | **none** |
| Attack windows | **cannot be formed from this file** |

The 21 names match the record's process-feature list. There is no `label`, `attack_*`,
or class column. `out_pv_on_off` / `out_batt_on_off` are plant actuators, not ground
truth.

`phos.eval.s7_process.prepare_labelled_track_a` raises on that schema.
`tests/eval/test_s7_process.py` pins: `normal` is not an attack (SWaT trap);
packets are not listed as a fetchable pcap; a *new* label column on the process file
forces this ADR to be revisited rather than auto-scoring.

The packet table's `label` column remains a **table**, not a capture. Joining those
packet-row strings onto process seconds would invent process-row attack windows. That
join is **out of scope**. So is an S7comm `ProtocolDissector`. So is quoting 13,912
unlabelled seconds as recall or as a 2–3/day budget.

Licence confirmation (ADR 0033) stands. Confirmation is still not a detection number.
`discover_labelled_command_corpora` stays empty. Known-station **0/16** and
unknown-master **1/4** were not remeasured and were not pooled. Distillation 2–3/day
remains refused (ADR 0031). Data4Cyber 6.6× is still not 10× (ADR 0046).

## Consequences

**Gained.** The shopping list is no longer "S7 process parquet is small Track A with
textual labels." The file was read. The gap is **no process-row labels**.

**Cost.** Battery+PV is not a third *labelled* public process type. Cross-plant at
≤2–3/day is still unearned. The ≥70% command-lead contract is still unearned.

**Rejected:** scoring unlabelled telemetry; fetching packets as pcap; adding S7comm
this PART; joining packet labels onto `archive_recv_ts`; adding `pyarrow` to the
pinned core; treating 13,912 rows as a control-room denominator.

## When to revisit

When the *process* table (or a declared, versioned conversion that does not bypass
ADR 0012) ships process-row labels, with an attack-free learn stretch, and the
SWaT trap (`normal` as a string) is mapped explicitly. Packet-table labels aligned
by clock are a new ADR, not a silent prepare. Until then, 3W remains the next
licence-confirmed process type — **as faults**, not attacks.
