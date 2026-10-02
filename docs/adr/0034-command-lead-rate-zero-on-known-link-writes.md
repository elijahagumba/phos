# ADR 0034 — Command lead rate is still 0/16; the battery writes from known stations

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle evaluation campaign (Atlas command ranking)
- **Supersedes:** nothing
- **Depends on:** [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md),
  [ADR 0017](0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md),
  [ADR 0027](0027-unknown-master-writes-are-not-maintenance.md)

## Context

ADR 0027 made a **marked unknown master** contradict `engineering_maintenance`. The cycle
contract asks that unauthorised control be top-ranked in ≥70% of confirmed command-attack
windows. The breaking harness is the measurement that exists (public pcaps still unacquired).

Re-run after 0027, commit `0362a6d`, seed 7, water + power graded batteries (batch has no
wire). Report: `eval_runs/breaking/breaking-report.md`.

Of **16** command attacks, commands moved `unauthorised_control_activity` **up in 12** and
**led in 0**. Same headline as before 0027.

The competing sets name why. Water mimic/rogue writes: after commands,
`engineering_maintenance` still leads; attack is 2nd or 3rd. Power is saturated
(`sensor_or_device_fault` always leads); inserting command structure **inserts maintenance
above the attack** and can make rank worse (3 → 4).

The graded issuers are `scada` and `hmi` — stations already on the learned graph. ADR 0027's
split does not apply. Unexpected function on a **known** link still supports both
explanations; maintenance's prior wins. That is ADR 0014's remaining limit, measured, not a
bug in the marker.

## Decision

**Do not weaken the known-link indistinguishability to chase 70% on this battery.** A
commissioning engineer and an intruder can still leave the same new function on a learned
station. Making maintenance lose that fight would be a template cheat.

The ≥70% contract is **unearned**, including on attacks we wrote. A later PART may add
**unknown-master issuers** to D2 and score those windows separately. That tests 0027. It does
not rewrite 0014. The ordinal rank remains not a field detection rate.

## Consequences

**Gained.** 0027 is not silently "the 70% fix." The battery's command attacks are the wrong
shape for that split.

**Cost.** Category command-reasoning is blocked on (a) unknown-master windows in a labelled
corpus, or (b) a public capture, not on another covariance knob.
