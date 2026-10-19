# ADR 0145 — Bet 001 is not run: the CERT payload and the trace cache are absent

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane A, Sentiel S1
- **Depends on:** [ADR 0084](0084-non-saturating-aggregation-for-sentiel.md),
  [ADR 0093](0093-bet-001-three-candidates-declared.md)

## Context

ADR 0084 fixed the success test before any candidate existed. ADR 0093 declared the three
formulas — `linear-excess`, `gaussian-tail`, and `family-max` — and scored none of them. S1
is settled only when those three are run once, under that contract, and the result is published
whichever way it goes.

This lane checked the machine it is running on. `data/cert-insider-threat/` contains the tracked
`sentiel-manifest.json` and no release directory. There is no `r3.1/` tree, no `answers/` tree,
and no `r3.1-entity-day-traces.jsonl.gz`. The manifest's file URLs are on
`ndownloader.figshare.com`. The dataset homepage is on `kilthub.cmu.edu`. Neither host is in the
build brief's allow-list.

`eval_runs/sentiel/cert-failure-classification.json` is the frozen scorer's visibility report. It
records, for the labelled days, one score and one strongest feature. It does not carry the 34
magnitudes for every entity-day. The top 48 under a different formula cannot be read out of it.

## Decision

**Bet 001 is not run in this lane.** The three candidates stay exactly as ADR 0093 pinned them.
`AggregationPolicy()` stays the PART 6B sum. Nothing is appended to `eval_runs/log.jsonl`. No
parameter, threshold, weight, or fourth formula is introduced to compensate for the missing files.

The archive is not fetched. Fetching it would leave the allow-list.

The block, and the reason, is the S1 record:
`eval_runs/build/lane-a/bet-001.md`.

## Consequences

S1's pass bar — run and published, whichever way it goes — is not met. Publishing the refusal is
the result this disk can support. The frozen CERT 6B row remains the public ruler; this lane did
not re-measure it and does not replace it.

A later run on a machine that already has the release, or that is allowed to fetch it, uses the
declared candidates as they stand. It reproduces the frozen 48-alert row and the ADR 0076
classification as gates before any candidate is scored. It reports all three. It does not retune.

## What would reopen this

The r3.1 events, or a trace cache proved equivalent to them, present on the machine before the
run starts. A summary JSON of the frozen scorer does not qualify.
