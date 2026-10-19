# ADR 0252 — H2 is rejected: the jump false-alarms on authorised writes

- **Status:** Accepted
- **Date:** 2026-10-19
- **PART:** Build brief D, lane T
- **Supersedes:** nothing
- **Depends on:** [ADR 0250](0250-a-command-effect-is-not-a-known-link-change.md),
  [ADR 0086](0086-empirical-command-baseline.md)

## Context

H2 was declared before the run. A step larger than the operating band's width, or a write during
a manual mode, supports unauthorised control at weight one half. The authorised runs in this
batch are jumps of that size. The prediction was a false-alarm rate of 1.00, and rejection.

The run is `uv run python scripts/score_trusted_station.py --features setpoint_jump,outside_operating_mode`
at `c9d066e`. Report: `eval_runs/build/d/trusted/h2-development.md`. Seeds 97801–97820. Simulated
diagnosis (ADR 0073). Not the frozen 0 of 16.

## Decision

**Reject H2.** Do not enable `setpoint_jump` or `outside_operating_mode` in the challenger.

False-alarm narratives per authorised run: **1.00** (20 of 20), above 0.20. Each authorised run
gained the jump fact and raised one narrative that is not maintenance about that write. Unique
unauthorised leads: **0 of 20**. The manual-mode clause did not attach: the write is before the
plant's first benign event.

The code stays. The rejection stays in `decisions.md`. The weight was not retuned to change this.

## Consequences

The challenger, if it has one, is H1 and whatever later hypothesis does not false-alarm above
0.20. A jump by itself does not separate a hostile write from an authorised unusual jump.
Known-station **0 of 16** and unknown-master **1 of 4** stay frozen and unpooled.
