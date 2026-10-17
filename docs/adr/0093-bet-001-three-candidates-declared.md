# ADR 0093 — Bet 001's three candidates are declared, and none is scored

- **Status:** Accepted
- **Date:** 2026-10-04
- **PART:** v1 roadmap, Sentiel S1 pre-registration
- **Depends on:** [ADR 0084](0084-non-saturating-aggregation-for-sentiel.md)

## Context

ADR 0084 opened the non-saturating aggregation session and froze its contract: at most
three candidates, every parameter pinned by a test in a commit that precedes any labelled
CERT measurement, empty weights, and an unquantified departure that cannot lead the queue
by itself. That commit did not exist. No candidate had a name.

The four families in ADR 0084 are linear excess, a tail-probability sum, family-first, and
an L*p* norm. The last of those is a knob. This record picks three and leaves the knob out.
It does not score them.

## Decision

**Three formulas, in `phos.sentiel.candidates`, not wired into the 6B scorer.**
`AggregationPolicy()` stays the PART 6B sum. Nothing here reads CERT. Nothing is appended
to `eval_runs/log.jsonl`.

A feature speaks when it is quantified and its magnitude is at least `emit_k`. That bar is
**1.0**, the existing `FittedModel.emit_k`, not a number chosen for these two insiders.
An unquantified term, or a magnitude at `MAX_MAGNITUDE`, contributes 0 and is counted.

| Id | Formula | Inherited parameter |
|---|---|---|
| `linear-excess` | Σ max(0, mᵢ − emit_k) over quantified speaking features | emit_k = 1.0 |
| `gaussian-tail` | Σ −log(1 − Φ(mᵢ)), standard normal, one-sided | the z-score's own tail |
| `family-max` | max quantified speaking magnitude inside each existing behaviour family, then the sum of those maxima | `family_of`, aggregator `max` |

`gaussian-tail` uses `math.erfc` while that value is positive, and the mills-ratio
asymptotic where float64 underflows. The switch is the underflow, not a threshold.
`family-max` uses max, not mean: the family's stated purpose in ADR 0084 is to remove
the redundancy that makes breadth cheap, and max is the reading that does so. A feature
the existing partition does not name is its own family, so it is not dropped and not
merged. A tie goes to the lexicographically first feature name. `feature_weights` and
`stem_weights` are empty on all three. Each `log_tag` is the candidate id, so none of
them can write the frozen 6B name.

**L*p* is not a candidate.** Any p would be a choice with no inherited value. Declaring
one here would be the search ADR 0084 forbade. A later session that wants it declares it
before its own labelled run; it does not edit this three.

The pinning test is `tests/sentiel/test_aggregation_candidates.py`. Its inputs are
hand-built magnitudes. It does not load CERT and it does not name either insider.

## Consequences

The pre-registration commit ADR 0084 required now exists, once this record is committed.
A later run may score these three on CERT r3.1 under that contract, gates first, all
three reported. It may not add a fourth formula to this set, change emit_k, switch max
to mean, or put a weight on a feature. Until that run, 0.104 at 48 stays Sentiel's
number, and the 14-of-34 notice stays on the frozen policy.

## What the next session assumes exists

- These three formulas and this ADR's parameters.
- No labelled CERT score of any of them.
