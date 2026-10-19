# ADR 0253 — H3 is kept, and H1 with H3 still does not uniquely lead

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane T
- **Supersedes:** nothing
- **Depends on:** [ADR 0251](0251-h1-attaches-and-does-not-lead.md),
  [ADR 0252](0252-h2-is-rejected-for-false-alarms.md)

## Context

H3 was declared before the run: a write whose actuator moves while the controlled reading stays
inside three of its own noise standard deviations supports unauthorised control. The weight is
one half. It is not `CROSS_SIGNAL_MISMATCH`, which would support a sensor fault, and it is not a
known-link function change.

The run is `uv run python scripts/score_trusted_station.py --features write_and_hide` at
`f135d57`. The combination H1+H3 was scored with the same code. Reports:
`eval_runs/build/d/trusted/h3-development.md` and `h1-h3-development.md`. Seeds 97801–97820.
Simulated diagnosis (ADR 0073). Not the frozen 0 of 16.

## Decision

**Keep H3. Freeze H1+H3 as the challenger. Do not enable H2.**

| Variant | Hostile unique leads | False alarms per authorised run |
| --- | ---: | ---: |
| H3 | 0 of 20 | 0.00 |
| H1+H3 | 0 of 20 | 0.00 |

H3 attached on every hostile write and on no authorised run. Together the two facts still leave
`insufficient_evidence` as the narrative lead. The weight was not raised. A tie is not a lead,
and the residual listed first is not a lead.

## Consequences

Held-back seeds 97901–97920 are scored once, after a declaration that names this challenger, the
command, the sha256, and the bars. The development result already says the lead bar is unlikely.
That does not authorise skipping the one score, and it does not authorise a second one.
