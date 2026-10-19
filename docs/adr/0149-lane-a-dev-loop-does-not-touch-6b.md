# ADR 0149 — Lane A's development loop does not touch 6B

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build lane A, Sentiel target 1
- **Depends on:** [ADR 0148](0148-bet-001-is-scored-once.md)

## Context

Bet 001 ran once on CERT r3.1 and lost (ADR 0148). The frozen 6B scorer finds
`CSF0929` and misses `CCH0959` (best rank 957 of 210,814 person-days). CERT r3.1
is development from that recording. A later change that finds both insiders is a
different experiment. It must not edit the three Bet 001 formulas, reuse the
frozen detector name, or append `eval_runs/log.jsonl`.

A full Gaussian replay of the 34 features costs about nine minutes. Target 1
cannot pay that on every loop. The four Phase 2b streams (ADRs 0190–0193) read
the entity-day trace cache and the LDAP directory, not the 34-feature magnitudes.

## Decision

1. Development scorers are named `lane-a-dev:<id>`. They rank every person-day
   by `(-score, user_id, timestamp)` and cut at 48, the same key ADR 0148 fixed.
   A user is found only by one of their own labelled days. The malicious flag is
   not in the key.

2. One loop changes one stream or one declared combination. It is scored on the
   same r3.1 development days. It is kept only when it finds more of the two
   labelled insiders, or when it holds the same insiders, improves the missed
   insider's best rank, and does not drop precision at 48. Losing `CSF0929` is
   always a revert. Finding the second insider may drop precision. Ten loops
   with no keep stop the target.

3. The frozen 6B row (precision 0.104 at 48) is the starting bar, read from
   `eval_runs/build/lane-a/bet-001.json`. It is not recomputed and not
   overwritten. Development scores are written under `eval_runs/build/lane-a/`.

4. CERT r4.2 stays held out (ADR 0147). This loop does not fetch it and does
   not score it.

## Consequences

The 34-feature scorer and `AggregationPolicy()` stay as 6B left them. New
evidence is added beside them. A keep on r3.1 is unconfirmed until a later
session scores the named scorer on r4.2, once, after a new declaration.
