# ADR 0030 — Moment dwell, and chronic volume decay

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle evaluation campaign (Atlas + Sentiel)
- **Supersedes:** nothing
- **Depends on:** [ADR 0026](0026-joint-distance-gating-and-the-actionable-alert-unit.md),
  [ADR 0028](0028-precision-policy-volume-peer-match-and-the-family-gate.md)

## Context

ADR 0026's joint-moment detector on distillation still posted ~49 alerts/day-equivalent:
quieter than per-signal Mahalanobis, still far from 2–3/day. A one-sample flicker off the
manifold is not an actionable control-room event.

ADR 0028's precision policy still treats each busy day independently. A backup that runs
for a week is one administrative pattern; equal-weight days make it eight SOC tickets.

Neither gap is a missing signature. Both are persistence.

## Decisions

### Decision 1 — Dwell on the moment detector, default 1

`JointMomentDetector.dwell_samples` is how many consecutive moments must sit at or above
the fitted `joint_k` before an alert is emitted. ``1`` is ADR 0026 unchanged, including
the detector name. ``dwell-N`` is appended only when N > 1, so the gated row cannot be
overwritten.

The run counter resets when the plant returns below the envelope. Two flickers separated
by a normal sample never accumulate. This is not a named-attack signature.

Rejected: raising the training quantile again as the only lever. ADR 0026 already measured
that 0.995 halves perturbation recall. Dwell asks a different question: did the unusual
chord *hold*.

Rejected: hysteresis (`exit_factor`). It needs a moment that sits between two distance
thresholds, which is a fitted quantity, and would add a second number chosen on the test
set if we picked it there. Dwell is countable samples of attack-free-gated time.

### Decision 2 — Chronic volume decay, default off

`AggregationPolicy.chronic_volume_halflife_days` is ``None`` by default. When set, volume
stems that have been out-of-band for consecutive person-days are multiplied by
``0.5 ** ((streak - 1) / halflife)``. Day one is unchanged. High-signal stems (thumb-drive
onset) are never decayed.

`precision_policy()` without arguments remains ADR 0028, tag ``:precision``. Passing a
halflife retags ``:precision-chronic``.

This is not `legitimate_change` winning in the template library. CERT still has no
sanction evidence (ADR 0023). It is the queue not promoting the second through seventh
copy of a backup.

## Consequences

**Gained.** Two opt-in persistence levers whose defaults leave every existing experiment
log row comparable.

**Cost.** Dwell delays detection of short attacks by ``(N-1) × sample interval``. Chronic
decay can bury a slow-and-steady collection that never uses a high-signal stem. Both costs
are measured on the dataset library and are **not** substituted for distillation or CERT
rows when stating the cycle contract.
