# ADR 0204 — The identity register stays empty for the S2 score

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Sentiel v1, S2, before any labelled identity score
- **Depends on:** [ADR 0146](0146-identity-features-keep-the-thirty-four-symmetric.md),
  [ADR 0202](0202-forty-eight-tickets-a-day-supersedes-the-top-48.md)

## Context

S2's pass sentence, from `docs/v1-roadmap.md` §2.2, is: "Implemented, tested and
scored on CERT r3.1 and at least one larger release with more insiders." ADR 0146
shipped the six features and an empty register, and forbade filling that register
from a labelled day. No register whose names are not copied from labelled insiders
is on disk. This commit does not read `insiders.csv` for the score.

## Decision

The register for this score is empty. Its contents are this sentence and nothing
else: no hosts, no destinations, no machines.

`register_sha256(DeclaredIdentities())` is
`2c284a6e2f41061c514104f6eb6e885b55664d0a7eb18b9b0278a1c3f74f168b`.

An empty register matches nothing, so each of the six features scores zero. That
zero is the result. It is not a reason to add a name after the run.

The 34 stay symmetric. `AggregationPolicy()` is not given a weight. The features
are scored apart from frozen 6B, by `IdentityFeaturiser` through
`phos.sentiel.identity_score.summarise_traces`.

Commands, run once each, only after this commit:

```
uv run python scripts/score_identity_features.py --release r3.1 --out eval_runs/build/v1/sentiel/s2-r31.json
uv run python scripts/score_identity_features.py --release r4.2 --out eval_runs/build/v1/sentiel/s2-r42.json
```

`insiders.csv` may be read only after the feature summary exists, and only to
count labelled insiders. It does not change the register.

## Consequences

If both files show zeros and r4.2 has more labelled insiders than r3.1, the
roadmap sentence has been scored. The zeros are what an empty register produces.
