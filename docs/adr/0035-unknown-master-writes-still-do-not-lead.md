# ADR 0035 — Unknown-master D2 writes still do not lead; score them apart from known stations

- **Status:** Accepted
- **Date:** 2026-08-22
- **PART:** Cycle evaluation campaign (Atlas command ranking)
- **Supersedes:** nothing
- **Depends on:** [ADR 0027](0027-unknown-master-writes-are-not-maintenance.md),
  [ADR 0034](0034-command-lead-rate-zero-on-known-link-writes.md),
  [ADR 0014](0014-command-evidence-the-second-boundary-door-and-the-unrun-measurement.md)

## Context

ADR 0034 measured **led in 0 of 16** on the graded battery. Those issuers are `scada` and `hmi` —
already on the learned command graph — so ADR 0027's unknown-master contradiction does not apply.

The next honest test is a write from a device that **never commanded anyone** in baseline traffic.
The water plant now declares a silent `engineering` workstation. A dedicated corpus
(`synth-attack-water-unknown-master`) issues `ROGUE_COMMAND` from that node only. The breaking
harness classifies each command attack from the learned graph, not from the attack type name, and
prints two headlines.

Re-run: commit of this PART, seed 7, fitted on `synth-water-treatment-train`. Report:
`eval_runs/breaking/breaking-report-unknown-master.md`.

Of **4** unknown-master attacks, commands moved `unauthorised_control_activity` **up in 4** and
**led in 0**. Ranks after commands: 3, 2, 2, 2. `engineering_maintenance` still leads. Attack
confidence saturates (~1 uncalibrated) beside maintenance at the same ceiling, so alphabetical
tie-break keeps maintenance first.

The window is flooded with command-graph findings (hundreds per attack, 1450 over the live
capture). Many are `silent_command_relationship` from comparing a 24-hour live capture to a
five-day train graph. Untyped structure still **supports** maintenance. The unknown-master marker
contradicts it, but not enough to win a flood. The command-path calibrator on this corpus also
maps graph magnitudes into a low band (~0.25–0.37), which the unit tests already showed is a
tie, not a reversal.

## Decision

**Keep issuer kinds scored apart.** A pooled "led in n of m" is forbidden. Known-station 0/16
and unknown-master 0/4 are different measurements of different template splits.

**Do not retune templates, and do not fit a per-feature command calibrator on this battery, to
chase 70%.** Making maintenance lose to a silence flood we created by duration mismatch would
be a cheat. Pooled graph calibration remains the limit ADR 0027 already named.

The ≥70% contract is **unearned**, including on unknown-master writes we designed. Next is a
licence-confirmed public capture with honest command labels, not another synthetic knob.

## Consequences

**Gained.** The 0/16 can no longer be misread as "0027 was not wired." 0027 is wired. It is not
enough, on this corpus, to make the attack lead.

**Cost.** Category command-reasoning is still blocked on a labelled public command corpus, not
on another covariance or prior tweak.
