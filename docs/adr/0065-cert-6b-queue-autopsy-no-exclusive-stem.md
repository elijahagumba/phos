# ADR 0065 — CERT 6B top-48 autopsy: no exclusive stem

- **Status:** Accepted
- **Date:** 2026-08-24
- **PART:** Engine week (Sentiel diagnosis)
- **Supersedes:** nothing
- **Depends on:** [ADR 0032](0032-precision-policy-lost-on-cert-at-48.md),
  [ADR 0022](0022-peer-group-baselining-and-the-scoring-shape-that-survives-a-wide-feature-set.md)

## Context

CERT r3.1 identity aggregation at 48 alerts remains the public Sentiel ruler: precision
**0.104** (5 TP / 43 FP), recall 0.5. Engine week asked which starter-count stems led that
queue. `ScoredWindow.contributions` already existed; there was no autopsy runner.

A named-subset bakeoff (`AggregationPolicy(log_tag=...)`) is justified only when one stem
led **every** true positive and **none** of the false positives. Otherwise scoring a family
is inventing a detector.

## Decision

1. `scripts/autopsy_sentiel_6b.py` streams the peer set once, ranks entity-windows, and
   writes `eval_runs/sentiel/6b-autopsy.md` under detector name `autopsy:6b-top-budget`.
   It never calls `append_to_experiment_log`. The frozen 6B detector name is not reused.
2. Measured on the same r3.1 peer stream as 6B: budget **48**, **5** TP / **43** FP (matches
   the public split). Leading stems:

   | Stem | TP | FP |
   | --- | --- | --- |
   | distinct_files | 3 | 7 |
   | off_hours_logon_count | 1 | 9 |
   | logon_count | 1 | 7 |
   | removable_device_connects | 0 | 13 |
   | distinct_http_hosts | 0 | 3 |
   | distinct_pcs | 0 | 2 |
   | new_counterparties | 0 | 1 |
   | new_pcs | 0 | 1 |

3. No stem led every TP with zero FP. **Do not invent a named subset.** Sequence-vs-6B stays
   later. Do not headline `:precision`. Do not overwrite 0.104.
4. `removable_device_connects` led **13** false positives and **0** true positives at this
   operating point. That is a diagnosis of the queue, not a licence to retune
   `precision_policy` high-signal stems.

## Consequences

**Gained.** The 48-alert queue is no longer an opaque 5/43. Volume (`distinct_files`) and
access (`logon_count` / `off_hours_logon_count`) share the labelled hits; removable-device
onset is loud in the false-alarm half.

**Cost.** There is no honest one-stem quieter 6B on this file. The public ruler stays
identity aggregation.

## Alternatives considered

- **Score removable-device only because the scenarios mention thumb drives.** Rejected. That
  stem led zero TPs in the top 48.
- **Score distinct_files because it led 3/5 TPs.** Rejected. It also led 7 FPs, and two TPs
  were other stems. Not exclusive.
- **Append a 6B row while autopsying.** Rejected. The public cell is frozen.
