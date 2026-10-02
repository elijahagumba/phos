# ADR 0026 — Joint-distance gating, and the alert unit that is a plant-moment

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Atlas OT core (cycle contract: ≤2–3 actionable alerts/day)
- **Supersedes:** nothing
- **Depends on:** [ADR 0009](0009-joint-modelling-per-signal-attribution-and-the-model-that-lost.md),
  [ADR 0018](0018-phase-conditional-modelling-for-a-batch-process.md),
  [ADR 0025](0025-joining-batch-distillation-without-poisoning-the-false-positive-ruler.md)

## Context

ADR 0025's designed protocol on batch-distillation posted **18.72 false positives per normal
hour** (~449/day-equivalent) for pooled `MahalanobisModel`, at perturbation recall 0.60. That is
the joint model working — 8.6× quieter than the per-signal Gaussian — and still ~150× too loud
for the cycle contract of 2–3 *actionable* alerts/day under normal traffic.

Two facts about that number were already on the record and had not been spent:

1. **The ruler counts per-signal residuals.** `ModelDetector` emits one `Detection` per
   `Deviation`. A moment whose combination of readings is only slightly off the manifold can
   therefore contribute one alert per instrument. Grouping (5B/5C) collapses that for the
   vertical; the distillation baseline never ran grouping, and distillation still has no
   declared topology (ADR 0025 left the equipment register as a candidate).
2. **The covariance is pooled across a batch column.** ADR 0018 measured why that is the wrong
   envelope: mixing regimes inflates the trace and, depending on scale, either swallows every
   band or treats ordinary recipe motion as a residual. Phase-conditional modelling exists and
   is unused here because the operation logs have not been shown to declare a phase register.
   The default `MahalanobisModel` remains ungated so ADR 0025's row stays comparable.

The cycle contract asks for a *plant-as-a-machine* joint model whose variance scales with the
active operational phase, not a static global covariance envelope. This record is the counting
and gating half of that: the scalar the joint model already computes — Mahalanobis distance
``D_M`` — becomes the gate and the actionable-alert unit. Per-phase envelopes fall out of
ADR 0018's wrapper without a second mechanism: each `PhaseConditionalModel` inner fit learns
its own `joint_k` from that phase's attack-free moments.

## Decisions

### Decision 1 — Gate per-signal emission on the moment's joint distance

A `Deviation` is still one signal's conditional residual, because Constitution §3.2 requires
attribution. It is emitted only when the *moment* also satisfies ``D_M ≥ joint_k``. A thermal
or pressure flicker that remains inside the learned joint envelope no longer multiplies into
one alert per instrument.

`joint_k = 0` (the default) disables the gate. Every number already on `eval_runs/log.jsonl`
is therefore unchanged.

### Decision 2 — Learn `joint_k` as a training quantile, not a number chosen on the test set

`MahalanobisModel.adaptive_joint_quantile` sets `joint_k` at fit time to that quantile of the
attack-free training distances. The envelope is a property of *this* plant's normal, recovered
from the stored `joint_k`. Under `PhaseConditionalModel` each phase learns its own quantile
from its own moments, which is the phase-aware adaptive threshold: CHARGE is not judged on
IDLE's envelope.

The explicit `joint_k` field remains for tests that need a known gate. When both are set, the
quantile wins: one source of truth, the learned envelope.

Rejected: a global scale-invariant shrinkage target. ADR 0018 already measured that it revives
a batch plant by destroying water treatment. The gate does not touch `_shrink`.

Rejected: inferred operating modes (clustering / HMM). ADR 0018 deferred that because a
misassigned mode produces a confident judgement against the wrong baseline with nothing in the
evidence to show it happened. This PART still requires a declared `phase_feature` to condition.
What it adds for a plant that has none is a pooled adaptive envelope, honestly weaker.

### Decision 3 — The actionable-alert unit is one detection per jointly unusual moment

`JointMomentDetector` emits one PART 2 `Detection` per assembled timestamp whose ``D_M``
reaches the fitted `joint_k`, scored by the distance itself. ``feature`` is empty: the score is
a property of the plant at that instant. Per-signal `Deviation`s remain the explainable
attribution.

The cycle contract's "actionable alerts/day" is this unit, not the per-signal count ADR 0025
logged. Both rows are emitted when `--gated` is passed to `scripts/evaluate_atlas.py`, so a
reader can see the counting change separately from the detection change.

## Consequences

**Gained.** A batch column's joint model can refuse to alert on moments that are still on the
learned manifold, and can be scored as moments rather than instruments. A phased plant gets a
per-phase envelope for free from the existing wrapper.

**Cost.** A high quantile will suppress mild perturbations along with noise; recall is part of
the measurement, not an assumption. An adaptive pooled envelope on a plant that *should* have
been phased is a weaker claim than ADR 0018's per-phase models, and is labelled as such.

**Default unchanged.** `MahalanobisModel()` is the ADR 0025 detector. Gating is opt-in
(`adaptive_joint_quantile`, or `--gated` on the eval script).

**Unmeasured on distillation until the gated row is logged.** This record ships the mechanism
and the tests that pin it. The 18.72 → ? number is a designed-protocol run, not a claim made
here in advance of that run.
