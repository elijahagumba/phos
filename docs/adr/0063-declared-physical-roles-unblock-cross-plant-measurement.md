# ADR 0063 — Declared physical roles unblock a new transfer measurement

- **Status:** Accepted
- **Date:** 2026-08-24
- **PART:** Clock B / Milestone 1 (cross-plant transfer)
- **Supersedes:** nothing
- **Depends on:** [ADR 0010](0010-declared-topology-and-the-granularity-hai-supports.md),
  [ADR 0062](0062-clock-b-freeze-before-optimise.md)

## Context

ADR 0062 froze PHOS Benchmark v1. The HAI→BATADAL transfer cell is **REFUSED** until a
declared shared plant-state schema exists. Different column names are not a protocol.
That refusal stands: the frozen table is not rewritten here.

Milestone 1 asked for loaders, a tag-normalisation layer, Atlas trained on SWaT/BATADAL,
and zero-shot evaluation on unseen HAI, logged under `eval_runs/log.jsonl`. SWaT is
form-gated in the registry (`itrust-swat-wadi`). The agent must not fetch it.

## Decision

**1. Canonical loaders live at `src/phos/atlas/data/`.**

The constitution's package is `phos`. There is no `src/atlas/data/` tree. BATADAL and HAI
<!-- evidence-ack: src/atlas/data/ — named only to say no such tree exists; the constitution's package is phos -->
read licence-confirmed prepared CSVs already on disk. SWaT raises `CorpusMissingError`
with reason `form-gated` when the files are absent.

**2. The shared schema is three declared physical roles, not native tags.**

Roles: `flow`, `pressure`, `pump_state`. Membership is documentation (BATADAL instrument
prefixes, HAI technical details, SWaT published FIT/PIT/P tags). Unmapped tags are
dropped. Averaging tags that share a role is a declared reduction. Tank levels, analyser
channels, turbine RPM, and setpoints stay plant-private so they cannot leak into the
shared space (ADR 0010: declared, never inferred from co-movement).

**3. Zero-shot uses source-only covariance and the public operating point.**

Fit ungated Mahalanobis on projected BATADAL train (SWaT joins only if present). Score
projected HAI test. Threshold **3.0**, seed **11**. No threshold search on HAI. No retune
of `joint_k`, `dwell_samples`, or Atlas templates.

**4. The result is a new log name. Frozen public rows stay frozen.**

Detector `atlas-mahalanobis-physical-roles` (logged as
`model:atlas-mahalanobis-physical-roles`). Dataset `zero-shot:hai-physical-roles`.
Do not reuse `hai` + `atlas-mahalanobis`. Caveat
`TRANSFER_IS_PHYSICAL_ROLES_NOT_IDENTICAL_PLANTS`.

Measured (seed 11, threshold 3.0, SWaT absent): **1078.99** FP/normal hour, window
recall **1.00**. Native in-plant HAI Mahalanobis **646.58** remains the public HAI
ruler. Transfer is louder. That is the measurement. Native Mahalanobis still wins
on HAI.

The Benchmark v1 HAI→BATADAL cell stays **REFUSED**. This three-role map is a new
protocol with its own log row, not a rewrite of the freeze.

**5. P1 stays a human conversation.** Intelligence / API / UI remain forbidden.

## Consequences

**Gained.** A declared, testable cross-plant protocol. SWaT absence is an honest refuse,
not a silent skip. The first BATADAL→HAI zero-shot number exists under a name that
cannot overwrite 646.58 / 18.72 / 0.104.

**Cost.** Three averaged roles are not the same plant. Units differ. A loud transfer
row is expected. Do not quiet it by retuning public knobs. Do not quote it as a
category win, a 10× stamp, or 2–3 pages/day.

## Alternatives considered

- **Fetch SWaT around the iTrust form.** Rejected. Form-gated means operator-provided.
- **Infer the map from co-movement.** Rejected. ADR 0010.
- **Z-score HAI with HAI train before scoring.** Rejected for the default path. That
  would use the target plant for scale. True zero-shot applies the source model as
  fitted.
- **Search a threshold on HAI test.** Rejected. ADR 0062: seed 11 is not a search
  dimension.
- **Rewrite the Benchmark v1 transfer cell.** Rejected. New log name; freeze stands.
