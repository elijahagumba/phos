# ADR 0251 — H1 attaches on every hostile write and does not uniquely lead

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane T
- **Supersedes:** nothing
- **Depends on:** [ADR 0250](0250-a-command-effect-is-not-a-known-link-change.md),
  [ADR 0036](0036-a-lead-tie-is-a-refusal-not-an-alphabetical-winner.md)

## Context

ADR 0250 added `toward_limit_against_state` and predicted the development result before the run.
The run is `uv run python scripts/score_trusted_station.py` at `b3d2dd8`. Report:
`eval_runs/build/d/trusted/h1-development.md`. Seeds 97801–97820. Water treatment. Issuer is the
declared operator. This is a simulated diagnosis (ADR 0073). It is not the frozen 0 of 16.

## Decision

**Keep the fact. Do not treat it as a unique lead.**

On all 20 development seeds the hostile write gained one `toward_limit_against_state` fact and
the authorised run gained none. Unique unauthorised leads: **0 of 20**. The narrative lead was
`insufficient_evidence` every time. False-alarm narratives per authorised run: **0.00** (0 of 20),
not above 0.20.

The weight stayed `FittedPlattCalibrator(coefficient=0.0, intercept=0.0)`. It was not raised to
force a lead.

## Consequences

H1 is evidence for unauthorised control and is silent on the authorised runs in this batch. One
half-weight fact cannot outrank the residual. A later feature has to be a different fact. It
must not be bought by tuning the weight. Known-station **0 of 16** and unknown-master **1 of 4**
stay frozen and unpooled.
